# Calling functions exported by `GWCA.dll`

When the Guild Wars client has `GWCA.dll` injected you can call any of its
exports from a Py4GW script.  The new `Py4GWCoreLib.GWCA` helper removes the
boilerplate usually required to bind decorated C++ exports with `ctypes`.

## 1. Load the library and call `Initialize`

```python
from Py4GWCoreLib import GWCALibrary

gwca = GWCALibrary()  # reuses the already-injected module inside Guild Wars
gwca.initialize()     # ensures GWCA scanned memory and installed its hooks
```

`GWCALibrary` looks for an existing copy of the DLL inside the game process
and reuses that handle so you are always talking to the injected module rather
than loading a new copy.【F:Py4GWCoreLib/GWCA.py†L41-L57】  During construction it
invokes `GWCA::Initialize` and raises an error if the call fails, but invoking
`initialize()` explicitly at the start of your script makes the dependency
obvious and lets you retry in custom workflows.【F:Py4GWCoreLib/GWCA.py†L59-L80】

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
create the corresponding `ctypes` definitions before binding the function. For
example, the quest demo maps `GW::Quest` and its nested `GW::GamePos` before
calling `GW::QuestMgr::GetQuest`:

```python
import ctypes
from ctypes import POINTER, Structure, c_float, c_uint32, c_void_p


class GamePos(Structure):
    _fields_ = [
        ("x", c_float),
        ("y", c_float),
        ("plane", c_float),
    ]


class QuestStruct(Structure):
    _fields_ = [
        ("quest_id", c_uint32),
        ("log_state", c_uint32),
        ("location", c_void_p),
        ("name", c_void_p),
        ("npc", c_void_p),
        ("map_from", c_uint32),
        ("marker", GamePos),
        ("_unknown_0x24", c_uint32),
        ("map_to", c_uint32),
        ("description", c_void_p),
        ("objectives", c_void_p),
    ]


get_quest = gwca.get_function(
    "?GetQuest@QuestMgr@GW@@YAPAUQuest@2@W4QuestID@Constants@2@@Z",
    restype=POINTER(QuestStruct),
    argtypes=(c_uint32,),
)
quest_ptr = get_quest(quest_id)
if quest_ptr:
    quest = quest_ptr.contents
    quest_name = ctypes.wstring_at(quest.name) if quest.name else None
```

## 4. Decode encoded strings returned by Guild Wars

Many fields exposed by GWCA (quest names, item descriptions, agent names,
etc.) are stored as encoded ``wchar_t`` buffers inside the client.  Toolbox
wraps them in ``GuiUtils::EncString`` so the Guild Wars UI thread can decode
the localized text asynchronously.  ``Py4GWCoreLib.GWCA`` now provides a
matching :class:`EncodedStringDecoder` helper that mirrors this behaviour:

```python
from Py4GWCoreLib import EncodedStringDecoder, GWCALibrary

gwca = GWCALibrary()
decoder = EncodedStringDecoder(gwca)

quest = get_quest(quest_id).contents
name, description = decoder.decode_many([
    int(quest.name) if quest.name else None,
    int(quest.description) if quest.description else None,
])
```

The helper queues ``GW::UI::AsyncDecodeStr`` calls and waits briefly for the
callback so scripts receive human-readable strings inside the same frame.
Fallback logic keeps the encoded text available if decoding takes longer than
expected.【F:Py4GWCoreLib/GWCA.py†L142-L257】

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
