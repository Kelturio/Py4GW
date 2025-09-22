"""Utilities for parsing Guild Wars chat logs stored by the Chat Log Saver widget.

This module mirrors the configuration lookup behaviour from
``Widgets/Chat Log Saver.py`` to locate the active log directory before
streaming the individual ``.txt`` files for statistics.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import os
import re
from typing import Dict, Iterable, Iterator, Mapping, MutableMapping, Optional

CONFIG_FILENAME = "ChatLogSaver.ini"
MODULE_NAME = "Chat Log Saver"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _get_project_root() -> str:
    """Return the absolute project root based on this file location."""

    script_directory = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(script_directory, os.pardir, os.pardir))


def get_config_path() -> str:
    """Return the path to the Chat Log Saver configuration file."""

    project_root = _get_project_root()
    config_base = os.path.join(project_root, "Widgets", "Config")
    os.makedirs(config_base, exist_ok=True)
    return os.path.join(config_base, CONFIG_FILENAME)


def get_log_directory(default_subdir: str = "Logs") -> str:
    """Return the resolved log directory configured by Chat Log Saver.

    Parameters
    ----------
    default_subdir:
        Relative folder used when no value is present in the INI file.
    """

    project_root = _get_project_root()
    default_log_dir = os.path.join(project_root, default_subdir)
    config_path = get_config_path()

    log_directory = default_log_dir

    if os.path.exists(config_path):
        from configparser import ConfigParser

        parser = ConfigParser()
        parser.read(config_path, encoding="utf-8")
        if parser.has_option(MODULE_NAME, "log_directory"):
            raw_value = parser.get(MODULE_NAME, "log_directory", fallback="").strip()
            if raw_value:
                log_directory = os.path.expanduser(raw_value)

    if not log_directory:
        log_directory = default_log_dir

    if not os.path.isabs(log_directory):
        log_directory = os.path.abspath(os.path.join(project_root, log_directory))

    return log_directory


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


def _default_counter() -> Counter[str]:
    return Counter()


@dataclass
class RewardTotals:
    """Structured representation of reward lines encountered in a log."""

    faction: Counter[str] = field(default_factory=_default_counter)
    reputation: Counter[str] = field(default_factory=_default_counter)
    reputation_events: Counter[str] = field(default_factory=_default_counter)
    experience: int = 0
    gold: int = 0
    skill_points: int = 0

    def add_faction(self, name: str, amount: int) -> None:
        self.faction[name] += amount

    def add_reputation(self, name: str, amount: int) -> None:
        self.reputation[name] += amount

    def add_reputation_event(self, event: str, amount: int) -> None:
        self.reputation_events[event] += amount

    def add_experience(self, amount: int) -> None:
        self.experience += amount

    def add_gold(self, amount: int) -> None:
        self.gold += amount

    def add_skill_points(self, amount: int = 1) -> None:
        self.skill_points += amount

    def merge(self, other: "RewardTotals") -> None:
        self.faction.update(other.faction)
        self.reputation.update(other.reputation)
        self.reputation_events.update(other.reputation_events)
        self.experience += other.experience
        self.gold += other.gold
        self.skill_points += other.skill_points


@dataclass
class LootTotals:
    """Aggregated loot entries grouped by item name."""

    dropped: Counter[str] = field(default_factory=_default_counter)
    received: Counter[str] = field(default_factory=_default_counter)

    def add_drop(self, item_name: str, quantity: int) -> None:
        self.dropped[item_name] += quantity

    def add_received(self, item_name: str, quantity: int) -> None:
        self.received[item_name] += quantity

    def merge(self, other: "LootTotals") -> None:
        self.dropped.update(other.dropped)
        self.received.update(other.received)


@dataclass
class SessionRecord:
    """Normalized statistics extracted from a single log file."""

    file_name: str
    path: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    kill_milestones: MutableMapping[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    rewards: RewardTotals = field(default_factory=RewardTotals)
    loot: LootTotals = field(default_factory=LootTotals)

    def total_kills(self) -> Counter[str]:
        totals: Counter[str] = Counter()
        for species, milestones in self.kill_milestones.items():
            if milestones:
                totals[species] = max(milestones)
        return totals


@dataclass
class SummaryTotals:
    """Aggregate statistics calculated from multiple sessions."""

    kills: Counter[str] = field(default_factory=_default_counter)
    rewards: RewardTotals = field(default_factory=RewardTotals)
    loot: LootTotals = field(default_factory=LootTotals)

    def add_session(self, session: SessionRecord) -> None:
        self.kills.update(session.total_kills())
        self.rewards.merge(session.rewards)
        self.loot.merge(session.loot)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


TIMESTAMP_RE = re.compile(r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(?P<message>.+)")
KILL_MILESTONE_RE = re.compile(r"^(?P<count>\d+)\s+(?P<target>[A-Za-z ']+?)\s+slain\.")
FACTION_RE = re.compile(r"^You gain\s+(?P<amount>[+\d,]+)\s+(?P<name>[A-Za-z ']+)\s+faction\.")
REPUTATION_RE = re.compile(r"^You gain\s+(?P<amount>[+\d,]+)\s+(?P<name>[A-Za-z ']+)\s+reputation points?\.")
REPUTATION_EVENT_RE = re.compile(
    r"^You gain\s+(?P<amount>[+\d,]+)\s+reputation points for defeating\s+(?P<target>.+?)\."
)
GAIN_EXPERIENCE_RE = re.compile(r"^You gain\s+(?P<amount>[+\d,]+)\s+experience\.")
EARN_EXPERIENCE_RE = re.compile(
    r"^You have earned\s+(?P<exp>[+\d,]+)\s+experience(?:\s+and\s+(?P<gold>[+\d,]+)\s+gold)?!"
)
EARN_EXPERIENCE_SKILL_RE = re.compile(
    r"^You have earned\s+(?P<exp>[+\d,]+)\s+experience\s+and\s+(?P<skill>[+\d,]+)\s+skill point(?:s)?!"
)
EARN_GOLD_SKILL_RE = re.compile(
    r"^You have earned\s+(?P<gold>[+\d,]+)\s+gold\s+and\s+(?P<skill>[+\d,]+)\s+skill point(?:s)?!"
)
SIMPLE_SKILL_GAIN_RE = re.compile(r"^You gain a skill point!")
DROP_RE = re.compile(r"^(?P<source>.+?)\s+drops\s+(?P<item>.+)")
RECEIVE_RE = re.compile(r"^You receive\s+(?P<item>.+)")


def _parse_number(raw_value: str) -> int:
    return int(raw_value.replace(",", "").replace("+", "").strip())


def _clean_item_text(text: str) -> str:
    text = text.strip()
    # Remove trailing reservation or ownership clauses.
    text = re.sub(r",\s+which.+$", "", text)
    text = re.sub(r",\s+and.+$", "", text)
    return text.rstrip(".").strip()


def _parse_item_quantity(text: str) -> tuple[str, int]:
    clean_text = _clean_item_text(text)
    if not clean_text:
        return "", 0

    if clean_text.lower().startswith("an "):
        return clean_text[3:].strip(), 1
    if clean_text.lower().startswith("a "):
        return clean_text[2:].strip(), 1

    match = re.match(r"^(?P<count>[+\d,]+)\s+(?P<item>.+)$", clean_text)
    if match:
        count = _parse_number(match.group("count"))
        return match.group("item").strip(), count

    return clean_text, 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_log_lines(file_name: str, lines: Iterable[str], *, path: str = "") -> SessionRecord:
    """Parse a sequence of log lines and return a :class:`SessionRecord`."""

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    kill_milestones: MutableMapping[str, list[int]] = defaultdict(list)
    rewards = RewardTotals()
    loot = LootTotals()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        match = TIMESTAMP_RE.match(line)
        if not match:
            continue

        timestamp_str = match.group("timestamp")
        message = match.group("message").strip()

        try:
            current_time = datetime.strptime(timestamp_str, TIMESTAMP_FORMAT)
        except ValueError:
            continue

        if start_time is None or current_time < start_time:
            start_time = current_time
        if end_time is None or current_time > end_time:
            end_time = current_time

        kill_match = KILL_MILESTONE_RE.match(message)
        if kill_match:
            count = _parse_number(kill_match.group("count"))
            target = kill_match.group("target").strip().lower()
            kill_milestones[target].append(count)
            continue

        faction_match = FACTION_RE.match(message)
        if faction_match:
            rewards.add_faction(faction_match.group("name").strip(), _parse_number(faction_match.group("amount")))
            continue

        reputation_match = REPUTATION_RE.match(message)
        if reputation_match:
            rewards.add_reputation(
                reputation_match.group("name").strip(), _parse_number(reputation_match.group("amount"))
            )
            continue

        reputation_event_match = REPUTATION_EVENT_RE.match(message)
        if reputation_event_match:
            rewards.add_reputation_event(
                reputation_event_match.group("target").strip(),
                _parse_number(reputation_event_match.group("amount")),
            )
            continue

        gain_experience_match = GAIN_EXPERIENCE_RE.match(message)
        if gain_experience_match:
            rewards.add_experience(_parse_number(gain_experience_match.group("amount")))
            continue

        if SIMPLE_SKILL_GAIN_RE.match(message):
            rewards.add_skill_points()
            continue

        earn_experience_skill_match = EARN_EXPERIENCE_SKILL_RE.match(message)
        if earn_experience_skill_match:
            rewards.add_experience(_parse_number(earn_experience_skill_match.group("exp")))
            rewards.add_skill_points(_parse_number(earn_experience_skill_match.group("skill")))
            continue

        earn_gold_skill_match = EARN_GOLD_SKILL_RE.match(message)
        if earn_gold_skill_match:
            rewards.add_gold(_parse_number(earn_gold_skill_match.group("gold")))
            rewards.add_skill_points(_parse_number(earn_gold_skill_match.group("skill")))
            continue

        earn_experience_match = EARN_EXPERIENCE_RE.match(message)
        if earn_experience_match:
            rewards.add_experience(_parse_number(earn_experience_match.group("exp")))
            gold_value = earn_experience_match.group("gold")
            if gold_value:
                rewards.add_gold(_parse_number(gold_value))
            continue

        drop_match = DROP_RE.match(message)
        if drop_match:
            item_name, quantity = _parse_item_quantity(drop_match.group("item"))
            if item_name:
                loot.add_drop(item_name, quantity)
            continue

        receive_match = RECEIVE_RE.match(message)
        if receive_match:
            item_name, quantity = _parse_item_quantity(receive_match.group("item"))
            if item_name:
                loot.add_received(item_name, quantity)
            continue

    return SessionRecord(
        file_name=file_name,
        path=path or file_name,
        start_time=start_time,
        end_time=end_time,
        kill_milestones=kill_milestones,
        rewards=rewards,
        loot=loot,
    )


def parse_log_file(path: str) -> SessionRecord:
    """Parse a log file from disk."""

    with open(path, "r", encoding="utf-8") as handle:
        return parse_log_lines(os.path.basename(path), handle, path=path)


def iter_log_files(directory: Optional[str] = None) -> Iterator[str]:
    """Yield log file paths from the configured directory."""

    directory = directory or get_log_directory()
    if not os.path.isdir(directory):
        return iter(())
    for entry in sorted(os.listdir(directory)):
        if entry.lower().endswith(".txt"):
            yield os.path.join(directory, entry)


def parse_log_directory(directory: Optional[str] = None) -> Dict[str, SessionRecord]:
    """Parse all logs within a directory and return keyed by filename."""

    records: Dict[str, SessionRecord] = {}
    for file_path in iter_log_files(directory):
        record = parse_log_file(file_path)
        records[record.file_name] = record
    return records


def summarize_sessions(sessions: Mapping[str, SessionRecord]) -> SummaryTotals:
    """Return an aggregate summary for multiple session records."""

    summary = SummaryTotals()
    for record in sessions.values():
        summary.add_session(record)
    return summary


__all__ = [
    "LootTotals",
    "RewardTotals",
    "SessionRecord",
    "SummaryTotals",
    "get_config_path",
    "get_log_directory",
    "iter_log_files",
    "parse_log_directory",
    "parse_log_file",
    "parse_log_lines",
    "summarize_sessions",
]
