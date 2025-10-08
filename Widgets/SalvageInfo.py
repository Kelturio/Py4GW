from __future__ import annotations

import ctypes
import os
from datetime import date, datetime, time, timedelta
from enum import IntEnum
from typing import List, Optional

from Py4GWCoreLib import IniHandler
from Py4GWCoreLib import Item
from Py4GWCoreLib import Inventory
from Py4GWCoreLib import PyImGui

from Py4GW_widget_manager import WidgetHandler
from Widgets import Calendar

__widget__ = {
    "category": "Gameplay",
    "subcategory": "Overlays",
    "icon": "ICON_INFO_CIRCLE",
    "quickdock": False,
    "enabled": True,
}

CONFIG_SECTION = "SalvageInfo"
_WIDGET_NAME = "SalvageInfo"
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_SCRIPT_DIR, "Config", "SalvageInfo.ini")
os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
_CONFIG = IniHandler(_CONFIG_PATH)

SHOW_COMMON = _CONFIG.read_bool(CONFIG_SECTION, "show_common", True)
SHOW_RARE = _CONFIG.read_bool(CONFIG_SECTION, "show_rare", True)
SHOW_NICHOLAS = _CONFIG.read_bool(CONFIG_SECTION, "show_nicholas", True)
SHOW_AMOUNTS = _CONFIG.read_bool(CONFIG_SECTION, "show_amounts", True)

_TOOLTIP_OFFSET_X = 18
_TOOLTIP_OFFSET_Y = 16

_BASE_NICHOLAS_CYCLE_LENGTH = len(Calendar.NICHOLAS_CYCLE)


class MaterialSlot(IntEnum):
    Bone = 0
    IronIngot = 1
    TannedHideSquare = 2
    Scale = 3
    ChitinFragment = 4
    BoltofCloth = 5
    WoodPlank = 6
    GraniteSlab = 8
    PileofGlitteringDust = 9
    PlantFiber = 10
    Feather = 11
    FurSquare = 12
    BoltofLinen = 13
    BoltofDamask = 14
    BoltofSilk = 15
    GlobofEctoplasm = 16
    SteelIngot = 17
    DeldrimorSteelIngot = 18
    MonstrousClaw = 19
    MonstrousEye = 20
    MonstrousFang = 21
    Ruby = 22
    Sapphire = 23
    Diamond = 24
    OnyxGemstone = 25
    LumpofCharcoal = 26
    ObsidianShard = 27
    TemperedGlassVial = 29
    LeatherSquare = 30
    ElonianLeatherSquare = 31
    VialofInk = 32
    RollofParchment = 33
    RollofVellum = 34
    SpiritwoodPlank = 35
    AmberChunk = 36
    JadeiteShard = 37
    BronzeZCoin = 38
    SilverZCoin = 39
    GoldZCoin = 40
    Count = 41


MATERIAL_NAMES: dict[MaterialSlot, str] = {
    MaterialSlot.Bone: "Bone",
    MaterialSlot.IronIngot: "Iron Ingot",
    MaterialSlot.TannedHideSquare: "Tanned Hide Square",
    MaterialSlot.Scale: "Scale",
    MaterialSlot.ChitinFragment: "Chitin Fragment",
    MaterialSlot.BoltofCloth: "Bolt of Cloth",
    MaterialSlot.WoodPlank: "Wood Plank",
    MaterialSlot.GraniteSlab: "Granite Slab",
    MaterialSlot.PileofGlitteringDust: "Pile of Glittering Dust",
    MaterialSlot.PlantFiber: "Plant Fiber",
    MaterialSlot.Feather: "Feather",
    MaterialSlot.FurSquare: "Fur Square",
    MaterialSlot.BoltofLinen: "Bolt of Linen",
    MaterialSlot.BoltofDamask: "Bolt of Damask",
    MaterialSlot.BoltofSilk: "Bolt of Silk",
    MaterialSlot.GlobofEctoplasm: "Glob of Ectoplasm",
    MaterialSlot.SteelIngot: "Steel Ingot",
    MaterialSlot.DeldrimorSteelIngot: "Deldrimor Steel Ingot",
    MaterialSlot.MonstrousClaw: "Monstrous Claw",
    MaterialSlot.MonstrousEye: "Monstrous Eye",
    MaterialSlot.MonstrousFang: "Monstrous Fang",
    MaterialSlot.Ruby: "Ruby",
    MaterialSlot.Sapphire: "Sapphire",
    MaterialSlot.Diamond: "Diamond",
    MaterialSlot.OnyxGemstone: "Onyx Gemstone",
    MaterialSlot.LumpofCharcoal: "Lump of Charcoal",
    MaterialSlot.ObsidianShard: "Obsidian Shard",
    MaterialSlot.TemperedGlassVial: "Tempered Glass Vial",
    MaterialSlot.LeatherSquare: "Leather Square",
    MaterialSlot.ElonianLeatherSquare: "Elonian Leather Square",
    MaterialSlot.VialofInk: "Vial of Ink",
    MaterialSlot.RollofParchment: "Roll of Parchment",
    MaterialSlot.RollofVellum: "Roll of Vellum",
    MaterialSlot.SpiritwoodPlank: "Spiritwood Plank",
    MaterialSlot.AmberChunk: "Amber Chunk",
    MaterialSlot.JadeiteShard: "Jadeite Shard",
    MaterialSlot.BronzeZCoin: "Bronze Zaishen Coin",
    MaterialSlot.SilverZCoin: "Silver Zaishen Coin",
    MaterialSlot.GoldZCoin: "Gold Zaishen Coin",
}


class _MaterialCost(ctypes.Structure):
    _fields_ = [
        ("material", ctypes.c_uint32),
        ("amount", ctypes.c_uint32),
        ("_pad0", ctypes.c_uint32),
        ("_pad1", ctypes.c_uint32),
    ]


class _ItemFormula(ctypes.Structure):
    _fields_ = [
        ("_pad0", ctypes.c_uint32),
        ("gold_cost", ctypes.c_uint32),
        ("skill_point_cost", ctypes.c_uint32),
        ("material_cost_count", ctypes.c_uint32),
        ("material_cost_buffer", ctypes.POINTER(_MaterialCost)),
    ]


class SalvageData:
    __slots__ = ("common", "rare")

    def __init__(self, common: List[str], rare: List[str]) -> None:
        self.common = common
        self.rare = rare

    @property
    def has_entries(self) -> bool:
        return bool(self.common or self.rare)


class DisplayInfo:
    __slots__ = ("lines",)

    def __init__(self, lines: List[str]) -> None:
        self.lines = lines


_salvage_cache: dict[int, SalvageData] = {}
_current_display: Optional[DisplayInfo] = None
_last_hovered_item: int = 0


def _format_material_entry(slot: MaterialSlot, amount: int) -> str:
    name = MATERIAL_NAMES.get(slot, slot.name.replace("_", " ").title())
    if not SHOW_AMOUNTS or amount <= 1:
        return name
    return f"{name} ×{amount}"


def _read_salvage_materials(item_id: int) -> Optional[SalvageData]:
    try:
        formula_ptr = Item.Customization.GetItemFormula(item_id)
    except Exception:
        return None
    if not formula_ptr:
        return None
    try:
        formula = ctypes.cast(ctypes.c_void_p(int(formula_ptr)), ctypes.POINTER(_ItemFormula)).contents
    except Exception:
        return None
    count = max(0, min(int(formula.material_cost_count), 8))
    if count == 0:
        return SalvageData([], [])
    buffer_ptr = formula.material_cost_buffer
    if not buffer_ptr:
        return SalvageData([], [])
    common: list[str] = []
    rare: list[str] = []
    for index in range(count):
        try:
            cost = buffer_ptr[index]
        except Exception:
            break
        try:
            slot = MaterialSlot(cost.material)
        except ValueError:
            continue
        entry = _format_material_entry(slot, int(cost.amount))
        if slot <= MaterialSlot.Feather:
            common.append(entry)
        else:
            rare.append(entry)
    return SalvageData(common, rare)


def _get_salvage_data(model_id: int, item_id: int) -> Optional[SalvageData]:
    if not Item.Usage.IsSalvageable(item_id):
        return None
    cached = _salvage_cache.get(model_id)
    if cached is not None:
        return cached if cached.has_entries else None
    data = _read_salvage_materials(item_id)
    if data is None:
        _salvage_cache[model_id] = SalvageData([], [])
        return None
    _salvage_cache[model_id] = data
    return data if data.has_entries else None


def _plural(amount: int, unit: str) -> str:
    if amount == 1:
        return f"{amount} {unit}"
    return f"{amount} {unit}s"


def _format_relative_time(target: datetime) -> str:
    delta_seconds = int((target - datetime.now()).total_seconds())
    if delta_seconds <= 0:
        return "the past"
    if delta_seconds < 60:
        return "less than a minute"
    amount = delta_seconds // 60
    if amount < 60:
        return _plural(amount, "minute")
    amount //= 60
    if amount < 24:
        return _plural(amount, "hour")
    amount //= 24
    if amount < 14:
        return _plural(amount, "day")
    amount //= 7
    if amount < 8:
        return _plural(amount, "week")
    amount //= 4
    if amount < 24:
        return _plural(amount, "month")
    amount //= 12
    return _plural(amount, "year")


def _lookup_nicholas(model_id: int) -> Optional[str]:
    if not SHOW_NICHOLAS:
        return None
    today = date.today()
    Calendar.expand_cycle_if_needed(today)
    Calendar.expand_cycle_if_needed(today + timedelta(weeks=_BASE_NICHOLAS_CYCLE_LENGTH))
    matching_entries = [entry for entry in Calendar.NICHOLAS_CYCLE if entry.get("model_id") == model_id]
    if not matching_entries:
        return None
    matching_entries.sort(key=lambda entry: entry["week"])
    for entry in matching_entries:
        start_week = entry["week"]
        if start_week <= today < start_week + timedelta(days=7):
            quantity = entry.get("quantity", 0)
            return f"Nicholas the Traveller collects {quantity} of these right now!"
    future_entry = next((entry for entry in matching_entries if entry["week"] >= today), None)
    if not future_entry:
        return None
    quantity = future_entry.get("quantity", 0)
    target_dt = datetime.combine(future_entry["week"], time())
    relative = _format_relative_time(target_dt)
    return f"Nicholas the Traveller collects {quantity} of these in {relative}."


def _get_item_name(item_id: int) -> str:
    name = Item.GetName(item_id)
    if name:
        return name
    Item.RequestName(item_id)
    name = Item.GetName(item_id)
    return name or f"Item #{item_id}"


def _build_display_info(item_id: int) -> Optional[DisplayInfo]:
    try:
        model_id = Item.GetModelID(item_id)
    except Exception:
        return None
    lines: list[str] = []
    info_lines: list[str] = []
    salvage_data = _get_salvage_data(model_id, item_id)
    if salvage_data:
        if SHOW_COMMON and salvage_data.common:
            info_lines.append(f"Common materials: {', '.join(salvage_data.common)}")
        if SHOW_RARE and salvage_data.rare:
            info_lines.append(f"Rare materials: {', '.join(salvage_data.rare)}")
    nicholas_line = _lookup_nicholas(model_id)
    if nicholas_line:
        if info_lines:
            info_lines.append("")
        info_lines.append(nicholas_line)
    if not info_lines:
        return None
    try:
        item_name = _get_item_name(item_id)
    except Exception:
        item_name = ""
    if item_name:
        lines.append(item_name)
    lines.extend(info_lines)
    return DisplayInfo(lines=[line for line in lines if line is not None])


def _draw_tooltip(info: DisplayInfo) -> None:
    io = PyImGui.get_io()
    pos_x = io.mouse_pos_x + _TOOLTIP_OFFSET_X
    pos_y = io.mouse_pos_y + _TOOLTIP_OFFSET_Y
    PyImGui.set_next_window_pos(pos_x, pos_y)
    flags = (
        PyImGui.WindowFlags.NoTitleBar
        | PyImGui.WindowFlags.NoResize
        | PyImGui.WindowFlags.NoScrollbar
        | PyImGui.WindowFlags.NoSavedSettings
        | PyImGui.WindowFlags.AlwaysAutoResize
        | PyImGui.WindowFlags.NoMove
        | PyImGui.WindowFlags.NoInputs
    )
    if PyImGui.begin("Salvage Info##Tooltip", flags):
        for line in info.lines:
            if not line:
                PyImGui.separator()
            else:
                PyImGui.text(line)
    PyImGui.end()


def configure() -> None:
    handler = WidgetHandler()
    widget_info = handler.get_widget_info(_WIDGET_NAME) if handler else None
    if not widget_info or not widget_info.get("configuring"):
        return
    if PyImGui.begin("Salvage Info Settings", PyImGui.WindowFlags.AlwaysAutoResize):
        global SHOW_COMMON, SHOW_RARE, SHOW_NICHOLAS, SHOW_AMOUNTS
        new_common = PyImGui.checkbox("Show common materials", SHOW_COMMON)
        if new_common != SHOW_COMMON:
            SHOW_COMMON = new_common
            _CONFIG.write_key(CONFIG_SECTION, "show_common", SHOW_COMMON)
        new_rare = PyImGui.checkbox("Show rare materials", SHOW_RARE)
        if new_rare != SHOW_RARE:
            SHOW_RARE = new_rare
            _CONFIG.write_key(CONFIG_SECTION, "show_rare", SHOW_RARE)
        new_amounts = PyImGui.checkbox("Show material counts", SHOW_AMOUNTS)
        if new_amounts != SHOW_AMOUNTS:
            SHOW_AMOUNTS = new_amounts
            _CONFIG.write_key(CONFIG_SECTION, "show_amounts", SHOW_AMOUNTS)
        new_nicholas = PyImGui.checkbox("Show Nicholas the Traveller", SHOW_NICHOLAS)
        if new_nicholas != SHOW_NICHOLAS:
            SHOW_NICHOLAS = new_nicholas
            _CONFIG.write_key(CONFIG_SECTION, "show_nicholas", SHOW_NICHOLAS)
        PyImGui.separator()
        if PyImGui.button("Close"):
            handler.set_widget_configuring(_WIDGET_NAME, False)
    PyImGui.end()


def main() -> None:
    global _current_display, _last_hovered_item
    try:
        hovered_item = Inventory.GetHoveredItemID()
    except Exception:
        hovered_item = 0
    if hovered_item != _last_hovered_item:
        _last_hovered_item = hovered_item
        _current_display = None
    if hovered_item:
        info = _build_display_info(hovered_item)
        _current_display = info
    if _current_display:
        _draw_tooltip(_current_display)
