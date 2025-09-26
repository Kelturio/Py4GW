from Py4GWCoreLib import *

from typing import Optional
from collections import defaultdict


module_name = "Mod Handler"
json_file_path = "modifiers.json"

from enum import Enum

window_module = ImGui.WindowModule("Item Compare", window_name="Item Compare", window_size=(300, 300))


class ModifierInfo:
    def __init__(self, identifier: int, 
                 name: str, 
                 arg: str, 
                 arg_eval_fn,      
                 arg1: str, 
                 arg1_eval_fn,     
                 arg2: str,
                 arg2_eval_fn,
                 representation):
        self.identifier = identifier
        self.name = name
        self.arg = arg
        self.arg_eval_fn = arg_eval_fn
        self.arg1 = arg1
        self.arg1_eval_fn = arg1_eval_fn
        self.arg2 = arg2
        self.arg2_eval_fn = arg2_eval_fn
        self.representation = representation if callable(representation) else (lambda *args: "")

modifiers = {}

def add_modifier(modifier):
    global modifiers
    next_key = len(modifiers)  # Get the next available key
    modifiers[next_key] = modifier


ARMOR_MODIFIERS_HEX_DATA = [
    # region warrior
    (9224, 505, 1, 249, "Knight's Insignia"),  # 240801F9
    (9224, 520, 2, 8, "Lieutenant's Insignia"),  # 24080208
    (9224, 521, 2, 9, "Stonefist Insignia"),  # 24080209
    (9224, 506, 1, 250, "Dreadnought Insignia"),  # 240801FA
    (9224, 507, 1, 251, "Sentinel's Insignia"),  # 240801FB
    (9224, 252, 0, 252, "Rune of Minor Absorption"),  # 240800FC
    (8680, 5377, 21, 1, "Rune of Minor Tactics"),  # 21E81501
    (8680, 4353, 17, 1, "Rune of Minor Strength"),  # 21E81101
    (8680, 4609, 18, 1, "Rune of Minor Axe Mastery"),  # 21E81201
    (8680, 4865, 19, 1, "Rune of Minor Hammer Mastery"),  # 21E81301
    (8680, 5121, 20, 1, "Rune of Minor Swordsmanship"),  # 21E81401
    (9224, 253, 0, 253, "Rune of Major Absorption"),  # 240800FD
    (8680, 5378, 21, 2, "Rune of Major Tactics"),  # 21E81502
    (8680, 4354, 17, 2, "Rune of Major Strength"),  # 21E81102
    (8680, 4610, 18, 2, "Rune of Major Axe Mastery"),  # 21E81202
    (8680, 4866, 19, 2, "Rune of Major Hammer Mastery"),  # 21E81302
    (8680, 5122, 20, 2, "Rune of Major Swordsmanship"),  # 21E81402
    (9224, 254, 0, 254, "Rune of Superior Absorption"),  # 240800FE
    (8680, 5379, 21, 3, "Rune of Superior Tactics"),  # 21E81503
    (8680, 4355, 17, 3, "Rune of Superior Strength"),  # 21E81103
    (8680, 4611, 18, 3, "Rune of Superior Axe Mastery"),  # 21E81203
    (8680, 4867, 19, 3, "Rune of Superior Hammer Mastery"),  # 21E81303
    (8680, 5123, 20, 3, "Rune of Superior Swordsmanship"),  # 21E81403
    # endregion
    # region ranger
    (9224, 508, 1, 252, "Frostbound Insignia"),  # 240801FC
    (9224, 510, 1, 254, "Pyrebound Insignia"),  # 240801FE
    (9224, 511, 1, 255, "Stormbound Insignia"),  # 240801FF
    (9224, 513, 2, 1, "Scout's Insignia"),  # 24080201
    (9224, 509, 1, 253, "Earthbound Insignia"),  # 240801FD
    (9224, 512, 2, 0, "Beastmaster's Insignia"),  # 24080200
    (8680, 6145, 24, 1, "Rune of Minor Wilderness Survival"),  # 21E81801
    (8680, 5889, 23, 1, "Rune of Minor Expertise"),  # 21E81701
    (8680, 5633, 22, 1, "Rune of Minor Beast Mastery"),  # 21E81601
    (8680, 6401, 25, 1, "Rune of Minor Marksmanship"),  # 21E81901
    (8680, 6146, 24, 2, "Rune of Major Wilderness Survival"),  # 21E81802
    (8680, 5890, 23, 2, "Rune of Major Expertise"),  # 21E81702
    (8680, 5634, 22, 2, "Rune of Major Beast Mastery"),  # 21E81602
    (8680, 6402, 25, 2, "Rune of Major Marksmanship"),  # 21E81902
    (8680, 6147, 24, 3, "Rune of Superior Wilderness Survival"),  # 21E81803
    (8680, 5891, 23, 3, "Rune of Superior Expertise"),  # 21E81703
    (8680, 5635, 22, 3, "Rune of Superior Beast Mastery"),  # 21E81603
    (8680, 6403, 25, 3, "Rune of Superior Marksmanship"),  # 21E81903
    # endregion
    # region monk
    (9224, 502, 1, 246, "Wanderer's Insignia"),  # 240801F6
    (9224, 503, 1, 247, "Disciple's Insignia"),  # 240801F7
    (9224, 504, 1, 248, "Anchorite's Insignia"),  # 240801F8
    (8680, 3329, 13, 1, "Rune of Minor Healing Prayers"),  # 21E80D01
    (8680, 3585, 14, 1, "Rune of Minor Smiting Prayers"),  # 21E80E01
    (8680, 3841, 15, 1, "Rune of Minor Protection Prayers"),  # 21E80F01
    (8680, 4097, 16, 1, "Rune of Minor Divine Favor"),  # 21E81001
    (8680, 3330, 13, 2, "Rune of Major Healing Prayers"),  # 21E80D02
    (8680, 3586, 14, 2, "Rune of Major Smiting Prayers"),  # 21E80E02
    (8680, 3842, 15, 2, "Rune of Major Protection Prayers"),  # 21E80F02
    (8680, 4098, 16, 2, "Rune of Major Divine Favor"),  # 21E81002
    (8680, 3331, 13, 3, "Rune of Superior Healing Prayers"),  # 21E80D03
    (8680, 3587, 14, 3, "Rune of Superior Smiting Prayers"),  # 21E80E03
    (8680, 3843, 15, 3, "Rune of Superior Protection Prayers"),  # 21E80F03
    (8680, 4099, 16, 3, "Rune of Superior Divine Favor"),  # 21E81003
    # endregion
    # region necromancer
    (9224, 522, 2, 10, "Bloodstained Insignia"),  # 2408020A
    (9224, 492, 1, 236, "Tormentor's Insignia"),  # 240801EC
    (9224, 494, 1, 238, "Bonelace Insignia"),  # 240801EE
    (9224, 495, 1, 239, "Minion Master's Insignia"),  # 240801EF
    (9224, 496, 1, 240, "Blighter's Insignia"),  # 240801F0
    (9224, 493, 1, 237, "Undertaker's Insignia"),  # 240801ED
    (8680, 1025, 4, 1, "Rune of Minor Blood Magic"),  # 21E80401
    (8680, 1281, 5, 1, "Rune of Minor Death Magic"),  # 21E80501
    (8680, 1793, 7, 1, "Rune of Minor Curses"),  # 21E80701
    (8680, 1537, 6, 1, "Rune of Minor Soul Reaping"),  # 21E80601
    (8680, 1026, 4, 2, "Rune of Major Blood Magic"),  # 21E80402
    (8680, 1282, 5, 2, "Rune of Major Death Magic"),  # 21E80502
    (8680, 1794, 7, 2, "Rune of Major Curses"),  # 21E80702
    (8680, 1538, 6, 2, "Rune of Major Soul Reaping"),  # 21E80602
    (8680, 1027, 4, 3, "Rune of Superior Blood Magic"),  # 21E80403
    (8680, 1283, 5, 3, "Rune of Superior Death Magic"),  # 21E80503
    (8680, 1795, 7, 3, "Rune of Superior Curses"),  # 21E80703
    (8680, 1539, 6, 3, "Rune of Superior Soul Reaping"),  # 21E80603
    # endregion
    # region mesmer
    (9224, 484, 1, 228, "Virtuoso's Insignia"),  # 240801E4
    (9224, 482, 1, 226, "Artificer's Insignia"),  # 240801E2
    (9224, 483, 1, 227, "Prodigy's Insignia"),  # 240801E3
    (8680, 1, 0, 1, "Rune of Minor Fast Casting"),  # 21E80001
    (8680, 513, 2, 1, "Rune of Minor Domination Magic"),  # 21E80201
    (8680, 257, 1, 1, "Rune of Minor Illusion Magic"),  # 21E80101
    (8680, 769, 3, 1, "Rune of Minor Inspiration Magic"),  # 21E80301
    (8680, 2, 0, 2, "Rune of Major Fast Casting"),  # 21E80002
    (8680, 514, 2, 2, "Rune of Major Domination Magic"),  # 21E80202
    (8680, 258, 1, 2, "Rune of Major Illusion Magic"),  # 21E80102
    (8680, 770, 3, 2, "Rune of Major Inspiration Magic"),  # 21E80302
    (8680, 3, 0, 3, "Rune of Superior Fast Casting"),  # 21E80003
    (8680, 515, 2, 3, "Rune of Superior Domination Magic"),  # 21E80203
    (8680, 259, 1, 3, "Rune of Superior Illusion Magic"),  # 21E80103
    (8680, 771, 3, 3, "Rune of Superior Inspiration Magic"),  # 21E80303
    # endregion
    # region elementalist
    (9224, 498, 1, 242, "Hydromancer Insignia"),  # 240801F2
    (9224, 499, 1, 243, "Geomancer Insignia"),  # 240801F3
    (9224, 500, 1, 244, "Pyromancer Insignia"),  # 240801F4
    (9224, 501, 1, 245, "Aeromancer Insignia"),  # 240801F5
    (9224, 497, 1, 241, "Prismatic Insignia"),  # 240801F1
    (8680, 3073, 12, 1, "Rune of Minor Energy Storage"),  # 21E80C01
    (8680, 2561, 10, 1, "Rune of Minor Fire Magic"),  # 21E80A01
    (8680, 2049, 8, 1, "Rune of Minor Air Magic"),  # 21E80801
    (8680, 2305, 9, 1, "Rune of Minor Earth Magic"),  # 21E80901
    (8680, 2817, 11, 1, "Rune of Minor Water Magic"),  # 21E80B01
    (8680, 3074, 12, 2, "Rune of Major Energy Storage"),  # 21E80C02
    (8680, 2562, 10, 2, "Rune of Major Fire Magic"),  # 21E80A02
    (8680, 2050, 8, 2, "Rune of Major Air Magic"),  # 21E80802
    (8680, 2306, 9, 2, "Rune of Major Earth Magic"),  # 21E80902
    (8680, 2818, 11, 2, "Rune of Major Water Magic"),  # 21E80B02
    (8680, 3075, 12, 3, "Rune of Superior Energy Storage"),  # 21E80C03
    (8680, 2563, 10, 3, "Rune of Superior Fire Magic"),  # 21E80A03
    (8680, 2051, 8, 3, "Rune of Superior Air Magic"),  # 21E80803
    (8680, 2307, 9, 3, "Rune of Superior Earth Magic"),  # 21E80903
    (8680, 2819, 11, 3, "Rune of Superior Water Magic"),  # 21E80B03
    # endregion
    # region assassin
    (9224, 478, 1, 222, "Vanguard's Insignia"),  # 240801DE
    (9224, 479, 1, 223, "Infiltrator's Insignia"),  # 240801DF
    (9224, 480, 1, 224, "Saboteur's Insignia"),  # 240801E0
    (9224, 481, 1, 225, "Nightstalker's Insignia"),  # 240801E1
    (8680, 8961, 35, 1, "Rune of Minor Critical Strikes"),  # 21E82301
    (8680, 7425, 29, 1, "Rune of Minor Dagger Mastery"),  # 21E81D01
    (8680, 7681, 30, 1, "Rune of Minor Deadly Arts"),  # 21E81E01
    (8680, 7937, 31, 1, "Rune of Minor Shadow Arts"),  # 21E81F01
    (8680, 8962, 35, 2, "Rune of Major Critical Strikes"),  # 21E82302
    (8680, 7426, 29, 2, "Rune of Major Dagger Mastery"),  # 21E81D02
    (8680, 7682, 30, 2, "Rune of Major Deadly Arts"),  # 21E81E02
    (8680, 7938, 31, 2, "Rune of Major Shadow Arts"),  # 21E81F02
    (8680, 8963, 35, 3, "Rune of Superior Critical Strikes"),  # 21E82303
    (8680, 7427, 29, 3, "Rune of Superior Dagger Mastery"),  # 21E81D03
    (8680, 7683, 30, 3, "Rune of Superior Deadly Arts"),  # 21E81E03
    (8680, 7939, 31, 3, "Rune of Superior Shadow Arts"),  # 21E81F03
    # endregion
    # region ritualist
    (9224, 516, 2, 4, "Shaman's Insignia"),  # 24080204
    (9224, 517, 2, 5, "Ghost Forge Insignia"),  # 24080205
    (9224, 518, 2, 6, "Mystic's Insignia"),  # 24080206
    (8680, 8705, 34, 1, "Rune of Minor Channeling Magic"),  # 21E82201
    (8680, 8449, 33, 1, "Rune of Minor Restoration Magic"),  # 21E82101
    (8680, 8193, 32, 1, "Rune of Minor Communing"),  # 21E82001
    (8680, 9217, 36, 1, "Rune of Minor Spawning Power"),  # 21E82401
    (8680, 8706, 34, 2, "Rune of Major Channeling Magic"),  # 21E82202
    (8680, 8450, 33, 2, "Rune of Major Restoration Magic"),  # 21E82102
    (8680, 8194, 32, 2, "Rune of Major Communing"),  # 21E82002
    (8680, 9218, 36, 2, "Rune of Major Spawning Power"),  # 21E82402
    (8680, 8707, 34, 3, "Rune of Superior Channeling Magic"),  # 21E82203
    (8680, 8451, 33, 3, "Rune of Superior Restoration Magic"),  # 21E82103
    (8680, 8195, 32, 3, "Rune of Superior Communing"),  # 21E82003
    (8680, 9219, 36, 3, "Rune of Superior Spawning Power"),  # 21E82403
    # endregion
    # region dervish
    (9224, 514, 2, 2, "Windwalker Insignia"),  # 24080202
    (9224, 515, 2, 3, "Forsaken Insignia"),  # 24080203
    (8680, 11265, 44, 1, "Rune of Minor Mysticism"),  # 21E82C01
    (8680, 11009, 43, 1, "Rune of Minor Earth Prayers"),  # 21E82B01
    (8680, 10497, 41, 1, "Rune of Minor Scythe Mastery"),  # 21E82901
    (8680, 10753, 42, 1, "Rune of Minor Wind Prayers"),  # 21E82A01
    (8680, 11266, 44, 2, "Rune of Major Mysticism"),  # 21E82C02
    (8680, 11010, 43, 2, "Rune of Major Earth Prayers"),  # 21E82B02
    (8680, 10498, 41, 2, "Rune of Major Scythe Mastery"),  # 21E82902
    (8680, 10754, 42, 2, "Rune of Major Wind Prayers"),  # 21E82A02
    (8680, 11267, 44, 3, "Rune of Superior Mysticism"),  # 21E82C03
    (8680, 11011, 43, 3, "Rune of Superior Earth Prayers"),  # 21E82B03
    (8680, 10499, 41, 3, "Rune of Superior Scythe Mastery"),  # 21E82903
    (8680, 10755, 42, 3, "Rune of Superior Wind Prayers"),  # 21E82A03
    # endregion
    # region paragon
    (9224, 519, 2, 7, "Centurion's Insignia"),  # 24080207
    (8680, 10241, 40, 1, "Rune of Minor Leadership"),  # 21E82801
    (8680, 9985, 39, 1, "Rune of Minor Motivation"),  # 21E82701
    (8680, 9729, 38, 1, "Rune of Minor Command"),  # 21E82601
    (8680, 9473, 37, 1, "Rune of Minor Spear Mastery"),  # 21E82501
    (8680, 10242, 40, 2, "Rune of Major Leadership"),  # 21E82802
    (8680, 9986, 39, 2, "Rune of Major Motivation"),  # 21E82702
    (8680, 9730, 38, 2, "Rune of Major Command"),  # 21E82602
    (8680, 9474, 37, 2, "Rune of Major Spear Mastery"),  # 21E82502
    (8680, 10243, 40, 3, "Rune of Superior Leadership"),  # 21E82803
    (8680, 9987, 39, 3, "Rune of Superior Motivation"),  # 21E82703
    (8680, 9731, 38, 3, "Rune of Superior Command"),  # 21E82603
    (8680, 9475, 37, 3, "Rune of Superior Spear Mastery"),  # 21E82503
    # endregion
    # region common
    (9224, 486, 1, 230, "Survivor Insignia"),  # 240801E6
    (9224, 485, 1, 229, "Radiant Insignia"),  # 240801E5
    (9224, 487, 1, 231, "Stalwart Insignia"),  # 240801E7
    (9224, 488, 1, 232, "Brawler's Insignia"),  # 240801E8
    (9224, 489, 1, 233, "Blessed Insignia"),  # 240801E9
    (9224, 490, 1, 234, "Herald's Insignia"),  # 240801EA
    (9224, 491, 1, 235, "Sentry's Insignia"),  # 240801EB
    (9224, 529, 2, 17, "Rune of Attunement"),  # 24080211
    (9224, 531, 2, 19, "Rune of Recovery"),  # 24080213
    (9224, 532, 2, 20, "Rune of Restoration"),  # 24080214
    (9224, 533, 2, 21, "Rune of Clarity"),  # 24080215
    (9224, 534, 2, 22, "Rune of Purity"),  # 24080216
    (9224, 255, 0, 255, "Rune of Minor Vigor"),  # 240800FF
    (9224, 194, 0, 194, "Rune of Minor Vigor"),  # 240800C2
    (9224, 257, 1, 1, "Rune of Superior Vigor"),  # 24080101
    (9224, 256, 1, 0, "Rune of Major Vigor"),  # 24080100
    (9224, 530, 2, 18, "Rune of Vitae"),  # 24080212
    # endregion
]


def _build_armor_modifier_lookup():
    lookup = {}
    for identifier, arg, arg1, arg2, label in ARMOR_MODIFIERS_HEX_DATA:
        lookup.setdefault(identifier, {})[arg] = {
            "name": label,
            "arg1": arg1,
            "arg2": arg2,
        }
    return lookup


_ARMOR_MODIFIER_LOOKUP = _build_armor_modifier_lookup()
ARMOR_MODIFIER_NAMES = {
    arg: data["name"] for arg, data in _ARMOR_MODIFIER_LOOKUP.get(0x2408, {}).items()
}


def GetArmorModifierName(arg_value: int) -> str:
    if not isinstance(arg_value, int):
        return str(arg_value)
    if arg_value in ARMOR_MODIFIER_NAMES:
        return ARMOR_MODIFIER_NAMES[arg_value]
    return f"Unknown armor modifier (0x{arg_value:04X})"

def find_modifier(identifier: int) -> Optional[ModifierInfo]:
    for mod in modifiers.values():
        if mod.identifier == identifier:
            return mod
    return None


def group_modifiers_by_identifier(modifier_list):
    grouped = defaultdict(list)
    for modifier in modifier_list:
        try:
            identifier = modifier.GetIdentifier()
        except AttributeError:
            continue
        grouped[identifier].append(modifier)
    return grouped

 #Helper functions to determine mod values 

def Value(value):
    return value

def GetAttributeName(attribute_id):
    try:
        return Attribute(attribute_id).name
    except ValueError:
        return attribute_id

def GetDamageType(damage_type_id):
    try:
        return DamageType(damage_type_id).name
    except ValueError:
        return damage_type_id

def GetAilment(ailment_id):
    try:
        return Ailment(ailment_id).name
    except ValueError:
        return ailment_id

def GetReducedAilment(ailment_id):
    try:
        return Reduced_Ailment(ailment_id).name
    except ValueError:
        return ailment_id

def GetInscription(inscription_id):
    try:
        return Inscription(inscription_id).name
    except ValueError:
        return inscription_id

# configure modifiers
add_modifier(ModifierInfo(
    identifier=8216,
     
    name='Inscription: "To the Pain!"',
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Armor",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor -{arg2} (while attacking)"
))

add_modifier(ModifierInfo(
    identifier=8312,
     
    name='Inscription: "Luck of the Draw"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Attribute", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Recieved physical damage -{arg2} (Chance: {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=8328,
     
    name='Inscription: "Sheltered by faith"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Recieved physical damage -{arg2} (while Enchanted)"
))

add_modifier(ModifierInfo(
    identifier=8344,
     
    name='Inscription: "Nothing to Fear"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Recieved physical damage -{arg2} (while Hexed)"
))

add_modifier(ModifierInfo(
    identifier=8360,
     
    name='Inscription: "Run For Your Life!"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Recieved physical damage -{arg2} (while in a Stance)"
))

add_modifier(ModifierInfo(
    identifier=8376,
     
    name='Inscription: "Brawn over Brains"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Energy -{arg2}"
))

add_modifier(ModifierInfo(
    identifier=8392,
     
    name='Energy regeneration', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Degen",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Energy regeneration -{arg2}"
))

add_modifier(ModifierInfo(
    identifier=8408,
     
    name='Inscription: "Life is Pain" / Superior Rune',  
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None,
    arg2="INVALID",
    arg2_eval_fn=lambda value: Value(value), 
    representation=lambda arg, arg1, arg2: f"Health +/-{arg2}"
))

add_modifier(ModifierInfo(
    identifier=8424,
     
    name='Vampiric', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Health regeneration -{arg2}"
))

add_modifier(ModifierInfo(
    identifier=8456,
     
    name='Armor', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Armor +{arg2}"
))


add_modifier(ModifierInfo(
    identifier=8488,
     
    name='Warding',
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Armor",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor +{arg2} (vs. elemental damage)"
))

add_modifier(ModifierInfo(
    identifier=8536,
     
    name='Shelter',
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Armor",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor +{arg2} (vs. physical damage)"
))

add_modifier(ModifierInfo(
    identifier=8568,
     
    name='Inscription: "Might makes Right"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value),
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor +{arg2} (while attacking)"
))

add_modifier(ModifierInfo(
    identifier=8584,
     
    name='Inscription: "Knowing is Half the Battle."', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value),
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor +{arg2} (while casting)"
))

add_modifier(ModifierInfo(
    identifier=8600,
     
    name='Inscription: "Faith is My Shield"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value),
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor +{arg2} (while Enchanted)"
))


add_modifier(ModifierInfo(
    identifier=8616,
     
    name='Inscription: "Hail to the King"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Above", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Damage",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor +{arg2} (while Health is above {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=8632,
     
    name='Inscription: "Down But Not Out"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Below", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Damage",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor +{arg2} (while Health is below {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=8648,
     
    name='Inscription: "Be Just and Fear Not"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value),
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor +{arg2} (while Hexed)"
))

add_modifier(ModifierInfo(
    identifier=8712,
     
    name='Inscription: "Don\'t Think Twice"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Halves casting time of spells (Chance: {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=8760,
     
    name='Damage"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Damage",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Damage +{arg2}%"
))

add_modifier(ModifierInfo(
    identifier=8792,
     
    name='Inscription: "Too Much Information"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Damage +{arg2}% (vs. Hexed foes)"
))

add_modifier(ModifierInfo(
    identifier=8808,
     
    name='Inscription: "Guided by Fate"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Damage +{arg2}% (while Enchanted)"
))

add_modifier(ModifierInfo(
    identifier=8824,
     
    name='Inscription: "Strength and Honor"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Above", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Damage",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Damage +{arg2}% (while Health is above {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=8840,
     
    name='Inscription: "Vengeance is Mine"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Below", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Damage",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Damage +{arg2}% (while Health is below {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=8856,
     
    name='Inscription: "Don\'t Fear the Reaper"',
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Damage +{arg2}% (while Hexed)"
))

add_modifier(ModifierInfo(
    identifier=8872,
     
    name='Inscription: "Dance With Death"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Damage +{arg2}% (while in a stance)"
))

add_modifier(ModifierInfo(
    identifier=8888,
     
    name='Of Enchanting', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Enchantments last {arg2}% longer"
))

add_modifier(ModifierInfo(
    identifier=8920,
     
    name='Insightful"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Above", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Damage",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Energy +{arg2}"
))

add_modifier(ModifierInfo(
    identifier=8952,
     
    name='Inscription: "Have faith"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Energy +{arg2} (while Enchanted)"
))

add_modifier(ModifierInfo(
    identifier=8968,
     
    name='Inscription: "Hale and Hearty"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Above", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Damage",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Energy +{arg2}% (while Health is above {arg1}%)"
))


add_modifier(ModifierInfo(
    identifier=8984,
     
    name='Inscription: "Don\'t call it a comeback!"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Below", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Damage",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Energy +{arg2}% (while Health is below {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=9000,
     
    name='Inscription: "I am Sorrow."', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Energy +{arg2} (while Hexed)"
))

add_modifier(ModifierInfo(
    identifier=9032,
     
    name='Health', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Health +{arg1}"
))

add_modifier(ModifierInfo(
    identifier=9064,
     
    name='Devotion', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Health +{arg1} (while Enchanted)"
))

add_modifier(ModifierInfo(
    identifier=9080,
     
    name='Health while Hexed"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Health +{arg1} (while Hexed)"
))

add_modifier(ModifierInfo(
    identifier=9096,
     
    name='Health wile in a stance"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value),
    arg2="Value",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Health +{arg1} (while in a stance)"
))

add_modifier(ModifierInfo(
    identifier=9112,
     
    name='Halves skill recharge of [Attribute] spells', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=lambda attribute_id: GetAttributeName(attribute_id),
    representation=lambda arg, arg1, arg2: f"Halves skill recharge of {arg2} spells (Chance: {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=9128,
     
    name='Inscription: "Let the Memory Live Again" / "Serenity Now"',
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Halves skill recharge of spells (Chance: {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=9144,
     
    name='Furious', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None,
    arg2="INVALID",
    arg2_eval_fn=lambda value: Value(value), 
    representation=lambda arg, arg1, arg2: f"Double adrenaline gain (Chance: {arg2}%)"
))

add_modifier(ModifierInfo(
    identifier=9208,
     
    name='Sundering', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor penetration +{arg2}% (Chance: {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=9224,

    name='Armor Modifier',
    arg="Modifier",
    arg_eval_fn=lambda value: GetArmorModifierName(value),
    arg1="INVALID",
    arg1_eval_fn=None,
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"{arg}"
))

add_modifier(ModifierInfo(
    identifier=9240,
     
    name="Mastery", 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Attribute", 
    arg1_eval_fn=lambda attribute_id: GetAttributeName(attribute_id), 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg1} +1 ({arg2} chance while using skills)"
))

add_modifier(ModifierInfo(
    identifier=9320,
     
    name='lengthens_condition', 
    arg="INVALID", 
    arg_eval_fn=lambda value: Value(value),
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value),
    arg2="Ailment",
    arg2_eval_fn=lambda damage_type_id: GetAilment(damage_type_id), 
    representation=lambda arg, arg1, arg2: f"Lenghtens {arg2} duration on foes by 33%"
))

add_modifier(ModifierInfo(
    identifier=9336,
     
    name='reduces_condition', 
    arg="INVALID", 
    arg_eval_fn=lambda value: Value(value),
    arg1="Ailment", 
    arg1_eval_fn=None,
    arg2="INVALID",
    arg2_eval_fn= lambda damage_type_id: GetAilment(damage_type_id),
    representation=lambda arg, arg1, arg2: f"Reduces {arg2} duration on you by 20% (Stacking)"
))

add_modifier(ModifierInfo(
    identifier=9400,
     
    name="Damage Type", 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Type", 
    arg1_eval_fn=lambda damage_type_id: GetDamageType(damage_type_id), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"{arg1} Dmg: "
))

add_modifier(ModifierInfo(
    identifier=9496,
     
    name='Zealous', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None,
    arg2="INVALID",
    arg2_eval_fn=lambda value: Value(value), 
    representation=lambda arg, arg1, arg2: f"Energy gain on hit: {arg2}"
))

add_modifier(ModifierInfo(
    identifier=9512,
     
    name='Vampiric', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Life Draining: {arg1}"
))

add_modifier(ModifierInfo(
    identifier=9520,
     
    name='Unknown 9520', 
    arg="Value", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg} , {arg1} , {arg2}"
))

add_modifier(ModifierInfo(
    identifier=9522,
     
    name='Unknown 9522', 
    arg="Value", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg} , {arg1} , {arg2}"
))

add_modifier(ModifierInfo(
    identifier=9720,
     
    name='Inscription: "Show me the money!"', 
    arg="INVALID", 
    arg_eval_fn=lambda value: Value(value),
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value),
    arg2="INVALID",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Improved sale value ({arg} , {arg1} , {arg2})"
))

add_modifier(ModifierInfo(
    identifier=9736,
     
    name='Inscription: "Measure for Measure"', 
    arg="INVALID", 
    arg_eval_fn=lambda value: Value(value),
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value),
    arg2="INVALID",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Highly salvageable ({arg} , {arg1} , {arg2})"
))

add_modifier(ModifierInfo(
    identifier=9752,
     
    name='Unknown 9752', 
    arg="Value", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg} , {arg1} , {arg2}"
))

add_modifier(ModifierInfo(
    identifier=9800,
     
    name='Unknown 9800', 
    arg="Value", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg} , {arg1} , {arg2}"
))

add_modifier(ModifierInfo(
    identifier=9880,
     
    name='Unknown 9880', 
    arg="Value", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg} , {arg1} , {arg2}"
))

add_modifier(ModifierInfo(
    identifier=10136,
     
    name="Requires", 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Attribute", 
    arg1_eval_fn=lambda attribute_id: GetAttributeName(attribute_id), 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"(Requires {arg2} {arg1})"
))

add_modifier(ModifierInfo(
    identifier=10248,
     
    name='Inscription: "Aptitude not Attitude"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Halves casting time of [Attribute] spells (Chance: {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=10280,
     
    name='Halves skill recharge of [Attribute] spells', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Halves skill recharge of [Attribute] spells (Chance: {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=10296,
     
    name='Inscription: "Master of My Domain"',  
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"[Attribute] +1 (Chance: {arg1}%)"
))

add_modifier(ModifierInfo(
    identifier=10328,
     
    name='reduces_condition', 
    arg="INVALID", 
    arg_eval_fn=lambda value: Value(value),
    arg1="Ailment", 
    arg1_eval_fn=lambda damage_type_id: GetReducedAilment(damage_type_id),
    arg2="INVALID",
    arg2_eval_fn= lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Reduces {arg1} duration on you by 20% (Stacking)"
))

add_modifier(ModifierInfo(
    identifier=25288,
     
    name='Inscription: "Seize the Day"', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Energy +{arg1}"
))

add_modifier(ModifierInfo(
    identifier=26568,
     
    name='Energy', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Above", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Damage",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Energy +{arg1}"
))

add_modifier(ModifierInfo(
    identifier=32784,
     
    name="Requires", 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Attribute", 
    arg1_eval_fn=lambda attribute_id: GetAttributeName(attribute_id), 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"(Requires {arg2} {arg1})"
))


add_modifier(ModifierInfo(
    identifier=32880,
     
    name='Unknown 32880', 
    arg="Value", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg} , {arg1} , {arg2}"
))

add_modifier(ModifierInfo(
    identifier=32896,
     
    name='Unknown 32896', 
    arg="Value", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg} , {arg1} , {arg2}"
))

add_modifier(ModifierInfo(
    identifier=41240,
     
    name="Inscription: Shield", 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Attribute", 
    arg1_eval_fn=lambda attribute_id: GetDamageType(attribute_id), 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"Armor +{arg2} (vs. {arg1} damage)"
))

add_modifier(ModifierInfo(
    identifier=41544,
     
    name='Deathbane', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="INVALID", 
    arg1_eval_fn=lambda value: Value(value),
    arg2="Value",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Dmg +{arg1}% (vs. undead)"
))

add_modifier(ModifierInfo(
    identifier=42288,
     
    name='Unknown 42288', 
    arg="Value", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None, 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg} , {arg1} , {arg2}"
))

add_modifier(ModifierInfo(
    identifier=42290,
     
    name='Inscription Name', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=None,
    arg2="INVALID",
    arg2_eval_fn=lambda attribute_id: GetInscription(attribute_id),
    representation=lambda arg, arg1, arg2: f"Inscription: {arg2}"
))

add_modifier(ModifierInfo(
    identifier=42920,
     
    name="Damage range", 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Max", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Min",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg2}-{arg1}"
))

add_modifier(ModifierInfo(
    identifier=42936,
     
    name='Shield Armor', 
    arg="INVALID", 
    arg_eval_fn=None, 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="INVALID",
    arg2_eval_fn=None,
    representation=lambda arg, arg1, arg2: f"Armor: {arg1}"
))

add_modifier(ModifierInfo(
    identifier=49152,
     
    name="Unknown 49152 InventoryItemtype?", 
    arg="Value", 
    arg_eval_fn=lambda value: Value(value), 
    arg1="Value", 
    arg1_eval_fn=lambda value: Value(value), 
    arg2="Value",
    arg2_eval_fn=lambda value: Value(value),
    representation=lambda arg, arg1, arg2: f"{arg} , {arg1} , {arg2}"
))

input_item1 = 0
input_item2 = 0
item1_id = 0
item2_id = 0
hovered_item = 0

def ShowOffhandItemdescription():
    try:
        global item1_id, item2_id, hovered_item
        global modifiers, window_module

        if window_module.first_run:
            PyImGui.set_next_window_size(window_module.window_size[0], window_module.window_size[1])     
            PyImGui.set_next_window_pos(window_module.window_pos[0], window_module.window_pos[1])
            window_module.first_run = False

        if PyImGui.begin(f"Offhand Item Description", window_module.window_flags):

            hovered_item = Inventory.GetHoveredItemID()
            PyImGui.text(f"Hovered Item: {hovered_item}")
            PyImGui.separator()

            bags_to_check = ItemArray.CreateBagList(1,2,3,4)
            item_array = ItemArray.GetItemArray(bags_to_check)

            item1_id = item_array[0] if item_array else None

            if not item1_id:
                PyImGui.text("No item selected for description.")
                PyImGui.end()
                return

            PyImGui.separator()

            
            item1_type_id, item1_type_name = Item.GetItemType(item1_id)
            PyImGui.text(f"Item 1 ID: {item1_id}")
            PyImGui.text(f"Type: {item1_type_id} - {item1_type_name}")


            modifiers1 = Item.Customization.Modifiers.GetModifiers(item1_id)
            if not modifiers1:
                PyImGui.text("No modifiers found.")
                PyImGui.end()
                return

            for modifier in modifiers1:
                identifier = modifier.GetIdentifier()
                mod_data = find_modifier(identifier)
                if not mod_data:
                    continue

                #check if the name of the modifier doesnt start weith "Unknown"
                if not mod_data.name.startswith("Unknown"):
                    arg, arg1, arg2 = modifier.GetArg(), modifier.GetArg1(), modifier.GetArg2()
                    arg_eval = mod_data.arg_eval_fn(arg) if mod_data.arg_eval_fn else arg
                    arg1_eval = mod_data.arg1_eval_fn(arg1) if mod_data.arg1_eval_fn else arg1
                    arg2_eval = mod_data.arg2_eval_fn(arg2) if mod_data.arg2_eval_fn else arg2

                    if mod_data.name.startswith("Inscription"):
                        PyImGui.text(f"{mod_data.name}")
                    PyImGui.text(f"{mod_data.representation(arg_eval, arg1_eval, arg2_eval)}")

            # Close window
            PyImGui.end()
    except Exception as e:
        # Log and handle the exception
        Py4GW.Console.Log(module_name, f"Error in ShowItemComparisonWindow: {str(e)}", Py4GW.Console.MessageType.Error)
        raise

def ShowItemdescription():
    try:
        global item1_id, item2_id, hovered_item
        global modifiers, window_module

        if window_module.first_run:
            PyImGui.set_next_window_size(window_module.window_size[0], window_module.window_size[1])     
            PyImGui.set_next_window_pos(window_module.window_pos[0], window_module.window_pos[1])
            window_module.first_run = False

        if PyImGui.begin(f"Item Description", window_module.window_flags):

            hovered_item = Inventory.GetHoveredItemID()
            PyImGui.text(f"Hovered Item: {hovered_item}")
            PyImGui.separator()

            bags_to_check = ItemArray.CreateBagList(1,2,3,4)
            item_array = ItemArray.GetItemArray(bags_to_check)

            item1_id = item_array[0] if item_array else None

            if not item1_id:
                PyImGui.text("No item selected for description.")
                PyImGui.end()
                return

            PyImGui.separator()

            
            item1_type_id, item1_type_name = Item.GetItemType(item1_id)
            PyImGui.text(f"Item 1 ID: {item1_id}")
            PyImGui.text(f"Type: {item1_type_id} - {item1_type_name}")


            modifiers1 = Item.Customization.Modifiers.GetModifiers(item1_id)
            if not modifiers1:
                PyImGui.text("No modifiers found.")
                PyImGui.end()
                return

            damage_type = find_modifier(9400)
            damage_range = find_modifier(42920)
            requires = find_modifier(10136)

            if not damage_type or not damage_range or not requires:
                PyImGui.text("Missing critical modifiers.")
                PyImGui.end()
                return


            result = Item.Customization.Modifiers.GetModifierValues(item1_id, 9400)

            if not result or result == (None, None, None):
                PyImGui.text("Damage type values could not be retrieved.")
                PyImGui.end()
                return
            arg, arg1, arg2 = result

            arg_eval = damage_type.arg_eval_fn(arg) if damage_type.arg_eval_fn else arg
            arg1_eval = damage_type.arg1_eval_fn(arg1) if damage_type.arg1_eval_fn else arg1
            arg2_eval = damage_type.arg2_eval_fn(arg2) if damage_type.arg2_eval_fn else arg2

            first_line = f"{damage_type.representation(arg_eval, arg1_eval, arg2_eval)}"
            
            result = Item.Customization.Modifiers.GetModifierValues(item1_id, 42920)

            if not result or result == (None, None, None):
                PyImGui.text("Damage Range values not be retrieved.")
                PyImGui.end()
                return
            arg, arg1, arg2 = result

            arg_eval = damage_range.arg_eval_fn(arg) if damage_range.arg_eval_fn else arg
            arg1_eval = damage_range.arg1_eval_fn(arg1) if damage_range.arg1_eval_fn else arg1
            arg2_eval = damage_range.arg2_eval_fn(arg2) if damage_range.arg2_eval_fn else arg2

            first_line += f"{damage_range.representation(arg_eval, arg1_eval, arg2_eval)}"
       
            result = Item.Customization.Modifiers.GetModifierValues(item1_id, 10136)

            if not result or result == (None, None, None):
                PyImGui.text("Requirement values could not be retrieved.")
                PyImGui.end()
                return
            arg, arg1, arg2 = result

            arg_eval = requires.arg_eval_fn(arg) if requires.arg_eval_fn else arg
            arg1_eval = requires.arg1_eval_fn(arg1) if requires.arg1_eval_fn else arg1
            arg2_eval = requires.arg2_eval_fn(arg2) if requires.arg2_eval_fn else arg2

            first_line += f" {requires.representation(arg_eval, arg1_eval, arg2_eval)}"

            PyImGui.text(f"{first_line}")

            for modifier in modifiers1:
                identifier = modifier.GetIdentifier()
                mod_data = find_modifier(identifier)
                if not mod_data:
                    continue

                if identifier == 9400 or identifier == 42920 or identifier == 10136:
                    continue

                #check if the name of the modifier doesnt start weith "Unknown"
                if not mod_data.name.startswith("Unknown"):
                    arg, arg1, arg2 = modifier.GetArg(), modifier.GetArg1(), modifier.GetArg2()
                    arg_eval = mod_data.arg_eval_fn(arg) if mod_data.arg_eval_fn else arg
                    arg1_eval = mod_data.arg1_eval_fn(arg1) if mod_data.arg1_eval_fn else arg1
                    arg2_eval = mod_data.arg2_eval_fn(arg2) if mod_data.arg2_eval_fn else arg2

                    if mod_data.name.startswith("Inscription"):
                        PyImGui.text(f"{mod_data.name}")
                    PyImGui.text(f"{mod_data.representation(arg_eval, arg1_eval, arg2_eval)}")

            # Close window
            PyImGui.end()
    except Exception as e:
        # Log and handle the exception
        Py4GW.Console.Log(module_name, f"Error in ShowItemComparisonWindow: {str(e)}", Py4GW.Console.MessageType.Error)
        raise

"""
identifier = 0
def ShowModifierDecoderWindow():
    try:
        global window_module, identifier

        if window_module.first_run:
            PyImGui.set_next_window_size(window_module.window_size[0], window_module.window_size[1])
            PyImGui.set_next_window_pos(0, 0)
            window_module.first_run = False

        if PyImGui.begin("Modifier Decoder", window_module.window_flags):
            PyImGui.text("Enter Modifier Identifier:")
            identifier = PyImGui.input_int("Identifier", identifier)

            if identifier is not None:
                modifier_info = decode_modifier(identifier)
                PyImGui.text(f"Decoded Modifier:")
                PyImGui.text(f"Name: {modifier_info.name}")
                PyImGui.text(f"Arg: {modifier_info.arg}")
                PyImGui.text(f"Arg1: {modifier_info.arg1}")
                PyImGui.text(f"Arg2: {modifier_info.arg2}")
            else:
                PyImGui.text("Invalid Identifier.")

            PyImGui.end()
    except Exception as e:
        Py4GW.Console.Log(module_name, f"Error in ShowModifierDecoderWindow: {str(e)}", Py4GW.Console.MessageType.Error)
        raise
    
    """
    
def ShowItemComparisonWindow():
    try:
        global item1_id, item2_id, hovered_item
        global item_show, input_item1, input_item2
        global modifiers, window_module

        if window_module.first_run:
            PyImGui.set_next_window_size(window_module.window_size[0], window_module.window_size[1])     
            PyImGui.set_next_window_pos(window_module.window_pos[0], window_module.window_pos[1])
            window_module.first_run = False

        if PyImGui.begin(f"Compare Items", window_module.window_flags):

            hovered_item = Inventory.GetHoveredItemID()
            PyImGui.text(f"Hovered Item: {hovered_item}")
            PyImGui.separator()

            bags_to_check = ItemArray.CreateBagList(1,2,3,4)
            item_array = ItemArray.GetItemArray(bags_to_check)

            input_item1 = item_array[0]
            input_item2 = item_array[1]
            # Input fields for item IDs
            #input_item1 = PyImGui.input_int("Item 1 ID", input_item1)
            #input_item2 = PyImGui.input_int("Item 2 ID", input_item2)


            #if PyImGui.button("Compare Items"):
            item1_id = input_item1
            item2_id = input_item2

            PyImGui.separator()

            headers = ["Property", "Item 1", "Item 2"]
            
            # Common Item Info
            item1_type_id, item1_type_name = Item.GetItemType(item1_id)
            item2_type_id, item2_type_name = Item.GetItemType(item2_id)
            
            data = [
                ("Item Type:", f"{item1_type_id} - {item1_type_name}", f"{item2_type_id} - {item2_type_name}"),
                ("Model Id:", Item.GetModelID(item1_id), Item.GetModelID(item2_id)),
                ("Slot:", Item.GetSlot(item1_id), Item.GetSlot(item2_id)),
                ("AgentId:", Item.GetAgentID(item1_id), Item.GetAgentID(item2_id)),
                ("AgentItemID:", Item.GetAgentItemID(item1_id), Item.GetAgentItemID(item2_id)),
            ]
            ImGui.table("Item comparison common info", headers, data)

            # Modifier comparison
            if PyImGui.collapsing_header("Modifiers"):
                # Retrieve modifiers for both items
                modifiers1 = Item.Customization.Modifiers.GetModifiers(item1_id)
                modifiers2 = Item.Customization.Modifiers.GetModifiers(item2_id)

                grouped_modifiers1 = group_modifiers_by_identifier(modifiers1)
                grouped_modifiers2 = group_modifiers_by_identifier(modifiers2)

                all_identifiers = sorted(set(grouped_modifiers1.keys()).union(grouped_modifiers2.keys()))

                for identifier in all_identifiers:
                    mods1 = grouped_modifiers1.get(identifier, [])
                    mods2 = grouped_modifiers2.get(identifier, [])

                    max_count = max(len(mods1), len(mods2))

                    for idx in range(max_count):
                        mod1 = mods1[idx] if idx < len(mods1) else None
                        mod2 = mods2[idx] if idx < len(mods2) else None

                        identifier1 = mod1.GetIdentifier() if mod1 else " "
                        identifier2 = mod2.GetIdentifier() if mod2 else " "

                        item1_arg = mod1.GetArg() if mod1 else " "
                        item2_arg = mod2.GetArg() if mod2 else " "

                        item1_arg1 = mod1.GetArg1() if mod1 else " "
                        item2_arg1 = mod2.GetArg1() if mod2 else " "

                        item1_arg2 = mod1.GetArg2() if mod1 else " "
                        item2_arg2 = mod2.GetArg2() if mod2 else " "

                        ident = identifier1 if mod1 else identifier2
                        mod_data = find_modifier(ident) if isinstance(ident, int) else None

                        header_1, header_2 = "Item 1", "Item 2"
                        arg_name, arg1_name, arg2_name = "", "", ""

                        representation_1, representation_2 = "", ""

                        if mod_data:
                            suffix = f" #{idx + 1}" if max_count > 1 else ""
                            header_1 = f"{mod_data.name}{suffix} (1)"
                            header_2 = f"{mod_data.name}{suffix} (2)"
                            arg_name = mod_data.arg
                            arg1_name = mod_data.arg1
                            arg2_name = mod_data.arg2

                            if mod1:
                                evaluated_arg = mod_data.arg_eval_fn(item1_arg) if mod_data.arg_eval_fn else item1_arg
                                evaluated_arg1 = mod_data.arg1_eval_fn(item1_arg1) if mod_data.arg1_eval_fn else item1_arg1
                                evaluated_arg2 = mod_data.arg2_eval_fn(item1_arg2) if mod_data.arg2_eval_fn else item1_arg2
                                representation_1 = mod_data.representation(evaluated_arg, evaluated_arg1, evaluated_arg2)
                            else:
                                evaluated_arg = evaluated_arg1 = evaluated_arg2 = " "

                            if mod2:
                                evaluated_arg_b = mod_data.arg_eval_fn(item2_arg) if mod_data.arg_eval_fn else item2_arg
                                evaluated_arg1_b = mod_data.arg1_eval_fn(item2_arg1) if mod_data.arg1_eval_fn else item2_arg1
                                evaluated_arg2_b = mod_data.arg2_eval_fn(item2_arg2) if mod_data.arg2_eval_fn else item2_arg2
                                representation_2 = mod_data.representation(evaluated_arg_b, evaluated_arg1_b, evaluated_arg2_b)
                            else:
                                evaluated_arg_b = evaluated_arg1_b = evaluated_arg2_b = " "
                        else:
                            suffix = f" #{idx + 1}" if max_count > 1 else ""
                            header_1 = f"Identifier {identifier}{suffix} (1)"
                            header_2 = f"Identifier {identifier}{suffix} (2)"
                            evaluated_arg = item1_arg
                            evaluated_arg1 = item1_arg1
                            evaluated_arg2 = item1_arg2
                            evaluated_arg_b = item2_arg
                            evaluated_arg1_b = item2_arg1
                            evaluated_arg2_b = item2_arg2

                        headers = ["Value", header_1, header_2]
                        data = [
                            ("Identifier:", identifier1, identifier2)
                        ]
                        data.append(("Item Type:", f"{item1_type_id} - {item1_type_name}", f"{item2_type_id} - {item2_type_name}"))

                        if mod_data:
                            data.append(("Representation:", representation_1 if representation_1 else " ", representation_2 if representation_2 else " "))

                        if mod_data and arg_name != "INVALID":
                            data.append((f"Arg: {arg_name}", evaluated_arg if evaluated_arg != "" else " ", evaluated_arg_b if evaluated_arg_b != "" else " "))
                        elif not mod_data:
                            data.append(("Arg:", evaluated_arg if evaluated_arg != "" else " ", evaluated_arg_b if evaluated_arg_b != "" else " "))

                        if mod_data and arg1_name != "INVALID":
                            data.append((f"Arg1: {arg1_name}", evaluated_arg1 if evaluated_arg1 != "" else " ", evaluated_arg1_b if evaluated_arg1_b != "" else " "))
                        elif not mod_data and (item1_arg1 != " " or item2_arg1 != " "):
                            data.append(("Arg1:", evaluated_arg1 if evaluated_arg1 != "" else " ", evaluated_arg1_b if evaluated_arg1_b != "" else " "))

                        if mod_data and arg2_name != "INVALID":
                            data.append((f"Arg2: {arg2_name}", evaluated_arg2 if evaluated_arg2 != "" else " ", evaluated_arg2_b if evaluated_arg2_b != "" else " "))
                        elif not mod_data and (item1_arg2 != " " or item2_arg2 != " "):
                            data.append(("Arg2:", evaluated_arg2 if evaluated_arg2 != "" else " ", evaluated_arg2_b if evaluated_arg2_b != "" else " "))

                        identical_values = (
                            identifier1 == identifier2 and
                            item1_arg == item2_arg and
                            item1_arg1 == item2_arg1 and
                            item1_arg2 == item2_arg2
                        )

                        if mod_data:
                            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, (0.0, 1.0, 1.0, 1.0))
                        elif identical_values:
                            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, (0.0, 1.0, 0.0, 1.0))
                        else:
                            PyImGui.push_style_color(PyImGui.ImGuiCol.Text, (1.0, 0.0, 0.0, 1.0))

                        table_identifier = f"Item Modifiers Comparison {identifier}-{idx}"
                        ImGui.table(table_identifier, headers, data)
                        PyImGui.pop_style_color(1)

            # Close window
            PyImGui.end()
    except Exception as e:
        # Log and handle the exception
        Py4GW.Console.Log(module_name, f"Error in ShowItemComparisonWindow: {str(e)}", Py4GW.Console.MessageType.Error)
        raise



# main function must exist in every script and is the entry point for your script's execution.
def main():
    global module_name
    try:
        ShowItemComparisonWindow()
        ShowItemdescription()
        ShowOffhandItemdescription()

    # Handle specific exceptions to provide detailed error messages
    except ImportError as e:
        Py4GW.Console.Log(module_name, f"ImportError encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(module_name, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    except ValueError as e:
        Py4GW.Console.Log(module_name, f"ValueError encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(module_name, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    except TypeError as e:
        Py4GW.Console.Log(module_name, f"TypeError encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(module_name, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    except Exception as e:
        # Catch-all for any other unexpected exceptions
        Py4GW.Console.Log(module_name, f"Unexpected error encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(module_name, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    finally:
        # Optional: Code that will run whether an exception occurred or not
        #Py4GW.Console.Log(module_name, "Execution of Main() completed", Py4GW.Console.MessageType.Info)
        # Place any cleanup tasks here
        pass

# This ensures that Main() is called when the script is executed directly.
if __name__ == "__main__":
    main()
