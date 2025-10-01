"""Interactive demo for quest-related GWCA exports.

This script showcases how to call quest functions exposed by ``GWCA.dll``
through the :class:`Py4GWCoreLib.GWCA.GWCALibrary` helper.  Launch it from
Py4GW while the Guild Wars client is running with GWCA injected to experiment
with setting, requesting and abandoning quests directly from the DLL.
"""
from __future__ import annotations

from ctypes import POINTER, Structure, c_bool, c_float, c_uint32, c_void_p
from typing import List

import ctypes
import Py4GW
import PyImGui

from Py4GWCoreLib import GWCALibrary
from Py4GWCoreLib.Quest import Quest

MODULE_NAME = "GWCA Quest Demo"

_gwca = GWCALibrary()
_gwca.initialize()


class _GamePos(Structure):
    """Representation of ``GW::GamePos`` used inside ``GW::Quest``."""

    _fields_ = [
        ("x", c_float),
        ("y", c_float),
        ("plane", c_float),
    ]


class _QuestStruct(Structure):
    """Mirror of the ``GW::Quest`` structure returned by ``GetQuest``."""

    _fields_ = [
        ("quest_id", c_uint32),
        ("log_state", c_uint32),
        ("location", c_void_p),
        ("name", c_void_p),
        ("npc", c_void_p),
        ("map_from", c_uint32),
        ("marker", _GamePos),
        ("_unknown_0x24", c_uint32),
        ("map_to", c_uint32),
        ("description", c_void_p),
        ("objectives", c_void_p),
    ]


_get_active_quest_id = _gwca.get_function(
    "?GetActiveQuestId@QuestMgr@GW@@YA?AW4QuestID@Constants@2@XZ",
    restype=c_uint32,
)
_set_active_quest_id = _gwca.get_function(
    "?SetActiveQuestId@QuestMgr@GW@@YA_NW4QuestID@Constants@2@@Z",
    restype=c_bool,
    argtypes=(c_uint32,),
)
_abandon_quest_id = _gwca.get_function(
    "?AbandonQuestId@QuestMgr@GW@@YA_NW4QuestID@Constants@2@@Z",
    restype=c_bool,
    argtypes=(c_uint32,),
)
_request_quest_info = _gwca.get_function(
    "?RequestQuestInfoId@QuestMgr@GW@@YA_NW4QuestID@Constants@2@_N@Z",
    restype=c_bool,
    argtypes=(c_uint32, c_bool),
)
_get_quest = _gwca.get_function(
    "?GetQuest@QuestMgr@GW@@YAPAUQuest@2@W4QuestID@Constants@2@@Z",
    restype=POINTER(_QuestStruct),
    argtypes=(c_uint32,),
)

_quest_id_input = 0
_update_marker = False
_logs: List[str] = []


def _log(message: str) -> None:
    """Send a message to both the Py4GW console and the ImGui log view."""

    Py4GW.Console.Log(MODULE_NAME, message)
    _logs.append(message)
    if len(_logs) > 12:
        del _logs[0]


def _call_bool(name: str, func, *args) -> None:
    """Call a GWCA function and record its success state."""

    try:
        success = bool(func(*args))
        status = "succeeded" if success else "failed"
        _log(f"{name} {status}")
    except Exception as exc:  # pragma: no cover - runtime feedback
        _log(f"{name} raised {exc!r}")


def _wstring_from_ptr(pointer: int | None) -> str | None:
    """Decode a pointer to a wide-character buffer returned by GWCA."""

    if not pointer:
        return None
    try:
        return ctypes.wstring_at(pointer)
    except (ValueError, OSError):  # pragma: no cover - defensive path
        return None


def _describe_log_state(log_state: int) -> str:
    """Return a readable summary of quest flags stored in ``log_state``."""

    flags: List[str] = []
    if log_state & 0x2:
        flags.append("completed")
    if log_state & 0x10:
        flags.append("mission quest")
    if log_state & 0x40:
        flags.append("area primary")
    if log_state & 0x20:
        flags.append("primary")
    if not flags:
        flags.append("active")
    return ", ".join(flags)


def _log_quest_details(quest: _QuestStruct) -> None:
    """Pretty-print quest details obtained from ``GWCA::QuestMgr::GetQuest``."""

    name = _wstring_from_ptr(quest.name) or "<unnamed>"
    location = _wstring_from_ptr(quest.location) or "<unknown category>"
    npc = _wstring_from_ptr(quest.npc) or "<no giver>"
    description = _wstring_from_ptr(quest.description) or "<no description>"
    objectives = _wstring_from_ptr(quest.objectives) or "<no objectives>"
    _log(f"Quest {quest.quest_id} – {name}")
    _log(f"  Flags: {_describe_log_state(quest.log_state)}")
    _log(f"  Category: {location}")
    _log(f"  NPC: {npc}")
    _log(
        "  Marker: x={:.1f}, y={:.1f}, plane={:.1f}".format(
            quest.marker.x, quest.marker.y, quest.marker.plane
        )
    )
    _log(f"  Description: {description}")
    _log(f"  Objectives: {objectives}")


def draw_window() -> None:
    """Render the ImGui window that exposes the quest helpers."""

    global _quest_id_input
    global _update_marker

    if PyImGui.begin(MODULE_NAME):
        PyImGui.text("Interact with quest exports provided by GWCA.dll")
        PyImGui.separator()

        _quest_id_input = PyImGui.input_int("Quest ID", _quest_id_input)
        _update_marker = PyImGui.checkbox("Update quest marker", _update_marker)

        if PyImGui.button("Get active quest (GWCA)"):
            try:
                quest_id = int(_get_active_quest_id().value)
            except AttributeError:
                quest_id = int(_get_active_quest_id())
            _log(f"GWCA reports active quest ID: {quest_id}")

        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Get active quest (PyQuest)"):
            try:
                quest_id = Quest.GetActiveQuest()
            except Exception as exc:  # pragma: no cover - runtime feedback
                _log(f"PyQuest.GetActiveQuest raised {exc!r}")
            else:
                _log(f"PyQuest reports active quest ID: {quest_id}")

        if PyImGui.button("Set active quest (GWCA)"):
            _call_bool("SetActiveQuestId", _set_active_quest_id, _quest_id_input)

        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Set active quest (PyQuest)"):
            try:
                Quest.SetActiveQuest(_quest_id_input)
            except Exception as exc:  # pragma: no cover - runtime feedback
                _log(f"PyQuest.SetActiveQuest raised {exc!r}")
            else:
                _log("PyQuest.SetActiveQuest completed")

        if PyImGui.button("Get quest details (GWCA)"):
            try:
                quest_ptr = _get_quest(_quest_id_input)
            except Exception as exc:  # pragma: no cover - runtime feedback
                _log(f"GetQuest raised {exc!r}")
            else:
                if not quest_ptr:
                    _log("GetQuest returned NULL")
                else:
                    _log_quest_details(quest_ptr.contents)

        if PyImGui.button("Request quest info (GWCA)"):
            _call_bool(
                "RequestQuestInfoId",
                _request_quest_info,
                _quest_id_input,
                _update_marker,
            )

        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Request quest info (PyQuest)"):
            try:
                Quest.RequestQuestInfo(_quest_id_input, _update_marker)
            except Exception as exc:  # pragma: no cover - runtime feedback
                _log(f"PyQuest.RequestQuestInfo raised {exc!r}")
            else:
                _log("PyQuest.RequestQuestInfo completed")

        if PyImGui.button("Abandon quest (GWCA)"):
            _call_bool("AbandonQuestId", _abandon_quest_id, _quest_id_input)

        PyImGui.same_line(0.0, -1.0)
        if PyImGui.button("Abandon quest (PyQuest)"):
            try:
                Quest.AbandonQuest(_quest_id_input)
            except Exception as exc:  # pragma: no cover - runtime feedback
                _log(f"PyQuest.AbandonQuest raised {exc!r}")
            else:
                _log("PyQuest.AbandonQuest completed")

        PyImGui.separator()
        PyImGui.text("Recent calls:")
        for entry in _logs:
            PyImGui.bullet_text(entry)

        PyImGui.end()


def main() -> None:
    try:
        draw_window()
    except Exception as exc:  # pragma: no cover - runtime feedback
        Py4GW.Console.Log(MODULE_NAME, f"Unexpected error: {exc!r}")


if __name__ == "__main__":
    main()
