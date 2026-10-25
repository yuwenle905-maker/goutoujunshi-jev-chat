import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from core import Store,UserError
from engine import Engine
from relationship_review import review_history


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'memory.db')
        for p in ('a','b'):self.store.save('objects',p,{'memory':True})
        self.rows=[dict(id=str(i),role='me' if i%2 else 'other',kind=1,text='原话'+str(i),time=i+1,seq=i) for i in range(1000)]
        self.store.remember('a',self.rows);self.store.remember('b',[dict(self.rows[0],id='secret',text='other-contact-canary')])
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def test_history_uses_multiple_periods_and_recent_without_other_person(self):
        rows,scope=review_history(self.store,'a',self.rows[-200:])
        self.assertEqual(scope['saved_count'],1000);self.assertLess(scope['provided_count'],1000)
        self.assertIn('0',{m['id'] for m in rows});self.assertIn('999',{m['id'] for m in rows})
        self.assertNotIn('other-contact-canary',str(rows));self.assertLessEqual(sum(len(m['text']) for m in rows),24000)
        self.assertIn('不是全部',scope['sampling'])
    def test_cancel_and_memory_off_do_not_recall(self):
        with self.assertRaisesRegex(UserError,'取消'):review_history(self.store,'a',[],cancelled=lambda:True)
        self.store.save('objects','a',{'memory':False})
        with self.assertRaisesRegex(UserError,'开启长期记忆'):review_history(self.store,'a',self.rows)
    def test_prompt_contains_pain_boundaries_progress_quotes_and_phone_preference(self):
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]));engine=Engine(root/'skill');captured={}
        def request(path,key,payload):
            captured.update(payload)
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'reply':'关系分析','reason':'依据','needs_human':False})}}]}
        engine.request=request
        result=engine.generate(self.rows[-20:],{'_relationship_review':True,'_review_scope':{'provided_count':20}},'synthetic','model',summary=True)
        payload=json.loads(captured['messages'][1]['content'])
        for word in ('关系现状','痛点','推进建议','原话依据','不确定性'):self.assertIn(word,payload['task'])
        self.assertIn('不要主动让对方',captured['messages'][0]['content'])
        self.assertTrue(result['needs_human']);self.assertEqual(payload['history_scope']['provided_count'],20)
    def test_clear_person_removes_only_its_analysis(self):
        for p in ('a','b'):self.store.save('settings','relationship_review:'+p,{'text':p})
        self.store.clear_person('a');self.assertIsNone(self.store.get('settings','relationship_review:a'))
        self.assertEqual(self.store.get('settings','relationship_review:b'),{'text':'b'})


class ReviewGuiTests(unittest.TestCase):
    def setUp(self):
        from app import App
        self.tmp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.root.withdraw();self.app=App(self.root,self.tmp.name)
        self.app.reply_queue.start();self.app.enabled.set(True)
        self.person=Store.person_id('own','peer');self.rows=[dict(id='1',kind=1,role='other',text='原话',time=time.time(),seq=1)]
        self.app.store.save('objects',self.person,{'memory':True,'stage':'朋友','goal':'正常交流'})
        self.app.register_person(dict(account='own',username='peer',alias='peer'),self.rows,self.person)
        self.app.key.set('synthetic');self.app.model.set('synthetic')
    def tearDown(self):self.app.close();self.tmp.cleanup()
    def test_analysis_does_not_cancel_reply_or_send_and_saved_per_person(self):
        app=self.app;job=app.reply_queue.begin(self.person);app.reply_queue.finish(job,{'reply':'原建议','reason':'依据','needs_human':False})
        app.latest_jobs[self.person]=job['id'];app.current_job=job['id'];app.auto_send.set(True)
        class FakeEngine:
            def generate(self,*args,**kwargs):return {'reply':'现状、痛点、注意与推进','reason':'依据','needs_human':True}
        app.model_engine=lambda:FakeEngine();sent=[];app.submit_send=lambda *a,**k:sent.append(a)
        app.analyze_relationship();task=app.review_task;app.review_workers[task['id']].join(3)
        while not app.events.empty():app.handle_event(app.events.get_nowait())
        self.assertEqual(app.reply_queue.jobs[job['id']]['status'],'ready');self.assertEqual(sent,[])
        saved=app.store.get('settings','relationship_review:'+self.person)
        self.assertIn('推进',saved['text']);self.assertIn('非全量',saved['status'])
        self.assertIn('推进',app.review_text.get('1.0','end'))
    def test_cancel_rejects_late_result_and_preserves_previous(self):
        app=self.app;app.store.save('settings','relationship_review:'+self.person,{'text':'旧结果'})
        task={'person':self.person,'id':'old','started':time.monotonic(),'token':app.gate.value};app.review_task=task
        app.cancel_review();app.handle_event(('relationship_review_done',task,{'reply':'迟到'},{}))
        self.assertEqual(app.store.get('settings','relationship_review:'+self.person)['text'],'旧结果')
    def test_binding_and_pause_states_are_visible(self):
        self.app.reply_queue.manually_paused.add(self.person);self.app.refresh_inbox()
        self.assertIn('未绑定',self.app.transport_status.get());self.assertIn('人工确认仍可发送',self.app.transport_status.get())
