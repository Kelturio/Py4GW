"""Interactive Guild Wars skill template demonstration with PyImGui controls.

This example mirrors the GWToolbox/GWCA skill template encoding and decoding
logic while exposing a PyImGui-driven interface for inspecting templates in
real time. Actions are throttled so they only run when triggered via the GUI,
preventing the script from spamming the Py4GW console when ``main`` is called
repeatedly by the in-game loader.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List

TEMPLATE_CODE = "OAhjQkGZIP3hhWVV4JNncDzxJ"
TEMPLATE_SKILL_NAMES = [
    "Blood is Power",
    "Blood Bond",
    "Signet of Lost Souls",
    "Spirit Transfer",
    "Mend Body and Soul",
    "Spirit Light",
    "Protective Was Kaolai",
    "Life",
]


def _resolve_root() -> Path:
    """Determine the project root even when ``__file__`` is unavailable."""

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


def _load_module(name: str, relative_path: str) -> Any:
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


skill_template = _load_module("py4gw_skill_template_example", "Py4GWCoreLib/skill_template.py")
gamedata = _load_module("py4gw_gamedata_example", "Py4GWCoreLib/enums_src/GameData_enums.py")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # Importing Py4GWCoreLib initialises GLOBAL_CACHE for in-game execution.
    from Py4GWCoreLib import GLOBAL_CACHE, PyImGui  # type: ignore
except Exception:  # pragma: no cover - only triggered in non-game contexts.
    GLOBAL_CACHE = None  # type: ignore
    PyImGui = None  # type: ignore


def _load_skill_data() -> dict[int, dict[str, Any]]:
    with (ROOT / "Py4GWCoreLib" / "skill_descriptions.json").open(encoding="utf-8") as handle:
        raw: dict[str, dict[str, Any]] = json.load(handle)
    return {int(skill_id): entry for skill_id, entry in raw.items() if "name" in entry}


def _lookup_skill_ids(names: list[str], lookup: dict[int, dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    name_map = {entry.get("name"): skill_id for skill_id, entry in lookup.items() if "name" in entry}
    for name in names:
        skill_id = name_map.get(name)
        if skill_id is None:
            raise KeyError(f"Unable to resolve skill name: {name}")
        ids.append(skill_id)
    return ids


def _describe_template(
    code: str,
    skill_lookup: dict[int, dict[str, Any]],
    log: Callable[[str], None],
    *,
    heading: str = "Decoded template",
) -> None:
    template = skill_template.decode_skill_template(code)

    log(heading)
    log("-" * len(heading))
    log(f"Primary profession : {gamedata.Profession(template.primary).name}")
    log(f"Secondary profession: {gamedata.Profession(template.secondary).name}")

    log("Skills")
    log("------")
    for index, skill_id in enumerate(template.skills, start=1):
        skill_name = skill_lookup.get(skill_id, {}).get("name", f"ID {skill_id}")
        log(f"{index:>2}. {skill_name}")

    log("Attributes")
    log("----------")
    for attribute in template.attributes:
        attr_enum = gamedata.Attribute(attribute.attribute)
        log(f"{attr_enum.name}: {attribute.points}")

    round_trip = skill_template.encode_skill_template(template)
    log("")
    log(f"Round-trip encoding produces: {round_trip}")


def _build_sample_template(skill_lookup: dict[int, dict[str, Any]], log: Callable[[str], None]) -> str:
    skills = _lookup_skill_ids(TEMPLATE_SKILL_NAMES, skill_lookup)
    template = skill_template.make_skill_template(
        primary=gamedata.Profession.Necromancer,
        secondary=gamedata.Profession.Ritualist,
        skills=skills,
        attributes=[
            (gamedata.Attribute.RestorationMagic, 12),
            (gamedata.Attribute.BloodMagic, 9),
            (gamedata.Attribute.SoulReaping, 9),
        ],
    )
    code = skill_template.encode_skill_template(template)
    log(f"Rebuilt template from structured data: {code}")
    _describe_template(code, skill_lookup, log, heading="Sample build details")
    return code


class _ActionThrottle:
    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._last: Dict[str, float] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        last = self._last.get(key, 0.0)
        if now - last >= self.interval:
            self._last[key] = now
            return True
        return False


class SkillTemplateUIState:
    """Encapsulates the PyImGui-driven UI and throttled actions."""

    MAX_LOG_LINES = 200
    DEFAULT_ACTION_THROTTLE = 1.0

    def __init__(self) -> None:
        self.skill_lookup = _load_skill_data()
        self.template_code = TEMPLATE_CODE
        self.log_lines: Deque[str] = deque(maxlen=self.MAX_LOG_LINES)
        self.action_throttle = self.DEFAULT_ACTION_THROTTLE
        self._throttler = _ActionThrottle(self.action_throttle)
        self._cli_ran = False

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------
    def log(self, message: str = "") -> None:
        formatted = f"[SkillTemplate] {message}" if message else ""
        if formatted:
            print(formatted)
            self.log_lines.append(formatted)
        else:
            print("")
            self.log_lines.append("")

    # ------------------------------------------------------------------
    # Action helpers
    # ------------------------------------------------------------------
    def _with_throttle(self, key: str, action: Callable[[], None]) -> None:
        self._throttler.interval = self.action_throttle
        if not self._throttler.allow(key):
            return
        try:
            action()
        except Exception as exc:  # pragma: no cover - defensive logging for in-game runtime.
            self.log(f"Action '{key}' failed: {exc}")

    def _describe_code(self, code: str, *, heading: str) -> None:
        if not code:
            self.log("No template code provided.")
            return
        self.log(f"Describing template: {code}")
        _describe_template(code, self.skill_lookup, self.log, heading=heading)

    def decode_input(self) -> None:
        self._describe_code(self.template_code.strip(), heading="Input template details")

    def describe_sample(self) -> None:
        self._describe_code(TEMPLATE_CODE, heading="Sample template details")

    def rebuild_sample(self) -> None:
        self.log("Rebuilding sample template from structured data...")
        _build_sample_template(self.skill_lookup, self.log)

    def encode_player_skillbar(self) -> None:
        if GLOBAL_CACHE is None:
            self.log(
                "GLOBAL_CACHE is unavailable; unable to encode player skillbar outside the game environment."
            )
            return

        try:
            GLOBAL_CACHE.SkillBar._update_cache()
        except AttributeError:
            pass

        try:
            player_code = GLOBAL_CACHE.SkillBar.EncodeSkillTemplate()
        except Exception as exc:
            self.log(f"Failed to encode player skillbar: {exc}")
            return

        self.log(f"Current player's skill template: {player_code}")
        self._describe_code(player_code, heading="Player skill template details")

    def dump_hero_templates(self) -> None:
        if GLOBAL_CACHE is None:
            self.log("GLOBAL_CACHE is unavailable; unable to inspect hero skillbars.")
            return

        try:
            GLOBAL_CACHE.Party._update_cache()
        except AttributeError:
            pass
        try:
            GLOBAL_CACHE.SkillBar._update_cache()
        except AttributeError:
            pass

        heroes = GLOBAL_CACHE.Party.GetHeroes()
        if not heroes:
            self.log("No heroes currently in the party.")
            return

        for index, hero in enumerate(heroes, start=1):
            try:
                hero_name = hero.hero_id.GetName()
            except Exception:
                hero_name = f"Hero #{index}"

            skillbar = GLOBAL_CACHE.SkillBar.GetHeroSkillbar(index) or []
            skill_ids: List[int] = []
            for skill in skillbar:
                skill_id = 0
                skill_obj = getattr(skill, "id", None)
                try:
                    if hasattr(skill_obj, "id"):
                        skill_id = int(getattr(skill_obj, "id"))
                    elif isinstance(skill_obj, int):
                        skill_id = int(skill_obj)
                    elif hasattr(skill, "skill_id"):
                        skill_id = int(getattr(skill, "skill_id"))
                except Exception:
                    skill_id = 0
                if skill_id:
                    skill_ids.append(skill_id)

            try:
                attributes = GLOBAL_CACHE.Agent.GetAttributes(hero.agent_id)
            except Exception:
                attributes = []
            if attributes is None:
                attributes = []

            try:
                hero_code = GLOBAL_CACHE.SkillBar.EncodeSkillTemplate(
                    primary=hero.primary,
                    secondary=hero.secondary,
                    skills=skill_ids,
                    attributes=attributes,
                )
            except Exception as exc:
                self.log(f"Failed to encode hero '{hero_name}': {exc}")
                continue

            profession_label = "Unknown professions"
            if hasattr(hero, "primary") and hasattr(hero, "secondary"):
                try:
                    primary_name = gamedata.Profession(hero.primary).name
                except Exception:
                    primary_name = str(getattr(hero, "primary", "?"))
                try:
                    secondary_name = gamedata.Profession(hero.secondary).name
                except Exception:
                    secondary_name = str(getattr(hero, "secondary", "?"))
                profession_label = f"{primary_name}/{secondary_name}"

            self.log(f"Hero {index} {hero_name} ({profession_label}): {hero_code}")
            self._describe_code(
                hero_code,
                heading=f"Hero {index} {hero_name} template details",
            )

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def render_gui(self) -> None:
        if PyImGui is None:
            return

        try:
            PyImGui.set_next_window_size(540, 480)
        except Exception:
            pass

        if not PyImGui.begin("Skill Template Tools", PyImGui.WindowFlags.AlwaysAutoResize):
            PyImGui.end()
            return

        PyImGui.text("Template input")
        self.template_code = PyImGui.input_text("Template Code", self.template_code)

        if PyImGui.button("Decode Input"):
            self._with_throttle("decode_input", self.decode_input)

        PyImGui.same_line(0, -1)
        if PyImGui.button("Describe Sample"):
            self._with_throttle("describe_sample", self.describe_sample)

        if PyImGui.button("Rebuild Sample"):
            self._with_throttle("rebuild_sample", self.rebuild_sample)

        PyImGui.separator()
        PyImGui.text("Live data")

        if PyImGui.button("Encode Player Skillbar"):
            self._with_throttle("player", self.encode_player_skillbar)

        PyImGui.same_line(0, -1)
        if PyImGui.button("Dump Hero Templates"):
            self._with_throttle("heroes", self.dump_hero_templates)

        PyImGui.separator()
        self.action_throttle = PyImGui.slider_float("Action throttle (s)", self.action_throttle, 0.2, 5.0)
        self.action_throttle = max(0.05, float(self.action_throttle))

        PyImGui.separator()
        PyImGui.text("Log output")
        if PyImGui.begin_child(
            "SkillTemplateLog",
            (0.0, 260.0),
            True,
            int(PyImGui.WindowFlags.HorizontalScrollbar),
        ):
            for line in list(self.log_lines):
                if line:
                    PyImGui.text_wrapped(line)
                else:
                    PyImGui.text("")
            PyImGui.end_child()

        PyImGui.end()

    # ------------------------------------------------------------------
    # CLI fallback
    # ------------------------------------------------------------------
    def run_cli_once(self) -> None:
        if self._cli_ran:
            return
        self._cli_ran = True
        self.log("PyImGui unavailable; running console-only summary once.")
        self.describe_sample()
        self.rebuild_sample()


_STATE = SkillTemplateUIState()


def main() -> None:
    if PyImGui is None:
        _STATE.run_cli_once()
        return

    _STATE.render_gui()


if __name__ == "__main__":
    main()

