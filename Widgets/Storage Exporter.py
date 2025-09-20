import json
import os
import time
import traceback
from datetime import datetime
from typing import Dict, List

import Py4GW  # type: ignore
import PyInventory  # type: ignore

from Py4GWCoreLib import GLOBAL_CACHE, IniHandler, PyImGui, Timer, Inventory, Item, Player, Routines
from Py4GWCoreLib.enums_src import Item_enums as ItemEnums

MODULE_NAME = "Storage Exporter"

script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))
config_directory = os.path.join(project_root, "Widgets/Config")
default_export_directory = os.path.join(project_root, "Widgets/Data/storage_exports")
os.makedirs(config_directory, exist_ok=True)
os.makedirs(default_export_directory, exist_ok=True)

config_path = os.path.join(config_directory, "StorageExporter.ini")
ini_handler = IniHandler(config_path)

first_run = True
window_x = ini_handler.read_int(MODULE_NAME, "x", 120)
window_y = ini_handler.read_int(MODULE_NAME, "y", 120)
window_collapsed = ini_handler.read_bool(MODULE_NAME, "collapsed", False)

COLOR_MUTED = (200, 200, 200, 255)
COLOR_SUCCESS = (140, 220, 140, 255)
COLOR_WARNING = (255, 210, 120, 255)
COLOR_ERROR = (255, 120, 120, 255)


def _normalize_path(path_value: str) -> str:
    path_value = (path_value or "").strip()
    if not path_value:
        return default_export_directory
    expanded = os.path.expanduser(path_value)
    if not os.path.isabs(expanded):
        expanded = os.path.join(project_root, expanded)
    return os.path.normpath(expanded)


class StorageExporterConfig:
    def __init__(self) -> None:
        self.auto_export = ini_handler.read_bool(MODULE_NAME, "auto_export", True)
        self.export_interval_ms = max(5000, ini_handler.read_int(MODULE_NAME, "export_interval_ms", 60000))
        stored_dir = ini_handler.read_key(MODULE_NAME, "output_dir", default_export_directory)
        self.output_dir = _normalize_path(stored_dir)
        self.file_prefix = ini_handler.read_key(MODULE_NAME, "file_prefix", "storage_inventory") or "storage_inventory"
        self.auto_open_storage = ini_handler.read_bool(MODULE_NAME, "auto_open_storage", True)
        self.include_equipment_pack = ini_handler.read_bool(MODULE_NAME, "include_equipment_pack", False)
        self.include_material_storage = ini_handler.read_bool(MODULE_NAME, "include_material_storage", True)
        self.ensure_output_dir()

    def ensure_output_dir(self) -> None:
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError as exc:
            Py4GW.Console.Log(MODULE_NAME, f"Failed to create output directory: {exc}", Py4GW.Console.MessageType.Error)

    def set_output_dir(self, new_dir: str) -> None:
        self.output_dir = _normalize_path(new_dir)
        self.ensure_output_dir()
        ini_handler.write_key(MODULE_NAME, "output_dir", self.output_dir)

    def save(self) -> None:
        ini_handler.write_key(MODULE_NAME, "auto_export", str(self.auto_export))
        ini_handler.write_key(MODULE_NAME, "export_interval_ms", str(self.export_interval_ms))
        ini_handler.write_key(MODULE_NAME, "file_prefix", self.file_prefix)
        ini_handler.write_key(MODULE_NAME, "auto_open_storage", str(self.auto_open_storage))
        ini_handler.write_key(MODULE_NAME, "include_equipment_pack", str(self.include_equipment_pack))
        ini_handler.write_key(MODULE_NAME, "include_material_storage", str(self.include_material_storage))
        ini_handler.write_key(MODULE_NAME, "output_dir", self.output_dir)


def _default_status() -> str:
    return "Waiting for next export interval."


exporter_config = StorageExporterConfig()
export_timer = Timer()
if exporter_config.auto_export:
    export_timer.Start()
else:
    export_timer.Stop()

waiting_for_storage = False
pending_export_is_manual = False
status_message = _default_status()
status_color = COLOR_MUTED
last_export_timestamp = ""
last_export_path = ""
last_export_counts = {"inventory": 0, "storage": 0, "material_storage": 0}
last_export_duration_ms = 0


BAG_LABEL_OVERRIDES = {
    ItemEnums.Bags.Bag1: "Bag 1",
    ItemEnums.Bags.Bag2: "Bag 2",
    ItemEnums.Bags.EquipmentPack: "Equipment Pack",
    ItemEnums.Bags.MaterialStorage: "Material Storage",
    ItemEnums.Bags.Storage1: "Storage 1",
    ItemEnums.Bags.Storage2: "Storage 2",
    ItemEnums.Bags.Storage3: "Storage 3",
    ItemEnums.Bags.Storage4: "Storage 4",
    ItemEnums.Bags.Storage5: "Storage 5",
    ItemEnums.Bags.Storage6: "Storage 6",
    ItemEnums.Bags.Storage7: "Storage 7",
    ItemEnums.Bags.Storage8: "Storage 8",
    ItemEnums.Bags.Storage9: "Storage 9",
    ItemEnums.Bags.Storage10: "Storage 10",
    ItemEnums.Bags.Storage11: "Storage 11",
    ItemEnums.Bags.Storage12: "Storage 12",
    ItemEnums.Bags.Storage13: "Storage 13",
    ItemEnums.Bags.Storage14: "Storage 14",
}


def _format_bag_name(bag_enum: ItemEnums.Bags) -> str:
    return BAG_LABEL_OVERRIDES.get(bag_enum, bag_enum.name.replace("_", " "))


def _set_status(message: str, color: tuple) -> None:
    global status_message, status_color
    status_message = message
    status_color = color


def _collect_items(bags: List[ItemEnums.Bags]) -> List[Dict]:
    collected: List[Dict] = []
    for bag_enum in bags:
        try:
            bag = PyInventory.Bag(bag_enum.value, bag_enum.name)
            items = bag.GetItems()
        except Exception as exc:  # pragma: no cover - defensive logging
            Py4GW.Console.Log(
                MODULE_NAME,
                f"Failed to read bag {bag_enum.name}: {exc}",
                Py4GW.Console.MessageType.Error,
            )
            continue

        for item in items:
            try:
                collected.append(_create_item_snapshot(bag_enum, item))
            except Exception as exc:  # pragma: no cover - defensive logging
                Py4GW.Console.Log(
                    MODULE_NAME,
                    f"Failed to snapshot item {getattr(item, 'item_id', 'unknown')}: {exc}",
                    Py4GW.Console.MessageType.Error,
                )
                Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    collected.sort(key=lambda entry: (entry["bag_id"], entry["slot"]))
    return collected


def _create_item_snapshot(bag_enum: ItemEnums.Bags, item) -> Dict:
    py_item = Item.item_instance(item.item_id)
    rarity_name = getattr(py_item.rarity, "name", str(py_item.rarity))
    rarity_value = int(py_item.rarity) if hasattr(py_item.rarity, "__int__") else int(getattr(py_item.rarity, "value", 0))

    entry: Dict = {
        "bag_id": int(bag_enum.value),
        "bag_name": _format_bag_name(bag_enum),
        "slot": int(getattr(item, "slot", 0)),
        "item_id": int(py_item.item_id),
        "model_id": int(py_item.model_id),
        "quantity": int(py_item.quantity),
        "value": int(py_item.value),
        "rarity": {"id": rarity_value, "name": rarity_name},
        "item_type": {
            "id": int(py_item.item_type.ToInt()) if hasattr(py_item.item_type, "ToInt") else 0,
            "name": py_item.item_type.GetName() if hasattr(py_item.item_type, "GetName") else "",
        },
        "is_stackable": bool(getattr(py_item, "is_stackable", False)),
        "is_customized": bool(getattr(py_item, "is_customized", False)),
        "equipped": bool(getattr(py_item, "equipped", False)),
    }

    item_name = (getattr(py_item, "name", "") or "").strip()
    if not item_name:
        try:
            Item.RequestName(py_item.item_id)
            if Item.IsNameReady(py_item.item_id):
                item_name = Item.GetName(py_item.item_id)
        except Exception:
            item_name = ""
    if item_name:
        entry["name"] = item_name

    modifiers: List[str] = []
    for modifier in getattr(py_item, "modifiers", []) or []:
        try:
            if modifier and modifier.IsValid():
                modifiers.append(modifier.ToString())
        except Exception:
            continue
    if modifiers:
        entry["modifiers"] = modifiers

    return entry


def _build_export_payload(trigger: str) -> Dict:
    timestamp_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    inventory_bags = [
        ItemEnums.Bags.Backpack,
        ItemEnums.Bags.BeltPouch,
        ItemEnums.Bags.Bag1,
        ItemEnums.Bags.Bag2,
    ]
    if exporter_config.include_equipment_pack:
        inventory_bags.append(ItemEnums.Bags.EquipmentPack)

    storage_bags = [
        ItemEnums.Bags.Storage1,
        ItemEnums.Bags.Storage2,
        ItemEnums.Bags.Storage3,
        ItemEnums.Bags.Storage4,
        ItemEnums.Bags.Storage5,
        ItemEnums.Bags.Storage6,
        ItemEnums.Bags.Storage7,
        ItemEnums.Bags.Storage8,
        ItemEnums.Bags.Storage9,
        ItemEnums.Bags.Storage10,
        ItemEnums.Bags.Storage11,
        ItemEnums.Bags.Storage12,
        ItemEnums.Bags.Storage13,
        ItemEnums.Bags.Storage14,
    ]

    material_items: List[Dict] = []
    if exporter_config.include_material_storage:
        material_items = _collect_items([ItemEnums.Bags.MaterialStorage])

    inventory_items = _collect_items(inventory_bags)
    storage_items = _collect_items(storage_bags)

    payload: Dict = {
        "timestamp": timestamp_iso,
        "character": "",
        "map": {},
        "inventory_gold": 0,
        "storage_gold": 0,
        "inventory": inventory_items,
        "storage": storage_items,
        "material_storage": material_items,
        "metadata": {
            "trigger": trigger,
            "include_equipment_pack": exporter_config.include_equipment_pack,
            "include_material_storage": exporter_config.include_material_storage,
            "export_interval_ms": exporter_config.export_interval_ms,
        },
        "storage_snapshot": Inventory.GetZeroFilledStorageArray(),
    }

    try:
        payload["character"] = GLOBAL_CACHE.Player.GetName()
    except Exception:
        try:
            payload["character"] = Player.GetName()
        except Exception:
            payload["character"] = ""

    try:
        payload["inventory_gold"] = GLOBAL_CACHE.Inventory.GetGoldOnCharacter()
        payload["storage_gold"] = GLOBAL_CACHE.Inventory.GetGoldInStorage()
    except Exception:
        pass

    try:
        payload["map"] = {
            "id": GLOBAL_CACHE.Map.GetMapID(),
            "name": GLOBAL_CACHE.Map.GetMapName(),
        }
    except Exception:
        payload["map"] = {}

    return payload


def _perform_export(is_manual: bool) -> bool:
    global last_export_timestamp, last_export_path, last_export_counts, last_export_duration_ms
    start_time = time.perf_counter()
    trigger = "manual" if is_manual else "auto"

    try:
        payload = _build_export_payload(trigger)
    except Exception as exc:
        _set_status(f"Export failed: {exc}", COLOR_ERROR)
        Py4GW.Console.Log(MODULE_NAME, f"Export failed: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
        return False

    timestamp_suffix = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    prefix = exporter_config.file_prefix or "storage_inventory"
    latest_path = os.path.join(exporter_config.output_dir, f"{prefix}_latest.json")
    timestamped_path = os.path.join(exporter_config.output_dir, f"{prefix}_{timestamp_suffix}.json")

    try:
        with open(timestamped_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        with open(latest_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        _set_status(f"Failed to write export: {exc}", COLOR_ERROR)
        Py4GW.Console.Log(MODULE_NAME, f"Failed to write export: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
        return False

    last_export_timestamp = payload["timestamp"]
    last_export_path = timestamped_path
    last_export_counts = {
        "inventory": len(payload["inventory"]),
        "storage": len(payload["storage"]),
        "material_storage": len(payload["material_storage"]),
    }
    last_export_duration_ms = int((time.perf_counter() - start_time) * 1000)

    _set_status(
        f"Exported {last_export_counts['inventory']} inventory and {last_export_counts['storage']} storage items.",
        COLOR_SUCCESS,
    )

    Py4GW.Console.Log(
        MODULE_NAME,
        f"Saved inventory/storage snapshot to {timestamped_path}",
        Py4GW.Console.MessageType.Info,
    )
    return True


def _try_queue_storage_open(is_manual: bool) -> None:
    GLOBAL_CACHE.Inventory.OpenXunlaiWindow()
    trigger = "manual" if is_manual else "auto"
    _set_status("Waiting for Xunlai storage window...", COLOR_WARNING)
    Py4GW.Console.Log(
        MODULE_NAME,
        f"Storage closed; queued open request before {trigger} export.",
        Py4GW.Console.MessageType.Warning,
    )


def _attempt_export(is_manual: bool) -> bool:
    global waiting_for_storage, pending_export_is_manual

    if not GLOBAL_CACHE.Inventory.IsStorageOpen():
        if exporter_config.auto_open_storage:
            waiting_for_storage = True
            pending_export_is_manual = is_manual
            _try_queue_storage_open(is_manual)
        else:
            _set_status("Storage window is closed. Enable auto-open to export.", COLOR_WARNING)
            Py4GW.Console.Log(
                MODULE_NAME,
                "Storage window closed; export skipped.",
                Py4GW.Console.MessageType.Warning,
            )
        return False

    success = _perform_export(is_manual)
    if success:
        waiting_for_storage = False
        pending_export_is_manual = False
    return success


def draw_widget() -> None:
    global first_run, window_x, window_y, window_collapsed

    if first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        first_run = False

    if PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize):
        PyImGui.text_wrapped("Automatically exports inventory and storage snapshots to JSON on a fixed schedule.")
        PyImGui.separator()

        auto_export = PyImGui.checkbox("Enable automatic export", exporter_config.auto_export)
        if auto_export != exporter_config.auto_export:
            exporter_config.auto_export = auto_export
            exporter_config.save()
            if exporter_config.auto_export:
                export_timer.Reset()
                _set_status(_default_status(), COLOR_MUTED)
            else:
                export_timer.Stop()
                _set_status("Automatic exports disabled.", COLOR_MUTED)

        interval_seconds = max(5, exporter_config.export_interval_ms // 1000)
        new_interval_seconds = PyImGui.slider_int("Interval (seconds)", interval_seconds, 5, 3600)
        if new_interval_seconds != interval_seconds:
            exporter_config.export_interval_ms = max(5000, new_interval_seconds * 1000)
            exporter_config.save()
            if exporter_config.auto_export:
                export_timer.Reset()

        auto_open = PyImGui.checkbox("Open Xunlai storage automatically", exporter_config.auto_open_storage)
        if auto_open != exporter_config.auto_open_storage:
            exporter_config.auto_open_storage = auto_open
            exporter_config.save()

        include_equipment = PyImGui.checkbox("Include equipment pack", exporter_config.include_equipment_pack)
        if include_equipment != exporter_config.include_equipment_pack:
            exporter_config.include_equipment_pack = include_equipment
            exporter_config.save()

        include_material = PyImGui.checkbox("Include material storage", exporter_config.include_material_storage)
        if include_material != exporter_config.include_material_storage:
            exporter_config.include_material_storage = include_material
            exporter_config.save()

        PyImGui.separator()

        PyImGui.text("Export directory:")
        new_directory = PyImGui.input_text("##StorageExporterPath", exporter_config.output_dir)
        if new_directory != exporter_config.output_dir:
            exporter_config.set_output_dir(new_directory)

        PyImGui.text("File prefix:")
        new_prefix = PyImGui.input_text("##StorageExporterPrefix", exporter_config.file_prefix)
        if new_prefix and new_prefix != exporter_config.file_prefix:
            exporter_config.file_prefix = new_prefix.strip()
            exporter_config.save()

        if PyImGui.button("Export now"):
            if _attempt_export(True) and exporter_config.auto_export:
                export_timer.Reset()

        if status_message:
            PyImGui.text_colored(status_message, status_color)

        if last_export_timestamp:
            PyImGui.text(f"Last export: {last_export_timestamp}")
            PyImGui.text(f"Duration: {last_export_duration_ms} ms")
            PyImGui.text(f"Inventory items: {last_export_counts['inventory']}")
            PyImGui.text(f"Storage items: {last_export_counts['storage']}")
            if exporter_config.include_material_storage:
                PyImGui.text(f"Material items: {last_export_counts['material_storage']}")
            PyImGui.text_wrapped(f"Last file: {last_export_path}")

        if exporter_config.auto_export and export_timer.IsRunning():
            remaining_ms = max(0, exporter_config.export_interval_ms - export_timer.GetElapsedTime())
            PyImGui.text(f"Next auto export in: {remaining_ms / 1000:.1f}s")

    new_collapsed = PyImGui.is_window_collapsed()
    end_pos = PyImGui.get_window_pos()
    PyImGui.end()

    if (int(end_pos[0]), int(end_pos[1])) != (window_x, window_y):
        window_x, window_y = int(end_pos[0]), int(end_pos[1])
        ini_handler.write_key(MODULE_NAME, "x", str(window_x))
        ini_handler.write_key(MODULE_NAME, "y", str(window_y))
    if new_collapsed != window_collapsed:
        window_collapsed = new_collapsed
        ini_handler.write_key(MODULE_NAME, "collapsed", str(window_collapsed))


def configure() -> None:
    pass


def _update_auto_export() -> None:
    global waiting_for_storage, pending_export_is_manual
    if waiting_for_storage:
        if GLOBAL_CACHE.Inventory.IsStorageOpen():
            success = _perform_export(pending_export_is_manual)
            waiting_for_storage = False
            pending_export_is_manual = False
            if success and exporter_config.auto_export:
                export_timer.Reset()
        return

    if not exporter_config.auto_export:
        return

    if export_timer.IsStopped():
        export_timer.Start()

    if export_timer.HasElapsed(exporter_config.export_interval_ms):
        if _attempt_export(False):
            export_timer.Reset()


def main() -> None:
    try:
        if not Routines.Checks.Map.MapValid():
            return

        if Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded():
            _update_auto_export()
            draw_widget()
    except Exception as exc:
        Py4GW.Console.Log(MODULE_NAME, f"Unexpected error: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)


if __name__ == "__main__":
    main()
