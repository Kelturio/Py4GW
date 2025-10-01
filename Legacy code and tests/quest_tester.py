import json
import os

from Py4GWCoreLib import *

MODULE_NAME = "tester for everything"

quest_log = []
quest_details = {}
requested_quests = set()
export_message = ""

QUEST_FIELDS = (
    ("quest_id", "Quest ID"),
    ("name", "Name"),
    ("description", "Description"),
    ("objectives", "Objectives"),
    ("location", "Location"),
    ("npc", "NPC"),
    ("log_state", "Log State"),
    ("map_from", "Map From"),
    ("map_to", "Map To"),
    ("marker_x", "Marker X"),
    ("marker_y", "Marker Y"),
    ("h0024", "H0024"),
    ("is_completed", "Is Completed"),
    ("is_current_mission_quest", "Is Current Mission Quest"),
    ("is_area_primary", "Is Area Primary"),
    ("is_primary", "Is Primary"),
)


def _get_quest_id(entry):
    return getattr(entry, "quest_id", entry)


def _coerce_text_field(value):
    """Return a JSON/UI friendly representation for quest data fields."""

    if isinstance(value, (bytes, bytearray)):
        for encoding in ("utf-8", "latin-1"):
            try:
                return value.decode(encoding)
            except UnicodeDecodeError:
                continue

        return value.decode("latin-1", errors="replace")

    return value


def _record_quest_details(quest_id):
    Quest.RequestQuestInfo(quest_id, update_marker=True)
    quest = Quest.GetQuestData(quest_id)

    if quest is None:
        quest_details[quest_id] = None
        return

    quest_snapshot = {}

    for field, _ in QUEST_FIELDS:
        try:
            value = getattr(quest, field, None)
        except UnicodeDecodeError as decode_error:
            # Some quest strings include bytes that cannot be decoded using the
            # UTF-8 codec that backs the binding. Preserve the remaining
            # fields and surface the issue instead of terminating the tester.
            value = f"<unable to decode ({decode_error})>"

        quest_snapshot[field] = _coerce_text_field(value)

    quest_details[quest_id] = quest_snapshot


def _get_export_directory():
    if "__file__" in globals():
        return os.path.dirname(os.path.abspath(__file__))

    return os.getcwd()


def _export_quests(path):
    export_payload = {
        str(quest_id): details for quest_id, details in quest_details.items() if details
    }

    with open(path, "w", encoding="utf-8") as export_file:
        json.dump(export_payload, export_file, indent=2)


def main():
    global quest_log, quest_details, requested_quests, export_message

    if PyImGui.begin("timer test"):
        if PyImGui.button("get quest log"):
            quest_log = Quest.GetQuestLog()
            quest_details.clear()
            requested_quests.clear()
            export_message = ""

        # PyImGui.same_line requires both an x_offset and spacing argument in this build,
        # so provide defaults that preserve the standard immediate-mode behaviour.
        PyImGui.same_line(0.0, -1.0)

        if PyImGui.button("export quest data"):
            if quest_details:
                export_path = os.path.join(
                    _get_export_directory(), "quest_data_export.json"
                )

                try:
                    _export_quests(export_path)
                except OSError as export_error:
                    export_message = f"Failed to export: {export_error}"
                else:
                    export_message = f"Exported quest data to {export_path}"
            else:
                export_message = "No quest data available to export."

        if export_message:
            PyImGui.text(export_message)

    for quest_entry in quest_log:
        quest_id = _get_quest_id(quest_entry)

        if quest_id not in requested_quests:
            _record_quest_details(quest_id)
            requested_quests.add(quest_id)

        if PyImGui.collapsing_header(f"Quest ID: {quest_id}"):
            quest = quest_details.get(quest_id)

            if quest is None:
                PyImGui.text("Quest data unavailable.")
                continue

            for field, label in QUEST_FIELDS:
                PyImGui.text(f"{label}: {quest.get(field)}")


    PyImGui.end()
    
if __name__ == "__main__":
    main()
