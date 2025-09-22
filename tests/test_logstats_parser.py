import os
import unittest
from datetime import datetime

from Widgets.LogStats import parser


class LogParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config_path = parser.get_config_path()
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(self.config_path)))
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as handle:
                self._original_config = handle.read()
        else:
            self._original_config = None

    def tearDown(self) -> None:
        if self._original_config is None:
            if os.path.exists(self.config_path):
                os.remove(self.config_path)
        else:
            with open(self.config_path, "w", encoding="utf-8") as handle:
                handle.write(self._original_config)

    def test_get_log_directory_uses_default_when_missing(self) -> None:
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

        expected = os.path.join(self.project_root, "Logs")
        self.assertEqual(parser.get_log_directory(), expected)

    def test_get_log_directory_honours_custom_value(self) -> None:
        with open(self.config_path, "w", encoding="utf-8") as handle:
            handle.write("[Chat Log Saver]\nlog_directory = CustomLogs\n")

        expected = os.path.join(self.project_root, "CustomLogs")
        self.assertEqual(parser.get_log_directory(), expected)

    def test_parse_sample_session(self) -> None:
        session_lines = [
            "[2025-09-19 13:27:03] 5 enemies slain.",
            "[2025-09-19 13:33:00] You gain 250 Kurzick faction.",
            "[2025-09-19 13:33:04] Stone Reaper drops 18 Piles of Glittering Dust, which your party reserves for Pelznickel Searinox.",
            "[2025-09-19 13:33:07] You receive 1 Imperial Commendation.",
            "[2025-09-19 13:41:48] You gain 15,800 Kurzick faction.",
            "[2025-09-19 13:41:48] You gain +150 reputation points for defeating Rekoff Broodmother.",
            "[2025-09-19 13:44:10] 95 enemies slain.",
            "[2025-09-19 13:44:20] Olias drops an Ashes of Protective Kaolai.",
            "[2025-09-19 13:45:27] 105 enemies slain.",
            "[2025-09-19 14:00:12] You gain a skill point!",
            "[2025-09-19 14:00:12] You have earned 1,580 experience and 1,580 gold!",
            "[2025-09-19 14:00:24] Your party shares 110 gold.",
        ]

        record = parser.parse_log_lines("sample_log.txt", session_lines)

        self.assertEqual(record.start_time, datetime(2025, 9, 19, 13, 27, 3))
        self.assertEqual(record.end_time, datetime(2025, 9, 19, 14, 0, 24))
        self.assertEqual(record.kill_milestones["enemies"], [5, 95, 105])
        self.assertEqual(record.rewards.faction["Kurzick"], 16050)
        self.assertEqual(record.rewards.reputation_events["Rekoff Broodmother"], 150)
        self.assertEqual(record.rewards.experience, 1580)
        self.assertEqual(record.rewards.gold, 1580)
        self.assertEqual(record.rewards.skill_points, 1)
        self.assertEqual(record.loot.dropped["Ashes of Protective Kaolai"], 1)
        self.assertEqual(record.loot.dropped["Piles of Glittering Dust"], 18)
        self.assertEqual(record.loot.received["Imperial Commendation"], 1)

    def test_session_summary_aggregates_multiple_logs(self) -> None:
        session_one = parser.parse_log_lines(
            "session_one.txt",
            [
                "[2025-09-19 13:27:03] 5 enemies slain.",
                "[2025-09-19 13:45:27] 105 enemies slain.",
                "[2025-09-19 13:33:00] You gain 250 Kurzick faction.",
                "[2025-09-19 13:41:48] You gain 15,800 Kurzick faction.",
                "[2025-09-19 13:41:48] You gain +150 reputation points for defeating Rekoff Broodmother.",
                "[2025-09-19 14:00:12] You have earned 1,580 experience and 1,580 gold!",
                "[2025-09-19 14:00:12] You gain a skill point!",
                "[2025-09-19 13:44:20] Olias drops an Ashes of Protective Kaolai.",
                "[2025-09-19 13:33:04] Stone Reaper drops 18 Piles of Glittering Dust, which your party reserves for Pelznickel Searinox.",
                "[2025-09-19 13:33:07] You receive 1 Imperial Commendation.",
            ],
        )

        session_two = parser.parse_log_lines(
            "session_two.txt",
            [
                "[2025-09-19 19:50:59] 5 heket slain.",
                "[2025-09-19 19:51:50] 10 heket slain.",
                "[2025-09-19 19:53:00] You gain 25 Asura reputation points.",
                "[2025-09-19 19:53:05] You gain 3,000 experience.",
                "[2025-09-19 19:53:10] You have earned 1,000 experience and 1 skill point!",
                "[2025-09-19 19:53:15] Krait drops 2 Gold Doubloons.",
                "[2025-09-19 19:53:20] You receive 175 gold.",
                "[2025-09-19 19:53:25] You receive an Amber Longbow.",
                "[2025-09-19 19:53:30] You have earned 2,035 experience and 2,035 gold!",
                "[2025-09-19 19:53:35] You receive 3 Lockpicks.",
                "[2025-09-19 19:53:40] You have earned 1,000 experience!",
                "[2025-09-19 19:53:45] You receive a Deldrimor Armor Remnant.",
            ],
        )

        summary = parser.summarize_sessions({
            session_one.file_name: session_one,
            session_two.file_name: session_two,
        })

        self.assertEqual(summary.kills["enemies"], 105)
        self.assertEqual(summary.kills["heket"], 10)
        self.assertEqual(summary.rewards.faction["Kurzick"], 16050)
        self.assertEqual(summary.rewards.reputation["Asura"], 25)
        self.assertEqual(summary.rewards.reputation_events["Rekoff Broodmother"], 150)
        self.assertEqual(summary.rewards.experience, 8615)
        self.assertEqual(summary.rewards.gold, 3615)
        self.assertEqual(summary.rewards.skill_points, 2)
        self.assertEqual(summary.loot.dropped["Ashes of Protective Kaolai"], 1)
        self.assertEqual(summary.loot.dropped["Piles of Glittering Dust"], 18)
        self.assertEqual(summary.loot.dropped["Gold Doubloons"], 2)
        self.assertEqual(summary.loot.received["Imperial Commendation"], 1)
        self.assertEqual(summary.loot.received["gold"], 175)
        self.assertEqual(summary.loot.received["Amber Longbow"], 1)
        self.assertEqual(summary.loot.received["Lockpicks"], 3)
        self.assertEqual(summary.loot.received["Deldrimor Armor Remnant"], 1)


if __name__ == "__main__":
    unittest.main()
