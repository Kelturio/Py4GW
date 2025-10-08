from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _resolve_root() -> Path:
    def _candidate_to_dir(candidate: Path) -> Path | None:
        try:
            resolved = candidate.resolve()
        except (FileNotFoundError, RuntimeError):
            return None
        return resolved if resolved.is_dir() else resolved.parent

    candidates: list[Path] = []

    if "__file__" in globals() and __file__:
        candidates.append(Path(__file__))

    if sys.argv:
        argv0 = sys.argv[0]
        if argv0:
            candidates.append(Path(argv0))

    candidates.append(Path.cwd())

    for candidate in candidates:
        directory = _candidate_to_dir(candidate)
        if not directory:
            continue
        for parent in [directory, *directory.parents]:
            if (parent / "Py4GWCoreLib").exists():
                return parent

    return Path.cwd()


ROOT = _resolve_root()


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Unable to locate {relative_path!r} from root {ROOT!r}")

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module {name!r} from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


skill_template = load_module("py4gw_skill_template", "Py4GWCoreLib/skill_template.py")
gamedata = load_module("py4gw_gamedata", "Py4GWCoreLib/enums_src/GameData_enums.py")

SkillTemplate = skill_template.SkillTemplate
SkillAttribute = skill_template.SkillAttribute
make_skill_template = skill_template.make_skill_template
encode_skill_template = skill_template.encode_skill_template
decode_skill_template = skill_template.decode_skill_template


def _load_skill_ids() -> dict[str, int]:
    with (ROOT / "Py4GWCoreLib" / "skill_descriptions.json").open(encoding="utf-8") as handle:
        data = json.load(handle)
    return {entry["name"]: int(skill_id) for skill_id, entry in data.items() if "name" in entry}


SKILL_IDS = _load_skill_ids()


def test_decode_known_build_matches_expected_data():
    code = "OwVUI2h5lPP8Id2BkAiAvpLBTAA"
    template = decode_skill_template(code)

    assert template.primary == gamedata.Profession.Assassin
    assert template.secondary == gamedata.Profession.Mesmer

    expected_skills = [
        SKILL_IDS["Deadly Paradox"],
        SKILL_IDS["Shadow Form"],
        SKILL_IDS["Shroud of Distress"],
        SKILL_IDS["Way of Perfection"],
        SKILL_IDS["Heart of Shadow"],
        SKILL_IDS["Wastrel's Demise"],
        SKILL_IDS["Arcane Echo"],
        SKILL_IDS["Channeling"],
    ]
    assert list(template.skills) == expected_skills

    attribute_map = {attribute.attribute: attribute.points for attribute in template.attributes}
    assert attribute_map[gamedata.Attribute.DominationMagic] == 11
    assert attribute_map[gamedata.Attribute.InspirationMagic] == 6
    assert attribute_map[gamedata.Attribute.DeadlyArts] == 2
    assert attribute_map[gamedata.Attribute.ShadowArts] == 12

    assert encode_skill_template(template) == code


def test_round_trip_with_custom_template():
    custom = make_skill_template(
        primary=gamedata.Profession.Warrior,
        secondary=gamedata.Profession.Ranger,
        skills=[1, 2, 3, 4, 5, 6, 7, 8],
        attributes=[
            (gamedata.Attribute.Strength, 12),
            (gamedata.Attribute.AxeMastery, 12),
            (gamedata.Attribute.Marksmanship, 3),
        ],
    )

    encoded = encode_skill_template(custom)
    decoded = decode_skill_template(encoded)

    assert encoded.endswith("A")
    assert decoded.primary == custom.primary
    assert decoded.secondary == custom.secondary
    assert list(decoded.skills) == list(custom.skills)

    decoded_attributes = {attribute.attribute: attribute.points for attribute in decoded.attributes}
    expected_attributes = {
        gamedata.Attribute.Strength: 12,
        gamedata.Attribute.AxeMastery: 12,
        gamedata.Attribute.Marksmanship: 3,
    }
    assert decoded_attributes == expected_attributes
