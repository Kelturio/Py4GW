import importlib.util
import pathlib
import sys
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "Py4GWCoreLib" / "SkillTemplate.py"
spec = importlib.util.spec_from_file_location("skill_template", MODULE_PATH)
skill_template = importlib.util.module_from_spec(spec)
sys.modules.setdefault("skill_template", skill_template)
assert spec.loader is not None
spec.loader.exec_module(skill_template)

ATTRIBUTE_NONE_ID = skill_template.ATTRIBUTE_NONE_ID
AttributeEntry = skill_template.AttributeEntry
DecodeSkillTemplate = skill_template.DecodeSkillTemplate
EncodeSkillTemplate = skill_template.EncodeSkillTemplate
SkillTemplate = skill_template.SkillTemplate


class DummyAttribute:
    def __init__(self, attribute_id: int, level: int):
        self.attribute_id = attribute_id
        self.level_base = level
        self.level = level


class SkillTemplateTests(unittest.TestCase):
    def test_round_trip_preserves_values(self):
        template = SkillTemplate(
            primary=3,
            secondary=6,
            attributes=[
                AttributeEntry(attribute=16, points=9),
                AttributeEntry(attribute=9, points=8),
            ],
            skills=[101, 202, 303, 404, 505, 606, 707, 808],
        )
        encoded = EncodeSkillTemplate(template)
        decoded = DecodeSkillTemplate(encoded)

        self.assertEqual(decoded.primary, template.primary)
        self.assertEqual(decoded.secondary, template.secondary)
        decoded_pairs = [(entry.attribute, entry.points) for entry in decoded.attributes]
        expected_pairs = [(entry.attribute, entry.points) for entry in template.attributes]
        self.assertEqual(decoded_pairs, expected_pairs)
        self.assertEqual(decoded.skills, template.skills)

    def test_known_template_round_trip(self):
        build_code = "OQASEDqEC1vcNABWAAAA"
        decoded = DecodeSkillTemplate(build_code)
        self.assertEqual(len(decoded.skills), 8)
        self.assertEqual(EncodeSkillTemplate(decoded), build_code)

    def test_attribute_normalization(self):
        template = SkillTemplate(
            primary=1,
            secondary=2,
            attributes=[
                DummyAttribute(attribute_id=8, level=12),
                AttributeEntry(attribute=ATTRIBUTE_NONE_ID, points=5),
                AttributeEntry(attribute=11, points=0),
            ],
            skills=[1, 2, 3],
        )
        encoded = EncodeSkillTemplate(template)
        decoded = DecodeSkillTemplate(encoded)

        decoded_pairs = [(entry.attribute, entry.points) for entry in decoded.attributes]
        self.assertEqual(decoded_pairs, [(8, 12)])
        self.assertEqual(decoded.skills[:3], [1, 2, 3])
        self.assertEqual(len(decoded.skills), 8)

    def test_invalid_character_raises(self):
        with self.assertRaises(ValueError):
            DecodeSkillTemplate("@@@")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
