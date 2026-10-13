"""Read-only Windows classic Bluetooth inquiry plus BLE discovery."""
import asyncio
import ctypes as c
from ctypes import wintypes as w
import json


def classic_devices():
    class SystemTime(c.Structure):
        _fields_ = [('values', w.WORD * 8)]
    class Info(c.Structure):
        _fields_ = [('size', w.DWORD), ('address', c.c_ulonglong),
                    ('device_class', w.ULONG), ('connected', w.BOOL),
                    ('remembered', w.BOOL), ('authenticated', w.BOOL),
                    ('last_seen', SystemTime), ('last_used', SystemTime),
                    ('name', w.WCHAR * 248)]
    class Search(c.Structure):
        _fields_ = [('size', w.DWORD), ('authenticated', w.BOOL),
                    ('remembered', w.BOOL), ('unknown', w.BOOL),
                    ('connected', w.BOOL), ('inquiry', w.BOOL),
                    ('timeout', c.c_ubyte), ('radio', w.HANDLE)]
    api = c.WinDLL('bthprops.cpl', use_last_error=True)
    api.BluetoothFindFirstDevice.argtypes = [c.POINTER(Search), c.POINTER(Info)]
    api.BluetoothFindFirstDevice.restype = w.HANDLE
    api.BluetoothFindNextDevice.argtypes = [w.HANDLE, c.POINTER(Info)]
    api.BluetoothFindNextDevice.restype = w.BOOL
    api.BluetoothFindDeviceClose.argtypes = [w.HANDLE]
    api.BluetoothFindDeviceClose.restype = w.BOOL
    search = Search(c.sizeof(Search), True, True, True, True, True, 8, None)
    info = Info()
    info.size = c.sizeof(Info)
    handle = api.BluetoothFindFirstDevice(c.byref(search), c.byref(info))
    if not handle:
        error = c.get_last_error()
        if error == 259:  # ERROR_NO_MORE_ITEMS
            return []
        raise c.WinError(error)
    devices = []
    try:
        while True:
            if any(n in info.name.lower() for n in ('paperang', 'miaomiao')):
                address = ':'.join(f'{(info.address >> shift) & 255:02X}' for shift in range(40, -1, -8))
                devices.append(dict(name=info.name, address=address, transport='classic',
                                    paired=bool(info.authenticated), connected=bool(info.connected)))
            if not api.BluetoothFindNextDevice(handle, c.byref(info)):
                error = c.get_last_error()
                if error != 259:
                    raise c.WinError(error)
                break
    finally:
        api.BluetoothFindDeviceClose(handle)
    return devices


def discover():
    from bleak import BleakScanner
    from bleak.backends.winrt.util import uninitialize_sta
    uninitialize_sta()
    async def scan():
        devices = await BleakScanner.discover(timeout=10)
        return [dict(name=d.name, address=d.address, transport='ble') for d in devices
                if any(n in (d.name or '').lower() for n in ('paperang', 'miaomiao'))]
    return asyncio.run(scan()) + classic_devices()


if __name__ == '__main__':
    print(json.dumps(discover(), indent=2))
