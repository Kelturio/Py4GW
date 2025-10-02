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
import threading
import weakref
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
        self._finalizer: Optional[weakref.Finalize] = None

        handle_value: Optional[int] = None

        if prefer_loaded:
            existing = self._kernel32.GetModuleHandleW(module_name)
            if existing:
                duplicate = self._kernel32.LoadLibraryW(module_name)
                if not duplicate:  # pragma: no cover - defensive path
                    raise ctypes.WinError(ctypes.get_last_error())
                handle_value = int(duplicate)
                self._cdecl = _CDLLNoFree(None, handle=handle_value)
                self._stdcall = _WinDLLNoFree(None, handle=handle_value)
                self._finalizer = weakref.finalize(
                    self,
                    self._kernel32.FreeLibrary,
                    wintypes.HMODULE(handle_value),
                )

        if handle_value is None:
            # ``CDLL``/``WinDLL`` load the module if it is not already present and
            # keep their own reference counts, so we can rely on their finalizers.
            self._cdecl = ctypes.CDLL(module_name)
            self._stdcall = ctypes.WinDLL(module_name)
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
