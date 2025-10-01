# Calling functions exported by `GWCA.dll`

When the Guild Wars client has `GWCA.dll` injected you can call any of its
exports from a Py4GW script.  The new `Py4GWCoreLib.GWCA` helper removes the
boilerplate usually required to bind decorated C++ exports with `ctypes`.

## 1. Load the library once

```python
from Py4GWCoreLib import GWCALibrary

gwca = GWCALibrary()  # reuses the already-injected module inside Guild Wars
```

`GWCALibrary` looks for an existing copy of the DLL inside the game process
and reuses that handle so you are always talking to the injected module rather
than loading a new copy.【F:Py4GWCoreLib/GWCA.py†L41-L57】

If you only need a single function you can skip the explicit instance and call
`load_gwca_function(...)` instead, which internally constructs a
`GWCALibrary` and returns the bound callable.【F:Py4GWCoreLib/GWCA.py†L102-L118】

## 2. Bind the function you need

Pass either the decorated export name or the ordinal from your dump together
with the expected signature:

```python
from ctypes import c_bool, c_uint32

# Using the decorated name
destroy_item = gwca.get_function(
    "?DestroyItem@Items@GW@@YA_NI@Z",
    restype=c_bool,
    argtypes=(c_uint32,),
)

# Using the ordinal number (466 == UseSkill in the table you provided)
use_skill = gwca.get_function(
    466,
    restype=c_bool,
    argtypes=(c_uint32, c_uint32),
)
```

The helper accepts either `cdecl` (GWCA’s default) or `stdcall` bindings and
exposes them via the `call_conv` parameter when needed.【F:Py4GWCoreLib/GWCA.py†L59-L100】

## 3. Call the function inside your script

```python
item_id = 0x12345678
if destroy_item(item_id):
    print(f"Destroyed item {item_id:#x}")

skill_id = 5
current_target = 0  # use 0 to keep the current target
gwca.Console.Log("demo", f"Use skill {skill_id}")
use_skill(skill_id, current_target)
```

Because the return value and parameter types are backed by `ctypes`, Python
will automatically marshal integral values for you. For pointers or structures
create the corresponding `ctypes` definitions before binding the function.

## Tips

* Keep using the Py4GW helper APIs (agents, inventory, etc.) whenever they
  already expose the behaviour you need. Drop down to `GWCA.dll` only for
  features that have not been wrapped yet.
* Many GWCA exports expect to be executed on the Guild Wars game thread. Use
  the existing `GameThread` utilities from Py4GW when you need to enqueue work
  there before calling into GWCA.
* Invalid signatures or incorrect calling conventions typically crash the
  Guild Wars client. Double-check the parameters against the GWCA headers in
  `external/GWToolboxpp/Dependencies/GWCA/include` when in doubt.
