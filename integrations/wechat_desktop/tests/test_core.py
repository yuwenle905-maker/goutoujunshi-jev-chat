import json
from pathlib import Path
import tempfile
import unittest
from core import Store, ReplyQueue, WindowsCipher, UserError, UnverifiedWechatSender
from engine import Engine


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'memory.db'
        self.store=Store(self.path)
        self.person=Store.person_id('account-a','peer-1')
        self.store.save('objects',self.person,{'memory':True})
        self.queue=ReplyQueue(self.store);self.queue.start()

    def tearDown(self):self.store.close();self.temp.cleanup()

    def message(self,id='1',role='other'):
        return {'id':id,'time':1,'role':role,'kind':1,'text':'private-canary-chat'}

    def ready(self):
        job=self.queue.begin(self.person)
        self.assertTrue(self.queue.finish(job,{'reply':'你好','reason':'承接','needs_human':False}))
        return job

    def test_dpapi_roundtrip(self):
        c=WindowsCipher();x={'key':'private-canary-key','text':'中文'}
        sealed=c.seal(x)
        self.assertNotIn(b'private-canary-key',sealed);self.assertEqual(c.open(sealed),x)

    def test_corrupted_cipher_preserves_file(self):
        c=WindowsCipher()
        with self.assertRaises(UserError):c.open(b'not-a-dpapi-blob')

    def test_message_payload_is_encrypted(self):
        self.store.remember(self.person,[self.message()])
        self.assertEqual(self.store.history(self.person)[0]['text'],'private-canary-chat')
        for p in Path(self.temp.name).iterdir():self.assertNotIn(b'private-canary-chat',p.read_bytes())

    def test_duplicate_message_saved_once(self):
        self.assertEqual(self.store.remember(self.person,[self.message(),self.message()]),1)
        self.assertEqual(self.store.remember(self.person,[self.message()]),0)
        self.assertEqual(self.store.count(self.person),1)

    def test_memory_off_stops_write_and_recall(self):
        self.store.remember(self.person,[self.message()])
        self.store.save('objects',self.person,{'memory':False})
        self.assertEqual(self.store.remember(self.person,[self.message('2')]),0)
        self.assertEqual(self.store.history(self.person),[])
        self.assertEqual(self.store.count(self.person),1)

    def test_cross_account_isolation(self):
        self.assertNotEqual(self.person,Store.person_id('account-b','peer-1'))
        self.store.remember(self.person,[self.message()])
        self.assertEqual(self.store.history(Store.person_id('account-b','peer-1')),[])

    def test_initial_history_not_treated_as_new(self):
        self.assertEqual(self.queue.observe(self.person,[self.message()],initial=True),[])
        self.assertEqual(self.queue.observe(self.person,[self.message()]),[])

    def test_new_message_cancels_inflight_result(self):
        job=self.queue.begin(self.person)
        self.queue.observe(self.person,[self.message('2')])
        self.assertFalse(self.queue.finish(job,{'reply':'stale'}))

    def test_duplicate_notification_does_not_cancel_ready_job(self):
        self.queue.observe(self.person,[self.message()],initial=True)
        job=self.ready()
        self.assertEqual(self.queue.observe(self.person,[self.message()]),[])
        self.assertTrue(self.queue.valid(job))

    def test_another_person_does_not_invalidate_job(self):
        job=self.ready()
        self.queue.observe('other-person',[self.message('another')])
        self.assertTrue(self.queue.valid(job))

    def test_manual_reply_pauses_automatic_generation(self):
        self.queue.observe(self.person,[self.message('3','me')])
        with self.assertRaises(UserError):self.queue.begin(self.person,trigger='incoming')

    def test_stop_cancels_pending_job(self):
        job=self.ready();self.queue.stop()
        self.assertFalse(self.queue.valid(job))
        with self.assertRaises(UserError):self.queue.send(job['id'],UnverifiedWechatSender(),'account-a','peer-1')

    def test_restart_does_not_revive_old_job(self):
        job=self.ready();self.queue.stop();self.queue.start()
        self.assertFalse(self.queue.valid(job))

    def test_unverified_sender_never_called(self):
        job=self.ready()
        with self.assertRaisesRegex(UserError,'身份验证尚未接通'):
            self.queue.send(job['id'],UnverifiedWechatSender(),'account-a','peer-1')

    def test_wrong_identity_blocks_before_send(self):
        class Bridge:
            verified_identity_transport=True
            def preflight(self,a,p):return {'account':a,'peer':'wrong-person'}
            def send(self,*args):raise AssertionError('must not send')
        job=self.ready()
        with self.assertRaisesRegex(UserError,'身份不匹配'):
            self.queue.send(job['id'],Bridge(),'account-a','peer-1')

    def test_missing_receipt_marked_unknown_no_retry(self):
        class Bridge:
            verified_identity_transport=True
            calls=0
            def preflight(self,a,p):return {'account':a,'peer':p}
            def send(self,*args):self.calls+=1;return {}
        b=Bridge();job=self.ready()
        with self.assertRaisesRegex(UserError,'回执不完整'):
            self.queue.send(job['id'],b,'account-a','peer-1')
        with self.assertRaises(UserError):self.queue.send(job['id'],b,'account-a','peer-1')
        self.assertEqual(b.calls,1)

    def test_success_receipt_not_sent_twice(self):
        class Bridge:
            verified_identity_transport=True
            calls=0
            def preflight(self,a,p):return {'account':a,'peer':p}
            def send(self,a,p,text,key,proof):
                self.calls+=1
                return {'account':a,'peer':p,'idempotency_key':key,'message_id':'receipt-1'}
        b=Bridge();job=self.ready()
        self.queue.send(job['id'],b,'account-a','peer-1')
        with self.assertRaises(UserError):self.queue.send(job['id'],b,'account-a','peer-1')
        self.assertEqual(b.calls,1)

    def test_needs_human_never_auto_sent(self):
        job=self.queue.begin(self.person)
        self.queue.finish(job,{'reply':'需要确认','reason':'边界','needs_human':True})
        with self.assertRaisesRegex(UserError,'人工处理'):
            self.queue.send(job['id'],UnverifiedWechatSender(),'account-a','peer-1')

    def test_clear_person_only(self):
        p2=Store.person_id('account-a','peer-2')
        self.store.save('objects',p2,{'memory':True})
        self.store.remember(self.person,[self.message()]);self.store.remember(p2,[self.message()])
        self.store.clear_person(self.person)
        self.assertEqual(self.store.count(self.person),0);self.assertEqual(self.store.count(p2),1)

    def test_archive_checkpoint_commits_with_messages(self):
        self.assertTrue(self.store.archive_batch(self.person,[self.message('shard:1')],{'shard':1}))
        self.assertEqual(self.store.count(self.person),1)
        self.assertEqual(self.store.get('settings','archive:'+self.person),{'shard':1})


class EngineTests(unittest.TestCase):
    def test_valid_structured_reply(self):
        self.assertEqual(Engine.parse('{"reply":"你好","reason":"承接","needs_human":false}')['reply'],'你好')

    def test_json_fence_supported(self):
        self.assertTrue(Engine.parse('```json\n{"reply":"你好","reason":"承接","needs_human":true}\n```')['needs_human'])

    def test_plain_text_never_becomes_reply(self):
        with self.assertRaises(UserError):Engine.parse('这里是整段分析，不应被发送')

    def test_missing_human_flag_rejected(self):
        with self.assertRaises(UserError):Engine.parse('{"reply":"你好","reason":"x"}')

    def test_string_boolean_rejected(self):
        with self.assertRaises(UserError):Engine.parse('{"reply":"你好","reason":"x","needs_human":"false"}')

    def test_rule_package(self):
        import sys
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        engine=Engine(root/'skill');rules,docs=engine.rules({'goal':'推进关系'})
        self.assertEqual(len(engine.references),43)
        self.assertIn(engine.main,rules)
        self.assertGreaterEqual(len(docs),2)
        self.assertLessEqual(len(docs),3)

    def test_no_sender_code_in_vendor(self):
        import sys
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        files={p.name for p in (root/'vendor').glob('*.py')}
        self.assertEqual(files,{'wechat_db.py'})

    def test_model_context_includes_history_excludes_cards_and_unknowns(self):
        import sys
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        engine=Engine(root/'skill');captured={}
        def fake_request(path,key,data=None):
            captured.update(data)
            return {'choices':[{'message':{'content':'{"reply":"你好","reason":"承接","needs_human":false}'}}]}
        engine.request=fake_request
        messages=[{'role':'other','kind':1,'time':1,'text':'earlier-fact'},
                  {'role':'me','kind':1,'time':2,'text':'my-promise'},
                  {'role':'unknown','kind':1,'time':3,'text':'ambiguous-not-evidence'},
                  {'role':'other','kind':49,'time':4,'text':'private-xml-not-speech'}]
        engine.generate(messages,{'summary':'confirmed-summary','_relevant_history':[
            {'role':'other','kind':1,'time':0,'text':'recalled-old-fact'}]},'test-key','chosen-model')
        payload=json.loads(captured['messages'][1]['content'])
        self.assertEqual([m['text'] for m in payload['messages']],['earlier-fact','my-promise'])
        self.assertEqual(payload['profile']['summary'],'confirmed-summary')
        self.assertEqual(payload['relevant_history'][0]['text'],'recalled-old-fact')
        self.assertEqual(captured['model'],'chosen-model')
        self.assertIn('不要主动让对方给用户致电、打语音电话或视频通话',captured['messages'][0]['content'])
        self.assertIn('不默认替用户答应',captured['messages'][0]['content'])
        self.assertNotIn('test-key',json.dumps(captured))


if __name__=='__main__':unittest.main()
