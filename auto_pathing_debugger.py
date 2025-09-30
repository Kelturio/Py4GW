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

import ctypes
import math
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Generator, Iterable, List, Sequence, Tuple

import Py4GW
from Py4GWCoreLib import (
    AutoPathing,
    Color,
    ConsoleLog,
    DXOverlay,
    GLOBAL_CACHE,
    LootConfig,
    PyImGui,
    Range,
    Routines,
    SharedCommandType,
)

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

_manual_pause: bool = False
_pause_reason: str | None = None

_active_follow_coroutine: Generator | None = None

# Loot detection helpers
_loot_detected_at: float = 0.0
_LOOT_GRACE_PERIOD: float = 1.5

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
_PATH_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_pending_plan: Future | None = None


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


def _execute_path_plan(
    start: Tuple[float, float, float],
    goal: Tuple[float, float, float],
    smoothing: dict | None,
    started_at: float,
) -> Tuple[List[Tuple[float, float, float]], float, float]:
    generator = auto_pathing.get_path(start, goal, **(smoothing or {}))
    path_points: List[Tuple[float, float, float]] = []
    try:
        while True:
            next(generator)
    except StopIteration as stop:
        if stop.value:
            path_points = list(stop.value)
    duration = max(0.0, time.time() - started_at)
    path_distance = _calculate_path_distance(path_points)
    return path_points, path_distance, duration


def _clear_path() -> None:
    global _path_points, _path_distance, _follow_progress, _status_message
    _path_points = []
    _path_distance = 0.0
    _follow_progress = 0.0
    _status_message = "Path cleared."


def _coerce_quest_coordinate(value: object) -> float | None:
    """Return a sane quest coordinate or ``None`` if it is unusable."""

    if value is None:
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(numeric):
        return None

    # Quest data sometimes arrives as unsigned 32-bit integers even though the
    # coordinates are meant to be signed.  Normalise those values so negative
    # positions are reported correctly.
    if numeric >= 2**31 or numeric <= -2**31:
        try:
            numeric = float(ctypes.c_int32(int(numeric) & 0xFFFFFFFF).value)
        except (OverflowError, ValueError):
            return None

    return numeric


def _use_active_quest_marker() -> None:
    global _destination_x, _destination_y, _combined_input, _combined_error, _status_message

    try:
        active_quest_id = GLOBAL_CACHE.Quest.GetActiveQuest()
    except Exception as exc:  # noqa: BLE001 - surface everything
        _status_message = f"Unable to read active quest: {exc}"
        return

    if not active_quest_id:
        _status_message = "No active quest to reference."
        return

    try:
        GLOBAL_CACHE.Quest.RequestQuestInfo(active_quest_id, True)
    except Exception as exc:  # noqa: BLE001 - surface everything
        _status_message = f"Failed to request quest info: {exc}"
        return

    try:
        quest_data = GLOBAL_CACHE.Quest.GetQuestData(active_quest_id)
    except Exception as exc:  # noqa: BLE001 - surface everything
        _status_message = f"Failed to load quest data: {exc}"
        return

    marker_x = _coerce_quest_coordinate(getattr(quest_data, "marker_x", None))
    marker_y = _coerce_quest_coordinate(getattr(quest_data, "marker_y", None))

    if marker_x is None or marker_y is None:
        _status_message = "Quest marker coordinates unavailable; requested refresh."
        try:
            GLOBAL_CACHE.Quest.RequestQuestInfo(active_quest_id, True)
        except Exception:
            pass
        return

    if marker_x == 0.0 and marker_y == 0.0:
        _status_message = "Quest marker not set; awaiting update."
        try:
            GLOBAL_CACHE.Quest.RequestQuestInfo(active_quest_id, True)
        except Exception:
            pass
        return

    _destination_x = marker_x
    _destination_y = marker_y
    _combined_input = _format_destination()
    _combined_error = ""
    _status_message = "Quest marker destination loaded."


def _follow_status_text() -> str:
    return f"Following path ({_follow_progress * 100:.0f}%)."


def _set_pause_reason(reason: str | None) -> None:
    global _pause_reason, _status_message

    if reason == _pause_reason:
        return

    _pause_reason = reason
    if reason:
        _status_message = reason
    elif _is_following:
        _status_message = _follow_status_text()


def _is_player_in_aggro() -> bool:
    try:
        return bool(Routines.Checks.Agents.InAggro(Range.Earshot.value))
    except Exception:
        return False


def _is_pickup_loot_active() -> bool:
    try:
        account_email = GLOBAL_CACHE.Player.GetAccountEmail()
        if not account_email:
            return False

        index, message = GLOBAL_CACHE.ShMem.PreviewNextMessage(account_email)
        if index == -1 or message is None:
            return False

        try:
            command = SharedCommandType(message.Command)
        except (ValueError, TypeError):
            return False

        return command == SharedCommandType.PickUpLoot
    except Exception:
        return False


def _has_pending_loot() -> bool:
    global _loot_detected_at

    try:
        loot_array = LootConfig().GetfilteredLootArray(
            Range.Earshot.value,
            multibox_loot=True,
        )
    except Exception:
        return False

    current_time = time.time()
    if loot_array:
        _loot_detected_at = current_time
        return True

    if _loot_detected_at and (current_time - _loot_detected_at) < _LOOT_GRACE_PERIOD:
        return True

    _loot_detected_at = 0.0
    return False


def _should_pause_following() -> bool:
    if _manual_pause:
        _set_pause_reason("Follow paused (manual).")
        return True

    if _is_player_in_aggro():
        _set_pause_reason("Pausing for combat (aggro detected).")
        return True

    if _is_pickup_loot_active():
        _set_pause_reason("Pausing for loot pickup.")
        return True

    if _has_pending_loot():
        _set_pause_reason("Waiting for HeroAI to loot.")
        return True

    _set_pause_reason(None)
    return False


def _queue_follow(points: Iterable[Tuple[float, float, float]], tolerance: float, log_steps: bool) -> None:
    global _active_follow_coroutine

    _stop_following(set_status=False, reset_manual_pause=False)

    follow_coroutine = _follow_path_coroutine(points, tolerance, log_steps)
    _active_follow_coroutine = follow_coroutine
    GLOBAL_CACHE.Coroutines.append(follow_coroutine)


def _wait_for_plan(
    future: Future,
    auto_follow_after_plan: bool,
    started_at: float,
) -> Generator:
    global _is_planning, _path_points, _status_message, _last_plan_duration
    global _path_distance, _pending_plan

    try:
        while not future.done():
            yield

        try:
            path_points, path_distance, duration = future.result()
        except Exception as exc:  # noqa: BLE001 - propagate full context
            _path_points = []
            _path_distance = 0.0
            _last_plan_duration = max(0.0, time.time() - started_at)
            _status_message = f"Path planning error: {exc}"
            ConsoleLog(
                MODULE_NAME,
                f"Path planning error: {exc}",
                Py4GW.Console.MessageType.Error,
            )
        else:
            _last_plan_duration = duration
            if path_points:
                _path_points = list(path_points)
                _path_distance = path_distance
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
                    _queue_follow(_path_points, _follow_tolerance, _log_follow_steps)
            else:
                _path_points = []
                _path_distance = 0.0
                _status_message = f"No path found ({_last_plan_duration:.2f}s)."
                ConsoleLog(
                    MODULE_NAME,
                    "Auto pathing returned no path.",
                    Py4GW.Console.MessageType.Warning,
                )
    finally:
        _is_planning = False
        _pending_plan = None


def _stop_following(set_status: bool = True, reset_manual_pause: bool = True) -> None:
    global _active_follow_coroutine, _is_following, _manual_pause, _follow_progress

    if _active_follow_coroutine in GLOBAL_CACHE.Coroutines:
        try:
            GLOBAL_CACHE.Coroutines.remove(_active_follow_coroutine)
        except ValueError:
            pass

    _active_follow_coroutine = None
    _is_following = False
    if reset_manual_pause:
        _manual_pause = False
    _follow_progress = 0.0
    if not _manual_pause:
        _set_pause_reason(None)
    try:
        GLOBAL_CACHE.Player.CancelMove()
    except Exception:
        pass

    if set_status:
        global _status_message
        _status_message = "Follow stopped."


def _start_plan(auto_follow: bool) -> None:
    global _is_planning, _plan_started_at, _status_message, _path_points
    global _path_distance, _combined_error, _follow_progress, _pending_plan

    if _pending_plan and not _pending_plan.done():
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

    smoothing_kwargs = dict(
        smooth_by_los=_smooth_by_los,
        margin=_smooth_margin,
        step_dist=_smooth_step_distance,
        smooth_by_chaikin=_smooth_by_chaikin,
        chaikin_iterations=_chaikin_iterations,
    )

    started_at = _plan_started_at
    try:
        future = _PATH_EXECUTOR.submit(
            _execute_path_plan,
            start_point,
            goal_point,
            dict(smoothing_kwargs),
            started_at,
        )
    except Exception as exc:  # noqa: BLE001 - executor setup issues should surface
        _is_planning = False
        _status_message = f"Failed to submit path plan: {exc}"
        ConsoleLog(
            MODULE_NAME,
            f"Failed to submit path plan: {exc}",
            Py4GW.Console.MessageType.Error,
        )
        return
    _pending_plan = future
    GLOBAL_CACHE.Coroutines.append(
        _wait_for_plan(future, auto_follow, started_at)
    )


def _follow_path_coroutine(
    points: Iterable[Tuple[float, float, float]],
    tolerance: float,
    log_steps: bool,
):
    global _is_following, _status_message, _follow_progress

    path_copy = list(points)
    if len(path_copy) < 2:
        _status_message = "Path is too short to follow."
        return

    _is_following = True
    _follow_progress = 0.0
    _status_message = "Following path..."

    path_2d = [(x, y) for x, y, _ in path_copy]

    def on_progress(value: float) -> None:
        global _follow_progress, _status_message
        _follow_progress = max(0.0, min(1.0, value))
        if _pause_reason:
            _status_message = _pause_reason
        else:
            _status_message = _follow_status_text()

    def runner():
        global _is_following, _status_message, _follow_progress, _active_follow_coroutine
        try:
            ConsoleLog(
                MODULE_NAME,
                f"Following {len(path_2d)} waypoints (tolerance {tolerance:.0f}).",
                Py4GW.Console.MessageType.Info,
            )
            if not _manual_pause:
                _set_pause_reason(None)
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
            _set_pause_reason(None)
            _active_follow_coroutine = None

    return runner()


def _start_follow() -> None:
    global _is_following, _status_message

    if _is_following:
        _status_message = "Already following a path."
        return
    if _is_planning:
        _status_message = "Wait for path planning to finish first."
        return
    if len(_path_points) < 2:
        _status_message = "Plan a path before following it."
        return

    _queue_follow(_path_points, _follow_tolerance, _log_follow_steps)


# --- UI rendering -------------------------------------------------------------------
def _render_destination_inputs() -> None:
    global _destination_x, _destination_y, _combined_input, _combined_error

    PyImGui.set_next_item_width(120.0)
    changed_x = PyImGui.input_float("Destination X", _destination_x)
    if changed_x != _destination_x:
        _destination_x = changed_x
        _combined_input = _format_destination()
        _combined_error = ""

    PyImGui.same_line(0.0, 8.0)
    PyImGui.set_next_item_width(120.0)
    changed_y = PyImGui.input_float("Destination Y", _destination_y)
    if changed_y != _destination_y:
        _destination_y = changed_y
        _combined_input = _format_destination()
        _combined_error = ""

    PyImGui.set_next_item_width(248.0)
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
    if _pause_reason:
        PyImGui.text(f"Pause reason: {_pause_reason}")
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
    global _destination_initialized, _destination_x, _destination_y, _combined_input
    global _combined_error, _status_message, _manual_pause

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
        if PyImGui.button("Use quest marker"):
            _use_active_quest_marker()
        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Plan path"):
            _start_plan(auto_follow=False)
        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Plan && follow"):
            _start_plan(auto_follow=True)

        if PyImGui.button("Follow saved path"):
            _start_follow()
        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Stop follow"):
            _stop_following()
        PyImGui.same_line(0.0, -1.0)
        pause_label = "Resume follow" if _manual_pause else "Pause follow"
        if PyImGui.button(pause_label):
            _manual_pause = not _manual_pause
            if _manual_pause:
                _set_pause_reason("Follow paused (manual).")
            else:
                _set_pause_reason(None)
                if not _is_following and not _is_planning:
                    _status_message = "Idle"
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