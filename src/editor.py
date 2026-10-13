"""Live desktop label editor. Rendering stays in Linux; Bluetooth stays on Windows."""
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog

from editor_presets import DEFAULTS, read_presets, save_preset
from render_bridge import render_job
from printer_ble import send_raster, status as printer_status
from discovery import discover

ROOT = Path(__file__).resolve().parents[1]


class Editor:
    def __init__(self, root):
        self.root, self.events = root, queue.Queue()
        self.rev = 0
        self.pending = None
        self.render_active = self.hw_busy = self.hold = False
        self.cached = None
        self.values = {}
        root.title('Thermy9 — Live label editor')
        root.geometry('1220x880')
        root.minsize(1000, 680)
        ttk.Style().theme_use('clam')
        header = ttk.Frame(root, padding=12)
        header.pack(fill='x')
        ttk.Label(header, text='Thermy9', font=('Segoe UI', 22, 'bold')).pack(side='left')
        self.address = tk.StringVar()
        try:
            self.address.set(json.loads((ROOT / 'config/paperang.json').read_text()).get('macaddress', ''))
        except (OSError, ValueError):
            pass
        ttk.Entry(header, textvariable=self.address, width=20).pack(side='left', padx=20)
        self.hw_buttons = []
        for title, action in [('Find printer', self.find_printer), ('Status', self.status)]:
            b = ttk.Button(header, text=title, command=action)
            b.pack(side='left', padx=4)
            self.hw_buttons.append(b)
        self.print_button = ttk.Button(header, text='Print this preview once', command=self.print_preview, state='disabled')
        self.print_button.pack(side='right')
        body = ttk.Panedwindow(root, orient='horizontal')
        body.pack(fill='both', expand=True, padx=12)
        side = ttk.Frame(body, width=450)
        body.add(side, weight=0)
        scroller = tk.Canvas(side, width=440, highlightthickness=0)
        scroll = ttk.Scrollbar(side, orient='vertical', command=scroller.yview)
        scroll.pack(side='right', fill='y')
        scroller.pack(fill='both', expand=True)
        scroller.configure(yscrollcommand=scroll.set)
        controls = ttk.Frame(scroller, padding=(4, 0, 12, 12))
        item = scroller.create_window(0, 0, anchor='nw', window=controls)
        controls.bind('<Configure>', lambda e: scroller.configure(scrollregion=scroller.bbox('all')))
        scroller.bind('<Configure>', lambda e: scroller.itemconfigure(item, width=e.width))
        scroller.bind('<MouseWheel>', lambda e: scroller.yview_scroll(-int(e.delta / 120), 'units'))
        self.preset = ttk.Combobox(controls, state='readonly')
        self.preset.pack(fill='x')
        self.preset.bind('<<ComboboxSelected>>', lambda e: self.load_preset())
        ttk.Button(controls, text='Save settings as my preset…', command=self.save).pack(fill='x', pady=6)
        self.kind = tk.StringVar(value='cable')
        modes = ttk.Frame(controls)
        modes.pack(fill='x', pady=6)
        for title, value in [('Machine', 'paragraph'), ('Cable flags', 'cable'), ('Image', 'image')]:
            ttk.Radiobutton(modes, text=title, value=value, variable=self.kind, command=self.switch_mode).pack(side='left')
        self.text_frame = ttk.Frame(controls)
        self.text_frame.pack(fill='x')
        self.column_options = ttk.Frame(self.text_frame)
        self.column_options.pack(fill='x')
        self.choice(self.column_options, 'Columns (total across both sides)', 'columns', ['2', '4'], '2')
        ttk.Label(self.column_options, text='4 columns: [name | IP]  · fold ·  [name | IP]\nEach line is one label; repeat lines for copies.').pack(anchor='w')
        self.text_heading = ttk.Label(self.text_frame, text='Text / left side — field 1')
        self.text_heading.pack(anchor='w')
        self.left = tk.Text(self.text_frame, height=4, width=30, font=('Consolas', 12), undo=True)
        self.left.pack(fill='x', pady=4)
        self.left.insert('1.0', 'GB10-01\nGB10-01')
        self.left_extra_frame = ttk.Frame(self.text_frame)
        ttk.Label(self.left_extra_frame, text='Left side — field 2 (e.g. IP address)').pack(anchor='w')
        self.left_extra = tk.Text(self.left_extra_frame, height=4, width=30, font=('Consolas', 12), undo=True)
        self.left_extra.pack(fill='x', pady=4)
        self.right_frame = ttk.Frame(self.text_frame)
        self.right_frame.pack(fill='x')
        self.check(self.right_frame, 'Repeat both left fields on right', 'mirror', True)
        ttk.Label(self.right_frame, text='Right side — field 1').pack(anchor='w')
        self.right = tk.Text(self.right_frame, height=4, width=30, font=('Consolas', 12), undo=True)
        self.right.pack(fill='x', pady=4)
        self.right_extra_frame = ttk.Frame(self.right_frame)
        ttk.Label(self.right_extra_frame, text='Right side — field 2').pack(anchor='w')
        self.right_extra = tk.Text(self.right_extra_frame, height=4, width=30, font=('Consolas', 12), undo=True)
        self.right_extra.pack(fill='x', pady=4)
        for widget in (self.left, self.right, self.left_extra, self.right_extra):
            widget.edit_modified(False)
            widget.bind('<<Modified>>', lambda e, w=widget: self.text_changed(w))
        self.image_frame = ttk.Frame(controls)
        self.image_path = tk.StringVar()
        ttk.Button(self.image_frame, text='Choose image…', command=self.choose_image).pack(fill='x')
        ttk.Label(self.image_frame, textvariable=self.image_path, wraplength=390).pack(anchor='w')
        self.choice(self.image_frame, 'Image conversion', 'image_mode', ['sticker', 'photo'], 'sticker')
        self.text_options = ttk.LabelFrame(controls, text='Text', padding=8)
        self.text_options.pack(fill='x', pady=8)
        self.slider(self.text_options, 'Font size', 'font_size', 16, 160, 1, 32, 'px')
        self.slider(self.text_options, 'Text inset from side borders', 'padding_mm', 0, 8, .25, 2.5, 'mm')
        self.check(self.text_options, 'Bold', 'bold', True)
        self.machine_options = ttk.LabelFrame(controls, text='Machine label', padding=8)
        self.slider(self.machine_options, 'Label length', 'label_length_mm', 20, 200, 1, 30, 'mm')
        self.choice(self.machine_options, 'Alignment', 'align', ['left', 'center', 'right'], 'center')
        self.choice(self.machine_options, 'Font', 'font_family', ['sans', 'serif', 'mono'], 'sans')
        self.check(self.machine_options, 'Border', 'border', True)
        self.cable_options = ttk.LabelFrame(controls, text='Cable rows', padding=8)
        self.cable_options.pack(fill='x', pady=8)
        for title, key, low, high, step, default in [
            ('Width', 'width_mm', 20, 44, .5, 44), ('Row height', 'row_mm', 5, 30, .5, 10),
            ('Gap between rows', 'gap_mm', 0, 10, .5, 2), ('Space around fold', 'fold_mm', 0, 12, .5, 4)]:
            self.slider(self.cable_options, title, key, low, high, step, default, 'mm')
        self.choice(self.cable_options, 'Border around', 'border_mode', ['Whole row', 'Each half'], 'Whole row')
        self.check(self.cable_options, 'Dotted fold line', 'fold_mark', False)
        self.field_options = ttk.Frame(self.cable_options)
        self.slider(self.field_options, 'Gap between fields on each side', 'field_gap_mm', 0, 5, .25, 1, 'mm')
        self.slider(self.field_options, 'Width reserved for field 1 on each side', 'first_field_percent', 20, 80, 1, 40, '%')
        ttk.Label(self.field_options, text='Four columns have less room. Reduce font size if text does not fit; the preview will tell you which field.', wraplength=370).pack(anchor='w')
        self.border_options = ttk.LabelFrame(controls, text='Borders', padding=8)
        self.border_options.pack(fill='x', pady=8)
        self.slider(self.border_options, 'Thickness (0 = off)', 'stroke', 0, 8, 1, 2, 'px')
        self.slider(self.border_options, 'Corner radius (0 = square)', 'radius_mm', 0, 5, .25, 1.5, 'mm')
        paper = ttk.LabelFrame(controls, text='Paper before / after the print', padding=8)
        self.paper_options = paper
        paper.pack(fill='x', pady=8)
        self.slider(paper, 'Start blank margin', 'leading_mm', 0, 40, .5, 0, 'mm')
        self.slider(paper, 'End feed / tear-off space', 'trailing_mm', 0, 40, .5, 14, 'mm')
        ttk.Label(paper, text='Start at 0 to add no leading paper. Existing exposed paper cannot be retracted. End feed affects the blank area before the next print too. Dimensions are approximate.', wraplength=370).pack(anchor='w')
        preview = ttk.Frame(body, padding=(16, 0, 0, 0))
        body.add(preview, weight=1)
        ttk.Label(preview, text='Live print preview', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
        ttk.Label(preview, text='Updates automatically after edits. Includes start and end paper margins.').pack(anchor='w', pady=4)
        self.details = tk.StringVar(value='Preparing preview…')
        ttk.Label(preview, textvariable=self.details, wraplength=600).pack(anchor='w', pady=6)
        pframe = ttk.Frame(preview)
        pframe.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(pframe, background='#dce1e5', highlightthickness=0)
        ps = ttk.Scrollbar(pframe, orient='vertical', command=self.canvas.yview)
        ps.pack(side='right', fill='y')
        px = ttk.Scrollbar(preview, orient='horizontal', command=self.canvas.xview)
        px.pack(fill='x')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.configure(yscrollcommand=ps.set, xscrollcommand=px.set)
        self.canvas.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta / 120), 'units'))
        self.message = tk.StringVar(value='Ready')
        ttk.Label(root, textvariable=self.message, padding=12, wraplength=1150).pack(fill='x')
        self.refresh_presets()
        self.preset.set('Cable flags')
        self.load_preset()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def slider(self, parent, title, key, low, high, step, default, unit):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=2)
        ttk.Label(frame, text=f'{title} ({unit})').pack(anchor='w')
        var = tk.DoubleVar(value=default)
        self.values[key] = var
        tk.Scale(frame, from_=low, to=high, resolution=step, orient='horizontal',
                 variable=var, command=lambda _: self.changed(), highlightthickness=0,
                 borderwidth=0, length=350).pack(fill='x')

    def check(self, parent, title, key, default):
        var = tk.BooleanVar(value=default)
        self.values[key] = var
        ttk.Checkbutton(parent, text=title, variable=var, command=self.changed).pack(anchor='w')

    def choice(self, parent, title, key, choices, default):
        ttk.Label(parent, text=title).pack(anchor='w')
        var = tk.StringVar(value=default)
        self.values[key] = var
        field = ttk.Combobox(parent, values=choices, textvariable=var, state='readonly')
        field.pack(fill='x', pady=3)
        field.bind('<<ComboboxSelected>>', lambda e: self.changed())

    def refresh_presets(self):
        try:
            self.presets = {**DEFAULTS, **read_presets()}
        except (OSError, ValueError) as exc:
            self.presets = dict(DEFAULTS)
            self.message.set(f'Could not read personal presets: {exc}')
        self.preset['values'] = list(self.presets)

    def load_preset(self):
        preset = self.presets[self.preset.get()]
        self.hold = True
        self.kind.set(preset['kind'])
        base = DEFAULTS['Cable flags' if preset['kind'] == 'cable' else 'Machine label']['settings']
        for key, value in {**base, **preset['settings']}.items():
            if key in self.values:
                self.values[key].set(value)
        self.hold = False
        self.update_sections()
        self.changed()

    def switch_mode(self):
        if self.kind.get() != 'image':
            self.preset.set('Cable flags' if self.kind.get() == 'cable' else 'Machine label')
            self.load_preset()
        else:
            self.update_sections()
            self.changed()

    def update_sections(self):
        kind = self.kind.get()
        self.right_frame.pack_forget()
        if kind == 'cable':
            self.right_frame.pack(fill='x')
        for frame, show in [(self.text_frame, kind != 'image'),
                            (self.image_frame, kind == 'image'), (self.text_options, kind != 'image'),
                            (self.machine_options, kind == 'paragraph'), (self.cable_options, kind == 'cable'),
                            (self.border_options, kind != 'image')]:
            frame.pack_forget()
            if show:
                frame.pack(fill='x', pady=5, before=self.paper_options)
        self.update_columns()

    def update_columns(self):
        cable = self.kind.get() == 'cable'
        four = cable and self.values['columns'].get() == '4'
        self.column_options.pack_forget()
        if cable:
            self.column_options.pack(fill='x', before=self.text_heading)
        self.left_extra_frame.pack_forget()
        self.right_extra_frame.pack_forget()
        self.field_options.pack_forget()
        if four:
            self.left_extra_frame.pack(fill='x', before=self.right_frame)
            self.right_extra_frame.pack(fill='x')
            self.field_options.pack(fill='x')

    def save(self):
        name = simpledialog.askstring('Save personal preset', 'Name for these settings:', parent=self.root)
        if name is None:
            return
        try:
            save_preset(name, self.kind.get(), self.settings())
            self.refresh_presets()
            self.preset.set(name.strip())
            self.message.set(f'Saved “{name.strip()}”. Text is kept separately; the preset stores your layout settings.')
        except (OSError, ValueError) as exc:
            self.message.set(str(exc))

    def settings(self):
        result = {key: value.get() for key, value in self.values.items()}
        result['layout'] = 'label'
        return result

    def text_changed(self, widget):
        if widget.edit_modified():
            widget.edit_modified(False)
            self.changed()

    def changed(self):
        if self.hold:
            return
        if hasattr(self, 'field_options'):
            self.update_columns()
        if hasattr(self, 'right_extra'):
            for source, target in [(self.left, self.right), (self.left_extra, self.right_extra)]:
                target.configure(state='normal')
                if self.values['mirror'].get():
                    content = source.get('1.0', 'end-1c')
                    if target.get('1.0', 'end-1c') != content:
                        target.delete('1.0', 'end')
                        target.insert('1.0', content)
                        target.edit_modified(False)
                    target.configure(state='disabled')
        self.rev += 1
        self.cached = None
        self.print_button.state(['disabled'])
        if not hasattr(self, 'details'):
            return
        self.details.set('Updating… previous preview is not printable until the new layout is ready.')
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = self.root.after(500, self.render)

    def snapshot(self):
        kind = self.kind.get()
        content = self.left.get('1.0', 'end-1c')
        if kind == 'cable':
            content = json.dumps(dict(left=content, right=self.right.get('1.0', 'end-1c'),
                                     left_extra=self.left_extra.get('1.0', 'end-1c'),
                                     right_extra=self.right_extra.get('1.0', 'end-1c')))
        elif kind == 'image':
            content = self.image_path.get()
        return kind, content, self.values['image_mode'].get(), self.settings()

    def render(self):
        self.pending = None
        if self.render_active or self.cached:
            return
        self.render_active = True
        rev, args = self.rev, self.snapshot()
        def worker():
            try:
                self.events.put(('render', rev, render_job(*args), None))
            except Exception as exc:
                self.events.put(('render', rev, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, rev, value, error = self.events.get_nowait()
                if kind == 'render':
                    self.render_active = False
                    if rev != self.rev:
                        self.render()
                        continue
                    if error:
                        self.details.set(error)
                        self.canvas.delete('all')
                        continue
                    self.cached = (rev, value)
                    meta, raster = value
                    self.preview_image = tk.PhotoImage(data=meta['preview_png'])
                    self.canvas.delete('all')
                    self.canvas.create_image(12, 12, anchor='nw', image=self.preview_image)
                    self.canvas.configure(scrollregion=self.canvas.bbox('all'))
                    rows = f"{meta['rows']} rows · " if 'rows' in meta else ''
                    self.details.set(f"{rows}~{meta['estimated_length_mm']:.1f} mm total · Start {meta['leading_mm']:g} mm · End {meta['trailing_mm']:g} mm")
                    if not self.hw_busy:
                        self.print_button.state(['!disabled'])
                else:
                    self.hw_busy = False
                    for button in self.hw_buttons:
                        button.state(['!disabled'])
                    self.message.set(error or value)
                    if self.cached:
                        self.print_button.state(['!disabled'])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def hardware(self, action):
        if self.hw_busy:
            return
        self.hw_busy = True
        self.print_button.state(['disabled'])
        for button in self.hw_buttons:
            button.state(['disabled'])
        self.message.set('Working…')
        def worker():
            try:
                self.events.put(('hardware', 0, action(), None))
            except Exception as exc:
                self.events.put(('hardware', 0, None, str(exc) or type(exc).__name__))
        threading.Thread(target=worker, daemon=True).start()

    def print_preview(self):
        if self.hw_busy or not self.cached or self.cached[0] != self.rev:
            return
        address = self.address.get().strip()
        if not address:
            self.message.set('Select a printer first.')
            return
        raster = self.cached[1][1]
        def send():
            try:
                send_raster(address, raster, allow_paper_use=True)
            except Exception as exc:
                raise RuntimeError(f'Print stopped: {exc}. Check for a partial print before retrying.') from exc
            return 'Sent one copy of the preview. Check the paper before printing another.'
        self.hardware(send)

    def status(self):
        address = self.address.get().strip()
        if not address:
            self.message.set('Select a printer first.')
            return
        self.hardware(lambda: json.dumps(printer_status(address), ensure_ascii=False))

    def find_printer(self):
        self.hardware(lambda: 'Discovered: ' + ', '.join(sorted({d['address'] + ' ' + d['name'] for d in discover()})) + ' — enter the address above if needed.')

    def choose_image(self):
        path = filedialog.askopenfilename(filetypes=[('Images', '*.png *.jpg *.jpeg *.bmp *.gif'), ('All files', '*.*')])
        if path:
            self.image_path.set(path)
            self.changed()

    def close(self):
        if self.hw_busy:
            self.message.set('Wait for the printer operation to finish before closing.')
        else:
            self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    Editor(root)
    root.mainloop()
