"""Put Unicode text on the Windows clipboard, including after the app closes."""
import ctypes
import sys
from ctypes import wintypes


def copy_text(text, hwnd):
    if sys.platform != 'win32':
        raise OSError('Буфер обмена Windows недоступен.')
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    # Windows clipboard CF_UNICODETEXT convention uses CRLF and a null terminator.
    payload = text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-16-le') + b'\0\0'
    handle = kernel32.GlobalAlloc(0x0002, len(payload))  # GMEM_MOVEABLE
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    transferred = False
    opened = False
    try:
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(ptr, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(hwnd):
            raise OSError('Буфер обмена занят другой программой. Попробуйте ещё раз.')
        opened = True
        if not user32.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        if not user32.SetClipboardData(13, handle):  # CF_UNICODETEXT
            raise ctypes.WinError(ctypes.get_last_error())
        transferred = True  # Clipboard now owns the allocation.
    finally:
        if opened:
            user32.CloseClipboard()
        if not transferred:
            kernel32.GlobalFree(handle)
