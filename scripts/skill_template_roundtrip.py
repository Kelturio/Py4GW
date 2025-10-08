"""Example showcasing skill template round-trip encoding and decoding."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


skill_template = load_module("py4gw_skill_template_example", "Py4GWCoreLib/skill_template.py")
gamedata = load_module("py4gw_gamedata_example", "Py4GWCoreLib/enums_src/GameData_enums.py")


def lookup_skill_id(name: str) -> int:
    with (ROOT / "Py4GWCoreLib" / "skill_descriptions.json").open(encoding="utf-8") as handle:
        data = json.load(handle)
    for skill_id, entry in data.items():
        if entry.get("name") == name:
            return int(skill_id)
    raise KeyError(name)


def main() -> None:
    code = "OwVUI2h5lPP8Id2BkAiAvpLBTAA"
    template = skill_template.decode_skill_template(code)

    print("Decoded template:")
    print(f"  Primary profession: {gamedata.Profession(template.primary).name}")
    print(f"  Secondary profession: {gamedata.Profession(template.secondary).name}")

    print("  Skills:")
    with (ROOT / "Py4GWCoreLib" / "skill_descriptions.json").open(encoding="utf-8") as handle:
        data = json.load(handle)
    name_lookup = {int(skill_id): entry["name"] for skill_id, entry in data.items() if "name" in entry}
    for index, skill_id in enumerate(template.skills, start=1):
        print(f"    {index}: {name_lookup.get(skill_id, f'ID {skill_id}')}")

    print("  Attributes:")
    for attribute in template.attributes:
        attr_enum = gamedata.Attribute(attribute.attribute)
        print(f"    {attr_enum.name}: {attribute.points}")

    round_trip = skill_template.encode_skill_template(template)
    print("\nRound-trip encoding produces:", round_trip)

    rebuilt = skill_template.make_skill_template(
        primary=gamedata.Profession.Warrior,
        secondary=gamedata.Profession.Ranger,
        skills=[lookup_skill_id(name) for name in [
            "Hundred Blades",
            "Cyclone Axe",
            "Penetrating Blow",
            "Frenzy",
            "Flurry",
            "Rush",
            "Resurrection Signet",
            "Battle Rage",
        ]],
        attributes=[
            (gamedata.Attribute.Strength, 12),
            (gamedata.Attribute.AxeMastery, 12),
            (gamedata.Attribute.Tactics, 3),
        ],
    )
    rebuilt_code = skill_template.encode_skill_template(rebuilt)
    print("Newly built code:", rebuilt_code)
    decoded = skill_template.decode_skill_template(rebuilt_code)
    assert list(decoded.skills) == list(rebuilt.skills)
    print("Decoded new code matches the source data.")


if __name__ == "__main__":
    main()
