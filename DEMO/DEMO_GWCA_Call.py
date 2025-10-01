import ctypes
import traceback

import Py4GW  # Py4GW console for logging messages back to the UI

MODULE_NAME = "GWCA Call Demo"

try:
    GWCA = ctypes.WinDLL("gwca.dll", use_last_error=True)
    # Ordinal 152 corresponds to ?GetInstanceTime@Map@GW@@YAIXZ in the exported list.
    GetInstanceTime = ctypes.WINFUNCTYPE(ctypes.c_uint32)((152, GWCA))
except OSError as load_error:
    GWCA = None
    GetInstanceTime = None
    LOAD_ERROR = load_error
else:
    LOAD_ERROR = None


def log(message: str, level: int = Py4GW.Console.MessageType.Info) -> None:
    """Helper that routes log output to the Py4GW console."""
    Py4GW.Console.Log(MODULE_NAME, message, level)


def main() -> None:
    """Demonstrate calling a GWCA export from Python."""
    if GWCA is None or GetInstanceTime is None:
        error_info = f"Failed to load gwca.dll: {LOAD_ERROR}" if LOAD_ERROR else "Unknown load failure"
        log(error_info, Py4GW.Console.MessageType.Error)
        win_error = ctypes.get_last_error()
        if win_error:
            log(f"Last Win32 error: {win_error}", Py4GW.Console.MessageType.Debug)
        return

    try:
        elapsed_ms = GetInstanceTime()
    except OSError as exc:
        log(f"GetInstanceTime call failed: {exc}", Py4GW.Console.MessageType.Error)
        win_error = ctypes.get_last_error()
        if win_error:
            log(f"Last Win32 error: {win_error}", Py4GW.Console.MessageType.Debug)
    except Exception as exc:  # pragma: no cover - defensive logging for unexpected issues
        log(f"Unexpected error while calling GetInstanceTime: {exc}", Py4GW.Console.MessageType.Error)
        log(traceback.format_exc(), Py4GW.Console.MessageType.Error)
    else:
        log(f"Instance time reported by GWCA: {elapsed_ms} ms")


if __name__ == "__main__":
    main()
