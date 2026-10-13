"""Windows Bluetooth front end with isolated Linux rendering."""
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from discovery import discover
from printer_ble import status as printer_status, send_raster
from render_bridge import render_job
from label_presets import PRESETS

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config' / 'paperang.json'


def discover_printers():
    devices = {}
    for device in discover():
        entry = devices.setdefault(device['address'], dict(name=device['name'], address=device['address'], transports=[]))
        entry['transports'].append(device['transport'])
    return list(devices.values())


def run_cli(args):
    """Legacy name: queries now use only the native BLE helper."""
    if len(args) != 3 or args[0] not in ('status', 'battery') or args[1] != '--address':
        raise ValueError('Unsupported query')
    return printer_status(args[2], battery_only=args[0] == 'battery')


def print_job(kind, content, address='', mode='sticker', real=False, renderer=render_job, sender=send_raster, settings=None):
    """Validate once, then send those exact raster bytes at most once."""
    if kind not in ('paragraph', 'image', 'cable') or not content.strip():
        raise ValueError('Enter text or choose an image first.')
    if real and not address.strip():
        raise ValueError('Find and select a printer first.')
    checked, raster = renderer(kind, content, mode, settings=settings)
    if real:
        try:
            sent = sender(address, raster, allow_paper_use=True)
        except Exception as exc:
            raise RuntimeError(f'Print did not complete: {exc or type(exc).__name__}. '
                               'Some paper may have printed. Check it before retrying.') from exc
        return {**checked, 'transmission': sent, 'paper_used': True}
    return checked


class App:
    def __init__(self, root):
        self.root = root
        self.busy = False
        self.events = queue.Queue()
        self.buttons = []
        root.title('Thermy9 — Machine labels & cable flags')
        root.geometry('820x800')
        root.minsize(780, 740)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', padding=7)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Thermy9', font=('Segoe UI', 24, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Paperang P2S • Bluetooth • Local printing', font=('Segoe UI', 11)).pack(anchor='w', pady=(0, 16))
        row = ttk.Frame(frame)
        row.pack(fill='x')
        self.button(row, 'Find printer', self.discover)
        self.button(row, 'Status', lambda: self.query('status'))
        self.button(row, 'Battery', lambda: self.query('battery'))
        ttk.Label(frame, text='Printer address (select a discovered device or paste its address)').pack(anchor='w', pady=(12, 3))
        self.address = ttk.Combobox(frame)
        self.address.pack(fill='x')
        try:
            self.address.set(json.loads(CONFIG.read_text(encoding='utf-8')).get('macaddress', ''))
        except (OSError, ValueError):
            pass
        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill='both', expand=True, pady=14)
        text_tab = ttk.Frame(self.tabs, padding=10)
        image_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(text_tab, text='Labels / text')
        self.tabs.add(image_tab, text='Image')
        cable_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(cable_tab, text='Cable flags (2 columns)')
        self.build_cable_tab(cable_tab)
        self.tabs.select(cable_tab)
        options = ttk.Frame(text_tab)
        options.pack(fill='x', pady=(0, 8))
        ttk.Label(options, text='Preset').grid(row=0, column=0, sticky='w')
        self.preset = ttk.Combobox(options, state='readonly', width=20,
                                  values=list(PRESETS))
        self.preset.set('Large label')
        self.preset.grid(row=1, column=0, padx=(0, 12))
        self.preset.bind('<<ComboboxSelected>>', self.apply_preset)
        ttk.Label(options, text='Font size (pixels)').grid(row=0, column=1, sticky='w')
        self.font_size = tk.StringVar(value='72')
        ttk.Spinbox(options, from_=24, to=160, increment=4, width=8,
                    textvariable=self.font_size).grid(row=1, column=1, padx=(0, 12))
        ttk.Label(options, text='Label length (mm)').grid(row=0, column=2, sticky='w')
        self.label_length = tk.StringVar(value='50')
        self.length_control = ttk.Spinbox(options, from_=20, to=200, increment=5, width=8,
                                          textvariable=self.label_length)
        self.length_control.grid(row=1, column=2, padx=(0, 12))
        self.bold = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text='Bold', variable=self.bold).grid(row=1, column=3, padx=(0, 12))
        self.align = ttk.Combobox(options, values=['left', 'center', 'right'], state='readonly', width=8)
        self.align.set('center')
        self.align.grid(row=1, column=4)
        extras = ttk.Frame(text_tab)
        extras.pack(fill='x', pady=(0, 8))
        ttk.Label(extras, text='Font').pack(side='left', padx=(0, 8))
        self.font_family = ttk.Combobox(extras, state='readonly', values=['sans', 'serif', 'mono'], width=8)
        self.font_family.set('sans')
        self.font_family.pack(side='left', padx=(0, 12))
        self.border = tk.BooleanVar(value=False)
        ttk.Checkbutton(extras, text='Border', variable=self.border).pack(side='left', padx=(0, 12))
        self.button(extras, 'Load example text', self.load_example)
        self.button(extras, 'Next style →', self.next_style)
        ttk.Label(text_tab, text='Labels use a fixed strip length, plus ~6 mm to tear off. Preview shows the printed layout.',
                  wraplength=700).pack(anchor='w', pady=(0, 8))
        self.text = tk.Text(text_tab, height=7, wrap='word', font=('Segoe UI', 13))
        self.text.pack(fill='both', expand=True)
        self.text.insert('1.0', 'Hello from Thermy9!')
        self.image_path = tk.StringVar()
        ttk.Entry(image_tab, textvariable=self.image_path).pack(fill='x', pady=6)
        image_buttons = ttk.Frame(image_tab)
        image_buttons.pack(fill='x')
        self.button(image_buttons, 'Choose image…', self.choose_image)
        self.mode = ttk.Combobox(image_tab, values=['sticker', 'photo'], state='readonly')
        self.mode.set('sticker')
        self.mode.pack(anchor='w', pady=12)
        ttk.Label(image_tab, text='Sticker: logos and line art. Photo: dithered photographs.\nImage printing is experimental; inspect the first print.').pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x')
        self.button(row, 'Preview (no paper)', lambda: self.print_current(False))
        self.button(row, 'Print once (uses paper)', lambda: self.print_current(True))
        self.status = tk.StringVar(value='Ready. Keep Docker Desktop running for text and image rendering.')
        ttk.Label(frame, textvariable=self.status, wraplength=700).pack(anchor='w', pady=10)
        self.output = tk.Text(frame, height=10, wrap='word', state='disabled', font=('Consolas', 10))
        self.output.pack(fill='both', expand=True)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def button(self, parent, label, callback):
        button = ttk.Button(parent, text=label, command=callback)
        button.pack(side='left', padx=(0, 8))
        self.buttons.append(button)

    def build_cable_tab(self, tab):
        ttk.Label(tab, text='One line = one cable flag. Repeat lines for copies; cut between rows and fold the centre.\nLeft text aligns to the left end, right text to the right end. Blank lines preserve row positions.',
                  wraplength=720).pack(anchor='w', pady=(0, 8))
        grid = ttk.Frame(tab)
        grid.pack(fill='x')
        self.cable_settings = {}
        controls = [('Width mm', 'width_mm', 44, 20, 44, 1), ('Row height mm', 'row_mm', 12, 5, 30, 1),
                    ('Row gap mm', 'gap_mm', 2, 0, 10, .5), ('Fold gap mm', 'fold_mm', 4, 0, 12, .5),
                    ('Font px', 'font_size', 32, 16, 100, 2), ('Corner radius mm', 'radius_mm', 1.5, 0, 5, .5),
                    ('Border px (0=off)', 'stroke', 2, 0, 8, 1)]
        for i, (label, key, default, low, high, step) in enumerate(controls):
            r, c = (i // 4) * 2, i % 4
            ttk.Label(grid, text=label).grid(row=r, column=c, sticky='w', padx=5)
            variable = tk.StringVar(value=str(default))
            self.cable_settings[key] = variable
            ttk.Spinbox(grid, from_=low, to=high, increment=step, width=13, textvariable=variable).grid(row=r+1, column=c, sticky='w', padx=5, pady=(0, 6))
        self.cable_border = ttk.Combobox(grid, state='readonly', values=['Whole row', 'Each half'], width=15)
        self.cable_border.set('Whole row')
        ttk.Label(grid, text='Border around').grid(row=2, column=3, sticky='w', padx=5)
        self.cable_border.grid(row=3, column=3, padx=5)
        toggles = ttk.Frame(tab)
        toggles.pack(fill='x', pady=6)
        self.cable_mirror = tk.BooleanVar(value=True)
        self.cable_bold = tk.BooleanVar(value=True)
        self.cable_fold_mark = tk.BooleanVar(value=False)
        ttk.Checkbutton(toggles, text='Repeat left text on right', variable=self.cable_mirror,
                        command=self.toggle_cable_mirror).pack(side='left')
        ttk.Checkbutton(toggles, text='Bold', variable=self.cable_bold).pack(side='left', padx=10)
        ttk.Checkbutton(toggles, text='Dotted fold line', variable=self.cable_fold_mark).pack(side='left')
        columns = ttk.Frame(tab)
        columns.pack(fill='both', expand=True)
        columns.columnconfigure(0, weight=1)
        columns.columnconfigure(1, weight=1)
        columns.rowconfigure(1, weight=1)
        ttk.Label(columns, text='Left end — one label per line').grid(row=0, column=0, sticky='w')
        ttk.Label(columns, text='Right end — uncheck repeat to edit').grid(row=0, column=1, sticky='w')
        self.cable_left = tk.Text(columns, height=6, width=25, wrap='none', font=('Consolas', 12))
        self.cable_right = tk.Text(columns, height=6, width=25, wrap='none', font=('Consolas', 12))
        self.cable_left.grid(row=1, column=0, sticky='nsew', padx=(0, 8))
        self.cable_right.grid(row=1, column=1, sticky='nsew')
        self.cable_left.insert('1.0', 'PC-01\nPC-01\nSW-02\nNAS-01')
        self.cable_right.insert('1.0', self.cable_left.get('1.0', 'end-1c'))
        self.cable_right.configure(state='disabled')
        self.cable_left.edit_modified(False)
        self.cable_left.bind('<<Modified>>', self.sync_cable_right)
        ttk.Label(tab, text='Width is limited to the ~44 mm printable strip. Dimensions are approximate. Up to 50 rows; Print once sends the whole batch.',
                  wraplength=720).pack(anchor='w', pady=(6, 0))

    def toggle_cable_mirror(self):
        self.cable_right.configure(state='normal')
        if self.cable_mirror.get():
            self.cable_right.delete('1.0', 'end')
            self.cable_right.insert('1.0', self.cable_left.get('1.0', 'end-1c'))
            self.cable_right.configure(state='disabled')
        elif not self.cable_right.get('1.0', 'end-1c'):
            self.cable_right.insert('1.0', self.cable_left.get('1.0', 'end-1c'))

    def sync_cable_right(self, _event=None):
        if self.cable_left.edit_modified():
            self.cable_left.edit_modified(False)
            if self.cable_mirror.get():
                self.toggle_cable_mirror()

    def apply_preset(self, _event=None):
        settings = PRESETS[self.preset.get()]['settings']
        self.font_size.set(str(settings['font_size']))
        self.label_length.set(str(settings['label_length_mm']))
        self.bold.set(settings['bold'])
        self.align.set(settings['align'])
        self.font_family.set(settings['font_family'])
        self.border.set(settings['border'])
        self.length_control.state(['disabled'] if self.preset.get() == 'Note' else ['!disabled'])

    def load_example(self):
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', PRESETS[self.preset.get()]['sample'])

    def next_style(self):
        names = list(PRESETS)
        self.preset.set(names[(names.index(self.preset.get()) + 1) % len(names)])
        self.apply_preset()

    def show_preview(self, result):
        if not result.get('preview_png'):
            return
        window = tk.Toplevel(self.root)
        window.title('Print preview — no paper used')
        window.geometry('640x650')
        ttk.Label(window, text=f"{result['width']} dots wide • ~{result['estimated_length_mm']:.1f} mm + 6 mm feed",
                  padding=10).pack(anchor='w')
        if 'rows' in result:
            ttk.Label(window, text=f"{result['rows']} rows / cable flags • {result['left_labels']} left labels • {result['right_labels']} right labels",
                      padding=(10, 0, 10, 10)).pack(anchor='w')
        frame = ttk.Frame(window)
        frame.pack(fill='both', expand=True)
        canvas = tk.Canvas(frame, background='#dddddd')
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        window.preview_image = tk.PhotoImage(data=result['preview_png'])
        canvas.create_image(12, 12, anchor='nw', image=window.preview_image)
        canvas.configure(scrollregion=canvas.bbox('all'))

    def choose_image(self):
        path = filedialog.askopenfilename(filetypes=[('Images', '*.png *.jpg *.jpeg *.bmp *.gif'), ('All files', '*.*')])
        if path:
            self.image_path.set(path)

    def start(self, label, action, done=None):
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.state(['disabled'])
        self.status.set(label)
        def worker():
            try:
                self.events.put((True, action(), done))
            except Exception as exc:
                self.events.put((False, str(exc) or type(exc).__name__, None))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            ok, result, done = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for button in self.buttons:
                button.state(['!disabled'])
            self.status.set('Done.' if ok else 'Operation failed. See details below.')
            self.output.configure(state='normal')
            self.output.delete('1.0', 'end')
            display = {k: v for k, v in result.items() if k != 'preview_png'} if ok and isinstance(result, dict) else result
            self.output.insert('end', json.dumps(display, indent=2, ensure_ascii=False) if ok else display)
            self.output.configure(state='disabled')
            if done and ok:
                done(result)
        self.root.after(100, self.poll)

    def discover(self):
        def found(devices):
            addresses = [device['address'] for device in devices]
            self.address['values'] = addresses
            if len(addresses) == 1:
                self.address.set(addresses[0])
            self.status.set(f'Found {len(addresses)} printer(s). Select an address.' if addresses else 'No printer found. Turn it on, move it closer, and disconnect the phone app, then scan again.')
        self.start('Scanning for printers…', discover_printers, found)

    def query(self, command):
        address = self.address.get().strip()
        if not address:
            self.status.set('Find and select a printer first.')
            return
        self.start(f'Reading {command}…', lambda: run_cli([command, '--address', address]))

    def print_current(self, real):
        kind = ('paragraph', 'image', 'cable')[self.tabs.index('current')]
        content = self.text.get('1.0', 'end-1c') if kind == 'paragraph' else self.image_path.get()
        address, mode = self.address.get().strip(), self.mode.get()
        settings = None
        if kind == 'cable':
            content = json.dumps(dict(left=self.cable_left.get('1.0', 'end-1c'), right=self.cable_right.get('1.0', 'end-1c')))
            try:
                settings = {key: float(value.get()) for key, value in self.cable_settings.items()}
            except ValueError:
                self.status.set('Use numbers for cable dimensions, font size and border thickness.')
                return
            settings.update(mirror=self.cable_mirror.get(), bold=self.cable_bold.get(),
                            fold_mark=self.cable_fold_mark.get(), border_mode=self.cable_border.get())
        if kind == 'paragraph':
            try:
                settings = dict(font_size=int(self.font_size.get()), label_length_mm=int(self.label_length.get()),
                                layout='note' if self.preset.get() == 'Note' else 'label',
                                bold=self.bold.get(), align=self.align.get(),
                                font_family=self.font_family.get(), border=self.border.get())
                if not 24 <= settings['font_size'] <= 160 or not 20 <= settings['label_length_mm'] <= 200:
                    raise ValueError()
            except ValueError:
                self.status.set('Use a font size from 24 to 160 and a label length from 20 to 200 mm.')
                return
        self.start('Checking and printing once…' if real else 'Checking job without using paper…',
                   lambda: print_job(kind, content, address, mode, real, settings=settings),
                   None if real else self.show_preview)

    def close(self):
        if self.busy:
            self.status.set('Wait for the current operation to finish before closing.')
        else:
            self.root.destroy()


if __name__ == '__main__':
    window = tk.Tk()
    App(window)
    window.mainloop()
