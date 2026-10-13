"""Label styles and editable examples, shared by the UI and rendering checks."""


def style(size, length, sample, *, family='sans', bold=True, border=False, align='center', layout='label'):
    return dict(sample=sample, settings=dict(font_size=size, label_length_mm=length,
                font_family=family, bold=bold, border=border, align=align, layout=layout))


PRESETS = {
    'Large label': style(72, 50, 'COFFEE\nBEANS'),
    'Extra-large label': style(104, 70, 'TOOLS'),
    'Small label': style(56, 30, 'SPARE\nPARTS'),
    'Spice jar': style(64, 35, 'OREGANO', family='serif', border=True),
    'Cable tag': style(40, 20, 'USB-C\nMONITOR', family='mono'),
    'Storage box': style(88, 60, 'WINTER\nCLOTHES', border=True),
    'Name tag': style(80, 40, 'HELLO\nAlex', border=True),
    'Address label': style(36, 45, 'Alex Example\n12 Sample Street\n123 45 Stockholm', bold=False, align='left'),
    'Price tag': style(96, 40, '49 kr', family='serif', border=True),
    'Date label': style(48, 30, 'PACKED\n2026-10-13', family='mono', border=True),
    'Minimal': style(64, 35, 'less is more', bold=False),
    'Classic serif': style(64, 50, 'From the\nkitchen', family='serif', bold=False, border=True),
    'Inventory': style(48, 40, 'BOX 009\nSHELF B-2', family='mono', align='left', border=True),
    'Thank you': style(64, 45, 'THANK YOU\nMade with care', family='serif'),
    'Note': style(54, 50, 'Remember to water\nthe plants.', bold=False, align='left', layout='note'),
}
