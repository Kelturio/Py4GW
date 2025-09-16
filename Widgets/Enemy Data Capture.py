# Widgets/Enemy Data Capture.py

import os
import time
import math
import json
import traceback

import Py4GW  # type: ignore
from HeroAI.cache_data import CacheData
from Py4GWCoreLib import PyImGui, Routines, Timer, Utils, AgentArray, Agent, Player, Map
from Py4GWCoreLib.enums import outposts, explorables

"""
Enemy Data Capture Widget
- Collects enemy positions *outside* aggro range to approximate spawn points/patrols.
- Runs independently of any bot; works in all zones (outposts + explorables).
- Auto-detects map change and starts a new NDJSON file automatically.
- File layout (no region folder): Py4GW/Bots/aC_Scripts/PyQuishAI_data/<MapName>/run-<timestamp>-map<id>.ndjson

SETUP CHECKLIST (once):
 - Add this widget's defaults to Widgets//widget_manager//default_settings.py (done in your previous step).
 - Add an entry to Py4GW.ini to enable it (done in your previous step).
"""

# --------------------------------------------------------------------------------------
# Paths & INI persistence
# --------------------------------------------------------------------------------------

script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))

first_run = True

# Where the capture files will be stored (as requested)
DATA_DIR = os.path.join(project_root, "Bots", "aC_Scripts", "PyQuishAI_data")

# Store window layout here
INI_BASE_DIR = os.path.join(project_root, "Widgets", "Config")
os.makedirs(INI_BASE_DIR, exist_ok=True)
INI_WIDGET_WINDOW_PATH = os.path.join(INI_BASE_DIR, "Enemy Data Capture.ini")

from Py4GWCoreLib import IniHandler  # late import to keep header tidy
ini_window = IniHandler(INI_WIDGET_WINDOW_PATH)
save_window_timer = Timer()
save_window_timer.Start()

# String consts
MODULE_NAME = "Enemy Data Capture"
COLLAPSED = "collapsed"
X_POS = "x"
Y_POS = "y"

# load last‐saved window state (fallback to 100,100 / un-collapsed)
window_x = ini_window.read_int(MODULE_NAME, X_POS, 100)
window_y = ini_window.read_int(MODULE_NAME, Y_POS, 100)
window_collapsed = ini_window.read_bool(MODULE_NAME, COLLAPSED, False)

cached_data = CacheData()

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def _try_agent_attr(method_name, agent_id):
    """Safely call Agent.<method>(agent_id) if it exists; else return None."""
    try:
        if hasattr(Agent, method_name):
            return getattr(Agent, method_name)(agent_id)
    except Exception:
        pass
    return None

def _dist_xy(a, b):
    try:
        return Utils.Distance(a, b)
    except Exception:
        try:
            ax, ay = a
            bx, by = b
            dx = float(ax) - float(bx)
            dy = float(ay) - float(by)
            return (dx * dx + dy * dy) ** 0.5
        except Exception:
            return 0.0

def _resolve_map_name(map_id):
    """Resolve a human-friendly map name from enums; fallback to 'map_<id>'."""
    try:
        mid = int(map_id)
    except Exception:
        return f"map_{map_id}"
    name = explorables.get(mid) or outposts.get(mid)
    if isinstance(name, str) and name:
        return name
    return f"map_{mid}"

def _normalize_name(name):
    if name is None:
        return None
    try:
        s = str(name).replace("\x00", "").strip()
        return s if s else None
    except Exception:
        return None

# --------------------------------------------------------------------------------------
# Collector
# --------------------------------------------------------------------------------------

class EnemyObservationCollector:
    """
    Writes newline-delimited JSON (NDJSON) per run & per map for easy post-processing.
    - Independent of bot state.
    - Works in outposts & explorables.
    - Rolls over on map change automatically.

    Name stabilization:
      Only logs an enemy record when the agent's name has been the SAME for the
      last N successful reads (default N=3). This avoids transient/invalid names
      right after zoning when names are still loading.
    """
    def __init__(self):
        self.enabled = False
        self.sample_interval_ms = 1000
        self.min_move_delta = 200              # don't re-log if agent hasn't moved ~>200 units
        self.max_buffer = 200                  # flush to disk every N records
        self._timer = Timer()
        self._buffer = []
        self._last_pos_by_agent = {}           # agent_id -> (x,y)
        self._run_id = None
        self._file_path = None
        self._total_written = 0
        self._started = False
        self._last_flush_time = time.time()
        self._flush_interval_sec = 15          # also flush by time
        self._current_aggro_range = 2500

        # Name stabilization config/state
        self.name_required_matches = 3         # N: consecutive identical names needed
        self._name_track = {}                  # agent_id -> (last_name, consecutive_count)

        # Metadata (used only for file organization)
        self.map_id = None
        self.map_name = ""
        self.segment_index = None  # optional, if a pathing FSM is present
        self._last_map_id_for_file = None

        # Ensure base dir
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
        except Exception as e:
            Py4GW.Console.Log(MODULE_NAME, f"[Data] Could not create data dir: {e}", Py4GW.Console.MessageType.Error)

    # ------------- Name utilities -------------

    def _request_name_if_possible(self, agent_id):
        """Best-effort: ask the client to resolve a name for this agent."""
        try:
            if hasattr(Agent, "RequestName"):
                Agent.RequestName(agent_id)
        except Exception:
            pass

    def _is_name_ready(self, agent_id):
        """If API supports readiness, respect it; otherwise assume ready."""
        try:
            if hasattr(Agent, "IsNameReady"):
                return bool(Agent.IsNameReady(agent_id))
        except Exception:
            pass
        return True

    def _read_name_if_ready(self, agent_id):
        """Return a normalized name if available & ready; else None."""
        self._request_name_if_possible(agent_id)
        if not self._is_name_ready(agent_id):
            return None
        name = None
        try:
            if hasattr(Agent, "GetName"):
                name = Agent.GetName(agent_id)
        except Exception:
            name = None
        if name is None:
            name = _try_agent_attr("GetName", agent_id)
        return _normalize_name(name)

    def _require_stable_name(self, agent_id):
        """
        Update per-agent name stability and return a stable name iff we have
        seen the same non-empty name for name_required_matches consecutive reads.
        """
        name = self._read_name_if_ready(agent_id)
        if name is None:
            # Do not penalize; simply skip logging until a non-empty name is available.
            return None

        last_name, count = self._name_track.get(agent_id, (None, 0))
        if name == last_name:
            count += 1
        else:
            last_name = name
            count = 1
        self._name_track[agent_id] = (last_name, count)

        if count >= max(1, int(self.name_required_matches)):
            return name
        return None

    # ------------- General config -------------

    def set_aggro_range(self, r):
        try:
            r = int(r)
            if r > 0:
                self._current_aggro_range = r
        except Exception:
            pass

    def begin_run(self, map_id=None):
        """Prepare a per-run file and reset counters. Map name is resolved from enums."""
        try:
            self.map_id = int(map_id) if map_id is not None else int(Map.GetMapID())
        except Exception:
            self.map_id = Map.GetMapID()

        self.map_name = _resolve_map_name(self.map_id)
        ts = time.strftime("%Y%m%d-%H%M%S")
        self._run_id = f"{ts}-map{self.map_id}"

        # Folder per map name (no region subfolder)
        safe_map = str(self.map_name).replace(os.sep, "_") or f"map_{self.map_id}"
        run_dir = os.path.join(DATA_DIR, safe_map)
        try:
            os.makedirs(run_dir, exist_ok=True)
        except Exception as e:
            Py4GW.Console.Log(MODULE_NAME, f"[Data] Could not create run dir: {e}", Py4GW.Console.MessageType.Error)

        self._file_path = os.path.join(run_dir, f"run-{self._run_id}.ndjson")
        self._buffer.clear()
        self._last_pos_by_agent.clear()
        self._name_track.clear()               # reset name history on new run
        self._total_written = 0
        self._started = True
        self._timer.Reset()
        self._last_flush_time = time.time()
        self._last_map_id_for_file = self.map_id
        Py4GW.Console.Log(MODULE_NAME, f"[Data] Started run capture -> {_shorten_path(self._file_path)}", Py4GW.Console.MessageType.Info)

    def end_run(self):
        """Flush and end."""
        if not self._started:
            return
        self.flush()
        Py4GW.Console.Log(MODULE_NAME, f"[Data] Ended run. Total written: {self._total_written}", Py4GW.Console.MessageType.Info)
        self._started = False

    def _ensure_run(self):
        """Ensure we have a file to write to based on the *current* map context."""
        if not self._started:
            current_map_id = None
            try:
                current_map_id = Map.GetMapID()
            except Exception:
                pass
            self.begin_run(current_map_id)

    def _record(self, rec):
        self._buffer.append(rec)
        if len(self._buffer) >= self.max_buffer or (time.time() - self._last_flush_time) >= self._flush_interval_sec:
            self.flush()

    def flush(self):
        """Write buffered records to disk."""
        if not self._file_path or not self._buffer:
            self._last_flush_time = time.time()
            return
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                for r in self._buffer:
                    f.write(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n")
            self._total_written += len(self._buffer)
        except Exception as e:
            Py4GW.Console.Log(MODULE_NAME, f"[Data] Flush error: {e}", Py4GW.Console.MessageType.Error)
        finally:
            self._buffer.clear()
            self._last_flush_time = time.time()

    def update_context(self):
        """Optionally pick up a path index & aggro setting if an FSM exists."""
        try:
            # If a bot FSM is present and exposes a current index, capture it (best-effort).
            fsm = globals().get("FSM_vars", None)
            if fsm and getattr(fsm, "path_and_aggro", None):
                idx = fsm.path_and_aggro.get_current_index()
                if isinstance(idx, int):
                    self.segment_index = idx
                if hasattr(fsm.path_and_aggro, "aggro_range"):
                    self._current_aggro_range = int(fsm.path_and_aggro.aggro_range)
        except Exception:
            pass

    def _handle_map_rollover_if_needed(self):
        """Detect map change at any time and rollover to a new file automatically."""
        try:
            current_map_id = Map.GetMapID()
        except Exception:
            return
        if self._last_map_id_for_file is not None and current_map_id != self._last_map_id_for_file:
            # rollover: end previous, start new with resolved name
            self.end_run()
            self.begin_run(current_map_id)

    def update(self):
        """Periodic sampling. Should be called every frame/tick; throttles internally."""
        if not self.enabled:
            return

        # Always ensure a run context and detect map changes
        self._ensure_run()
        self._handle_map_rollover_if_needed()
        self.update_context()

        # sample throttle
        if not self._timer.HasElapsed(self.sample_interval_ms):
            return

        try:
            px, py = Player.GetXY()
        except Exception:
            px, py = 0, 0
        player_xy = (int(px), int(py))
        now = time.time()

        try:
            enemies = list(AgentArray.GetEnemyArray())
        except Exception:
            enemies = []

        for e in enemies:
            try:
                # Normalize agent id
                agent_id = None
                try:
                    if hasattr(Agent, "GetIdFromAgent"):
                        agent_id = Agent.GetIdFromAgent(e)
                except Exception:
                    agent_id = None
                if agent_id is None:
                    agent_id = int(e)

                # Liveness & position
                if not Agent.IsAlive(agent_id):
                    continue
                ex, ey = Agent.GetXY(agent_id)
                ex, ey = int(ex), int(ey)
                if ex == 0 and ey == 0:
                    continue
                
                # Name must be stable for N consecutive identical reads
                stable_name = self._require_stable_name(agent_id)
                if stable_name is None:
                    continue

                # Aggro filter
                if _dist_xy(player_xy, (ex, ey)) <= self._current_aggro_range:
                    continue

                # Dedup by small movements
                last = self._last_pos_by_agent.get(agent_id)
                if last is not None and _dist_xy(last, (ex, ey)) < self.min_move_delta:
                    continue
                self._last_pos_by_agent[agent_id] = (ex, ey)

                # Other enrichment (best-effort)
                model_id = _try_agent_attr("GetModelID", agent_id)
                level = _try_agent_attr("GetLevel", agent_id)
                hp = _try_agent_attr("GetHealth", agent_id)
                if hp is None or hp < 0.99:
                    continue

                rec = {
                    "ts": now,
                    "player": {"x": player_xy[0], "y": player_xy[1]},
                    "path_idx": self.segment_index,
                    "enemy": {
                        "agent_id": agent_id,
                        "model_id": model_id,
                        "name": stable_name,
                        "level": level
                    },
                    "pos": {"x": ex, "y": ey}
                }
                self._record(rec)

            except Exception:
                continue

        self._timer.Reset()

# --------------------------------------------------------------------------------------
# Small util
# --------------------------------------------------------------------------------------

def _shorten_path(p):
    try:
        base = os.path.basename(p)
        parent = os.path.basename(os.path.dirname(p))
        return f".../{parent}/{base}"
    except Exception:
        return p

# Single global collector instance
collector = EnemyObservationCollector()

# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------

def draw_widget(_cached_data: CacheData):
    global window_x, window_y, window_collapsed, first_run

    if first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        first_run = False

    is_window_opened = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
    new_collapsed = PyImGui.is_window_collapsed()
    end_pos = PyImGui.get_window_pos()

    if is_window_opened:
        # Toggle + Flush
        en_label = "On" if collector.enabled else "Off"
        if PyImGui.button(f"{en_label}##capture_toggle", width=40):
            collector.enabled = not collector.enabled
            if collector.enabled:
                collector._ensure_run()
        PyImGui.same_line(0, 8)
        if PyImGui.button("Flush", width=50):
            collector.flush()

        # Live stats
        PyImGui.text(f"Buffered: {len(collector._buffer)}   Written: {collector._total_written}")

        # Controls
        PyImGui.push_item_width(120)
        cur = collector._current_aggro_range
        new_aggro = PyImGui.input_int("Aggro", cur, 100, 500, 0)
        PyImGui.pop_item_width()
        if new_aggro != cur and new_aggro > 0:
            collector.set_aggro_range(new_aggro)

        PyImGui.push_item_width(120)
        cur_int = collector.sample_interval_ms
        new_int = PyImGui.input_int("Interval(ms)", cur_int, 100, 500, 0)
        PyImGui.pop_item_width()
        if new_int != cur_int and new_int >= 100:
            collector.sample_interval_ms = new_int

        PyImGui.push_item_width(120)
        cur_move = collector.min_move_delta
        new_move = PyImGui.input_int("MinMove", cur_move, 10, 200, 0)
        PyImGui.pop_item_width()
        if new_move != cur_move and new_move >= 0:
            collector.min_move_delta = new_move

        PyImGui.push_item_width(120)
        cur_stab = collector.name_required_matches
        new_stab = PyImGui.input_int("Name stable N", cur_stab, 1, 2, 0)
        PyImGui.pop_item_width()
        if new_stab != cur_stab and new_stab >= 1:
            collector.name_required_matches = int(new_stab)

    PyImGui.end()

    # Persist window state occasionally
    if save_window_timer.HasElapsed(1000):
        # Position changed?
        if end_pos and (int(end_pos[0]), int(end_pos[1])) != (window_x, window_y):
            window_x, window_y = int(end_pos[0]), int(end_pos[1])
            ini_window.write_key(MODULE_NAME, X_POS, str(window_x))
            ini_window.write_key(MODULE_NAME, Y_POS, str(window_y))
        # Collapsed state changed?
        if new_collapsed != window_collapsed:
            window_collapsed = new_collapsed
            ini_window.write_key(MODULE_NAME, COLLAPSED, str(window_collapsed))
        save_window_timer.Reset()

# --------------------------------------------------------------------------------------
# Widget lifecycle
# --------------------------------------------------------------------------------------

def configure():
    pass

def main():
    global cached_data
    try:
        if not Routines.Checks.Map.MapValid():
            return

        cached_data.Update()

        # Always run the collector, independent of UI state
        collector.update()

        if Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded():
            draw_widget(cached_data)

    except ImportError as e:
        Py4GW.Console.Log(MODULE_NAME, f"ImportError encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    except ValueError as e:
        Py4GW.Console.Log(MODULE_NAME, f"ValueError encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    except TypeError as e:
        Py4GW.Console.Log(MODULE_NAME, f"TypeError encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    except Exception as e:
        Py4GW.Console.Log(MODULE_NAME, f"Unexpected error encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    finally:
        pass


if __name__ == "__main__":
    main()
