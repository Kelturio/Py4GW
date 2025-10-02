"""Helpers for calling exported functions from gwca.dll.

This module offers a thin wrapper around :mod:`ctypes` so Py4GW scripts can
bind decorated exports from ``gwca.dll`` (the Guild Wars Client API library).
The helpers only deal with obtaining the function pointer and applying the
correct calling convention; scripts are still responsible for mapping the
arguments and return types to matching ``ctypes`` declarations.
"""
from __future__ import annotations

import ctypes
from ctypes import c_bool, c_uint32, wintypes
from pathlib import Path
import threading
from typing import Optional, Sequence, Union

__all__ = [
    "GWCALibrary",
    "EncodedStringDecoder",
    "get_shared_gwca_library",
    "load_gwca_function",
]


class _CDLLNoFree(ctypes.CDLL):
    """``ctypes.CDLL`` variant that skips ``FreeLibrary`` on GC."""

    def __del__(self) -> None:  # pragma: no cover - behaviour depends on GC
        pass


class _WinDLLNoFree(ctypes.WinDLL):
    """``ctypes.WinDLL`` variant that skips ``FreeLibrary`` on GC."""

    def __del__(self) -> None:  # pragma: no cover - behaviour depends on GC
        pass


class GWCALibrary:
    """Lightweight loader for ``gwca.dll`` exports.

    Parameters
    ----------
    module_name:
        Name of the DLL to load. Defaults to ``"gwca.dll"`` which is the
        canonical name shipped with GWToolbox/Py4GW setups.
    prefer_loaded:
        If ``True`` (the default) and the module is already loaded inside the
        current process the existing handle is reused. Reusing the handle avoids
        accidentally loading a second copy of the library which would fail to
        see Guild Wars' game state.
    default_call_conv:
        Either ``"cdecl"`` or ``"stdcall"``. GWCA exports are declared with
        the default ``__cdecl`` calling convention, but the parameter is
        exposed so that scripts can opt into ``stdcall`` when binding custom
        hooks or third-party exports.
    """

    _init_lock = threading.Lock()
    _global_init_result: Optional[bool] = None

    def __init__(
        self,
        module_name: str = "gwca.dll",
        *,
        prefer_loaded: bool = True,
        default_call_conv: str = "cdecl",
    ) -> None:
        self._module_name = module_name
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        self._kernel32.LoadLibraryW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.LoadLibraryW.restype = wintypes.HMODULE
        self._kernel32.FreeLibrary.argtypes = [wintypes.HMODULE]
        self._kernel32.FreeLibrary.restype = wintypes.BOOL
        self._kernel32.GetModuleFileNameW.argtypes = [
            wintypes.HMODULE,
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        self._kernel32.GetModuleFileNameW.restype = wintypes.DWORD
        self._kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        self._kernel32.GetCurrentProcessId.restype = wintypes.DWORD
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32.CreateToolhelp32Snapshot.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self._kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        try:
            self._psapi = ctypes.WinDLL("psapi", use_last_error=True)
        except OSError:  # pragma: no cover - psapi should always be present on Windows
            self._psapi = None
        else:
            self._psapi.EnumProcessModules.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.HMODULE),
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
            ]
            self._psapi.EnumProcessModules.restype = wintypes.BOOL
            if hasattr(self._psapi, "EnumProcessModulesEx"):
                self._psapi.EnumProcessModulesEx.argtypes = [
                    wintypes.HANDLE,
                    ctypes.POINTER(wintypes.HMODULE),
                    wintypes.DWORD,
                    ctypes.POINTER(wintypes.DWORD),
                    wintypes.DWORD,
                ]
                self._psapi.EnumProcessModulesEx.restype = wintypes.BOOL
            self._psapi.GetModuleBaseNameW.argtypes = [
                wintypes.HANDLE,
                wintypes.HMODULE,
                wintypes.LPWSTR,
                wintypes.DWORD,
            ]
            self._psapi.GetModuleBaseNameW.restype = wintypes.DWORD

        handle_value: Optional[int] = None

        if prefer_loaded:
            existing_handle, module_path = self._find_loaded_module(module_name)
            if existing_handle:
                if module_path:
                    try:
                        cdecl = ctypes.CDLL(module_path)
                        stdcall = ctypes.WinDLL(module_path)
                    except OSError:
                        pass
                    else:
                        self._cdecl = cdecl
                        self._stdcall = stdcall
                        handle_value = int(cdecl._handle)
                if handle_value is None:
                    handle_value = existing_handle
                    self._cdecl = _CDLLNoFree(None, handle=handle_value)
                    self._stdcall = _WinDLLNoFree(None, handle=handle_value)

        if handle_value is None:
            # ``CDLL``/``WinDLL`` load the module if it is not already present and
            # keep their own reference counts, so we can rely on their finalizers.
            try:
                self._cdecl = ctypes.CDLL(module_name)
                self._stdcall = ctypes.WinDLL(module_name)
            except OSError as exc:
                raise FileNotFoundError(
                    f"Could not locate {module_name}. Inject gwca.dll or provide an absolute path."
                ) from exc
            handle_value = int(self._cdecl._handle)

        self._handle = wintypes.HMODULE(handle_value)
        self._default_call_conv = default_call_conv.lower()
        self._initialized = False

        if not self.initialize():
            raise RuntimeError("GWCA::Initialize() failed")

    @property
    def handle(self) -> int:
        """Return the raw ``HMODULE`` handle."""

        return self._handle.value

    def initialize(self) -> bool:
        """Ensure ``GWCA::Initialize`` ran successfully."""

        if self._initialized:
            return True

        if GWCALibrary._global_init_result is not None:
            self._initialized = GWCALibrary._global_init_result
            return self._initialized

        with GWCALibrary._init_lock:
            if GWCALibrary._global_init_result is None:
                initialize = self.get_function(
                    "?Initialize@GW@@YA_NXZ", restype=c_bool
                )
                GWCALibrary._global_init_result = bool(initialize())
            self._initialized = GWCALibrary._global_init_result
        return self._initialized

    def get_function(
        self,
        symbol: Union[str, int],
        *,
        restype: Optional[ctypes._CData] = None,
        argtypes: Sequence[ctypes._CData] | None = None,
        call_conv: Optional[str] = None,
    ) -> ctypes._CFuncPtr:
        """Return a callable ctypes wrapper for an exported function.

        Parameters
        ----------
        symbol:
            Either the decorated export name (for example,
            ``"?GetMapID@Map@GW@@YA?AW4MapID@Constants@2@XZ"``) or the ordinal
            number published by the DLL (``193`` for ``GetMapID`` in the list
            provided by GWCA).
        restype:
            ``ctypes`` type that describes the function's return value. ``None``
            (the default) makes the wrapper behave like a ``void`` function.
        argtypes:
            Sequence describing the argument types for ``ctypes``. Providing it
            enables automatic type conversion and stack validation.
        call_conv:
            Override for the calling convention. ``"cdecl"`` uses the ``CDLL``
            binding while ``"stdcall"`` uses the ``WinDLL`` binding.

        Returns
        -------
        ``ctypes._CFuncPtr``
            A ready-to-use callable that can be invoked directly from Python.
        """

        binding = (call_conv or self._default_call_conv).lower()
        if binding not in {"cdecl", "stdcall"}:
            raise ValueError("call_conv must be either 'cdecl' or 'stdcall'")

        library = self._cdecl if binding == "cdecl" else self._stdcall
        if isinstance(symbol, int):
            lookup = f"#{symbol}"
        else:
            lookup = symbol
        try:
            func = getattr(library, lookup)
        except AttributeError as exc:  # pragma: no cover - defensive path
            raise AttributeError(
                f"Function '{symbol}' not found in {self._module_name}"
            ) from exc

        if argtypes is not None:
            func.argtypes = list(argtypes)
        if restype is not None:
            func.restype = restype
        return func

    def _find_loaded_module(self, module_name: str) -> tuple[Optional[int], Optional[str]]:
        """Return an existing module handle and its on-disk path if available."""

        candidates: list[str] = []
        path = Path(module_name)
        base = path.name
        stem = path.stem or base
        for name in (
            module_name,
            base,
            base.lower(),
            base.upper(),
            stem,
            stem.lower(),
            stem.upper(),
        ):
            if name and name not in candidates:
                candidates.append(name)

        for candidate in candidates:
            handle = self._kernel32.GetModuleHandleW(candidate)
            if handle:
                win_handle = wintypes.HMODULE(handle)
                path = self._get_module_path(win_handle)
                return int(win_handle.value), path

        enumerated = self._enumerate_process_modules()
        if enumerated:
            targets = {base.lower()}
            if stem:
                targets.add(stem.lower())

            for handle, module_path, module_base in enumerated:
                candidate_names: list[str] = []
                if module_path:
                    candidate_names.append(Path(module_path).name)
                    candidate_names.append(module_path)
                if module_base:
                    candidate_names.append(module_base)

                normalized: list[str] = []
                for name in candidate_names:
                    if not name:
                        continue
                    try:
                        normalized.append(str(name).lower())
                    except Exception:  # pragma: no cover - defensive
                        continue

                for name in normalized:
                    for target in targets:
                        if name == target or name.endswith(target):
                            return int(handle), module_path

                if stem:
                    stem_lower = stem.lower()
                    for name in candidate_names:
                        if not name:
                            continue
                        try:
                            if Path(str(name)).stem.lower() == stem_lower:
                                return int(handle), module_path
                        except Exception:  # pragma: no cover - defensive
                            continue

                # As a final fallback, probe for a well-known export on the
                # module handle in case the DLL was renamed during injection.
                try:
                    probe = _WinDLLNoFree(None, handle=int(handle))
                    getattr(probe, "GWCAVersion")
                except (AttributeError, OSError, ValueError):
                    continue
                else:
                    return int(handle), module_path
        return None, None

    def _get_module_path(
        self, handle: Union[int, wintypes.HMODULE]
    ) -> Optional[str]:
        """Resolve the filesystem path for a loaded module handle."""

        if isinstance(handle, int):
            handle = wintypes.HMODULE(handle)

        buffer_length = 260
        while True:
            buffer = ctypes.create_unicode_buffer(buffer_length)
            written = self._kernel32.GetModuleFileNameW(handle, buffer, buffer_length)
            if written == 0:
                return None
            if written < buffer_length - 1:
                return buffer.value
            buffer_length *= 2

    def _enumerate_process_modules(self) -> list[tuple[int, Optional[str], Optional[str]]]:
        """Return a list of modules loaded in the current process."""

        modules = self._enumerate_process_modules_psapi()
        if modules:
            return modules
        return self._enumerate_process_modules_toolhelp()

    def _enumerate_process_modules_psapi(
        self,
    ) -> list[tuple[int, Optional[str], Optional[str]]]:
        if self._psapi is None:
            return []

        capacity = 32
        process = self._kernel32.GetCurrentProcess()
        needed = wintypes.DWORD()
        modules: list[tuple[int, Optional[str], Optional[str]]] = []
        module_size = ctypes.sizeof(wintypes.HMODULE)

        enum_func = getattr(self._psapi, "EnumProcessModulesEx", None)
        enum_flags = 0x03  # LIST_MODULES_ALL
        while True:
            array_type = wintypes.HMODULE * capacity
            module_array = array_type()
            buffer_size = ctypes.sizeof(module_array)
            if enum_func is None:
                ok = self._psapi.EnumProcessModules(
                    process,
                    module_array,
                    buffer_size,
                    ctypes.byref(needed),
                )
            else:
                ok = enum_func(
                    process,
                    module_array,
                    buffer_size,
                    ctypes.byref(needed),
                    enum_flags,
                )
            if not ok:
                return []

            required_bytes = needed.value
            module_count = required_bytes // module_size
            if required_bytes <= buffer_size:
                for index in range(module_count):
                    raw_handle = module_array[index]
                    handle_value = int(raw_handle)
                    if handle_value == 0:
                        continue
                    modules.append(
                        (
                            handle_value,
                            self._get_module_path(handle_value),
                            self._get_module_base_name(handle_value),
                        )
                    )
                return modules

            capacity = module_count + 8

    def _enumerate_process_modules_toolhelp(
        self,
    ) -> list[tuple[int, Optional[str], Optional[str]]]:
        TH32CS_SNAPMODULE = 0x00000008
        TH32CS_SNAPMODULE32 = 0x00000010
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

        class MODULEENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("th32ModuleID", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("GlblcntUsage", wintypes.DWORD),
                ("ProccntUsage", wintypes.DWORD),
                ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
                ("modBaseSize", wintypes.DWORD),
                ("hModule", wintypes.HMODULE),
                ("szModule", wintypes.WCHAR * 256),
                ("szExePath", wintypes.WCHAR * 260),
            ]

        self._kernel32.Module32FirstW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(MODULEENTRY32W),
        ]
        self._kernel32.Module32FirstW.restype = wintypes.BOOL
        self._kernel32.Module32NextW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(MODULEENTRY32W),
        ]
        self._kernel32.Module32NextW.restype = wintypes.BOOL

        snapshot = self._kernel32.CreateToolhelp32Snapshot(
            TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
            self._kernel32.GetCurrentProcessId(),
        )
        if snapshot == INVALID_HANDLE_VALUE:
            return []

        modules: list[tuple[int, Optional[str], Optional[str]]] = []
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(MODULEENTRY32W)

        try:
            if not self._kernel32.Module32FirstW(snapshot, ctypes.byref(entry)):
                return []
            while True:
                handle_value = int(entry.hModule)
                if handle_value:
                    path = entry.szExePath or None
                    base = entry.szModule or None
                    modules.append((handle_value, path, base))
                if not self._kernel32.Module32NextW(snapshot, ctypes.byref(entry)):
                    break
        finally:
            self._kernel32.CloseHandle(snapshot)

        return modules

    def _get_module_base_name(
        self, handle: Union[int, wintypes.HMODULE]
    ) -> Optional[str]:
        """Return the base filename for a module handle."""

        if self._psapi is None:
            return None

        if isinstance(handle, int):
            handle = wintypes.HMODULE(handle)

        process = self._kernel32.GetCurrentProcess()
        buffer_length = 260
        while True:
            buffer = ctypes.create_unicode_buffer(buffer_length)
            written = self._psapi.GetModuleBaseNameW(
                process,
                handle,
                buffer,
                buffer_length,
            )
            if written == 0:
                return None
            if written < buffer_length - 1:
                return buffer.value
            buffer_length *= 2


class EncodedStringDecoder:
    """Decode Guild Wars encoded strings via ``GW::UI::AsyncDecodeStr``.

    Guild Wars stores many localized strings in an encoded wide-character
    format.  ``gwca.dll`` exposes ``AsyncDecodeStr`` which resolves those
    strings asynchronously on the game thread.  This helper mirrors the
    behaviour of GWToolbox's ``GuiUtils::EncString`` so Python scripts can
    synchronously obtain decoded text for quest names, item descriptions and
    similar fields.

    Parameters
    ----------
    library:
        Active :class:`GWCALibrary` instance used to look up ``AsyncDecodeStr``.
    timeout:
        Maximum time in seconds to wait for each string to decode before
        falling back to the raw encoded value.
    language:
        Optional ``GW::Constants::Language`` override.  The default (``0xFF``)
        lets the client pick the currently active language.
    """

    _DecodeCallback = ctypes.CFUNCTYPE(None, ctypes.py_object, ctypes.c_wchar_p)

    class _DecodeState:
        __slots__ = ("event", "result", "encoded")

        def __init__(self, encoded: ctypes.c_wchar_p) -> None:
            self.event = threading.Event()
            self.result: str | None = None
            # Keep a reference to the encoded pointer object alive until the
            # asynchronous decode finishes.
            self.encoded = encoded

    def __init__(
        self,
        library: GWCALibrary,
        *,
        timeout: float = 0.5,
        language: int = 0xFF,
    ) -> None:
        self._timeout = timeout
        self._language = language
        self._callback = self._DecodeCallback(self._on_decoded)
        self._decode = library.get_function(
            "?AsyncDecodeStr@UI@GW@@YAXPB_WP6AXPAX0@Z1W4Language@Constants@2@@Z",
            restype=None,
            argtypes=(
                ctypes.c_wchar_p,
                self._DecodeCallback,
                ctypes.py_object,
                c_uint32,
            ),
        )
        self._lock = threading.Lock()
        self._pending: set[EncodedStringDecoder._DecodeState] = set()

    def _start_decode(self, encoded: ctypes.c_wchar_p) -> _DecodeState:
        state = self._DecodeState(encoded)
        with self._lock:
            self._pending.add(state)
        try:
            self._decode(encoded, self._callback, state, self._language)
        except Exception:
            with self._lock:
                self._pending.discard(state)
            raise
        return state

    def _on_decoded(self, state: _DecodeState, decoded: str | None) -> None:
        state.result = decoded or ""
        state.event.set()
        with self._lock:
            self._pending.discard(state)

    def decode_many(self, pointers: Sequence[int | None]) -> list[str | None]:
        """Decode multiple encoded string pointers at once."""

        states: list[tuple[EncodedStringDecoder._DecodeState | None, str | None]] = []
        for pointer in pointers:
            if not pointer:
                states.append((None, None))
                continue
            try:
                address = int(pointer)
            except (TypeError, ValueError):
                address = pointer
            encoded = ctypes.cast(ctypes.c_void_p(address), ctypes.c_wchar_p)
            try:
                raw_value = encoded.value
            except (ValueError, OSError):
                states.append((None, None))
                continue
            if raw_value in (None, ""):
                states.append((None, raw_value or ""))
                continue
            state = self._start_decode(encoded)
            states.append((state, raw_value))

        results: list[str | None] = []
        for state, fallback in states:
            if state is None:
                results.append(fallback)
                continue
            if state.event.wait(self._timeout) and state.result is not None:
                results.append(state.result)
            elif state.event.is_set() and state.result is not None:
                results.append(state.result)
            else:
                results.append(fallback)
        return results

    def decode_pointer(self, pointer: int | None) -> str | None:
        """Decode a single encoded string pointer."""

        return self.decode_many([pointer])[0]


_shared_library: Optional[GWCALibrary] = None
_shared_library_lock = threading.Lock()


def get_shared_gwca_library(
    *,
    module_name: str = "gwca.dll",
    prefer_loaded: bool = True,
    default_call_conv: str = "cdecl",
) -> GWCALibrary:
    """Return the process-wide ``GWCALibrary`` instance."""

    global _shared_library
    with _shared_library_lock:
        if _shared_library is None:
            _shared_library = GWCALibrary(
                module_name=module_name,
                prefer_loaded=prefer_loaded,
                default_call_conv=default_call_conv,
            )
        else:
            if module_name != _shared_library._module_name:
                raise ValueError(
                    "GWCA is already loaded for module "
                    f"{_shared_library._module_name}, cannot switch to {module_name}"
                )
        return _shared_library


def load_gwca_function(
    symbol: Union[str, int],
    *,
    restype: Optional[ctypes._CData] = None,
    argtypes: Sequence[ctypes._CData] | None = None,
    call_conv: str = "cdecl",
    module_name: str = "gwca.dll",
    prefer_loaded: bool = True,
) -> ctypes._CFuncPtr:
    """Convenience wrapper that instantiates :class:`GWCALibrary` on demand."""

    library = get_shared_gwca_library(
        module_name=module_name,
        prefer_loaded=prefer_loaded,
        default_call_conv="cdecl",
    )
    return library.get_function(
        symbol,
        restype=restype,
        argtypes=argtypes,
        call_conv=call_conv,
    )
