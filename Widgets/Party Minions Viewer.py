"""Party Minions Viewer
======================

A compact monitor showing every allied minion currently controlled by the party.
The widget keeps a stable table height, avoids name flicker, and throttles game
queries to remain lightweight.  Minions are sorted by the time they first
appeared so the oldest summons stay at the top of the list.
"""

from __future__ import annotations

import math
import os
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

import Py4GW  # type: ignore

from Py4GWCoreLib import (
    Agent,
    AgentArray,
    Color,
    Player,
    PyImGui,
    Routines,
    Timer,
    Utils,
)
from Py4GWCoreLib import IniHandler

MODULE_NAME = "Party Minions Viewer"

# --------------------------------------------------------------------------------------
# Persistent window state --------------------------------------------------------------
# --------------------------------------------------------------------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_INI_DIRECTORY = os.path.join(_PROJECT_ROOT, "Widgets", "Config")
os.makedirs(_INI_DIRECTORY, exist_ok=True)
_INI_FILE = os.path.join(_INI_DIRECTORY, f"{MODULE_NAME}.ini")


@dataclass(slots=True)
class WindowState:
    x: int = 120
    y: int = 120
    collapsed: bool = False


class WindowStateManager:
    """Handles loading and saving the ImGui window position/collapse state."""

    def __init__(self, handler: IniHandler, section: str) -> None:
        self._handler = handler
        self._section = section
        self.state = WindowState(
            x=self._handler.read_int(section, "x", 120),
            y=self._handler.read_int(section, "y", 120),
            collapsed=self._handler.read_bool(section, "collapsed", False),
        )
        self._save_timer = Timer()
        self._save_timer.Start()
        self._dirty = False
        self._first_frame = True

    def apply_on_first_frame(self) -> None:
        if not self._first_frame:
            return
        PyImGui.set_next_window_pos(self.state.x, self.state.y)
        PyImGui.set_next_window_collapsed(self.state.collapsed, 0)
        self._first_frame = False

    def mark_dirty(self, position: Optional[Tuple[float, float]], collapsed: bool) -> None:
        if position:
            try:
                px, py = int(position[0]), int(position[1])
            except Exception:
                px, py = self.state.x, self.state.y
        else:
            px, py = self.state.x, self.state.y

        if (px, py) != (self.state.x, self.state.y):
            self.state.x, self.state.y = px, py
            self._dirty = True

        if collapsed != self.state.collapsed:
            self.state.collapsed = collapsed
            self._dirty = True

    def persist_if_needed(self) -> None:
        if not self._dirty:
            return
        if not self._save_timer.HasElapsed(1000):
            return

        self._handler.write_key(self._section, "x", str(self.state.x))
        self._handler.write_key(self._section, "y", str(self.state.y))
        self._handler.write_key(self._section, "collapsed", str(self.state.collapsed))
        self._save_timer.Reset()
        self._dirty = False


_ini_handler = IniHandler(_INI_FILE)
_window_state = WindowStateManager(_ini_handler, MODULE_NAME)

# --------------------------------------------------------------------------------------
# Utility helpers ---------------------------------------------------------------------
# --------------------------------------------------------------------------------------

HP_OK_COLOR = Color(92, 184, 92, 255).to_tuple_normalized()
HP_BAD_COLOR = Color(200, 80, 80, 255).to_tuple_normalized()
TARGET_NAME_COLOR = Color(255, 215, 0, 255).to_tuple_normalized()


@contextmanager
def _style_var(var, value):
    PyImGui.push_style_var(var, value)
    try:
        yield
    finally:
        PyImGui.pop_style_var(1)


def _tiny_button(label: str, width: int = 70) -> bool:
    """Render a compact button without increasing row height."""
    if hasattr(PyImGui, "small_button"):
        return PyImGui.small_button(label)
    with _style_var(PyImGui.ImGuiStyleVar.FramePadding, (4, 1)):
        return PyImGui.button(label, width=width)


def _safe_xy(getter) -> Optional[Tuple[float, float]]:
    try:
        x, y = getter()
        return float(x), float(y)
    except Exception:
        return None


def _distance(a: Optional[Tuple[float, float]], b: Optional[Tuple[float, float]]) -> Optional[float]:
    if not a or not b:
        return None
    try:
        return float(Utils.Distance(a, b))
    except Exception:
        try:
            ax, ay = a
            bx, by = b
            return math.hypot(float(ax) - float(bx), float(ay) - float(by))
        except Exception:
            return None


def _hp_percent(agent_id: int) -> float:
    try:
        health = float(Agent.GetHealth(agent_id))
        if 0.0 <= health <= 1.1:
            value = health * 100.0
        else:
            maximum = max(1.0, float(Agent.GetMaxHealth(agent_id)))
            value = (health / maximum) * 100.0
        return max(0.0, min(100.0, value))
    except Exception:
        return 0.0


# --------------------------------------------------------------------------------------
# Sticky name cache -------------------------------------------------------------------
# --------------------------------------------------------------------------------------

class NameCache:
    """Caches resolved names and throttles RequestName calls."""

    def __init__(self, request_interval: float = 1.0) -> None:
        self._values: dict[int, str] = {}
        self._last_request: dict[int, float] = {}
        self._interval = max(0.1, request_interval)

    @staticmethod
    def _sanitize(name: object) -> str:
        text = str(name) if not isinstance(name, str) else name
        return text.replace("\x00", "").strip()

    def get(self, agent_id: int) -> str:
        if agent_id in self._values:
            return self._values[agent_id]

        now = time.time()
        last = self._last_request.get(agent_id, 0.0)
        if now - last >= self._interval:
            try:
                Agent.RequestName(agent_id)
            except Exception:
                pass
            self._last_request[agent_id] = now

        try:
            if Agent.IsNameReady(agent_id):
                candidate = self._sanitize(Agent.GetName(agent_id))
                if candidate:
                    self._values[agent_id] = candidate
                    return candidate
        except Exception:
            pass

        return f"#{agent_id}"

    def prune(self, active_ids: Iterable[int]) -> None:
        active = set(active_ids)
        for cache in (self._values, self._last_request):
            for agent_id in list(cache.keys()):
                if agent_id not in active:
                    cache.pop(agent_id, None)


_name_cache = NameCache()

# --------------------------------------------------------------------------------------
# Minion data collection --------------------------------------------------------------
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class MinionRow:
    agent_id: int
    name: str
    level: int
    health_pct: float
    distance_to_player: Optional[int]
    first_seen: float

    @property
    def health_color(self) -> Tuple[float, float, float, float]:
        return HP_OK_COLOR if self.health_pct >= 50.0 else HP_BAD_COLOR

    @property
    def hp_display(self) -> str:
        return f"{self.health_pct:4.0f}%"

    @property
    def distance_display(self) -> str:
        return f"{self.distance_to_player:4d}" if self.distance_to_player is not None else " -- "


class PartyMinionTracker:
    """Produces sorted minion snapshots suitable for rendering."""

    def __init__(self, cache: NameCache) -> None:
        self._cache = cache
        self._first_seen: dict[int, float] = {}
        self._rows: list[MinionRow] = []
        self.refresh_interval_ms = 500
        self._refresh_timer = Timer()
        self._refresh_timer.Start()

    def _minion_ids(self) -> Iterable[int]:
        try:
            minions = list(AgentArray.GetMinionArray())
            if minions:
                return minions
        except Exception:
            pass

        try:
            return [agent_id for agent_id in AgentArray.GetAgentArray() if Agent.IsMinion(agent_id)]
        except Exception:
            return []

    def _is_valid_minion(self, agent_id: int) -> bool:
        if not agent_id:
            return False
        try:
            return Agent.IsAlive(agent_id) and Agent.IsMinion(agent_id)
        except Exception:
            return False

    def _build_row(
        self,
        agent_id: int,
        player_xy: Optional[Tuple[float, float]],
        first_seen: float,
    ) -> Optional[MinionRow]:
        try:
            name = self._cache.get(agent_id)
            level = int(Agent.GetLevel(agent_id) or 0)
        except Exception:
            return None

        health_pct = _hp_percent(agent_id)
        position = _safe_xy(lambda: Agent.GetXY(agent_id))
        dist_value = _distance(player_xy, position)
        distance_to_player = int(round(dist_value)) if dist_value is not None else None

        return MinionRow(
            agent_id=agent_id,
            name=name,
            level=level,
            health_pct=health_pct,
            distance_to_player=distance_to_player,
            first_seen=first_seen,
        )

    def refresh(self, player_xy: Optional[Tuple[float, float]]) -> None:
        if not self._refresh_timer.HasElapsed(self.refresh_interval_ms):
            return
        self._refresh_timer.Reset()

        now = time.time()
        current_ids: list[int] = []

        for agent_id in self._minion_ids():
            if not self._is_valid_minion(agent_id):
                continue
            current_ids.append(agent_id)
            self._first_seen.setdefault(agent_id, now)

        active_set = set(current_ids)
        for cached_id in list(self._first_seen.keys()):
            if cached_id not in active_set:
                self._first_seen.pop(cached_id, None)

        rows: list[MinionRow] = []
        for agent_id in sorted(current_ids, key=lambda aid: self._first_seen.get(aid, now)):
            row = self._build_row(agent_id, player_xy, self._first_seen.get(agent_id, now))
            if row:
                rows.append(row)

        self._cache.prune(active_set)
        self._rows = rows

    @property
    def rows(self) -> Sequence[MinionRow]:
        return self._rows


_tracker = PartyMinionTracker(_name_cache)

# --------------------------------------------------------------------------------------
# Rendering ---------------------------------------------------------------------------
# --------------------------------------------------------------------------------------

TABLE_ID = "party_minions_table"
TABLE_FLAGS = (
    PyImGui.TableFlags.Borders
    | PyImGui.TableFlags.RowBg
    | PyImGui.TableFlags.SizingFixedFit
    | PyImGui.TableFlags.Resizable
)


class PartyMinionViewer:
    def __init__(self) -> None:
        self._tracker = _tracker

    @staticmethod
    def _player_xy() -> Optional[Tuple[float, float]]:
        return _safe_xy(Player.GetXY)

    @staticmethod
    def _player_target() -> Optional[int]:
        try:
            target_id = Player.GetTargetID()
            return int(target_id) if target_id else None
        except Exception:
            return None

    def _render_empty_state(self) -> None:
        PyImGui.text_disabled("No party minions detected.")

    def _render_table(self, rows: Sequence[MinionRow], player_target: Optional[int]) -> None:
        if not rows:
            self._render_empty_state()
            return

        if PyImGui.begin_table(TABLE_ID, 6, TABLE_FLAGS):
            PyImGui.table_setup_column("ID", PyImGui.TableColumnFlags.WidthFixed, 70)
            PyImGui.table_setup_column("Name", PyImGui.TableColumnFlags.WidthFixed, 220)
            PyImGui.table_setup_column("Lv", PyImGui.TableColumnFlags.WidthFixed, 40)
            PyImGui.table_setup_column("HP%", PyImGui.TableColumnFlags.WidthFixed, 60)
            PyImGui.table_setup_column("Dist Me", PyImGui.TableColumnFlags.WidthFixed, 70)
            PyImGui.table_setup_column("", PyImGui.TableColumnFlags.WidthFixed, 70)
            if hasattr(PyImGui, "table_setup_scroll_freeze"):
                PyImGui.table_setup_scroll_freeze(0, 1)
            PyImGui.table_headers_row()

            for row in rows:
                is_targeted = player_target == row.agent_id

                PyImGui.table_next_row()

                PyImGui.table_next_column()
                PyImGui.text(str(row.agent_id))

                PyImGui.table_next_column()
                if is_targeted:
                    PyImGui.text_colored(row.name, TARGET_NAME_COLOR)
                else:
                    PyImGui.text(row.name)

                PyImGui.table_next_column()
                PyImGui.text(f"{row.level}")

                PyImGui.table_next_column()
                PyImGui.text_colored(row.hp_display, row.health_color)

                PyImGui.table_next_column()
                PyImGui.text(row.distance_display)

                PyImGui.table_next_column()
                if _tiny_button(f"Target##{row.agent_id}", width=60):
                    try:
                        Player.ChangeTarget(row.agent_id)
                    except Exception:
                        pass

            PyImGui.end_table()

    def draw(self) -> None:
        _window_state.apply_on_first_frame()

        opened = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
        collapsed = PyImGui.is_window_collapsed()
        position = PyImGui.get_window_pos() if hasattr(PyImGui, "get_window_pos") else None

        if opened:
            player_xy = self._player_xy()
            self._tracker.refresh(player_xy)
            rows = self._tracker.rows
            target = self._player_target()

            PyImGui.text_disabled(f"Minions: {len(rows)}")
            PyImGui.separator()
            self._render_table(rows, target)

        PyImGui.end()

        _window_state.mark_dirty(position, collapsed)
        _window_state.persist_if_needed()


_viewer = PartyMinionViewer()

# --------------------------------------------------------------------------------------
# Widget lifecycle --------------------------------------------------------------------
# --------------------------------------------------------------------------------------


def configure() -> None:
    """Called by the widget manager when configuration should be displayed."""
    pass


def main() -> None:
    try:
        if not Routines.Checks.Map.MapValid():
            return
        _viewer.draw()
    except Exception as exc:
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Unexpected error: {exc}",
            Py4GW.Console.MessageType.Error,
        )
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Stack trace: {traceback.format_exc()}",
            Py4GW.Console.MessageType.Error,
        )


if __name__ == "__main__":
    main()
