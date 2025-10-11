# Skillbar Encoding Research

## Existing References in Py4GW
- `Py4GWCoreLib/Skillbar.py` exposes helper methods to load skill templates and read the current bar, but it does not expose any API to encode the bar into a Guild Wars build template string. All functions either query the skill slots or call into the C extension to load a template. No encode-related methods are implemented.  
- The generated stub `stubs/PySkillbar.pyi` documents the methods available on the `PySkillbar.Skillbar` extension class. Similar to the Python facade, it includes getters, `LoadSkillTemplate`, and hero helpers, but there is no `EncodeSkillTemplate` counterpart or any other method that returns a build code.

## Relevant Implementations in C++ Dependencies
- Guild Wars Toolbox (`Dependencies/GWToolboxpp`) uses GWCA's `GW::SkillbarMgr::EncodeSkillTemplate` to turn the in-memory skillbar into a template string (e.g. `Dependencies/GWToolboxpp/GWToolboxdll/Windows/BuildsWindow.cpp`).
- The underlying Guild Wars Client API (`Dependencies/GWCA/Source/SkillbarMgr.cpp`) implements `EncodeSkillTemplate`, `DecodeSkillTemplate`, and `LoadSkillTemplate`, providing the low-level logic required to build or parse the template strings.

## Recommendation
Py4GW currently only supports **loading** templates. To support encoding the live skillbar into a template string, we should:
1. Inspect the GWToolbox/GWCA implementations of `EncodeSkillTemplate` to understand the necessary data structures and bit packing logic.
2. Add equivalent bindings in the Py4GW C++ layer (or leverage existing DLL exports if available) to expose an `EncodeSkillTemplate` function.
3. Wrap the new binding inside `Py4GWCoreLib/Skillbar.py` (and update `stubs/PySkillbar.pyi`) with a friendly Python API, e.g. `SkillBar.EncodeSkillTemplate()`.
4. Provide unit/integration tests or an example script demonstrating round-trip encode/decode of skillbars.

This work would let bots or tools capture the player's current build string directly from the game client, matching the capabilities already available in the C++ tooling.
