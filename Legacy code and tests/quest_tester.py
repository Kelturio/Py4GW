import json
import os

from Py4GWCoreLib import *

MODULE_NAME = "tester for everything"

quest_log = []
quest_details = {}
requested_quests = set()
export_message = ""


def _get_quest_id(entry):
    return getattr(entry, "quest_id", entry)


def _to_json_compatible(value, _visited=None):
    """Convert quest data values into a JSON serialisable structure."""

    if _visited is None:
        _visited = set()

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__type__": "bytes", "data": list(value)}

    if isinstance(value, dict):
        return {
            str(key): _to_json_compatible(sub_value, _visited)
            for key, sub_value in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_to_json_compatible(item, _visited) for item in value]

    if hasattr(value, "__dict__"):
        return _extract_object_snapshot(value, _visited)

    return repr(value)


def _extract_object_snapshot(obj, _visited=None):
    if _visited is None:
        _visited = set()

    obj_id = id(obj)

    if obj_id in _visited:
        return "<recursive reference>"

    _visited.add(obj_id)
    snapshot = {}

    for attribute in dir(obj):
        if attribute.startswith("_"):
            continue

        try:
            value = getattr(obj, attribute)
        except UnicodeDecodeError as decode_error:
            raw_buffer = getattr(decode_error, "object", b"") or b""
            snapshot[attribute] = _to_json_compatible(raw_buffer, _visited)
            continue
        except Exception:
            continue

        if callable(value):
            continue

        snapshot[attribute] = _to_json_compatible(value, _visited)

    _visited.remove(obj_id)
    return snapshot


def _record_quest_details(quest_id):
    Quest.RequestQuestInfo(quest_id, update_marker=True)
    quest = Quest.GetQuestData(quest_id)

    if quest is None:
        quest_details[quest_id] = None
        return

    quest_details[quest_id] = _extract_object_snapshot(quest)


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

            for attribute in sorted(quest):
                PyImGui.text(f"{attribute}: {quest.get(attribute)}")


    PyImGui.end()
    
if __name__ == "__main__":
    main()
