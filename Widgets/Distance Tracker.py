import os
import traceback
from typing import Optional, Tuple

import Py4GW  # type: ignore
from Py4GWCoreLib import GLOBAL_CACHE, IniHandler, PyImGui, Timer, Utils

MODULE_NAME = "Distance Tracker"

script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))

BASE_DIR = os.path.join(project_root, "Widgets/Config")
INI_WIDGET_WINDOW_PATH = os.path.join(BASE_DIR, "DistanceTracker.ini")
os.makedirs(BASE_DIR, exist_ok=True)

ini_window = IniHandler(INI_WIDGET_WINDOW_PATH)
save_window_timer = Timer()
save_window_timer.Start()

COLLAPSED_KEY = "collapsed"
X_POS_KEY = "x"
Y_POS_KEY = "y"

window_x = ini_window.read_int(MODULE_NAME, X_POS_KEY, 100)
window_y = ini_window.read_int(MODULE_NAME, Y_POS_KEY, 100)
window_collapsed = ini_window.read_bool(MODULE_NAME, COLLAPSED_KEY, False)

first_run = True

# Distance tracking state
_distance_walked: float = 0.0
_last_position: Optional[Tuple[float, float]] = None
_current_position: Optional[Tuple[float, float]] = None
_last_map_id: Optional[int] = None
_current_map_name: str = ""
_status_message: str = "Waiting for map data..."
_last_reset_reason: str = "Widget loaded"

# Minimum distance delta to accumulate (filters out positional jitter)
MIN_DISTANCE_DELTA = 1.0


def _log_exception(exc: Exception) -> None:
    Py4GW.Console.Log(
        MODULE_NAME,
        f"{exc.__class__.__name__} encountered: {str(exc)}",
        Py4GW.Console.MessageType.Error,
    )
    Py4GW.Console.Log(
        MODULE_NAME,
        f"Stack trace: {traceback.format_exc()}",
        Py4GW.Console.MessageType.Error,
    )


def _reset_distance(reason: str, keep_position: bool = False) -> None:
    global _distance_walked, _last_position, _last_reset_reason

    _distance_walked = 0.0
    _last_reset_reason = reason
    if keep_position and _current_position is not None:
        _last_position = _current_position
    else:
        _last_position = None


def _handle_loading_state(map_ready: bool, party_loaded: bool) -> bool:
    global _status_message, _current_position, _last_position, _current_map_name

    if not map_ready:
        _status_message = "Waiting for map to become ready..."
        _current_position = None
        _last_position = None
        _current_map_name = ""
        return False

    if not party_loaded:
        try:
            map_id = GLOBAL_CACHE.Map.GetMapID()
            _current_map_name = GLOBAL_CACHE.Map.GetMapName(map_id)
        except Exception:
            _current_map_name = ""
        _status_message = "Waiting for party data..."
        _current_position = None
        _last_position = None
        return False

    _status_message = ""
    return True


def _update_distance_state() -> None:
    global _distance_walked, _last_position, _current_position, _last_map_id
    global _current_map_name

    map_id = GLOBAL_CACHE.Map.GetMapID()
    if _last_map_id is None or map_id != _last_map_id:
        _last_map_id = map_id
        _reset_distance("Map change")

    _current_map_name = GLOBAL_CACHE.Map.GetMapName(map_id)

    _current_position = GLOBAL_CACHE.Player.GetXY()
    if _last_position is None:
        _last_position = _current_position
        return

    segment_distance = Utils.Distance(_last_position, _current_position)
    if segment_distance >= MIN_DISTANCE_DELTA:
        _distance_walked += segment_distance
    _last_position = _current_position



def _format_distance(distance: float) -> str:
    if distance >= 1_000_000:
        return f"{distance / 1_000_000:.2f}M"
    if distance >= 1_000:
        return f"{distance / 1_000:.2f}k"
    return f"{distance:.1f}"


def draw_widget():
    global first_run, window_x, window_y, window_collapsed
    global _status_message

    if first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        first_run = False

    is_window_opened = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
    new_collapsed = PyImGui.is_window_collapsed()
    end_pos = PyImGui.get_window_pos()

    if is_window_opened:
        if _current_map_name:
            PyImGui.text(f"Map: {_current_map_name}")
        else:
            PyImGui.text("Map: Unknown")

        if _last_map_id is not None:
            PyImGui.text(f"Map ID: {_last_map_id}")

        PyImGui.separator()
        PyImGui.text(f"Distance walked: {_distance_walked:,.1f} gwinches")
        PyImGui.text(f"Approx. map units (÷96): {_distance_walked / 96:,.2f}")
        PyImGui.text(f"Formatted: {_format_distance(_distance_walked)} units")

        if _current_position is not None:
            PyImGui.separator()
            PyImGui.text(
                f"Current position: ({_current_position[0]:.0f}, {_current_position[1]:.0f})"
            )

        PyImGui.separator()
        PyImGui.text(f"Last reset: {_last_reset_reason}")

        if PyImGui.button("Reset distance"):
            _reset_distance("Manual reset", keep_position=True)

        if _status_message:
            PyImGui.separator()
            PyImGui.text(_status_message)

    PyImGui.end()

    if save_window_timer.HasElapsed(1000):
        if (int(end_pos[0]), int(end_pos[1])) != (window_x, window_y):
            window_x, window_y = int(end_pos[0]), int(end_pos[1])
            ini_window.write_key(MODULE_NAME, X_POS_KEY, str(window_x))
            ini_window.write_key(MODULE_NAME, Y_POS_KEY, str(window_y))

        if new_collapsed != window_collapsed:
            window_collapsed = new_collapsed
            ini_window.write_key(MODULE_NAME, COLLAPSED_KEY, str(window_collapsed))

        save_window_timer.Reset()


def configure():
    pass


def main():
    try:
        map_ready = GLOBAL_CACHE.Map.IsMapReady()
        party_loaded = GLOBAL_CACHE.Party.IsPartyLoaded() if map_ready else False

        if map_ready and party_loaded:
            if _handle_loading_state(map_ready, party_loaded):
                _update_distance_state()
        else:
            _handle_loading_state(map_ready, party_loaded)

        draw_widget()

    except ImportError as exc:
        _log_exception(exc)
    except ValueError as exc:
        _log_exception(exc)
    except TypeError as exc:
        _log_exception(exc)
    except Exception as exc:
        _log_exception(exc)


if __name__ == "__main__":
    main()
