"""Read-only USB hub descriptor inspection on Windows; never switches ports."""
import ctypes
import re
import sys
from ctypes import wintypes

# USB_NODE_INFORMATION is packed in usbioctl.h; the hub descriptor is packed
# in usbspec.h. This is the documented read-only IOCTL used by USBView.
class HubDescriptor(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('length', ctypes.c_uint8), ('kind', ctypes.c_uint8),
                ('ports', ctypes.c_uint8), ('characteristics', ctypes.c_uint16),
                ('power_good', ctypes.c_uint8), ('current', ctypes.c_uint8),
                ('mask', ctypes.c_uint8 * 64)]

class HubInformation(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('descriptor', HubDescriptor), ('bus_powered', ctypes.c_uint8)]

class NodeInformation(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('node_type', ctypes.c_uint32), ('hub', HubInformation)]

class GUID(ctypes.Structure):
    _fields_ = [('Data1', ctypes.c_uint32), ('Data2', ctypes.c_uint16),
                ('Data3', ctypes.c_uint16), ('Data4', ctypes.c_uint8 * 8)]

class InterfaceData(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('InterfaceClassGuid', GUID),
                ('Flags', wintypes.DWORD), ('Reserved', ctypes.c_size_t)]

HUB_GUID = GUID(0xf18a0e88, 0xc30c, 0x11d0, (ctypes.c_uint8 * 8)(0x88,0x15,0x00,0xa0,0xc9,0x06,0xbe,0xd8))
IOCTL_USB_GET_NODE_INFORMATION = (0x22 << 16) | (258 << 2)


def switching_description(characteristics):
    return {0: 'групповое', 1: 'по отдельным портам',
            2: 'не поддерживается', 3: 'не поддерживается (значение 3)'}.get(characteristics & 3)


def hub_report(hubs):
    lines = ['CHAIRLIGHT — проверка USB-концентраторов (только чтение)', '',
             'Питание портов и устройства программа не отключала.',
             'Сведения о переключении заявлены концентратором; реальное отключение питания и работа в Windows не подтверждены.',
             'Для USB без передачи данных определить порт кресла автоматически может быть невозможно.', '']
    if not hubs:
        lines.append('Концентраторы не найдены Windows или сведения недоступны.')
    for i, hub in enumerate(hubs, 1):
        lines.append(f'Концентратор {i}: {hub["model"]}')
        if hub.get('error'):
            lines.append('  Не удалось прочитать дескриптор: ' + hub['error'])
        else:
            lines.append(f'  Портов: {hub["ports"]}; характеристики: 0x{hub["characteristics"]:04X}')
            lines.append('  Заявленное переключение питания: ' + switching_description(hub['characteristics']))
    lines += ['', 'Это не проверка управления креслом, не гарантия отключения 5 В и не идентификация USB-порта кресла.']
    return '\n'.join(lines)


def windows_hubs():
    if sys.platform != 'win32':
        raise RuntimeError('Проверка концентраторов работает только в Windows.')
    setup = ctypes.WinDLL('setupapi', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    setup.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    setup.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    setup.SetupDiEnumDeviceInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.POINTER(InterfaceData)]
    setup.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [wintypes.HANDLE, ctypes.POINTER(InterfaceData), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    setup.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
    setup.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.DeviceIoControl.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    invalid = ctypes.c_void_p(-1).value
    device_set = setup.SetupDiGetClassDevsW(ctypes.byref(HUB_GUID), None, None, 0x12)
    if device_set == invalid:
        raise RuntimeError(f'Windows не предоставила список концентраторов (код {ctypes.get_last_error()}).')
    hubs = []
    try:
        for index in range(1024):
            data = InterfaceData(); data.cbSize = ctypes.sizeof(data)
            if not setup.SetupDiEnumDeviceInterfaces(device_set, None, ctypes.byref(HUB_GUID), index, ctypes.byref(data)):
                code = ctypes.get_last_error()
                if code == 259: break
                raise RuntimeError(f'Не удалось перечислить концентраторы (код {code}).')
            required = wintypes.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(device_set, ctypes.byref(data), None, 0, ctypes.byref(required), None)
            if required.value < 6 or required.value > 65536:
                hubs.append({'model': 'неизвестная модель', 'error': 'не удалось получить путь интерфейса'}); continue
            detail = ctypes.create_string_buffer(required.value)
            ctypes.cast(detail, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if not setup.SetupDiGetDeviceInterfaceDetailW(device_set, ctypes.byref(data), detail, required.value, ctypes.byref(required), None):
                hubs.append({'model': 'неизвестная модель', 'error': f'код {ctypes.get_last_error()}'}); continue
            path = ctypes.wstring_at(ctypes.addressof(detail) + 4)
            match = re.search(r'(?i)vid_([0-9a-f]{4})&pid_([0-9a-f]{4})', path)
            model = ('USB VID_' + match[1].upper() + '&PID_' + match[2].upper()) if match else 'корневой или другой USB-концентратор'
            hub = {'model': model}
            # Like Microsoft USBView: open a hub and issue only GET_NODE_INFORMATION.
            handle = kernel.CreateFileW(path, 0x40000000, 3, None, 3, 0, None)
            if handle == invalid:
                hub['error'] = f'код {ctypes.get_last_error()}'
            else:
                try:
                    node = NodeInformation()
                    returned = wintypes.DWORD()
                    size = ctypes.sizeof(node)
                    ok = kernel.DeviceIoControl(handle, IOCTL_USB_GET_NODE_INFORMATION, ctypes.byref(node), size,
                                                ctypes.byref(node), size, ctypes.byref(returned), None)
                    if not ok:
                        hub['error'] = f'код {ctypes.get_last_error()}'
                    elif returned.value < 9 or node.hub.descriptor.length < 7:
                        hub['error'] = 'неполный дескриптор Windows'
                    else:
                        hub['ports'] = node.hub.descriptor.ports
                        hub['characteristics'] = node.hub.descriptor.characteristics
                finally:
                    kernel.CloseHandle(handle)
            hubs.append(hub)
        else:
            raise RuntimeError('Слишком много концентраторов; проверка остановлена.')
    finally:
        setup.SetupDiDestroyDeviceInfoList(device_set)
    return hubs
