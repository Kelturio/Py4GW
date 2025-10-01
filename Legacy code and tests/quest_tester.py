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


def _record_quest_details(quest_id):
    Quest.RequestQuestInfo(quest_id, update_markers=True)
    quest = Quest.GetQuestData(quest_id)

    if quest is None:
        quest_details[quest_id] = None
        return

    quest_details[quest_id] = {
        field: getattr(quest, field, None)
        for field, _ in QUEST_FIELDS
    }


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

        PyImGui.same_line()

        if PyImGui.button("export quest data"):
            if quest_details:
                export_path = os.path.join(
                    os.path.dirname(__file__), "quest_data_export.json"
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
