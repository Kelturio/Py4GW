# Calling `gwca.dll` exports from Py4GW scripts

The Guild Wars client exposes a large set of helper functions through `gwca.dll`. Once the
library is injected you can call any of its exports from a Py4GW script by using the standard
`ctypes` module.  The steps below show the full workflow and highlight a few common pitfalls.

## 1. Make sure the DLL is loaded
Py4GW runs inside the Guild Wars process after the launcher injects the automation DLL.  As long
as your injector has already loaded `gwca.dll` into the game process you can access it straight
from Python.  No additional initialization is required on the Python side.

```python
import ctypes

gwca = ctypes.WinDLL("gwca.dll", use_last_error=True)
```

If the DLL lives under a different name or path, adjust the argument accordingly.  You can verify
that the load succeeded by checking `ctypes.get_last_error()` or by wrapping the call in a
`try/except OSError` block.

## 2. Bind a function by ordinal or decorated name
The export list often contains decorated C++ names (for example
`?GetInstanceTime@Map@GW@@YAIXZ`).  Calling them by string can be awkward because you must pass the
exact decorated name.  The export list in the question also contains ordinals, which are easier to
use with `ctypes`:

```python
GetInstanceTime = ctypes.WINFUNCTYPE(ctypes.c_uint32)((152, gwca))
```

`ctypes.WINFUNCTYPE` creates a callable that knows both the return type and the argument types.
The tuple `(152, gwca)` instructs `ctypes` to bind to export ordinal **152** from the already
loaded `gwca` module.  Replace `ctypes.c_uint32` and the ordinal with the correct signature for the
function you want to call.  For exports that take arguments just list their ctypes equivalents after
the return type, e.g. `ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint32, ctypes.c_uint32)`.

If you prefer to bind by name you can do it as well:

```python
GetInstanceTime = ctypes.WINFUNCTYPE(ctypes.c_uint32)(("?GetInstanceTime@Map@GW@@YAIXZ", gwca))
```

## 3. Call the function from your script
Once you have a callable object you can invoke it like a normal Python function.  The snippet below
uses Py4GW's console to log the value returned by `GetInstanceTime`.

```python
import Py4GW

MODULE_NAME = "GWCA Call Demo"

def log_instance_time():
    try:
        elapsed = GetInstanceTime()
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Instance time: {elapsed} ms",
            Py4GW.Console.MessageType.Info,
        )
    except OSError as exc:
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Failed to call GetInstanceTime: {exc}",
            Py4GW.Console.MessageType.Error,
        )
```

Remember that most GWCA functions expect to be executed from the game thread.  When you are unsure
whether a call is thread-safe, dispatch it through the game-thread helper provided by Py4GW (for
example `Py4GW.GameThread.Enqueue` in standard builds) so it runs inside the client's game loop.

## 4. Re-use the binding in multiple scripts
You can keep the binding logic in a helper module if you need to call several exports from many
scripts.  The new demo script `DEMO/DEMO_GWCA_Call.py` in this repository shows a complete example
that you can copy into your own project.  Feel free to adjust the ordinals and signatures to match
the GWCA function you need.
