import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from editor_presets import DEFAULTS, save_preset, read_presets
from editor import Editor


class EditorTests(unittest.TestCase):
    def test_only_two_defaults(self):
        self.assertEqual(list(DEFAULTS), ['Machine label', 'Cable flags'])

    def test_personal_preset_round_trip_and_update(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'presets.json'
            settings = dict(DEFAULTS['Cable flags']['settings'], padding_mm=3.5, trailing_mm=18,
                            columns='4', field_gap_mm=1.5, first_field_percent=40)
            save_preset('My GB10 labels', 'cable', settings, path)
            self.assertEqual(read_presets(path)['My GB10 labels']['settings'], settings)
            save_preset('My GB10 labels', 'cable', dict(settings, leading_mm=2), path)
            self.assertEqual(len(read_presets(path)), 1)
            self.assertEqual(read_presets(path)['My GB10 labels']['settings']['leading_mm'], 2)

    def test_bad_existing_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'presets.json'
            path.write_text('broken')
            with self.assertRaises(ValueError):
                save_preset('Test', 'cable', {}, path)
            self.assertEqual(path.read_text(), 'broken')

    def test_stale_preview_cannot_print(self):
        app = Editor.__new__(Editor)
        app.hw_busy = False
        app.rev = 3
        app.cached = (2, ({}, b'old raster'))
        app.hardware = Mock()
        app.print_preview()
        app.hardware.assert_not_called()

    def test_current_preview_sends_cached_raster_once(self):
        app = Editor.__new__(Editor)
        app.hw_busy = False
        app.rev = 3
        app.cached = (3, ({}, b'exact preview bytes'))
        app.address = Mock()
        app.address.get.return_value = 'test-printer'
        app.hardware = lambda action: action()
        with patch('editor.send_raster') as send, patch('editor.render_job') as render:
            app.print_preview()
        send.assert_called_once_with('test-printer', b'exact preview bytes', allow_paper_use=True)
        render.assert_not_called()


if __name__ == '__main__':
    unittest.main()
