"""Demonstrate round-trip encoding and decoding of skill templates."""

import importlib.util
import pathlib
import sys

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "Py4GWCoreLib" / "SkillTemplate.py"
spec = importlib.util.spec_from_file_location("skill_template", MODULE_PATH)
skill_template = importlib.util.module_from_spec(spec)
sys.modules.setdefault("skill_template", skill_template)
assert spec.loader is not None
spec.loader.exec_module(skill_template)

AttributeEntry = skill_template.AttributeEntry
DecodeSkillTemplate = skill_template.DecodeSkillTemplate
EncodeSkillTemplate = skill_template.EncodeSkillTemplate
SkillTemplate = skill_template.SkillTemplate


def main() -> None:
    original_code = "OQASEDqEC1vcNABWAAAA"
    template = DecodeSkillTemplate(original_code)

    print("Decoded template:")
    print(f"  Primary profession: {template.primary}")
    print(f"  Secondary profession: {template.secondary}")
    print("  Attributes:")
    for entry in template.attributes:
        print(f"    - Attribute {entry.attribute}: {entry.points} points")
    print("  Skills:")
    for slot, skill_id in enumerate(template.skills, start=1):
        print(f"    {slot}: {skill_id}")

    # Modify one of the values just to prove the encoder accepts manual input.
    updated = SkillTemplate(
        primary=template.primary,
        secondary=template.secondary,
        attributes=template.attributes + [AttributeEntry(attribute=1, points=3)],
        skills=template.skills,
    )

    encoded_again = EncodeSkillTemplate(updated)
    print("\nRe-encoded template (with an extra attribute entry):")
    print(f"  {encoded_again}")


if __name__ == "__main__":  # pragma: no cover
    main()
