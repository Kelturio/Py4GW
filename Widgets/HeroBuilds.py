from __future__ import annotations

import os
import traceback
from collections import deque
from dataclasses import dataclass, field
from itertools import count
from typing import Deque, List, Optional, Tuple

import Py4GW  # type: ignore
from Py4GWCoreLib import (
    GLOBAL_CACHE,
    HeroType,
    IconsFontAwesome5,
    IniHandler,
    Map,
    Party,
    Player,
    PyImGui,
    Routines,
    Timer,
    UIManager,
    WindowID,
)

MODULE_NAME = "Hero Builds"
CONFIG_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Config")
CONFIG_PATH = os.path.join(CONFIG_DIRECTORY, "HeroBuilds.ini")
os.makedirs(CONFIG_DIRECTORY, exist_ok=True)

ini_handler = IniHandler(CONFIG_PATH)

UI_ID_COUNTER = count(1)
BUILD_SLOT_COUNT = 8
CHAT_DELAY_MS = 600
KICK_DELAY_MS = 500
HERO_TIMEOUT_MS = 1000
WINDOW_SAVE_INTERVAL_MS = 1000

HERO_INDEX_TO_ID: List[int] = [
    int(HeroType.None_),
    int(HeroType.Goren),
    int(HeroType.Koss),
    int(HeroType.Jora),
    int(HeroType.AcolyteJin),
    int(HeroType.MagridTheSly),
    int(HeroType.PyreFierceshot),
    int(HeroType.Tahlkora),
    int(HeroType.Dunkoro),
    int(HeroType.Ogden),
    int(HeroType.MasterOfWhispers),
    int(HeroType.Olias),
    int(HeroType.Livia),
    int(HeroType.Norgu),
    int(HeroType.Razah),
    int(HeroType.Gwen),
    int(HeroType.AcolyteSousuke),
    int(HeroType.ZhedShadowhoof),
    int(HeroType.Vekk),
    int(HeroType.Zenmai),
    int(HeroType.Anton),
    int(HeroType.Miku),
    int(HeroType.Xandra),
    int(HeroType.ZeiRi),
    int(HeroType.GeneralMorgahn),
    int(HeroType.KeiranThackeray),
    int(HeroType.Hayda),
    int(HeroType.Melonni),
    int(HeroType.MOX),
    int(HeroType.Kahmu),
    int(HeroType.MercenaryHero1),
    int(HeroType.MercenaryHero2),
    int(HeroType.MercenaryHero3),
    int(HeroType.MercenaryHero4),
    int(HeroType.MercenaryHero5),
    int(HeroType.MercenaryHero6),
    int(HeroType.MercenaryHero7),
    int(HeroType.MercenaryHero8),
]

DEFAULT_HERO_NAMES = {
    int(HeroType.None_): "No Hero",
    int(HeroType.Norgu): "Norgu",
    int(HeroType.Goren): "Goren",
    int(HeroType.Tahlkora): "Tahlkora",
    int(HeroType.MasterOfWhispers): "Master of Whispers",
    int(HeroType.AcolyteJin): "Acolyte Jin",
    int(HeroType.Koss): "Koss",
    int(HeroType.Dunkoro): "Dunkoro",
    int(HeroType.AcolyteSousuke): "Acolyte Sousuke",
    int(HeroType.Melonni): "Melonni",
    int(HeroType.ZhedShadowhoof): "Zhed Shadowhoof",
    int(HeroType.GeneralMorgahn): "General Morgahn",
    int(HeroType.MagridTheSly): "Margrid the Sly",
    int(HeroType.Zenmai): "Zenmai",
    int(HeroType.Olias): "Olias",
    int(HeroType.Razah): "Razah",
    int(HeroType.MOX): "MOX",
    int(HeroType.KeiranThackeray): "Keiran Thackeray",
    int(HeroType.Jora): "Jora",
    int(HeroType.PyreFierceshot): "Pyre Fierceshot",
    int(HeroType.Anton): "Anton",
    int(HeroType.Livia): "Livia",
    int(HeroType.Hayda): "Hayda",
    int(HeroType.Kahmu): "Kahmu",
    int(HeroType.Gwen): "Gwen",
    int(HeroType.Xandra): "Xandra",
    int(HeroType.Vekk): "Vekk",
    int(HeroType.Ogden): "Ogden",
    int(HeroType.MercenaryHero1): "Mercenary Hero 1",
    int(HeroType.MercenaryHero2): "Mercenary Hero 2",
    int(HeroType.MercenaryHero3): "Mercenary Hero 3",
    int(HeroType.MercenaryHero4): "Mercenary Hero 4",
    int(HeroType.MercenaryHero5): "Mercenary Hero 5",
    int(HeroType.MercenaryHero6): "Mercenary Hero 6",
    int(HeroType.MercenaryHero7): "Mercenary Hero 7",
    int(HeroType.MercenaryHero8): "Mercenary Hero 8",
    int(HeroType.Miku): "Miku",
    int(HeroType.ZeiRi): "Zei Ri",
}

HERO_SLOT_WINDOWS = {
    1: WindowID.WindowID_Hero1,
    2: WindowID.WindowID_Hero2,
    3: WindowID.WindowID_Hero3,
    4: WindowID.WindowID_Hero4,
    5: WindowID.WindowID_Hero5,
    6: WindowID.WindowID_Hero6,
    7: WindowID.WindowID_Hero7,
}

BEHAVIOR_ICONS = {
    0: IconsFontAwesome5.ICON_FIST_RAISED,
    1: IconsFontAwesome5.ICON_SHIELD_ALT,
    2: IconsFontAwesome5.ICON_DOVE,
}

BEHAVIOR_TOOLTIPS = {
    0: "Hero behaviour: Fight",
    1: "Hero behaviour: Guard",
    2: "Hero behaviour: Avoid Combat",
}


@dataclass
class HeroBuild:
    name: str = ""
    code: str = ""
    hero_index: int = -1
    behavior: int = 1
    show_panel: bool = False


@dataclass
class TeamHeroBuild:
    name: str = ""
    mode: int = 0
    builds: List[HeroBuild] = field(
        default_factory=lambda: [
            HeroBuild(hero_index=-1 if idx == 0 else 0) for idx in range(BUILD_SLOT_COUNT)
        ]
    )
    edit_open: bool = False
    ui_id: int = field(default_factory=lambda: next(UI_ID_COUNTER))


@dataclass
class PendingHeroLoad:
    code: str
    hero_id: int
    show_panel: bool
    behavior: int
    stage: str = "add"
    timer: Timer = field(default_factory=Timer)

    def __post_init__(self) -> None:
        self.timer.Start()

    def process(self, state: "HeroBuildsState") -> bool:
        if self.stage == "add":
            state.enqueue_add_hero(self.hero_id)
            self.stage = "wait"
            self.timer.Reset()
            return False

        if self.timer.HasElapsed(HERO_TIMEOUT_MS):
            return True

        hero_info = state.find_owned_hero(self.hero_id)
        if not hero_info:
            return False

        agent_id, hero_slot = hero_info
        if self.code:
            GLOBAL_CACHE.SkillBar.LoadHeroSkillTemplate(hero_slot, self.code)
        state.set_hero_panel_visibility(hero_slot, self.show_panel)
        if self.behavior in (0, 1, 2):
            GLOBAL_CACHE.Party.Heroes.SetHeroBehavior(agent_id, self.behavior)
        return True


class HeroBuildsState:
    def __init__(self) -> None:
        self.teambuilds: List[TeamHeroBuild] = []
        self.builds_changed = False
        self.send_queue: Deque[str] = deque()
        self.pending_hero_loads: List[PendingHeroLoad] = []
        self.send_timer = Timer()
        self.send_timer.Start()
        self.kick_timer = Timer()
        self.kick_timer.Stop()
        self.window_timer = Timer()
        self.window_timer.Start()
        self.window_pos = (
            ini_handler.read_int(MODULE_NAME, "x", 100),
            ini_handler.read_int(MODULE_NAME, "y", 100),
        )
        self.window_collapsed = ini_handler.read_bool(MODULE_NAME, "collapsed", False)
        self.hide_when_entering_explorable = ini_handler.read_bool(
            MODULE_NAME, "hide_when_entering_explorable", False
        )
        self.one_teambuild_at_a_time = ini_handler.read_bool(
            MODULE_NAME, "one_teambuild_at_a_time", False
        )
        self.first_run = True
        self.visible_this_frame = False
        self.was_visible_last_frame = False
        self.last_instance: Optional[str] = None
        self.copy_combo_index = 0
        self.load_from_file()

    def begin_frame(self) -> None:
        self.visible_this_frame = False

    def mark_visible(self) -> None:
        self.visible_this_frame = True

    def end_frame(self) -> None:
        if self.visible_this_frame and not self.was_visible_last_frame:
            self.load_from_file()
        elif not self.visible_this_frame and self.was_visible_last_frame:
            self.save_to_file()
        self.was_visible_last_frame = self.visible_this_frame

    def update_environment(self) -> None:
        current = self._get_instance_type()
        if current == self.last_instance:
            return

        if current == "Explorable" and self.hide_when_entering_explorable:
            for tbuild in self.teambuilds:
                tbuild.edit_open = False
        if current == "Loading":
            self.send_queue.clear()
            self.pending_hero_loads.clear()
            self.kick_timer.Stop()
        self.last_instance = current

    def process_async_tasks(self) -> None:
        self._process_send_queue()
        self._process_pending_hero_loads()

    def should_hide_window(self) -> bool:
        if not self.hide_when_entering_explorable:
            return False
        try:
            return Map.IsExplorable()
        except Exception:
            return False

    def load_from_file(self) -> None:
        config = ini_handler.reload()
        sections = sorted(section for section in config.sections() if section.startswith("builds"))
        self.teambuilds.clear()

        for section in sections:
            name = config.get(section, "buildname", fallback="")
            mode = config.getint(section, "mode", fallback=0)
            teambuild = TeamHeroBuild(name=name, mode=mode)
            teambuild.edit_open = False
            for idx in range(BUILD_SLOT_COUNT):
                build = teambuild.builds[idx]
                build.name = config.get(section, f"name{idx}", fallback="")
                build.code = config.get(section, f"template{idx}", fallback="")
                hero_index = config.getint(section, f"heroindex{idx}", fallback=-1)
                if idx == 0:
                    build.hero_index = -1
                else:
                    if hero_index < 0:
                        hero_index = 0
                    if hero_index >= len(HERO_INDEX_TO_ID):
                        hero_index = len(HERO_INDEX_TO_ID) - 1
                    build.hero_index = hero_index
                build.show_panel = config.getint(section, f"panel{idx}", fallback=0) == 1
                behavior = config.getint(section, f"behavior{idx}", fallback=1)
                if behavior not in (0, 1, 2):
                    behavior = 1
                build.behavior = behavior
            self.teambuilds.append(teambuild)

        self.builds_changed = False

    def save_to_file(self) -> None:
        if not self.builds_changed:
            return
        config = ini_handler.reload()
        for section in list(config.sections()):
            if section.startswith("builds"):
                config.remove_section(section)

        for idx, teambuild in enumerate(self.teambuilds):
            section = f"builds{idx:03d}"
            if not config.has_section(section):
                config.add_section(section)
            config.set(section, "buildname", teambuild.name)
            config.set(section, "mode", str(teambuild.mode))
            for slot, build in enumerate(teambuild.builds):
                config.set(section, f"name{slot}", build.name)
                config.set(section, f"template{slot}", build.code)
                config.set(section, f"heroindex{slot}", str(build.hero_index))
                config.set(section, f"panel{slot}", "1" if build.show_panel else "0")
                config.set(section, f"behavior{slot}", str(build.behavior))

        config.set(MODULE_NAME, "x", str(self.window_pos[0]))
        config.set(MODULE_NAME, "y", str(self.window_pos[1]))
        config.set(MODULE_NAME, "collapsed", str(self.window_collapsed))
        config.set(
            MODULE_NAME,
            "hide_when_entering_explorable",
            "True" if self.hide_when_entering_explorable else "False",
        )
        config.set(
            MODULE_NAME,
            "one_teambuild_at_a_time",
            "True" if self.one_teambuild_at_a_time else "False",
        )
        ini_handler.save(config)
        self.builds_changed = False

    def enqueue_add_hero(self, hero_id: int) -> None:
        try:
            GLOBAL_CACHE.Party.Heroes.AddHero(hero_id)
        except Exception:
            try:
                Party.Heroes.AddHero(hero_id)
            except Exception as exc:
                Py4GW.Console.Log(
                    MODULE_NAME,
                    f"Failed to add hero {hero_id}: {exc}",
                    Py4GW.Console.MessageType.Error,
                )

    def find_owned_hero(self, hero_id: int) -> Optional[Tuple[int, int]]:
        try:
            heroes = Party.GetHeroes()
        except Exception:
            heroes = []
        if not heroes:
            return None

        owner_login = self._get_player_login_number()
        for idx, hero in enumerate(heroes):
            owner = getattr(hero, "owner_player_id", owner_login)
            if owner_login and owner != owner_login:
                continue
            current_id = self._hero_id_from_party_member(hero)
            if current_id != hero_id:
                continue
            agent_id = getattr(hero, "agent_id", 0)
            if agent_id:
                return agent_id, idx + 1
        return None

    def set_hero_panel_visibility(self, slot: int, visible: bool) -> None:
        window_id = HERO_SLOT_WINDOWS.get(slot)
        if not window_id:
            return
        try:
            UIManager.set_window_visible(int(window_id), visible)
        except Exception:
            pass

    def add_teambuild(self) -> None:
        teambuild = TeamHeroBuild()
        teambuild.edit_open = True
        self.teambuilds.append(teambuild)
        self.builds_changed = True

    def clone_teambuild(self, source: TeamHeroBuild) -> TeamHeroBuild:
        clone = TeamHeroBuild(name=source.name, mode=source.mode)
        for idx in range(BUILD_SLOT_COUNT):
            original = source.builds[idx]
            clone.builds[idx] = HeroBuild(
                name=original.name,
                code=original.code,
                hero_index=original.hero_index if idx > 0 else -1,
                behavior=original.behavior,
                show_panel=original.show_panel,
            )
        clone.edit_open = True
        return clone

    def load_teambuild(self, teambuild: TeamHeroBuild) -> None:
        if not self._is_outpost():
            Py4GW.Console.Log(
                MODULE_NAME,
                "Hero builds can only be loaded in outposts.",
                Py4GW.Console.MessageType.Warning,
            )
            return

        GLOBAL_CACHE.Party.Heroes.KickAllHeroes()
        self.kick_timer.Reset()
        self.pending_hero_loads.clear()

        if teambuild.mode == 2:
            GLOBAL_CACHE.Party.SetHardMode()
        elif teambuild.mode == 1:
            GLOBAL_CACHE.Party.SetNormalMode()

        for idx, build in enumerate(teambuild.builds):
            self._load_slot(build, idx)
        self.send_timer.Reset()

    def _load_slot(self, build: HeroBuild, slot: int) -> None:
        if not self._is_outpost():
            Py4GW.Console.Log(
                MODULE_NAME,
                "Hero builds can only be loaded in outposts.",
                Py4GW.Console.MessageType.Warning,
            )
            return
        code = build.code.strip()
        if slot == 0:
            if code:
                GLOBAL_CACHE.SkillBar.LoadSkillTemplate(code)
            return

        if build.hero_index <= 0 or build.hero_index >= len(HERO_INDEX_TO_ID):
            return
        hero_id = HERO_INDEX_TO_ID[build.hero_index]
        self.pending_hero_loads.append(
            PendingHeroLoad(code=code, hero_id=hero_id, show_panel=build.show_panel, behavior=build.behavior)
        )

    def send_teambuild(self, teambuild: TeamHeroBuild) -> None:
        name = teambuild.name.strip()
        if name:
            self.send_queue.append(name)
        for idx, build in enumerate(teambuild.builds):
            self._send_slot(teambuild, build, idx)

    def _send_slot(self, teambuild: TeamHeroBuild, build: HeroBuild, slot: int) -> None:
        message = self._compose_build_message(teambuild, build, slot)
        if message:
            self.send_queue.append(message)

    def view_build(self, teambuild: TeamHeroBuild, slot: int) -> None:
        if slot >= len(teambuild.builds):
            return
        build = teambuild.builds[slot]
        message = self._compose_build_message(teambuild, build, slot)
        if not message:
            return
        PyImGui.set_clipboard_text(message)
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Copied build '{self._build_display_name(teambuild, build, slot)}' to the clipboard.",
            Py4GW.Console.MessageType.Info,
        )

    def _compose_build_message(self, teambuild: TeamHeroBuild, build: HeroBuild, slot: int) -> str:
        display_name = self._build_display_name(teambuild, build, slot)
        if not display_name:
            return ""
        code = build.code.strip()
        if code:
            return f"[{display_name};{code}]"
        return display_name

    def _build_display_name(self, teambuild: TeamHeroBuild, build: HeroBuild, slot: int) -> str:
        base_name = build.name.strip()
        if slot == 0:
            if base_name:
                return f"{base_name} (Player)"
            return "Player" if build.code.strip() else ""
        hero_label = self._hero_label(build.hero_index)
        if base_name:
            return f"{base_name} ({hero_label})" if hero_label else base_name
        return hero_label

    def _hero_label(self, hero_index: int) -> str:
        if hero_index <= 0 or hero_index >= len(HERO_INDEX_TO_ID):
            return ""
        hero_id = HERO_INDEX_TO_ID[hero_index]
        try:
            name = Party.Heroes.GetHeroNameById(hero_id)
            if name:
                return name
        except Exception:
            pass
        return DEFAULT_HERO_NAMES.get(hero_id, f"Hero {hero_id}")

    def draw_main_window(self) -> None:
        if self.should_hide_window():
            return

        if self.first_run:
            PyImGui.set_next_window_pos(self.window_pos[0], self.window_pos[1])
            PyImGui.set_next_window_collapsed(self.window_collapsed, 0)
            self.first_run = False

        is_window_open = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
        self.mark_visible()
        new_collapsed = PyImGui.is_window_collapsed()
        end_pos = PyImGui.get_window_pos()

        if is_window_open:
            available_width = PyImGui.get_content_region_avail()[0]
            load_button_width = 80
            spacing = 6

            for idx, teambuild in enumerate(self.teambuilds):
                label = teambuild.name or f"Team Build {idx + 1}"
                button_width = max(120.0, available_width - load_button_width - spacing)
                if PyImGui.button(f"{label}##open_{teambuild.ui_id}", width=button_width):
                    if self.one_teambuild_at_a_time and not teambuild.edit_open:
                        for other in self.teambuilds:
                            other.edit_open = False
                    teambuild.edit_open = not teambuild.edit_open
                PyImGui.same_line(0, spacing)
                io = PyImGui.get_io()
                label_text = "Send" if io.key_ctrl else "Load"
                if PyImGui.button(f"{label_text}##load_{teambuild.ui_id}", width=load_button_width):
                    if io.key_ctrl:
                        self.send_teambuild(teambuild)
                    else:
                        self.load_teambuild(teambuild)
                if PyImGui.is_item_hovered():
                    tooltip = (
                        "Click to send to team chat"
                        if io.key_ctrl
                        else "Click to load builds to heroes and player. Hold Ctrl to send instead."
                    )
                    PyImGui.set_tooltip(tooltip)

            if PyImGui.button(f"{IconsFontAwesome5.ICON_PLUS} Add Team Build", width=max(200.0, available_width)):
                self.add_teambuild()
            if PyImGui.button(
                f"{IconsFontAwesome5.ICON_COPY} Add from Current Party",
                width=max(200.0, available_width),
            ):
                Py4GW.Console.Log(
                    MODULE_NAME,
                    "Importing builds from the current party is not supported yet.",
                    Py4GW.Console.MessageType.Warning,
                )

            if self.teambuilds:
                names = [tb.name or f"Team Build {idx + 1}" for idx, tb in enumerate(self.teambuilds)]
                self.copy_combo_index = max(0, min(self.copy_combo_index, len(names) - 1))
                PyImGui.push_item_width(max(200.0, available_width - 90.0))
                self.copy_combo_index = PyImGui.combo(
                    "##copy_source", self.copy_combo_index, names
                )
                PyImGui.pop_item_width()
                PyImGui.same_line(0, spacing)
                if PyImGui.button("Copy", width=80):
                    clone = self.clone_teambuild(self.teambuilds[self.copy_combo_index])
                    if clone.name:
                        clone.name = f"{clone.name} (Copy)"
                    self.teambuilds.append(clone)
                    self.builds_changed = True
        PyImGui.end()

        if self.window_timer.HasElapsed(WINDOW_SAVE_INTERVAL_MS):
            if (int(end_pos[0]), int(end_pos[1])) != self.window_pos:
                self.window_pos = (int(end_pos[0]), int(end_pos[1]))
                ini_handler.write_key(MODULE_NAME, "x", str(self.window_pos[0]))
                ini_handler.write_key(MODULE_NAME, "y", str(self.window_pos[1]))
            if new_collapsed != self.window_collapsed:
                self.window_collapsed = new_collapsed
                ini_handler.write_key(MODULE_NAME, "collapsed", str(self.window_collapsed))
            self.window_timer.Reset()

    def draw_edit_windows(self) -> None:
        for idx in range(len(self.teambuilds)):
            if idx >= len(self.teambuilds):
                break
            teambuild = self.teambuilds[idx]
            if not teambuild.edit_open:
                continue
            window_label = f"{teambuild.name or 'Team Build'}##hero_build_{teambuild.ui_id}"
            PyImGui.set_next_window_size(600, 0)
            is_open = PyImGui.begin(window_label, True, PyImGui.WindowFlags.AlwaysAutoResize)
            self.mark_visible()
            if not is_open:
                PyImGui.end()
                continue

            new_name = PyImGui.input_text("Team Build Name", teambuild.name)
            if new_name != teambuild.name:
                teambuild.name = new_name
                self.builds_changed = True

            PyImGui.spacing()
            PyImGui.text("Slot")
            PyImGui.same_line(0, 80)
            PyImGui.text("Name")
            PyImGui.same_line(0, 170)
            PyImGui.text("Template Code")

            for slot, build in enumerate(teambuild.builds):
                PyImGui.spacing()
                label = "Player" if slot == 0 else f"Hero #{slot}"
                PyImGui.text(label)
                PyImGui.same_line(0, 80)

                PyImGui.push_item_width(150)
                new_build_name = PyImGui.input_text(f"##name_{teambuild.ui_id}_{slot}", build.name)
                PyImGui.pop_item_width()
                if new_build_name != build.name:
                    build.name = new_build_name
                    self.builds_changed = True

                PyImGui.same_line(0, 10)
                PyImGui.push_item_width(260)
                new_code = PyImGui.input_text(f"##code_{teambuild.ui_id}_{slot}", build.code)
                PyImGui.pop_item_width()
                if new_code != build.code:
                    build.code = new_code
                    self.builds_changed = True
                if PyImGui.is_item_hovered() and build.code.strip():
                    PyImGui.set_tooltip(build.code.strip())

                io = PyImGui.get_io()
                if slot > 0:
                    PyImGui.same_line(0, 10)
                    PyImGui.push_item_width(170)
                    current_index = build.hero_index if build.hero_index >= 0 else 0
                    hero_labels = [self._hero_label(idx) or "No Hero" for idx in range(len(HERO_INDEX_TO_ID))]
                    new_index = PyImGui.combo(
                        f"##hero_{teambuild.ui_id}_{slot}", current_index, hero_labels
                    )
                    PyImGui.pop_item_width()
                    if new_index != build.hero_index:
                        build.hero_index = new_index
                        self.builds_changed = True

                    PyImGui.same_line(0, 6)
                    new_panel = PyImGui.checkbox(
                        f"Show Panel##panel_{teambuild.ui_id}_{slot}", build.show_panel
                    )
                    if new_panel != build.show_panel:
                        build.show_panel = new_panel
                        self.builds_changed = True

                    PyImGui.same_line(0, 6)
                    icon = BEHAVIOR_ICONS.get(build.behavior, IconsFontAwesome5.ICON_SHIELD_ALT)
                    if PyImGui.button(
                        f"{icon}##behavior_{teambuild.ui_id}_{slot}", width=40
                    ):
                        build.behavior = (build.behavior + 1) % 3
                        self.builds_changed = True
                    tooltip = BEHAVIOR_TOOLTIPS.get(build.behavior, "Hero behaviour")
                    if PyImGui.is_item_hovered():
                        PyImGui.set_tooltip(tooltip)

                PyImGui.same_line(0, 6)
                view_label = "Send" if io.key_ctrl else "View"
                if PyImGui.button(
                    f"{view_label}##view_{teambuild.ui_id}_{slot}", width=70
                ):
                    if io.key_ctrl:
                        self._send_slot(teambuild, build, slot)
                    else:
                        self.view_build(teambuild, slot)
                if PyImGui.is_item_hovered():
                    tooltip = (
                        "Click to send to team chat"
                        if io.key_ctrl
                        else "Click to copy the build string to clipboard. Hold Ctrl to send instead."
                    )
                    PyImGui.set_tooltip(tooltip)

                PyImGui.same_line(0, 6)
                if PyImGui.button(
                    f"Load##slot_load_{teambuild.ui_id}_{slot}", width=60
                ):
                    self._load_slot(build, slot)
                if PyImGui.is_item_hovered():
                    tip = "Load build on Player" if slot == 0 else "Load build on Hero"
                    PyImGui.set_tooltip(tip)

            PyImGui.spacing()
            if PyImGui.button(f"Up##order_up_{teambuild.ui_id}") and idx > 0:
                self.teambuilds[idx - 1], self.teambuilds[idx] = self.teambuilds[idx], self.teambuilds[idx - 1]
                self.builds_changed = True
            if PyImGui.is_item_hovered():
                PyImGui.set_tooltip("Move the team build up in the list")

            PyImGui.same_line(0, 6)
            if (
                PyImGui.button(f"Down##order_down_{teambuild.ui_id}")
                and idx < len(self.teambuilds) - 1
            ):
                self.teambuilds[idx], self.teambuilds[idx + 1] = (
                    self.teambuilds[idx + 1],
                    self.teambuilds[idx],
                )
                self.builds_changed = True
            if PyImGui.is_item_hovered():
                PyImGui.set_tooltip("Move the team build down in the list")

            PyImGui.same_line(0, 6)
            if PyImGui.button(f"Delete##delete_{teambuild.ui_id}"):
                PyImGui.open_popup(f"Delete Team Build?##{teambuild.ui_id}")
            if PyImGui.is_item_hovered():
                PyImGui.set_tooltip("Delete this team build")

            PyImGui.same_line(0, 6)
            PyImGui.push_item_width(150)
            mode_labels = ["Don't change", "Normal Mode", "Hard Mode"]
            new_mode = PyImGui.combo(
                f"Mode##mode_{teambuild.ui_id}", teambuild.mode, mode_labels
            )
            PyImGui.pop_item_width()
            if new_mode != teambuild.mode:
                teambuild.mode = new_mode
                self.builds_changed = True

            PyImGui.spacing()
            close_width = PyImGui.get_content_region_avail()[0]
            if PyImGui.button(f"Close##close_{teambuild.ui_id}", width=max(120.0, close_width)):
                teambuild.edit_open = False

            if PyImGui.begin_popup_modal(
                f"Delete Team Build?##{teambuild.ui_id}", True, PyImGui.WindowFlags.AlwaysAutoResize
            ):
                PyImGui.text("Are you sure? This operation cannot be undone.")
                if PyImGui.button("Delete", width=120):
                    del self.teambuilds[idx]
                    self.builds_changed = True
                    PyImGui.close_current_popup()
                    PyImGui.end_popup_modal()
                    PyImGui.end()
                    return
                PyImGui.same_line(0, 10)
                if PyImGui.button("Cancel", width=120):
                    PyImGui.close_current_popup()
                PyImGui.end_popup_modal()

            PyImGui.end()

    def _process_send_queue(self) -> None:
        if not self.send_queue:
            return
        if not self.send_timer.HasElapsed(CHAT_DELAY_MS):
            return
        message = self.send_queue.popleft()
        GLOBAL_CACHE.Player.SendChat('#', message)
        self.send_timer.Reset()

    def _process_pending_hero_loads(self) -> None:
        if not self.pending_hero_loads:
            return
        if not self._is_outpost():
            self.pending_hero_loads.clear()
            return
        if self.kick_timer.IsRunning() and not self.kick_timer.HasElapsed(KICK_DELAY_MS):
            return
        for load in list(self.pending_hero_loads):
            if load.process(self):
                self.pending_hero_loads.remove(load)
                break

    def _get_instance_type(self) -> Optional[str]:
        try:
            instance = Map.map_instance()
            return instance.instance_type.GetName()
        except Exception:
            return None

    def _is_outpost(self) -> bool:
        try:
            return Map.IsOutpost()
        except Exception:
            return False

    def _get_player_login_number(self) -> int:
        try:
            agent_id = Player.GetAgentID()
            return Party.Players.GetLoginNumberByAgentID(agent_id) or 0
        except Exception:
            return 0

    @staticmethod
    def _hero_id_from_party_member(hero) -> Optional[int]:
        hero_obj = getattr(hero, "hero_id", None)
        if hero_obj is None:
            return None
        if hasattr(hero_obj, "GetID"):
            try:
                return int(hero_obj.GetID())
            except Exception:
                pass
        if hasattr(hero_obj, "id"):
            try:
                return int(hero_obj.id)
            except Exception:
                pass
        try:
            return int(hero_obj)
        except Exception:
            return None


state = HeroBuildsState()


def draw_widget() -> None:
    state.draw_main_window()
    state.draw_edit_windows()


def configure() -> None:
    if PyImGui.begin(
        f"{MODULE_NAME} Settings##config", PyImGui.WindowFlags.AlwaysAutoResize
    ):
        hide = PyImGui.checkbox(
            "Hide hero build windows when entering explorable areas",
            state.hide_when_entering_explorable,
        )
        if hide != state.hide_when_entering_explorable:
            state.hide_when_entering_explorable = hide
            ini_handler.write_key(
                MODULE_NAME, "hide_when_entering_explorable", str(hide)
            )
        single_window = PyImGui.checkbox(
            "Only show one team build window at a time",
            state.one_teambuild_at_a_time,
        )
        if single_window != state.one_teambuild_at_a_time:
            state.one_teambuild_at_a_time = single_window
            ini_handler.write_key(
                MODULE_NAME, "one_teambuild_at_a_time", str(single_window)
            )
        PyImGui.spacing()
        PyImGui.text_wrapped(
            "View copies the build string to the clipboard so you can paste it in game."
        )
    PyImGui.end()


def main() -> None:
    try:
        state.begin_frame()
        state.update_environment()
        state.process_async_tasks()

        if not Routines.Checks.Map.MapValid():
            return
        if not (
            Routines.Checks.Map.IsMapReady()
            and Routines.Checks.Party.IsPartyLoaded()
        ):
            return

        if not state.should_hide_window():
            draw_widget()
    except ImportError as exc:
        Py4GW.Console.Log(
            MODULE_NAME,
            f"ImportError encountered: {exc}",
            Py4GW.Console.MessageType.Error,
        )
        Py4GW.Console.Log(
            MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error
        )
    except ValueError as exc:
        Py4GW.Console.Log(
            MODULE_NAME,
            f"ValueError encountered: {exc}",
            Py4GW.Console.MessageType.Error,
        )
        Py4GW.Console.Log(
            MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error
        )
    except TypeError as exc:
        Py4GW.Console.Log(
            MODULE_NAME,
            f"TypeError encountered: {exc}",
            Py4GW.Console.MessageType.Error,
        )
        Py4GW.Console.Log(
            MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error
        )
    except Exception as exc:  # noqa: BLE001
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Unexpected error encountered: {exc}",
            Py4GW.Console.MessageType.Error,
        )
        Py4GW.Console.Log(
            MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error
        )
    finally:
        state.end_frame()


if __name__ == "__main__":
    main()
