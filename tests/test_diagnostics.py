import unittest
import json
import sys
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

class PcInventoryTests(unittest.TestCase):
    def test_report_uses_only_whitelisted_fields_and_redacts_mac(self):
        data = {
            'System': {'Manufacturer': 'Vendor', 'Model': 'Model 1', 'SerialNumber': 'SUPERSECRET'},
            'Board': {'Manufacturer': 'Board maker', 'Product': 'B1', 'SerialNumber': 'BOARDSECRET'},
            'OS': {'Caption': 'Windows 11', 'Version': '10.0', 'BuildNumber': '22631', 'OSArchitecture': '64-bit'},
            'CPU': [{'Name': 'CPU'}],
            'Devices': [{'Class': 'Bluetooth', 'Name': 'Headphones AA:BB:CC:DD:EE:FF',
                         'Hardware': 'USB VID_1234&PID_5678', 'InstanceId': 'SERIAL-SECRET',
                         'DriverVersion': '1.2', 'Status': 'OK'}],
            'Warnings': ['Часть драйверов недоступна'], 'UserName': 'SECRETUSER'
        }
        text = diagnostics.pc_report(data)
        self.assertIn('Windows 11', text)
        self.assertIn('USB VID_1234&PID_5678', text)
        self.assertIn('[MAC скрыт]', text)
        for value in ('SUPERSECRET', 'BOARDSECRET', 'SERIAL-SECRET', 'SECRETUSER', 'AA:BB:CC:DD:EE:FF'):
            self.assertNotIn(value, text)

    @patch('diagnostics.sys.platform', 'win32')
    @patch('diagnostics.subprocess.run')
    def test_inventory_parses_valid_data(self, run):
        data = {'System': {'Model': 'PC'}, 'Devices': [], 'Warnings': []}
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(data), '')
        self.assertEqual(diagnostics.pc_inventory()['System']['Model'], 'PC')

    @patch('diagnostics.sys.platform', 'win32')
    @patch('diagnostics.subprocess.run')
    def test_inventory_rejects_invalid_json(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, 'not json', '')
        with self.assertRaisesRegex(RuntimeError, 'некорректные'): diagnostics.pc_inventory()

    @patch('diagnostics.sys.platform', 'win32')
    @patch('diagnostics.subprocess.run')
    def test_inventory_timeout_is_an_error(self, run):
        run.side_effect = subprocess.TimeoutExpired('powershell', 90)
        with self.assertRaises(RuntimeError): diagnostics.pc_inventory()

    @unittest.skipUnless(sys.platform == 'win32', 'Requires real Windows CIM and PnP')
    def test_real_windows_inventory_without_printing_private_data(self):
        data = diagnostics.pc_inventory()
        self.assertIsInstance(data['Devices'], list)
        self.assertGreater(len(data['Devices']), 0, 'PnP device collection failed on the Windows runner')
        self.assertIsNotNone(data.get('OS'), 'Windows version collection failed on the Windows runner')
        self.assertNotIn('SerialNumber', json.dumps(data))
        self.assertNotIn('InstanceId', json.dumps(data))
        self.assertNotIn('MacAddress', json.dumps(data))

if __name__ == '__main__': unittest.main()
