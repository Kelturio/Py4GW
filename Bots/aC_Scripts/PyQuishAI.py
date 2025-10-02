from Py4GWCoreLib import *
from Widgets.Blessed import Get_Blessed
from aC_api import *
from HeroAI.cache_data import *
import time
import math
import os
import importlib.util
import random
from aC_api.Blessing_Core import get_blessing_npc
from aC_api.Titles import (
    display_title_track, display_faction, display_title_progress,
    vanguard_tiers, norn_tiers, asura_tiers, deldrimor_tiers,
    sunspear_tiers, lightbringer_tiers, kurzick_tiers, luxon_tiers,
    luxon_regions, kurzick_regions, nightfall_regions, eotn_region_titles
)

module_name = "PyQuishAI "
cache_data = CacheData()

RECHECK_INTERVAL_MS = 500 # Used for followpathandaggro
ARRIVAL_TOLERANCE = 250  # Used for path point arrival

# NEW: Auto-load selected map script
MAPS_DIR = "PyQuishAI_maps"

# Default placeholders (used if no dynamic script is selected)
OUTPOST_ID = 389
MAP_ID = 200
MAX_COMPASS_RANGE = int(Range.Compass.value)
outpost_path = []
map_path = []

combat_handler = SkillManager.Autocombat()

class FSMVars:
    def __init__(self):
        self.global_combat_fsm = FSM("Global Combat Monitor")
        self.global_combat_handler = FSM("Interruptible Combat")
        self.state_machine = FSM("MainStateMachine")
        self.movement_handler = Routines.Movement.FollowXY()
        self.exact_movement_handler = Routines.Movement.FollowXY(tolerance=500)
        self.outpost_pathing = Routines.Movement.PathHandler(outpost_path)
        self.explorable_pathing = Routines.Movement.PathHandler(map_path)
        self.path_and_aggro = None  # set after map load

        self.chest_found_pathing = None
        self.loot_chest = FSM("LootChestStateMachine")
        self.sell_to_vendor = FSM("VendorStateMachine")
        self._current_path_point = None
        self.non_movement_timer = Timer()
        self.auto_stuck_command_timer = Timer()
        self.old_player_x = 0
        self.old_player_y = 0
        self.stuck_count = 0
        self.in_waiting_routine = False
        self.in_killing_routine = False
        self.last_skill_time = 0
        self.current_skill = 1
        self.blessing_timer = Timer()
        self.has_blessing = False
        self.in_blessing_dialog = False
        self.get_blessing_delay_start = None
        self.blessing_points = []
        self.blessing_triggered = set()
        self.blessing_timers = {}
        # Waypoint cache for UI/controls
        self.explorable_waypoints = []

class BotVars:
    def __init__(self):
        # Make the window resizable by removing AlwaysAutoResize
        self.window_module = ImGui.WindowModule(
            module_name,
            window_name="MQVQ Bot",
            window_size=(420, 560),
            window_flags=0  # resizable via corner drag
        )
        self.is_running = False
        self.is_paused = False
        self.starting_map = OUTPOST_ID
        self.combat_started = False
        self.pause_combat_fsm = False
        self.global_timer = Timer()
        self.lap_timer = Timer()
        self.lap_history = []
        self.min_time = 0
        self.max_time = 0
        self.avg_time = 0.0
        self.runs_attempted = 0
        self.runs_completed = 0
        self.success_rate = 0.0
        self.selected_region = ""
        self.selected_map = ""
        self.map_data = {}  # stores map_path, outpost_path, ids, etc.
        self.aggro_range = 2500

        # UI collapse state
        self.show_controls = True
        self.show_map_select = True
        self.show_state = True
        self.show_stats = True
        self.show_titles = True
        self.force_close_map_select = False

        # Segment detail toggles (per loaded map)
        self.segment_open = {}           # {seg_index: bool}
        self.show_outpost_list = False   # toggle listing outpost waypoints
        self.show_merged_list = False    # toggle listing merged explorable WPs

        # Movement behaviour tweaks
        self.use_waypoint_jitter = True
        self.waypoint_jitter_amount = 100

        # Debug UI helpers (see Debug Tools section in DrawWindow)
        self.debug_enabled = False
        self.debug_state_filter = ""
        self.debug_force_index_input = ""
        self.debug_recent_error = ""

def trigger_blessing_at(point):
    if point in FSM_vars.blessing_triggered:
        return

    if point not in FSM_vars.blessing_timers:
        FSM_vars.blessing_timers[point] = time.time()
        return

    if time.time() - FSM_vars.blessing_timers[point] < 5.0:
        return

    ConsoleLog("Blessing", f"Triggering blessing at {point}", Console.MessageType.Info)
    Get_Blessed()
    FSM_vars.blessing_triggered.add(point)

# -----------------------------------------------
# Helpers to introspect / sync PathHandler indices
# -----------------------------------------------

def _get_waypoints_from_handler(ph):
    """Try to pull the underlying waypoint list from a PathHandler-like object."""
    for name in ('waypoints', 'path', 'points', '_waypoints', '_path', '_points'):
        if hasattr(ph, name):
            lst = getattr(ph, name)
            if isinstance(lst, (list, tuple)):
                return list(lst)
    # Fallback: if the handler exposes a getter
    for name in ('get_waypoints', 'get_path', 'get_points'):
        if hasattr(ph, name):
            try:
                lst = getattr(ph, name)()
                if isinstance(lst, (list, tuple)):
                    return list(lst)
            except Exception:
                pass
    return []

def _get_index_from_handler(ph):
    """Best-effort current index lookup from a PathHandler-like object."""
    for name in ('index', 'idx', 'current_index', '_index', '_current_index'):
        if hasattr(ph, name):
            try:
                val = int(getattr(ph, name))
                return val
            except Exception:
                pass
    return None

def _set_index_on_handler(ph, idx):
    """Try to set the internal index on PathHandler; if not possible, return False."""
    # Prefer a setter if present
    for name in ('set_index', 'SetIndex'):
        if hasattr(ph, name):
            try:
                getattr(ph, name)(int(idx))
                return True
            except Exception:
                pass
    # Try known field names
    for name in ('index', 'idx', 'current_index', '_index', '_current_index'):
        if hasattr(ph, name):
            try:
                setattr(ph, name, int(idx))
                return True
            except Exception:
                pass
    return False

def _clamp(n, low, high):
    return max(low, min(high, n))

def _safe_read(label, supplier, fallback="-"):
    """Utility for debug UI to swallow access errors without spamming the console."""
    try:
        return label, supplier()
    except Exception:
        return label, fallback

# -----------------------------------------------
# Map/segment helpers (for UI and controls)
# -----------------------------------------------

def _compute_map_stats():
    """Return a dict with friendly counts for UI."""
    md = bot_vars.map_data or {}
    map_path = md.get("map_path", [])
    outpost_path_local = md.get("outpost_path", [])
    stats = {
        "region": bot_vars.selected_region or "",
        "map_name": bot_vars.selected_map or "",
        "map_id": md.get("map_id", MAP_ID),
        "outpost_id": md.get("outpost_id", OUTPOST_ID),
        "segments": 0,
        "segments_wp_counts": [],
        "explorable_wp_total": len(FSM_vars.explorable_waypoints) if FSM_vars.explorable_waypoints else 0,
        "outpost_wp_total": len(outpost_path_local) if isinstance(outpost_path_local, list) else 0,
        "bless_count": len(FSM_vars.blessing_points) if FSM_vars.blessing_points else 0,
        "bless_preview": [],
    }

    if isinstance(map_path, list) and all(isinstance(x, dict) for x in map_path):
        stats["segments"] = len(map_path)
        for seg in map_path:
            pts = seg.get("path", []) or []
            stats["segments_wp_counts"].append(len(pts))
    elif isinstance(map_path, list):
        # flat list of waypoints — treat as one segment
        stats["segments"] = 1 if map_path else 0
        stats["segments_wp_counts"] = [len(map_path)] if map_path else []

    # bless preview (up to first 5)
    if FSM_vars.blessing_points:
        try:
            preview = [tuple(map(int, (x, y))) for (x, y) in FSM_vars.blessing_points[:5]]
        except Exception:
            preview = FSM_vars.blessing_points[:5]
        stats["bless_preview"] = preview

    return stats

def _segment_base_index(map_path, seg_idx):
    """Return the global index offset for a given segment index."""
    if not (isinstance(map_path, list) and all(isinstance(x, dict) for x in map_path)):
        return 0
    total = 0
    for k in range(seg_idx):
        pts = map_path[k].get("path", []) or []
        total += len(pts)
    return total

class FollowPathAndAggro:
    def __init__(self, path_handler, follow_handler, aggro_range=2500, log_actions=False, waypoints=None):
        self.path_handler       = path_handler
        self.follow_handler     = follow_handler
        self.aggro_range        = aggro_range
        self.log_actions        = log_actions
        self._last_scanned_enemy = None
        # ── THROTTLING STATE ───────────────────────────────────────────
        self._scan_move_thresh   = max(0, aggro_range * 0.75)
        self._last_scan_pos      = Player.GetXY()
        self._scan_interval_ms   = 500
        self._enemy_scan_timer   = Timer()
        self._last_target_id     = None
        self._last_move_target   = None
        self._stats_start_time      = time.time()
        self.enemy_array_fetches    = 0
        self.change_target_calls    = 0
        self.move_calls             = 0
        self._stats_interval_secs   = 30.0

        self._last_enemy_check      = Timer()
        self._current_target_enemy  = None
        self._mode                  = 'path'
        self._current_path_point    = None
        self._current_command_point = None
        self.status_message         = "Waiting to begin..."

        # Waypoint cache + debug controls
        self._external_waypoints = list(waypoints) if waypoints else []
        self._forced_index = None        # one-shot command target
        self._debug_hold   = False       # if True, do not auto-advance

    # --- Debug control API ---
    def enable_hold(self): self._debug_hold = True
    def release_hold(self):
        self._debug_hold = False
        self._forced_index = None

    def set_active_index(self, idx):
        """Set the internal active waypoint index without forcing immediate movement."""
        wps = self.get_waypoints()
        if not wps:
            self.status_message = "No waypoints available."
            return False
        idx = _clamp(idx, 0, len(wps) - 1)
        _set_index_on_handler(self.path_handler, idx)
        # Clear any pending forced move and HOLD; next tick will use advance() from this index.
        self._forced_index = None
        self.release_hold()
        self._current_path_point = None
        self._current_command_point = None
        self.follow_handler._following = False
        self.follow_handler.arrived = False
        self.status_message = f"[DEBUG] Set active index to {idx+1}/{len(wps)}"
        if self.log_actions:
            ConsoleLog("FollowPathAndAggro", self.status_message, Console.MessageType.Info)
        return True

    # ------------- Waypoint Debug Utilities -----------------

    def get_waypoints(self):
        # Prefer explicit cache
        if self._external_waypoints:
            return self._external_waypoints
        # Try handler
        wps = _get_waypoints_from_handler(self.path_handler)
        if wps:
            return wps
        # Last resort: FSM cache (set at map load)
        if FSM_vars.explorable_waypoints:
            return FSM_vars.explorable_waypoints
        return []

    def get_current_waypoint(self):
        if self._current_path_point is not None:
            return self._current_path_point
        # Fallback: nearest to player for display if we haven't moved yet
        wps = self.get_waypoints()
        if wps:
            try:
                px, py = Player.GetXY()
                idx = min(range(len(wps)), key=lambda i: Utils.Distance((px, py), wps[i]))
                return wps[idx]
            except Exception:
                pass
        return None

    def get_current_index(self):
        """Best-effort current index: forced index -> handler -> from current point -> nearest."""
        if isinstance(self._forced_index, int):
            return _clamp(self._forced_index, 0, max(0, len(self.get_waypoints()) - 1))
        idx = _get_index_from_handler(self.path_handler)
        if isinstance(idx, int):
            return idx
        wps = self.get_waypoints()
        if self._current_path_point in wps:
            return wps.index(self._current_path_point)
        if wps:
            try:
                px, py = Player.GetXY()
                return min(range(len(wps)), key=lambda i: Utils.Distance((px, py), wps[i]))
            except Exception:
                pass
        return None

    def force_move_to_index(self, idx, sticky=True):
        """Jump to a waypoint index for debugging. If sticky=True, enter HOLD mode."""
        wps = self.get_waypoints()
        if not wps:
            self.status_message = "No waypoints available."
            return False
        idx = _clamp(idx, 0, len(wps) - 1)
        pt = wps[idx]
        _set_index_on_handler(self.path_handler, idx)  # best-effort sync
        self._forced_index = idx
        if sticky:
            self.enable_hold()
        # Move now; do not auto-increment
        self.follow_handler._following = False
        self.follow_handler.arrived = False
        self._current_path_point = pt
        issued = self._issue_move_command(pt)
        target_label = self._format_move_target(pt, issued)
        self.status_message = (
            f"[DEBUG] Forced move -> wp {idx+1}/{len(wps)} {target_label}"
            + (" [HOLD]" if self._debug_hold else "")
        )
        if self.log_actions:
            ConsoleLog("FollowPathAndAggro", self.status_message, Console.MessageType.Warning)
        return True

    def seek_relative(self, delta, sticky=True):
        """Move to next/prev waypoint relative to the current one (defaults to HOLD)."""
        wps = self.get_waypoints()
        if not wps:
            self.status_message = "No waypoints to seek."
            return False
        cur_idx = self.get_current_index()
        if cur_idx is None:
            cur_idx = 0
        new_idx = _clamp(cur_idx + delta, 0, len(wps) - 1)
        return self.force_move_to_index(new_idx, sticky=sticky)

    def set_aggro_range(self, aggro_range):
        try:
            aggro_range = int(aggro_range)
        except (TypeError, ValueError):
            return
        aggro_range = max(0, aggro_range)
        if aggro_range == self.aggro_range:
            return
        self.aggro_range = aggro_range
        self._scan_move_thresh = max(0, aggro_range * 0.75)

    # --------------------------------------------------------

    def _apply_waypoint_jitter(self, point):
        """Return a potentially offset version of the supplied waypoint."""
        if not point:
            return point
        if not getattr(bot_vars, "use_waypoint_jitter", False):
            return (int(point[0]), int(point[1])) if isinstance(point, (tuple, list)) else point

        jitter_radius = max(0, int(getattr(bot_vars, "waypoint_jitter_amount", 0)))
        if jitter_radius <= 0:
            return (int(point[0]), int(point[1])) if isinstance(point, (tuple, list)) else point

        try:
            x, y = point
        except (TypeError, ValueError):
            return point

        offset_x = random.randint(-jitter_radius, jitter_radius)
        offset_y = random.randint(-jitter_radius, jitter_radius)
        return (int(x) + offset_x, int(y) + offset_y)

    def _issue_move_command(self, waypoint):
        """Apply jitter (if enabled) and send the move command to the handler."""
        if waypoint is None:
            self._current_command_point = None
            return None

        if isinstance(waypoint, (tuple, list)) and len(waypoint) >= 2:
            target = self._apply_waypoint_jitter(waypoint)
        else:
            target = waypoint

        if isinstance(target, (tuple, list)) and len(target) >= 2:
            target = (int(target[0]), int(target[1]))

        self._current_command_point = target
        try:
            self.follow_handler.move_to_waypoint(*target)
        except TypeError:
            # Fallback if the handler expects a tuple/list only
            self.follow_handler.move_to_waypoint(target)
        self.move_calls += 1
        return target

    # --------------------------------------------------------

    def _format_move_target(self, original, issued):
        """Format a status label showing the original waypoint and any applied jitter."""
        try:
            orig_tuple = (int(original[0]), int(original[1]))
        except Exception:
            return str(issued if issued is not None else original)

        if isinstance(issued, (tuple, list)) and len(issued) >= 2:
            issued_tuple = (int(issued[0]), int(issued[1]))
            if issued_tuple != orig_tuple:
                return f"{orig_tuple} -> {issued_tuple}"
            return str(orig_tuple)

        return str(orig_tuple)

    # --------------------------------------------------------

    def _throttled_scan(self):
        curr_pos   = Player.GetXY()
        dist_moved = Utils.Distance(curr_pos, self._last_scan_pos)

        if (dist_moved >= self._scan_move_thresh
                or self._enemy_scan_timer.HasElapsed(self._scan_interval_ms)):
            self._last_scanned_enemy = self._find_nearest_enemy()
            self._last_scan_pos      = curr_pos
            self._enemy_scan_timer.Reset()

        return self._last_scanned_enemy

    def _find_nearest_enemy(self):
        self.enemy_array_fetches += 1
        my_pos = Player.GetXY()
        enemies = [
            e for e in AgentArray.GetEnemyArray()
            if Agent.IsAlive(e) and Utils.Distance(my_pos, Agent.GetXY(e)) <= self.aggro_range
        ]
        if not enemies:
            return None
        return AgentArray.Sort.ByDistance(enemies, my_pos)[0]

    def _advance_to_next_point(self):
        wps = self.get_waypoints()

        # HOLD mode: do not advance automatically.
        if self._debug_hold:
            if self._forced_index is not None and wps:
                idx = _clamp(self._forced_index, 0, len(wps) - 1)
                next_point = wps[idx]
                _set_index_on_handler(self.path_handler, idx)
                self._current_path_point = next_point
                issued = self._issue_move_command(next_point)
                target_label = self._format_move_target(next_point, issued)
                self.status_message = f"[DEBUG] Holding at wp {idx+1}/{len(wps)} {target_label} [HOLD]"
                self._forced_index = None
            return

        # One-shot forced move when NOT holding
        if self._forced_index is not None and wps:
            idx = _clamp(self._forced_index, 0, len(wps) - 1)
            next_point = wps[idx]
            _set_index_on_handler(self.path_handler, idx)
            self._current_path_point = next_point
            issued = self._issue_move_command(next_point)
            target_label = self._format_move_target(next_point, issued)
            self.status_message = f"[DEBUG] Moving to wp {idx+1}/{len(wps)} {target_label}"
            self._forced_index = None
            return

        if not self.follow_handler.is_following():
            next_point = self.path_handler.advance()
            if not next_point:
                self.status_message = "No valid next waypoint! Stopping pathing."
                if self.log_actions:
                    ConsoleLog("FollowPathAndAggro", "PathHandler returned None – halting movement.", Console.MessageType.Warning)
                self._current_command_point = None
                if hasattr(self.path_handler, "reset"):
                    self.path_handler.reset()
                    retry_point = self.path_handler.advance()
                    if retry_point:
                        self._current_path_point = retry_point
                        issued = self._issue_move_command(retry_point)
                        target_label = self._format_move_target(retry_point, issued)
                        self.status_message = f"Path reset -> moving to {target_label}"
                        ConsoleLog("FollowPathAndAggro", f"Path reset after failure, moving to {target_label}", Console.MessageType.Warning)
                return

            self._current_path_point = next_point
            issued = self._issue_move_command(next_point)
            target_label = self._format_move_target(next_point, issued)
            self.status_message = f"Moving to {target_label}"
            if self.log_actions:
                ConsoleLog("FollowPathAndAggro", f"Moving to {target_label}", Console.MessageType.Info)
        else:
            if not self._current_path_point:
                self.status_message = "Lost current path point, hang on a second"
                self.follow_handler._following = False
                self._current_command_point = None
                return
            px, py = Player.GetXY()
            target_point = self._current_command_point or self._current_path_point
            if target_point:
                tx, ty = target_point
            else:
                tx, ty = self._current_path_point
            if Utils.Distance((px, py), (tx, ty)) <= ARRIVAL_TOLERANCE:
                self.follow_handler._following = False
                self.follow_handler.arrived    = True
                self.status_message            = "Arrived at waypoint."
                self._current_command_point    = None

    def _maybe_log_stats(self):
        elapsed = time.time() - self._stats_start_time
        if elapsed >= self._stats_interval_secs:
            ConsoleLog(
                "FollowPathAndAggro",
                f"[Stats over {int(elapsed)}s] fetches={self.enemy_array_fetches}, "
                f"changeTarget={self.change_target_calls}, move={self.move_calls}",
                Console.MessageType.Info
            )
            self._stats_start_time     = time.time()
            self.enemy_array_fetches   = 0
            self.change_target_calls   = 0
            self.move_calls            = 0

    def update(self):
        self._maybe_log_stats()

        if CacheData().in_looting_routine:
            self.status_message = "Waiting for looting to finish..."
            self.follow_handler.update()
            return

        # Mid-map blessing trigger
        if FSM_vars.blessing_points:
            px, py = Player.GetXY()
            for point in FSM_vars.blessing_points:
                if point in FSM_vars.blessing_triggered:
                    continue
                if Utils.Distance((px, py), point) < 2500:
                    self.status_message = f"Near blessing point {point}"
                    trigger_blessing_at(point)
                    break

        if self._mode == 'path':
            target = self._throttled_scan()
            if target:
                self._current_target_enemy = target
                self._last_enemy_check.Reset()
                self._mode = 'combat'
                self.status_message = "Switching to combat mode."
                if self.log_actions:
                    ConsoleLog("FollowPathAndAggro", "Switching to COMBAT mode", Console.MessageType.Warning)
            else:
                self._advance_to_next_point()

        elif self._mode == 'combat':
            if not self._current_target_enemy or not Agent.IsAlive(self._current_target_enemy):
                self._mode                  = 'path'
                self._current_target_enemy  = None
                self.status_message         = "Combat done. Switching to path mode."
                return

            self._current_target_enemy = self._throttled_scan()
            if not self._current_target_enemy:
                self._mode = 'path'
                self.status_message = "No enemies (throttled)—returning to path."
                return

            try:
                tx, ty = Agent.GetXY(self._current_target_enemy)
            except Exception:
                self._mode                 = 'path'
                self._current_target_enemy = None
                self.status_message        = "Enemy fetch failed. Returning to path."
                return

            if self._current_target_enemy != self._last_target_id:
                Player.ChangeTarget(self._current_target_enemy)
                self.change_target_calls += 1
                self._last_target_id = self._current_target_enemy

            new_move = (int(tx), int(ty))
            if new_move != self._last_move_target:
                Player.Move(*new_move)
                self.move_calls += 1
                self._last_move_target = new_move

            self.status_message = f"Closing in on enemy at ({int(tx)}, {int(ty)})"

        self.follow_handler.update()

def load_map_script():
    region_path = os.path.join(MAPS_DIR, bot_vars.selected_region)
    map_file = os.path.join(region_path, f"{bot_vars.selected_map}.py")
    if not os.path.exists(map_file):
        ConsoleLog(module_name, f"[ERROR] Map script not found: {map_file}", Console.MessageType.Error)
        return

    spec = importlib.util.spec_from_file_location(bot_vars.selected_map, map_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    data = getattr(mod, bot_vars.selected_map, [])
    outpost = getattr(mod, f"{bot_vars.selected_map}_outpost_path", [])
    ids = getattr(mod, f"{bot_vars.selected_map}_ids", {})

    # Blessing points detection
    bless_points = []
    if isinstance(data, list):
        for segment in data:
            if isinstance(segment, dict) and "bless" in segment:
                bless_points.append(segment["bless"])

    # Merge to a flat, explorable waypoint list and cache it
    merged = merge_map_segments(data)
    FSM_vars.explorable_waypoints = list(merged) if merged else []

    bot_vars.map_data = {
        "map_path": data,
        "outpost_path": outpost,
        "outpost_id": ids.get("outpost_id", OUTPOST_ID),
        "map_id": ids.get("map_id", MAP_ID),
    }

    # Reset per-segment open states
    bot_vars.segment_open = {}
    if isinstance(data, list) and all(isinstance(x, dict) for x in data):
        for i in range(len(data)):
            bot_vars.segment_open[i] = False
    elif isinstance(data, list) and data:
        bot_vars.segment_open[0] = False

    bot_vars.show_outpost_list = False
    bot_vars.show_merged_list = False

    FSM_vars.blessing_points = bless_points
    FSM_vars.outpost_pathing = Routines.Movement.PathHandler(bot_vars.map_data["outpost_path"])
    FSM_vars.explorable_pathing = Routines.Movement.PathHandler(FSM_vars.explorable_waypoints)

    # Rebuild FollowPathAndAggro with reliable waypoint cache
    FSM_vars.path_and_aggro = FollowPathAndAggro(
        FSM_vars.explorable_pathing,
        FSM_vars.movement_handler,
        aggro_range=bot_vars.aggro_range,
        log_actions=True,
        waypoints=FSM_vars.explorable_waypoints
    )
    bot_vars.starting_map = bot_vars.map_data["outpost_id"]

def merge_map_segments(data):
    if isinstance(data, list) and all(isinstance(x, dict) for x in data):
        all_coords = []
        for segment in data:
            all_coords.extend(segment.get("path", []))
        return all_coords
    elif isinstance(data, list):
        return data
    return []

# Add combat control functions

def check_combat():
    return Routines.Checks.Agents.InDanger(Range.Area)

def start_combat():
    bot_vars.combat_started = True

def stop_combat():
    bot_vars.combat_started = False


def ensure_hard_mode_enabled():
    if Map.IsMapLoading():
        return

    if not GLOBAL_CACHE.Party.IsHardModeUnlocked():
        return

    if GLOBAL_CACHE.Party.IsHardMode():
        return

    GLOBAL_CACHE.Party.SetHardMode()


def pause_all(debug: bool = False):
    if not check_combat():
        return
    if not FSM_vars.state_machine.is_paused():
        if debug: ConsoleLog("FSM", "[DEBUG] Pausing Main FSM", Console.MessageType.Warning)
        FSM_vars.state_machine.pause()
    FSM_vars.movement_handler.pause()

def resume_all(debug: bool = False):
    if check_combat():
        return
    if FSM_vars.state_machine.is_paused():
        if debug:
            ConsoleLog("FSM", "[DEBUG] Resuming Main FSM", Console.MessageType.Warning)
        FSM_vars.state_machine.resume()
    FSM_vars.movement_handler.resume()

# Modify InitializeStateMachine
def InitializeStateMachine():
    # Combat FSM setup
    FSM_vars.global_combat_fsm.SetLogBehavior(False)
    FSM_vars.global_combat_fsm.AddState(
        name="Check: In Danger",
        execute_fn=lambda: pause_all(),
        exit_condition=check_combat,
        run_once=False)
    FSM_vars.global_combat_fsm.AddSubroutine(
        name="Combat: Execute Global",
        condition_fn=lambda: check_combat(),
        sub_fsm=FSM_vars.global_combat_handler)
    FSM_vars.global_combat_fsm.AddState(
        name="Resume: Main FSM",
        execute_fn=lambda: resume_all(),
        exit_condition=lambda: not check_combat(),
        run_once=False)

    FSM_vars.global_combat_handler.SetLogBehavior(False)
    FSM_vars.global_combat_handler.AddState(
        name="Combat: Wait Safe",
        execute_fn=lambda: None,
        exit_condition=lambda: not check_combat(),
        run_once=False)
    FSM_vars.global_combat_handler.AddState(
        name="Combat: Stop",
        execute_fn=lambda: stop_combat(),
        exit_condition=lambda: True)

    # Primary flow states
    FSM_vars.state_machine.AddState(
        name="Check Current Map",
        execute_fn= lambda: Routines.Transition.TravelToOutpost(bot_vars.starting_map),
        exit_condition= lambda: Routines.Transition.HasArrivedToOutpost(bot_vars.starting_map),
        transition_delay_ms=1000
    )
    FSM_vars.state_machine.AddState(
        name="Wait For Map Load",
        exit_condition=lambda: not Map.IsMapLoading(),
        transition_delay_ms=1000
    )
    FSM_vars.state_machine.AddState(
        name="Ensure Hard Mode",
        execute_fn=ensure_hard_mode_enabled,
        exit_condition=lambda: (
            not GLOBAL_CACHE.Party.IsHardModeUnlocked()
            or GLOBAL_CACHE.Party.IsHardMode()
        ),
        transition_delay_ms=1000,
        run_once=True
    )
    FSM_vars.state_machine.AddState(
        name="Navigate Outpost",
        execute_fn=lambda: Routines.Movement.FollowPath(
            FSM_vars.outpost_pathing, FSM_vars.movement_handler
        ),
        exit_condition=lambda: (
            Routines.Movement.IsFollowPathFinished(FSM_vars.outpost_pathing, FSM_vars.movement_handler)
            or Map.IsExplorable()
        ),
        run_once=False
    )
    FSM_vars.state_machine.AddState(
        name="Wait For Explorable Load",
        exit_condition=lambda: not Map.IsMapLoading() and Map.IsExplorable(),
        transition_delay_ms=1000
    )
    FSM_vars.state_machine.AddState(
        name="Initial Auto-Blessing",
        execute_fn=lambda: Get_Blessed(),
        exit_condition=lambda: has_any_blessing(Player.GetAgentID()) or Map.IsMapLoading() or (get_blessing_npc()[0] is None),
        transition_delay_ms=5000,
        run_once=True
    )
    FSM_vars.state_machine.AddState(
        name="Combat and Movement",
        execute_fn=lambda: FSM_vars.path_and_aggro.update(),
        exit_condition=lambda: Routines.Movement.IsFollowPathFinished(FSM_vars.explorable_pathing, FSM_vars.movement_handler),
        run_once=False
    )

def ResetEnvironment():
    FSM_vars.outpost_pathing.reset()
    FSM_vars.explorable_pathing.reset()
    FSM_vars.blessing_triggered.clear()
    FSM_vars.blessing_timers.clear()
    FSM_vars.movement_handler.reset()
    if bot_vars.combat_started:
        stop_combat()

# --------------------------------------------------------------------------------------------------
# THEME COLORS
# --------------------------------------------------------------------------------------------------

window_bg_color       = Color(28,  28,  28, 230).to_tuple_normalized()
frame_bg_color        = Color(48,  48,  48, 230).to_tuple_normalized()
frame_hover_color     = Color(68,  68,  68, 230).to_tuple_normalized()
frame_active_color    = Color(58,  58,  58, 230).to_tuple_normalized()
body_text_color       = Color(139, 131, 99, 255).to_tuple_normalized()
disabled_text_color   = Color(140, 140, 140, 255).to_tuple_normalized()
separator_color       = Color(90,  90,  90, 255).to_tuple_normalized()
header_color          = Color(136, 117, 44, 255).to_tuple_normalized()
icon_color            = Color(177, 152, 55, 255).to_tuple_normalized()
neutral_button        = Color(33, 51, 58, 255).to_tuple_normalized()
neutral_button_hover  = Color(140, 140, 140, 255).to_tuple_normalized()
neutral_button_active = Color( 90,  90,  90, 255).to_tuple_normalized()
header_bg_color       = Color(33, 51, 58, 255).to_tuple_normalized()
header_hover_color    = Color(33, 51, 58, 255).to_tuple_normalized()
header_active_color   = Color(95, 145,  95, 255).to_tuple_normalized()

# --------------------------------------------------------------------------------------------------
# DrawWindow() WITH COLLAPSIBLE SECTIONS + WAYPOINT CONTROLS + COMPACT BUTTONS + RESIZABLE WINDOW
# --------------------------------------------------------------------------------------------------

def DrawWindow():
    # Remove AlwaysAutoResize to allow manual corner drag resizing
    if not PyImGui.begin(module_name):
        PyImGui.end()
        return

    PyImGui.push_style_color(PyImGui.ImGuiCol.WindowBg,       window_bg_color)
    PyImGui.push_style_color(PyImGui.ImGuiCol.FrameBg,        frame_bg_color)
    PyImGui.push_style_color(PyImGui.ImGuiCol.FrameBgHovered, frame_hover_color)
    PyImGui.push_style_color(PyImGui.ImGuiCol.FrameBgActive,  frame_active_color)
    PyImGui.push_style_color(PyImGui.ImGuiCol.Text,           body_text_color)
    PyImGui.push_style_color(PyImGui.ImGuiCol.Separator,      separator_color)
    PyImGui.push_style_color(PyImGui.ImGuiCol.Header,         header_bg_color)
    PyImGui.push_style_color(PyImGui.ImGuiCol.HeaderHovered,  header_hover_color)
    PyImGui.push_style_color(PyImGui.ImGuiCol.HeaderActive,   header_active_color)
    PyImGui.push_style_color(PyImGui.ImGuiCol.Button,         neutral_button)
    PyImGui.push_style_color(PyImGui.ImGuiCol.ButtonHovered,  neutral_button_hover)
    PyImGui.push_style_color(PyImGui.ImGuiCol.ButtonActive,   neutral_button_active)

    # ====== Run Controls (compact) ======
    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    run_controls_open = PyImGui.collapsing_header(
        f"{IconsFontAwesome5.ICON_ROBOT} Run Controls",
        PyImGui.TreeNodeFlags.DefaultOpen
    )
    PyImGui.pop_style_color(1)
    if run_controls_open:
        # Start/Stop (compact)
        btn_label = IconsFontAwesome5.ICON_PLAY if not bot_vars.is_running else IconsFontAwesome5.ICON_STOP
        if PyImGui.button(btn_label, width=26):
            if not bot_vars.is_running:
                StartBot()
                bot_vars.show_map_select = False
                bot_vars.force_close_map_select = True
            else:
                StopBot()
        if PyImGui.is_item_hovered():
            tooltip = "Start bot" if not bot_vars.is_running else "Stop bot"
            PyImGui.set_tooltip(tooltip)

        # Pause (compact)
        PyImGui.same_line(0, 4)
        pause_icon = IconsFontAwesome5.ICON_PAUSE if not bot_vars.is_paused else IconsFontAwesome5.ICON_PLAY
        if not bot_vars.is_running:
            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, disabled_text_color)
            PyImGui.button(pause_icon, width=26)
            PyImGui.pop_style_color(1)
            if PyImGui.is_item_hovered():
                PyImGui.set_tooltip("Pause/Resume bot (unavailable while stopped)")
        else:
            if PyImGui.button(pause_icon, width=26):
                TogglePause()
            if PyImGui.is_item_hovered():
                tooltip = "Resume bot" if bot_vars.is_paused else "Pause bot"
                PyImGui.set_tooltip(tooltip)

        # Hold toggle (compact)
        PyImGui.same_line(0, 4)
        hold_on = bool(FSM_vars.path_and_aggro and FSM_vars.path_and_aggro._debug_hold)
        hold_label = IconsFontAwesome5.ICON_UNLOCK if hold_on else IconsFontAwesome5.ICON_HAND
        if PyImGui.button(hold_label, width=26):
            if FSM_vars.path_and_aggro:
                if hold_on:
                    FSM_vars.path_and_aggro.release_hold()
                else:
                    FSM_vars.path_and_aggro.enable_hold()
        if PyImGui.is_item_hovered():
            tooltip = "Release hold" if hold_on else "Hold current waypoint"
            PyImGui.set_tooltip(tooltip)

        # Waypoint navigation controls (compact)
        PyImGui.same_line(0, 4)
        if PyImGui.button(IconsFontAwesome5.ICON_ARROW_LEFT, width=22):
            if FSM_vars.path_and_aggro:
                FSM_vars.path_and_aggro.seek_relative(-1, sticky=True)
        if PyImGui.is_item_hovered():
            PyImGui.set_tooltip("Previous waypoint")

        PyImGui.same_line(0, 2)
        if PyImGui.button(IconsFontAwesome5.ICON_ARROW_RIGHT, width=22):
            if FSM_vars.path_and_aggro:
                FSM_vars.path_and_aggro.seek_relative(+1, sticky=True)
        if PyImGui.is_item_hovered():
            PyImGui.set_tooltip("Next waypoint")

        PyImGui.separator()

        # Waypoint bar + aggro controls
        wps = FSM_vars.path_and_aggro.get_waypoints() if FSM_vars.path_and_aggro else []
        cur_pt = FSM_vars.path_and_aggro.get_current_waypoint() if FSM_vars.path_and_aggro else None
        cur_idx = FSM_vars.path_and_aggro.get_current_index() if FSM_vars.path_and_aggro else None

        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text(f"{IconsFontAwesome5.ICON_BULLSEYE} Aggro Range")
        PyImGui.pop_style_color(1)

        PyImGui.same_line(0, 6)
        PyImGui.push_item_width(200)
        new_aggro = PyImGui.slider_int("##aggro_range_slider", bot_vars.aggro_range, 500, MAX_COMPASS_RANGE)
        PyImGui.pop_item_width()
        rounded_aggro = int(((new_aggro + 50) // 100) * 100)
        rounded_aggro = max(500, min(MAX_COMPASS_RANGE, rounded_aggro))
        if rounded_aggro != bot_vars.aggro_range:
            bot_vars.aggro_range = rounded_aggro
            if FSM_vars.path_and_aggro:
                FSM_vars.path_and_aggro.set_aggro_range(rounded_aggro)

        PyImGui.separator()

        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("Active WP:")
        PyImGui.pop_style_color(1)

        PyImGui.same_line(0, 4)
        if cur_pt is not None and wps:
            total = len(wps)
            idx_display = (cur_idx + 1) if isinstance(cur_idx, int) else "?"
            try:
                x, y = int(cur_pt[0]), int(cur_pt[1])
                hold_tag = " [HOLD]" if hold_on else ""
                PyImGui.text(f"{idx_display}/{total} ({x},{y}){hold_tag}")
            except Exception:
                PyImGui.text(f"{idx_display}/{total} {cur_pt}{' [HOLD]' if hold_on else ''}")
        else:
            PyImGui.text("(none)")

        PyImGui.separator()
        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        movement_tweaks_open = PyImGui.collapsing_header(
            f"{IconsFontAwesome5.ICON_SLIDERS_H} Movement Tweaks",
            PyImGui.TreeNodeFlags.DefaultOpen
        )
        PyImGui.pop_style_color(1)
        if movement_tweaks_open:
            bot_vars.use_waypoint_jitter = PyImGui.checkbox("Randomize waypoint targets", bot_vars.use_waypoint_jitter)
            jitter_value = int(PyImGui.slider_int(
                "Jitter radius (units)",
                int(bot_vars.waypoint_jitter_amount),
                0,
                200
            ))
            rounded_jitter = int(((jitter_value + 5) // 10) * 10)
            rounded_jitter = max(0, min(200, rounded_jitter))
            if rounded_jitter != bot_vars.waypoint_jitter_amount:
                bot_vars.waypoint_jitter_amount = rounded_jitter

        PyImGui.separator()
        bot_vars.debug_enabled = PyImGui.checkbox("Show Debug Tools", bot_vars.debug_enabled)

    # ====== Map Selection ======
    if bot_vars.force_close_map_select:
        PyImGui.set_next_item_open(False, PyImGui.ImGuiCond.Always)
        bot_vars.force_close_map_select = False
    else:
        PyImGui.set_next_item_open(bot_vars.show_map_select, PyImGui.ImGuiCond.Once)

    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    map_select_open = PyImGui.collapsing_header(
        f"{IconsFontAwesome5.ICON_GLOBE_EUROPE} Select Region / Map",
        PyImGui.TreeNodeFlags.DefaultOpen
    )
    PyImGui.pop_style_color(1)
    bot_vars.show_map_select = map_select_open
    if map_select_open:
        regions = []
        if os.path.isdir(MAPS_DIR):
            regions = sorted(
                [d for d in os.listdir(MAPS_DIR) if os.path.isdir(os.path.join(MAPS_DIR, d))]
            )

        if regions:
            region_index = regions.index(bot_vars.selected_region) if bot_vars.selected_region in regions else 0
            region_index = PyImGui.combo("##Region", region_index, regions)
            if region_index < len(regions):
                new_region = regions[region_index]
                if bot_vars.selected_region != new_region:
                    bot_vars.selected_region = new_region
                    bot_vars.selected_map = ""
        else:
            if bot_vars.selected_region:
                bot_vars.selected_region = ""
            if bot_vars.selected_map:
                bot_vars.selected_map = ""
            PyImGui.text("No map regions found")

        if bot_vars.selected_region:
            region_path = os.path.join(MAPS_DIR, bot_vars.selected_region)
            maps = []
            if os.path.isdir(region_path):
                maps = sorted([
                    f[:-3] for f in os.listdir(region_path)
                    if f.endswith(".py")
                ])

            if maps:
                map_index = maps.index(bot_vars.selected_map) if bot_vars.selected_map in maps else 0
                map_index = PyImGui.combo("##Map", map_index, maps)
                if map_index < len(maps):
                    new_map = maps[map_index]
                    if bot_vars.selected_map != new_map:
                        bot_vars.selected_map = new_map
                        load_map_script()
            else:
                if bot_vars.selected_map:
                    bot_vars.selected_map = ""
                PyImGui.text("No map scripts found")

    # ====== Current State ======
    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    current_state_open = PyImGui.collapsing_header(
        f"{IconsFontAwesome5.ICON_INFO_CIRCLE} Current State",
        PyImGui.TreeNodeFlags.DefaultOpen
    )
    PyImGui.pop_style_color(1)
    if current_state_open:
        current_state = FSM_vars.state_machine.get_current_step_name()
        PyImGui.text(f"{current_state}")
        if current_state == "Combat and Movement" and FSM_vars.path_and_aggro:
            PyImGui.text(f"> {FSM_vars.path_and_aggro.status_message}")

    # ====== Statistics ======
    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    metrics_open = PyImGui.collapsing_header(
        f"{IconsFontAwesome5.ICON_LIST_ALT} Run Metrics",
        PyImGui.TreeNodeFlags.DefaultOpen
    )
    PyImGui.pop_style_color(1)
    if metrics_open:
        if bot_vars.is_running:
            total_elapsed = FormatTime(bot_vars.global_timer.GetElapsedTime(), 'hh:mm:ss')
            current_elapsed = FormatTime(bot_vars.lap_timer.GetElapsedTime(), 'mm:ss')
            PyImGui.text(
                f"{IconsFontAwesome5.ICON_STOPWATCH} Total: {total_elapsed} | Current: {current_elapsed}"
            )
            draw_vanquish_status("Vanquish Progress")

        if bot_vars.runs_attempted > 0:
            PyImGui.text(f"Runs Attempted: {bot_vars.runs_attempted}")
            PyImGui.text(f"Runs Completed: {bot_vars.runs_completed}")
            PyImGui.text(f"Success Rate: {bot_vars.success_rate * 100:.1f}%")
            if bot_vars.lap_history:
                PyImGui.text(f"Best Time: {FormatTime(bot_vars.min_time, 'mm:ss')}")
                PyImGui.text(f"Worst Time: {FormatTime(bot_vars.max_time, 'mm:ss')}")
                PyImGui.text(f"Average Time: {FormatTime(bot_vars.avg_time, 'mm:ss')}")

    # ====== Titles / Allegiance ======
    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    titles_open = PyImGui.collapsing_header(
        f"{IconsFontAwesome5.ICON_TROPHY} Title Progress",
        PyImGui.TreeNodeFlags.DefaultOpen
    )
    PyImGui.pop_style_color(1)
    if titles_open:
        region = bot_vars.selected_region
        if region in kurzick_regions:
            display_faction("Kurzick", 5, Player.GetKurzickData, kurzick_tiers)
        elif region in luxon_regions:
            display_faction("Luxon", 6, Player.GetLuxonData, luxon_tiers)
        elif region in nightfall_regions:
            display_title_progress("Sunspear Title", 17, sunspear_tiers)
            display_title_progress("Lightbringer Title", 20, lightbringer_tiers)
        elif region in eotn_region_titles:
            for title_id, title_name, tier_data in eotn_region_titles[region]:
                display_title_progress(title_name, title_id, tier_data)

    # ====== Loaded Script Info ======
    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    loaded_info_open = PyImGui.collapsing_header(
        f"{IconsFontAwesome5.ICON_MAP} Loaded Script Info",
        0
    )
    PyImGui.pop_style_color(1)
    if loaded_info_open:
        stats = _compute_map_stats()

        # Map IDs
        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("MapID / OutpostID:")
        PyImGui.pop_style_color(1)
        PyImGui.same_line(0, 6)
        PyImGui.text(f"{stats['map_id']} / {stats['outpost_id']}")

        # Totals
        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("Segments:")
        PyImGui.pop_style_color(1)
        PyImGui.same_line(0, 6)
        PyImGui.text(str(stats["segments"]))

        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("Outpost WPs:")
        PyImGui.pop_style_color(1)
        PyImGui.same_line(0, 6)
        PyImGui.text(str(stats["outpost_wp_total"]))

        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("Explorable WPs (merged):")
        PyImGui.pop_style_color(1)
        PyImGui.same_line(0, 6)
        PyImGui.text(str(stats["explorable_wp_total"]))

        # Per-segment quick counts
        if stats["segments_wp_counts"]:
            PyImGui.separator()
            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
            PyImGui.text("Per-Segment Waypoints:")
            PyImGui.pop_style_color(1)
            for i, cnt in enumerate(stats["segments_wp_counts"], start=1):
                PyImGui.text(f"- Segment {i}: {cnt}")

        # Segment open/close controls and details WITH per-waypoint controls
        map_path = bot_vars.map_data.get("map_path", [])
        if isinstance(map_path, list) and map_path:
            PyImGui.separator()
            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
            PyImGui.text("Segment Details:")
            PyImGui.pop_style_color(1)

            if all(isinstance(x, dict) for x in map_path):
                for i, seg in enumerate(map_path):
                    pts = seg.get("path", []) or []
                    bless_raw = seg.get("bless", None)
                    # Normalize bless list per segment
                    bless_list = []
                    if bless_raw is not None:
                        if isinstance(bless_raw, (list, tuple)) and bless_raw and isinstance(bless_raw[0], (list, tuple)):
                            bless_list = list(bless_raw)
                        else:
                            bless_list = [bless_raw]

                    # Header line with toggle
                    PyImGui.text(f"Segment {i+1}: {len(pts)} WPs" + (f", Bless: {len(bless_list)}" if bless_list else ""))

                    PyImGui.same_line(0, 12)
                    is_open = bool(bot_vars.segment_open.get(i, False))
                    btn_lbl = "Close" if is_open else "Open"
                    if PyImGui.button(f"{btn_lbl}##seg{i}", width=60):
                        bot_vars.segment_open[i] = not is_open
                        is_open = not is_open

                    # Details if open
                    if is_open:
                        # Waypoints list with controls
                        if pts:
                            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
                            PyImGui.text("  Waypoints:")
                            PyImGui.pop_style_color(1)
                            base_idx = _segment_base_index(map_path, i)
                            for j, p in enumerate(pts, start=1):
                                try:
                                    x, y = int(p[0]), int(p[1])
                                    PyImGui.text(f"  - WP {j}: ({x},{y})")
                                except Exception:
                                    PyImGui.text(f"  - WP {j}: {p}")
                                # Buttons: Go (move to & HOLD) and Set (set active index)
                                PyImGui.same_line(0, 6)
                                global_idx = base_idx + (j - 1)
                                if PyImGui.button(f">##go_{i}_{j}", width=20):
                                    if FSM_vars.path_and_aggro:
                                        FSM_vars.path_and_aggro.force_move_to_index(global_idx, sticky=True)
                                PyImGui.same_line(0, 2)
                                if PyImGui.button(f"I##set_{i}_{j}", width=18):
                                    if FSM_vars.path_and_aggro:
                                        FSM_vars.path_and_aggro.set_active_index(global_idx)
                        else:
                            PyImGui.text("  - (no waypoints)")

                        # Bless list
                        if bless_list:
                            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
                            PyImGui.text("  Bless Points:")
                            PyImGui.pop_style_color(1)
                            for b in bless_list:
                                try:
                                    bx, by = int(b[0]), int(b[1])
                                    PyImGui.text(f"  - ({bx},{by})")
                                except Exception:
                                    PyImGui.text(f"  - {b}")

            else:
                # Flat path: treat as one segment with optional open toggle at index 0
                pts = map_path
                PyImGui.text(f"Segment 1: {len(pts)} WPs")
                PyImGui.same_line(0, 12)
                is_open = bool(bot_vars.segment_open.get(0, False))
                btn_lbl = "Close" if is_open else "Open"
                if PyImGui.button(f"{btn_lbl}##seg0", width=60):
                    bot_vars.segment_open[0] = not is_open
                    is_open = not is_open
                if is_open:
                    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
                    PyImGui.text("  Waypoints:")
                    PyImGui.pop_style_color(1)
                    for j, p in enumerate(pts, start=1):
                        try:
                            x, y = int(p[0]), int(p[1])
                            PyImGui.text(f"  - WP {j}: ({x},{y})")
                        except Exception:
                            PyImGui.text(f"  - WP {j}: {p}")
                        # Buttons for flat list (global index = j-1)
                        PyImGui.same_line(0, 6)
                        global_idx = j - 1
                        if PyImGui.button(f">##go_flat_{j}", width=20):
                            if FSM_vars.path_and_aggro:
                                FSM_vars.path_and_aggro.force_move_to_index(global_idx, sticky=True)
                        PyImGui.same_line(0, 2)
                        if PyImGui.button(f"I##set_flat_{j}", width=18):
                            if FSM_vars.path_and_aggro:
                                FSM_vars.path_and_aggro.set_active_index(global_idx)

        # Bless points summary + preview
        PyImGui.separator()
        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("Bless Points (all):")
        PyImGui.pop_style_color(1)
        PyImGui.same_line(0, 6)
        PyImGui.text(str(stats["bless_count"]))
        if stats["bless_preview"]:
            for bp in stats["bless_preview"]:
                try:
                    x, y = int(bp[0]), int(bp[1])
                    PyImGui.text(f"- ({x},{y})")
                except Exception:
                    PyImGui.text(f"- {bp}")

        # Optional lists: Outpost path and merged exp path
        PyImGui.separator()
        out_btn = "Hide Outpost Path" if bot_vars.show_outpost_list else "Show Outpost Path"
        if PyImGui.button(out_btn, width=140):
            bot_vars.show_outpost_list = not bot_vars.show_outpost_list
        PyImGui.same_line(0, 8)
        exp_btn = "Hide Merged WPs" if bot_vars.show_merged_list else "Show Merged WPs"
        if PyImGui.button(exp_btn, width=140):
            bot_vars.show_merged_list = not bot_vars.show_merged_list

        if bot_vars.show_outpost_list:
            out_pts = bot_vars.map_data.get("outpost_path", []) or []
            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
            PyImGui.text("Outpost Path:")
            PyImGui.pop_style_color(1)
            if out_pts:
                for j, p in enumerate(out_pts, start=1):
                    try:
                        x, y = int(p[0]), int(p[1])
                        PyImGui.text(f"- OP {j}: ({x},{y})")
                    except Exception:
                        PyImGui.text(f"- OP {j}: {p}")
            else:
                PyImGui.text("- (empty)")

        if bot_vars.show_merged_list:
            merged_pts = FSM_vars.explorable_waypoints or []
            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
            PyImGui.text("Explorable (merged) Waypoints:")
            PyImGui.pop_style_color(1)
            if merged_pts:
                for j, p in enumerate(merged_pts, start=1):
                    try:
                        x, y = int(p[0]), int(p[1])
                        PyImGui.text(f"- WP {j}: ({x},{y})")
                    except Exception:
                        PyImGui.text(f"- WP {j}: {p}")
                    # Controls for merged list too
                    PyImGui.same_line(0, 6)
                    global_idx = j - 1
                    if PyImGui.button(f">##go_merge_{j}", width=20):
                        if FSM_vars.path_and_aggro:
                            FSM_vars.path_and_aggro.force_move_to_index(global_idx, sticky=True)
                    PyImGui.same_line(0, 2)
                    if PyImGui.button(f"I##set_merge_{j}", width=18):
                        if FSM_vars.path_and_aggro:
                            FSM_vars.path_and_aggro.set_active_index(global_idx)
            else:
                PyImGui.text("- (empty)")

    # ====== Debug Tools ======
    if bot_vars.debug_enabled:
        PyImGui.separator()
        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        debug_open = PyImGui.collapsing_header(
            f"{IconsFontAwesome5.ICON_TOOLS} Debug Tools",
            PyImGui.TreeNodeFlags.DefaultOpen
        )
        PyImGui.pop_style_color(1)

        if debug_open:
            state_machine = FSM_vars.state_machine
            started = False
            paused = False
            current_step = "-"
            try:
                started = state_machine.is_started()
            except Exception:
                pass
            try:
                paused = state_machine.is_paused()
            except Exception:
                pass
            try:
                current_step = state_machine.get_current_step_name()
            except Exception:
                current_step = "-"

            PyImGui.text(f"Main FSM Started: {started} | Paused: {paused}")
            PyImGui.text(f"Current Step: {current_step}")
            if bot_vars.debug_recent_error:
                PyImGui.text_wrapped(f"Last Debug Error: {bot_vars.debug_recent_error}")

            try:
                state_names = state_machine.get_state_names()
            except Exception as exc:
                state_names = []
                PyImGui.text_wrapped(f"State list error: {exc}")

            if state_names:
                PyImGui.push_item_width(220)
                bot_vars.debug_state_filter = PyImGui.input_text(
                    "Filter States##debug_state_filter",
                    bot_vars.debug_state_filter
                )
                PyImGui.pop_item_width()
                filter_text = bot_vars.debug_state_filter.lower()
                filtered_states = [
                    name for name in state_names
                    if not filter_text or filter_text in name.lower()
                ]
                if not filtered_states:
                    PyImGui.text("(no matching states)")
                elif PyImGui.begin_table(
                    "DebugStateJumpTable",
                    2,
                    int(PyImGui.TableFlags.RowBg | PyImGui.TableFlags.BordersOuterH)
                ):
                    for idx, name in enumerate(filtered_states):
                        PyImGui.table_next_row()
                        PyImGui.table_next_column()
                        PyImGui.text(name)
                        PyImGui.table_next_column()
                        if PyImGui.button(f"Jump##debug_jump_{idx}"):
                            try:
                                if not state_machine.is_started():
                                    msg = "Main FSM not started; start the bot before jumping."
                                    bot_vars.debug_recent_error = msg
                                    ConsoleLog(
                                        "Debug Tools",
                                        msg,
                                        Console.MessageType.Warning
                                    )
                                elif state_machine.is_paused():
                                    msg = "Main FSM is paused; resume before jumping."
                                    bot_vars.debug_recent_error = msg
                                    ConsoleLog(
                                        "Debug Tools",
                                        msg,
                                        Console.MessageType.Warning
                                    )
                                else:
                                    state_machine.jump_to_state_by_name(name)
                                    bot_vars.debug_recent_error = ""
                                    ConsoleLog(
                                        "Debug Tools",
                                        f"Jumped to state '{name}'.",
                                        Console.MessageType.Info
                                    )
                            except Exception as exc:
                                bot_vars.debug_recent_error = str(exc)
                                ConsoleLog(
                                    "Debug Tools",
                                    f"Failed to jump to '{name}': {exc}",
                                    Console.MessageType.Error
                                )
                    PyImGui.end_table()

            PyImGui.separator()
            PyImGui.text("Waypoint Debug Controls:")
            path_debugger = FSM_vars.path_and_aggro
            hold_active = bool(getattr(path_debugger, "_debug_hold", False)) if path_debugger else False
            if path_debugger:
                total_wps = len(path_debugger.get_waypoints()) if path_debugger else 0
                try:
                    current_idx = path_debugger.get_current_index()
                except Exception:
                    current_idx = None
                if current_idx is not None and total_wps:
                    PyImGui.text(f"Current Index: {current_idx + 1}/{total_wps}")
                elif total_wps:
                    PyImGui.text(f"Current Index: -/{total_wps}")
                else:
                    PyImGui.text("Current Index: (no waypoints)")

                if PyImGui.button("Prev##debug_prev_wp"):
                    try:
                        path_debugger.seek_relative(-1, sticky=True)
                        bot_vars.debug_recent_error = ""
                    except Exception as exc:
                        bot_vars.debug_recent_error = str(exc)
                        ConsoleLog("Debug Tools", f"Failed to move to previous waypoint: {exc}", Console.MessageType.Error)
                PyImGui.same_line(0, 4)
                if PyImGui.button("Next##debug_next_wp"):
                    try:
                        path_debugger.seek_relative(1, sticky=True)
                        bot_vars.debug_recent_error = ""
                    except Exception as exc:
                        bot_vars.debug_recent_error = str(exc)
                        ConsoleLog("Debug Tools", f"Failed to move to next waypoint: {exc}", Console.MessageType.Error)
                PyImGui.same_line(0, 4)
                hold_label = "Release Hold" if hold_active else "Enable Hold"
                if PyImGui.button(f"{hold_label}##debug_hold_toggle"):
                    try:
                        if hold_active:
                            path_debugger.release_hold()
                        else:
                            path_debugger.enable_hold()
                        bot_vars.debug_recent_error = ""
                    except Exception as exc:
                        bot_vars.debug_recent_error = str(exc)
                        ConsoleLog("Debug Tools", f"Failed to toggle hold: {exc}", Console.MessageType.Error)

                PyImGui.push_item_width(90)
                bot_vars.debug_force_index_input = PyImGui.input_text(
                    "Waypoint##debug_force_index",
                    bot_vars.debug_force_index_input
                )
                PyImGui.pop_item_width()
                PyImGui.same_line(0, 4)
                if PyImGui.button("Force Move##debug_force_move"):
                    idx_text = bot_vars.debug_force_index_input.strip()
                    if not idx_text:
                        bot_vars.debug_recent_error = "Enter a waypoint index before forcing movement."
                        ConsoleLog("Debug Tools", bot_vars.debug_recent_error, Console.MessageType.Warning)
                    else:
                        try:
                            idx_value = int(idx_text)
                            target_index = idx_value - 1 if idx_value > 0 else idx_value
                            if target_index < 0:
                                target_index = 0
                            path_debugger.force_move_to_index(target_index, sticky=True)
                            bot_vars.debug_recent_error = ""
                        except ValueError:
                            bot_vars.debug_recent_error = "Invalid waypoint index"
                            ConsoleLog(
                                "Debug Tools",
                                f"Invalid waypoint index '{idx_text}'.",
                                Console.MessageType.Warning
                            )
                        except Exception as exc:
                            bot_vars.debug_recent_error = str(exc)
                            ConsoleLog("Debug Tools", f"Failed to force move: {exc}", Console.MessageType.Error)

                if PyImGui.button("Release Hold##debug_release_hold"):
                    try:
                        path_debugger.release_hold()
                        bot_vars.debug_recent_error = ""
                    except Exception as exc:
                        bot_vars.debug_recent_error = str(exc)
                        ConsoleLog("Debug Tools", f"Failed to release hold: {exc}", Console.MessageType.Error)
            else:
                PyImGui.text("Path and aggro handler not available.")

            PyImGui.separator()

            def _fmt_timer(timer, fmt='mm:ss'):
                try:
                    return FormatTime(timer.GetElapsedTime(), fmt)
                except Exception:
                    return "-"

            def _format_distance(value):
                if value is None:
                    return "n/a"
                try:
                    return f"{float(value):.0f}"
                except Exception:
                    return str(value)

            if PyImGui.begin_tab_bar("DebugToolsTabBar"):
                if PyImGui.begin_tab_item("Runtime"):
                    runtime_rows = [
                        ("Bot Running", bot_vars.is_running),
                        ("Bot Paused", bot_vars.is_paused),
                        ("Runs Attempted", bot_vars.runs_attempted),
                        ("Runs Completed", bot_vars.runs_completed),
                        ("Success Rate", f"{bot_vars.success_rate * 100:.1f}%" if bot_vars.runs_attempted else "0.0%"),
                        ("Global Timer", _fmt_timer(bot_vars.global_timer, 'hh:mm:ss')),
                        ("Current Run", _fmt_timer(bot_vars.lap_timer, 'mm:ss')),
                        _safe_read("Main FSM Started", lambda: state_machine.is_started(), False),
                        _safe_read("Main FSM Finished", lambda: state_machine.is_finished(), False),
                    ]
                    ImGui.table("DebugRuntimeTable", ["Variable", "Value"], runtime_rows)
                    PyImGui.end_tab_item()

                if PyImGui.begin_tab_item("Combat"):
                    combat_rows = [
                        ("Combat Started", bot_vars.combat_started),
                        ("Pause Combat Flag", bot_vars.pause_combat_fsm),
                        _safe_read("Global Combat FSM Started", lambda: FSM_vars.global_combat_fsm.is_started(), False),
                        _safe_read("Global Combat FSM Paused", lambda: FSM_vars.global_combat_fsm.is_paused(), False),
                        _safe_read("Combat Handler Started", lambda: FSM_vars.global_combat_handler.is_started(), False),
                        _safe_read("In Killing Routine", lambda: FSM_vars.in_killing_routine, False),
                        _safe_read("Last Skill Index", lambda: FSM_vars.current_skill, 0),
                        ("Last Skill Time", f"{FSM_vars.last_skill_time:.2f}" if FSM_vars.last_skill_time else "0.00"),
                    ]
                    ImGui.table("DebugCombatTable", ["Variable", "Value"], combat_rows)
                    PyImGui.end_tab_item()

                if PyImGui.begin_tab_item("Movement"):
                    movement_rows = [
                        _safe_read("FollowXY Following", lambda: FSM_vars.movement_handler.is_following(), False),
                        _safe_read("FollowXY Arrived", lambda: FSM_vars.movement_handler.has_arrived(), False),
                        _safe_read("FollowXY Distance", lambda: _format_distance(FSM_vars.movement_handler.get_distance_to_waypoint()), "n/a"),
                        _safe_read("FollowXY Timer", lambda: _fmt_timer(FSM_vars.movement_handler.wait_timer), "-"),
                        _safe_read("Movement Handler Paused", lambda: FSM_vars.movement_handler.is_paused(), False),
                        ("Auto-Stuck Timer", _fmt_timer(FSM_vars.auto_stuck_command_timer)),
                        ("Non-Movement Timer", _fmt_timer(FSM_vars.non_movement_timer)),
                        ("Waypoint Hold", hold_active),
                        ("Forced Index", getattr(path_debugger, "_forced_index", None) if path_debugger else "-"),
                    ]
                    ImGui.table("DebugMovementTable", ["Variable", "Value"], movement_rows)
                    PyImGui.end_tab_item()

                PyImGui.end_tab_bar()

    # Pop styles
    PyImGui.pop_style_color(3)
    PyImGui.pop_style_color(3)
    PyImGui.pop_style_color(6)

    PyImGui.end()

def main():
    try:
        DrawWindow()

        if not bot_vars.is_running or bot_vars.is_paused:
            return

        if Map.IsMapLoading():
            FSM_vars.movement_handler.reset()
            return

        if FSM_vars.global_combat_fsm.is_finished():
            FSM_vars.global_combat_fsm.reset()
            return

        if Map.IsExplorable():
            if bot_vars.combat_started:
                combat_handler.HandleCombat()

        ActionQueueManager().ProcessAll()

        if not bot_vars.pause_combat_fsm:
            FSM_vars.global_combat_fsm.update()
        FSM_vars.state_machine.update()

    except Exception as e:
        ConsoleLog(module_name, f"Error in main: {str(e)}", Console.MessageType.Error)
        raise

def StartBot():
    global bot_vars, FSM_vars

    if FSM_vars.state_machine.get_state_count() == 0:
        InitializeStateMachine()

    # Reset vars/states
    FSM_vars.has_blessing = False
    FSM_vars.in_blessing_dialog = False
    FSM_vars.blessing_timer.Stop()
    FSM_vars.movement_handler.reset()
    FSM_vars.outpost_pathing.reset()
    FSM_vars.explorable_pathing.reset()

    # Clear any leftover debug state
    if FSM_vars.path_and_aggro:
        FSM_vars.path_and_aggro.release_hold()

    if Map.GetMapID() != bot_vars.starting_map:
        Routines.Transition.TravelToOutpost(bot_vars.starting_map)

    FSM_vars.state_machine.reset()
    FSM_vars.global_combat_fsm.reset()
    FSM_vars.global_combat_handler.reset()

    bot_vars.is_running = True
    bot_vars.combat_started = False
    bot_vars.global_timer.Start()
    bot_vars.lap_timer.Start()

    FSM_vars.state_machine.start()
    FSM_vars.global_combat_fsm.start()

def TogglePause():
    if bot_vars.is_paused:
        ResumeBotExecution()
    else:
        PauseBotExecution()

def PauseBotExecution():
    if not bot_vars.is_running:
        return
    bot_vars.is_paused = True
    FSM_vars.state_machine.pause()
    FSM_vars.global_combat_fsm.pause()
    FSM_vars.movement_handler.pause()
    ConsoleLog(module_name, "Bot Paused", Console.MessageType.Info)

def ResumeBotExecution():
    if not bot_vars.is_running:
        return
    bot_vars.is_paused = False
    FSM_vars.state_machine.resume()
    FSM_vars.global_combat_fsm.resume()
    FSM_vars.movement_handler.resume()
    ConsoleLog(module_name, "Bot Resumed", Console.MessageType.Info)

def StopBot():
    global bot_vars, FSM_vars
    bot_vars.is_running = False
    bot_vars.is_paused = False
    bot_vars.global_timer.Stop()
    bot_vars.lap_timer.Stop()
    FSM_vars.state_machine.stop()
    FSM_vars.global_combat_fsm.stop()
    if bot_vars.combat_started:
        stop_combat()
    ResetEnvironment()

# Initialize the global instances
FSM_vars = FSMVars()
bot_vars = BotVars()
