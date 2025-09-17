import importlib.util
import os
import traceback
from collections import OrderedDict
from typing import Dict, Iterable, List, Sequence, Tuple

import Py4GW  # type: ignore
from HeroAI.cache_data import CacheData
from Py4GWCoreLib import GLOBAL_CACHE
from Py4GWCoreLib import Overlay
from Py4GWCoreLib import PyImGui
from Py4GWCoreLib import Routines
from Py4GWCoreLib import Timer
from Py4GWCoreLib import Utils
from Py4GWCoreLib.py4gwcorelib_src.IniHandler import IniHandler

MODULE_NAME = "Hero Formation Flagger"

# -----------------------------------------------------------------------------
# Paths & persistence helpers
# -----------------------------------------------------------------------------
script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))

BASE_DIR = os.path.join(project_root, "Widgets", "Config")
INI_WIDGET_WINDOW_PATH = os.path.join(BASE_DIR, "HeroFormationFlagger.ini")
os.makedirs(BASE_DIR, exist_ok=True)

ini_window = IniHandler(INI_WIDGET_WINDOW_PATH)
save_window_timer = Timer()
save_window_timer.Start()

first_run = True

COLLAPSED_KEY = "collapsed"
X_POS_KEY = "x"
Y_POS_KEY = "y"
DATASET_INDEX_KEY = "dataset_index"
FORMATION_INDEX_KEY = "formation_index"
SCALE_KEY = "scale"
PREVIEW_KEY = "preview"

window_x = ini_window.read_int(MODULE_NAME, X_POS_KEY, 120)
window_y = ini_window.read_int(MODULE_NAME, Y_POS_KEY, 120)
window_collapsed = ini_window.read_bool(MODULE_NAME, COLLAPSED_KEY, False)
selected_dataset_index = ini_window.read_int(MODULE_NAME, DATASET_INDEX_KEY, 0)
selected_formation_index = ini_window.read_int(MODULE_NAME, FORMATION_INDEX_KEY, 0)
distance_scale = ini_window.read_float(MODULE_NAME, SCALE_KEY, 1.0)
preview_enabled = ini_window.read_bool(MODULE_NAME, PREVIEW_KEY, False)

cached_data = CacheData()

# -----------------------------------------------------------------------------
# Formation data
# -----------------------------------------------------------------------------
FormationOffsets = Sequence[Tuple[float, float]]


def _normalize_offsets(raw: Dict[str, Iterable[Iterable[float]]]) -> Dict[str, List[Tuple[float, float]]]:
    formatted: Dict[str, List[Tuple[float, float]]] = {}
    for name, offsets in raw.items():
        formatted[name] = [
            (float(pair[0]), float(pair[1]))
            for pair in offsets
        ]
    return formatted


FANDOM_FORMATIONS: Dict[str, FormationOffsets] = _normalize_offsets(
    OrderedDict(
        [
            (
                "Arrowhead Pressure",
                [
                    (0, -360),
                    (-220, -160),
                    (220, -160),
                    (-420, 120),
                    (420, 120),
                    (-260, 420),
                    (260, 420),
                ],
            ),
            (
                "Split Wings",
                [
                    (-480, -220),
                    (-480, 80),
                    (-220, -440),
                    (220, -440),
                    (480, -220),
                    (480, 80),
                    (0, 380),
                ],
            ),
            (
                "Protect the Backline",
                [
                    (0, -260),
                    (-220, -120),
                    (220, -120),
                    (-320, 220),
                    (320, 220),
                    (-120, 460),
                    (120, 460),
                ],
            ),
            (
                "Caster Shell",
                [
                    (-320, -160),
                    (320, -160),
                    (-480, 140),
                    (480, 140),
                    (-240, 440),
                    (240, 440),
                    (0, 640),
                ],
            ),
            (
                "Wide Sweep",
                [
                    (-620, -220),
                    (-410, 0),
                    (-200, -220),
                    (0, 0),
                    (200, -220),
                    (410, 0),
                    (620, -220),
                ],
            ),
            (
                "Vanguard Column",
                [
                    (0, -420),
                    (0, -210),
                    (-160, 0),
                    (160, 0),
                    (-160, 260),
                    (160, 260),
                    (0, 520),
                ],
            ),
        ]
    )
)


LEGACY_FORMATION_PATH = os.path.join(
    project_root,
    "Legacy code and tests",
    "texture handling scripts",
    "flagging mockup.py",
)
LEGACY_FORMATION_SOURCE_NAME = "Legacy Mockup"
FANDOM_SOURCE_NAME = "Fandom Sandbox"


def _load_legacy_formations() -> Dict[str, FormationOffsets]:
    if not os.path.exists(LEGACY_FORMATION_PATH):
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Legacy formation file not found at {LEGACY_FORMATION_PATH}",
            Py4GW.Console.MessageType.Warning,
        )
        return {}

    try:
        spec = importlib.util.spec_from_file_location("hero_flagging_mockup", LEGACY_FORMATION_PATH)
        if spec is None or spec.loader is None:
            raise ImportError("Unable to load formation spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        formations = getattr(module, "formations", {})
        if not isinstance(formations, dict):
            raise ValueError("Legacy formations is not a dictionary")
        return _normalize_offsets(formations)
    except Exception as exc:  # pragma: no cover - defensive logging
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Failed to import legacy formations: {exc}",
            Py4GW.Console.MessageType.Warning,
        )
        Py4GW.Console.Log(
            MODULE_NAME,
            traceback.format_exc(),
            Py4GW.Console.MessageType.Debug,
        )
        return {}


LEGACY_FORMATIONS: Dict[str, FormationOffsets] = _load_legacy_formations()
FORMATION_SETS: "OrderedDict[str, Dict[str, FormationOffsets]]" = OrderedDict(
    [
        (FANDOM_SOURCE_NAME, FANDOM_FORMATIONS),
        (LEGACY_FORMATION_SOURCE_NAME, LEGACY_FORMATIONS),
    ]
)
FORMATION_SOURCE_NAMES: List[str] = list(FORMATION_SETS.keys())

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def _ensure_valid_indices() -> Tuple[str | None, List[str]]:
    global selected_dataset_index, selected_formation_index

    if not FORMATION_SOURCE_NAMES:
        selected_dataset_index = 0
        selected_formation_index = 0
        return None, []

    if selected_dataset_index >= len(FORMATION_SOURCE_NAMES):
        selected_dataset_index = 0

    dataset_name = FORMATION_SOURCE_NAMES[selected_dataset_index]
    formations = FORMATION_SETS.get(dataset_name, {})
    formation_names = sorted(formations.keys())

    if formation_names:
        if selected_formation_index >= len(formation_names):
            selected_formation_index = 0
    else:
        selected_formation_index = 0

    return dataset_name, formation_names


def _compute_rotated_positions(
    offsets: Sequence[Tuple[float, float]],
    scale: float,
    hero_limit: int,
) -> List[Tuple[float, float]]:
    if hero_limit <= 0:
        return []

    player_id = GLOBAL_CACHE.Player.GetAgentID()
    if player_id == 0:
        return []

    base_x, base_y = GLOBAL_CACHE.Agent.GetXY(player_id)
    rotation_cos = GLOBAL_CACHE.Agent.GetRotationCos(player_id)
    rotation_sin = GLOBAL_CACHE.Agent.GetRotationSin(player_id)

    # rotate offsets so that positive Y follows player's forward direction
    rotated_positions: List[Tuple[float, float]] = []
    max_heroes = min(hero_limit, len(offsets))

    for offset_x, offset_y in offsets[:max_heroes]:
        scaled_x = offset_x * scale
        scaled_y = offset_y * scale

        rotated_x = scaled_x * rotation_sin + scaled_y * rotation_cos
        rotated_y = -scaled_x * rotation_cos + scaled_y * rotation_sin

        rotated_positions.append((base_x + rotated_x, base_y + rotated_y))

    return rotated_positions


def _draw_preview(positions: Sequence[Tuple[float, float]]) -> None:
    if not positions:
        return

    overlay = Overlay()
    overlay.BeginDraw()

    flag_color = Utils.RGBToColor(0, 200, 255, 255)
    pole_thickness = 3

    for pos_x, pos_y in positions:
        pos_z = overlay.FindZ(pos_x, pos_y)
        overlay.DrawLine3D(pos_x, pos_y, pos_z, pos_x, pos_y, pos_z - 150, flag_color, pole_thickness)
        overlay.DrawTriangleFilled3D(
            pos_x + 25,
            pos_y,
            pos_z - 150,
            pos_x - 25,
            pos_y,
            pos_z - 150,
            pos_x,
            pos_y,
            pos_z - 100,
            flag_color,
        )

    overlay.EndDraw()


def _flag_heroes(positions: Sequence[Tuple[float, float]]) -> int:
    flagged = 0
    for index, (pos_x, pos_y) in enumerate(positions, start=1):
        agent_id = GLOBAL_CACHE.Party.Heroes.GetHeroAgentIDByPartyPosition(index)
        if agent_id:
            GLOBAL_CACHE.Party.Heroes.FlagHero(agent_id, pos_x, pos_y)
            flagged += 1
    return flagged


def reload_legacy_formations() -> None:
    global LEGACY_FORMATIONS
    LEGACY_FORMATIONS = _load_legacy_formations()
    FORMATION_SETS[LEGACY_FORMATION_SOURCE_NAME] = LEGACY_FORMATIONS


# -----------------------------------------------------------------------------
# UI drawing
# -----------------------------------------------------------------------------

def draw_widget(_: CacheData) -> None:
    global first_run, window_collapsed, window_x, window_y
    global selected_dataset_index, selected_formation_index
    global distance_scale, preview_enabled

    if first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        first_run = False

    window_flags = PyImGui.WindowFlags.AlwaysAutoResize
    is_window_open = PyImGui.begin(MODULE_NAME, window_flags)
    new_collapsed = PyImGui.is_window_collapsed()
    window_pos = PyImGui.get_window_pos()

    current_dataset_name, available_formations = _ensure_valid_indices()

    if is_window_open:
        PyImGui.text("Select a hero formation to flag relative to your character.")

        if PyImGui.button("Reload Legacy Formations"):
            reload_legacy_formations()
            current_dataset_name, available_formations = _ensure_valid_indices()

        PyImGui.separator()

        if FORMATION_SOURCE_NAMES:
            selected_dataset_index = PyImGui.combo(
                "Formation Set",
                selected_dataset_index,
                FORMATION_SOURCE_NAMES,
            )
            # Ensure indices remain valid after user selection changes
            current_dataset_name, available_formations = _ensure_valid_indices()
        else:
            PyImGui.text_colored("No formation sets available.", (1.0, 0.4, 0.1, 1.0))

        if current_dataset_name is None:
            PyImGui.end()
            return

        current_set = FORMATION_SETS.get(current_dataset_name, {})

        if not available_formations:
            PyImGui.text_colored("Selected set does not contain any formations.", (1.0, 0.4, 0.1, 1.0))
        else:
            selected_formation_index = PyImGui.combo(
                "Formation",
                selected_formation_index,
                available_formations,
            )

        distance_scale = PyImGui.slider_float("Scale", distance_scale, 0.5, 2.5, "%.2fx")
        preview_enabled = PyImGui.checkbox("Preview formation", preview_enabled)

        hero_count = GLOBAL_CACHE.Party.GetHeroCount()
        PyImGui.text(f"Detected heroes: {hero_count}")

        selected_formation_name = (
            available_formations[selected_formation_index]
            if available_formations and selected_formation_index < len(available_formations)
            else None
        )

        positions: List[Tuple[float, float]] = []
        offsets: Sequence[Tuple[float, float]] = []

        if selected_formation_name:
            offsets = current_set.get(selected_formation_name, [])
            positions = _compute_rotated_positions(offsets, distance_scale, hero_count)

            if hero_count > len(offsets):
                PyImGui.text_colored(
                    "Formation provides fewer offsets than heroes. Extra heroes will remain at their current flags.",
                    (1.0, 0.6, 0.0, 1.0),
                )

        if PyImGui.button("Flag Formation") and selected_formation_name:
            if not positions:
                Py4GW.Console.Log(
                    MODULE_NAME,
                    "No hero agents resolved or no offsets available for the selected formation.",
                    Py4GW.Console.MessageType.Warning,
                )
            else:
                flagged = _flag_heroes(positions)
                if flagged:
                    Py4GW.Console.Log(
                        MODULE_NAME,
                        f"Flagged {flagged} hero{'es' if flagged != 1 else ''} using '{selected_formation_name}'.",
                        Py4GW.Console.MessageType.Success,
                    )
                else:
                    Py4GW.Console.Log(
                        MODULE_NAME,
                        "Failed to resolve hero agent IDs for flagging.",
                        Py4GW.Console.MessageType.Warning,
                    )

        PyImGui.same_line()
        if PyImGui.button("Clear Flags"):
            GLOBAL_CACHE.Party.Heroes.UnflagAllHeroes()
            Py4GW.Console.Log(
                MODULE_NAME,
                "Cleared all hero flags.",
                Py4GW.Console.MessageType.Info,
            )

        if preview_enabled and positions:
            _draw_preview(positions)

        if selected_formation_name and offsets:
            PyImGui.separator()
            PyImGui.text(f"Formation: {selected_formation_name}")
            PyImGui.text(f"Offsets defined: {len(offsets)}")
            if PyImGui.collapsing_header("Offset Details"):
                if PyImGui.begin_table("Offsets", 3):
                    PyImGui.table_setup_column("Hero")
                    PyImGui.table_setup_column("X")
                    PyImGui.table_setup_column("Y")
                    PyImGui.table_headers_row()
                    for idx, (offset_x, offset_y) in enumerate(offsets, start=1):
                        PyImGui.table_next_row()
                        PyImGui.table_next_column()
                        PyImGui.text(str(idx))
                        PyImGui.table_next_column()
                        PyImGui.text(f"{offset_x:.0f}")
                        PyImGui.table_next_column()
                        PyImGui.text(f"{offset_y:.0f}")
                    PyImGui.end_table()

    PyImGui.end()

    if save_window_timer.HasElapsed(1000):
        if (int(window_pos[0]), int(window_pos[1])) != (window_x, window_y):
            window_x, window_y = int(window_pos[0]), int(window_pos[1])
            ini_window.write_key(MODULE_NAME, X_POS_KEY, window_x)
            ini_window.write_key(MODULE_NAME, Y_POS_KEY, window_y)
        if new_collapsed != window_collapsed:
            window_collapsed = new_collapsed
            ini_window.write_key(MODULE_NAME, COLLAPSED_KEY, window_collapsed)
        ini_window.write_key(MODULE_NAME, DATASET_INDEX_KEY, selected_dataset_index)
        ini_window.write_key(MODULE_NAME, FORMATION_INDEX_KEY, selected_formation_index)
        ini_window.write_key(MODULE_NAME, SCALE_KEY, distance_scale)
        ini_window.write_key(MODULE_NAME, PREVIEW_KEY, preview_enabled)
        save_window_timer.Reset()


def configure() -> None:
    """Optional configuration hook for the widget manager."""


def main() -> None:
    global cached_data
    try:
        if not Routines.Checks.Map.MapValid():
            return

        cached_data.Update()
        if Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded():
            draw_widget(cached_data)

    except ImportError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"ImportError encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    except ValueError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"ValueError encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    except TypeError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"TypeError encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    except Exception as exc:  # pragma: no cover - defensive logging
        Py4GW.Console.Log(MODULE_NAME, f"Unexpected error encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)


if __name__ == "__main__":
    main()
