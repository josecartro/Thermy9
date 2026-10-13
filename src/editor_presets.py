"""Two built-in starting points and atomic storage for personal presets."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESET_FILE = ROOT / 'config' / 'my-presets.json'
COMMON = dict(leading_mm=0, trailing_mm=14, padding_mm=2.5, stroke=2,
              radius_mm=1.5, bold=True, border=True, font_family='sans', align='center')
DEFAULTS = {
    'Machine label': dict(kind='paragraph', settings=dict(COMMON, font_size=64,
                          label_length_mm=30, layout='label')),
    'Cable flags': dict(kind='cable', settings=dict(COMMON, font_size=32, width_mm=44,
                       row_mm=10, gap_mm=2, fold_mm=4, mirror=True, columns='2',
                       field_gap_mm=1, first_field_percent=40,
                       left_swap=False, right_swap=False, left_align='left',
                       left_extra_align='left', right_align='right', right_extra_align='right',
                       fold_mark=False, border_mode='Whole row')),
}


def read_presets(path=PRESET_FILE):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Personal preset file must contain an object')
    for name, item in data.items():
        if not isinstance(name, str) or not isinstance(item, dict) or item.get('kind') not in ('paragraph', 'cable', 'image') or not isinstance(item.get('settings'), dict):
            raise ValueError('Invalid personal preset file')
    return data


def save_preset(name, kind, settings, path=PRESET_FILE):
    name = name.strip()
    if not name or len(name) > 80 or name in DEFAULTS:
        raise ValueError('Use a personal preset name (1–80 characters), different from the two defaults.')
    data = read_presets(path)
    data[name] = dict(kind=kind, settings=dict(settings))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)
