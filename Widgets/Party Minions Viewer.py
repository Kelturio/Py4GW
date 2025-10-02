# Widgets/Party Minions Viewer.py

"""
Party Minions Viewer
====================
A compact widget that lists every minion owned by the player's party.
The list has a stable height thanks to a sticky name cache and a
first-seen tracker that prevents rows from jumping around whenever
minions spawn or die.

Compared to the original implementation this rewrite focuses on
structured state management, clearer responsibilities and slightly
richer feedback (for example the currently targeted minion is now
highlighted and HP colours are tiered).
"""

from __future__ import annotations

import math
import os
import time
import traceback
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

import Py4GW  # type: ignore
from Py4GWCoreLib import (
    Agent,
    AgentArray,
    Color,
    IniHandler,
    Player,
    PyImGui,
    Routines,
    Timer,
    Utils,
)

# --------------------------------------------------------------------------------------
# Constants & configuration
# --------------------------------------------------------------------------------------

MODULE_NAME = "Party Minions Viewer"
INI_SECTION = MODULE_NAME
REFRESH_INTERVAL_MS = 500
WINDOW_SAVE_INTERVAL_MS = 1000
DEFAULT_WINDOW_POS = (120, 120)
DEFAULT_COLLAPSED = False

_widget_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_widget_dir, os.pardir))
_config_dir = os.path.join(_project_root, "Widgets", "Config")
os.makedirs(_config_dir, exist_ok=True)
INI_WIDGET_WINDOW_PATH = os.path.join(_config_dir, f"{MODULE_NAME}.ini")

ini_window = IniHandler(INI_WIDGET_WINDOW_PATH)

# --------------------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------------------

HP_COLOR_HIGH = Color(92, 184, 92, 255).to_tuple_normalized()
HP_COLOR_MID = Color(229, 180, 25, 255).to_tuple_normalized()
HP_COLOR_LOW = Color(200, 80, 80, 255).to_tuple_normalized()
TARGET_ID_COLOR = Color(110, 170, 255, 255).to_tuple_normalized()
TARGET_NAME_COLOR = Color(120, 180, 255, 255).to_tuple_normalized()

# --------------------------------------------------------------------------------------
# Helper utilities
# --------------------------------------------------------------------------------------


def _distance_xy(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Return planar distance between two XY pairs."""
    try:
        return float(Utils.Distance(a, b))
    except Exception:
        try:
            ax, ay = a
            bx, by = b
            return math.hypot(float(ax) - float(bx), float(ay) - float(by))
        except Exception:
            return 0.0


def _hp_percent(agent_id: int) -> float:
    """Return the agent's HP percentage in [0, 100]."""
    try:
        hp = float(Agent.GetHealth(agent_id))
    except Exception:
        return 0.0

    if hp <= 0:
        return 0.0

    if 0.0 <= hp <= 1.2:
        return max(0.0, min(100.0, hp * 100.0))

    try:
        max_hp = float(max(1.0, Agent.GetMaxHealth(agent_id)))
    except Exception:
        return 0.0

    return max(0.0, min(100.0, (hp / max_hp) * 100.0))


def _safe_level(agent_id: int) -> int:
    try:
        value = Agent.GetLevel(agent_id)
        return int(value) if value is not None else 0
    except Exception:
        return 0


def _safe_xy(agent_id: int) -> Optional[Tuple[float, float]]:
    try:
        coords = Agent.GetXY(agent_id)
        if isinstance(coords, Sequence) and len(coords) >= 2:
            return float(coords[0]), float(coords[1])
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------------------
# Sticky name cache (prevents '#id' flicker)
# --------------------------------------------------------------------------------------


class NameCache:
    """Caches the first resolved name for each agent ID."""

    def __init__(self, request_interval: float = 1.0) -> None:
        self._names: dict[int, str] = {}
        self._last_request: dict[int, float] = {}
        self._request_interval = max(0.1, float(request_interval))

    @staticmethod
    def _sanitize(name: object) -> str:
        if isinstance(name, str):
            return name.replace("\x00", "").strip()
        return str(name)

    def get(self, agent_id: int) -> str:
        cached = self._names.get(agent_id)
        if cached:
            return cached

        now = time.monotonic()
        last = self._last_request.get(agent_id, 0.0)
        if now - last >= self._request_interval:
            try:
                Agent.RequestName(agent_id)
            except Exception:
                pass
            self._last_request[agent_id] = now

        try:
            if Agent.IsNameReady(agent_id):
                resolved = self._sanitize(Agent.GetName(agent_id))
                if resolved:
                    self._names[agent_id] = resolved
                    return resolved
        except Exception:
            pass

        return f"#{agent_id}"

    def trim(self, valid_ids: Iterable[int]) -> None:
        valid = set(valid_ids)
        self._names = {aid: name for aid, name in self._names.items() if aid in valid}
        self._last_request = {
            aid: stamp for aid, stamp in self._last_request.items() if aid in valid
        }


# --------------------------------------------------------------------------------------
# Minion tracking model
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class MinionRow:
    agent_id: int
    name: str
    level: int
    hp_pct: float
    position: Optional[Tuple[float, float]]
    first_seen: float
    is_target: bool = False

    def distance_from(self, origin: Optional[Tuple[float, float]]) -> int:
        if not origin or not self.position:
            return 0
        return int(_distance_xy(origin, self.position))


class MinionTracker:
    """Produces a sorted list of party minions with cached metadata."""

    def __init__(self, cache: NameCache, refresh_ms: int = REFRESH_INTERVAL_MS) -> None:
        self._cache = cache
        self._refresh_ms = refresh_ms
        self._refresh_timer = Timer()
        self._refresh_timer.Start()
        self._first_seen: dict[int, float] = {}
        self._rows: list[MinionRow] = []

    def refresh(self) -> None:
        if not self._refresh_timer.HasElapsed(self._refresh_ms):
            return

        self._refresh_timer.Reset()
        now = time.time()
        target_id = self._safe_target_id()

        valid_ids: list[int] = []
        rows: list[MinionRow] = []

        for agent_id in self._collect_candidate_ids():
            row = self._build_row(agent_id, now, target_id)
            if row is None:
                continue
            valid_ids.append(agent_id)
            rows.append(row)

        rows.sort(key=lambda item: item.first_seen)
        self._rows = rows

        valid_set = set(valid_ids)
        for stale_id in list(self._first_seen.keys()):
            if stale_id not in valid_set:
                self._first_seen.pop(stale_id, None)

        self._cache.trim(valid_set)

    @property
    def rows(self) -> list[MinionRow]:
        return list(self._rows)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _collect_candidate_ids(self) -> Sequence[int]:
        try:
            minion_ids = list(AgentArray.GetMinionArray())
            if minion_ids:
                return minion_ids
        except Exception:
            pass

        try:
            return [
                agent_id
                for agent_id in AgentArray.GetAgentArray()
                if Agent.IsMinion(agent_id)
            ]
        except Exception:
            return []

    def _build_row(
        self, agent_id: int, timestamp: float, target_id: int
    ) -> Optional[MinionRow]:
        try:
            if not agent_id or not Agent.IsAlive(agent_id) or not Agent.IsMinion(agent_id):
                return None
        except Exception:
            return None

        first_seen = self._first_seen.setdefault(agent_id, timestamp)
        name = self._cache.get(agent_id)
        level = _safe_level(agent_id)
        hp_pct = _hp_percent(agent_id)
        position = _safe_xy(agent_id)

        return MinionRow(
            agent_id=agent_id,
            name=name,
            level=level,
            hp_pct=hp_pct,
            position=position,
            first_seen=first_seen,
            is_target=agent_id == target_id,
        )

    @staticmethod
    def _safe_target_id() -> int:
        try:
            return int(Player.GetTargetID())
        except Exception:
            return 0


# --------------------------------------------------------------------------------------
# Window persistence helper
# --------------------------------------------------------------------------------------


class WindowPersistence:
    def __init__(self) -> None:
        self._first_frame = True
        self._position = (
            ini_window.read_int(INI_SECTION, "x", DEFAULT_WINDOW_POS[0]),
            ini_window.read_int(INI_SECTION, "y", DEFAULT_WINDOW_POS[1]),
        )
        self._collapsed = ini_window.read_bool(INI_SECTION, "collapsed", DEFAULT_COLLAPSED)
        self._save_timer = Timer()
        self._save_timer.Start()

    def apply_initial_state(self) -> None:
        if not self._first_frame:
            return
        PyImGui.set_next_window_pos(*self._position)
        PyImGui.set_next_window_collapsed(self._collapsed, 0)
        self._first_frame = False

    def persist(self, position: Optional[Sequence[float]], collapsed: bool) -> None:
        if not self._save_timer.HasElapsed(WINDOW_SAVE_INTERVAL_MS):
            return

        try:
            if position and len(position) >= 2:
                pos_x, pos_y = int(position[0]), int(position[1])
                if (pos_x, pos_y) != self._position:
                    self._position = (pos_x, pos_y)
                    ini_window.write_key(INI_SECTION, "x", str(pos_x))
                    ini_window.write_key(INI_SECTION, "y", str(pos_y))

            if collapsed != self._collapsed:
                self._collapsed = collapsed
                ini_window.write_key(INI_SECTION, "collapsed", str(collapsed))
        finally:
            self._save_timer.Reset()


# --------------------------------------------------------------------------------------
# UI helpers
# --------------------------------------------------------------------------------------


def _hp_color(value: float) -> Tuple[float, float, float, float]:
    if value >= 75.0:
        return HP_COLOR_HIGH
    if value >= 40.0:
        return HP_COLOR_MID
    return HP_COLOR_LOW


def _tiny_button(label: str, width: int = 70) -> bool:
    if hasattr(PyImGui, "small_button"):
        try:
            return PyImGui.small_button(label)
        except Exception:
            pass

    try:
        PyImGui.push_style_var(PyImGui.ImGuiStyleVar.FramePadding, (4, 1))
        clicked = PyImGui.button(label, width=width)
        PyImGui.pop_style_var(1)
        return clicked
    except Exception:
        return PyImGui.button(label, width=width)


def _text_disabled(message: str) -> None:
    if hasattr(PyImGui, "text_disabled"):
        try:
            PyImGui.text_disabled(message)
            return
        except Exception:
            pass
    PyImGui.text(message)


# --------------------------------------------------------------------------------------
# Widget implementation
# --------------------------------------------------------------------------------------


class PartyMinionsWidget:
    def __init__(self) -> None:
        self._names = NameCache()
        self._tracker = MinionTracker(self._names)
        self._window_state = WindowPersistence()

    def draw(self) -> None:
        self._window_state.apply_initial_state()

        opened = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
        collapsed = PyImGui.is_window_collapsed()
        position = PyImGui.get_window_pos()

        if opened:
            self._tracker.refresh()
            rows = self._tracker.rows
            if rows:
                self._render_table(rows)
            else:
                _text_disabled("No party minions found.")

        PyImGui.end()
        self._window_state.persist(position, collapsed)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_table(self, rows: Sequence[MinionRow]) -> None:
        flags = (
            PyImGui.TableFlags.Borders
            | PyImGui.TableFlags.RowBg
            | PyImGui.TableFlags.SizingFixedFit
            | PyImGui.TableFlags.Resizable
        )

        if not PyImGui.begin_table("party_minions_table", 6, flags):
            return

        PyImGui.table_setup_column("ID", PyImGui.TableColumnFlags.WidthFixed, 70)
        PyImGui.table_setup_column("Name", PyImGui.TableColumnFlags.WidthFixed, 220)
        PyImGui.table_setup_column("Lv", PyImGui.TableColumnFlags.WidthFixed, 40)
        PyImGui.table_setup_column("HP%", PyImGui.TableColumnFlags.WidthFixed, 60)
        PyImGui.table_setup_column("Dist Me", PyImGui.TableColumnFlags.WidthFixed, 70)
        PyImGui.table_setup_column("", PyImGui.TableColumnFlags.WidthFixed, 70)
        PyImGui.table_headers_row()

        player_xy = self._player_xy()

        for row in rows:
            PyImGui.table_next_row()

            PyImGui.table_next_column()
            if row.is_target:
                PyImGui.text_colored(str(row.agent_id), TARGET_ID_COLOR)
            else:
                PyImGui.text(str(row.agent_id))

            PyImGui.table_next_column()
            if row.is_target:
                PyImGui.text_colored(row.name, TARGET_NAME_COLOR)
            else:
                PyImGui.text(row.name)

            PyImGui.table_next_column()
            PyImGui.text(f"{row.level}")

            PyImGui.table_next_column()
            PyImGui.text_colored(f"{row.hp_pct:4.0f}%", _hp_color(row.hp_pct))

            PyImGui.table_next_column()
            PyImGui.text(f"{row.distance_from(player_xy):4d}")

            PyImGui.table_next_column()
            if _tiny_button(f"Target##{row.agent_id}", width=60):
                try:
                    Player.ChangeTarget(row.agent_id)
                except Exception:
                    pass

        PyImGui.end_table()

    @staticmethod
    def _player_xy() -> Optional[Tuple[float, float]]:
        try:
            coords = Player.GetXY()
            if isinstance(coords, Sequence) and len(coords) >= 2:
                return float(coords[0]), float(coords[1])
        except Exception:
            pass
        return None


_widget_instance = PartyMinionsWidget()


def configure() -> None:
    """Widget configuration hook (required by widget loader)."""
    # The widget currently has no user-configurable options.
    return None


def draw_widget() -> None:
    _widget_instance.draw()


def main() -> None:
    try:
        if not Routines.Checks.Map.MapValid():
            return
        draw_widget()
    except Exception as exc:  # pragma: no cover - guard against GUI crashes
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
