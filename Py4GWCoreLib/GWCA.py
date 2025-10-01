"""Helpers for calling exported functions from GWCA.dll.

This module offers a thin wrapper around :mod:`ctypes` so Py4GW scripts can
bind decorated exports from ``GWCA.dll`` (the Guild Wars Client API library).
The helpers only deal with obtaining the function pointer and applying the
correct calling convention; scripts are still responsible for mapping the
arguments and return types to matching ``ctypes`` declarations.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional, Sequence, Union

__all__ = ["GWCALibrary", "load_gwca_function"]


class GWCALibrary:
    """Lightweight loader for ``GWCA.dll`` exports.

    Parameters
    ----------
    module_name:
        Name of the DLL to load. Defaults to ``"GWCA.dll"`` which is the
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

    def __init__(
        self,
        module_name: str = "GWCA.dll",
        *,
        prefer_loaded: bool = True,
        default_call_conv: str = "cdecl",
    ) -> None:
        self._module_name = module_name
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = wintypes.HMODULE()
        if prefer_loaded:
            existing = self._kernel32.GetModuleHandleW(module_name)
            if existing:
                handle = wintypes.HMODULE(existing)
        if not handle.value:
            # ``CDLL``/``WinDLL`` load the module if it is not already present.
            self._cdecl = ctypes.CDLL(module_name)
            self._stdcall = ctypes.WinDLL(module_name)
            handle = wintypes.HMODULE(self._cdecl._handle)
        else:
            # Wrap the existing handle without reloading the DLL.
            self._cdecl = ctypes.CDLL(None, handle=handle.value)
            self._stdcall = ctypes.WinDLL(None, handle=handle.value)
        self._handle = handle
        self._default_call_conv = default_call_conv.lower()

    @property
    def handle(self) -> int:
        """Return the raw ``HMODULE`` handle."""

        return self._handle.value

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


def load_gwca_function(
    symbol: Union[str, int],
    *,
    restype: Optional[ctypes._CData] = None,
    argtypes: Sequence[ctypes._CData] | None = None,
    call_conv: str = "cdecl",
    module_name: str = "GWCA.dll",
    prefer_loaded: bool = True,
) -> ctypes._CFuncPtr:
    """Convenience wrapper that instantiates :class:`GWCALibrary` on demand."""

    library = GWCALibrary(
        module_name=module_name,
        prefer_loaded=prefer_loaded,
        default_call_conv=call_conv,
    )
    return library.get_function(
        symbol,
        restype=restype,
        argtypes=argtypes,
        call_conv=call_conv,
    )
