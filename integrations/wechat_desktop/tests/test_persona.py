import json
from pathlib import Path
import sys
import unittest
import test_runtime
from persona import normalize,resolve,DEFAULT_PERSONA
from core import UserError
from engine import Engine


class PersonaTests(unittest.TestCase):
    def test_global_and_contact_override_are_independent(self):
        global_value=dict(DEFAULT_PERSONA)
        self.assertEqual(resolve(global_value,{}),global_value)
        person={'persona_override':True,'persona_description':'稳重','persona_expression':'短句','persona_avoid':'不用昵称'}
        self.assertEqual(resolve(global_value,person)['description'],'稳重')
        self.assertEqual(global_value,DEFAULT_PERSONA)
        self.assertEqual(resolve(dict(global_value,enabled=False),person),{})
    def test_invalid_values_rejected_without_truncation(self):
        for value in (None,{'description':42},{'expression':'x'*1501}):
            with self.assertRaises(UserError):normalize(value)
    def test_empty_override_is_explicit_and_does_not_inherit(self):
        self.assertEqual(resolve(DEFAULT_PERSONA,{'persona_override':True})['description'],'')
    def test_model_request_contains_preferences_and_safety_priority(self):
        engine=Engine(Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'skill')
        requests=[]
        def request(path,key,data):
            requests.append(data)
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'reply':'自然回复','reason':'依据','needs_human':False})}}]}
        engine.request=request
        messages=[{'kind':1,'role':'other','text':'最近好吗','time':1}]
        engine.generate(messages,{'_persona':dict(DEFAULT_PERSONA)},'synthetic','mock')
        payload=json.loads(requests[-1]['messages'][1]['content'])
        self.assertEqual(payload['expression_persona']['description'],DEFAULT_PERSONA['description'])
        self.assertIn('真实事实、对方意愿和明确边界',requests[-1]['messages'][0]['content'])
        engine.generate(messages,{'_persona':dict(DEFAULT_PERSONA)},'synthetic','mock',summary=True)
        self.assertNotIn('expression_persona',json.loads(requests[-1]['messages'][1]['content']))


class PersonaGuiTests(unittest.TestCase):
    setUp=test_runtime.GuiRegressionTests.setUp
    tearDown=test_runtime.GuiRegressionTests.tearDown
    add=test_runtime.GuiRegressionTests.add
    def test_each_contact_keeps_unsaved_and_saved_persona(self):
        self.app.select_person(self.a);self.app.persona_override.set(True)
        self.app.object_persona_description.set('甲独立人设')
        self.app.select_person(self.b)
        self.assertFalse(self.app.persona_override.get());self.assertEqual(self.app.object_persona_description.get(),'')
        self.app.select_person(self.a);self.assertEqual(self.app.object_persona_description.get(),'甲独立人设')
        self.app.save_profile(quiet=True)
        self.assertEqual(self.app.store.get('objects',self.a)['persona_description'],'甲独立人设')
        self.assertNotEqual(self.app.people[self.b]['profile'].get('persona_description'),'甲独立人设')
    def test_global_persona_only_changes_after_save(self):
        old=dict(self.app.persona_settings);self.app.persona_description.set('新语气')
        self.assertEqual(self.app.persona_settings,old)
        self.app.save_persona()
        self.assertEqual(self.app.store.get('settings','persona')['description'],'新语气')
        self.assertNotIn('persona_description',self.app.people[self.a]['profile'])
    def test_sidebar_reaches_all_original_pages_and_nested_memory_tabs_remain(self):
        self.assertEqual(set(self.app.navigation_buttons),set(self.app.tabs))
        for name,button in self.app.navigation_buttons.items():
            button.invoke();self.root.update_idletasks()
            self.assertEqual(self.app.book.select(),str(self.app.tabs[name]))
        self.assertEqual(len(self.app.tabs),6)
        self.assertEqual(str(self.app.approve_button.cget('style')),'Primary.TButton')
