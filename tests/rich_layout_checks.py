"""Run in the Linux renderer image, like cable_layout_checks.py."""
import base64
import json
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, '/opt')
from PIL import ImageFont, ImageDraw
from inline_text import RichText, ICONS, icon_image
import render


class RichLayoutChecks(unittest.TestCase):
    def setUp(self):
        self.rich = RichText(ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16))

    def test_five_mm_label(self):
        result = render.render(dict(kind='paragraph',text='PORT 3',settings=dict(label_length_mm=5,font_size=16,trailing_mm=0,border=True)))
        self.assertEqual(result['content_height'],round(5/.08472))
        self.assertEqual(len(base64.b64decode(result['raster'])),result['height']*72)

    def test_inline_styles_and_icons_are_measured(self):
        block = self.rich.layout('[b]NAME[/b] [size:24]BIG[/size][br][icon:network:18] PORT')
        parts = block['lines'][0]
        self.assertIn('Bold', parts[0]['font'].path)
        self.assertEqual(parts[-1]['font'].size,24)
        self.assertEqual(block['lines'][1][0]['icon'].size,(18,18))
        self.assertEqual(len(block['lines']),2)
        self.assertGreater(block['height'],24)

    def test_every_catalogue_icon_has_ink(self):
        for name in ICONS:
            with self.subTest(name=name):
                self.assertEqual(icon_image(name,24).getextrema(),(0,255))
        with self.assertRaises(ValueError): icon_image('missing',24)

    def test_hardware_models_are_parsed_as_icons(self):
        for name in ('rtx-5090','rtx-4090','gb10','dgx-spark','switch','router'):
            with self.subTest(name=name):
                block = self.rich.layout(f'[icon:{name}:64]')
                self.assertEqual(block['width'],64)
                self.assertIsNotNone(block['lines'][0][0]['icon'])

    def test_two_lines_remain_one_flag_and_repeat(self):
        result = render.render(dict(kind='cable',text=json.dumps(dict(left='[b]GB10[/b][br][regular]Port-3[/regular]',right='',copies=[2])),settings=dict(columns=2,font_size=16,row_mm=10)))
        self.assertEqual(result['source_rows'],1)
        self.assertEqual(result['rows'],2)

    def test_line_alignment_and_icon_overflow(self):
        block = self.rich.layout('[left]A[br][right]B')
        self.assertEqual(block['alignments'],['left','right'])
        with self.assertRaisesRegex(ValueError,'wider'):
            self.rich.layout('[icon:server:100]',max_width=50)
        with self.assertRaises(ValueError): self.rich.layout('[size:999]no[/size]')


if __name__ == '__main__': unittest.main()
