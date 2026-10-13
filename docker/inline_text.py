"""Small deterministic rich-text and monochrome icon renderer; no emoji fonts."""
import json
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

ICONS = json.loads(Path(__file__).with_name('icons.json').read_text())
TOKEN = re.compile(r'(\[icon:[a-z0-9-]+(?::\d+)?\]|\[/?b\]|\[/?regular\]|\[size:\d+\]|\[/size\]|\[br\]|\[left\]|\[center\]|\[right\]|\n)')


def icon_image(name, size):
    if name not in ICONS:
        raise ValueError(f'Unknown icon: {name}. Choose one from the icon library.')
    image = Image.new('L', (size, size), 255)
    draw = ImageDraw.Draw(image)
    scale = (size - 2) / 24
    def pos(value):
        return 1 + value * scale
    stroke = max(1, round(size / 12))
    for kind, *v in ICONS[name]:
        if kind == 'text':
            x, y, font_size, text = v
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', max(1, round(font_size*scale)))
            draw.text((pos(x), pos(y)), text, font=font, fill=0, anchor='ms')
        elif kind == 'circle':
            x, y, r = v
            draw.ellipse(tuple(pos(n) for n in (x-r,y-r,x+r,y+r)), outline=0, width=stroke)
        elif kind == 'rect':
            x,y,w,h = v
            draw.rectangle(tuple(pos(n) for n in (x,y,x+w,y+h)), outline=0, width=stroke)
        else:
            points = [(pos(v[i]),pos(v[i+1])) for i in range(0,len(v),2)]
            if kind == 'polygon':
                points.append(points[0])
            draw.line(points, fill=0, width=stroke, joint='curve')
    return image


class RichText:
    def __init__(self, font, icon_size=32, line_gap=4):
        self.font = font
        self.icon_size = int(icon_size)
        self.line_gap = int(line_gap)
        if not 8 <= self.icon_size <= 240 or not 0 <= self.line_gap <= 100:
            raise ValueError('Icon size must be 8–240 px and line spacing 0–100 px.')
        self.measure = ImageDraw.Draw(Image.new('L', (1,1)))

    def layout(self, text, max_width=None):
        lines, line, alignments = [], [], []
        line_align = None
        sizes = [self.font.size]
        bold = ['Bold' in str(self.font.path)]
        def finish():
            nonlocal line, line_align
            while line and line[-1]['text'].isspace():
                line.pop()
            lines.append(line)
            alignments.append(line_align)
            line = []
            line_align = None
        for part in TOKEN.split(text):
            if not part:
                continue
            if part in ('\n', '[br]'):
                finish()
                continue
            if part in ('[left]', '[center]', '[right]'):
                line_align = part[1:-1]; continue
            if part == '[regular]':
                bold.append(False); continue
            if part == '[/regular]':
                if len(bold) > 1: bold.pop()
                continue
            if part == '[b]':
                bold.append(True); continue
            if part == '[/b]':
                if len(bold) > 1: bold.pop()
                continue
            if part.startswith('[size:'):
                size = int(part[6:-1])
                if not 8 <= size <= 240: raise ValueError('Text size must be 8–240 px.')
                sizes.append(size); continue
            if part == '[/size]':
                if len(sizes) > 1: sizes.pop()
                continue
            font_path = str(self.font.path).replace('-Bold.ttf', '.ttf')
            if bold[-1]: font_path = font_path.replace('.ttf', '-Bold.ttf')
            font = ImageFont.truetype(font_path, sizes[-1])
            pieces = [part] if part.startswith('[icon:') else re.findall(r'\s+|\S+', part)
            for piece in pieces:
                icon = None
                if piece.startswith('[icon:'):
                    values = piece[1:-1].split(':')
                    size = int(values[2]) if len(values) == 3 else self.icon_size
                    if not 8 <= size <= 240: raise ValueError('Icon size must be 8–240 px.')
                    icon = icon_image(values[1], size)
                    box = (0,0,size,size)
                else:
                    box = self.measure.textbbox((0,0),piece,font=font)
                width = box[2]-box[0]
                if max_width is not None and width > max_width:
                    raise ValueError('A word or icon is wider than the label. Reduce its size or the side inset.')
                if max_width is not None and line and sum(p['width'] for p in line)+width > max_width:
                    finish()
                if not line and piece.isspace(): continue
                line.append(dict(text=piece,font=font,icon=icon,box=box,width=width,height=box[3]-box[1]))
        finish()
        heights = [max((p['height'] for p in line),default=max(1,self.font.size//2)) for line in lines]
        widths = [sum(p['width'] for p in line) for line in lines]
        return dict(lines=lines, heights=heights, widths=widths, alignments=alignments, width=max(widths,default=0),
                    height=sum(heights)+self.line_gap*(len(lines)-1))

    def bbox(self, text):
        layout = self.layout(text)
        return (0,0,layout['width'],layout['height'])

    def paint(self, image, xy, layout, align='left', area_width=None):
        draw = ImageDraw.Draw(image)
        y = xy[1]
        area_width = layout['width'] if area_width is None else area_width
        for line, height, width, line_align in zip(layout['lines'],layout['heights'],layout['widths'],layout['alignments']):
            x = xy[0] + {'left':0,'center':(area_width-width)/2,'right':area_width-width}[line_align or align]
            for part in line:
                top = y + (height-part['height'])/2
                if part['icon']:
                    image.paste(part['icon'], (round(x),round(top)))
                else:
                    box = part['box']
                    draw.text((x-box[0],top-box[1]),part['text'],font=part['font'],fill=0)
                x += part['width']
            y += height+self.line_gap
