import os
import configparser
from dataclasses import dataclass, field
from typing import Any, List, Optional

import Py4GW  # type: ignore

from HeroAI.cache_data import CacheData
from Py4GWCoreLib import (
    GLOBAL_CACHE,
    IconsFontAwesome5,
    ImGui,
    IniHandler,
    Map,
    Party,
    Player,
    PyImGui,
    Routines,
    Timer,
    ChatChannel,
)
from Py4GWCoreLib.enums import HeroType

MODULE_NAME = "Hero Builds"

BUFFER_SIZE = 128
TEAM_SIZE = 8
_BASE64_TABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

script_directory = os.path.dirname(os.path.abspath(__file__))
root_directory = os.path.normpath(os.path.join(script_directory, ".."))
CONFIG_DIRECTORY = os.path.join(root_directory, "Widgets", "Config")
os.makedirs(CONFIG_DIRECTORY, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIRECTORY, "HeroBuilds.ini")

WINDOW_SECTION = "HeroBuildsWindow"
CONFIG_WINDOW_SECTION = "HeroBuildsConfig"

ini_handler = IniHandler(CONFIG_FILE)

cached_data = CacheData()

window_module = ImGui.WindowModule(
    MODULE_NAME,
    window_name="Hero Builds",
    window_size=(300, 250),
    window_flags=PyImGui.WindowFlags.NoFlag,
)
config_module = ImGui.WindowModule(
    f"Config {MODULE_NAME}",
    window_name="Hero Builds Settings",
    window_size=(280, 120),
    window_flags=PyImGui.WindowFlags.NoFlag,
)

window_save_timer = Timer()
window_save_timer.Start()
config_save_timer = Timer()
config_save_timer.Start()
autosave_timer = Timer()
autosave_timer.Start()
send_timer = Timer()
send_timer.Start()
kickall_timer = Timer()

hide_when_entering_explorable = ini_handler.read_bool(
    WINDOW_SECTION, "hide_when_entering_explorable", False
)
one_teambuild_at_a_time = ini_handler.read_bool(
    WINDOW_SECTION, "one_teambuild_at_a_time", False
)

window_module.window_pos = (
    ini_handler.read_int(WINDOW_SECTION, "x", 100),
    ini_handler.read_int(WINDOW_SECTION, "y", 100),
)
window_module.collapse = ini_handler.read_bool(WINDOW_SECTION, "collapsed", False)
window_module.window_size = (
    ini_handler.read_int(WINDOW_SECTION, "width", window_module.window_size[0]),
    ini_handler.read_int(WINDOW_SECTION, "height", window_module.window_size[1]),
)

config_module.window_pos = (
    ini_handler.read_int(CONFIG_WINDOW_SECTION, "x", 120),
    ini_handler.read_int(CONFIG_WINDOW_SECTION, "y", 120),
)
config_module.collapse = ini_handler.read_bool(
    CONFIG_WINDOW_SECTION, "collapsed", False
)
config_module.window_size = (
    ini_handler.read_int(CONFIG_WINDOW_SECTION, "width", config_module.window_size[0]),
    ini_handler.read_int(CONFIG_WINDOW_SECTION, "height", config_module.window_size[1]),
)

last_instance_type = "Loading"
old_visibility_state = False
collapse_main_window_next_frame = False

send_queue: List[str] = []
kicking_heroes = False

_next_team_ui_id = 0


def _font_scale(io: PyImGui.ImGuiIO) -> float:
    """Return the global font scale with a safe fallback."""

    return getattr(io, "FontGlobalScale", getattr(io, "font_global_scale", 1.0))


def _style_component(style: Any, attribute: str, component: int = 0, default: float = 0.0) -> float:
    """Retrieve a style vector component across differing ImGui bindings."""

    value = getattr(style, attribute, None)
    if value is None:
        return default
    if isinstance(value, (tuple, list)):
        try:
            return float(value[component])
        except (IndexError, TypeError, ValueError):
            return default
    attr_name = "xy"[component] if component < 2 else ""
    if attr_name and hasattr(value, attr_name):
        try:
            return float(getattr(value, attr_name))
        except (TypeError, ValueError):
            return default
    value_attr = ("value1", "value2")
    if component < len(value_attr) and hasattr(value, value_attr[component]):
        component_value = getattr(value, value_attr[component])
        if component_value is not None:
            try:
                return float(component_value)
            except (TypeError, ValueError):
                return default
    if hasattr(value, "__getitem__"):
        try:
            return float(value[component])
        except (IndexError, TypeError, ValueError):
            return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _generate_ui_id() -> int:
    global _next_team_ui_id
    _next_team_ui_id += 1
    return _next_team_ui_id


HERO_INDEX_TO_ID: List[HeroType] = [
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

MERCENARY_IDS = {
    HeroType.MercenaryHero1,
    HeroType.MercenaryHero2,
    HeroType.MercenaryHero3,
    HeroType.MercenaryHero4,
    HeroType.MercenaryHero5,
    HeroType.MercenaryHero6,
    HeroType.MercenaryHero7,
    HeroType.MercenaryHero8,
}

HERO_DEFAULT_NAMES = {
    HeroType.None_: "No Hero",
    HeroType.Norgu: "Norgu",
    HeroType.Goren: "Goren",
    HeroType.Tahlkora: "Tahlkora",
    HeroType.MasterOfWhispers: "Master of Whispers",
    HeroType.AcolyteJin: "Acolyte Jin",
    HeroType.Koss: "Koss",
    HeroType.Dunkoro: "Dunkoro",
    HeroType.AcolyteSousuke: "Acolyte Sousuke",
    HeroType.Melonni: "Melonni",
    HeroType.ZhedShadowhoof: "Zhed Shadowhoof",
    HeroType.GeneralMorgahn: "General Morgahn",
    HeroType.MagridTheSly: "Margrid the Sly",
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

HERO_BEHAVIOR_ICONS = {
    0: IconsFontAwesome5.ICON_FIST_RAISED,
    1: IconsFontAwesome5.ICON_SHIELD_ALT,
    2: IconsFontAwesome5.ICON_DOVE,
}

HERO_BEHAVIOR_TOOLTIPS = {
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
            HeroBuild(hero_index=-2 if i == 0 else 0, behavior=1)
            for i in range(TEAM_SIZE)
        ]
    )
    edit_open: bool = False
    window_first_run: bool = True
    ui_id: int = field(default_factory=_generate_ui_id)


@dataclass
class PendingHeroLoad:
    hero_id: HeroType
    code: str
    show_panel: bool
    behavior: int
    stage: str = "add"
    timer: Timer = field(default_factory=Timer)

    def __post_init__(self) -> None:
        self.code = self.code or ""
        if self.behavior not in (0, 1, 2):
            self.behavior = 1
        self.timer.Start()

    def process(self) -> bool:
        if Map.IsMapReady() and not Map.IsOutpost():
            return True
        if self.stage == "add":
            GLOBAL_CACHE.Party.Heroes.AddHero(int(self.hero_id))
            self.timer.Reset()
            self.stage = "wait"
            return False
        if self.stage == "wait":
            if self.timer.HasElapsed(1000):
                return True
            hero_info = _find_party_hero(self.hero_id)
            if hero_info is None:
                return False
            hero_index, hero_member = hero_info
            if self.code:
                GLOBAL_CACHE.SkillBar.LoadHeroSkillTemplate(hero_index, self.code)
            if hero_member.agent_id and self.behavior in (0, 1, 2):
                GLOBAL_CACHE.Party.Heroes.SetHeroBehavior(hero_member.agent_id, self.behavior)
            return True
        return True


def _get_player_login_number() -> Optional[int]:
    agent_id = GLOBAL_CACHE.Player.GetAgentID()
    if not agent_id:
        return None
    login_number = GLOBAL_CACHE.Party.Players.GetLoginNumberByAgentID(agent_id)
    return login_number or None


def _find_party_hero(hero_id: HeroType) -> Optional[tuple[int, Any]]:
    heroes = GLOBAL_CACHE.Party.GetHeroes() or []
    owner_login = _get_player_login_number()
    if owner_login is None:
        return None
    for index, hero in enumerate(heroes, start=1):
        try:
            hero_login = hero.owner_player_id
            hero_id_value = hero.hero_id.GetID()
        except AttributeError:
            continue
        if hero_login == owner_login and hero_id_value == int(hero_id):
            return index, hero
    return None


def _player_hero_count() -> int:
    heroes = GLOBAL_CACHE.Party.GetHeroes() or []
    owner_login = _get_player_login_number()
    if owner_login is None:
        return 0
    count = 0
    for hero in heroes:
        try:
            if hero.owner_player_id == owner_login:
                count += 1
        except AttributeError:
            continue
    return count


def _get_instance_type() -> str:
    if Map.IsMapLoading():
        return "Loading"
    if Map.IsOutpost():
        return "Outpost"
    if Map.IsExplorable():
        return "Explorable"
    return "Instance"


def _hero_name_from_id(hero_id: HeroType) -> str:
    if hero_id in MERCENARY_IDS:
        try:
            name = GLOBAL_CACHE.Party.Heroes.GetHeroNameById(int(hero_id))
            if name:
                return name
        except Exception:
            pass
    return HERO_DEFAULT_NAMES.get(hero_id, "Unknown Hero")


def _hero_label_from_index(hero_index: int) -> str:
    if hero_index <= 0 or hero_index >= len(HERO_INDEX_TO_ID):
        return ""
    hero_id = HERO_INDEX_TO_ID[hero_index]
    return _hero_name_from_id(hero_id)


def _hero_selection_options() -> List[tuple[str, int]]:
    options: List[tuple[str, int]] = [("<Choose Hero>", -1), ("No Hero", 0)]
    for idx in range(1, len(HERO_INDEX_TO_ID)):
        hero_id = HERO_INDEX_TO_ID[idx]
        options.append((_hero_name_from_id(hero_id), idx))
    return options


def _profession_to_int(profession: Any) -> int:
    if profession is None:
        return 0
    for attr in ("ToInt", "value"):
        if hasattr(profession, attr):
            try:
                value = getattr(profession, attr)
                return int(value() if callable(value) else value)
            except Exception:
                continue
    try:
        return int(profession)
    except Exception:
        return 0


def _collect_professions(agent_id: int, hero_member: Any | None = None) -> tuple[int, int]:
    primary = 0
    secondary = 0
    if hero_member is not None:
        primary = _profession_to_int(getattr(hero_member, "primary", None))
        secondary = _profession_to_int(getattr(hero_member, "secondary", None))
    if not primary and not secondary:
        try:
            profs = GLOBAL_CACHE.Agent.GetProfessionIDs(agent_id)
            if isinstance(profs, (tuple, list)) and len(profs) >= 2:
                primary = _profession_to_int(profs[0])
                secondary = _profession_to_int(profs[1])
        except Exception:
            primary = secondary = 0
    return max(0, min(primary, 10)), max(0, min(secondary, 10))


def _collect_attributes(agent_id: int) -> List[tuple[int, int]]:
    attributes: List[tuple[int, int]] = []
    if not agent_id:
        return attributes
    try:
        raw_attributes = GLOBAL_CACHE.Agent.GetAttributes(agent_id) or []
    except Exception:
        return attributes
    for attr in raw_attributes:
        attr_id = getattr(attr, "attribute_id", getattr(attr, "attribute", 0))
        try:
            attr_id_int = int(attr_id)
        except Exception:
            continue
        points = getattr(attr, "level", None)
        if points in (None, 0):
            points = getattr(attr, "level_base", 0)
        try:
            points_int = int(points)
        except Exception:
            continue
        if attr_id_int <= 0 or points_int <= 0:
            continue
        attributes.append((attr_id_int, max(0, min(points_int, 15))))
        if len(attributes) >= 16:
            break
    return attributes


def _player_skill_ids() -> List[int]:
    skills: List[int] = []
    for slot in range(1, 9):
        try:
            skill_id = GLOBAL_CACHE.SkillBar.GetSkillIDBySlot(slot)
        except Exception:
            skill_id = 0
        try:
            skill_int = int(skill_id)
        except Exception:
            skill_int = 0
        skills.append(max(0, skill_int))
    return skills


def _hero_skill_ids(hero_index: int) -> List[int]:
    try:
        if hero_index <= 0:
            return [0] * 8
        hero_bar = GLOBAL_CACHE.SkillBar.GetHeroSkillbar(hero_index)
    except Exception:
        hero_bar = None
    skills: List[int] = []
    for idx in range(8):
        skill_id = 0
        if hero_bar is not None and idx < len(hero_bar):
            skill = hero_bar[idx]
            value = getattr(skill, "id", 0)
            if hasattr(value, "id"):
                value = getattr(value, "id", 0)
            if not isinstance(value, int):
                try:
                    value = int(value)
                except Exception:
                    value = 0
            skill_id = max(0, value)
        skills.append(skill_id)
    return skills


def _append_bits(buffer: List[int], value: int, count: int) -> None:
    for bit in range(count):
        buffer.append((value >> bit) & 1)


def _encode_skill_template(primary: int, secondary: int, attributes: List[tuple[int, int]], skills: List[int]) -> str:
    bitstream: List[int] = []
    _append_bits(bitstream, 14, 4)
    _append_bits(bitstream, 0, 4)
    bits_per_prof = max(4, primary.bit_length(), secondary.bit_length())
    if bits_per_prof % 2:
        bits_per_prof += 1
    bits_per_prof = min(max(bits_per_prof, 4), 10)
    _append_bits(bitstream, (bits_per_prof - 4) // 2, 2)
    _append_bits(bitstream, primary, bits_per_prof)
    _append_bits(bitstream, secondary, bits_per_prof)
    filtered_attributes = [(attr_id, points) for attr_id, points in attributes if attr_id and points]
    bits_per_attr = 4
    for attr_id, _ in filtered_attributes:
        bits_per_attr = max(bits_per_attr, int(attr_id).bit_length())
    filtered_attributes = filtered_attributes[:16]
    _append_bits(bitstream, len(filtered_attributes), 4)
    _append_bits(bitstream, max(bits_per_attr, 4) - 4, 4)
    for attr_id, points in filtered_attributes:
        _append_bits(bitstream, int(attr_id), max(bits_per_attr, 4))
        _append_bits(bitstream, int(points), 4)
    padded_skills = (skills + [0] * 8)[:8]
    bits_per_skill = 8
    for skill_id in padded_skills:
        bits_per_skill = max(bits_per_skill, int(skill_id).bit_length())
    _append_bits(bitstream, max(bits_per_skill, 8) - 8, 4)
    for skill_id in padded_skills:
        _append_bits(bitstream, int(skill_id), max(bits_per_skill, 8))
    while len(bitstream) % 6:
        bitstream.append(0)
    encoded_chars: List[str] = []
    for idx in range(0, len(bitstream), 6):
        value = 0
        for bit_offset in range(6):
            value |= bitstream[idx + bit_offset] << bit_offset
        encoded_chars.append(_BASE64_TABLE[value])
    return "".join(encoded_chars)


def _encode_agent_template(
    agent_id: int, hero_index: Optional[int], hero_member: Any | None
) -> str:
    if not agent_id:
        return ""
    primary, secondary = _collect_professions(agent_id, hero_member)
    if hero_index:
        skills = _hero_skill_ids(hero_index)
    else:
        skills = _player_skill_ids()
    if not any(skills):
        return ""
    attributes = _collect_attributes(agent_id)
    try:
        return _encode_skill_template(primary, secondary, attributes, skills)
    except Exception:
        return ""


def _hero_index_from_id_value(hero_id_value: int) -> int:
    for idx, hero_type in enumerate(HERO_INDEX_TO_ID):
        try:
            if int(hero_type) == int(hero_id_value):
                return idx
        except Exception:
            continue
    return 0


def _hero_behavior_from_member(hero_member: Any) -> int:
    behavior = getattr(hero_member, "hero_behavior", None)
    if behavior is None:
        return 1
    try:
        return int(behavior)
    except Exception:
        return 1


def _format_build_label(tbuild: TeamHeroBuild, slot: int) -> str:
    build = tbuild.builds[slot]
    name = (build.name or "").strip()
    code = (build.code or "").strip()
    if slot == 0:
        suffix = "Player"
    else:
        suffix = _hero_label_from_index(build.hero_index)
    if not name:
        return suffix
    if suffix:
        return f"{name} ({suffix})"
    if code:
        return name
    return ""


def _format_chat_message(tbuild: TeamHeroBuild, slot: int) -> Optional[str]:
    build = tbuild.builds[slot]
    name = _format_build_label(tbuild, slot)
    code = (build.code or "").strip()
    if not name and not code:
        return None
    if code:
        return f"[{name};{code}]" if name else f"[{code}]"
    return name


def _send_chat_message(message: str) -> None:
    send_queue.append(message)


def _send_teambuild(tbuild: TeamHeroBuild) -> None:
    if tbuild.name.strip():
        _send_chat_message(tbuild.name.strip())
    for idx in range(len(tbuild.builds)):
        if idx == 0:
            build = tbuild.builds[idx]
            if not (build.name.strip() or build.code.strip()):
                continue
        msg = _format_chat_message(tbuild, idx)
        if msg:
            _send_chat_message(msg)


def _send_single_build(tbuild: TeamHeroBuild, slot: int) -> None:
    msg = _format_chat_message(tbuild, slot)
    if msg:
        _send_chat_message(msg)


def _view_build(tbuild: TeamHeroBuild, slot: int) -> None:
    msg = _format_chat_message(tbuild, slot)
    if not msg:
        return
    Player.SendFakeChat(ChatChannel.CHANNEL_ALL, msg)


def _load_teambuild(tbuild: TeamHeroBuild) -> None:
    global kicking_heroes
    if not Map.IsOutpost():
        Py4GW.Console.Log(
            MODULE_NAME,
            "Teambuilds can only be loaded while in an outpost.",
            Py4GW.Console.MessageType.Warning,
        )
        return
    GLOBAL_CACHE.Party.Heroes.KickAllHeroes()
    kickall_timer.Reset()
    kickall_timer.Start()
    kicking_heroes = True
    if tbuild.mode == 1:
        GLOBAL_CACHE.Party.SetNormalMode()
    elif tbuild.mode == 2:
        GLOBAL_CACHE.Party.SetHardMode()
    for idx in range(len(tbuild.builds)):
        _load_single_build(tbuild, idx)
    send_timer.Reset()


def _load_single_build(tbuild: TeamHeroBuild, slot: int) -> None:
    build = tbuild.builds[slot]
    code = (build.code or "").strip()
    if slot == 0:
        if code:
            GLOBAL_CACHE.SkillBar.LoadSkillTemplate(code)
        return
    if build.hero_index <= 0 or build.hero_index >= len(HERO_INDEX_TO_ID):
        return
    hero_id = HERO_INDEX_TO_ID[build.hero_index]
    if hero_id == HeroType.None_:
        return
    pending_hero_loads.append(
        PendingHeroLoad(hero_id=hero_id, code=code, show_panel=build.show_panel, behavior=build.behavior)
    )


def _copy_teambuild(source: TeamHeroBuild, suffix: str = " (Copy)") -> TeamHeroBuild:
    clone = TeamHeroBuild()
    clone.name = f"{source.name}{suffix}" if source.name else suffix.strip()
    clone.mode = source.mode
    clone.builds = [
        HeroBuild(
            name=hb.name,
            code=hb.code,
            hero_index=hb.hero_index,
            behavior=hb.behavior,
            show_panel=hb.show_panel,
        )
        for hb in source.builds
    ]
    clone.edit_open = True
    return clone


def _add_teambuild_from_current() -> None:
    global builds_changed
    new_tb = TeamHeroBuild()
    new_tb.edit_open = True
    builds: List[HeroBuild] = []
    player_agent = GLOBAL_CACHE.Player.GetAgentID()
    player_code = _encode_agent_template(player_agent, None, None)
    builds.append(HeroBuild(hero_index=0, code=player_code or ""))
    hero_members = GLOBAL_CACHE.Party.GetHeroes() or []
    hero_lookup = {idx: member for idx, member in enumerate(hero_members[: TEAM_SIZE - 1])}
    for slot in range(1, TEAM_SIZE):
        member = hero_lookup.get(slot - 1)
        hero_index = 0
        behavior = 1
        code = ""
        agent_id = 0
        hero_id_value = 0
        try:
            agent_id = GLOBAL_CACHE.Party.Heroes.GetHeroAgentIDByPartyPosition(slot - 1)
        except Exception:
            agent_id = 0
        if member is not None:
            member_agent = getattr(member, "agent_id", 0)
            if not agent_id and isinstance(member_agent, int):
                agent_id = member_agent
            hero_id_obj = getattr(member, "hero_id", None)
            if hero_id_obj is not None:
                if hasattr(hero_id_obj, "GetID"):
                    try:
                        hero_id_value = int(hero_id_obj.GetID())
                    except Exception:
                        hero_id_value = 0
                else:
                    try:
                        hero_id_value = int(hero_id_obj)
                    except Exception:
                        hero_id_value = 0
            behavior = _hero_behavior_from_member(member)
        if not hero_id_value:
            try:
                hero_id_value = GLOBAL_CACHE.Party.Heroes.GetHeroIDByPartyPosition(slot - 1) or 0
            except Exception:
                hero_id_value = 0
        hero_index = _hero_index_from_id_value(hero_id_value)
        template_index: Optional[int] = hero_index if hero_index > 0 else None
        if agent_id and template_index is not None:
            code = _encode_agent_template(agent_id, template_index, member)
        builds.append(
            HeroBuild(
                hero_index=hero_index if hero_index > 0 else 0,
                behavior=behavior,
                code=code or "",
            )
        )
    new_tb.builds = builds
    teambuilds.append(new_tb)
    builds_changed = True


teambuilds: List[TeamHeroBuild] = []
pending_hero_loads: List[PendingHeroLoad] = []
selected_teambuild_for_copy = 0
builds_changed = False


def _load_from_file() -> None:
    global teambuilds, builds_changed, selected_teambuild_for_copy
    config = ini_handler.reload()
    teambuilds = []
    sections = [
        section
        for section in config.sections()
        if section.lower().startswith("builds")
    ]
    sections.sort()
    for section in sections:
        tb = TeamHeroBuild()
        tb.name = config.get(section, "buildname", fallback="")
        tb.mode = config.getint(section, "mode", fallback=0)
        builds: List[HeroBuild] = []
        for idx in range(TEAM_SIZE):
            name_key = f"name{idx}"
            template_key = f"template{idx}"
            hero_index_key = f"heroindex{idx}"
            panel_key = f"panel{idx}"
            behavior_key = f"behavior{idx}"
            hero_index = config.getint(section, hero_index_key, fallback=-1)
            if hero_index < -2:
                hero_index = -1
            if hero_index >= len(HERO_INDEX_TO_ID):
                hero_index = 0
            behavior = config.getint(section, behavior_key, fallback=1)
            if behavior not in (0, 1, 2):
                behavior = 1
            builds.append(
                HeroBuild(
                    name=config.get(section, name_key, fallback=""),
                    code=config.get(section, template_key, fallback=""),
                    hero_index=hero_index,
                    behavior=behavior,
                    show_panel=config.getint(section, panel_key, fallback=0) == 1,
                )
            )
        tb.builds = builds
        teambuilds.append(tb)
    builds_changed = False
    selected_teambuild_for_copy = 0


def _save_to_file(force: bool = False) -> None:
    global builds_changed
    if not (force or builds_changed):
        return
    config = configparser.ConfigParser()
    if hide_when_entering_explorable or one_teambuild_at_a_time:
        config[WINDOW_SECTION] = {
            "hide_when_entering_explorable": str(hide_when_entering_explorable),
            "one_teambuild_at_a_time": str(one_teambuild_at_a_time),
            "x": str(int(window_module.window_pos[0])),
            "y": str(int(window_module.window_pos[1])),
            "collapsed": str(window_module.collapse),
            "width": str(int(window_module.window_size[0])),
            "height": str(int(window_module.window_size[1])),
        }
    else:
        config[WINDOW_SECTION] = {
            "x": str(int(window_module.window_pos[0])),
            "y": str(int(window_module.window_pos[1])),
            "collapsed": str(window_module.collapse),
            "width": str(int(window_module.window_size[0])),
            "height": str(int(window_module.window_size[1])),
        }
    config[CONFIG_WINDOW_SECTION] = {
        "x": str(int(config_module.window_pos[0])),
        "y": str(int(config_module.window_pos[1])),
        "collapsed": str(config_module.collapse),
        "width": str(int(config_module.window_size[0])),
        "height": str(int(config_module.window_size[1])),
    }
    for index, tb in enumerate(teambuilds):
        section = f"builds{index:03d}"
        config[section] = {
            "buildname": tb.name,
            "mode": str(tb.mode),
        }
        for slot, build in enumerate(tb.builds):
            config[section][f"name{slot}"] = build.name
            config[section][f"template{slot}"] = build.code
            config[section][f"heroindex{slot}"] = str(build.hero_index)
            config[section][f"panel{slot}"] = "1" if build.show_panel else "0"
            config[section][f"behavior{slot}"] = str(build.behavior)
    ini_handler.config = config
    ini_handler.save(config)
    builds_changed = False


_load_from_file()


def _update_window_state() -> None:
    if window_save_timer.HasElapsed(1000):
        pos = PyImGui.get_window_pos()
        window_module.window_pos = (int(pos[0]), int(pos[1]))
        window_module.collapse = PyImGui.is_window_collapsed()
        size = PyImGui.get_window_size()
        window_module.window_size = (int(size[0]), int(size[1]))
        ini_handler.write_key(WINDOW_SECTION, "x", int(window_module.window_pos[0]))
        ini_handler.write_key(WINDOW_SECTION, "y", int(window_module.window_pos[1]))
        ini_handler.write_key(WINDOW_SECTION, "collapsed", window_module.collapse)
        ini_handler.write_key(WINDOW_SECTION, "width", int(window_module.window_size[0]))
        ini_handler.write_key(WINDOW_SECTION, "height", int(window_module.window_size[1]))
        window_save_timer.Reset()


def _update_config_window_state() -> None:
    if config_save_timer.HasElapsed(1000):
        pos = PyImGui.get_window_pos()
        config_module.window_pos = (int(pos[0]), int(pos[1]))
        config_module.collapse = PyImGui.is_window_collapsed()
        size = PyImGui.get_window_size()
        config_module.window_size = (int(size[0]), int(size[1]))
        ini_handler.write_key(CONFIG_WINDOW_SECTION, "x", int(config_module.window_pos[0]))
        ini_handler.write_key(CONFIG_WINDOW_SECTION, "y", int(config_module.window_pos[1]))
        ini_handler.write_key(CONFIG_WINDOW_SECTION, "collapsed", config_module.collapse)
        ini_handler.write_key(CONFIG_WINDOW_SECTION, "width", int(config_module.window_size[0]))
        ini_handler.write_key(CONFIG_WINDOW_SECTION, "height", int(config_module.window_size[1]))
        config_save_timer.Reset()


def _process_send_queue() -> None:
    if not send_queue:
        return
    if send_timer.HasElapsed(600):
        message = send_queue.pop(0)
        Player.SendChat('#', message)
        send_timer.Reset()


def _process_pending_loads() -> None:
    global kicking_heroes
    if kicking_heroes:
        if not Map.IsOutpost() or kickall_timer.HasElapsed(500) or _player_hero_count() == 0:
            kicking_heroes = False
    if not Map.IsOutpost():
        pending_hero_loads.clear()
        return
    if kicking_heroes or not pending_hero_loads:
        return
    if pending_hero_loads[0].process():
        pending_hero_loads.pop(0)


def _handle_instance_change(instance_type: str) -> None:
    global collapse_main_window_next_frame
    if instance_type == "Explorable" and hide_when_entering_explorable:
        collapse_main_window_next_frame = True
        for tb in teambuilds:
            tb.edit_open = False
    if instance_type == "Loading":
        send_queue.clear()
        pending_hero_loads.clear()


def _update_state() -> None:
    global last_instance_type
    instance_type = _get_instance_type()
    if instance_type != last_instance_type:
        _handle_instance_change(instance_type)
        last_instance_type = instance_type
    _process_send_queue()
    _process_pending_loads()
    if builds_changed and autosave_timer.HasElapsed(3000):
        _save_to_file()
        autosave_timer.Reset()


def _draw_main_window() -> bool:
    global collapse_main_window_next_frame, selected_teambuild_for_copy, builds_changed
    if window_module.first_run:
        PyImGui.set_next_window_size(
            window_module.window_size[0], window_module.window_size[1]
        )
        PyImGui.set_next_window_pos(window_module.window_pos[0], window_module.window_pos[1])
        PyImGui.set_next_window_collapsed(window_module.collapse, 0)
        window_module.first_run = False
    if collapse_main_window_next_frame:
        PyImGui.set_next_window_collapsed(True, PyImGui.ImGuiCond.Always)
        collapse_main_window_next_frame = False
    window_open = PyImGui.begin(window_module.window_name, window_module.window_flags)
    try:
        if not window_open:
            return False
        io = PyImGui.get_io()
        button_width = 60.0 * _font_scale(io)
        item_spacing = _style_component(ImGui.get_style(), "ItemInnerSpacing")
        for index, tbuild in enumerate(teambuilds):
            PyImGui.push_id(str(tbuild.ui_id))
            display_name = tbuild.name or f"Teambuild {index + 1}"
            available_width = PyImGui.get_content_region_avail()[0]
            main_button_width = max(0.0, available_width - button_width - item_spacing)
            if PyImGui.button(display_name, main_button_width):
                if one_teambuild_at_a_time and not tbuild.edit_open:
                    for other in teambuilds:
                        other.edit_open = False
                tbuild.edit_open = not tbuild.edit_open
            PyImGui.same_line(0, item_spacing)
            action_label = "Send" if io.key_ctrl else "Load"
            if PyImGui.button(action_label, button_width):
                if io.key_ctrl:
                    _send_teambuild(tbuild)
                else:
                    _load_teambuild(tbuild)
            tooltip = (
                "Click to send to team chat" if io.key_ctrl else "Click to load builds to heroes and player"
            )
            PyImGui.show_tooltip(tooltip)
            PyImGui.pop_id()
        PyImGui.separator()
        if PyImGui.button("Add Teambuild", PyImGui.get_content_region_avail()[0]):
            new_tb = TeamHeroBuild()
            new_tb.edit_open = True
            teambuilds.append(new_tb)
            builds_changed = True
        if PyImGui.button(
            "Add Teambuild from Current", PyImGui.get_content_region_avail()[0]
        ):
            _add_teambuild_from_current()
        PyImGui.show_tooltip("Capture the current player and hero skill bars into a new teambuild.")
        if teambuilds:
            options = [tb.name or f"Teambuild {idx + 1}" for idx, tb in enumerate(teambuilds)]
            if selected_teambuild_for_copy >= len(options):
                selected_teambuild_for_copy = 0
            PyImGui.push_item_width(-60.0 - item_spacing)
            selected_teambuild_for_copy = PyImGui.combo("##teambuild_select", selected_teambuild_for_copy, options)
            PyImGui.pop_item_width()
            PyImGui.same_line(0, item_spacing)
            if PyImGui.button("Copy", 60.0):
                clone = _copy_teambuild(teambuilds[selected_teambuild_for_copy])
                teambuilds.append(clone)
                builds_changed = True
        return True
    finally:
        _update_window_state()
        PyImGui.end()


def _draw_teambuild_editor(tbuild: TeamHeroBuild, index: int) -> None:
    global builds_changed
    window_name = f"{tbuild.name or f'Teambuild {index + 1}'}##HeroBuild{tbuild.ui_id}"
    if tbuild.window_first_run:
        PyImGui.set_next_window_size(520, 0)
        tbuild.window_first_run = False
    expanded, tbuild.edit_open = PyImGui.begin_with_close(
        window_name,
        tbuild.edit_open,
        PyImGui.WindowFlags.NoFlag,
    )
    try:
        if not expanded:
            return
        name_input = PyImGui.input_text("Hero Build Name", tbuild.name, BUFFER_SIZE)
        if name_input != tbuild.name:
            tbuild.name = name_input
            builds_changed = True
        io = PyImGui.get_io()
        item_spacing = _style_component(ImGui.get_style(), "ItemInnerSpacing")
        button_width = 55.0 * _font_scale(io)
        icon_width = button_width / 1.75
        label_width = (PyImGui.get_content_region_avail()[0] - (button_width * 2) - icon_width * 3 - item_spacing * 5) / 3
        PyImGui.set_cursor_pos_x(button_width)
        PyImGui.text("Name")
        PyImGui.same_line(button_width + label_width + item_spacing, 0.0)
        PyImGui.text("Template")
        hero_options = _hero_selection_options()
        for slot, build in enumerate(tbuild.builds):
            PyImGui.push_id(str(slot))
            PyImGui.set_cursor_pos_x(0)
            PyImGui.text("P" if slot == 0 else f"H#{slot}")
            PyImGui.same_line(button_width, 0.0)
            PyImGui.push_item_width(label_width)
            new_name = PyImGui.input_text("##name", build.name, BUFFER_SIZE)
            if new_name != build.name:
                build.name = new_name
                builds_changed = True
            PyImGui.pop_item_width()
            PyImGui.same_line(button_width + label_width + item_spacing, 0.0)
            PyImGui.push_item_width(label_width)
            new_code = PyImGui.input_text("##code", build.code, BUFFER_SIZE)
            if new_code != build.code:
                build.code = new_code
                builds_changed = True
            PyImGui.pop_item_width()
            if slot > 0:
                PyImGui.same_line(
                    button_width + label_width * 2 + item_spacing * 2, 0.0
                )
                PyImGui.push_item_width(label_width)
                option_labels = [label for label, _ in hero_options]
                current_index = next((i for i, (_, value) in enumerate(hero_options) if value == build.hero_index), 0)
                selected = PyImGui.combo("##hero", current_index, option_labels)
                hero_value = hero_options[selected][1]
                if hero_value != build.hero_index:
                    build.hero_index = hero_value
                    builds_changed = True
                PyImGui.pop_item_width()
                PyImGui.same_line(0, item_spacing)
                icon = IconsFontAwesome5.ICON_EYE if build.show_panel else IconsFontAwesome5.ICON_EYE_SLASH
                if PyImGui.button(icon, icon_width):
                    build.show_panel = not build.show_panel
                    builds_changed = True
                PyImGui.show_tooltip("Hero panel visibility toggle (not yet supported).")
                PyImGui.same_line(0, item_spacing)
                behaviour_icon = HERO_BEHAVIOR_ICONS.get(build.behavior, IconsFontAwesome5.ICON_SHIELD_ALT)
                if PyImGui.button(behaviour_icon, icon_width):
                    build.behavior = (build.behavior + 1) % 3
                    builds_changed = True
                PyImGui.show_tooltip(HERO_BEHAVIOR_TOOLTIPS.get(build.behavior, "Hero behaviour"))
            else:
                PyImGui.same_line(
                    button_width + label_width * 2 + item_spacing * 2, 0.0
                )
                PyImGui.text_disabled("Player")
                PyImGui.same_line(
                    0,
                    item_spacing + icon_width * 2 + item_spacing * 2,
                )
            action_label = "Send" if io.key_ctrl else "View"
            if PyImGui.button(action_label, button_width):
                if io.key_ctrl:
                    _send_single_build(tbuild, slot)
                else:
                    _view_build(tbuild, slot)
            tooltip = "Click to send to team chat" if io.key_ctrl else "Click to view build locally"
            PyImGui.show_tooltip(tooltip)
            PyImGui.same_line(0, item_spacing)
            if PyImGui.button("Load", button_width):
                _load_single_build(tbuild, slot)
            PyImGui.show_tooltip("Load build onto {}".format("player" if slot == 0 else "hero"))
            PyImGui.pop_id()
        PyImGui.spacing()
        if PyImGui.small_button("Up") and index > 0:
            teambuilds[index - 1], teambuilds[index] = teambuilds[index], teambuilds[index - 1]
            builds_changed = True
        PyImGui.show_tooltip("Move the teambuild up in the list")
        PyImGui.same_line(0, item_spacing)
        if PyImGui.small_button("Down") and index + 1 < len(teambuilds):
            teambuilds[index], teambuilds[index + 1] = teambuilds[index + 1], teambuilds[index]
            builds_changed = True
        PyImGui.show_tooltip("Move the teambuild down in the list")
        PyImGui.same_line(0, item_spacing)
        if PyImGui.small_button("Delete"):
            PyImGui.open_popup("Delete Teambuild?")
        PyImGui.show_tooltip("Delete the teambuild")
        PyImGui.same_line(0, item_spacing)
        PyImGui.push_item_width(110.0)
        mode_labels = ["Don't change", "Normal Mode", "Hard Mode"]
        new_mode = PyImGui.combo("Mode", tbuild.mode, mode_labels)
        PyImGui.pop_item_width()
        if new_mode != tbuild.mode:
            tbuild.mode = new_mode
            builds_changed = True
        close_button_x = (
            PyImGui.get_window_content_region_max()[0]
            - _style_component(ImGui.get_style(), "WindowPadding")
            - 40
        )
        PyImGui.same_line(close_button_x, 0.0)
        if PyImGui.button("Close", PyImGui.get_content_region_avail()[0]):
            tbuild.edit_open = False
        PyImGui.show_tooltip("Close this window")
        if PyImGui.begin_popup_modal("Delete Teambuild?", True, PyImGui.WindowFlags.AlwaysAutoResize):
            PyImGui.text("Are you sure? This operation cannot be undone.\n")
            if PyImGui.button("OK", 120):
                del teambuilds[index]
                builds_changed = True
                tbuild.edit_open = False
                PyImGui.close_current_popup()
            PyImGui.same_line(0, item_spacing)
            if PyImGui.button("Cancel", 120):
                PyImGui.close_current_popup()
            PyImGui.end_popup_modal()
    finally:
        PyImGui.end()


def draw_widget(_: CacheData) -> None:
    _update_state()
    main_window_expanded = _draw_main_window()
    for idx, tbuild in enumerate(list(teambuilds)):
        if tbuild.edit_open:
            _draw_teambuild_editor(tbuild, idx)
    global old_visibility_state
    cur_visible = bool(main_window_expanded) or any(tb.edit_open for tb in teambuilds)
    if cur_visible and not old_visibility_state:
        _load_from_file()
    elif not cur_visible and old_visibility_state:
        _save_to_file()
    old_visibility_state = cur_visible


def configure() -> None:
    global hide_when_entering_explorable, one_teambuild_at_a_time, builds_changed
    if config_module.first_run:
        PyImGui.set_next_window_size(
            config_module.window_size[0], config_module.window_size[1]
        )
        PyImGui.set_next_window_pos(config_module.window_pos[0], config_module.window_pos[1])
        PyImGui.set_next_window_collapsed(config_module.collapse, 0)
        config_module.first_run = False
    if not PyImGui.begin(config_module.window_name, config_module.window_flags):
        PyImGui.end()
        return
    try:
        new_hide = PyImGui.checkbox(
            "Hide Hero Builds when entering explorable areas",
            hide_when_entering_explorable,
        )
        if new_hide != hide_when_entering_explorable:
            hide_when_entering_explorable = new_hide
            ini_handler.write_key(WINDOW_SECTION, "hide_when_entering_explorable", hide_when_entering_explorable)
        new_single = PyImGui.checkbox(
            "Only show one teambuild editor at a time",
            one_teambuild_at_a_time,
        )
        if new_single != one_teambuild_at_a_time:
            one_teambuild_at_a_time = new_single
            ini_handler.write_key(WINDOW_SECTION, "one_teambuild_at_a_time", one_teambuild_at_a_time)
        PyImGui.show_tooltip("Close other teambuild windows when you open a new one")
    finally:
        _update_config_window_state()
        PyImGui.end()


def main() -> None:
    try:
        if not Routines.Checks.Map.MapValid():
            return
        cached_data.Update()
        if Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded():
            draw_widget(cached_data)
    except ImportError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"ImportError encountered: {exc}", Py4GW.Console.MessageType.Error)
    except ValueError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"ValueError encountered: {exc}", Py4GW.Console.MessageType.Error)
    except TypeError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"TypeError encountered: {exc}", Py4GW.Console.MessageType.Error)
    except Exception as exc:  # noqa: BLE001
        Py4GW.Console.Log(MODULE_NAME, f"Unexpected error encountered: {exc}", Py4GW.Console.MessageType.Error)


if __name__ == "__main__":
    main()
