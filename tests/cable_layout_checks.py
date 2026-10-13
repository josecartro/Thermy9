"""Run inside the renderer container with /opt on sys.path; no printer access."""
import itertools
import json
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, '/opt')
import render
from PIL import ImageDraw


class CableLayoutChecks(unittest.TestCase):
    def test_row_multipliers_repeat_complete_labels(self):
        for columns in (2, 4):
            with self.subTest(columns=columns):
                request = dict(kind='cable', settings=dict(columns=columns, font_size=16,
                    mirror=False, right_swap=True, row_mm=10, gap_mm=2, leading_mm=3, trailing_mm=14),
                    text=json.dumps(dict(left='NAME-A\nNAME-B',left_extra='P1\nP2',
                        right='OTHER-A\nOTHER-B', right_extra='P3\nP4', copies=[4,2])))
                result = render.render(request)
                import base64
                raster = base64.b64decode(result['raster'])
                row, gap = round(10/.08472), round(2/.08472)
                start = result['leading_rows']
                labels = [raster[(start+i*(row+gap))*72:(start+i*(row+gap)+row)*72] for i in range(6)]
                self.assertEqual(result['source_rows'], 2)
                self.assertEqual(result['rows'], 6)
                self.assertTrue(all(label == labels[0] for label in labels[:4]))
                self.assertEqual(labels[4], labels[5])
                self.assertNotEqual(labels[0], labels[4])
                self.assertEqual(result['height'], start+6*row+5*gap+result['trailing_rows'])

    def test_copy_defaults_and_invalid_quantities(self):
        request = dict(settings=dict(font_size=16), text=json.dumps(dict(left='A\nB',right='')))
        meta, _ = render.render_cables(request)
        self.assertEqual(meta['copies'], [1,1])
        for copies in ([0,1], [1.5,1], ['4',1], [True,1], [51,1], [30,30], [1,1,1]):
            with self.subTest(copies=copies), self.assertRaises(ValueError):
                render.render_cables(dict(request,text=json.dumps(dict(left='A\nB',right='',copies=copies))))

    def test_swaps_and_every_field_alignment(self):
        original = ImageDraw.ImageDraw.text
        for left_swap, right_swap in itertools.product((False, True), repeat=2):
            for alignment in ('left', 'center', 'right'):
                with self.subTest(left=left_swap, right=right_swap, alignment=alignment):
                    calls = []
                    def record(draw, xy, text, **kwargs):
                        box = draw.textbbox((0, 0), text, font=kwargs['font'])
                        calls.append((text, xy[0] + box[0], box[2] - box[0]))
                        return original(draw, xy, text, **kwargs)
                    settings = dict(columns=4, font_size=16, bold=False, mirror=False,
                                    left_swap=left_swap, right_swap=right_swap)
                    for field in ('left', 'left_extra', 'right', 'right_extra'):
                        settings[field + '_align'] = alignment
                    with patch.object(ImageDraw.ImageDraw, 'text', record):
                        meta, raster = render.render_cables(dict(settings=settings, text=json.dumps(
                            dict(left='NAME', left_extra='P1', right='OTHER', right_extra='P2'))))
                    expected = (['P1', 'NAME'] if left_swap else ['NAME', 'P1']) + (['P2', 'OTHER'] if right_swap else ['OTHER', 'P2'])
                    self.assertEqual([call[0] for call in calls], expected)
                    for (_, ink_x, width), (x, y, available, h) in zip(calls, meta['guides']['fields']):
                        offset = dict(left=0, center=(available-width)/2, right=available-width)[alignment]
                        self.assertAlmostEqual(ink_x, x + offset)
                    self.assertEqual(len(raster), meta['height'] * 72)

    def test_mirrored_values_can_have_different_order(self):
        original = ImageDraw.ImageDraw.text
        calls = []
        def record(draw, xy, text, **kwargs):
            calls.append(text)
            return original(draw, xy, text, **kwargs)
        with patch.object(ImageDraw.ImageDraw, 'text', record):
            render.render_cables(dict(settings=dict(columns=4, font_size=16, bold=False,
                width_mm=42, padding_mm=2.5, right_swap=True, mirror=True), text=json.dumps(
                dict(left='GB10-BM-03', left_extra='Port-3', right='ignored', right_extra='ignored'))))
        self.assertEqual(calls, ['GB10-BM-03', 'Port-3', 'Port-3', 'GB10-BM-03'])


if __name__ == '__main__':
    unittest.main()
