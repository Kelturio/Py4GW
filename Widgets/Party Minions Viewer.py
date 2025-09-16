# Widgets/Party Minions Viewer.py

import os
import math
import time
import traceback

import Py4GW  # type: ignore
from Py4GWCoreLib import (
    PyImGui, Routines, Timer, Utils,
    AgentArray, Agent, Player, Map, Color
)

"""
Party Minions Viewer
- Lists all party minions in a compact, stable-height table.
- Columns: ID, Name (sticky), Lv, HP%, Dist Me, [Target].
- Names are cached so they don't flicker between '#id' and the real name.
- Sorted by minion age (oldest first, newest last).
"""

# --------------------------------------------------------------------------------------
# Window persistence
# --------------------------------------------------------------------------------------

script_directory = os.path.dirname(os.path.abspath(__file__))
project_root     = os.path.abspath(os.path.join(script_directory, os.pardir))

INI_BASE_DIR = os.path.join(project_root, "Widgets", "Config")
os.makedirs(INI_BASE_DIR, exist_ok=True)
INI_WIDGET_WINDOW_PATH = os.path.join(INI_BASE_DIR, "Party Minions Viewer.ini")

from Py4GWCoreLib import IniHandler
ini_window = IniHandler(INI_WIDGET_WINDOW_PATH)

MODULE_NAME = "Party Minions Viewer"
X_POS, Y_POS, COLLAPSED = "x", "y", "collapsed"

_first_run        = True
_save_window_tick = Timer(); _save_window_tick.Start()
_window_x         = ini_window.read_int(MODULE_NAME, X_POS, 120)
_window_y         = ini_window.read_int(MODULE_NAME, Y_POS, 120)
_window_collapsed = ini_window.read_bool(MODULE_NAME, COLLAPSED, False)

# --------------------------------------------------------------------------------------
# Colors & helpers
# --------------------------------------------------------------------------------------

ok_color  = Color( 92, 184,  92, 255).to_tuple_normalized()
bad_color = Color(200,  80,  80, 255).to_tuple_normalized()

def _dist_xy(a, b):
    try:
        return Utils.Distance(a, b)
    except Exception:
        try:
            ax, ay = a; bx, by = b
            return math.hypot(float(ax) - float(bx), float(ay) - float(by))
        except Exception:
            return 0.0

def _hp_pct(agent_id: int) -> float:
    try:
        hp = float(Agent.GetHealth(agent_id))
        if 0.0 <= hp <= 1.1:
            return max(0.0, min(100.0, hp * 100.0))
        mx = float(max(1.0, Agent.GetMaxHealth(agent_id)))
        return max(0.0, min(100.0, (hp / mx) * 100.0))
    except Exception:
        return 0.0

# --------------------------------------------------------------------------------------
# Sticky name cache (prevents flicker)
# --------------------------------------------------------------------------------------

class _NameCache:
    """
    Caches first valid name per agent. Never downgrades back to '#id'.
    Throttles RequestName to at most once per second per agent.
    """
    def __init__(self):
        self._cache: dict[int, str] = {}
        self._last_req: dict[int, float] = {}
        self._req_interval = 1.0  # seconds

    @staticmethod
    def _sanitize(n):
        if isinstance(n, str):
            return n.replace("\x00", "").strip()
        return str(n)

    def get(self, agent_id: int) -> str:
        if agent_id in self._cache:
            return self._cache[agent_id]

        now = time.time()
        last = self._last_req.get(agent_id, 0.0)
        if now - last >= self._req_interval:
            try:
                Agent.RequestName(agent_id)
            except Exception:
                pass
            self._last_req[agent_id] = now

        try:
            if Agent.IsNameReady(agent_id):
                n = self._sanitize(Agent.GetName(agent_id))
                if n:
                    self._cache[agent_id] = n
                    return n
        except Exception:
            pass

        return f"#{agent_id}"

_name_cache = _NameCache()

# --------------------------------------------------------------------------------------
# Core model (flat list of minions, age-tracked)
# --------------------------------------------------------------------------------------

class PartyMinionsModel:
    def __init__(self):
        self._throttle = Timer(); self._throttle.Reset()
        self.refresh_ms = 500  # doubled from 250 → 500ms
        self._minions: list[int] = []
        self._first_seen: dict[int, float] = {}  # id -> timestamp first observed

    def _minion_ids(self) -> list[int]:
        try:
            arr = list(AgentArray.GetMinionArray())
            if arr:
                return arr
        except Exception:
            pass
        try:
            return [a for a in AgentArray.GetAgentArray() if Agent.IsMinion(a)]
        except Exception:
            return []

    def refresh(self):
        if not self._throttle.HasElapsed(self.refresh_ms):
            return
        self._throttle.Reset()

        current = []
        now = time.time()

        for m in self._minion_ids():
            try:
                if m and Agent.IsAlive(m) and Agent.IsMinion(m):
                    current.append(m)
                    self._first_seen.setdefault(m, now)  # record once
            except Exception:
                continue

        # prune ages for despawned minions
        current_set = set(current)
        for mid in list(self._first_seen.keys()):
            if mid not in current_set:
                self._first_seen.pop(mid, None)

        # sort by age: oldest first, newest last
        current.sort(key=lambda mid: self._first_seen.get(mid, 0.0))
        self._minions = current

    @property
    def minions(self) -> list[int]:
        return list(self._minions)

model = PartyMinionsModel()

# --------------------------------------------------------------------------------------
# Tiny button helper (keeps row height small)
# --------------------------------------------------------------------------------------

def _tiny_button(label: str, width: int = 70) -> bool:
    # Prefer SmallButton if available
    if hasattr(PyImGui, "small_button"):
        return PyImGui.small_button(label)
    # Fallback: reduce vertical padding around a normal button
    try:
        PyImGui.push_style_var(PyImGui.ImGuiStyleVar.FramePadding, (4, 1))
        clicked = PyImGui.button(label, width=width)
        PyImGui.pop_style_var(1)
        return clicked
    except Exception:
        return PyImGui.button(label, width=width)

# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------

def _draw_row(mid: int, player_xy):
    try:
        name   = _name_cache.get(mid)
        lvl    = int(Agent.GetLevel(mid) or 0)
        hpct   = _hp_pct(mid)
        mx, my = Agent.GetXY(mid)
        d_me   = int(_dist_xy(player_xy, (mx, my)))

        PyImGui.table_next_row()
        PyImGui.table_next_column(); PyImGui.text(str(mid))
        PyImGui.table_next_column(); PyImGui.text(name)
        PyImGui.table_next_column(); PyImGui.text(str(lvl))
        PyImGui.table_next_column()
        col = ok_color if hpct >= 50 else bad_color
        PyImGui.text_colored(f"{hpct:4.0f}%", col)
        PyImGui.table_next_column(); PyImGui.text(f"{d_me:4d}")
        PyImGui.table_next_column()
        if _tiny_button(f"Target##{mid}", width=60):
            try:
                Player.ChangeTarget(mid)
            except Exception:
                pass
    except Exception:
        pass

def draw_widget():
    global _first_run, _window_x, _window_y, _window_collapsed

    if _first_run:
        PyImGui.set_next_window_pos(_window_x, _window_y)
        PyImGui.set_next_window_collapsed(_window_collapsed, 0)
        _first_run = False

    opened = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
    new_collapsed = PyImGui.is_window_collapsed()
    pos = PyImGui.get_window_pos()

    if opened:
        # Auto-refresh data
        model.refresh()

        # Table only (no header/controls/empty text)
        flags = (PyImGui.TableFlags.Borders
                 | PyImGui.TableFlags.RowBg
                 | PyImGui.TableFlags.SizingFixedFit
                 | PyImGui.TableFlags.Resizable)

        if PyImGui.begin_table("party_minions_table", 6, flags):
            PyImGui.table_setup_column("ID",       PyImGui.TableColumnFlags.WidthFixed, 70)
            PyImGui.table_setup_column("Name",     PyImGui.TableColumnFlags.WidthFixed, 220)
            PyImGui.table_setup_column("Lv",       PyImGui.TableColumnFlags.WidthFixed, 40)
            PyImGui.table_setup_column("HP%",      PyImGui.TableColumnFlags.WidthFixed, 60)
            PyImGui.table_setup_column("Dist Me",  PyImGui.TableColumnFlags.WidthFixed, 70)
            PyImGui.table_setup_column("",         PyImGui.TableColumnFlags.WidthFixed, 70)
            PyImGui.table_headers_row()

            try:
                px, py = Player.GetXY()
            except Exception:
                px, py = 0, 0

            for mid in model.minions:
                _draw_row(mid, (px, py))

            PyImGui.end_table()

    PyImGui.end()

    # Persist window state occasionally
    if _save_window_tick.HasElapsed(1000):
        try:
            if pos and (int(pos[0]) != _window_x or int(pos[1]) != _window_y):
                _window_x, _window_y = int(pos[0]), int(pos[1])
                ini_window.write_key(MODULE_NAME, X_POS, str(_window_x))
                ini_window.write_key(MODULE_NAME, Y_POS, str(_window_y))
            if new_collapsed != _window_collapsed:
                _window_collapsed = new_collapsed
                ini_window.write_key(MODULE_NAME, COLLAPSED, str(_window_collapsed))
        finally:
            _save_window_tick.Reset()

# --------------------------------------------------------------------------------------
# Widget lifecycle
# --------------------------------------------------------------------------------------

def configure():
    pass

def main():
    try:
        if not Routines.Checks.Map.MapValid():
            return
        draw_widget()
    except Exception as e:
        Py4GW.Console.Log(MODULE_NAME, f"Unexpected error: {e}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)

if __name__ == "__main__":
    main()
