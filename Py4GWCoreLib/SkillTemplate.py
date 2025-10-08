"""Utilities for working with Guild Wars skill templates.

This module provides a pure Python implementation of the bit packing logic
used by GWToolbox and GWCA to encode and decode skill templates.  The code is
heavily inspired by the original C++ implementation located in
``Dependencies/GWCA/Source/SkillbarMgr.cpp`` but exposes a Python friendly API
that can be used by bots and widgets without touching the native layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

BASE64_TABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
BASE64_TO_VALUE = {ch: idx for idx, ch in enumerate(BASE64_TABLE)}

TEMPLATE_HEADER = 14
TEMPLATE_VERSION = 0

MAX_SKILL_SLOTS = 8
MAX_ATTRIBUTE_ENTRIES = 16
# Value taken from ``Py4GWCoreLib/enums_src/GameData_enums.py``.
ATTRIBUTE_NONE_ID = 45


@dataclass(slots=True)
class AttributeEntry:
    """Represents a single attribute investment entry."""

    attribute: int
    points: int


@dataclass(slots=True)
class SkillTemplate:
    """Container describing a build template."""

    primary: int = 0
    secondary: int = 0
    attributes: List[AttributeEntry] = field(default_factory=list)
    skills: List[int] = field(default_factory=list)

    def normalized(self) -> "SkillTemplate":
        """Return a normalized copy of the template.

        The normalization step ensures the skill list contains exactly eight
        entries (padded with zeros), filters out zero-point attribute entries,
        and clamps obvious out-of-range values.
        """

        attrs: list[AttributeEntry] = []
        for entry in self.attributes:
            attr_id = int(getattr(entry, "attribute", getattr(entry, "attribute_id", entry[0] if isinstance(entry, (list, tuple)) and entry else 0)))
            points = int(getattr(entry, "points", getattr(entry, "level_base", getattr(entry, "level", entry[1] if isinstance(entry, (list, tuple)) and len(entry) > 1 else 0))))
            if attr_id == ATTRIBUTE_NONE_ID:
                continue
            if points <= 0:
                continue
            attrs.append(AttributeEntry(attribute=attr_id, points=points))
            if len(attrs) >= MAX_ATTRIBUTE_ENTRIES:
                break

        skills = [int(skill) if skill else 0 for skill in self.skills[:MAX_SKILL_SLOTS]]
        if len(skills) < MAX_SKILL_SLOTS:
            skills.extend([0] * (MAX_SKILL_SLOTS - len(skills)))

        return SkillTemplate(
            primary=int(self.primary or 0),
            secondary=int(self.secondary or 0),
            attributes=attrs,
            skills=skills,
        )


def _write_bits(buffer: List[int], value: int, count: int) -> None:
    for i in range(count):
        buffer.append((value >> i) & 1)


def _read_bits(bits: Sequence[int], offset: int, count: int) -> tuple[int, int]:
    if offset + count > len(bits):
        raise ValueError("Not enough bits remaining to satisfy read request")
    value = 0
    for i in range(count):
        value |= (bits[offset + i] << i)
    return value, offset + count


def encode_skill_template(template: SkillTemplate) -> str:
    """Encode a :class:`SkillTemplate` into a Guild Wars build string."""

    normalized = template.normalized()

    bits: list[int] = []
    _write_bits(bits, TEMPLATE_HEADER, 4)
    _write_bits(bits, TEMPLATE_VERSION, 4)

    # Professions
    bits_per_prof = max(4, normalized.primary.bit_length(), normalized.secondary.bit_length())
    if bits_per_prof % 2:
        bits_per_prof += 1
    bits_per_prof = max(bits_per_prof, 4)
    prof_code = (bits_per_prof - 4) // 2
    _write_bits(bits, prof_code, 2)
    _write_bits(bits, normalized.primary, bits_per_prof)
    _write_bits(bits, normalized.secondary, bits_per_prof)

    # Attributes
    if normalized.attributes:
        bits_per_attr = max(4, max(entry.attribute.bit_length() for entry in normalized.attributes))
    else:
        bits_per_attr = 4
    _write_bits(bits, len(normalized.attributes), 4)
    _write_bits(bits, bits_per_attr - 4, 4)
    for entry in normalized.attributes:
        _write_bits(bits, entry.attribute, bits_per_attr)
        _write_bits(bits, entry.points, 4)

    # Skills
    bits_per_skill = max(8, max((skill.bit_length() for skill in normalized.skills), default=0))
    _write_bits(bits, bits_per_skill - 8, 4)
    for skill in normalized.skills:
        _write_bits(bits, skill, bits_per_skill)

    # Pad to 6 bits and encode as base64
    remainder = len(bits) % 6
    if remainder:
        for _ in range(6 - remainder):
            bits.append(0)

    result_chars: list[str] = []
    for i in range(0, len(bits), 6):
        value = 0
        for j in range(6):
            value |= (bits[i + j] << j)
        result_chars.append(BASE64_TABLE[value])

    return "".join(result_chars)


def decode_skill_template(build_code: str) -> SkillTemplate:
    """Decode a Guild Wars build string into a :class:`SkillTemplate`."""

    bit_stream: list[int] = []
    for ch in build_code.strip():
        if ch not in BASE64_TO_VALUE:
            raise ValueError(f"Invalid base64 character '{ch}' in template")
        numeric_value = BASE64_TO_VALUE[ch]
        _write_bits(bit_stream, numeric_value, 6)

    offset = 0
    header, offset = _read_bits(bit_stream, offset, 4)
    if header not in (0, TEMPLATE_HEADER):
        raise ValueError(f"Unsupported template header: {header}")
    if header == TEMPLATE_HEADER:
        # Skip version
        _, offset = _read_bits(bit_stream, offset, 4)

    bits_per_prof_code, offset = _read_bits(bit_stream, offset, 2)
    bits_per_prof = bits_per_prof_code * 2 + 4
    primary, offset = _read_bits(bit_stream, offset, bits_per_prof)
    secondary, offset = _read_bits(bit_stream, offset, bits_per_prof)

    attrib_count, offset = _read_bits(bit_stream, offset, 4)
    bits_per_attr_offset, offset = _read_bits(bit_stream, offset, 4)
    bits_per_attr = bits_per_attr_offset + 4
    attributes: list[AttributeEntry] = []
    for _ in range(min(attrib_count, MAX_ATTRIBUTE_ENTRIES)):
        attribute_id, offset = _read_bits(bit_stream, offset, bits_per_attr)
        points, offset = _read_bits(bit_stream, offset, 4)
        if points <= 0 or attribute_id == ATTRIBUTE_NONE_ID:
            continue
        attributes.append(AttributeEntry(attribute=attribute_id, points=points))

    bits_per_skill_offset, offset = _read_bits(bit_stream, offset, 4)
    bits_per_skill = bits_per_skill_offset + 8
    skills: list[int] = []
    for _ in range(MAX_SKILL_SLOTS):
        if offset + bits_per_skill > len(bit_stream):
            break
        skill_id, offset = _read_bits(bit_stream, offset, bits_per_skill)
        skills.append(skill_id)
    if len(skills) < MAX_SKILL_SLOTS:
        skills.extend([0] * (MAX_SKILL_SLOTS - len(skills)))

    return SkillTemplate(primary=primary, secondary=secondary, attributes=attributes, skills=skills)


# Convenience aliases using the naming convention from the native layer.
def EncodeSkillTemplate(template: SkillTemplate) -> str:
    return encode_skill_template(template)


def DecodeSkillTemplate(build_code: str) -> SkillTemplate:
    return decode_skill_template(build_code)


__all__ = [
    "AttributeEntry",
    "SkillTemplate",
    "EncodeSkillTemplate",
    "DecodeSkillTemplate",
    "encode_skill_template",
    "decode_skill_template",
]
