import PySkillbar
from typing import Optional
from Py4GWCoreLib.Py4GWcorelib import ActionQueueManager

class SkillbarCache:
    def __init__(self, action_queue_manager):
        self._skillbar_instance = PySkillbar.Skillbar()
        self._action_queue_manager:ActionQueueManager = action_queue_manager
        
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

    def EncodeSkillTemplate(
        self,
        hero_index: Optional[int] = None,
        primary: Optional[int] = None,
        secondary: Optional[int] = None,
        attributes=None,
        skill_ids=None,
    ) -> str:
        """Encode the specified skillbar into a Guild Wars build string."""

        from Py4GWCoreLib.SkillTemplate import SkillTemplate, encode_skill_template

        try:
            from Py4GWCoreLib import GLOBAL_CACHE as global_cache
        except ImportError:  # pragma: no cover - defensive path
            global_cache = None

        resolved_skills = list(skill_ids) if skill_ids is not None else None
        agent_id = None

        if hero_index and hero_index > 0:
            hero_skills = self._skillbar_instance.GetHeroSkillbar(hero_index) or []
            if resolved_skills is None:
                resolved_skills = [skill.id.id for skill in hero_skills]
            if global_cache is not None:
                agent_id = global_cache.Party.Heroes.GetHeroAgentIDByPartyPosition(hero_index)
                if not agent_id and hero_index > 0:
                    agent_id = global_cache.Party.Heroes.GetHeroAgentIDByPartyPosition(hero_index - 1)
        else:
            if resolved_skills is None:
                resolved_skills = [
                    self._skillbar_instance.GetSkill(slot).id.id
                    for slot in range(1, 9)
                ]
            if global_cache is not None:
                agent_id = global_cache.Player.GetAgentID()

        resolved_attributes = list(attributes) if attributes is not None else None
        resolved_primary = primary
        resolved_secondary = secondary

        if global_cache is not None and agent_id:
            if resolved_primary is None or resolved_secondary is None:
                prof1, prof2 = global_cache.Agent.GetProfessionIDs(agent_id)
                if resolved_primary is None:
                    resolved_primary = prof1
                if resolved_secondary is None:
                    resolved_secondary = prof2
            if resolved_attributes is None:
                resolved_attributes = list(global_cache.Agent.GetAttributes(agent_id) or [])

        if resolved_skills is None:
            raise RuntimeError("Unable to resolve skill ids for template encoding")
        if resolved_primary is None or resolved_secondary is None:
            raise RuntimeError("Primary and secondary professions are required to encode a template")
        if resolved_attributes is None:
            resolved_attributes = []

        template = SkillTemplate(
            primary=resolved_primary,
            secondary=resolved_secondary,
            attributes=resolved_attributes,
            skills=resolved_skills,
        )
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
    
    
    
    
    
    
    
    
    
    
    
    