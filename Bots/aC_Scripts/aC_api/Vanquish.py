from Py4GWCoreLib import *

_vanquish_timer = ThrottledTimer(1000)  # 1 second
_cached_vanquish = {"killed": 0, "total": 0, "valid": False}
_vanquish_completed = False

def draw_vanquish_status(label: str = "Vanquish Status"):
    if not Routines.Checks.Map.MapValid():
        return
    if not Map.IsExplorable():
        return
    """
    Displays vanquish status with kills, total, and percent.
    Updates once per second via cached values.
    """
    global _cached_vanquish, _vanquish_completed

    if _vanquish_timer.IsExpired():
        ready = (
            GLOBAL_CACHE.Map.IsMapReady() and
            GLOBAL_CACHE.Party.IsPartyLoaded() and
            GLOBAL_CACHE.Map.IsExplorable() and
            GLOBAL_CACHE.Map.IsVanquishable() and
            GLOBAL_CACHE.Party.IsHardMode()
        )
        _cached_vanquish["valid"] = ready
        if ready:
            _cached_vanquish["killed"] = GLOBAL_CACHE.Map.GetFoesKilled()
            _cached_vanquish["total"] = GLOBAL_CACHE.Map.GetFoesToKill()
        _vanquish_timer.Reset()
        if not ready:
            _vanquish_completed = False

    if _cached_vanquish["valid"]:
        killed = _cached_vanquish["killed"]
        remaining = _cached_vanquish["total"]
        total = remaining + killed
        if remaining <= 0:
            if not _vanquish_completed:
                GLOBAL_CACHE.Player.SendChatCommand("dmg")
                _vanquish_completed = True
        else:
            _vanquish_completed = False
        percent = (killed / total * 100) if total > 0 else 0
        PyImGui.text(f"{label}: {killed:,} / {total:,} ({percent:.1f}%)")
    else:
        PyImGui.text(f"{label}: N/A")
        _vanquish_completed = False

__all__ = ["draw_vanquish_status"]
