from __future__ import annotations

# -*- coding: utf-8 -*-

"""
Аннотация

🧩 1. Назначение файла
- Единый модуль взаимодействия с ОС Windows (SSOT).
- Объединяет WinAPI вызовы, управление окнами, уведомления и безопасность.
- Реализует логику позиционирования относительно системного трея.

🧱 2. Компоненты
- Low-Level: Ctypes структуры, COM-интерфейсы, вызовы DLL.
- Managers: WindowManager, ShellManager, SecurityManager.
- Utilities: Notifier (Toast via WinRT), SecretStorage (DPAPI), UpdateInstaller (Handover).
- Positioning: PositionWorker (Thread) и логика расчета координат.

⚙️ 3. Особенности
- Отсутствие прямых зависимостей от UI-виджетов (работа через HWND/Signals).
- Строгая типизация структур (wintypes).
- Изоляция платформозависимого кода.
"""

import sys
import os
import time
import ctypes
import uuid
import binascii
import winreg
import subprocess
import tempfile
from typing import Optional, Tuple, Callable, Any
from ctypes import wintypes

from PySide6.QtCore import QObject, QThread, QRect, Signal, QSettings, QProcess

# Импорт конфигурации
import config

# Опциональные импорты
try:
    import keyring
except ImportError:
    keyring = None

# Безопасный импорт библиотеки уведомлений (WinRT)
try:
    from windows_toasts import (
        Toast, WindowsToaster, ToastAudio, ToastDuration,
        ToastImageAndCrop, ToastButton, ToastActivationType
    )
    
    _HAS_WIN_TOASTS = True
except ImportError:
    _HAS_WIN_TOASTS = False

_IS_WIN = sys.platform == "win32"

# -------------------------------------------------------------------------
# 1. WinAPI Constants & Polyfills
# -------------------------------------------------------------------------

# Polyfills
if not hasattr(wintypes, 'UINT_PTR'):
    wintypes.UINT_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

if not hasattr(wintypes, 'HRESULT'):
    wintypes.HRESULT = ctypes.c_long

if not hasattr(wintypes, 'LPARAM'):
    wintypes.LPARAM = wintypes.UINT_PTR

# Window Positioning
HWND_TOPMOST = ctypes.c_void_p(-1)
HWND_NOTOPMOST = ctypes.c_void_p(-2)

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SWP_NOOWNERZORDER = 0x0200
SWP_ASYNCWINDOWPOS = 0x4000

# Window Styles
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

# Window Messages
WM_WINDOWPOSCHANGING = 0x0046
WM_ACTIVATE = 0x0006

# Activation States
WA_INACTIVE = 0
WA_ACTIVE = 1
WA_CLICKACTIVE = 2

# Shell Query User Notification State
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4

# COM / OLE
CLSCTX_INPROC_SERVER = 1
S_OK = 0
PKEY_AUMID_FMTID = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
PKEY_AUMID_PID = 5

# Process Synchronization
SYNCHRONIZE = 0x00100000
INFINITE = 0xFFFFFFFF


# -------------------------------------------------------------------------
# 2. WinAPI Structures
# -------------------------------------------------------------------------

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]
    
    def width(self) -> int: return self.right - self.left
    
    def height(self) -> int: return self.bottom - self.top


class WINDOWPOS(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("hwndInsertAfter", wintypes.HWND),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("cx", ctypes.c_int),
        ("cy", ctypes.c_int),
        ("flags", wintypes.UINT),
    ]


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]
    
    def __init__(self, guid_str: str = None):
        super().__init__()
        if guid_str:
            u = uuid.UUID(guid_str)
            self.Data1 = u.time_low
            self.Data2 = u.time_mid
            self.Data3 = u.time_hi_version
            for i, b in enumerate(u.bytes[8:]): self.Data4[i] = b


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("pwszVal", wintypes.LPCWSTR)]
    
    _fields_ = [("vt", wintypes.WORD), ("wReserved1", wintypes.WORD), ("wReserved2", wintypes.WORD), ("wReserved3", wintypes.WORD), ("u", _U)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT), ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM), ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


# -------------------------------------------------------------------------
# 3. DLL Loading & Prototypes
# -------------------------------------------------------------------------

if _IS_WIN:
    _user32 = ctypes.windll.user32
    _shell32 = ctypes.windll.shell32
    _ole32 = ctypes.windll.ole32
    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    
    # User32
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _user32.SetWindowPos.restype = wintypes.BOOL
    
    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wintypes.HWND
    
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    
    _user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    _user32.FindWindowW.restype = wintypes.HWND
    
    _user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    _user32.FindWindowExW.restype = wintypes.HWND
    
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    
    _user32.GetShellWindow.argtypes = []
    _user32.GetShellWindow.restype = wintypes.HWND
    
    _user32.GetDesktopWindow.argtypes = []
    _user32.GetDesktopWindow.restype = wintypes.HWND
    
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    
    # Handle SetWindowLongPtr for 64-bit compatibility
    try:
        _SetWindowLong = _user32.SetWindowLongPtrW
        _GetWindowLong = _user32.GetWindowLongPtrW
    except AttributeError:
        _SetWindowLong = _user32.SetWindowLongW
        _GetWindowLong = _user32.GetWindowLongW
    
    _SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LPARAM]
    _SetWindowLong.restype = wintypes.LPARAM
    _GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    _GetWindowLong.restype = wintypes.LPARAM
    
    # Shell32
    _shell32.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]
    _shell32.SHQueryUserNotificationState.restype = wintypes.HRESULT
    
    _shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
    _shell32.SetCurrentProcessExplicitAppUserModelID.restype = wintypes.HRESULT
    
    # Crypt32
    _crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    
    _crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    
    # Kernel32
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    
    # Ole32
    _ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    _ole32.CoInitialize.restype = wintypes.HRESULT
    
    _ole32.CoUninitialize.argtypes = []
    _ole32.CoUninitialize.restype = None
    
    _ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    _ole32.CoCreateInstance.restype = wintypes.HRESULT


# -------------------------------------------------------------------------
# 4. COM Interfaces
# -------------------------------------------------------------------------

def _com_method(restype, *argtypes):
    return ctypes.WINFUNCTYPE(restype, *argtypes)


class IUnknown(ctypes.Structure):
    _fields_ = [("lpVtbl", ctypes.POINTER(ctypes.c_void_p))]
    
    def QueryInterface(self, riid, ppvObj):
        return _com_method(wintypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(self.lpVtbl.contents[0])(ctypes.addressof(self), riid, ppvObj)
    
    def Release(self):
        return _com_method(wintypes.ULONG, ctypes.c_void_p)(self.lpVtbl.contents[2])(ctypes.addressof(self))


class IPersistFile(IUnknown):
    def Save(self, pszFileName, fRemember):
        return _com_method(wintypes.HRESULT, ctypes.c_void_p, wintypes.LPCWSTR, wintypes.BOOL)(self.lpVtbl.contents[6])(ctypes.addressof(self), pszFileName, fRemember)


class IShellLinkW(IUnknown):
    def SetPath(self, pszFile):
        return _com_method(wintypes.HRESULT, ctypes.c_void_p, wintypes.LPCWSTR)(self.lpVtbl.contents[20])(ctypes.addressof(self), pszFile)
    
    def SetArguments(self, pszArgs):
        return _com_method(wintypes.HRESULT, ctypes.c_void_p, wintypes.LPCWSTR)(self.lpVtbl.contents[11])(ctypes.addressof(self), pszArgs)
    
    def SetWorkingDirectory(self, pszDir):
        return _com_method(wintypes.HRESULT, ctypes.c_void_p, wintypes.LPCWSTR)(self.lpVtbl.contents[9])(ctypes.addressof(self), pszDir)


class IPropertyStore(IUnknown):
    def SetValue(self, key, propvar):
        return _com_method(wintypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))(self.lpVtbl.contents[6])(ctypes.addressof(self), key, propvar)
    
    def Commit(self):
        return _com_method(wintypes.HRESULT, ctypes.c_void_p)(self.lpVtbl.contents[7])(ctypes.addressof(self))


CLSID_ShellLink = GUID("{00021401-0000-0000-C000-000000000046}")
IID_IShellLinkW = GUID("{000214F9-0000-0000-C000-000000000046}")
IID_IPersistFile = GUID("{0000010b-0000-0000-C000-000000000046}")
IID_IPropertyStore = GUID("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")


# -------------------------------------------------------------------------
# 5. Low-Level Managers
# -------------------------------------------------------------------------

class WindowManager:
    """Управление окнами (позиция, Z-порядок)."""
    
    @staticmethod
    def set_window_pos(hwnd: int, x: int, y: int, w: int, h: int, top_most: bool = True, no_activate: bool = True) -> bool:
        if not _IS_WIN: return False
        flags = SWP_SHOWWINDOW
        if no_activate: flags |= SWP_NOACTIVATE
        if w == 0 and h == 0: flags |= SWP_NOSIZE | SWP_NOMOVE
        hwnd_insert = HWND_TOPMOST if top_most else HWND_NOTOPMOST
        return bool(_user32.SetWindowPos(wintypes.HWND(hwnd), hwnd_insert, x, y, w, h, flags))
    
    @staticmethod
    def set_overlay_position(hwnd: int, x: int, y: int, w: int, h: int, menu_open: bool) -> None:
        """Специальный метод для оверлея с учетом Z-Fighting."""
        if not _IS_WIN: return
        flags = SWP_NOACTIVATE | SWP_SHOWWINDOW
        z_order = HWND_TOPMOST
        if menu_open:
            flags |= SWP_NOZORDER
        _user32.SetWindowPos(wintypes.HWND(hwnd), z_order, x, y, w, h, flags)
    
    @staticmethod
    def force_top_most(hwnd: int, toggle: bool = False) -> None:
        """Агрессивное восстановление Z-порядка (Async)."""
        if not _IS_WIN: return
        # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_ASYNCWINDOWPOS | SWP_NOOWNERZORDER
        flags = 0x0001 | 0x0002 | 0x0010 | 0x0040 | 0x4000 | 0x0200
        
        if toggle:
            # Сброс стека: опускаем окно, затем поднимаем
            _user32.SetWindowPos(wintypes.HWND(hwnd), HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        
        _user32.SetWindowPos(wintypes.HWND(hwnd), HWND_TOPMOST, 0, 0, 0, 0, flags)
    
    @staticmethod
    def set_no_activate_style(hwnd: int) -> None:
        """Устанавливает стиль WS_EX_NOACTIVATE (Ghost Window)."""
        if not _IS_WIN: return
        try:
            style = _GetWindowLong(wintypes.HWND(hwnd), GWL_EXSTYLE)
            # Добавляем NOACTIVATE и TOOLWINDOW (чтобы не было в Alt-Tab)
            new_style = style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            if style != new_style:
                _SetWindowLong(wintypes.HWND(hwnd), GWL_EXSTYLE, wintypes.LPARAM(new_style))
        except Exception:
            pass
    
    @staticmethod
    def set_ghost_overlay_style(hwnd: int) -> None:
        """
        Применяет полный набор стилей для независимого оверлея.
        ToolWindow + NoActivate.
        """
        if not _IS_WIN: return
        try:
            style = _GetWindowLong(wintypes.HWND(hwnd), GWL_EXSTYLE)
            # Combine: ToolWindow (no alt-tab), NoActivate (no focus)
            new_style = style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            if style != new_style:
                _SetWindowLong(wintypes.HWND(hwnd), GWL_EXSTYLE, wintypes.LPARAM(new_style))
                # Flush frame to apply style immediately
                _user32.SetWindowPos(wintypes.HWND(hwnd), 0, 0, 0, 0, 0,
                                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        except Exception:
            pass


class ShellManager:
    """Взаимодействие с оболочкой."""
    
    @staticmethod
    def is_fullscreen_app_running() -> bool:
        """
        Проверяет наличие полноэкранного приложения.
        Использует API Windows и эвристику (размер активного окна).
        """
        if not _IS_WIN: return False
        
        # 1. API Check (SHQueryUserNotificationState)
        state = ctypes.c_int(0)
        if _shell32.SHQueryUserNotificationState(ctypes.byref(state)) == S_OK:
            if state.value in (QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE):
                return True
        
        # 2. Heuristic Check (Foreground Window Size)
        try:
            hwnd_active = _user32.GetForegroundWindow()
            if not hwnd_active: return False
            
            # Ignore Shell/Desktop
            shell_wnd = _user32.GetShellWindow()
            desktop_wnd = _user32.GetDesktopWindow()
            if hwnd_active == shell_wnd or hwnd_active == desktop_wnd:
                return False
            
            r = RECT()
            if _user32.GetWindowRect(hwnd_active, ctypes.byref(r)):
                w_scr = _user32.GetSystemMetrics(0)  # SM_CXSCREEN
                h_scr = _user32.GetSystemMetrics(1)  # SM_CYSCREEN
                
                # Если окно занимает весь экран (или больше)
                if (r.right - r.left) >= w_scr and (r.bottom - r.top) >= h_scr:
                    return True
        except Exception:
            pass
        
        return False
    
    @staticmethod
    def is_start_menu_open() -> bool:
        """Проверяет, открыто ли меню Пуск, Поиск или Панель задач."""
        if not _IS_WIN: return False
        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd: return False
            
            buff = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(wintypes.HWND(hwnd), buff, 256)
            cls = buff.value
            
            # Windows.UI.Core.CoreWindow = Start Menu / Search / Action Center
            # Shell_TrayWnd = Taskbar
            # Shell_SecondaryTrayWnd = Taskbar on secondary monitor
            # SearchPane = Old search
            system_classes = (
                "Windows.UI.Core.CoreWindow",
                "Shell_TrayWnd",
                "Shell_SecondaryTrayWnd",
                "SearchPane",
                "Cortana"
            )
            return cls in system_classes
        except Exception:
            return False


class SecurityManager:
    """DPAPI Шифрование."""
    
    @staticmethod
    def encrypt_string(text: str) -> Optional[bytes]:
        if not _IS_WIN or not text: return None
        try:
            data_in = text.encode('utf-8')
            blob_in = DATA_BLOB(len(data_in), ctypes.cast(ctypes.create_string_buffer(data_in), ctypes.POINTER(ctypes.c_byte)))
            blob_out = DATA_BLOB()
            if _crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
                result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                _kernel32.LocalFree(blob_out.pbData)
                return result
        except Exception:
            pass
        return None
    
    @staticmethod
    def decrypt_string(data: bytes) -> Optional[str]:
        if not _IS_WIN or not data: return None
        try:
            blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
            blob_out = DATA_BLOB()
            if _crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
                result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                _kernel32.LocalFree(blob_out.pbData)
                return result.decode('utf-8')
        except Exception:
            pass
        return None


class ShortcutManager:
    """Создание ярлыков с AUMID."""
    
    @staticmethod
    def create_shortcut(path_lnk: str, target_path: str, arguments: str = "", work_dir: str = "", aumid: str = "") -> bool:
        if not _IS_WIN: return False
        _ole32.CoInitialize(None)
        try:
            pShellLink = ctypes.c_void_p()
            if _ole32.CoCreateInstance(ctypes.byref(CLSID_ShellLink), None, CLSCTX_INPROC_SERVER, ctypes.byref(IID_IShellLinkW), ctypes.byref(pShellLink)) != S_OK:
                return False
            sl = ctypes.cast(pShellLink, ctypes.POINTER(IShellLinkW)).contents
            sl.SetPath(target_path)
            if arguments: sl.SetArguments(arguments)
            if work_dir: sl.SetWorkingDirectory(work_dir)
            
            if aumid:
                pPropStore = ctypes.c_void_p()
                if sl.QueryInterface(ctypes.byref(IID_IPropertyStore), ctypes.byref(pPropStore)) == S_OK:
                    ps = ctypes.cast(pPropStore, ctypes.POINTER(IPropertyStore)).contents
                    pkey = PROPERTYKEY();
                    pkey.fmtid = GUID(PKEY_AUMID_FMTID);
                    pkey.pid = PKEY_AUMID_PID
                    pv = PROPVARIANT();
                    pv.vt = 31;
                    pv.u.pwszVal = ctypes.c_wchar_p(aumid)
                    ps.SetValue(ctypes.byref(pkey), ctypes.byref(pv))
                    ps.Commit();
                    ps.Release()
            
            pPersistFile = ctypes.c_void_p()
            if sl.QueryInterface(ctypes.byref(IID_IPersistFile), ctypes.byref(pPersistFile)) == S_OK:
                pf = ctypes.cast(pPersistFile, ctypes.POINTER(IPersistFile)).contents
                pf.Save(path_lnk, True);
                pf.Release()
            sl.Release()
            return True
        except Exception:
            return False
        finally:
            _ole32.CoUninitialize()


# -------------------------------------------------------------------------
# 6. High-Level Utilities
# -------------------------------------------------------------------------

def show_file_in_explorer(path: str):
    """
    Открывает Проводник Windows с выделением указанного файла.
    Использует команду 'explorer /select,<path>'.
    """
    if not _IS_WIN or not path: return
    
    # Нормализация пути
    clean_path = os.path.normpath(path)
    
    try:
        subprocess.Popen(f'explorer /select,"{clean_path}"', shell=False)
    except Exception:
        pass


class Notifier:
    """
    Менеджер уведомлений (Toast).
    Использует библиотеку windows-toasts (WinRT) для безопасности и надежности.
    """
    
    def __init__(self, *, app_id: str = config.APP_AUMID, display_name: str = config.APP_NAME_DISPLAY, on_fallback: Optional[Callable[[str, str], None]] = None):
        self.app_id = app_id
        self.name = display_name
        self._fallback = on_fallback
        self._toaster = None
        
        if _IS_WIN:
            self._init_windows()
            if _HAS_WIN_TOASTS:
                try:
                    self._toaster = WindowsToaster(self.app_id)
                except Exception:
                    pass
    
    @property
    def is_supported(self) -> bool:
        return _IS_WIN
    
    def _init_windows(self) -> None:
        try:
            _shell32.SetCurrentProcessExplicitAppUserModelID(self.app_id)
        except Exception:
            pass
        try:
            self._ensure_shortcut()
        except Exception:
            pass
    
    def _ensure_shortcut(self) -> None:
        """Гарантирует наличие ярлыка с AUMID для работы уведомлений."""
        lnk_path = os.path.join(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"), f"{self.name}.lnk")
        
        if os.path.exists(lnk_path):
            return
        
        # Используем WinAPI для получения реального пути к EXE
        target = sys.executable
        if _IS_WIN:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                ctypes.windll.kernel32.GetModuleFileNameW(None, buf, 1024)
                if buf.value:
                    target = buf.value
            except Exception:
                pass
        
        args = ""
        work_dir = os.getcwd()
        is_compiled = hasattr(sys, "__compiled__") or getattr(sys, "frozen", False)
        if not is_compiled and sys.argv and os.path.isfile(sys.argv[0]):
            args = f'"{os.path.abspath(sys.argv[0])}"'
        
        ShortcutManager.create_shortcut(lnk_path, target, args, work_dir, self.app_id)
    
    def toast(self, title: str, msg: str, *, url: Optional[str] = None, silent: bool = False, duration: str = "short", icon: Optional[str] = None) -> bool:
        """
        Отправляет уведомление через WinRT (windows-toasts).
        Если библиотека недоступна или произошла ошибка - использует fallback.
        """
        # 1. Попытка отправить через Native WinRT
        if self._toaster and _HAS_WIN_TOASTS:
            try:
                new_toast = Toast()
                new_toast.text_fields = [title, msg]
                
                # Иконка
                if icon and os.path.exists(icon):
                    new_toast.AddImage(ToastImageAndCrop(icon, circle_crop=True))
                
                # Звук
                if silent:
                    new_toast.audio = ToastAudio(silent=True)
                
                # Длительность
                if duration == "long":
                    new_toast.duration = ToastDuration.Long
                else:
                    new_toast.duration = ToastDuration.Short
                
                # Кнопка действия (URL)
                if url:
                    btn = ToastButton("Открыть", arguments=url)
                    btn.activation_type = ToastActivationType.PROTOCOL
                    new_toast.AddAction(btn)
                
                self._toaster.show_toast(new_toast)
                return True
            except Exception:
                # Если WinRT упал, идем в fallback
                pass
        
        # 2. Fallback (например, QSystemTrayIcon)
        if self._fallback:
            try:
                self._fallback(title, msg)
                return True
            except Exception:
                pass
        return False


class SecretStorage:
    """Хранилище ключей (Keyring -> DPAPI -> Memory)."""
    KEY_NAME = "ETHERSCAN_API_KEY"
    SETTINGS_KEY = "security/encrypted_key"
    
    @classmethod
    def get_key(cls) -> Tuple[Optional[str], str]:
        if keyring:
            try:
                val = keyring.get_password(config.APP_AUMID, cls.KEY_NAME)
                if val: return val, "keyring"
            except Exception:
                pass
        
        s = QSettings()
        enc_hex = s.value(cls.SETTINGS_KEY, "")
        if enc_hex and isinstance(enc_hex, str):
            try:
                data = binascii.unhexlify(enc_hex)
                decrypted = SecurityManager.decrypt_string(data)
                if decrypted: return decrypted, "dpapi"
            except Exception:
                pass
        return None, "none"
    
    @classmethod
    def save_key(cls, key: str) -> str:
        if not key:
            if keyring:
                try:
                    keyring.delete_password(config.APP_AUMID, cls.KEY_NAME)
                except Exception:
                    pass
            QSettings().remove(cls.SETTINGS_KEY)
            return "deleted"
        
        if keyring:
            try:
                keyring.set_password(config.APP_AUMID, cls.KEY_NAME, key)
                QSettings().remove(cls.SETTINGS_KEY)
                return "keyring"
            except Exception:
                pass
        
        enc = SecurityManager.encrypt_string(key)
        if enc:
            QSettings().setValue(cls.SETTINGS_KEY, binascii.hexlify(enc).decode('ascii'))
            return "dpapi"
        return "memory"


class UpdateInstaller:
    """
    Утилита для установки обновлений (Handover Mechanism).
    Запускает новую версию, которая сама удаляет старую.
    """
    
    @staticmethod
    def restart_and_cleanup(new_file_path: str):
        """
        Запускает новый EXE с аргументами для удаления текущего файла.
        """
        if not _IS_WIN: return
        
        # 1. Получаем информацию о текущем процессе
        current_pid = os.getpid()
        current_exe = sys.executable
        
        # Если запущено из скрипта (dev mode), не удаляем интерпретатор
        if not (getattr(sys, 'frozen', False) or hasattr(sys, "__compiled__")):
            if sys.argv and os.path.isfile(sys.argv[0]):
                current_exe = os.path.abspath(sys.argv[0])
        
        # 2. Формируем аргументы для нового процесса
        # --cleanup-pid: PID старого процесса (чтобы ждать его завершения)
        # --cleanup-path: Путь к файлу старого процесса (чтобы удалить его)
        args = [
            "--cleanup-pid", str(current_pid),
            "--cleanup-path", current_exe
        ]
        
        # 3. Запускаем новый процесс полностью отвязанным (QProcess.startDetached)
        # AV Evasion: Используем легитимный Qt метод вместо subprocess.Popen с флагами скрытия
        try:
            QProcess.startDetached(new_file_path, args)
        except Exception:
            pass
        
        # 4. Немедленно завершаем текущий процесс
        os._exit(0)


def wait_for_pid_and_delete(pid: int, path: str):
    """
    Ждет завершения процесса PID и удаляет файл path.
    Используется в фоновом потоке новой версии.
    """
    if not _IS_WIN: return
    
    # 1. Ждем завершения процесса (WinAPI)
    try:
        # SYNCHRONIZE access rights
        handle = _kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            # Ждем бесконечно, пока процесс не умрет
            _kernel32.WaitForSingleObject(handle, INFINITE)
            _kernel32.CloseHandle(handle)
    except Exception:
        pass
    
    # 2. Пытаемся удалить файл (с повторами на случай блокировок антивирусом)
    for _ in range(20):  # ~10 секунд попыток
        try:
            if os.path.exists(path):
                os.remove(path)
            break  # Успех или файла уже нет
        except OSError:
            time.sleep(0.5)


def purge_legacy_autostart() -> None:
    """Очистка старых ярлыков автозапуска."""
    if not _IS_WIN: return
    try:
        p = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup", f"{config.APP_NAME_DISPLAY}.lnk")
        if os.path.exists(p): os.remove(p)
    except Exception:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, "EthereumGasTracker")
            except FileNotFoundError:
                pass
    except Exception:
        pass


# -------------------------------------------------------------------------
# 7. Positioning System
# -------------------------------------------------------------------------

class PositionWorker(QThread):
    """Фоновый поток для поиска координат трея."""
    coordinatesFound = Signal(int, QRect, QRect, bool)
    
    def __init__(self):
        super().__init__()
        self._running = True
        self._tray_hwnd = 0
        self._notify_hwnd = 0
        self._screen_size = (0, 0)
        self._last_emit_data: Optional[Tuple[int, QRect, QRect, bool]] = None
    
    def stop(self):
        self._running = False
        self.wait()
    
    def run(self):
        if not _IS_WIN: return
        
        # Adaptive polling interval
        current_sleep = 200
        
        while self._running:
            try:
                # 1. Find Handles
                if not self._tray_hwnd or not _user32.IsWindow(self._tray_hwnd):
                    self._tray_hwnd = _user32.FindWindowW("Shell_TrayWnd", None)
                
                if not self._tray_hwnd:
                    self.msleep(1000)  # Retry slower if tray lost
                    continue
                
                if not self._notify_hwnd or not _user32.IsWindow(self._notify_hwnd):
                    self._notify_hwnd = _user32.FindWindowExW(self._tray_hwnd, 0, "TrayNotifyWnd", None)
                
                if not self._notify_hwnd:
                    self.msleep(1000)
                    continue
                
                # 2. Get Geometry
                r_tray, r_notify = RECT(), RECT()
                ok_t = _user32.GetWindowRect(self._tray_hwnd, ctypes.byref(r_tray))
                ok_n = _user32.GetWindowRect(self._notify_hwnd, ctypes.byref(r_notify))
                
                # 3. Check Fullscreen (Centralized Logic)
                is_fullscreen = ShellManager.is_fullscreen_app_running()
                
                # 4. Emit & Sleep
                if ok_t and ok_n:
                    qt = QRect(r_tray.left, r_tray.top, r_tray.width(), r_tray.height())
                    qn = QRect(r_notify.left, r_notify.top, r_notify.width(), r_notify.height())
                    
                    new_data = (self._tray_hwnd, qt, qn, is_fullscreen)
                    
                    # Deduplication: Emit only if changed
                    if new_data != self._last_emit_data:
                        self.coordinatesFound.emit(*new_data)
                        self._last_emit_data = new_data
                    
                    # Adaptive Sleep
                    if is_fullscreen:
                        current_sleep = 2000  # Deep sleep
                    else:
                        current_sleep = 200  # Normal poll
            
            except Exception:
                current_sleep = 1000
            
            self.msleep(current_sleep)


class PositionLogic(QObject):
    """Логика расчета координат оверлея."""
    
    def __init__(self):
        super().__init__()
        self._worker = PositionWorker()
    
    def start(self):
        if _IS_WIN: self._worker.start()
    
    def stop(self):
        if self._worker.isRunning(): self._worker.stop()
    
    @property
    def worker_signal(self):
        return self._worker.coordinatesFound
    
    @staticmethod
    def calculate_geometry(tray_rect: QRect, notify_rect: QRect, widget_w: int, widget_h: int, dpr: float) -> Tuple[int, int, int, int]:
        """Возвращает (x, y, w_physical, h_physical)."""
        tb_h = tray_rect.height()
        margin_physical = int(config.DOCK_MARGIN_RIGHT_PX * dpr)
        w_physical = int(widget_w * dpr)
        h_physical = tb_h
        
        x = notify_rect.left() - w_physical - margin_physical
        y = tray_rect.top()
        return x, y, w_physical, h_physical
    
    @staticmethod
    def apply_position(hwnd: int, x: int, y: int, w: int, h: int, menu_open: bool):
        WindowManager.set_overlay_position(hwnd, x, y, w, h, menu_open)