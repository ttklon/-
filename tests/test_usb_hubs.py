import ctypes
import sys
import unittest
from usb_hubs import HubDescriptor, NodeInformation, IOCTL_USB_GET_NODE_INFORMATION, hub_report, switching_description, windows_hubs

class HubTests(unittest.TestCase):
    def test_windows_packed_structure(self):
        self.assertEqual(ctypes.sizeof(HubDescriptor), 71)
        self.assertEqual(ctypes.sizeof(NodeInformation), 76)
        self.assertEqual(IOCTL_USB_GET_NODE_INFORMATION, 0x220408)
        self.assertEqual(HubDescriptor.characteristics.offset, 3)
    def test_report_and_errors(self):
        report = hub_report([{'model':'USB VID_ABCD&PID_1234','ports':4,'characteristics':9},
                             {'model':'другой','error':'код 5'}])
        self.assertIn('по отдельным портам', report)
        self.assertIn('код 5', report)
        self.assertIn('не гарантия', report)
        self.assertIn('не отключала', report)
        self.assertEqual(switching_description(0), 'групповое')
        self.assertEqual(switching_description(2), 'не поддерживается')
    @unittest.skipUnless(sys.platform == 'win32', 'Requires Windows USB hubs')
    def test_real_windows_enumeration(self):
        hubs = windows_hubs()
        self.assertGreater(len(hubs), 0, 'No hub interfaces on Windows runner')
        self.assertTrue(any('characteristics' in h for h in hubs), f'No descriptors read: {hubs}')
        for h in hubs:
            self.assertNotIn('path', h)
            self.assertNotIn('\\\\?', str(h))

if __name__ == '__main__': unittest.main()
