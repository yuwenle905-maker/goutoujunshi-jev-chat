import datetime as dt
from pathlib import Path
import queue
import tempfile
import time
import unittest
import tkinter as tk
from core import Store,UserError
from runtime import Behavior,SessionGate,split_targets,SHANGHAI


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'test.db')
        self.policy=Behavior(self.store)
        self.policy.save({'enabled':True,'auto_suggestions':True})
    def tearDown(self):self.store.close();self.temp.cleanup()
    def date(self,hour,day=24):return dt.datetime(2026,10,day,hour,tzinfo=SHANGHAI)
    def test_multiple_targets(self):self.assertEqual(split_targets('alpha，beta; alpha\ngamma'),['alpha','beta','gamma'])
    def test_too_many_targets_rejected(self):
        with self.assertRaises(UserError):split_targets(','.join(str(i) for i in range(21)))
    def test_old_connection_events_rejected(self):
        gate=SessionGate();a=gate.next();b=gate.next()
        self.assertFalse(gate.accepts(a));self.assertTrue(gate.accepts(b))
    def test_daytime_window(self):
        self.assertTrue(self.policy.can_auto(self.date(8))[0]);self.assertTrue(self.policy.can_auto(self.date(22))[0])
        self.assertFalse(self.policy.can_auto(self.date(23))[0]);self.assertFalse(self.policy.can_auto(self.date(7))[0])
    def test_overnight_window(self):
        self.policy.save({'start':22,'end':6})
        for hour in (22,23,0,5):self.assertTrue(self.policy.can_auto(self.date(hour))[0])
        for hour in (6,12,21):self.assertFalse(self.policy.can_auto(self.date(hour))[0])
    def test_all_day_window(self):
        self.policy.save({'start':8,'end':8})
        self.assertTrue(self.policy.can_auto(self.date(0))[0])
    def test_master_switch(self):
        self.policy.save({'enabled':False});self.assertFalse(self.policy.can_auto(self.date(12))[0])
    def test_daily_count_persists_and_resets(self):
        self.policy.save({'daily_limit':1});self.policy.record_success(self.date(12))
        self.assertFalse(self.policy.can_auto(self.date(13))[0]);self.assertTrue(self.policy.can_auto(self.date(12,25))[0])
        other=Behavior(self.store);self.assertEqual(other.used(self.date(12)),1)
    def test_zero_is_unlimited(self):
        self.policy.save({'daily_limit':0});self.policy.record_success(self.date(12))
        self.assertTrue(self.policy.can_auto(self.date(13))[0])
    def test_invalid_config_does_not_replace_previous(self):
        old=dict(self.policy.config)
        for setting in ({'start':'bad'},{'end':25},{'daily_limit':-1},{'end':-1}):
            with self.assertRaises(UserError):self.policy.save(setting)
            self.assertEqual(self.policy.config,old)
    def test_unconfigured_draft_not_persisted(self):
        self.store.draft({'id':'test','person':'unconfigured','status':'ready','text':'private-test'})
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0],0)


class GuiRegressionTests(unittest.TestCase):
    def setUp(self):
        from app import App
        self.temp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.root.withdraw()
        self.app=App(self.root,self.temp.name)
        self.a=self.add('alpha','A-only-text');self.b=self.add('beta','B-only-text')
    def add(self,peer,text):
        binding={'account':'test-account','username':peer,'alias':peer,'remark':peer,'nick_name':peer}
        person=Store.person_id('test-account',peer)
        row={'id':'shared-id','role':'other','kind':1,'type':'文本','time':1,'seq':1,'text':text}
        self.app.register_person(binding,[row],person)
        return person
    def tearDown(self):self.app.close();self.temp.cleanup()
    def test_review_mode_does_not_submit_generated_reply(self):
        self.app.reply_queue.start();self.app.enabled.set(True)
        self.app.behavior.save({'enabled':True,'auto_suggestions':True,'start':0,'end':0})
        job=self.app.reply_queue.begin(self.a)
        result=dict(reply='待审核',reason='依据',needs_human=False)
        self.app.reply_queue.finish(job,result);self.app.latest_jobs[self.a]=job['id']
        submitted=[];self.app.submit_send=lambda *a,**k:submitted.append((a,k))
        self.app.handle_event(('generated',job['id'],result,False,True))
        self.assertEqual(submitted,[]);self.assertIn('待审核',self.app.reply.get('1.0','end'))
    def test_auto_mode_submits_only_new_automatic_generation(self):
        self.app.reply_queue.start();self.app.enabled.set(True);self.app.auto_send.set(True)
        self.app.hour_start.set('0');self.app.hour_end.set('0');self.app.save_behavior(quiet=True)
        job=self.app.reply_queue.begin(self.a);result=dict(reply='自动候选',reason='依据',needs_human=False)
        self.app.reply_queue.finish(job,result);self.app.latest_jobs[self.a]=job['id']
        submitted=[];self.app.submit_send=lambda *a,**k:submitted.append((a,k))
        self.app.handle_event(('generated',job['id'],result,False,False));self.assertEqual(submitted,[])
        self.app.handle_event(('generated',job['id'],result,False,True));self.assertEqual(len(submitted),1)
        self.assertTrue(submitted[0][1]['automatic'])
    def test_review_confirmation_uses_current_edited_text(self):
        from unittest.mock import patch
        self.app.reply_queue.start();job=self.app.reply_queue.begin(self.a)
        self.app.reply_queue.finish(job,dict(reply='原文',reason='依据',needs_human=False))
        self.app.current_job=job['id'];self.app.put(self.app.reply,'自己修改的版本')
        submitted=[];self.app.submit_send=lambda *a,**k:submitted.append((a,k))
        self.app.window_sender.check=lambda *a:None
        with patch('tkinter.messagebox.askokcancel',side_effect=AssertionError('bound review must not ask twice')):self.app.approve_send()
        self.assertEqual(submitted[0][1]['text'],'自己修改的版本')
    def test_switch_view_refreshes_chat_and_header(self):
        self.app.select_person(self.a);self.assertIn('A-only-text',self.app.chat.get('1.0','end'))
        self.app.select_person(self.b);text=self.app.chat.get('1.0','end')
        self.assertIn('B-only-text',text);self.assertNotIn('A-only-text',text)
        self.assertIn('beta',self.app.chat_header.get())
    def test_input_change_clears_old_view_immediately(self):
        self.app.select_person(self.a);self.app.monitor=object()
        self.app.alias.set('replacement')
        self.assertIsNone(self.app.person);self.assertEqual(self.app.chat.get('1.0','end').strip(),'')
        self.app.monitor=None
    def test_delayed_event_cannot_restore_previous_person(self):
        old=self.app.gate.value
        self.app.invalidate('switch')
        binding={'account':'test-account','username':'old','alias':'old'}
        self.app.events.put(('session',old,('person',binding,[],Store.person_id('test-account','old'))))
        self.app.tick();self.assertEqual(self.app.people,{})
    def test_refresh_same_ids_updates_correct_snapshot(self):
        self.app.select_person(self.b)
        rows=[dict(self.app.messages[0],text='updated-B-only')]
        self.app.handle_event(('messages',self.b,rows,[]))
        self.assertIn('updated-B-only',self.app.chat.get('1.0','end'))
    def test_unconfigured_contacts_not_saved(self):self.assertEqual(self.app.store.objects(),[])
    def test_numeric_unknown_message_type_does_not_blank_history(self):
        rows=[dict(self.app.people[self.b]['messages'][0],kind=999,type=999)]
        self.app.handle_event(('messages',self.b,rows,[]));self.app.select_person(self.b)
        self.assertIn('999：未转写',self.app.chat.get('1.0','end'))
    def test_enabling_memory_merges_loaded_history_without_manual_import(self):
        self.app.select_person(self.b);self.app.memory.set(True);self.app.save_profile(quiet=True)
        self.assertEqual(self.app.store.count(self.b),1)
        self.app.save_profile(quiet=True);self.assertEqual(self.app.store.count(self.b),1)
        self.assertEqual(self.app.store.count(self.a),0)
    def test_remembered_contact_merges_history_on_reconnect(self):
        self.app.select_person(self.b);self.app.memory.set(True);self.app.save_profile(quiet=True)
        binding=self.app.people[self.b]['binding']
        row=dict(self.app.messages[0],id='new-history-id',text='new-history')
        self.app.register_person(binding,[row],self.b)
        self.assertEqual(self.app.store.count(self.b),2)
    def test_background_and_boundaries_are_isolated_per_relationship(self):
        self.app.select_person(self.a);self.app.put(self.app.notes,'A boundaries');self.app.save_profile(quiet=True)
        self.app.select_person(self.b);self.app.put(self.app.notes,'B boundaries');self.app.save_profile(quiet=True)
        self.app.select_person(self.a);self.assertEqual(self.app.notes.get('1.0','end-1c'),'A boundaries')
        self.assertEqual(self.app.store.get('objects',self.b)['notes'],'B boundaries')
    def test_each_relationship_keeps_its_own_stage_and_goal(self):
        self.app.select_person(self.a)
        self.app.stage.set('暧昧');self.app.goal.set('暧昧升温');self.app.save_profile(quiet=True)
        self.app.select_person(self.b)
        self.app.stage.set('了解中');self.app.goal.set('自然接话');self.app.save_profile(quiet=True)
        self.app.select_person(self.a)
        self.assertEqual((self.app.stage.get(),self.app.goal.get()),('暧昧','暧昧升温'))
        self.assertEqual(self.app.store.get('objects',self.b)['goal'],'自然接话')
        self.assertEqual(self.app.store.get('objects',self.a)['stage'],'暧昧')
    def test_automatic_generation_uses_requested_person_only(self):
        captured={}
        class FakeEngine:
            def generate(self,messages,profile,key,model,summary=False):
                captured['texts']=[m['text'] for m in messages]
                captured['profile']=profile
                return {'reply':'draft-B','reason':'test','needs_human':False,'references':[]}
        self.app.model_engine=lambda:FakeEngine()
        self.app.enabled.set(True);self.app.reply_queue.start()
        self.app.behavior.can_auto=lambda *args:(True,'')
        self.app.key.set('test-key-not-real');self.app.model.set('test-model')
        self.app.select_person(self.a)
        self.app.people[self.a]['profile'].update(stage='暧昧',goal='暧昧升温')
        self.app.people[self.b]['profile'].update(stage='了解中',goal='自然接话')
        self.app.generate(automatic=True,person=self.b)
        for _ in range(100):
            if captured:break
            time.sleep(.01)
        self.assertEqual(captured['texts'],['B-only-text'])
        self.assertEqual(captured['profile']['goal'],'自然接话')
        self.assertEqual(self.app.person,self.a)
    def test_model_list_failure_is_visible_and_button_reenabled(self):
        self.app.model_request=2;self.app.models_busy=True;self.app.key.set('test-key')
        self.app.handle_event(('models_result',2,'test-key',None,UserError('HTTP 401 test')))
        self.assertFalse(self.app.models_busy)
        self.assertIn('401',self.app.model_fetch_status.get())
    def test_model_list_success_is_saved(self):
        self.app.model_request=1;self.app.key.set('test-key')
        self.app.handle_event(('models_result',1,'test-key',['deepseek-flash','deepseek-v4-pro'],None))
        self.assertEqual(self.app.model.get(),'deepseek-v4-pro')
        self.assertEqual(len(self.app.store.get('settings','model')['models']),2)


if __name__=='__main__':unittest.main()
