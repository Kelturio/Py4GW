import json
import os
import traceback
from datetime import datetime
from typing import List

import Py4GW
from Py4GWCoreLib import Bags
from Py4GWCoreLib import GLOBAL_CACHE
from Py4GWCoreLib import IniHandler
from Py4GWCoreLib import PyImGui
from Py4GWCoreLib import PyInventory
from Py4GWCoreLib import Routines
from Py4GWCoreLib import Timer

MODULE_NAME = "Storage Exporter"

script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))
config_path = os.path.join(project_root, "Widgets/Config/StorageExporter.ini")
export_base_dir = os.path.join(project_root, "Widgets/Data/StorageExporter")
latest_snapshot_path = os.path.join(export_base_dir, "latest_snapshot.json")
history_dir = os.path.join(export_base_dir, "history")

os.makedirs(export_base_dir, exist_ok=True)

ini_handler = IniHandler(config_path)

first_run = True
window_x = ini_handler.read_int(MODULE_NAME, "x", 100)
window_y = ini_handler.read_int(MODULE_NAME, "y", 100)
window_collapsed = ini_handler.read_bool(MODULE_NAME, "collapsed", False)

save_window_timer = Timer()
save_window_timer.Start()


def _format_bag_name(bag_enum: Bags) -> str:
    name = bag_enum.name
    if name == "BeltPouch":
        return "Belt Pouch"
    if name == "EquipmentPack":
        return "Equipment Pack"
    if name == "MaterialStorage":
        return "Material Storage"
    if name.startswith("Storage") and len(name) > len("Storage"):
        return f"Storage {name[len('Storage') :]}"
    if name.startswith("Bag") and len(name) > len("Bag"):
        return f"Bag {name[len('Bag') :]}"
    return name.replace("_", " ")


class ExporterState:
    def __init__(self) -> None:
        self.export_enabled = ini_handler.read_bool(MODULE_NAME, "export_enabled", True)
        self.auto_open_storage = ini_handler.read_bool(MODULE_NAME, "auto_open_storage", True)
        self.include_equipment_pack = ini_handler.read_bool(MODULE_NAME, "include_equipment_pack", False)
        self.write_history = ini_handler.read_bool(MODULE_NAME, "write_history", False)
        self.interval_minutes = max(1, ini_handler.read_int(MODULE_NAME, "interval_minutes", 5))

        self.timer = Timer()
        self.timer.Start()
        self.retry_timer = Timer()
        self.retry_timer.Start()
        self.retry_interval_ms = 2000

        self.pending_export = False
        self.pending_manual = False
        self.waiting_for_storage = False

        self.last_export_timestamp: str = ""
        self.last_export_path: str = ""
        self.last_inventory_count = 0
        self.last_storage_count = 0
        self.status_message: str = ""
        self.status_is_error = False

    def set_export_enabled(self, enabled: bool) -> None:
        self.export_enabled = bool(enabled)
        ini_handler.write_key(MODULE_NAME, "export_enabled", str(self.export_enabled))
        if self.export_enabled:
            self.timer.Reset()
        else:
            self.pending_export = False
            self.pending_manual = False
            self.waiting_for_storage = False
            self.status_message = "Automatic exports disabled."
            self.status_is_error = False

    def set_interval_minutes(self, minutes: int) -> None:
        minutes = max(1, int(minutes))
        if minutes != self.interval_minutes:
            self.interval_minutes = minutes
            ini_handler.write_key(MODULE_NAME, "interval_minutes", str(self.interval_minutes))
            self.timer.Reset()

    def set_auto_open_storage(self, enabled: bool) -> None:
        self.auto_open_storage = bool(enabled)
        ini_handler.write_key(MODULE_NAME, "auto_open_storage", str(self.auto_open_storage))

    def set_include_equipment_pack(self, enabled: bool) -> None:
        self.include_equipment_pack = bool(enabled)
        ini_handler.write_key(MODULE_NAME, "include_equipment_pack", str(self.include_equipment_pack))

    def set_write_history(self, enabled: bool) -> None:
        self.write_history = bool(enabled)
        ini_handler.write_key(MODULE_NAME, "write_history", str(self.write_history))

    def trigger_manual_export(self) -> None:
        self.pending_export = True
        self.pending_manual = True
        self.waiting_for_storage = False
        self.retry_timer.Reset()
        self.status_message = "Manual export queued."
        self.status_is_error = False
        Py4GW.Console.Log(MODULE_NAME, "Manual export requested.", Py4GW.Console.MessageType.Info)

    def update(self, allow_export: bool) -> None:
        if not allow_export:
            return

        if self.export_enabled and self.timer.HasElapsed(self.get_interval_ms()):
            self.pending_export = True
            self.pending_manual = False
            self.waiting_for_storage = False
            self.retry_timer.Reset()
            self.status_message = "Automatic export queued."
            self.status_is_error = False

        if self.pending_export:
            if self.waiting_for_storage and not self.retry_timer.HasElapsed(self.retry_interval_ms):
                return
            self._attempt_export(self.pending_manual)

    def get_interval_ms(self) -> int:
        return max(60_000, int(self.interval_minutes * 60_000))

    def time_until_next_export(self) -> int:
        interval = self.get_interval_ms()
        elapsed = int(self.timer.GetElapsedTime())
        remaining = max(0, interval - elapsed)
        if self.pending_export:
            return 0
        return remaining

    def has_pending_export(self) -> bool:
        return self.pending_export

    def get_last_export_relative_path(self) -> str:
        if not self.last_export_path:
            return ""
        try:
            return os.path.relpath(self.last_export_path, project_root)
        except ValueError:
            return self.last_export_path

    def _attempt_export(self, manual: bool) -> None:
        if not GLOBAL_CACHE.Inventory.IsStorageOpen():
            if self.auto_open_storage:
                GLOBAL_CACHE.Inventory.OpenXunlaiWindow()
                self.status_message = "Waiting for Xunlai storage to open..."
                self.status_is_error = False
            else:
                self.status_message = "Xunlai storage is closed. Open it to export."
                self.status_is_error = True
            self.waiting_for_storage = True
            self.retry_timer.Reset()
            return

        if self._export_snapshot(manual):
            self.pending_export = False
            self.pending_manual = False
            self.waiting_for_storage = False
            self.timer.Reset()
            self.retry_timer.Reset()

    def _export_snapshot(self, manual: bool) -> bool:
        try:
            snapshot = self._build_snapshot(manual)
            with open(latest_snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, indent=2, ensure_ascii=False)

            export_path = latest_snapshot_path
            if self.write_history:
                os.makedirs(history_dir, exist_ok=True)
                history_name = self._build_history_filename(snapshot["timestamp"], manual)
                export_path = os.path.join(history_dir, history_name)
                with open(export_path, "w", encoding="utf-8") as history_handle:
                    json.dump(snapshot, history_handle, indent=2, ensure_ascii=False)

            inventory_items = sum(len(bag["items"]) for bag in snapshot["inventory"]["bags"])
            storage_items = sum(len(bag["items"]) for bag in snapshot["storage"]["bags"])

            self.last_export_timestamp = snapshot["timestamp"]
            self.last_export_path = export_path
            self.last_inventory_count = inventory_items
            self.last_storage_count = storage_items

            export_mode = "Manual" if manual else "Automatic"
            relative_path = self.get_last_export_relative_path()
            self.status_message = (
                f"{export_mode} export complete: {inventory_items} inventory items and "
                f"{storage_items} storage items saved to {relative_path}."
            )
            self.status_is_error = False

            Py4GW.Console.Log(
                MODULE_NAME,
                f"{export_mode} export wrote {inventory_items} inventory and {storage_items} storage items to {relative_path}.",
                Py4GW.Console.MessageType.Info,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self.status_message = f"Export failed: {exc}"
            self.status_is_error = True
            Py4GW.Console.Log(MODULE_NAME, self.status_message, Py4GW.Console.MessageType.Error)
            Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
            return False

    def _build_snapshot(self, manual: bool) -> dict:
        timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        inventory_bags = self._collect_bags(self._inventory_bags())
        storage_bags = self._collect_bags(self._storage_bags())

        snapshot = {
            "timestamp": timestamp,
            "manual": manual,
            "character": GLOBAL_CACHE.Player.GetName(),
            "map": {
                "id": GLOBAL_CACHE.Map.GetMapID(),
                "name": GLOBAL_CACHE.Map.GetMapName(),
            },
            "gold": {
                "character": GLOBAL_CACHE.Inventory.GetGoldOnCharacter(),
                "storage": GLOBAL_CACHE.Inventory.GetGoldInStorage(),
            },
            "inventory": {"bags": inventory_bags},
            "storage": {"bags": storage_bags},
        }
        return snapshot

    def _build_history_filename(self, timestamp: str, manual: bool) -> str:
        safe_timestamp = timestamp.replace(":", "-")
        suffix = "manual" if manual else "auto"
        return f"snapshot_{safe_timestamp}_{suffix}.json"

    def _collect_bags(self, bag_enums: List[Bags]) -> List[dict]:
        bag_data = []
        for bag_enum in bag_enums:
            bag_data.append(self._collect_single_bag(bag_enum))
        return bag_data

    def _collect_single_bag(self, bag_enum: Bags) -> dict:
        bag = PyInventory.Bag(bag_enum.value, bag_enum.name)
        try:
            bag.GetContext()
        except AttributeError:
            pass

        try:
            size = int(bag.GetSize())
        except Exception:  # noqa: BLE001
            size = 0

        try:
            raw_items = bag.GetItems() or []
        except Exception:  # noqa: BLE001
            raw_items = []

        items = []
        for item in raw_items:
            try:
                items.append(self._serialize_item(item, bag_enum))
            except Exception as exc:  # noqa: BLE001
                Py4GW.Console.Log(
                    MODULE_NAME,
                    f"Failed to read item {getattr(item, 'item_id', '?')} in {bag_enum.name}: {exc}",
                    Py4GW.Console.MessageType.Warning,
                )
        items.sort(key=lambda entry: entry.get("slot", -1))

        return {
            "bag_id": int(getattr(bag, "id", bag_enum.value)),
            "bag_enum": bag_enum.name,
            "bag_name": _format_bag_name(bag_enum),
            "size": size,
            "item_count": len(items),
            "items": items,
        }

    def _serialize_item(self, item, bag_enum: Bags) -> dict:
        try:
            item.GetContext()
        except AttributeError:
            pass

        rarity = getattr(item, "rarity", None)
        rarity_name = getattr(rarity, "name", None)
        rarity_value = getattr(rarity, "value", None)

        modifiers = getattr(item, "modifiers", None) or []
        try:
            mod_count = len(modifiers)
        except TypeError:
            mod_count = 0

        name = getattr(item, "name", "")

        return {
            "item_id": int(getattr(item, "item_id", 0)),
            "model_id": int(getattr(item, "model_id", 0)),
            "bag_enum": bag_enum.name,
            "slot": int(getattr(item, "slot", -1)),
            "quantity": int(getattr(item, "quantity", 0)),
            "rarity": rarity_name,
            "rarity_value": int(rarity_value) if rarity_value is not None else None,
            "identified": bool(getattr(item, "is_identified", False)),
            "stackable": bool(getattr(item, "is_stackable", False)),
            "tradable": bool(getattr(item, "is_tradable", False)),
            "material": bool(getattr(item, "is_material", False)),
            "usable": bool(getattr(item, "is_usable", False)),
            "name": str(name) if name else "",
            "mod_count": int(mod_count),
        }

    def _inventory_bags(self) -> List[Bags]:
        bags = [Bags.Backpack, Bags.BeltPouch, Bags.Bag1, Bags.Bag2]
        if self.include_equipment_pack:
            bags.append(Bags.EquipmentPack)
        return bags

    def _storage_bags(self) -> List[Bags]:
        storage_bags = [Bags.MaterialStorage]
        storage_bags.extend([
            Bags.Storage1,
            Bags.Storage2,
            Bags.Storage3,
            Bags.Storage4,
            Bags.Storage5,
            Bags.Storage6,
            Bags.Storage7,
            Bags.Storage8,
            Bags.Storage9,
            Bags.Storage10,
            Bags.Storage11,
            Bags.Storage12,
            Bags.Storage13,
            Bags.Storage14,
        ])
        return storage_bags


export_state = ExporterState()


def _format_duration(milliseconds: int) -> str:
    seconds, ms = divmod(max(0, milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02}m {seconds:02}s"
    if minutes:
        return f"{minutes}m {seconds:02}s"
    return f"{seconds}s" if ms == 0 else f"{seconds}.{ms:03d}s"


def draw_widget(state: ExporterState) -> None:
    global first_run, window_x, window_y, window_collapsed

    if first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        first_run = False

    is_window_opened = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
    new_collapsed = PyImGui.is_window_collapsed()
    end_pos = PyImGui.get_window_pos()

    if is_window_opened:
        PyImGui.text("Automatically export inventory and Xunlai storage snapshots to disk.")
        PyImGui.separator()

        prev_enabled = state.export_enabled
        enabled = PyImGui.checkbox("Enable automatic export", prev_enabled)
        if enabled != prev_enabled:
            state.set_export_enabled(enabled)

        if PyImGui.button("Export now"):
            state.trigger_manual_export()
        PyImGui.same_line(0.0, -1.0)
        PyImGui.text("Manual export")

        interval_value = PyImGui.slider_int("Export interval (minutes)", state.interval_minutes, 1, 60)
        if interval_value != state.interval_minutes:
            state.set_interval_minutes(interval_value)

        auto_open = PyImGui.checkbox("Open Xunlai storage automatically", state.auto_open_storage)
        if auto_open != state.auto_open_storage:
            state.set_auto_open_storage(auto_open)

        include_pack = PyImGui.checkbox("Include equipment pack", state.include_equipment_pack)
        if include_pack != state.include_equipment_pack:
            state.set_include_equipment_pack(include_pack)

        history = PyImGui.checkbox("Keep timestamped history", state.write_history)
        if history != state.write_history:
            state.set_write_history(history)

        PyImGui.separator()

        if state.export_enabled:
            next_run = _format_duration(state.time_until_next_export())
            PyImGui.text(f"Next automatic export in: {next_run}")
        else:
            PyImGui.text("Automatic export is disabled.")

        PyImGui.text(f"Pending export: {'Yes' if state.has_pending_export() else 'No'}")

        last_timestamp = state.last_export_timestamp or "Never"
        PyImGui.text(f"Last export: {last_timestamp}")
        if state.last_export_path:
            PyImGui.text(f"Last file: {state.get_last_export_relative_path()}")
            PyImGui.text(
                f"Items exported: {state.last_inventory_count} inventory / {state.last_storage_count} storage"
            )

        if state.status_message:
            color = (0.9, 0.25, 0.25, 1.0) if state.status_is_error else (0.25, 0.85, 0.4, 1.0)
            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, color)
            PyImGui.text_wrapped(state.status_message)
            PyImGui.pop_style_color(1)

        PyImGui.separator()
        PyImGui.text_wrapped(f"Exports are written to: {os.path.relpath(export_base_dir, project_root)}")

    PyImGui.end()

    if save_window_timer.HasElapsed(1000):
        if (int(end_pos[0]), int(end_pos[1])) != (window_x, window_y):
            window_x, window_y = int(end_pos[0]), int(end_pos[1])
            ini_handler.write_key(MODULE_NAME, "x", str(window_x))
            ini_handler.write_key(MODULE_NAME, "y", str(window_y))
        if new_collapsed != window_collapsed:
            window_collapsed = new_collapsed
            ini_handler.write_key(MODULE_NAME, "collapsed", str(window_collapsed))
        save_window_timer.Reset()


def configure() -> None:
    pass


def main() -> None:
    global export_state
    try:
        if not Routines.Checks.Map.MapValid():
            return

        map_ready = Routines.Checks.Map.IsMapReady()
        party_loaded = Routines.Checks.Party.IsPartyLoaded()

        export_state.update(map_ready and party_loaded)

        if map_ready and party_loaded:
            draw_widget(export_state)
    except ImportError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"ImportError encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    except ValueError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"ValueError encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    except TypeError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"TypeError encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    except Exception as exc:  # noqa: BLE001
        Py4GW.Console.Log(MODULE_NAME, f"Unexpected error encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)


if __name__ == "__main__":
    main()
