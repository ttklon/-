"""Put Unicode text on the Windows clipboard, including after the app closes."""
import ctypes
import sys
from ctypes import wintypes


def copy_text(text, hwnd):
    if sys.platform != 'win32':
        raise OSError('Буфер обмена Windows недоступен.')
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
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
    # Tk clears clipboard data owned by its own window on shutdown. Use an
    # independent native window, so copied text survives the Tk app closing.
    owner = user32.CreateWindowExW(0, 'STATIC', '', 0, 0, 0, 0, 0, None, None,
                                   kernel32.GetModuleHandleW(None), None)
    if not owner:
        kernel32.GlobalFree(handle)
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(ptr, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(owner):
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
        user32.DestroyWindow(owner)
