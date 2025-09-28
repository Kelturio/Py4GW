from Py4GWCoreLib import *

_vanquish_timer = ThrottledTimer(1000)  # 1 second
_cached_vanquish = {"killed": 0, "total": 0, "valid": False}
_vanquish_dmg_sent = False

def draw_vanquish_status(label: str = "Vanquish Status"):
    global _cached_vanquish, _vanquish_dmg_sent

    if not Routines.Checks.Map.MapValid():
        _vanquish_dmg_sent = False
        return
    if not Map.IsExplorable():
        _vanquish_dmg_sent = False
        return
    """
    Displays vanquish status with kills, total, and percent.
    Updates once per second via cached values.
    """
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

    if _cached_vanquish["valid"]:
        killed = _cached_vanquish["killed"]
        total = _cached_vanquish["total"] + killed
        percent = (killed / total * 100) if total > 0 else 0
        PyImGui.text(f"{label}: {killed:,} / {total:,} ({percent:.1f}%)")
        if total > 0 and killed >= total:
            if not _vanquish_dmg_sent:
                Player.SendChatCommand("dmg")
                _vanquish_dmg_sent = True
        else:
            _vanquish_dmg_sent = False
    else:
        PyImGui.text(f"{label}: N/A")
        _vanquish_dmg_sent = False

__all__ = ["draw_vanquish_status"]
