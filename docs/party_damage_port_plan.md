# Porting plan: PartyDamage widget

## 1. Understand the Guild Wars Toolbox implementation
- Review how the C++ widget stores running damage totals per party member (`PlayerDamage`) and keeps separate "recent" damage with a timeout so the overlay can show two bars.【F:Dependencies/GWToolboxpp/GWToolboxdll/Widgets/PartyDamage.cpp†L70-L226】
- Capture the behaviour of the `/dmg` chat command: it prints party totals, individual entries, "me", and "reset" options, and throttles chat output through a queue processed during `Update`.【F:Dependencies/GWToolboxpp/GWToolboxdll/Widgets/PartyDamage.cpp†L125-L265】【F:Dependencies/GWToolboxpp/GWToolboxdll/Widgets/PartyDamage.cpp†L315-L333】
- Note the hook registrations: the widget subscribes to `GenericModifier` packets to detect damage, resets totals on `MapLoaded`, and tears everything down in `Terminate`.【F:Dependencies/GWToolboxpp/GWToolboxdll/Widgets/PartyDamage.cpp†L158-L226】【F:Dependencies/GWToolboxpp/GWToolboxdll/Widgets/PartyDamage.cpp†L281-L313】
- The drawing routine depends on `SnapsToPartyWindow` helpers to align the bars with Guild Wars' party UI, colours configurable bars, and handles ctrl+click to print a single player's contribution.【F:Dependencies/GWToolboxpp/GWToolboxdll/Widgets/PartyDamage.cpp†L335-L483】
- Settings are persisted both to the Toolbox INI and to a dedicated `healthlog.ini` file that caches enemy max HP estimates for later scaling.【F:Dependencies/GWToolboxpp/GWToolboxdll/Widgets/PartyDamage.cpp†L490-L546】

## 2. Inventory available Py4GW building blocks
- Follow the standard widget structure from `Widgets/WidgetTemplate.py` (window persistence, `main()` guard, cached data updates) when scaffolding the Python port.【F:Widgets/WidgetTemplate.py†L1-L110】
- Audit existing widgets that render ImGui overlays (for example `Widgets/Party Minions Viewer.py`) to reuse table/window patterns, timers, and cached name lookups for party agents.
- Review `Py4GWCoreLib` modules for functionality parity:
  - `Agent`, `AgentArray`, `Player`, and `Party` expose agent and party information that can replace `SnapsToPartyWindow::FetchPartyInfo()` lookups.
  - `PyImGui` and colour utilities provide the drawing primitives required for stacked bars.
  - `IniHandler` supports the window-position persistence seen in the C++ settings flow and can be extended to manage the `healthlog.ini` cache.
  - Investigate whether GWCA packet hooks (StoC `GenericModifier` and `MapLoaded`) are already exposed to Python; if not, plan to extend the bindings.

## 3. Suggested implementation tasks
1. **Expose needed GWCA hooks**
   - Confirm whether Py4GW already surfaces StoC callbacks for `GenericModifier` and `MapLoaded`. If absent, add ctypes bindings in `Py4GWCoreLib.GWCA` (or a dedicated hook manager) to register/unregister callbacks similar to Toolbox.
   - Provide Python-side dispatch that normalises packet data (damage amount, cause/target IDs) and runs safely on the main thread.
2. **Build the damage tracking model**
   - Create a `PlayerDamage` dataclass mirroring the C++ fields (total, recent, timestamp, profession IDs, agent mapping).
   - Maintain dictionaries for `hp_map`, total damage, recent damage timeout, and party index lookups. Reuse Py4GW's party caches or mirror `SnapsToPartyWindow` logic to keep `party_indeces_by_agent_id` in sync.
   - Implement helpers to convert `GenericModifier` packets into scaled integer damage, respecting allegiance filters and cached max HP approximations from `healthlog.ini`.
3. **Persist configuration and HP cache**
   - Store widget options (width, colours, offsets, behaviour toggles) using the widget manager defaults and the widget's INI file, matching the Toolbox settings surface.
   - Load and save the HP cache to a secondary INI (`healthlog.ini`) via `IniHandler`, mirroring the C++ `hp_map` logic.
4. **Chat command integration**
   - Expose `/dmg` command handling by binding to Py4GW's chat helpers (e.g. `Player.SendChatCommand`), replicating the queue/throttle so reports respect Toolbox's 600 ms cadence.
   - Support `print/report`, `me`, numeric indices, and `reset` arguments, and ensure the output formatting matches expectations.
5. **Rendering the overlay**
   - Use `PyImGui` to create a window that either overlays the party UI or anchors beside it, depending on the `overlay_party_window` flag.
   - Render background rectangles, total/recent bars, numerical and percentage labels, and handle ctrl+click printing of individual players.
   - Integrate with whatever Python equivalent of `SnapsToPartyWindow` exists; if missing, replicate the functionality to compute party health bar bounds from UI frame metrics.
6. **Lifecycle management**
   - During `main()`, gate updates on `Routines.Checks` (map ready, party loaded) and call update/render functions accordingly.
   - Reset state on map transitions, drop hooks during shutdown, and guard against missing data when players join/leave.
7. **Testing and validation**
   - Unit-test helpers that parse packet data and format chat strings.
   - Run in-game smoke tests to confirm damage is tracked correctly, chat commands work, settings persist, and the overlay follows the party window in both outposts and explorable areas.

## 4. Open questions / risks
- Py4GW may not yet expose the UI layout data that `SnapsToPartyWindow` relies on; scoping the required UI manager calls is necessary before attempting a one-to-one port.
- Hooking Guild Wars packets from Python could require threading or callback-safety considerations. Design the binding with care to avoid crashes or freezes.
- Performance: iterating over the whole party each frame should be profiled to ensure the Python port stays responsive, especially when recalculating party positions.
