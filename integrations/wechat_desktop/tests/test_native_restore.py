import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import tkinter as tk
import types
import unittest
from core import Store,ReplyQueue,UserError
from engine import Engine
from settings_bridge import read_web_settings
from wechat_reader import WechatReader

class NativeRestoreTests(unittest.TestCase):
    def setUp(self):
        from app import App
        self.temp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.root.withdraw();self.app=App(self.root,self.temp.name)
        self.ids=[]
        for peer in ('alpha','beta'):
            binding={'account':'test-account','username':peer,'alias':peer,'remark':peer}
            person=Store.person_id('test-account',peer);self.ids.append(person)
            row={'id':'baseline','role':'other','kind':1,'type':'文本','time':1,'seq':1,'text':peer+'-history'}
            self.app.register_person(binding,[row],person)
    def tearDown(self):self.app.close();self.temp.cleanup()
    def test_each_current_state_and_assessment_preference_is_independent(self):
        a,b=self.ids;self.app.select_person(a);self.app.relation_state.set('A忙碌');self.app.assessment_enabled.set(False);self.app.save_profile(quiet=True)
        self.app.select_person(b);self.app.relation_state.set('B刚认识');self.app.assessment_enabled.set(True);self.app.save_profile(quiet=True)
        self.app.select_person(a)
        self.assertEqual(self.app.relation_state.get(),'A忙碌');self.assertFalse(self.app.assessment_enabled.get())
        self.assertEqual(self.app.store.get('objects',b)['current_state'],'B刚认识')
    def test_connect_uses_latest_visible_aliases_and_saves_them(self):
        requests=[];self.app.wait_for_switch=lambda:requests.append(self.app.pending_connection)
        self.app.alias.set('first, second');self.app.connect()
        self.assertEqual(requests[0][2],['first','second'])
        self.assertEqual(self.app.store.get('settings','connection')['aliases'],['first','second'])
    def test_saved_aliases_restore_without_auto_start(self):
        from app import App
        self.app.alias.set('first, second');self.app.save_connection(quiet=True);self.app.close()
        self.root=tk.Tk();self.root.withdraw();self.app=App(self.root,self.temp.name)
        self.assertEqual(self.app.alias.get(),'first, second');self.assertFalse(self.app.enabled.get());self.assertIsNone(self.app.monitor)
    def test_read_failure_keeps_window_open_with_specific_reason(self):
        self.app.handle_event(('error',UserError('联系人未核验测试原因')));self.app.handle_event(('disconnected',))
        self.assertEqual(self.root.winfo_exists(),1);self.assertIn('测试原因',self.app.connection_status.get());self.assertFalse(self.app.enabled.get())
    def test_legacy_saved_profiles_restore_aliases_without_starting(self):
        from app import App
        for person in self.ids:self.app.select_person(person);self.app.save_profile(quiet=True)
        self.app.close();self.root=tk.Tk();self.root.withdraw();self.app=App(self.root,self.temp.name)
        self.assertEqual(self.app.alias.get(),'alpha, beta');self.assertFalse(self.app.enabled.get())
    def test_new_message_updates_only_its_person_and_queues_that_person(self):
        a,b=self.ids;queued=[];self.app.follow_messages.set(False);self.app.queue_auto=lambda person:queued.append(person);self.app.select_person(a)
        row=dict(self.app.people[b]['messages'][0],id='incoming',text='B-new-message')
        self.app.handle_event(('messages',b,self.app.people[b]['messages']+[row],[row]))
        self.assertEqual(queued,[b]);self.assertEqual(self.app.people[b]['new_count'],1);self.assertEqual(self.app.people[a]['new_count'],0)
        self.assertEqual(self.app.person,a);self.app.select_person(b);self.assertIn('B-new-message',self.app.chat.get('1.0','end'))
    def test_manual_takeover_pauses_only_matching_person(self):
        a,b=self.ids;self.app.pending_people[a]=True;self.app.pending_people[b]=True
        row=dict(self.app.people[b]['messages'][0],id='mine',role='me')
        self.app.handle_event(('messages',b,[row],[row]))
        self.assertIn(b,self.app.reply_queue.manually_paused);self.assertNotIn(a,self.app.reply_queue.manually_paused)
        self.assertIn(a,self.app.pending_people);self.assertNotIn(b,self.app.pending_people)

class BridgeTests(unittest.TestCase):
    def parse(self,data):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json';path.write_text(json.dumps(data),encoding='utf-8');return read_web_settings(path)
    def test_web_config_import_excludes_send_and_auto_flags(self):
        result=self.parse({'wechat':{'aliases':['a','b']},'llm':{'api_key':'synthetic'},'behavior':{'auto_send':True,'enabled':True}})
        self.assertEqual(result['connection']['aliases'],['a','b']);self.assertEqual(set(result),{'connection','model','warning'})
        self.assertNotIn('auto_send',json.dumps(result))
    def test_overwritten_empty_web_list_does_not_replace_window_list(self):
        result=self.parse({'wechat':{'aliases':[]},'llm':{'api_key':'synthetic'}})
        self.assertIsNone(result['connection']);self.assertIsNotNone(result['model']);self.assertIn('为空',result['warning'])
    def test_custom_provider_key_not_copied_to_official_provider(self):
        result=self.parse({'llm':{'base_url':'https://custom.invalid','api_key':'synthetic'}})
        self.assertIsNone(result['model'])

class AssessmentTests(unittest.TestCase):
    def run_engine(self,assessment):
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]));engine=Engine(root/'skill');captured={}
        reply={'reply':'你好','reason':'承接','needs_human':False}
        if assessment is not None:reply['assessment']=assessment
        def request(path,key,data=None):
            captured.update(data);return {'choices':[{'message':{'content':json.dumps(reply)}}]}
        engine.request=request
        result=engine.generate([{'kind':1,'role':'other','text':'最近有点忙','time':1}],
            {'assess_relationship':True,'current_state':'工作忙，慢回','stage':'了解中'},'synthetic','model')
        return result,captured
    def test_assessment_and_reply_share_one_request_with_current_state(self):
        assessment=dict.fromkeys(('stage','signals','uncertainties','next_step','boundaries'),'依据不足，保持自然')
        result,captured=self.run_engine(assessment)
        self.assertEqual(result['assessment'],assessment)
        self.assertEqual(json.loads(captured['messages'][1]['content'])['profile']['current_state'],'工作忙，慢回')
    def test_missing_assessment_is_visible_error_not_silent_success(self):
        with self.assertRaisesRegex(UserError,'关系评估'):self.run_engine(None)

class ReaderPollingTests(unittest.TestCase):
    def test_database_update_detected_once_without_crossing_contacts(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'messages.sqlite'
            def table(peer):return 'Msg_'+hashlib.md5(peer.encode()).hexdigest()
            def open_db(rel):
                c=sqlite3.connect(path);c.row_factory=sqlite3.Row;return c
            c=open_db(None)
            for peer,sender in (('alpha',2),('beta',3)):
                c.execute('CREATE TABLE '+table(peer)+' (local_id INTEGER PRIMARY KEY,local_type INTEGER,server_id INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content TEXT,packed_info_data BLOB,sort_seq INTEGER)')
                c.execute('INSERT INTO '+table(peer)+' VALUES (1,1,0,?,1,?,NULL,1)',(sender,'old'))
            c.commit();c.close()
            obj=types.SimpleNamespace(_db_files=[('message/message_0.db',str(path),None)],_keys={'message/message_0.db':b'test'},_open=open_db,
                _name2id_map=lambda c:{1:'account',2:'alpha',3:'beta'},
                _export_row=lambda r,n:{'type_code':r['local_type'],'content':r['message_content'],'type':'文本'})
            reader=object.__new__(WechatReader);reader.obj=obj;reader.account={'account':'account'};reader.snapshots={}
            reader.module=types.SimpleNamespace(MSG_TYPE_NAMES={1:'文本'})
            a={'account':'account','username':'alpha'};b={'account':'account','username':'beta'}
            class Cipher:
                def seal(self,v):return json.dumps(v).encode()
                def open(self,v):return json.loads(v)
            store=Store(Path(folder)/'test.db',cipher=Cipher())
            try:
                q=ReplyQueue(store);q.start();q.observe('A',reader.read_peer(a,200),initial=True);q.observe('B',reader.read_peer(b,200),initial=True)
                c=open_db(None);c.execute('INSERT INTO '+table('beta')+' VALUES (2,1,0,3,2,?,NULL,2)',('new-B',));c.commit();c.close()
                self.assertEqual(q.observe('A',reader.read_peer(a,200)),[])
                fresh=q.observe('B',reader.read_peer(b,200));self.assertEqual([m['text'] for m in fresh],['new-B'])
                self.assertEqual(fresh[0]['role'],'other');self.assertEqual(q.observe('B',reader.read_peer(b,200)),[])
            finally:store.close()
