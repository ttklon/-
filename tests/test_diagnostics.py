import unittest
from unittest.mock import patch
import subprocess
import diagnostics


class DiagnosticsTests(unittest.TestCase):
    def test_compare_and_report(self):
        before = {'old': {'InstanceId': 'old'}}
        after = {**before, 'USB\\VID_1234': {'InstanceId': 'USB\\VID_1234', 'FriendlyName': 'Test', 'Class': 'USB', 'Status': 'OK'}}
        new = diagnostics.compare(before, after)
        self.assertEqual(len(new), 1)
        self.assertIn('USB\\VID_1234', diagnostics.report(new))
        self.assertIn('не подтверждает', diagnostics.report(new))

    def test_no_device_is_not_proof(self):
        self.assertIn('не доказывает', diagnostics.report([]))

    @patch('diagnostics.sys.platform', 'win32')
    @patch('diagnostics.subprocess.run')
    def test_powershell_single_object(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '{"InstanceId":"USB\\\\VID_1234"}', '')
        self.assertIn('USB\\VID_1234', diagnostics.windows_devices())

    @patch('diagnostics.sys.platform', 'win32')
    @patch('diagnostics.subprocess.run')
    def test_powershell_error_not_empty_result(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, '', 'access denied')
        with self.assertRaisesRegex(RuntimeError, 'access denied'):
            diagnostics.windows_devices()

    @patch('diagnostics.sys.platform', 'win32')
    @patch('diagnostics.subprocess.run')
    def test_timeout(self, run):
        run.side_effect = subprocess.TimeoutExpired('powershell', 30)
        with self.assertRaises(RuntimeError): diagnostics.windows_devices()

if __name__ == '__main__': unittest.main()
