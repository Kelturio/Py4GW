"""Py4GW widget that lists the Guild Wars process handles.

This widget inspects the running Guild Wars client (the same process Py4GW is
attached to) and enumerates every open handle. The results are presented in a
PyImGui table so it is easy to inspect the handle type, its kernel name and the
raw handle value.

The enumeration relies on Windows' ``NtQuerySystemInformation`` API. As this is
Windows specific the widget gracefully reports an error when executed on other
platforms.
"""

from __future__ import annotations

import ctypes
import os
import time
import traceback
from ctypes import wintypes
from typing import Iterable, List, Optional, Tuple

import Py4GW  # type: ignore
from Py4GWCoreLib import PyImGui, Routines  # type: ignore


MODULE_NAME = "GW Handle Viewer"

_REFRESH_INTERVAL_MS = 5_000
_HANDLE_TABLE_FLAGS = (
    PyImGui.TableFlags.Borders
    | PyImGui.TableFlags.RowBg
    | PyImGui.TableFlags.SizingStretchSame
    | PyImGui.TableFlags.Resizable
)


class _WindowsApis:
    """Lazy loader for the Win32 APIs used by the widget."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Windows APIs are only available on Windows platforms")

        self.ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)

        self._configure_ntdll()
        self._configure_kernel32()
        self._configure_user32()

    def _configure_ntdll(self) -> None:
        self.ntdll.NtQuerySystemInformation.argtypes = [
            wintypes.ULONG,
            ctypes.c_void_p,
            wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG),
        ]
        self.ntdll.NtQuerySystemInformation.restype = wintypes.LONG

        self.ntdll.NtQueryObject.argtypes = [
            wintypes.HANDLE,
            wintypes.ULONG,
            ctypes.c_void_p,
            wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG),
        ]
        self.ntdll.NtQueryObject.restype = wintypes.LONG

    def _configure_kernel32(self) -> None:
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE

        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

        self.kernel32.DuplicateHandle.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self.kernel32.DuplicateHandle.restype = wintypes.BOOL

        self.kernel32.GetCurrentProcess.argtypes = []
        self.kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    def _configure_user32(self) -> None:
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD


_WINDOWS: Optional[_WindowsApis] = None


def _get_windows_api() -> _WindowsApis:
    global _WINDOWS
    if _WINDOWS is None:
        _WINDOWS = _WindowsApis()
    return _WINDOWS


ULONG_PTR = ctypes.c_size_t


class _UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]


class _SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX(ctypes.Structure):
    _fields_ = [
        ("Object", ctypes.c_void_p),
        ("UniqueProcessId", ULONG_PTR),
        ("HandleValue", ULONG_PTR),
        ("GrantedAccess", wintypes.ULONG),
        ("CreatorBackTraceIndex", wintypes.USHORT),
        ("ObjectTypeIndex", wintypes.USHORT),
        ("HandleAttributes", wintypes.ULONG),
        ("Reserved", wintypes.ULONG),
    ]


# --- Constants -----------------------------------------------------------------
SystemExtendedHandleInformation = 64
ObjectNameInformation = 1
ObjectTypeInformation = 2
DUPLICATE_SAME_ACCESS = 0x00000002
PROCESS_DUP_HANDLE = 0x00000040
PROCESS_QUERY_LIMITED_INFORMATION = 0x00001000
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
STATUS_BUFFER_OVERFLOW = 0x80000005
STATUS_BUFFER_TOO_SMALL = 0xC0000023
STATUS_SUCCESS = 0


HandleInfo = Tuple[str, str, str]


def _ntstatus_code(status: int) -> int:
    """Return the unsigned 32-bit representation of an NTSTATUS value."""

    return status & 0xFFFFFFFF


class _ElapsedTimer:
    """Utility timer based on ``time.monotonic``."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._start = time.monotonic()

    def has_elapsed(self, milliseconds: int) -> bool:
        return (time.monotonic() - self._start) * 1000 >= milliseconds


class _HandleCache:
    """Caches the handle list and refreshes it on demand."""

    def __init__(self) -> None:
        self.timer = _ElapsedTimer()
        self.handles: List[HandleInfo] = []
        self.error: Optional[str] = None

    def maybe_refresh(self) -> None:
        if not self.handles or self.timer.has_elapsed(_REFRESH_INTERVAL_MS):
            try:
                self.handles = list(_enumerate_gw_handles())
                self.error = None
            except Exception as exc:  # pragma: no cover - defensive, Windows only
                self.handles = []
                self.error = str(exc)
                Py4GW.Console.Log(
                    MODULE_NAME,
                    f"Failed to enumerate handles: {exc}\n{traceback.format_exc()}",
                    Py4GW.Console.MessageType.Error,
                )
            finally:
                self.timer.reset()


_HANDLE_CACHE = _HandleCache()


def _get_gw_process_id() -> Optional[int]:
    """Return the Guild Wars process id or ``None`` if unavailable."""

    if os.name != "nt":
        return None

    hwnd = Py4GW.Console.get_gw_window_handle()
    if not hwnd:
        return None

    win = _get_windows_api()
    pid = wintypes.DWORD(0)
    if not win.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid)):
        return None
    return int(pid.value)


def _enumerate_gw_handles() -> Iterable[HandleInfo]:
    """Yield tuples describing every Guild Wars process handle."""

    if os.name != "nt":
        raise OSError("Handle enumeration is only supported on Windows")

    windows_api = _get_windows_api()
    pid = _get_gw_process_id()
    if pid is None:
        raise RuntimeError("Unable to resolve Guild Wars process id")

    system_entries = _query_system_handles(windows_api)
    process_handle = windows_api.kernel32.OpenProcess(
        PROCESS_DUP_HANDLE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not process_handle:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        current_process = windows_api.kernel32.GetCurrentProcess()
        pointer_width = ctypes.sizeof(ctypes.c_void_p) * 2
        type_cache: dict[int, str] = {}

        results: List[HandleInfo] = []
        for entry in system_entries:
            if int(entry.UniqueProcessId) != pid:
                continue

            duplicate = wintypes.HANDLE()
            handle_value = wintypes.HANDLE(int(entry.HandleValue))
            duplicated = windows_api.kernel32.DuplicateHandle(
                process_handle,
                handle_value,
                current_process,
                ctypes.byref(duplicate),
                0,
                False,
                DUPLICATE_SAME_ACCESS,
            )

            if not duplicated:
                continue

            try:
                type_name = type_cache.get(entry.ObjectTypeIndex)
                if type_name is None:
                    type_name = _query_object_string(duplicate, ObjectTypeInformation)
                    if type_name:
                        type_cache[entry.ObjectTypeIndex] = type_name
                    else:
                        type_name = f"Type {entry.ObjectTypeIndex}"

                object_name = _query_object_string(duplicate, ObjectNameInformation)
                handle_hex = f"0x{int(entry.HandleValue):0{pointer_width}X}"

                results.append((type_name or "<unknown>", object_name or "", handle_hex))
            finally:
                windows_api.kernel32.CloseHandle(duplicate)

        results.sort(key=lambda item: (item[0], item[1], item[2]))
        return results
    finally:
        windows_api.kernel32.CloseHandle(process_handle)


def _query_system_handles(windows_api: _WindowsApis) -> List[_SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX]:
    """Fetch the system handle table using ``SystemExtendedHandleInformation``."""

    size = 0x10000
    return_length = wintypes.ULONG(0)

    while True:
        buffer = ctypes.create_string_buffer(size)
        status = windows_api.ntdll.NtQuerySystemInformation(
            SystemExtendedHandleInformation,
            buffer,
            size,
            ctypes.byref(return_length),
        )

        if status == STATUS_SUCCESS:
            break

        status_code = _ntstatus_code(status)

        if status_code in (STATUS_INFO_LENGTH_MISMATCH, STATUS_BUFFER_TOO_SMALL):
            size = max(size * 2, int(return_length.value) or size * 2)
            continue

        raise OSError(status_code, f"NtQuerySystemInformation failed: 0x{status_code:08X}")

    buffer_address = ctypes.addressof(buffer)
    pointer_type = ctypes.c_size_t
    pointer_size = ctypes.sizeof(pointer_type)
    handle_count = ctypes.cast(buffer_address, ctypes.POINTER(pointer_type)).contents.value
    offset = pointer_size * 2
    entry_size = ctypes.sizeof(_SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX)

    entries: List[_SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX] = []
    for index in range(handle_count):
        entry_address = buffer_address + offset + index * entry_size
        raw = ctypes.string_at(entry_address, entry_size)
        entries.append(_SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX.from_buffer_copy(raw))
    return entries


def _query_object_string(handle: wintypes.HANDLE, info_class: int) -> Optional[str]:
    """Query the object type or name as a Python string."""

    windows_api = _get_windows_api()
    length = wintypes.ULONG(0)
    size = 0x400

    while True:
        buffer = ctypes.create_string_buffer(size)
        status = windows_api.ntdll.NtQueryObject(
            handle,
            info_class,
            buffer,
            size,
            ctypes.byref(length),
        )

        if status == STATUS_SUCCESS:
            break

        status_code = _ntstatus_code(status)

        if status_code in (
            STATUS_INFO_LENGTH_MISMATCH,
            STATUS_BUFFER_OVERFLOW,
            STATUS_BUFFER_TOO_SMALL,
        ):
            size = max(size * 2, int(length.value) or size * 2)
            continue

        if status < 0:
            return None

        raise OSError(status_code, f"NtQueryObject failed: 0x{status_code:08X}")

    base_address = ctypes.addressof(buffer)
    unicode_string = ctypes.cast(base_address, ctypes.POINTER(_UNICODE_STRING)).contents
    if unicode_string.Length == 0 or not unicode_string.Buffer:
        return ""
    string_length = unicode_string.Length // ctypes.sizeof(wintypes.WCHAR)
    return ctypes.wstring_at(unicode_string.Buffer, string_length)


def configure() -> None:
    """Widget configuration hook (not used)."""


def _draw_table(handles: Iterable[HandleInfo]) -> None:
    if not PyImGui.begin_table("GWHandles", 3, _HANDLE_TABLE_FLAGS):
        return

    PyImGui.table_setup_column("Type")
    PyImGui.table_setup_column("Name")
    PyImGui.table_setup_column("Handle")
    PyImGui.table_headers_row()

    for type_name, object_name, handle_hex in handles:
        PyImGui.table_next_row()
        PyImGui.table_set_column_index(0)
        PyImGui.text(type_name)

        PyImGui.table_set_column_index(1)
        if object_name:
            PyImGui.text_wrapped(object_name)
        else:
            PyImGui.text_disabled("<no name>")

        PyImGui.table_set_column_index(2)
        PyImGui.text(handle_hex)

    PyImGui.end_table()


def main() -> None:
    if not Routines.Checks.Map.MapValid():
        return

    if not PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize):
        PyImGui.end()
        return

    try:
        _HANDLE_CACHE.maybe_refresh()

        if os.name != "nt":
            PyImGui.text_wrapped("This widget is only available on Windows.")
        elif _HANDLE_CACHE.error:
            PyImGui.text_wrapped(f"Unable to enumerate handles: {_HANDLE_CACHE.error}")
        else:
            PyImGui.text(f"Handles: {len(_HANDLE_CACHE.handles)}")
            PyImGui.separator()
            _draw_table(_HANDLE_CACHE.handles)
    finally:
        PyImGui.end()


if __name__ == "__main__":
    main()
