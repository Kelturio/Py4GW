from __future__ import annotations

import configparser
import copy
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional
import traceback

from Py4GWCoreLib import (
    GLOBAL_CACHE,
    IconsFontAwesome5,
    Map,
    Party,
    Player,
    Py4GW,
    PyImGui,
    Routines,
)
from Py4GWCoreLib import ConsoleLog
from Py4GWCoreLib import HeroType
from Py4GWCoreLib.py4gwcorelib_src.Timer import Timer as CoreTimer


MODULE_NAME = "Hero Builds"
CONFIG_SECTION_GENERAL = "General"

script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))

CONFIG_DIR = os.path.join(project_root, "Widgets", "Config")
os.makedirs(CONFIG_DIR, exist_ok=True)

DATA_PATH = os.path.join(CONFIG_DIR, "HeroBuilds.ini")
WINDOW_PATH = os.path.join(CONFIG_DIR, "HeroBuildsWindow.ini")

DEFAULT_WINDOW_X = 200
DEFAULT_WINDOW_Y = 200
DEFAULT_CONFIG_X = 250
DEFAULT_CONFIG_Y = 220

def _make_ini_handler(path: str):
    try:
        from Py4GWCoreLib import IniHandler

        return IniHandler(path)
    except Exception:
        # Fallback: create an empty file so future writes succeed.
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8"):
                pass
        return None


window_state_ini = _make_ini_handler(WINDOW_PATH)


def _read_window_state(section: str, key: str, default: int | bool) -> int | bool:
    if window_state_ini is None:
        return default
    if isinstance(default, bool):
        return window_state_ini.read_bool(section, key, default)
    return window_state_ini.read_int(section, key, default)


def _write_window_state(section: str, key: str, value: int | bool) -> None:
    if window_state_ini is None:
        return
    window_state_ini.write_key(section, key, str(value))


WINDOW_KEY_X = "x"
WINDOW_KEY_Y = "y"
WINDOW_KEY_COLLAPSED = "collapsed"

window_x = int(_read_window_state(MODULE_NAME, WINDOW_KEY_X, DEFAULT_WINDOW_X))
window_y = int(_read_window_state(MODULE_NAME, WINDOW_KEY_Y, DEFAULT_WINDOW_Y))
window_collapsed = bool(_read_window_state(MODULE_NAME, WINDOW_KEY_COLLAPSED, False))

CONFIG_MODULE_NAME = f"{MODULE_NAME} Config"
config_window_x = int(_read_window_state(CONFIG_MODULE_NAME, WINDOW_KEY_X, DEFAULT_CONFIG_X))
config_window_y = int(_read_window_state(CONFIG_MODULE_NAME, WINDOW_KEY_Y, DEFAULT_CONFIG_Y))
config_window_collapsed = bool(_read_window_state(CONFIG_MODULE_NAME, WINDOW_KEY_COLLAPSED, True))


def _ensure_data_file() -> None:
    if not os.path.exists(DATA_PATH):
        config = configparser.ConfigParser()
        config[CONFIG_SECTION_GENERAL] = {
            "hide_when_entering_explorable": "false",
            "one_teambuild_at_a_time": "false",
        }
        with open(DATA_PATH, "w", encoding="utf-8") as handle:
            config.write(handle)


_ensure_data_file()


def _next_ui_id() -> int:
    _next_ui_id.counter += 1
    return _next_ui_id.counter


_next_ui_id.counter = 0  # type: ignore[attr-defined]


HERO_INDEX_TO_TYPE: List[HeroType] = [
    HeroType.None_,
    HeroType.Goren,
    HeroType.Koss,
    HeroType.Jora,
    HeroType.AcolyteJin,
    HeroType.MagridTheSly,
    HeroType.PyreFierceshot,
    HeroType.Tahlkora,
    HeroType.Dunkoro,
    HeroType.Ogden,
    HeroType.MasterOfWhispers,
    HeroType.Olias,
    HeroType.Livia,
    HeroType.Norgu,
    HeroType.Razah,
    HeroType.Gwen,
    HeroType.AcolyteSousuke,
    HeroType.ZhedShadowhoof,
    HeroType.Vekk,
    HeroType.Zenmai,
    HeroType.Anton,
    HeroType.Miku,
    HeroType.Xandra,
    HeroType.ZeiRi,
    HeroType.GeneralMorgahn,
    HeroType.KeiranThackeray,
    HeroType.Hayda,
    HeroType.Melonni,
    HeroType.MOX,
    HeroType.Kahmu,
    HeroType.MercenaryHero1,
    HeroType.MercenaryHero2,
    HeroType.MercenaryHero3,
    HeroType.MercenaryHero4,
    HeroType.MercenaryHero5,
    HeroType.MercenaryHero6,
    HeroType.MercenaryHero7,
    HeroType.MercenaryHero8,
]


DEFAULT_HERO_NAMES: Dict[HeroType, str] = {
    HeroType.None_: "No Hero",
    HeroType.Norgu: "Norgu",
    HeroType.Goren: "Goren",
    HeroType.Tahlkora: "Tahlkora",
    HeroType.MasterOfWhispers: "Master Of Whispers",
    HeroType.AcolyteJin: "Acolyte Jin",
    HeroType.Koss: "Koss",
    HeroType.Dunkoro: "Dunkoro",
    HeroType.AcolyteSousuke: "Acolyte Sousuke",
    HeroType.Melonni: "Melonni",
    HeroType.ZhedShadowhoof: "Zhed Shadowhoof",
    HeroType.GeneralMorgahn: "General Morgahn",
    HeroType.MagridTheSly: "Margrid The Sly",
    HeroType.Zenmai: "Zenmai",
    HeroType.Olias: "Olias",
    HeroType.Razah: "Razah",
    HeroType.MOX: "MOX",
    HeroType.KeiranThackeray: "Keiran Thackeray",
    HeroType.Jora: "Jora",
    HeroType.PyreFierceshot: "Pyre Fierceshot",
    HeroType.Anton: "Anton",
    HeroType.Livia: "Livia",
    HeroType.Hayda: "Hayda",
    HeroType.Kahmu: "Kahmu",
    HeroType.Gwen: "Gwen",
    HeroType.Xandra: "Xandra",
    HeroType.Vekk: "Vekk",
    HeroType.Ogden: "Ogden",
    HeroType.Miku: "Miku",
    HeroType.ZeiRi: "Zei Ri",
    HeroType.MercenaryHero1: "Mercenary Hero 1",
    HeroType.MercenaryHero2: "Mercenary Hero 2",
    HeroType.MercenaryHero3: "Mercenary Hero 3",
    HeroType.MercenaryHero4: "Mercenary Hero 4",
    HeroType.MercenaryHero5: "Mercenary Hero 5",
    HeroType.MercenaryHero6: "Mercenary Hero 6",
    HeroType.MercenaryHero7: "Mercenary Hero 7",
    HeroType.MercenaryHero8: "Mercenary Hero 8",
}


@dataclass
class HeroBuild:
    name: str = ""
    code: str = ""
    hero_index: int = 0
    behavior: int = 1
    show_panel: bool = False


def _default_builds() -> List[HeroBuild]:
    builds = [HeroBuild(hero_index=-2)]
    builds.extend(HeroBuild(hero_index=0) for _ in range(7))
    return builds


@dataclass
class TeamHeroBuild:
    name: str = ""
    mode: int = 0
    builds: List[HeroBuild] = field(default_factory=_default_builds)
    edit_open: bool = False
    first_run: bool = True
    ui_id: int = field(default_factory=_next_ui_id)


@dataclass
class PendingHeroLoad:
    code: str
    hero_type: HeroType
    show_panel: bool
    behavior: int
    stage: str = "add"
    start_time: float = field(default_factory=time.perf_counter)

    def timed_out(self, timeout_ms: int = 1200) -> bool:
        return (time.perf_counter() - self.start_time) * 1000.0 > timeout_ms


hero_builds: List[TeamHeroBuild] = []
builds_changed = False
hide_when_entering_explorable = False
one_teambuild_at_a_time = False

data_mtime: float = 0.0

window_open = True
window_first_run = True
main_window_expanded = False

config_window_open = False
config_window_first_run = True
config_window_expanded = False

pending_hero_loads: List[PendingHeroLoad] = []
send_queue: Deque[str] = deque()

send_timer = CoreTimer()
send_timer.Start()

kickall_timer = CoreTimer()
kickall_timer.Stop()

save_timer = CoreTimer()
save_timer.Start()

last_instance_type = "Loading"
last_visibility = False


def hero_type_from_index(index: int) -> HeroType:
    if index <= 0:
        return HeroType.None_
    if index >= len(HERO_INDEX_TO_TYPE):
        return HeroType.None_
    return HERO_INDEX_TO_TYPE[index]


def hero_display_name(hero_type: HeroType) -> str:
    if hero_type in (HeroType.None_,):
        return DEFAULT_HERO_NAMES[HeroType.None_]
    try:
        name = GLOBAL_CACHE.Party.Heroes.GetHeroNameById(hero_type.value)
        if name:
            return name
    except Exception:
        pass
    return DEFAULT_HERO_NAMES.get(hero_type, hero_type.name.replace("_", " "))


def get_instance_type() -> str:
    if Map.IsMapLoading():
        return "Loading"
    if Map.IsOutpost():
        return "Outpost"
    if Map.IsExplorable():
        return "Explorable"
    return "Other"


def _load_from_file() -> None:
    global hero_builds, builds_changed, data_mtime
    global hide_when_entering_explorable, one_teambuild_at_a_time

    config = configparser.ConfigParser()
    try:
        config.read(DATA_PATH, encoding="utf-8")
    except (configparser.Error, OSError) as exc:
        ConsoleLog(
            MODULE_NAME,
            f"Failed to load hero builds: {exc}",
            Console.MessageType.Error,
        )
        return

    hide_when_entering_explorable = config.getboolean(
        CONFIG_SECTION_GENERAL,
        "hide_when_entering_explorable",
        fallback=False,
    )
    one_teambuild_at_a_time = config.getboolean(
        CONFIG_SECTION_GENERAL,
        "one_teambuild_at_a_time",
        fallback=False,
    )

    hero_builds = []

    sections = [
        section
        for section in config.sections()
        if section.lower().startswith("builds")
    ]
    sections.sort()

    for section in sections:
        team_build = TeamHeroBuild()
        team_build.name = config.get(section, "buildname", fallback="")
        team_build.mode = config.getint(section, "mode", fallback=0)
        team_build.builds = []
        for index in range(8):
            name = config.get(section, f"name{index}", fallback="")
            code = config.get(section, f"template{index}", fallback="")
            default_index = -2 if index == 0 else 0
            hero_index = config.getint(
                section,
                f"heroindex{index}",
                fallback=default_index,
            )
            if index > 0 and hero_index < 0:
                hero_index = 0
            behavior = config.getint(section, f"behavior{index}", fallback=1)
            show_panel = config.getboolean(
                section,
                f"panel{index}",
                fallback=False,
            )
            team_build.builds.append(
                HeroBuild(
                    name=name,
                    code=code,
                    hero_index=hero_index,
                    behavior=behavior,
                    show_panel=show_panel,
                )
            )
        if len(team_build.builds) < 8:
            team_build.builds.extend(_default_builds()[len(team_build.builds) :])
        hero_builds.append(team_build)

    builds_changed = False
    try:
        data_mtime = os.path.getmtime(DATA_PATH)
    except OSError:
        data_mtime = 0.0


def _save_to_file(force: bool = False) -> None:
    global builds_changed, data_mtime
    if not (force or builds_changed):
        return

    config = configparser.ConfigParser()
    config[CONFIG_SECTION_GENERAL] = {
        "hide_when_entering_explorable": "true"
        if hide_when_entering_explorable
        else "false",
        "one_teambuild_at_a_time": "true"
        if one_teambuild_at_a_time
        else "false",
    }

    for idx, team_build in enumerate(hero_builds):
        section = f"builds{idx:03d}"
        config[section] = {
            "buildname": team_build.name,
            "mode": str(team_build.mode),
        }
        for build_idx, build in enumerate(team_build.builds):
            config[section][f"name{build_idx}"] = build.name
            config[section][f"template{build_idx}"] = build.code
            config[section][f"heroindex{build_idx}"] = str(build.hero_index)
            config[section][f"panel{build_idx}"] = (
                "1" if build.show_panel else "0"
            )
            config[section][f"behavior{build_idx}"] = str(build.behavior)

    try:
        with open(DATA_PATH, "w", encoding="utf-8") as handle:
            config.write(handle)
        builds_changed = False
        data_mtime = os.path.getmtime(DATA_PATH)
    except OSError as exc:
        ConsoleLog(
            MODULE_NAME,
            f"Failed to save hero builds: {exc}",
            Console.MessageType.Error,
        )


def _mark_dirty() -> None:
    global builds_changed
    builds_changed = True


_load_from_file()


def _hero_build_display_name(team_build: TeamHeroBuild, index: int) -> str:
    if index >= len(team_build.builds):
        return ""
    build = team_build.builds[index]
    if index == 0:
        return f"{build.name} (Player)" if build.name else "Player"

    hero_type = hero_type_from_index(build.hero_index)
    hero_name = hero_display_name(hero_type)

    if build.name:
        return f"{build.name} ({hero_name})"
    if hero_type is HeroType.None_:
        return ""
    return hero_name


def _queue_message(message: str) -> None:
    if message:
        send_queue.append(message)


def _send_teambuild(team_build: TeamHeroBuild) -> None:
    if team_build.name:
        _queue_message(team_build.name)
    for idx, build in enumerate(team_build.builds):
        if idx == 0 and not build.code and not build.name:
            continue
        _send_single_build(team_build, idx)


def _send_single_build(team_build: TeamHeroBuild, index: int) -> None:
    if index >= len(team_build.builds):
        return
    build = team_build.builds[index]
    build_name = _hero_build_display_name(team_build, index)
    if not build_name:
        return
    if build.code:
        message = f"[{build_name};{build.code}]"
    else:
        message = build_name
    _queue_message(message)


def _player_login_number() -> int:
    try:
        agent_id = Player.GetAgentID()
        return GLOBAL_CACHE.Party.Players.GetLoginNumberByAgentID(agent_id)
    except Exception:
        return 0


def _get_player_hero_by_id(hero_type: HeroType) -> tuple[Optional[object], Optional[int]]:
    heroes = GLOBAL_CACHE.Party.GetHeroes()
    if not heroes:
        return None, None
    login_number = _player_login_number()
    for idx, hero in enumerate(heroes):
        try:
            hero_id = hero.hero_id.GetID()
            owner = hero.owner_player_id
        except AttributeError:
            continue
        if owner == login_number and hero_id == hero_type.value:
            return hero, idx + 1
    return None, None


def _load_team_build(team_build: TeamHeroBuild) -> None:
    if not Map.IsOutpost():
        ConsoleLog(
            MODULE_NAME,
            "Hero builds can only be loaded in an outpost.",
            Console.MessageType.Warning,
        )
        return

    GLOBAL_CACHE.Party.Heroes.KickAllHeroes()
    kickall_timer.Reset()
    pending_hero_loads.clear()

    if team_build.mode == 1:
        GLOBAL_CACHE.Party.SetNormalMode()
    elif team_build.mode == 2:
        GLOBAL_CACHE.Party.SetHardMode()

    for idx in range(len(team_build.builds)):
        _load_single_build(team_build, idx)

    send_timer.Reset()


def _load_single_build(team_build: TeamHeroBuild, index: int) -> None:
    if index >= len(team_build.builds):
        return

    build = team_build.builds[index]
    if index == 0:
        if build.code:
            GLOBAL_CACHE.SkillBar.LoadSkillTemplate(build.code)
        return

    hero_type = hero_type_from_index(build.hero_index)
    if hero_type in (HeroType.None_,):
        return

    pending_hero_loads.append(
        PendingHeroLoad(
            code=build.code,
            hero_type=hero_type,
            show_panel=build.show_panel,
            behavior=build.behavior,
        )
    )


def _process_pending_loads(instance_type: str) -> None:
    if not pending_hero_loads:
        return
    if instance_type != "Outpost":
        pending_hero_loads.clear()
        return

    login_number = _player_login_number()
    if login_number == 0:
        return

    for pending in list(pending_hero_loads):
        if pending.timed_out():
            pending_hero_loads.remove(pending)
            continue

        if pending.stage == "add":
            GLOBAL_CACHE.Party.Heroes.AddHero(pending.hero_type.value)
            pending.stage = "wait"
            pending.start_time = time.perf_counter()
            continue

        hero, hero_index = _get_player_hero_by_id(pending.hero_type)
        if hero is None or hero_index is None:
            continue

        if pending.code:
            GLOBAL_CACHE.SkillBar.LoadHeroSkillTemplate(hero_index, pending.code)
        try:
            hero_agent_id = hero.agent_id
            GLOBAL_CACHE.Party.Heroes.SetHeroBehavior(hero_agent_id, pending.behavior)
        except AttributeError:
            pass

        pending_hero_loads.remove(pending)


def _process_send_queue() -> None:
    if not send_queue:
        return
    if send_timer.HasElapsed(600):
        try:
            message = send_queue.popleft()
            GLOBAL_CACHE.Player.SendChat('#', message)
        except Exception as exc:
            ConsoleLog(
                MODULE_NAME,
                f"Failed to send build to chat: {exc}",
                Console.MessageType.Error,
            )
        finally:
            send_timer.Reset()


def _player_hero_count() -> int:
    heroes = GLOBAL_CACHE.Party.GetHeroes()
    if not heroes:
        return 0
    login_number = _player_login_number()
    if login_number == 0:
        return 0
    count = 0
    for hero in heroes:
        try:
            if hero.owner_player_id == login_number:
                count += 1
        except AttributeError:
            continue
    return count


def _handle_map_state() -> None:
    global last_instance_type

    instance_type = get_instance_type()

    if instance_type != last_instance_type:
        if (
            instance_type == "Explorable"
            and hide_when_entering_explorable
        ):
            _close_all_windows()
        if instance_type == "Loading":
            send_queue.clear()
            pending_hero_loads.clear()
            kickall_timer.Stop()
        last_instance_type = instance_type

    if kickall_timer.IsRunning():
        if (
            kickall_timer.HasElapsed(500)
            or instance_type != "Outpost"
            or _player_hero_count() == 0
        ):
            kickall_timer.Stop()

    _process_pending_loads(instance_type)


def _close_all_windows() -> None:
    global window_open
    window_open = False
    for team_build in hero_builds:
        team_build.edit_open = False


def _ensure_loaded_when_visible(visible: bool) -> None:
    global last_visibility
    if visible and not last_visibility:
        current_mtime = 0.0
        try:
            current_mtime = os.path.getmtime(DATA_PATH)
        except OSError:
            current_mtime = 0.0
        if current_mtime != data_mtime:
            _load_from_file()
    if not visible and last_visibility:
        _save_to_file(force=True)
    last_visibility = visible


def _handle_auto_save() -> None:
    if builds_changed and save_timer.HasElapsed(1500):
        _save_to_file()
        save_timer.Reset()


def _draw_main_window() -> None:
    global window_first_run, window_open, main_window_expanded
    global window_x, window_y, window_collapsed

    if window_first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        window_first_run = False

    expanded, window_open_state = PyImGui.begin_with_close(
        MODULE_NAME,
        window_open,
        PyImGui.WindowFlags.AlwaysAutoResize,
    )
    window_open = window_open_state
    main_window_expanded = expanded and window_open

    if expanded and window_open_state:
        _draw_main_window_contents()

    end_pos = PyImGui.get_window_pos()
    PyImGui.end()

    new_collapsed = not expanded
    if (int(end_pos[0]), int(end_pos[1])) != (window_x, window_y):
        window_x, window_y = int(end_pos[0]), int(end_pos[1])
        _write_window_state(MODULE_NAME, WINDOW_KEY_X, window_x)
        _write_window_state(MODULE_NAME, WINDOW_KEY_Y, window_y)
    if new_collapsed != window_collapsed:
        window_collapsed = new_collapsed
        _write_window_state(MODULE_NAME, WINDOW_KEY_COLLAPSED, window_collapsed)


def _draw_main_window_contents() -> None:
    global hero_builds

    io = PyImGui.get_io()
    button_width = 70 * io.font_global_scale
    spacing = PyImGui.get_style().item_inner_spacing.x

    for team_build in hero_builds:
        PyImGui.push_id(team_build.ui_id)
        label = team_build.name or "Unnamed Teambuild"
        if PyImGui.button(
            label,
            size=(PyImGui.get_content_region_available()[0] - spacing - button_width, 0),
        ):
            if one_teambuild_at_a_time and not team_build.edit_open:
                for other in hero_builds:
                    other.edit_open = False
            team_build.edit_open = not team_build.edit_open
        PyImGui.same_line(0, spacing)
        if PyImGui.button("Send" if io.key_ctrl else "Load", size=(button_width, 0)):
            if io.key_ctrl:
                _send_teambuild(team_build)
            else:
                _load_team_build(team_build)
        PyImGui.pop_id()

    PyImGui.separator()

    if PyImGui.button("Add Teambuild", size=(PyImGui.get_content_region_available()[0], 0)):
        new_build = TeamHeroBuild()
        new_build.edit_open = True
        hero_builds.append(new_build)
        _mark_dirty()

    disabled_reason = None
    PyImGui.begin_disabled(disabled_reason is not None)
    if PyImGui.button(
        "Add From Current", size=(PyImGui.get_content_region_available()[0], 0)
    ):
        ConsoleLog(
            MODULE_NAME,
            "Importing builds from the current party is not yet supported.",
            Console.MessageType.Info,
        )
    PyImGui.end_disabled()

    if hero_builds:
        names = [tb.name or f"Teambuild {idx + 1}" for idx, tb in enumerate(hero_builds)]
        PyImGui.push_item_width(-60.0 - spacing)
        PyImGui.set_next_item_width(-60.0 - spacing)
        _draw_copy_row(names)
        PyImGui.pop_item_width()


def _draw_copy_row(names: List[str]) -> None:
    if not names:
        return
    _draw_copy_row.selected = getattr(_draw_copy_row, "selected", 0)
    _draw_copy_row.selected = PyImGui.combo("##copy_combo", _draw_copy_row.selected, names)
    PyImGui.same_line(0, PyImGui.get_style().item_inner_spacing.x)
    if PyImGui.button("Copy", size=(60.0, 0)):
        if 0 <= _draw_copy_row.selected < len(hero_builds):
            duplicate = copy.deepcopy(hero_builds[_draw_copy_row.selected])
            duplicate.name = f"{duplicate.name} (Copy)"
            duplicate.ui_id = _next_ui_id()
            duplicate.edit_open = True
            hero_builds.append(duplicate)
            _mark_dirty()


def _draw_edit_windows() -> None:
    for team_build in hero_builds:
        if not team_build.edit_open:
            continue
        _draw_teambuild_editor(team_build)


def _draw_teambuild_editor(team_build: TeamHeroBuild) -> None:
    title = team_build.name or "Teambuild"
    window_name = f"{title}##herobuild{team_build.ui_id}"

    if team_build.first_run:
        PyImGui.set_next_window_size(520, 0)
        team_build.first_run = False

    expanded, open_state = PyImGui.begin_with_close(
        window_name,
        team_build.edit_open,
        PyImGui.WindowFlags.AlwaysAutoResize,
    )
    team_build.edit_open = open_state

    if expanded and open_state:
        _draw_teambuild_editor_contents(team_build)

    PyImGui.end()


def _draw_teambuild_editor_contents(team_build: TeamHeroBuild) -> None:
    global hero_builds

    PyImGui.push_item_width(-1)
    new_name = PyImGui.input_text("Hero Build Name", team_build.name)
    PyImGui.pop_item_width()
    if new_name != team_build.name:
        team_build.name = new_name
        _mark_dirty()

    io = PyImGui.get_io()
    button_width = 60 * io.font_global_scale
    icon_width = button_width * 0.6
    spacing = PyImGui.get_style().item_inner_spacing.x
    available = PyImGui.get_content_region_available()[0]
    text_width = (available - button_width * 2 - icon_width * 2 - spacing * 4) / 3

    for index, build in enumerate(team_build.builds):
        PyImGui.push_id(index)
        PyImGui.text("P" if index == 0 else f"H#{index}")
        PyImGui.same_line(spacing * 2)
        PyImGui.push_item_width(text_width)
        new_build_name = PyImGui.input_text("##name", build.name)
        if new_build_name != build.name:
            build.name = new_build_name
            _mark_dirty()
        PyImGui.pop_item_width()

        PyImGui.same_line(spacing * 3 + text_width)
        PyImGui.push_item_width(text_width)
        new_code = PyImGui.input_text("##code", build.code)
        if new_code != build.code:
            build.code = new_code
            _mark_dirty()
        PyImGui.pop_item_width()

        if index == 0:
            PyImGui.same_line(spacing * 4 + text_width * 2)
            PyImGui.text_disabled("Player")
        else:
            PyImGui.same_line(spacing * 4 + text_width * 2)
            hero_names = [hero_display_name(ht) for ht in HERO_INDEX_TO_TYPE]
            new_index = PyImGui.combo("##hero", build.hero_index, hero_names)
            if new_index != build.hero_index:
                build.hero_index = new_index
                _mark_dirty()

            PyImGui.same_line(spacing * 5 + text_width * 2)
            icon = (
                IconsFontAwesome5.ICON_EYE
                if build.show_panel
                else IconsFontAwesome5.ICON_EYE_SLASH
            )
            if PyImGui.button(icon, size=(icon_width, 0)):
                build.show_panel = not build.show_panel
                _mark_dirty()
            PyImGui.same_line(spacing * 6 + text_width * 2 + icon_width)
            behavior_icon = {
                0: IconsFontAwesome5.ICON_FIST_RAISED,
                1: IconsFontAwesome5.ICON_SHIELD_ALT,
                2: IconsFontAwesome5.ICON_DOVE,
            }.get(build.behavior, IconsFontAwesome5.ICON_SHIELD_ALT)
            if PyImGui.button(behavior_icon, size=(icon_width, 0)):
                build.behavior = (build.behavior + 1) % 3
                _mark_dirty()

        PyImGui.same_line(0, spacing)
        if PyImGui.button("Send" if io.key_ctrl else "View", size=(button_width, 0)):
            if io.key_ctrl:
                _send_single_build(team_build, index)
            else:
                if build.code:
                    PyImGui.set_clipboard_text(build.code)
                    ConsoleLog(
                        MODULE_NAME,
                        f"Copied build code for {_hero_build_display_name(team_build, index)}",
                        Console.MessageType.Info,
                    )
        PyImGui.same_line(0, spacing)
        if PyImGui.button("Load", size=(button_width, 0)):
            _load_single_build(team_build, index)
        PyImGui.pop_id()

    PyImGui.separator()

    if PyImGui.small_button("Up"):
        idx = hero_builds.index(team_build)
        if idx > 0:
            hero_builds[idx - 1], hero_builds[idx] = hero_builds[idx], hero_builds[idx - 1]
            _mark_dirty()
    PyImGui.same_line()
    if PyImGui.small_button("Down"):
        idx = hero_builds.index(team_build)
        if idx + 1 < len(hero_builds):
            hero_builds[idx + 1], hero_builds[idx] = hero_builds[idx], hero_builds[idx + 1]
            _mark_dirty()
    PyImGui.same_line()
    if PyImGui.small_button("Delete"):
        hero_builds.remove(team_build)
        _mark_dirty()
        return

    PyImGui.same_line()
    modes = ["Don't change", "Normal Mode", "Hard Mode"]
    team_build.mode = PyImGui.combo("Mode", team_build.mode, modes)


def _draw_config_window() -> None:
    global config_window_first_run, config_window_open, config_window_expanded
    global config_window_x, config_window_y, config_window_collapsed
    global hide_when_entering_explorable, one_teambuild_at_a_time

    if config_window_first_run:
        PyImGui.set_next_window_pos(config_window_x, config_window_y)
        PyImGui.set_next_window_collapsed(config_window_collapsed, 0)
        config_window_first_run = False

    expanded, open_state = PyImGui.begin_with_close(
        CONFIG_MODULE_NAME,
        config_window_open,
        PyImGui.WindowFlags.AlwaysAutoResize,
    )
    config_window_open = open_state
    config_window_expanded = expanded and open_state

    if expanded and open_state:
        new_hide = PyImGui.checkbox(
            "Hide Hero Build windows when entering explorable areas",
            hide_when_entering_explorable,
        )
        if new_hide != hide_when_entering_explorable:
            hide_when_entering_explorable = new_hide
            _mark_dirty()
        new_single = PyImGui.checkbox(
            "Only show one teambuild editor at a time",
            one_teambuild_at_a_time,
        )
        if new_single != one_teambuild_at_a_time:
            one_teambuild_at_a_time = new_single
            _mark_dirty()

    end_pos = PyImGui.get_window_pos()
    PyImGui.end()

    new_collapsed = not expanded
    if (int(end_pos[0]), int(end_pos[1])) != (config_window_x, config_window_y):
        config_window_x, config_window_y = int(end_pos[0]), int(end_pos[1])
        _write_window_state(CONFIG_MODULE_NAME, WINDOW_KEY_X, config_window_x)
        _write_window_state(CONFIG_MODULE_NAME, WINDOW_KEY_Y, config_window_y)
    if new_collapsed != config_window_collapsed:
        config_window_collapsed = new_collapsed
        _write_window_state(
            CONFIG_MODULE_NAME,
            WINDOW_KEY_COLLAPSED,
            config_window_collapsed,
        )


def configure() -> None:
    _draw_config_window()


def main() -> None:
    global window_open
    try:
        if not Routines.Checks.Map.MapValid():
            return

        _handle_map_state()
        _process_send_queue()
        _handle_auto_save()

        if Map.IsMapReady() and Party.IsPartyLoaded():
            _draw_main_window()
            _draw_edit_windows()

        visible = (window_open and main_window_expanded) or any(
            tb.edit_open for tb in hero_builds
        )
        _ensure_loaded_when_visible(visible)

    except ImportError as exc:
        Py4GW.Console.Log(
            MODULE_NAME,
            f"ImportError encountered: {exc}",
            Py4GW.Console.MessageType.Error,
        )
        Py4GW.Console.Log(
            MODULE_NAME,
            traceback.format_exc(),
            Py4GW.Console.MessageType.Error,
        )
    except Exception as exc:
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Unexpected error encountered: {exc}",
            Py4GW.Console.MessageType.Error,
        )
        Py4GW.Console.Log(
            MODULE_NAME,
            traceback.format_exc(),
            Py4GW.Console.MessageType.Error,
        )


__widget__ = {
    "category": "Gameplay",
    "subcategory": "Utilities",
    "icon": "ICON_USERS",
    "enabled": False,
    "quickdock": True,
}

