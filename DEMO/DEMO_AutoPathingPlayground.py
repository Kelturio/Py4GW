import math
from typing import Generator, Iterable, Optional

import Py4GW
from Py4GWCoreLib import (
    AutoPathing,
    Color,
    DXOverlay,
    GLOBAL_CACHE,
    PyImGui,
    PyMap,
    Routines,
)

module_name = "Auto Pathing Playground"


class AutoPathingDebugUI:
    """Interactive playground for testing AutoPathing with live movement."""

    MAX_STATUS_LINES = 6

    def __init__(self) -> None:
        self.pathing = AutoPathing()
        self.target_x: float = 0.0
        self.target_y: float = 0.0
        self.coordinate_input: str = ""
        self.status_lines: list[str] = []

        self.path_points: list[tuple[float, float]] = []
        self.search_in_progress: bool = False
        self.follow_in_progress: bool = False
        self.follow_progress: float = 0.0
        self._initialized_target: bool = False

        self._path_coroutine: Optional[Generator] = None
        self._follow_coroutine: Optional[Generator] = None
        self._stop_requested: bool = False

        # Path planning controls
        self.use_los_smoothing: bool = True
        self.los_margin: float = 100.0
        self.los_step_distance: float = 200.0
        self.use_chaikin_smoothing: bool = False
        self.chaikin_iterations: int = 1

        # Movement controls
        self.draw_path_overlay: bool = True
        self.log_follow_to_console: bool = False
        self.arrival_tolerance: float = 150.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _console_log(self, message: str) -> None:
        Py4GW.Console.Log(module_name, message, Py4GW.Console.MessageType.Info)
        self._push_status(message)

    def _console_error(self, message: str) -> None:
        Py4GW.Console.Log(module_name, message, Py4GW.Console.MessageType.Error)
        self._push_status(message)

    def _push_status(self, message: str) -> None:
        self.status_lines.insert(0, message)
        del self.status_lines[self.MAX_STATUS_LINES :]

    def _cancel_coroutine(self, handle: Optional[Generator]) -> None:
        if handle and handle in GLOBAL_CACHE.Coroutines:
            GLOBAL_CACHE.Coroutines.remove(handle)

    def _parse_combined_input(self, value: str) -> Optional[tuple[float, float]]:
        cleaned = value.strip()
        if not cleaned:
            return None

        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = cleaned[1:-1]

        cleaned = cleaned.replace(",", " ")
        parts = [p for p in cleaned.split() if p]
        if len(parts) < 2:
            return None

        try:
            x_value = float(parts[0])
            y_value = float(parts[1])
        except ValueError:
            return None
        return x_value, y_value

    # ------------------------------------------------------------------
    # Path search and movement coroutines
    # ------------------------------------------------------------------
    def _queue_path_search(self, follow_after: bool) -> None:
        if self.search_in_progress:
            self._push_status("Path search already running.")
            return

        self._cancel_coroutine(self._path_coroutine)

        def path_coroutine() -> Iterable[None]:
            self.search_in_progress = True
            self._console_log(
                f"Planning path to ({self.target_x:.1f}, {self.target_y:.1f})..."
            )
            yield
            try:
                path2d = yield from self.pathing.get_path_to(
                    self.target_x,
                    self.target_y,
                    smooth_by_los=self.use_los_smoothing,
                    margin=self.los_margin,
                    step_dist=self.los_step_distance,
                    smooth_by_chaikin=self.use_chaikin_smoothing,
                    chaikin_iterations=self.chaikin_iterations,
                )
                self.path_points = list(path2d)
                if self.path_points:
                    self._console_log(
                        f"Path ready with {len(self.path_points)} points."
                    )
                    if follow_after:
                        self._queue_follow(self.path_points)
                else:
                    self._push_status("No path found.")
            except Exception as exc:  # pragma: no cover - safety for UI errors
                self._console_error(f"Path search failed: {exc}")
            finally:
                self.search_in_progress = False
                self._path_coroutine = None
            yield

        self._path_coroutine = path_coroutine()
        GLOBAL_CACHE.Coroutines.append(self._path_coroutine)

    def _queue_follow(self, path: Iterable[tuple[float, float]]) -> None:
        path_points = list(path)
        if not path_points:
            self._push_status("No cached path to follow.")
            return

        self._cancel_coroutine(self._follow_coroutine)

        self._stop_requested = False
        self.follow_progress = 0.0

        def on_progress(progress: float) -> None:
            self.follow_progress = max(0.0, min(100.0, progress * 100.0))

        def exit_condition() -> bool:
            return self._stop_requested

        def follow_coroutine() -> Iterable[None]:
            self.follow_in_progress = True
            self._console_log("Following planned path...")
            try:
                completed = yield from Routines.Yield.Movement.FollowPath(
                    path_points=path_points,
                    custom_exit_condition=exit_condition,
                    tolerance=self.arrival_tolerance,
                    log=self.log_follow_to_console,
                    progress_callback=on_progress,
                )
                if completed and not self._stop_requested:
                    self.follow_progress = 100.0
                    self._console_log("Destination reached.")
                elif self._stop_requested:
                    self._push_status("Movement stopped by user.")
                else:
                    self._push_status("Movement interrupted before arrival.")
            except Exception as exc:  # pragma: no cover - safety for UI errors
                self._console_error(f"Movement failed: {exc}")
            finally:
                self.follow_in_progress = False
                self._follow_coroutine = None
                self._stop_requested = False
            yield

        self._follow_coroutine = follow_coroutine()
        GLOBAL_CACHE.Coroutines.append(self._follow_coroutine)

    def stop_following(self) -> None:
        if not self.follow_in_progress:
            return
        self._stop_requested = True
        self._cancel_coroutine(self._follow_coroutine)
        self.follow_in_progress = False
        self._follow_coroutine = None
        self.follow_progress = 0.0
        self._push_status("Movement cancelled.")

    # ------------------------------------------------------------------
    # UI rendering
    # ------------------------------------------------------------------
    def draw(self) -> None:
        player_xy = GLOBAL_CACHE.Player.GetXY()
        player_agent_id = GLOBAL_CACHE.Player.GetAgentID()
        player_z = GLOBAL_CACHE.Agent.GetZPlane(player_agent_id) if player_agent_id else 0.0

        if not self._initialized_target and any(player_xy):
            self.target_x, self.target_y = player_xy
            self.coordinate_input = f"{self.target_x:.0f}, {self.target_y:.0f}"
            self._initialized_target = True

        if PyImGui.begin(module_name, PyImGui.WindowFlags.AlwaysAutoResize):
            PyImGui.text(f"Map ID: {PyMap.PyMap().map_id.ToInt()}")
            navmesh_loaded = self.pathing.get_navmesh() is not None
            PyImGui.text(f"NavMesh loaded: {'Yes' if navmesh_loaded else 'No'}")
            PyImGui.separator()

            PyImGui.text(
                f"Player: ({player_xy[0]:.1f}, {player_xy[1]:.1f}, {player_z:.1f})"
            )
            PyImGui.separator()

            self.target_x = PyImGui.input_float("Target X", self.target_x)
            self.target_y = PyImGui.input_float("Target Y", self.target_y)

            if PyImGui.button("Set Target To Player"):
                self.target_x, self.target_y = player_xy
                self.coordinate_input = f"{self.target_x:.0f}, {self.target_y:.0f}"
                self._push_status("Target set to current player position.")
            PyImGui.same_line()
            if PyImGui.button("Plan Path"):
                self._queue_path_search(follow_after=False)
            PyImGui.same_line()
            if PyImGui.button("Plan & Move"):
                self._queue_path_search(follow_after=True)

            combined_value = PyImGui.input_text("Target (x, y)", self.coordinate_input)
            if combined_value != self.coordinate_input:
                self.coordinate_input = combined_value
            PyImGui.same_line()
            if PyImGui.button("Apply"):
                parsed = self._parse_combined_input(self.coordinate_input)
                if parsed:
                    self.target_x, self.target_y = parsed
                    self._push_status(
                        f"Target updated to ({self.target_x:.1f}, {self.target_y:.1f})."
                    )
                else:
                    self._push_status("Could not parse combined coordinate input.")

            PyImGui.separator()
            self.use_los_smoothing = PyImGui.checkbox(
                "Smooth by line-of-sight", self.use_los_smoothing
            )
            self.los_margin = PyImGui.input_float("LOS margin", self.los_margin)
            self.los_step_distance = PyImGui.input_float(
                "LOS step distance", self.los_step_distance
            )
            self.use_chaikin_smoothing = PyImGui.checkbox(
                "Apply Chaikin smoothing", self.use_chaikin_smoothing
            )
            self.chaikin_iterations = PyImGui.input_int(
                "Chaikin iterations", self.chaikin_iterations
            )

            PyImGui.separator()
            self.log_follow_to_console = PyImGui.checkbox(
                "Log movement steps", self.log_follow_to_console
            )
            self.arrival_tolerance = PyImGui.input_float(
                "Arrival tolerance", self.arrival_tolerance
            )
            self.draw_path_overlay = PyImGui.checkbox(
                "Draw path overlay", self.draw_path_overlay
            )

            if self.path_points:
                if PyImGui.button("Follow Cached Path"):
                    self._queue_follow(self.path_points)
                PyImGui.same_line()
                if PyImGui.button("Clear Path"):
                    self.path_points.clear()
                    self._push_status("Cached path cleared.")

            if self.follow_in_progress:
                PyImGui.same_line()
                if PyImGui.button("Stop Movement"):
                    self.stop_following()

            PyImGui.separator()
            PyImGui.text(f"Status: {'Planning' if self.search_in_progress else 'Idle'}")
            PyImGui.text(
                f"Movement: {'Active' if self.follow_in_progress else 'Stopped'}"
            )
            if self.follow_in_progress or self.follow_progress > 0:
                PyImGui.text(f"Progress: {self.follow_progress:.1f}%")

            if self.path_points:
                distance = self._estimate_path_length(self.path_points)
                PyImGui.text(
                    f"Cached path length: {len(self.path_points)} points, ~{distance:.1f} units"
                )

            if self.status_lines:
                PyImGui.separator()
                if PyImGui.collapsing_header(
                    "Recent events", PyImGui.TreeNodeFlags.DefaultOpen
                ):
                    for line in self.status_lines:
                        PyImGui.text_wrapped(line)

            if self.path_points and PyImGui.collapsing_header(
                "Path preview", PyImGui.TreeNodeFlags.DefaultOpen
            ):
                for index, (px, py) in enumerate(self.path_points):
                    PyImGui.text(f"{index:02d}: ({px:.1f}, {py:.1f})")

            PyImGui.end()

        if self.draw_path_overlay and self.path_points:
            self._draw_overlay_path(self.path_points)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @staticmethod
    def _estimate_path_length(points: Iterable[tuple[float, float]]) -> float:
        total = 0.0
        iterator = iter(points)
        try:
            prev = next(iterator)
        except StopIteration:
            return 0.0
        for current in iterator:
            total += math.dist(prev, current)
            prev = current
        return total

    @staticmethod
    def _draw_overlay_path(points: Iterable[tuple[float, float]]) -> None:
        line_color = Color(0, 200, 255, 255).to_dx_color()
        points_list = list(points)
        for idx in range(len(points_list) - 1):
            x1, y1 = points_list[idx]
            x2, y2 = points_list[idx + 1]
            z1 = DXOverlay.FindZ(x1, y1) - 125
            z2 = DXOverlay.FindZ(x2, y2) - 125
            DXOverlay().DrawLine3D(x1, y1, z1, x2, y2, z2, line_color, False)


auto_pathing_ui = AutoPathingDebugUI()


def main() -> None:
    auto_pathing_ui.draw()


if __name__ == "__main__":
    main()
