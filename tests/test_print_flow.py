import sys
from pathlib import Path
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thermy9 import print_job
from printer_ble import pack, extract_frames, send_raster


class PrintFlowTests(unittest.TestCase):
    def setUp(self):
        self.raster = b'\x55' * 72
        self.render = Mock(return_value=({'paper_used': False}, self.raster))
        self.send = Mock(return_value={'sent': True})

    def test_check_never_prints(self):
        result = print_job('paragraph', '--a literal note', renderer=self.render, sender=self.send)
        self.assertFalse(result['paper_used'])
        self.send.assert_not_called()

    def test_real_print_sends_exact_checked_bytes_once(self):
        result = print_job('paragraph', 'Hej!', 'AA', real=True, renderer=self.render, sender=self.send)
        self.render.assert_called_once()
        self.send.assert_called_once_with('AA', self.raster, allow_paper_use=True)
        self.assertTrue(result['paper_used'])

    def test_failed_check_blocks_print(self):
        self.render.side_effect = RuntimeError('Render failed')
        with self.assertRaises(RuntimeError):
            print_job('paragraph', 'Hi', 'AA', real=True, renderer=self.render, sender=self.send)
        self.send.assert_not_called()

    def test_failed_print_is_not_retried(self):
        self.send.side_effect = RuntimeError('Connection lost')
        with self.assertRaisesRegex(RuntimeError, 'Check it before retrying'):
            print_job('paragraph', 'Hi', 'AA', real=True, renderer=self.render, sender=self.send)
        self.send.assert_called_once()

    def test_real_print_requires_target(self):
        with self.assertRaises(ValueError):
            print_job('paragraph', 'Hi', real=True, renderer=self.render, sender=self.send)
        self.render.assert_not_called()

    def test_transport_requires_approval(self):
        with self.assertRaises(ValueError):
            send_raster('AA', self.raster)

    def test_fragmented_real_battery_response(self):
        data = bytes.fromhex('021100010064cc4add9803')
        buffer = bytearray(data[:6])
        self.assertEqual(extract_frames(buffer), [])
        buffer.extend(data[6:])
        self.assertEqual(extract_frames(buffer), [(17, b'\x64')])
        self.assertEqual(buffer, b'')

    def test_corrupt_response_is_rejected(self):
        data = bytearray(pack(17, b'\x64'))
        data[-2] ^= 1
        with self.assertRaises(RuntimeError):
            extract_frames(data)


if __name__ == '__main__':
    unittest.main()
