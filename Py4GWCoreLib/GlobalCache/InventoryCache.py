import PyInventory
from typing import List, Tuple, Optional
from Py4GWCoreLib.Py4GWcorelib import ActionQueueManager
from Py4GWCoreLib import ConsoleLog
from Py4GWCoreLib.UIManager import UIManager
from Py4GWCoreLib import Bags
from Py4GWCoreLib import ModelID
from Py4GWCoreLib import Item
from .ItemCache import RawItemCache, Bag_enum, ItemCache

MATERIAL_STORAGE_SLOT_BY_MODEL_ID = {
    # Material storage uses fixed slots per material; the indices below follow the
    # in-game layout so we can target the correct pane position even when the stack
    # is currently empty.
    ModelID.Bone.value: 0,
    ModelID.Iron_Ingot.value: 1,
    ModelID.Tanned_Hide_Square.value: 2,
    ModelID.Scale.value: 3,
    ModelID.Chitin_Fragment.value: 4,
    ModelID.Bolt_Of_Cloth.value: 5,
    ModelID.Wood_Plank.value: 6,
    ModelID.Granite_Slab.value: 8,
    ModelID.Pile_Of_Glittering_Dust.value: 9,
    ModelID.Plant_Fiber.value: 10,
    ModelID.Feather.value: 11,
    ModelID.Fur_Square.value: 12,
    ModelID.Bolt_Of_Linen.value: 13,
    ModelID.Bolt_Of_Damask.value: 14,
    ModelID.Bolt_Of_Silk.value: 15,
    ModelID.Glob_Of_Ectoplasm.value: 16,
    ModelID.Steel_Ingot.value: 17,
    ModelID.Deldrimor_Steel_Ingot.value: 18,
    ModelID.Monstrous_Claw.value: 19,
    ModelID.Monstrous_Eye.value: 20,
    ModelID.Monstrous_Fang.value: 21,
    ModelID.Diamond.value: 22,
    ModelID.Sapphire.value: 23,
    ModelID.Ruby.value: 24,
    ModelID.Onyx_Gemstone.value: 25,
    ModelID.Lump_Of_Charcoal.value: 26,
    ModelID.Obsidian_Shard.value: 27,
    ModelID.Tempered_Glass_Vial.value: 28,
    ModelID.Leather_Square.value: 30,
    ModelID.Elonian_Leather_Square.value: 31,
    ModelID.Vial_Of_Ink.value: 32,
    ModelID.Roll_Of_Parchment.value: 33,
    ModelID.Roll_Of_Vellum.value: 34,
    ModelID.Spiritwood_Plank.value: 35,
    ModelID.Amber_Chunk.value: 36,
    ModelID.Jadeite_Shard.value: 37,
}

class InventoryCache:
    def __init__(self, action_queue_manager, raw_item_cache, item_cache):
        self._raw_item_cache:RawItemCache = raw_item_cache
        self.item_cache:ItemCache = item_cache
        self._inventory_instance = PyInventory.PyInventory()
        self._action_queue_manager:ActionQueueManager = action_queue_manager


    def GetInventorySpace(self):
        bags_to_check = [
            Bag_enum.Backpack.value,
            Bag_enum.Belt_Pouch.value,
            Bag_enum.Bag_1.value,
            Bag_enum.Bag_2.value
        ]
        bag_array = self._raw_item_cache.get_bags(bags_to_check)
        
        total_items = 0
        bag_size = 0
        for bag in bag_array:
            total_items += bag.GetItemCount()
            bag_size += bag.GetSize()
            
        return total_items, bag_size
    
    def GetStorageSpace(self, Anniversary_panel=True):
        start = Bag_enum.Storage_1.value
        end = Bag_enum.Storage_13.value

        bags_to_check = list(range(start, end + 1))  # Storage_1 to Storage_13

        if Anniversary_panel:
            bags_to_check.append(Bag_enum.Storage_14.value)  # Add Storage_14 if available

        bag_array = self._raw_item_cache.get_bags(bags_to_check)

        total_items = 0
        bag_size = 0
        for bag in bag_array:
            total_items += bag.GetItemCount()
            bag_size += bag.GetSize()

        return total_items, bag_size
    
    def GetZeroFilledStorageArray(self, Anniversary_panel=True, ExtraStoragePanes=0):
        """
        Returns a flat list of item_ids ordered by bag and slot.
        Empty slots are represented as 0.
        """
        result = []

        # Base: Storage_1 to Storage_13
        start = Bag_enum.Storage_1.value
        end = Bag_enum.Storage_13.value

        if Anniversary_panel:
            end = Bag_enum.Storage_14.value

        end += ExtraStoragePanes  # Add any extra panes

        bags_to_check = list(range(start, min(end + 1, Bag_enum.Max.value)))

        bag_array = self._raw_item_cache.get_bags(bags_to_check)

        for bag in bag_array:
            size = bag.GetSize()
            item_slots = [0] * size  # Fill with 0s

            for item in bag.GetItems():
                if 0 <= item.slot < size:
                    item_slots[item.slot] = item.item_id

            result.extend(item_slots)

        return result

    def GetFreeSlotCount(self):
        """
        Purpose: Calculate and return the number of free slots in inventory bags (1 to 4).
        Returns: int: The number of free slots available.
        """
        total_items, total_capacity = self.GetInventorySpace()
        return max(total_capacity - total_items, 0)

    def GetItemCount(self, item_id: int) -> int:
        """
        Purpose: Count the total quantity of items with the specified item_id 
        in bags Backpack, Belt Pouch, Bag 1, and Bag 2.
        Returns: int: Total quantity across all matching items.
        """
        bags_to_check = [
            Bag_enum.Backpack.value,
            Bag_enum.Belt_Pouch.value,
            Bag_enum.Bag_1.value,
            Bag_enum.Bag_2.value
        ]

        bags = self._raw_item_cache.get_bags(bags_to_check)
        total_quantity = 0

        for bag in bags:
            for item in bag.GetItems():
                if item.model_id == item_id:
                    total_quantity += item.quantity

        return total_quantity

    def GetModelCount(self, model_id: int) -> int:
        """
        Purpose: Count the number of items with the specified model_id 
        in inventory bags 1, 2, 3, and 4.
        Args:
            model_id (int): The model ID of the item to count.
        Returns:
            int: Total quantity of matching items.
        """
        
        if model_id <= 0:
            return 0
        
        bags_to_check = [
            Bag_enum.Backpack.value,
            Bag_enum.Belt_Pouch.value,
            Bag_enum.Bag_1.value,
            Bag_enum.Bag_2.value
        ]

        bags = self._raw_item_cache.get_bags(bags_to_check)
        total_quantity = 0

        for bag in bags:
            for item in bag.GetItems():
                if item.model_id == model_id:
                    total_quantity += item.quantity

        return total_quantity
    
    def GetModelCountInStorage(self, model_id: int, Anniversary_panel: bool = True) -> int:
        """
        Purpose: Count the number of items with the specified model_id 
        in storage bags.
        Args:
            model_id (int): The model ID of the item to count.
            Anniversary_panel (bool): Whether to include Storage14.
        Returns:
            int: Total quantity of matching items in storage.
        """
        
        if model_id <= 0:
            return 0
        
        bags_to_check = [
            Bag_enum.Storage_1.value,
            Bag_enum.Storage_2.value,
            Bag_enum.Storage_3.value,
            Bag_enum.Storage_4.value,
            Bag_enum.Storage_5.value if Anniversary_panel else None,
            Bag_enum.Storage_6.value,
            Bag_enum.Storage_7.value,
            Bag_enum.Storage_8.value,
            Bag_enum.Storage_9.value,
            Bag_enum.Storage_10.value,
            Bag_enum.Storage_11.value,
            Bag_enum.Storage_12.value,
            Bag_enum.Storage_13.value,
            Bag_enum.Storage_14.value,
        ]

        bags = self._raw_item_cache.get_bags([bag for bag in bags_to_check if bag is not None])
        total_quantity = 0

        for bag in bags:
            for item in bag.GetItems():
                if item.model_id == model_id:
                    total_quantity += item.quantity

        return total_quantity

    def GetModelCountInEquipped(self, model_id: int) -> int:
        """
        Count items with the given model_id in the Equipped Items bag (bag id 22).
        """
        EQUIPPED_BAG_ID = Bag_enum.Equipped_Items.value  # Equipped Items
        if model_id <= 0:
            return 0

        bags= self._raw_item_cache.get_bags([EQUIPPED_BAG_ID]) or []
        total = 0
        for bag in bags:
            for item in bag.GetItems():
                if item.model_id == model_id:
                    total += int(getattr(item, "quantity", 1) or 1)
        return total

    def GetFirstIDKit(self) -> int:
        """
        Purpose: Find the Identification Kit (ID Kit) with the lowest remaining uses
        in bags 1, 2, 3, and 4.
        Returns:
            int: The Item ID of the ID Kit with the lowest uses, or 0 if no ID Kit is found.
        """
        bags_to_check = [
            Bag_enum.Backpack.value,
            Bag_enum.Belt_Pouch.value,
            Bag_enum.Bag_1.value,
            Bag_enum.Bag_2.value
        ]

        bags = self._raw_item_cache.get_bags(bags_to_check)
        id_kits = []

        for bag in bags:
            for item in bag.GetItems():
                if self.item_cache.Usage.IsIDKit(item.item_id):
                    id_kits.append(item)

        if not id_kits:
            return 0

        id_kit_with_lowest_uses = min(id_kits, key=lambda item: self.item_cache.Usage.GetUses(item.item_id))
        return id_kit_with_lowest_uses.item_id
    

    def GetFirstUnidentifiedItem(self) -> int:
        """
        Purpose: Find the first unidentified item in bags 1, 2, 3, and 4.
        Returns:
            int: The Item ID of the first unidentified item found, or 0 if none found.
        """
        bags_to_check = [
            Bag_enum.Backpack.value,
            Bag_enum.Belt_Pouch.value,
            Bag_enum.Bag_1.value,
            Bag_enum.Bag_2.value
        ]

        bags = self._raw_item_cache.get_bags(bags_to_check)

        for bag in bags:
            for item in bag.GetItems():
                if not self.item_cache.Usage.IsIdentified(item.item_id):
                    return item.item_id

        return 0

    def GetFirstSalvageKit(self, use_lesser=True) -> int:
        """
        Purpose: Find the salvage kit with the lowest remaining uses 
        in bags 1, 2, 3, and 4. Optionally filters to only lesser kits.
        
        Args:
            use_lesser (bool): If True, only consider lesser salvage kits.

        Returns:
            int: The item_id of the salvage kit with the fewest uses, or 0 if none found.
        """
        bags_to_check = [
            Bag_enum.Backpack.value,
            Bag_enum.Belt_Pouch.value,
            Bag_enum.Bag_1.value,
            Bag_enum.Bag_2.value
        ]

        bags = self._raw_item_cache.get_bags(bags_to_check)
        kits = []

        for bag in bags:
            for item in bag.GetItems():
                if not self.item_cache.Usage.IsSalvageKit(item.item_id):
                    continue
                if use_lesser and not self.item_cache.Usage.IsLesserKit(item.item_id):
                    continue
                kits.append(item)

        if not kits:
            return 0

        best_kit = min(kits, key=lambda item: self.item_cache.Usage.GetUses(item.item_id))
        return best_kit.item_id

    def GetFirstSalvageableItem(self) -> int:
        """
        Purpose: Find the first salvageable item in bags 1, 2, 3, and 4.
        Returns:
            int: The Item ID of the first salvageable item found, or 0 if none found.
        """
        bags_to_check = [
            Bag_enum.Backpack.value,
            Bag_enum.Belt_Pouch.value,
            Bag_enum.Bag_1.value,
            Bag_enum.Bag_2.value
        ]

        bags = self._raw_item_cache.get_bags(bags_to_check)

        for bag in bags:
            for item in bag.GetItems():
                if self.item_cache.Usage.IsSalvageable(item.item_id):
                    return item.item_id

        return 0
    
    def GetFirstModelID(self, model_id: int) -> int:
        """
        Purpose: Find the first item with the specified model_id in bags 1, 2, 3, and 4.
        Args:
            model_id (int): The model ID to search for.
        Returns:
            int: The Item ID of the first item with the specified model_id, or 0 if none found.
        """
        bags_to_check = [
            Bag_enum.Backpack.value,
            Bag_enum.Belt_Pouch.value,
            Bag_enum.Bag_1.value,
            Bag_enum.Bag_2.value
        ]

        bags = self._raw_item_cache.get_bags(bags_to_check)

        for bag in bags:
            for item in bag.GetItems():
                if item.model_id == model_id:
                    return item.item_id

        return 0
    
    def GetfirstModelIDInStorage(self, model_id: int) -> int:
        """
        Purpose: Find the first item with the specified model_id in storage bags.
        Args:
            model_id (int): The model ID to search for.
        Returns:
            int: The Item ID of the first item with the specified model_id, or 0 if none found.
        """
        bags_to_check = [
            Bag_enum.Storage_1.value,
            Bag_enum.Storage_2.value,
            Bag_enum.Storage_3.value,
            Bag_enum.Storage_4.value,
            Bag_enum.Storage_5.value,
            Bag_enum.Storage_6.value,
            Bag_enum.Storage_7.value,
            Bag_enum.Storage_8.value,
            Bag_enum.Storage_9.value,
            Bag_enum.Storage_10.value,
            Bag_enum.Storage_11.value,
            Bag_enum.Storage_12.value,
            Bag_enum.Storage_13.value,
            Bag_enum.Storage_14.value
        ]

        bags = self._raw_item_cache.get_bags(bags_to_check)

        for bag in bags:
            for item in bag.GetItems():
                if item.model_id == model_id:
                    return item.item_id

        return 0

    def IdentifyItem (self, item_id, id_kit_id):
        """
        Purpose: Identify an item using an Identification Kit.
        """
        self._action_queue_manager.AddAction("IDENTIFY", self._inventory_instance.IdentifyItem,id_kit_id, item_id)

    def IdentifyFirst(self) -> bool:
        """
        Purpose: Identify the first unidentified item found in bags 1, 2, 3, and 4 using the first available ID kit.
        Returns:
            bool: True if an item was queued for identification, False otherwise.
        """
        id_kit_id = self.GetFirstIDKit()
        if id_kit_id == 0:
            ConsoleLog("IdentifyFirst", "No ID Kit found.")
            return False

        unid_item_id = self.GetFirstUnidentifiedItem()
        if unid_item_id == 0:
            ConsoleLog("IdentifyFirst", "No unidentified item found.")
            return False

        self._action_queue_manager.AddAction("IDENTIFY", self._inventory_instance.IdentifyItem, id_kit_id, unid_item_id)
        ConsoleLog("IdentifyFirst", f"Queued identification for item ID: {unid_item_id} using ID Kit ID: {id_kit_id}")
        return True

    def SalvageItem(self, item_id: int, salvage_kit_id: int):
        """
        Purpose: Identify an item using an Identification Kit.
        """
        self._action_queue_manager.AddAction("SALVAGE", self._inventory_instance.Salvage, salvage_kit_id, item_id)

    def SalvageFirst(self) -> bool:
        """
        Purpose: Queue the action to salvage the first salvageable item using the first available salvage kit.
        Returns:
            bool: True if a salvage action was queued, False if no valid kit or item was found.
        """
        salvage_kit_id = self.GetFirstSalvageKit()
        if salvage_kit_id == 0:
            ConsoleLog("SalvageFirst", "No salvage kit found.")
            return False

        salvage_item_id = self.GetFirstSalvageableItem()
        if salvage_item_id == 0:
            ConsoleLog("SalvageFirst", "No salvageable item found.")
            return False

        self._action_queue_manager.AddAction(
            "SALVAGE",
            self._inventory_instance.Salvage,
            salvage_kit_id,
            salvage_item_id
        )
        ConsoleLog("SalvageFirst", f"Queued salvage for item ID {salvage_item_id} with kit ID {salvage_kit_id}")
        return True

    def AcceptSalvageMaterialsWindow(self):

        parent_hash = 140452905
        yes_button_offsets = [6,98,6]
        
        salvage_material_window = UIManager.GetChildFrameID(parent_hash, yes_button_offsets)
        UIManager.FrameClick(salvage_material_window)

    def IsStorageOpen(self):

        return self._inventory_instance.GetIsStorageOpen()
    
    def OpenXunlaiWindow(self) -> bool:

        if self._inventory_instance.GetIsStorageOpen():
            return True  # Already open

        self._action_queue_manager.AddAction("ACTION",self._inventory_instance.OpenXunlaiWindow)
        return False  # Queued but not yet open

    def PickUpItem(self, item_id: int, call_target: bool = False) -> None:
        """
        Purpose: Queue an action to pick up an item from the ground.
        """
        self._action_queue_manager.AddAction("ACTION", self._inventory_instance.PickUpItem, item_id, call_target)

    def DropItem(self, item_id: int, quantity: int = 1) -> None:
        """
        Purpose: Queue an action to drop an item from the inventory.
        """
        self._action_queue_manager.AddAction("ACTION", self._inventory_instance.DropItem,item_id, quantity)
        
    def EquipItem(self, item_id: int, agent_id: int) -> None:
        """
        Purpose: Queue an action to equip an item from the inventory.
        """
        self._action_queue_manager.AddAction("ACTION",self._inventory_instance.EquipItem, item_id,agent_id)

    def UseItem(self, item_id: int) -> None:
        """
        Purpose: Queue an action to use an item from the inventory.
        """
        self._action_queue_manager.AddAction("ACTION",self._inventory_instance.UseItem,item_id)

    def DestroyItem(self, item_id: int):
        self._action_queue_manager.AddAction("ACTION",self._inventory_instance.DestroyItem,item_id)

    def GetHoveredItemID(self) -> int:
        return self._inventory_instance.GetHoveredItemID()

    def GetGoldOnCharacter(self) -> int:
        return self._inventory_instance.GetGoldAmount()

    def GetGoldInStorage(self) -> int:
        return self._inventory_instance.GetGoldAmountInStorage()

    def DepositGold(self, amount: int):
        self._action_queue_manager.AddAction( "ACTION",self._inventory_instance.DepositGold,amount )

    def WithdrawGold(self, amount: int):
        self._action_queue_manager.AddAction( "ACTION", self._inventory_instance.WithdrawGold,amount)

    def DropGold(self, amount: int):
        self._action_queue_manager.AddAction("ACTION",self._inventory_instance.DropGold,amount)

    def MoveItem(self, item_id: int, bag_id: int, slot: int, quantity: int = 1):
        self._action_queue_manager.AddAction( "ACTION",self._inventory_instance.MoveItem, item_id, bag_id,slot,quantity)

    def FindItemBagAndSlot(self, item_id: int) -> tuple[int | None, int | None]:
        """
        Locate the bag ID and slot of the given item ID in inventory bags (1, 2, 3, 4).
        """
        bags_to_check = [1, 2, 3, 4]
        bags = self._raw_item_cache.get_bags(bags_to_check)

        for bag in bags:
            for item in bag.GetItems():
                if item.item_id == item_id:
                    return bag.id, item.slot

        return None, None

    def DepositItemToStorage(self, item_id: int, Anniversary_panel: bool = True, ammount:int = -1) -> bool:
        """
        Purpose: Moves the specified item to storage, filling partial stacks first.
        Args:
            item_id (int): ID of the item to deposit.
            Anniversary_panel (bool): Whether the Anniversary Panel (Storage14) is enabled.
        Returns:
            bool: True if moved at least some of the items, False if failed.
        """
        def GetStorageBags():
            bag_list = [
                Bags.Storage1, Bags.Storage2, Bags.Storage3, Bags.Storage4,
                *( [Bags.Storage5] if Anniversary_panel else [] ),
                Bags.Storage6, Bags.Storage7, Bags.Storage8, Bags.Storage9, Bags.Storage10,
                Bags.Storage11, Bags.Storage12, Bags.Storage13, Bags.Storage14
            ]
            # Only include bags that exist (have size > 0)
            valid_bags = []
            for bag_enum in bag_list:
                try:
                    bag = PyInventory.Bag(bag_enum.value, bag_enum.name)
                    if bag.GetSize() > 0:
                        valid_bags.append((bag_enum, bag))
                except Exception:
                    continue
            return valid_bags
        
        DEFAULT_STACK_SIZE = 250
        quantity = self.item_cache.Properties.GetQuantity(item_id)
        is_stackable = self.item_cache.Customization.IsStackable(item_id)

        if quantity == 0:
            return False  # Nothing to move
        
        model_id = self.item_cache.GetModelID(item_id)
        is_dye = (model_id == ModelID.Vial_Of_Dye.value)
        dye1_to_match = None
        if is_dye:
            dye_info = Item.Customization.GetDyeInfo(item_id)
            dye1_to_match = dye_info.dye1.ToInt()

        storage_bags = GetStorageBags()
        material_bag_entry: Optional[Tuple[int, PyInventory.Bag]] = None
        is_material = self.item_cache.Type.IsMaterial(item_id) or self.item_cache.Type.IsRareMaterial(item_id)
        if is_material:
            try:
                material_bag = PyInventory.Bag(Bags.MaterialStorage.value, Bags.MaterialStorage.name)
                if material_bag.GetSize() > 0:
                    material_bag_entry = (Bags.MaterialStorage, material_bag)
            except Exception:
                material_bag_entry = None

        if material_bag_entry:
            storage_bags = [material_bag_entry, *storage_bags]

        material_stack_limit_cache: Optional[int] = None

        def determine_material_stack_limit() -> int:
            nonlocal material_stack_limit_cache
            if material_stack_limit_cache is not None:
                return material_stack_limit_cache

            material_stack_limit_cache = DEFAULT_STACK_SIZE
            if not material_bag_entry or not is_stackable:
                return material_stack_limit_cache

            bag = material_bag_entry[1]
            limit_candidates: List[int] = []
            potential_getters = (
                "GetMaterialStackSize",
                "GetMaxStackSize",
                "GetStackSize",
                "GetMaxQuantity",
                "GetCapacity",
            )

            for attr_name in potential_getters:
                getter = getattr(bag, attr_name, None)
                if not callable(getter):
                    continue
                try:
                    value = getter(model_id)
                except TypeError:
                    try:
                        value = getter()
                    except Exception:
                        continue
                except Exception:
                    continue
                if isinstance(value, int) and value > 0:
                    limit_candidates.append(value)

            highest_quantity = 0
            try:
                for material_item in bag.GetItems():
                    qty = self.item_cache.Properties.GetQuantity(material_item.item_id)
                    if qty > highest_quantity:
                        highest_quantity = qty
            except Exception:
                highest_quantity = 0

            if highest_quantity > 0:
                limit_candidates.append(highest_quantity)

            positive_limits = [value for value in limit_candidates if isinstance(value, int) and value > 0]
            if positive_limits:
                material_stack_limit_cache = max(positive_limits)
            else:
                material_stack_limit_cache = DEFAULT_STACK_SIZE

            if material_stack_limit_cache <= 0:
                material_stack_limit_cache = DEFAULT_STACK_SIZE

            return material_stack_limit_cache
        target_quantity = min(quantity, ammount) if ammount > 0 else quantity
        remaining_quantity = target_quantity
        moved_any = False
        model_id = self.item_cache.GetModelID(item_id)

        material_partial_slots: List[Tuple[int, int, int]] = []
        general_partial_slots: List[Tuple[int, int, int]] = []
        material_empty_slots: List[Tuple[int, int, int]] = []
        general_empty_slots: List[Tuple[int, int, int]] = []
        material_target_slot: Optional[int] = None

        for bag_enum, bag in storage_bags:
            items = bag.GetItems()

            bag_stack_limit = DEFAULT_STACK_SIZE
            if is_stackable and bag_enum == Bags.MaterialStorage:
                bag_stack_limit = determine_material_stack_limit()

            if is_stackable:
                for item in items:
                    if item.model_id != model_id:
                        continue

                    if is_dye:
                        item_dye_info = self.item_cache.Customization.GetDyeInfo(item.item_id)
                        if item_dye_info.dye1.ToInt() != dye1_to_match:
                            continue

                    current_qty = self.item_cache.Properties.GetQuantity(item.item_id)
                    if bag_enum == Bags.MaterialStorage and is_material:
                        material_target_slot = item.slot
                    if current_qty > bag_stack_limit:
                        bag_stack_limit = current_qty
                    if current_qty < bag_stack_limit:
                        space_left = bag_stack_limit - current_qty
                        target_partial_slots = material_partial_slots if (is_material and bag_enum == Bags.MaterialStorage) else general_partial_slots
                        target_partial_slots.append((bag_enum, item.slot, space_left))

            occupied_slots = {item.slot for item in items}
            if is_material and bag_enum == Bags.MaterialStorage:
                if material_target_slot is None:
                    material_target_slot = MATERIAL_STORAGE_SLOT_BY_MODEL_ID.get(model_id)
                if material_target_slot is not None and material_target_slot not in occupied_slots:
                    material_empty_slots.append((bag_enum, material_target_slot, bag_stack_limit))
            else:
                for slot in range(bag.GetSize()):
                    if slot in occupied_slots:
                        continue
                    general_empty_slots.append((bag_enum, slot, bag_stack_limit))

        def fill_partial_slots(slots: List[Tuple[int, int, int]]):
            nonlocal remaining_quantity, moved_any
            if not is_stackable:
                return
            for bag_enum, slot, space_left in slots:
                if remaining_quantity <= 0:
                    break
                to_move = min(space_left, remaining_quantity)
                if to_move <= 0:
                    continue
                self.MoveItem(item_id, bag_enum.value, slot, to_move)
                remaining_quantity -= to_move
                moved_any = True

        def fill_empty_slots(slots: List[Tuple[int, int, int]]):
            nonlocal remaining_quantity, moved_any
            for bag_enum, slot, bag_stack_limit in slots:
                if remaining_quantity <= 0:
                    break
                to_move = remaining_quantity if not is_stackable else min(remaining_quantity, bag_stack_limit)
                if to_move <= 0:
                    continue
                self.MoveItem(item_id, bag_enum.value, slot, to_move)
                remaining_quantity -= to_move
                moved_any = True

        if is_material:
            fill_partial_slots(material_partial_slots)
            fill_empty_slots(material_empty_slots)

        fill_partial_slots(general_partial_slots)
        fill_empty_slots(general_empty_slots)

        return moved_any
    
    def WithdrawItemFromStorage(self, item_id: int, ammount:int = -1) -> bool:
        """
        Moves the specified item from storage to player inventory, filling partial stacks first.
        Args:
            item_id (int): ID of the item to withdraw.
        Returns:
            bool: True if moved at least some of the items, False otherwise.
        """
        MAX_STACK_SIZE = 250
        quantity = self.item_cache.Properties.GetQuantity(item_id)
        is_stackable = self.item_cache.Customization.IsStackable(item_id)

        if quantity == 0:
            return False  # Nothing to move

        inventory_bags = [
            Bags.Backpack,
            Bags.BeltPouch,
            Bags.Bag1,
            Bags.Bag2
        ]

        remaining_quantity = min(quantity, ammount) if ammount > 0 else quantity
        moved_any = False
        model_id = self.item_cache.GetModelID(item_id)
        is_dye = (model_id == ModelID.Vial_Of_Dye.value)
        dye1_to_match = None
        if is_dye:
            dye_info = self.item_cache.Customization.GetDyeInfo(item_id)
            dye1_to_match = dye_info.dye1.ToInt()

        for bag_enum in inventory_bags:
            try:
                bag = PyInventory.Bag(bag_enum.value, bag_enum.name)
                size = bag.GetSize()
                items = bag.GetItems()
            except Exception:
                continue

            # Fill existing partial stacks
            if is_stackable:
                for item in items:
                    if item.model_id != model_id:
                        continue

                    if is_dye:
                        item_dye_info = self.item_cache.Customization.GetDyeInfo(item.item_id)
                        if item_dye_info.dye1.ToInt() != dye1_to_match:
                            continue

                    item_qty = self.item_cache.Properties.GetQuantity(item.item_id)
                    if item_qty < MAX_STACK_SIZE:
                        space_left = MAX_STACK_SIZE - item_qty
                        to_move = min(space_left, remaining_quantity)
                        to_move = min(to_move, ammount) if ammount > 0 else to_move
                        if to_move > 0:
                            self.MoveItem(item_id, bag_enum.value, item.slot, to_move)
                            remaining_quantity -= to_move
                            moved_any = True
                            if remaining_quantity == 0:
                                return True

            # Fill empty slots
            occupied_slots = {item.slot for item in items}
            for slot in range(size):
                if slot in occupied_slots:
                    continue
                to_move = remaining_quantity if not is_stackable else min(remaining_quantity, MAX_STACK_SIZE)
                self.MoveItem(item_id, bag_enum.value, slot, to_move)
                remaining_quantity -= to_move
                moved_any = True
                if remaining_quantity == 0:
                    return True

        return moved_any
    
    def WithdrawItemFromStorageByModelID(self, model_id: int, ammount:int = -1) -> bool:
        """
        Withdraws the first item with the specified model_id from storage to inventory.
        Args:
            model_id (int): The model ID of the item to withdraw.
        Returns:
            bool: True if an item was moved, False if no matching item was found.
        """
        item_id = self.GetfirstModelIDInStorage(model_id)
        if item_id == 0:
            return False
        
        return self.WithdrawItemFromStorage(item_id, ammount)
    
    
    def DepositItemToStorageByModelID(self, model_id: int, Anniversary_panel: bool = True, ammount:int = -1) -> bool:
        """ 
        Deposits the first item with the specified model_id from inventory to storage.
        Args:
            model_id (int): The model ID of the item to deposit.
            Anniversary_panel (bool): Whether the Anniversary Panel (Storage14) is enabled.
        Returns:
            bool: True if an item was moved, False if no matching item was found.
        """
        item_id = self.GetFirstModelID(model_id)
        if item_id == 0:
            return False
        
        return self.DepositItemToStorage(item_id, Anniversary_panel, ammount)

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
