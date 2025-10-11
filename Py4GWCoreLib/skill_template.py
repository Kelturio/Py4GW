"""Utilities for working with Guild Wars skill template codes.

This module provides a pure Python implementation of the encoding and

decoding routines that GWToolbox/GWCA expose via the C++ API.  The
implementation follows the bit packing strategy used by the original
client so that build codes generated here remain compatible with the game
client and community tooling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

__all__ = [
    "SkillAttribute",
    "SkillTemplate",
    "make_skill_template",
    "encode_skill_template",
    "decode_skill_template",
]

_BASE64_TABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_BASE64_LOOKUP = {ch: idx for idx, ch in enumerate(_BASE64_TABLE)}
_TEMPLATE_TYPE_SKILL = 14
_SKILL_COUNT = 8
_ATTRIBUTE_MAX = 16
_ATTRIBUTE_NONE_ID = 45  # Mirrors GW::Constants::Attribute::None


def _normalise_profession(profession: object) -> int:
    """Best-effort conversion of ``profession`` into an integer id."""

    if profession is None:
        return 0

    if isinstance(profession, int):
        return profession

    # ``PyAgent.Profession`` instances expose ``ToInt``/``Get`` helpers.
    for accessor_name in ("ToInt", "Get"):
        accessor = getattr(profession, accessor_name, None)
        if callable(accessor):
            try:
                value = accessor()
            except Exception:  # pragma: no cover - defensive conversion.
                continue
            try:
                return int(value)
            except Exception:  # pragma: no cover - defensive conversion.
                continue

    for attribute_name in ("value", "profession", "id"):
        value = getattr(profession, attribute_name, None)
        if isinstance(value, int):
            return value

    if isinstance(profession, str):
        lowered = profession.strip().lower()
        if not lowered or lowered in {"none", "_none"}:
            return 0
        try:
            return int(profession)
        except ValueError:
            return 0

    try:
        return int(profession)
    except Exception:  # pragma: no cover - defensive conversion.
        return 0


@dataclass(frozen=True)
class SkillAttribute:
    """Attribute investment used within a skill template."""

    attribute: int
    points: int

    def __post_init__(self) -> None:
        if self.attribute < 0:
            raise ValueError("attribute id must be non-negative")
        if self.points < 0:
            raise ValueError("attribute points must be non-negative")


@dataclass(frozen=True)
class SkillTemplate:
    """Represents the data stored in a Guild Wars skill template."""

    primary: int
    secondary: int
    skills: tuple[int, ...]
    attributes: tuple[SkillAttribute, ...]

    def __post_init__(self) -> None:
        if self.primary < 0 or self.secondary < 0:
            raise ValueError("profession ids must be non-negative")
        if len(self.skills) != _SKILL_COUNT:
            raise ValueError(f"skill list must contain {_SKILL_COUNT} elements")
        if len(self.attributes) > _ATTRIBUTE_MAX:
            raise ValueError(f"attribute list must not exceed {_ATTRIBUTE_MAX} entries")


def _write_bits(value: int, count: int, buffer: list[int]) -> None:
    """Append ``count`` bits of ``value`` to ``buffer`` (little-endian)."""

    for i in range(count):
        buffer.append((value >> i) & 1)


def _read_bits(bits: list[int], count: int, offset: int) -> tuple[int, int]:
    """Read ``count`` bits from ``bits`` starting at ``offset`` (little-endian)."""

    value = 0
    for i in range(count):
        if offset + i >= len(bits):
            raise ValueError("unexpected end of bitstream while decoding skill template")
        value |= bits[offset + i] << i
    return value, offset + count


def _normalise_skills(skills: Iterable[int]) -> tuple[int, ...]:
    skill_list = list(skills)
    if len(skill_list) > _SKILL_COUNT:
        raise ValueError(f"skill list must not exceed {_SKILL_COUNT} entries")
    while len(skill_list) < _SKILL_COUNT:
        skill_list.append(0)
    return tuple(int(skill) for skill in skill_list)


def _normalise_attributes(attributes: Iterable[object]) -> tuple[SkillAttribute, ...]:
    normalised: list[SkillAttribute] = []
    for attribute in attributes:
        if isinstance(attribute, SkillAttribute):
            candidate = attribute
        elif isinstance(attribute, tuple) and len(attribute) >= 2:
            candidate = SkillAttribute(int(attribute[0]), int(attribute[1]))
        else:
            attr_id = getattr(attribute, "attribute", None)
            points = getattr(attribute, "points", None)
            if attr_id is None or points is None:
                attr_id = getattr(attribute, "attribute_id", None)
                points = getattr(attribute, "level", None)
            if attr_id is None or points is None:
                continue
            candidate = SkillAttribute(int(attr_id), int(points))

        if candidate.attribute == _ATTRIBUTE_NONE_ID or candidate.points == 0:
            continue
        normalised.append(candidate)

    if len(normalised) > _ATTRIBUTE_MAX:
        raise ValueError(f"attribute list must not exceed {_ATTRIBUTE_MAX} non-zero entries")
    return tuple(normalised)


def make_skill_template(
    *,
    primary: int,
    secondary: int,
    skills: Iterable[int],
    attributes: Iterable[object] = (),
) -> SkillTemplate:
    """Create a :class:`SkillTemplate` from raw data collections.

    ``attributes`` accepts :class:`SkillAttribute` instances, ``(id, points)``
    tuples or objects that expose ``attribute``/``points`` or
    ``attribute_id``/``level`` properties (matching the GWCA structures).
    """

    return SkillTemplate(
        primary=_normalise_profession(primary),
        secondary=_normalise_profession(secondary),
        skills=_normalise_skills(skills),
        attributes=_normalise_attributes(attributes),
    )


def encode_skill_template(template: SkillTemplate) -> str:
    """Encode ``template`` into a Guild Wars build code string."""

    bits: list[int] = []
    _write_bits(_TEMPLATE_TYPE_SKILL, 4, bits)
    _write_bits(0, 4, bits)  # Version

    bits_per_prof = max(template.primary.bit_length(), template.secondary.bit_length(), 4)
    # Clamp to even increments of 2 bits above 4 (GW encodes as floor((bits-4)/2))
    prof_code = max(0, (bits_per_prof - 4) // 2)
    bits_per_prof = prof_code * 2 + 4
    _write_bits(prof_code, 2, bits)
    _write_bits(template.primary, bits_per_prof, bits)
    _write_bits(template.secondary, bits_per_prof, bits)

    bits_per_attr = 4
    for attribute in template.attributes:
        if attribute.attribute > 0:
            bits_per_attr = max(bits_per_attr, attribute.attribute.bit_length())
    _write_bits(len(template.attributes), 4, bits)
    _write_bits(bits_per_attr - 4, 4, bits)
    for attribute in template.attributes:
        _write_bits(attribute.attribute, bits_per_attr, bits)
        _write_bits(attribute.points, 4, bits)

    bits_per_skill = 8
    for skill in template.skills:
        if skill > 0:
            bits_per_skill = max(bits_per_skill, skill.bit_length())
    _write_bits(bits_per_skill - 8, 4, bits)
    for skill in template.skills:
        _write_bits(skill, bits_per_skill, bits)

    padding = (-len(bits)) % 6
    if padding:
        bits.extend([0] * padding)
    # Match GW's behaviour by appending an additional zero sextet so build codes
    # retain the conventional trailing 'A'.
    bits.extend([0] * 6)

    output = []
    for idx in range(0, len(bits), 6):
        value = 0
        for i in range(6):
            value |= bits[idx + i] << i
        output.append(_BASE64_TABLE[value])
    return "".join(output)


def decode_skill_template(code: str) -> SkillTemplate:
    """Decode a Guild Wars build ``code`` into a :class:`SkillTemplate`."""

    if not code:
        raise ValueError("skill template code must not be empty")

    bits: list[int] = []
    for ch in code.strip():
        if ch not in _BASE64_LOOKUP:
            raise ValueError(f"invalid base64 character '{ch}' in skill template")
        value = _BASE64_LOOKUP[ch]
        _write_bits(value, 6, bits)

    offset = 0
    header, offset = _read_bits(bits, 4, offset)
    if header not in (0, _TEMPLATE_TYPE_SKILL):
        raise ValueError(f"unsupported template header {header}")
    if header == _TEMPLATE_TYPE_SKILL:
        _, offset = _read_bits(bits, 4, offset)  # Version (unused)

    prof_code, offset = _read_bits(bits, 2, offset)
    bits_per_prof = prof_code * 2 + 4
    primary, offset = _read_bits(bits, bits_per_prof, offset)
    secondary, offset = _read_bits(bits, bits_per_prof, offset)

    attrib_count, offset = _read_bits(bits, 4, offset)
    bits_per_attr_delta, offset = _read_bits(bits, 4, offset)
    bits_per_attr = bits_per_attr_delta + 4
    attributes: list[SkillAttribute] = []
    for _ in range(min(attrib_count, _ATTRIBUTE_MAX)):
        attr_id, offset = _read_bits(bits, bits_per_attr, offset)
        points, offset = _read_bits(bits, 4, offset)
        if attr_id == _ATTRIBUTE_NONE_ID or points == 0:
            continue
        attributes.append(SkillAttribute(attr_id, points))

    bits_per_skill_delta, offset = _read_bits(bits, 4, offset)
    bits_per_skill = bits_per_skill_delta + 8
    skills: list[int] = []
    for _ in range(_SKILL_COUNT):
        if offset + bits_per_skill > len(bits):
            break
        skill_id, offset = _read_bits(bits, bits_per_skill, offset)
        skills.append(skill_id)
    skills = _normalise_skills(skills)

    return SkillTemplate(primary, secondary, skills, tuple(attributes))
