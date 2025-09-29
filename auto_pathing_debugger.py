"""Auto pathing test harness with a debug UI.

This script exposes a small ImGui window that lets you experiment with the
`AutoPathing` helper.  You can type a destination either as individual X/Y
values or as a single combined string in ``(x, y)`` / ``x,y`` form, ask the
engine to generate an automatic path, and optionally order the player to follow
that path using the routine helpers.

Usage: load the script inside Py4GW, open the "Auto Pathing Debugger" window,
and set a destination.  The script will plan a path and, if requested, move the
player along it while drawing the route in the 3D overlay.
"""

from __future__ import annotations

import math
import re
import time
from typing import Iterable, List, Sequence, Tuple

import Py4GW
from Py4GWCoreLib import (
    AutoPathing,
    Color,
    ConsoleLog,
    DXOverlay,
    GLOBAL_CACHE,
    PyImGui,
    Routines,
)
from HeroAI.cache_data import CacheData

MODULE_NAME = "Auto Pathing Debugger"

_DESTINATION_PATTERN = re.compile(
    r"^\s*\(?\s*([-+]?[0-9]*\.?[0-9]+)\s*,\s*([-+]?[0-9]*\.?[0-9]+)\s*\)?\s*$"
)

# --- Runtime state -----------------------------------------------------------------
_destination_x: float = 0.0
_destination_y: float = 0.0
_destination_initialized: bool = False
_combined_input: str = ""
_combined_error: str = ""

_path_points: List[Tuple[float, float, float]] = []
_path_distance: float = 0.0
_plan_started_at: float = 0.0
_last_plan_duration: float = 0.0

_is_planning: bool = False
_is_following: bool = False
_follow_progress: float = 0.0
_status_message: str = "Idle"
_pause_reason: str | None = None

# Smoothing + movement options
_smooth_by_los: bool = True
_smooth_margin: float = 100.0
_smooth_step_distance: float = 200.0
_smooth_by_chaikin: bool = False
_chaikin_iterations: int = 1
_follow_tolerance: float = 175.0
_log_follow_steps: bool = False

# Cached helpers
_PATH_COLOR = Color(32, 200, 255, 255)
_ERROR_COLOR = Color(255, 96, 96, 255)
auto_pathing = AutoPathing()
_heroai_cache = CacheData()
_manual_pause_requested: bool = False


# --- Helper utilities ---------------------------------------------------------------
def _format_destination() -> str:
    return f"{_destination_x:.1f}, {_destination_y:.1f}"


def _parse_combined_destination(value: str) -> Tuple[float, float] | None:
    match = _DESTINATION_PATTERN.match(value)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def _calculate_path_distance(points: Sequence[Tuple[float, float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    distance = 0.0
    for (x1, y1, _), (x2, y2, _) in zip(points, points[1:]):
        distance += math.hypot(x2 - x1, y2 - y1)
    return distance


def _toggle_manual_pause() -> None:
    global _manual_pause_requested, _status_message

    _manual_pause_requested = not _manual_pause_requested
    if _manual_pause_requested:
        _status_message = "Manual pause enabled."
    else:
        _status_message = "Manual pause disabled."


def _determine_pause_reason() -> str | None:
    if _manual_pause_requested:
        return "manual"

    if getattr(_heroai_cache.data, "in_aggro", False):
        return "combat"

    if getattr(_heroai_cache, "in_looting_routine", False):
        return "looting"

    return None


def _should_pause_following() -> bool:
    global _pause_reason, _status_message

    reason = _determine_pause_reason()
    if reason:
        if reason != _pause_reason:
            _pause_reason = reason
            if reason == "manual":
                _status_message = "Paused manually."
            elif reason == "combat":
                _status_message = "Pausing for combat..."
            elif reason == "looting":
                _status_message = "Waiting for loot pickup..."
            else:
                _status_message = "Pausing follow..."
        return True

    if _pause_reason is not None:
        _pause_reason = None
        _status_message = "Resuming path..."

    return False


def _draw_path(points: Sequence[Tuple[float, float, float]]) -> None:
    if len(points) < 2:
        return

    overlay = DXOverlay()
    dx_color = _PATH_COLOR.to_dx_color()
    for start, end in zip(points, points[1:]):
        x1, y1, _ = start
        x2, y2, _ = end
        z1 = DXOverlay.FindZ(x1, y1) - 125
        z2 = DXOverlay.FindZ(x2, y2) - 125
        overlay.DrawLine3D(x1, y1, z1, x2, y2, z2, dx_color, False)


def _clear_path() -> None:
    global _path_points, _path_distance, _follow_progress, _status_message
    global _manual_pause_requested, _pause_reason
    _path_points = []
    _path_distance = 0.0
    _follow_progress = 0.0
    _status_message = "Path cleared."
    _manual_pause_requested = False
    _pause_reason = None


def _start_plan(auto_follow: bool) -> None:
    global _is_planning, _plan_started_at, _status_message, _path_points
    global _path_distance, _combined_error, _follow_progress
    global _manual_pause_requested, _pause_reason

    if _is_planning:
        _status_message = "Already planning a path."
        return

    player_agent_id = GLOBAL_CACHE.Player.GetAgentID()
    if player_agent_id == 0:
        _status_message = "Cannot plan path: player agent unavailable."
        return

    player_x, player_y = GLOBAL_CACHE.Player.GetXY()
    zplane = GLOBAL_CACHE.Agent.GetZPlane(player_agent_id)

    start_point = (player_x, player_y, zplane)
    goal_point = (_destination_x, _destination_y, zplane)

    _is_planning = True
    _path_points = []
    _path_distance = 0.0
    _follow_progress = 0.0
    _combined_error = ""
    _status_message = "Planning path..."
    _plan_started_at = time.time()
    _manual_pause_requested = False
    _pause_reason = None

    smoothing_kwargs = dict(
        smooth_by_los=_smooth_by_los,
        margin=_smooth_margin,
        step_dist=_smooth_step_distance,
        smooth_by_chaikin=_smooth_by_chaikin,
        chaikin_iterations=_chaikin_iterations,
    )

    def plan_coroutine(
        start: Tuple[float, float, float] = start_point,
        goal: Tuple[float, float, float] = goal_point,
        smoothing: dict | None = None,
        auto_follow_after_plan: bool = auto_follow,
        started_at: float = _plan_started_at,
    ):
        global _is_planning, _path_points, _status_message, _last_plan_duration
        global _path_distance

        try:
            path_result = yield from auto_pathing.get_path(
                start,
                goal,
                **(smoothing or {}),
            )
            _last_plan_duration = max(0.0, time.time() - started_at)

            if path_result:
                _path_points = list(path_result)
                _path_distance = _calculate_path_distance(_path_points)
                _status_message = (
                    f"Path ready: {len(_path_points)} points, "
                    f"{_path_distance:.0f}u ({_last_plan_duration:.2f}s)"
                )
                ConsoleLog(
                    MODULE_NAME,
                    f"Path planned with {len(_path_points)} waypoints.",
                    Py4GW.Console.MessageType.Info,
                )
                if auto_follow_after_plan:
                    GLOBAL_CACHE.Coroutines.append(
                        _follow_path_coroutine(_path_points, _follow_tolerance, _log_follow_steps)
                    )
            else:
                _status_message = f"No path found ({_last_plan_duration:.2f}s)."
                ConsoleLog(
                    MODULE_NAME,
                    "Auto pathing returned no path.",
                    Py4GW.Console.MessageType.Warning,
                )
        except Exception as exc:  # noqa: BLE001 - we want to surface everything
            _path_points = []
            _status_message = f"Path planning error: {exc}"
            ConsoleLog(
                MODULE_NAME,
                f"Path planning error: {exc}",
                Py4GW.Console.MessageType.Error,
            )
        finally:
            _is_planning = False
            yield

    GLOBAL_CACHE.Coroutines.append(
        plan_coroutine(smoothing=dict(smoothing_kwargs))
    )


def _follow_path_coroutine(
    points: Iterable[Tuple[float, float, float]],
    tolerance: float,
    log_steps: bool,
):
    global _is_following, _status_message, _follow_progress, _pause_reason

    path_copy = list(points)
    if len(path_copy) < 2:
        _status_message = "Path is too short to follow."
        return

    _is_following = True
    _follow_progress = 0.0
    _status_message = "Following path..."
    _pause_reason = None

    path_2d = [(x, y) for x, y, _ in path_copy]

    def on_progress(value: float) -> None:
        global _follow_progress, _status_message
        _follow_progress = max(0.0, min(1.0, value))
        _status_message = f"Following path ({_follow_progress * 100:.0f}%)."

    def runner():
        global _is_following, _status_message, _follow_progress
        global _manual_pause_requested, _pause_reason
        try:
            ConsoleLog(
                MODULE_NAME,
                f"Following {len(path_2d)} waypoints (tolerance {tolerance:.0f}).",
                Py4GW.Console.MessageType.Info,
            )
            result = yield from Routines.Yield.Movement.FollowPath(
                path_2d,
                tolerance=tolerance,
                log=log_steps,
                progress_callback=on_progress,
                custom_pause_fn=_should_pause_following,
            )
            _follow_progress = 1.0 if result else _follow_progress
            if result:
                _status_message = "Finished following path."
                ConsoleLog(
                    MODULE_NAME,
                    "Finished following path.",
                    Py4GW.Console.MessageType.Info,
                )
            else:
                _status_message = "Movement cancelled or failed."
                ConsoleLog(
                    MODULE_NAME,
                    "FollowPath returned early.",
                    Py4GW.Console.MessageType.Warning,
                )
        except Exception as exc:  # noqa: BLE001 - broad for debugging
            _status_message = f"Follow error: {exc}"
            ConsoleLog(
                MODULE_NAME,
                f"FollowPath raised: {exc}",
                Py4GW.Console.MessageType.Error,
            )
        finally:
            _is_following = False
            _manual_pause_requested = False
            _pause_reason = None
            yield

    return runner()


def _start_follow() -> None:
    global _is_following, _status_message, _manual_pause_requested, _pause_reason

    if _is_following:
        _status_message = "Already following a path."
        return
    if _is_planning:
        _status_message = "Wait for path planning to finish first."
        return
    if len(_path_points) < 2:
        _status_message = "Plan a path before following it."
        return

    _manual_pause_requested = False
    _pause_reason = None
    GLOBAL_CACHE.Coroutines.append(
        _follow_path_coroutine(_path_points, _follow_tolerance, _log_follow_steps)
    )


# --- UI rendering -------------------------------------------------------------------
def _render_destination_inputs() -> None:
    global _destination_x, _destination_y, _combined_input, _combined_error

    changed_x = PyImGui.input_float("Destination X", _destination_x)
    if changed_x != _destination_x:
        _destination_x = changed_x
        _combined_input = _format_destination()
        _combined_error = ""

    changed_y = PyImGui.input_float("Destination Y", _destination_y)
    if changed_y != _destination_y:
        _destination_y = changed_y
        _combined_input = _format_destination()
        _combined_error = ""

    combined = PyImGui.input_text("Combined (x,y)", _combined_input, 64)
    if combined != _combined_input:
        _combined_input = combined
        parsed = _parse_combined_destination(combined)
        if parsed:
            _destination_x, _destination_y = parsed
            _combined_error = ""
        elif combined.strip():
            _combined_error = "Expected format: (x, y) or x,y"
        else:
            _combined_error = ""

    if _combined_error:
        PyImGui.text_colored(_combined_error, _ERROR_COLOR.color_tuple)


def _render_options_section() -> None:
    global _smooth_by_los, _smooth_margin, _smooth_step_distance
    global _smooth_by_chaikin, _chaikin_iterations, _follow_tolerance, _log_follow_steps

    if PyImGui.collapsing_header("Path Options", PyImGui.TreeNodeFlags.DefaultOpen):
        _smooth_by_los = PyImGui.checkbox("Smooth by line of sight", _smooth_by_los)
        _smooth_margin = max(0.0, PyImGui.input_float("LOS margin", _smooth_margin))
        _smooth_step_distance = max(0.0, PyImGui.input_float("LOS step distance", _smooth_step_distance))
        _smooth_by_chaikin = PyImGui.checkbox("Apply Chaikin smoothing", _smooth_by_chaikin)
        _chaikin_iterations = max(0, PyImGui.input_int("Chaikin iterations", _chaikin_iterations))

        PyImGui.separator()
        _follow_tolerance = max(1.0, PyImGui.input_float("Follow tolerance", _follow_tolerance))
        _log_follow_steps = PyImGui.checkbox("Log movement retries", _log_follow_steps)


def _render_path_details() -> None:
    PyImGui.text(f"Status: {_status_message}")
    if _is_planning:
        PyImGui.text("Planning in progress...")
    if _is_following:
        PyImGui.text("Following path...")
    if _manual_pause_requested:
        PyImGui.text("Manual pause is active.")
    if _follow_progress > 0.0 and _follow_progress < 1.0:
        PyImGui.progress_bar(_follow_progress, 200.0, f"{_follow_progress * 100:.1f}%")
    elif _follow_progress >= 1.0:
        PyImGui.progress_bar(1.0, 200.0, "100%")

    PyImGui.separator()

    if _path_points:
        PyImGui.text(f"Planned points: {len(_path_points)}")
        PyImGui.text(f"Total distance: {_path_distance:.1f} units")
        PyImGui.text(f"Last plan time: {_last_plan_duration:.2f}s")
        if PyImGui.collapsing_header("Path waypoints", PyImGui.TreeNodeFlags.DefaultOpen):
            if PyImGui.begin_child("##path_points_child", (360, 150), True, PyImGui.WindowFlags.AlwaysVerticalScrollbar):
                for idx, (px, py, pz) in enumerate(_path_points):
                    PyImGui.text(f"{idx:02d}: ({px:.1f}, {py:.1f}, {pz:.1f})")
                PyImGui.end_child()
    else:
        PyImGui.text("No path planned yet.")


def main() -> None:
    global _destination_initialized, _destination_x, _destination_y, _combined_input, _combined_error, _status_message

    player_agent_id = GLOBAL_CACHE.Player.GetAgentID()
    if not _destination_initialized and player_agent_id != 0:
        player_x, player_y = GLOBAL_CACHE.Player.GetXY()
        _destination_x = player_x
        _destination_y = player_y
        _combined_input = _format_destination()
        _destination_initialized = True

    if PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize):
        if player_agent_id != 0:
            player_x, player_y = GLOBAL_CACHE.Player.GetXY()
            zplane = GLOBAL_CACHE.Agent.GetZPlane(player_agent_id)
            PyImGui.text(f"Player position: ({player_x:.1f}, {player_y:.1f}, {zplane})")
        else:
            PyImGui.text("Player position unavailable.")

        PyImGui.separator()
        _render_destination_inputs()

        if PyImGui.button("Use player position"):
            if player_agent_id != 0:
                player_x, player_y = GLOBAL_CACHE.Player.GetXY()
                _destination_x = player_x
                _destination_y = player_y
                _combined_input = _format_destination()
                _combined_error = ""
            else:
                _status_message = "Cannot read player position right now."
        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Plan path"):
            _start_plan(auto_follow=False)
        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Plan && follow"):
            _start_plan(auto_follow=True)

        if PyImGui.button("Follow saved path"):
            _start_follow()
        PyImGui.same_line(0.0, -1.0)
        pause_label = "Resume follow" if _manual_pause_requested else "Pause follow"
        if PyImGui.button(pause_label):
            _toggle_manual_pause()
        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Clear path"):
            _clear_path()

        PyImGui.separator()
        _render_options_section()
        PyImGui.separator()
        _render_path_details()

    PyImGui.end()

    _draw_path(_path_points)


if __name__ == "__main__":
    main()
