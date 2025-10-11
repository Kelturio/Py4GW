import PySkillbar
from Py4GWCoreLib.Py4GWcorelib import ActionQueueManager
from Py4GWCoreLib.skill_template import SkillAttribute
from Py4GWCoreLib.skill_template import SkillTemplate
from Py4GWCoreLib.skill_template import encode_skill_template
from Py4GWCoreLib.skill_template import make_skill_template

class SkillbarCache:
    def __init__(self, action_queue_manager, agent_cache, player_cache, skillbar_instance=None):
        self._skillbar_instance = skillbar_instance or PySkillbar.Skillbar()
        self._action_queue_manager:ActionQueueManager = action_queue_manager
        self._agent_cache = agent_cache
        self._player_cache = player_cache
        
    def _update_cache(self):
        self._skillbar_instance.GetContext()
        
    def LoadSkillTemplate(self, skill_template):
        self._action_queue_manager.AddAction("ACTION", self._skillbar_instance.LoadSkillTemplate, skill_template)
        
    def LoadHeroSkillTemplate (self, hero_index, skill_template):
        self._action_queue_manager.AddAction("ACTION", self._skillbar_instance.LoadHeroSkillTemplate, hero_index, skill_template)
        
    def GetSkillIDBySlot(self, slot):
        return self._skillbar_instance.GetSkill(slot).id.id
    
    def GetSkillbar(self):
        skill_ids = []
        for slot in range(1, 9):  # Loop through skill slots 1 to 8
            skill_id = self.GetSkillIDBySlot(slot)
            if skill_id != 0:
                skill_ids.append(skill_id)

        return skill_ids

    def GetSkillTemplate(self, *, primary=None, secondary=None, attributes=None, skills=None) -> SkillTemplate:
        agent_id = self._player_cache.GetAgentID()

        if skills is None:
            skills = [self._skillbar_instance.GetSkill(slot).id.id for slot in range(1, 9)]

        if primary is None or secondary is None:
            primary_id, secondary_id = self._agent_cache.GetProfessionIDs(agent_id)
            if primary is None:
                primary = primary_id
            if secondary is None:
                secondary = secondary_id

        if attributes is None:
            attributes = self._agent_cache.GetAttributes(agent_id)

        normalised_attributes: list[SkillAttribute] = []
        for attribute in attributes:
            if isinstance(attribute, SkillAttribute):
                normalised_attributes.append(attribute)
                continue

            attr_id = getattr(attribute, "attribute", None)
            points = getattr(attribute, "points", None)
            if attr_id is None or points is None:
                attr_id = getattr(attribute, "attribute_id", None)
                points = getattr(attribute, "level", None)
            if attr_id is None or points is None:
                continue
            normalised_attributes.append(SkillAttribute(int(attr_id), int(points)))

        return make_skill_template(
            primary=primary,
            secondary=secondary,
            skills=skills,
            attributes=normalised_attributes,
        )

    def EncodeSkillTemplate(self, **kwargs) -> str:
        template = self.GetSkillTemplate(**kwargs)
        return encode_skill_template(template)
    
    def GetHeroSkillbar(self, hero_index):
        hero_skillbar = self._skillbar_instance.GetHeroSkillbar(hero_index)
        return hero_skillbar
    
    def UseSkill(self, skill_slot, target_agent_id=0, aftercast_delay=0):
        self._action_queue_manager.AddActionWithDelay("ACTION",aftercast_delay, self._skillbar_instance.UseSkill, skill_slot, target_agent_id)
     
    def UseSkillTargetless(self, skill_slot, aftercast_delay=0):
        self._action_queue_manager.AddActionWithDelay("ACTION",aftercast_delay, self._skillbar_instance.UseSkillTargetless, skill_slot)
        
    def HeroUseSkill(self, target_agent_id, skill_number, hero_number):
        self._action_queue_manager.AddAction("ACTION", self._skillbar_instance.HeroUseSkill, target_agent_id, skill_number, hero_number)
      
    def ChangeHeroSecondary(self, hero_index, secondary_profession):
        self._action_queue_manager.AddAction("ACTION", self._skillbar_instance.ChangeHeroSecondary, hero_index, secondary_profession)  
        
    def GetSlotBySkillID(self, skill_id):
        for slot in range(1, 9):
            if self.GetSkillIDBySlot(slot) == skill_id:
                return slot    
        return 0
    
    def GetSkillData(self, slot):
        return self._skillbar_instance.GetSkill(slot)
        
    def GetHoveredSkillID(self):
        return self._skillbar_instance.GetHoveredSkill()
    
    def IsSkillUnlocked(self, skill_id):
        return self._skillbar_instance.IsSkillUnlocked(skill_id)
    
    def IsSkillLearnt(self, skill_id):
        return self._skillbar_instance.IsSkillLearnt(skill_id)
    
    def GetAgentID(self):
        return self._skillbar_instance.agent_id
    
    def GetDisabled(self):
        return self._skillbar_instance.disabled
    
    def GetCasting(self):
        return self._skillbar_instance.casting
    
    
    
    
    
    
    
    
    
    
    
    