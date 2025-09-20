import math
import os
import traceback
from typing import Optional, Tuple

import Py4GW  # type: ignore

from Py4GWCoreLib import FormatTime
from Py4GWCoreLib import GLOBAL_CACHE
from Py4GWCoreLib import IniHandler
from Py4GWCoreLib import PyImGui
from Py4GWCoreLib import Timer
from Py4GWCoreLib import Utils

MODULE_NAME = "Distance Tracker"
CONFIG_SECTION = MODULE_NAME
CONFIG_WINDOW_SECTION = f"{MODULE_NAME} Config"

__widget__ = {
    "category": "Gameplay",
    "subcategory": "Overlays",
    "icon": "ICON_PERSON_WALKING",
    "quickdock": True,
}

script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))
config_path = os.path.join(project_root, "Widgets/Config/DistanceTracker.ini")
os.makedirs(os.path.dirname(config_path), exist_ok=True)
ini_handler = IniHandler(config_path)

# Window persistence
save_window_timer = Timer()
save_window_timer.Start()
first_run = True

window_x = ini_handler.read_int(CONFIG_SECTION, "x", 100)
window_y = ini_handler.read_int(CONFIG_SECTION, "y", 100)
window_collapsed = ini_handler.read_bool(CONFIG_SECTION, "collapsed", False)

# Display / behaviour options
update_interval_ms = max(50, ini_handler.read_int(CONFIG_SECTION, "update_interval", 200))
decimal_places = max(0, min(4, ini_handler.read_int(CONFIG_SECTION, "decimal_places", 1)))
show_normalized = ini_handler.read_bool(CONFIG_SECTION, "show_normalized", True)
normalized_divisor = max(1.0, ini_handler.read_float(CONFIG_SECTION, "normalized_divisor", 96.0))
show_average_speed = ini_handler.read_bool(CONFIG_SECTION, "show_average_speed", True)

# Config window persistence
config_first_run = True
config_window_x = ini_handler.read_int(CONFIG_WINDOW_SECTION, "config_x", 400)
config_window_y = ini_handler.read_int(CONFIG_WINDOW_SECTION, "config_y", 200)
config_collapsed = ini_handler.read_bool(CONFIG_WINDOW_SECTION, "collapsed", False)
config_save_timer = Timer()
config_save_timer.Start()

# Runtime state
update_timer = Timer()
update_timer.Start()

total_distance = 0.0
last_position: Optional[Tuple[float, float]] = None
last_map_id: Optional[int] = None
last_instance_time: Optional[int] = None
latest_instance_time: int = 0
map_entry_uptime: int = 0


def _format_distance(value: float) -> str:
    if math.isfinite(value):
        return f"{value:.{decimal_places}f}"
    return "--"


def _reset_distance(
    current_map_id: Optional[int] = None, current_instance_time: Optional[int] = None
) -> None:
    global total_distance, last_position, last_map_id, last_instance_time, map_entry_uptime

    total_distance = 0.0
    last_position = None
    last_map_id = current_map_id
    last_instance_time = current_instance_time
    if current_instance_time is not None:
        map_entry_uptime = max(0, current_instance_time)
    else:
        map_entry_uptime = 0


def _update_distance() -> None:
    global last_position, total_distance, last_map_id, last_instance_time, latest_instance_time, map_entry_uptime, update_interval_ms

    if not update_timer.HasElapsed(update_interval_ms):
        return

    if not (GLOBAL_CACHE.Map.IsMapReady() and GLOBAL_CACHE.Party.IsPartyLoaded()):
        last_position = None
        update_timer.Reset()
        return

    try:
        current_map_id = GLOBAL_CACHE.Map.GetMapID()
        current_instance_time = GLOBAL_CACHE.Map.GetInstanceUptime()
        player_position_raw = GLOBAL_CACHE.Player.GetXY()
    except Exception:
        update_timer.Reset()
        return

    if not player_position_raw or len(player_position_raw) < 2:
        update_timer.Reset()
        return

    player_position = (float(player_position_raw[0]), float(player_position_raw[1]))

    # Detect map change or new instance
    if last_map_id is None or current_map_id != last_map_id:
        _reset_distance(current_map_id, current_instance_time)
        last_position = player_position
        latest_instance_time = current_instance_time
        update_timer.Reset()
        return

    if last_instance_time is not None and current_instance_time < last_instance_time:
        _reset_distance(current_map_id, current_instance_time)
        last_position = player_position
        latest_instance_time = current_instance_time
        update_timer.Reset()
        return

    if last_position is not None:
        step_distance = Utils.Distance(last_position, player_position)
        if math.isfinite(step_distance):
            total_distance += step_distance

    last_position = player_position
    last_map_id = current_map_id
    last_instance_time = current_instance_time
    latest_instance_time = current_instance_time
    if map_entry_uptime == 0 and current_instance_time is not None:
        map_entry_uptime = current_instance_time

    update_timer.Reset()


def draw_widget() -> None:
    global first_run, window_x, window_y, window_collapsed

    if first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        first_run = False

    is_window_open = PyImGui.begin(f"{MODULE_NAME}##{MODULE_NAME}", PyImGui.WindowFlags.AlwaysAutoResize)
    new_collapsed = PyImGui.is_window_collapsed()
    end_pos = PyImGui.get_window_pos()

    if is_window_open:
        if not (GLOBAL_CACHE.Map.IsMapReady() and GLOBAL_CACHE.Party.IsPartyLoaded()):
            PyImGui.text("Waiting for map...")
        else:
            map_name = GLOBAL_CACHE.Map.GetMapName(GLOBAL_CACHE.Map.GetMapID())
            elapsed_ms = max(0, latest_instance_time - map_entry_uptime) if latest_instance_time else 0

            PyImGui.text(f"Map: {map_name}")
            PyImGui.text(f"Time in instance: {FormatTime(elapsed_ms, 'mm:ss:ms') if elapsed_ms else '00:00:000'}")
            PyImGui.text(f"Distance walked: {_format_distance(total_distance)} gwinches")

            if show_normalized:
                normalized_value = total_distance / normalized_divisor if normalized_divisor else 0.0
                PyImGui.text(f"Normalized: {_format_distance(normalized_value)} units")
            if show_average_speed:
                if elapsed_ms > 0:
                    speed = total_distance / (elapsed_ms / 1000.0)
                    PyImGui.text(f"Average speed: {_format_distance(speed)} gwinches/s")
                else:
                    PyImGui.text("Average speed: --")

    PyImGui.end()

    if save_window_timer.HasElapsed(1000):
        if (int(end_pos[0]), int(end_pos[1])) != (window_x, window_y):
            window_x, window_y = int(end_pos[0]), int(end_pos[1])
            ini_handler.write_key(CONFIG_SECTION, "x", window_x)
            ini_handler.write_key(CONFIG_SECTION, "y", window_y)
        if new_collapsed != window_collapsed:
            window_collapsed = new_collapsed
            ini_handler.write_key(CONFIG_SECTION, "collapsed", window_collapsed)
        save_window_timer.Reset()


def configure() -> None:
    global config_first_run, config_window_x, config_window_y, config_collapsed
    global decimal_places, update_interval_ms, show_normalized, normalized_divisor, show_average_speed

    window_flags = PyImGui.WindowFlags.AlwaysAutoResize

    if config_first_run:
        PyImGui.set_next_window_pos(config_window_x, config_window_y)
        PyImGui.set_next_window_collapsed(config_collapsed, 0)
        config_first_run = False

    is_open = PyImGui.begin(f"{MODULE_NAME} Configuration##{MODULE_NAME}", window_flags)
    new_collapsed = PyImGui.is_window_collapsed()
    end_pos = PyImGui.get_window_pos()

    if is_open:
        PyImGui.text("Display options")
        PyImGui.separator()

        new_decimals = PyImGui.slider_int("Decimal places", decimal_places, 0, 4)
        if new_decimals != decimal_places:
            decimal_places = new_decimals
            ini_handler.write_key(CONFIG_SECTION, "decimal_places", decimal_places)

        new_interval = PyImGui.slider_int("Update interval (ms)", update_interval_ms, 50, 1000)
        if new_interval != update_interval_ms:
            update_interval_ms = new_interval
            ini_handler.write_key(CONFIG_SECTION, "update_interval", update_interval_ms)
            update_timer.Reset()

        new_show_normalized = PyImGui.checkbox("Show normalized distance", show_normalized)
        if new_show_normalized != show_normalized:
            show_normalized = new_show_normalized
            ini_handler.write_key(CONFIG_SECTION, "show_normalized", show_normalized)

        if show_normalized:
            new_divisor = PyImGui.slider_float("Normalization divisor", normalized_divisor, 1.0, 500.0)
            if new_divisor != normalized_divisor:
                normalized_divisor = new_divisor
                ini_handler.write_key(CONFIG_SECTION, "normalized_divisor", normalized_divisor)
            if PyImGui.is_item_hovered():
                PyImGui.begin_tooltip()
                PyImGui.text("Distance is divided by this value (default 96 for gwinches → map units).")
                PyImGui.end_tooltip()

        new_show_speed = PyImGui.checkbox("Show average speed", show_average_speed)
        if new_show_speed != show_average_speed:
            show_average_speed = new_show_speed
            ini_handler.write_key(CONFIG_SECTION, "show_average_speed", show_average_speed)

        if PyImGui.button("Reset distance##DistanceTrackerConfig"):
            _reset_distance(last_map_id, latest_instance_time)

    PyImGui.end()

    if config_save_timer.HasElapsed(500):
        if (int(end_pos[0]), int(end_pos[1])) != (config_window_x, config_window_y):
            config_window_x, config_window_y = int(end_pos[0]), int(end_pos[1])
            ini_handler.write_key(CONFIG_WINDOW_SECTION, "config_x", config_window_x)
            ini_handler.write_key(CONFIG_WINDOW_SECTION, "config_y", config_window_y)
        if new_collapsed != config_collapsed:
            config_collapsed = new_collapsed
            ini_handler.write_key(CONFIG_WINDOW_SECTION, "collapsed", config_collapsed)
        config_save_timer.Reset()


def main() -> None:
    try:
        _update_distance()
        draw_widget()
    except Exception as e:
        err_type = type(e).__name__
        Py4GW.Console.Log(MODULE_NAME, f"{err_type} encountered: {e}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)


if __name__ == "__main__":
    main()
