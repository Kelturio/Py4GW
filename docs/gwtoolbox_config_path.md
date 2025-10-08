# Locating the GWToolbox Configuration Path

Injected instances of GWToolbox load their configuration files from the per-computer folder that the toolbox creates in the user's **Documents** directory. The location is determined at runtime by the `Resources` helper inside the injected DLL:

* `Resources::GetComputerFolderPath()` first resolves `%USERPROFILE%\\Documents\\GWToolboxpp` and appends the current Windows computer name, creating the folder if it does not already exist.【F:Dependencies/GWToolboxpp/GWToolboxdll/Modules/Resources.cpp†L457-L475】【F:Dependencies/GWToolboxpp/Core/Path.cpp†L37-L71】
* `Resources::GetSettingsFolderPath()` reuses that computer folder and, if a profile-specific subdirectory has been selected (for example via `/config load <profile>`), appends it under `configs/<profile>`.【F:Dependencies/GWToolboxpp/GWToolboxdll/Modules/Resources.cpp†L476-L493】

To inspect which configuration file is in use:

1. Determine the Documents path and computer folder as described above (e.g. `C:\\Users\\<name>\\Documents\\GWToolboxpp\\<COMPUTER_NAME>\\`).
2. If no custom profile is active, GWToolbox reads `GWToolbox.ini` and other data directly from that folder.
3. If a profile is active, look inside `configs\\<profile>` within the same folder for the configuration that GWToolbox currently loads.

These paths are the same regardless of whether GWToolbox is launched standalone or injected by Py4GW, because the injected DLL calls the same helper when bootstrapping its configuration state.【F:Dependencies/GWToolboxpp/GWToolboxdll/GWToolbox.cpp†L1079-L1080】
