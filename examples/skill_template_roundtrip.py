"""Round-trip Guild Wars skill template demonstration script.

This script shows how to decode, inspect, and re-encode Guild Wars skill
templates using the pure Python encoder/decoder.  It also demonstrates how to
query the currently equipped player skillbar via ``GLOBAL_CACHE`` and output a
build code for it so it can be shared or logged.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, List

try:  # Optional GUI support for in-game visibility of the summary output.
    import tkinter as tk
    from tkinter import scrolledtext
except Exception:  # pragma: no cover - GUI is best-effort only.
    tk = None  # type: ignore[assignment]
    scrolledtext = None  # type: ignore[assignment]


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
    from Py4GWCoreLib import GLOBAL_CACHE  # type: ignore
except Exception:  # pragma: no cover - only triggered in non-game contexts.
    GLOBAL_CACHE = None  # type: ignore


def _load_skill_data() -> dict[int, dict[str, Any]]:
    with (ROOT / "Py4GWCoreLib" / "skill_descriptions.json").open(encoding="utf-8") as handle:
        raw: dict[str, dict[str, Any]] = json.load(handle)
    return {int(skill_id): entry for skill_id, entry in raw.items()}


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


def _rebuild_template(skill_lookup: dict[int, dict[str, Any]], log: Callable[[str], None]) -> None:
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


def _encode_player_skillbar(
    skill_lookup: dict[int, dict[str, Any]], log: Callable[[str], None]
) -> None:
    if GLOBAL_CACHE is None:
        log(
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
        log(f"Failed to encode player skillbar: {exc}")
    else:
        log(f"Current player's skill template: {player_code}")
        log("")
        _describe_template(
            player_code,
            skill_lookup,
            log,
            heading="Player skill template details",
        )


def _show_summary_window(lines: List[str]) -> None:
    if not lines or tk is None or scrolledtext is None:
        return

    try:
        window = tk.Tk()
    except Exception:  # pragma: no cover - GUI is best-effort only.
        return

    window.title("Skill Template Round-Trip Summary")
    window.resizable(width=True, height=True)

    text_widget = scrolledtext.ScrolledText(window, wrap=tk.WORD, width=80, height=30)
    text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    text_widget.insert("1.0", "\n".join(lines))
    text_widget.configure(state=tk.DISABLED)

    close_button = tk.Button(window, text="Close", command=window.destroy)
    close_button.pack(pady=(0, 10))

    try:
        window.after(100, window.lift)
    except Exception:
        pass

    window.mainloop()


_RUN_STATE: dict[str, Any] = {"has_run": False, "last_run": 0.0}


def main() -> None:
    now = time.time()
    if _RUN_STATE["has_run"]:
        # Avoid rerunning continuously when the loader repeatedly invokes ``main``.
        return

    _RUN_STATE["has_run"] = True
    _RUN_STATE["last_run"] = now

    lines: List[str] = []

    def log(message: str = "") -> None:
        print(message)
        lines.append(message)

    banner = "Guild Wars Skill Template Round-Trip"
    log("=" * len(banner))
    log(banner)
    log("=" * len(banner))
    log("")

    skill_lookup = _load_skill_data()

    log(f"Using template code: {TEMPLATE_CODE}")
    log("")
    _describe_template(TEMPLATE_CODE, skill_lookup, log)
    log("")
    _rebuild_template(skill_lookup, log)
    log("")
    _encode_player_skillbar(skill_lookup, log)

    _show_summary_window(lines)


if __name__ == "__main__":
    main()
