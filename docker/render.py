"""Single-job renderer. JSON on stdin/stdout; no printer access."""
import base64
import json
import io
from pathlib import Path
import sys
import tempfile
from PIL import Image, ImageDraw, ImageFont, ImageOps
from paperang_cli.render import render_image_job
from inline_text import RichText


def render_text(request):
    settings = request.get('settings') or {}
    size = int(settings.get('font_size', 72))
    length = float(settings.get('label_length_mm', 50))
    layout = settings.get('layout', 'label')
    align = settings.get('align', 'center')
    bold = bool(settings.get('bold', True))
    family = settings.get('font_family', 'sans')
    border = bool(settings.get('border', False))
    padding_mm = float(settings.get('padding_mm', 2.5))
    if not 0 <= padding_mm <= 20:
        raise ValueError('Text padding must be 0-20 mm.')
    padding = max(8 + int(settings.get('stroke', 2)) if border else 0, round(padding_mm * 576 / 44))
    available_width = 576 - 2 * padding
    if not 8 <= size <= 240 or not 5 <= length <= 500:
        raise ValueError('Font size must be 8-240 px and label length 5-500 mm.')
    if layout not in ('label', 'note') or align not in ('left', 'center', 'right'):
        raise ValueError('Invalid text layout')
    fonts = {'sans': 'DejaVuSans', 'serif': 'DejaVuSerif', 'mono': 'DejaVuSansMono'}
    if family not in fonts:
        raise ValueError('Choose sans, serif or mono font.')
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/' + fonts[family] + ('-Bold' if bold else '') + '.ttf', size)
    rich = RichText(font, settings.get('icon_size', 32), settings.get('line_gap', 4))
    block = rich.layout(request['text'], max_width=available_width)
    text_width, text_height = block['width'], block['height']
    vertical_inset = max(10, int(settings.get('stroke', 2)) + 8) if border else 4
    height = round(length / .08472) if layout == 'label' else text_height + 2*vertical_inset
    if text_height + 2*vertical_inset > height or height > 12000:
        raise ValueError('Text or icons do not fit vertically. Increase label length, or reduce text/icon size or line spacing.')
    canvas = Image.new('L', (576, height), 255)
    y = (height - text_height) / 2
    rich.paint(canvas, (padding,y), block, align, available_width)
    if border:
        stroke = int(settings.get('stroke', 2))
        radius = float(settings.get('radius_mm', 1.5))
        if not 0 <= stroke <= 16 or not 0 <= radius <= 20:
            raise ValueError('Invalid border thickness or radius.')
        if stroke:
            ImageDraw.Draw(canvas).rounded_rectangle((8, 8, 567, height - 9), radius=round(radius / .08472), outline=0, width=stroke)
    raster = ImageOps.invert(canvas).point(lambda p: 255 if p > 127 else 0, mode='1').tobytes()
    return dict(width=576, height=height, estimated_length_mm=round(height * .08472, 2),
                styling=dict(layout=layout, font_size=size, bold=bold, align=align, font_family=family, border=border,
                             label_length_mm=length if layout == 'label' else None)), raster


def render_cables(request):
    s = request.get('settings') or {}
    columns = json.loads(request['text'])
    column_count = int(s.get('columns', 2))
    if column_count not in (2, 4):
        raise ValueError('Choose 2 or 4 columns.')
    left = columns['left'].splitlines()
    right = left[:] if s.get('mirror', True) else columns['right'].splitlines()
    left_extra = columns.get('left_extra', '').splitlines() if column_count == 4 else []
    right_extra = (left_extra[:] if s.get('mirror', True) else columns.get('right_extra', '').splitlines()) if column_count == 4 else []
    count = max(map(len, (left, right, left_extra, right_extra)))
    if not 1 <= count <= 50:
        raise ValueError('Enter 1-50 label rows.')
    left += [''] * (count - len(left))
    right += [''] * (count - len(right))
    left_extra += [''] * (count - len(left_extra))
    right_extra += [''] * (count - len(right_extra))
    if not any(v.strip() for v in left + right + left_extra + right_extra):
        raise ValueError('Enter at least one cable name.')
    source_count = count
    copies = columns.get('copies', [])
    if not isinstance(copies, list) or len(copies) > source_count:
        raise ValueError('Provide one copy count per label row.')
    copies = copies + [1] * (source_count - len(copies))
    for index, quantity in enumerate(copies):
        if type(quantity) is not int or not 1 <= quantity <= 50:
            raise ValueError(f'Row {index + 1}: copies must be a whole number from 1 to 50.')
    count = sum(copies)
    if count > 50:
        raise ValueError(f'This batch contains {count} labels. Use at most 50 labels including copies, or split it into batches.')
    source_rows = [i for i, quantity in enumerate(copies) for _ in range(quantity)]
    left, right, left_extra, right_extra = [[values[i] for i in source_rows]
                                         for values in (left, right, left_extra, right_extra)]
    def number(key, default, low, high):
        value = float(s.get(key, default))
        if not low <= value <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
        return value
    width_mm = number('width_mm', 44, 5, 44)
    row_mm = number('row_mm', 12, 5, 100)
    gap_mm = number('gap_mm', 2, 0, 30)
    fold_mm = number('fold_mm', 4, 0, 30)
    radius_mm = number('radius_mm', 1.5, 0, 20)
    stroke = int(number('stroke', 2, 0, 16))
    size = int(number('font_size', 32, 8, 240))
    width = round(width_mm * 576 / 44)
    row = round(row_mm / .08472)
    gap = round(gap_mm / .08472)
    fold = round(fold_mm * 576 / 44)
    height = count * row + (count - 1) * gap
    if height > 12000:
        raise ValueError('Batch is too long (about 1 metre maximum). Split the rows into smaller batches.')
    canvas = Image.new('L', (576, height), 255)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans' + ('-Bold' if s.get('bold', True) else '') + '.ttf', size)
    rich = RichText(font, s.get('icon_size', 32), s.get('line_gap', 4))
    x0, x1 = (576 - width) // 2, (576 + width) // 2 - 1
    midpoint = 288
    padding = stroke + round(number('padding_mm', 2.5, 0, 20) * 576 / 44)
    half_width = width // 2 - fold // 2 - 2 * padding
    field_gap = round(number('field_gap_mm', 1, 0, 20) * 576 / 44)
    first_fraction = number('first_field_percent', 40, 5, 95) / 100
    if column_count == 4 and half_width <= field_gap:
        raise ValueError('No room for four columns. Reduce text inset or fold/field gaps.')
    radius = min(round(radius_mm / .08472), (row - 2) // 2, width // 4)
    border_mode = s.get('border_mode', 'Whole row')
    if border_mode not in ('Whole row', 'Each half'):
        raise ValueError('Invalid border layout')
    # Keep columns aligned across the batch, but let a longer field borrow unused
    # space from its neighbour. The percentage is a preference, not a hard clip.
    splits = {}
    if column_count == 4:
        usable = half_width - field_gap
        for side, primary, extra in [('left', left, left_extra), ('right', right, right_extra)]:
            def widest(values):
                return max((rich.bbox(text.strip())[2] -
                            rich.bbox(text.strip())[0] for text in values), default=0)
            need_first, need_second = widest(primary), widest(extra)
            preferred = round(usable * first_fraction)
            if s.get('auto_field_widths', True):
                if need_first + need_second > usable:
                    raise ValueError(f'{side.capitalize()} side needs {(need_first + need_second + field_gap) * 44 / 576:.1f} mm for both fields; '
                                     f'only {half_width * 44 / 576:.1f} mm is available. Reduce text size, side inset or fold space, or increase label width.')
                preferred = max(need_first, min(preferred, usable - need_second))
            splits[side] = preferred
    guides = dict(fields=[], rows=[], fold=[midpoint - fold // 2, fold],
                  content_height=height)
    for i, (a, b) in enumerate(zip(left, right)):
        top = i * (row + gap)
        guides['rows'].append([x0, top, width, row])
        if stroke:
            boxes = [(x0, top, x1, top + row - 1)] if border_mode == 'Whole row' else [
                (x0, top, midpoint - fold // 2 - 1, top + row - 1),
                (midpoint + fold // 2, top, x1, top + row - 1)]
            for box in boxes:
                draw.rounded_rectangle(box, radius=radius, outline=0, width=stroke)
        fields = []
        for side, primary, extra, start in [('left', a, left_extra[i], x0 + padding),
                                           ('right', b, right_extra[i], x1 - padding - half_width)]:
            if column_count == 2:
                fields.append((primary.strip(), side, start, half_width, side + '_align'))
            else:
                first_width = splits[side]
                second_width = half_width - field_gap - first_width
                pair = [(primary.strip(), side + ' field 1', first_width, side + '_align'),
                        (extra.strip(), side + ' field 2', second_width, side + '_extra_align')]
                if s.get(side + '_swap', False):
                    pair.reverse()
                cursor = start
                for text, label, available, alignment_key in pair:
                    fields.append((text, label, cursor, available, alignment_key))
                    cursor += available + field_gap
        for text, side, start, available, alignment_key in fields:
            alignment = s.get(alignment_key, 'left' if side.startswith('left') else 'right')
            if alignment not in ('left', 'center', 'right'):
                raise ValueError(f'Invalid alignment for {side}.')
            guides['fields'].append([start, top + stroke + 4, available, row - 2 * (stroke + 4)])
            if not text:
                continue
            box = rich.bbox(text)
            tw, th = box[2] - box[0], box[3] - box[1]
            if tw > available or th > row - 2 * (stroke + 4):
                raise ValueError(f'Row {source_rows[i] + 1}, {side}: "{text}" does not fit. Reduce text size or inset, increase row/label size, or enable automatic field widths.')
            rich.paint(canvas, (start, top + (row - th) / 2), rich.layout(text), alignment, available)
        if s.get('fold_mark', False):
            for y in range(top + 8, top + row - 8, 12):
                draw.line((midpoint, y, midpoint, min(y + 5, top + row - 8)), fill=0, width=1)
    raster = ImageOps.invert(canvas).point(lambda p: 255 if p > 127 else 0, mode='1').tobytes()
    return dict(width=576, height=height, rows=count, source_rows=source_count, copies=copies, columns=column_count, left_labels=sum(bool(x.strip()) for x in left),
                right_labels=sum(bool(x.strip()) for x in right), estimated_length_mm=round(height * .08472, 1),
                guides=guides, styling={**s, 'layout': 'cable_flags'}), raster


def render(request):
    kind = request['kind']
    if kind == 'paragraph':
        metadata, raster = render_text(request)
    elif kind == 'cable':
        metadata, raster = render_cables(request)
    elif kind == 'image':
        mode = request.get('mode', 'sticker')
        if mode not in ('sticker', 'photo'):
            raise ValueError('Invalid image mode')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input-image'
            path.write_bytes(base64.b64decode(request['image'], validate=True))
            result = render_image_job(path, printer_width=576, mode=mode,
                                      conversion='dither' if mode == 'photo' else 'threshold',
                                      advance_mm_per_px=0.08472, max_length_mm=200,
                                      fit_mode='fit-within-length')
        metadata = dict(width=result.width, height=result.height,
                        estimated_length_mm=result.estimated_length_mm, styling=result.styling.to_dict())
        raster = result.bitstream
    else:
        raise ValueError('Unsupported job')
    settings = request.get('settings') or {}
    leading_mm = float(settings.get('leading_mm', 0))
    trailing_mm = float(settings.get('trailing_mm', 14))
    if not 0 <= leading_mm <= 100 or not 0 <= trailing_mm <= 100:
        raise ValueError('Start and end paper margins must be 0-100 mm.')
    leading_rows, trailing_rows = round(leading_mm / .08472), round(trailing_mm / .08472)
    raster = bytes(leading_rows * 72) + raster + bytes(trailing_rows * 72)
    metadata['content_height'] = metadata['height']
    metadata['height'] += leading_rows + trailing_rows
    metadata.update(leading_rows=leading_rows, trailing_rows=trailing_rows,
                    leading_mm=leading_mm, trailing_mm=trailing_mm,
                    estimated_length_mm=round(metadata['height'] * .08472, 1))
    if not 0 < metadata['height'] <= 12000 or len(raster) != metadata['height'] * 72:
        raise ValueError('Unexpected raster size')
    preview = ImageOps.invert(Image.frombytes('1', (576, metadata['height']), raster).convert('L'))
    stream = io.BytesIO()
    preview.save(stream, format='PNG')
    return dict(**metadata, raster=base64.b64encode(raster).decode('ascii'),
                preview_png=base64.b64encode(stream.getvalue()).decode('ascii'))


if __name__ == '__main__':
    try:
        request = json.loads(sys.stdin.read(32 * 1024 * 1024))
        print(json.dumps(dict(status='ok', result=render(request))))
    except Exception as exc:
        print(json.dumps(dict(status='error', message=str(exc))))
        sys.exit(1)
