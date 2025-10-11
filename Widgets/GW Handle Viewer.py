import os
import traceback
from dataclasses import dataclass
from typing import List, Optional

import Py4GW  # type: ignore
from Py4GWCoreLib import IniHandler
from Py4GWCoreLib import PyImGui
from Py4GWCoreLib import Routines
from Py4GWCoreLib import Timer

import ctypes
from ctypes import wintypes

# --------------------------------------------------------------------------------------
# Windows API setup
# --------------------------------------------------------------------------------------

_HAS_WINDLL = hasattr(ctypes, "WinDLL")

if _HAS_WINDLL:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    _ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class _SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX(ctypes.Structure):
        _fields_ = [
            ("Object", ctypes.c_void_p),
            ("UniqueProcessId", _ULONG_PTR),
            ("HandleValue", _ULONG_PTR),
            ("GrantedAccess", ctypes.c_ulong),
            ("CreatorBackTraceIndex", ctypes.c_ushort),
            ("ObjectTypeIndex", ctypes.c_ushort),
            ("HandleAttributes", ctypes.c_ulong),
            ("Reserved", ctypes.c_ulong),
        ]

    class _SYSTEM_HANDLE_INFORMATION_EX(ctypes.Structure):
        _fields_ = [
            ("NumberOfHandles", ctypes.c_ulonglong),
            ("Reserved", ctypes.c_ulonglong),
        ]

    class _UNICODE_STRING(ctypes.Structure):
        _fields_ = [
            ("Length", ctypes.c_ushort),
            ("MaximumLength", ctypes.c_ushort),
            ("Buffer", ctypes.c_void_p),
        ]

    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.DuplicateHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.DuplicateHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.GetCurrentProcess.argtypes = []
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    _ntdll.NtQuerySystemInformation.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
    _ntdll.NtQuerySystemInformation.restype = ctypes.c_long
    _ntdll.NtQueryObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
    _ntdll.NtQueryObject.restype = ctypes.c_long
else:
    _kernel32 = None
    _ntdll = None
    _user32 = None
    _SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX = None  # type: ignore
    _SYSTEM_HANDLE_INFORMATION_EX = None  # type: ignore
    _UNICODE_STRING = None  # type: ignore

STATUS_SUCCESS = 0
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
OBJECT_NAME_INFORMATION = 1
OBJECT_TYPE_INFORMATION = 2
SYSTEM_EXTENDED_HANDLE_INFORMATION = 64
DUPLICATE_SAME_ACCESS = 0x00000002
PROCESS_DUP_HANDLE = 0x00000040
PROCESS_QUERY_INFORMATION = 0x00000400
PROCESS_VM_READ = 0x00000010
PROCESS_QUERY_LIMITED_INFORMATION = 0x00001000
PROCESS_ACCESS = PROCESS_DUP_HANDLE | PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION

# --------------------------------------------------------------------------------------
# Widget configuration
# --------------------------------------------------------------------------------------

@dataclass
class HandleInfo:
    type_name: str
    object_name: str
    handle_value: int


script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))

BASE_DIR = os.path.join(project_root, "Widgets", "Config")
INI_WIDGET_WINDOW_PATH = os.path.join(BASE_DIR, "gw_handle_viewer.ini")
os.makedirs(BASE_DIR, exist_ok=True)

ini_window = IniHandler(INI_WIDGET_WINDOW_PATH)
save_window_timer = Timer(); save_window_timer.Start()
refresh_timer = Timer(); refresh_timer.Start()

MODULE_NAME = "GW Handle Viewer"
COLLAPSED = "collapsed"
X_POS = "x"
Y_POS = "y"
REFRESH_INTERVAL_MS = 2000

window_x = ini_window.read_int(MODULE_NAME, X_POS, 100)
window_y = ini_window.read_int(MODULE_NAME, Y_POS, 100)
window_collapsed = ini_window.read_bool(MODULE_NAME, COLLAPSED, False)

first_run = True
_handles: List[HandleInfo] = []
_last_error: Optional[str] = None
_last_logged_error: Optional[str] = None
_data_initialized = False

# --------------------------------------------------------------------------------------
# Windows helpers
# --------------------------------------------------------------------------------------

def _query_unicode_from_handle(handle: wintypes.HANDLE, info_class: int) -> str:
    if not _HAS_WINDLL:
        return ""

    size = 0x400
    for _ in range(8):
        buffer = ctypes.create_string_buffer(size)
        return_length = ctypes.c_ulong(0)
        status = _ntdll.NtQueryObject(handle, info_class, buffer, size, ctypes.byref(return_length))
        if status == STATUS_SUCCESS:
            unicode_info = ctypes.cast(buffer, ctypes.POINTER(_UNICODE_STRING)).contents
            if not unicode_info.Buffer or unicode_info.Length == 0:
                return ""
            length = unicode_info.Length // ctypes.sizeof(wintypes.WCHAR)
            return ctypes.wstring_at(unicode_info.Buffer, length)
        if status != STATUS_INFO_LENGTH_MISMATCH:
            break
        size = max(size * 2, return_length.value or size * 2)
    return ""


def _get_system_handle_entries() -> List[_SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX]:
    if not _HAS_WINDLL:
        return []

    size = 0x10000
    for _ in range(8):
        buffer = ctypes.create_string_buffer(size)
        needed = ctypes.c_ulong(0)
        status = _ntdll.NtQuerySystemInformation(
            SYSTEM_EXTENDED_HANDLE_INFORMATION,
            buffer,
            size,
            ctypes.byref(needed),
        )
        if status == STATUS_SUCCESS:
            header = ctypes.cast(buffer, ctypes.POINTER(_SYSTEM_HANDLE_INFORMATION_EX)).contents
            count = int(header.NumberOfHandles)
            if count <= 0:
                return []
            entry_ptr = ctypes.cast(
                ctypes.addressof(buffer) + ctypes.sizeof(_SYSTEM_HANDLE_INFORMATION_EX),
                ctypes.POINTER(_SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX),
            )
            return [entry_ptr[i] for i in range(count)]
        if status != STATUS_INFO_LENGTH_MISMATCH:
            raise ctypes.WinError(status & 0xFFFFFFFF)
        size = max(size * 2, needed.value or size * 2)
    raise RuntimeError("Unable to query system handle information")


def _enumerate_process_handles(pid: int) -> List[HandleInfo]:
    if not _HAS_WINDLL:
        raise RuntimeError("Windows handle enumeration is not supported on this platform")

    process_handle = _kernel32.OpenProcess(PROCESS_ACCESS, False, pid)
    if not process_handle:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        current_process = _kernel32.GetCurrentProcess()
        entries = [
            entry for entry in _get_system_handle_entries()
            if int(entry.UniqueProcessId) == pid
        ]
        results: List[HandleInfo] = []
        for entry in entries:
            duplicate = wintypes.HANDLE()
            success = _kernel32.DuplicateHandle(
                process_handle,
                wintypes.HANDLE(int(entry.HandleValue)),
                current_process,
                ctypes.byref(duplicate),
                0,
                False,
                DUPLICATE_SAME_ACCESS,
            )
            if not success:
                continue
            try:
                type_name = _query_unicode_from_handle(duplicate, OBJECT_TYPE_INFORMATION) or "Unknown"
                object_name = _query_unicode_from_handle(duplicate, OBJECT_NAME_INFORMATION)
            finally:
                _kernel32.CloseHandle(duplicate)

            results.append(
                HandleInfo(
                    type_name=type_name,
                    object_name=object_name,
                    handle_value=int(entry.HandleValue),
                )
            )
        results.sort(key=lambda h: (h.type_name.lower(), h.object_name.lower(), h.handle_value))
        return results
    finally:
        _kernel32.CloseHandle(process_handle)


def _get_gw_pid() -> Optional[int]:
    if not _HAS_WINDLL:
        return None

    try:
        hwnd = Py4GW.Console.get_gw_window_handle()
    except AttributeError:
        hwnd = None

    if not hwnd:
        return None

    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value) if pid.value else None


# --------------------------------------------------------------------------------------
# Data refresh helpers
# --------------------------------------------------------------------------------------

def _update_handle_cache(force: bool = False) -> None:
    global _handles, _last_error, _last_logged_error, _data_initialized

    if not _HAS_WINDLL:
        _handles = []
        _last_error = "Handle enumeration is only available on Windows."
        _data_initialized = True
        return

    if not _data_initialized or force or refresh_timer.HasElapsed(REFRESH_INTERVAL_MS):
        refresh_timer.Reset()
        _data_initialized = True
        try:
            pid = _get_gw_pid()
            if not pid:
                _handles = []
                _last_error = "Unable to locate an active Guild Wars process."
                return

            _handles = _enumerate_process_handles(pid)
            _last_error = None
            _last_logged_error = None
        except Exception as exc:
            error_message = f"Failed to enumerate handles: {exc}"
            _handles = []
            _last_error = error_message
            if error_message != _last_logged_error:
                Py4GW.Console.Log(MODULE_NAME, error_message, Py4GW.Console.MessageType.Error)
                Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Debug)
                _last_logged_error = error_message


# --------------------------------------------------------------------------------------
# Widget rendering
# --------------------------------------------------------------------------------------

def draw_widget() -> None:
    global first_run, window_x, window_y, window_collapsed

    if first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        first_run = False

    opened = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
    new_collapsed = PyImGui.is_window_collapsed()
    window_pos = PyImGui.get_window_pos()

    if opened:
        _update_handle_cache()

        if _last_error:
            PyImGui.text_colored(_last_error, (1.0, 0.3, 0.3, 1.0))
        else:
            PyImGui.text(f"Handles: {len(_handles)}")
            table_flags = (
                PyImGui.TableFlags.Borders
                | PyImGui.TableFlags.RowBg
                | PyImGui.TableFlags.SizingStretchProp
                | PyImGui.TableFlags.Resizable
                | PyImGui.TableFlags.ScrollY
            )
            if PyImGui.begin_table("gw_handle_table", 3, table_flags, (600, 300)):
                PyImGui.table_setup_column("Type", PyImGui.TableColumnFlags.WidthStretch, 0.25)
                PyImGui.table_setup_column("Name", PyImGui.TableColumnFlags.WidthStretch, 0.55)
                PyImGui.table_setup_column("Handle", PyImGui.TableColumnFlags.WidthStretch, 0.20)
                PyImGui.table_headers_row()

                PyImGui.push_text_wrap_pos(0)
                for handle in _handles:
                    PyImGui.table_next_row()

                    PyImGui.table_next_column()
                    PyImGui.text(handle.type_name)

                    PyImGui.table_next_column()
                    if handle.object_name:
                        PyImGui.text(handle.object_name)
                    else:
                        PyImGui.text_disabled("<no name>")

                    PyImGui.table_next_column()
                    PyImGui.text(f"0x{handle.handle_value:X}")

                PyImGui.pop_text_wrap_pos()
                PyImGui.end_table()

    PyImGui.end()

    if save_window_timer.HasElapsed(1000):
        if window_pos and (int(window_pos[0]) != window_x or int(window_pos[1]) != window_y):
            window_x, window_y = int(window_pos[0]), int(window_pos[1])
            ini_window.write_key(MODULE_NAME, X_POS, str(window_x))
            ini_window.write_key(MODULE_NAME, Y_POS, str(window_y))
        if new_collapsed != window_collapsed:
            window_collapsed = new_collapsed
            ini_window.write_key(MODULE_NAME, COLLAPSED, str(window_collapsed))
        save_window_timer.Reset()


# --------------------------------------------------------------------------------------
# Widget lifecycle
# --------------------------------------------------------------------------------------

def configure() -> None:
    pass


def main() -> None:
    if not Routines.Checks.Map.MapValid():
        return

    if Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded():
        draw_widget()


if __name__ == "__main__":
    main()
