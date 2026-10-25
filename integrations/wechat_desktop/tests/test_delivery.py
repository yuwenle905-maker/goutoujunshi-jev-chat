import json
from pathlib import Path
import tempfile
import time
import threading
import unittest
from core import Store,ReplyQueue,UserError
from runtime import Behavior
from delivery import Delivery
from window_sender import WindowSender


class FakeWindows:
    def __init__(self):
        self.row=dict(hwnd=123,title='甲',pid=99,exe=r'C:\test\Weixin.exe',width=800,height=600)
        self.sent=[];self.fail=False
    def info(self,hwnd):return dict(self.row)
    def windows(self):return [dict(self.row)]
    def deliver(self,bound,text,guard):
        guard()
        if self.fail:raise UserError('injected failure')
        self.sent.append(text)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'memory.db')
        self.q=ReplyQueue(self.store);self.q.start();self.person='a'
        self.behavior=Behavior(self.store);self.behavior.save({'enabled':True,'auto_suggestions':True,'start':0,'end':0})
        self.backend=FakeWindows();self.sender=WindowSender(self.backend)
        self.binding=dict(account='own',username='peer-a',remark='甲',alias='alias-a')
        self.sender.bind('a',self.binding,self.backend.row,[100,500])
        self.d=Delivery(self.q,self.store,self.sender,self.behavior)
        self.q.observe('a',[],initial=True)
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def job(self,needs_human=False):
        job=self.q.begin('a');self.q.finish(job,dict(reply='原建议',reason='test',needs_human=needs_human))
        return job['id']
    def receipt(self,text='用户修改',peer='a',identifier='receipt1'):
        return self.d.observe(peer,[dict(id=identifier,kind=1,role='me',text=text,time=time.time())])
    def test_manual_review_sends_edited_body_only_after_submit(self):
        job=self.job();self.assertEqual(self.backend.sent,[])
        self.d.submit(job,self.binding,'用户修改')
        self.assertEqual(self.backend.sent,['用户修改']);self.assertEqual(self.q.jobs[job]['status'],'awaiting_receipt')
        self.assertEqual(self.store.get('settings','style:a',[]),[])
        self.assertEqual(self.receipt()[0][0],'sent');self.assertEqual(self.q.jobs[job]['status'],'sent')
        self.assertEqual(self.store.get('settings','style:a')[0]['approved'],'用户修改')
    def test_own_receipt_does_not_pause_or_repeat(self):
        job=self.job();self.d.submit(job,self.binding,'用户修改');self.receipt()
        self.assertEqual(self.q.observe('a',[dict(id='receipt1',role='me')]),[])
        self.assertNotIn('a',self.q.manually_paused)
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'用户修改')
        self.assertEqual(len(self.backend.sent),1)
    def test_auto_off_requires_review(self):
        job=self.job()
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'原建议',automatic=True)
        self.assertEqual(self.backend.sent,[])
    def test_auto_on_sends_but_does_not_learn(self):
        self.behavior.save({'auto_send':True});job=self.job();self.d.submit(job,self.binding,'原建议',True)
        self.receipt('原建议');self.assertEqual(self.store.get('settings','style:a',[]),[])
    def test_auto_needs_human_stays_reviewable(self):
        self.behavior.save({'auto_send':True});job=self.job(True)
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'原建议',True)
        self.d.submit(job,self.binding,'已审核修改');self.assertEqual(self.backend.sent,['已审核修改'])
    def test_mismatched_window_prevents_keyboard(self):
        for field,value in [('title','乙'),('pid',100),('exe',r'C:\evil.exe')]:
            old=self.backend.row[field];self.backend.row[field]=value
            with self.assertRaises(UserError):self.d.submit(self.job(),self.binding,'用户修改')
            self.backend.row[field]=old
        self.assertEqual(self.backend.sent,[])
    def test_resize_recomputes_bottom_anchor_but_dpi_change_rejects(self):
        self.backend.row.update(width=1000,height=800)
        bound=self.sender.check('a',self.binding)
        self.assertEqual(bound['point'],[125,700])
        bound['dpi']=96;self.backend.row['dpi']=144
        with self.assertRaisesRegex(UserError,'缩放比例'):self.sender.check('a',self.binding)
    def test_before_enter_failure_does_not_permanently_pause_auto(self):
        self.backend.tracks_submission=True;self.backend.fail=True;job=self.job()
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'用户修改')
        self.assertNotIn('a',self.q.manually_paused);self.assertEqual(self.q.jobs[job]['status'],'ready')
        self.assertEqual(self.store.get('settings','delivery:'+job)['state'],'not_sent')
        self.backend.fail=False;self.d.submit(job,self.binding,'用户修改');self.receipt()
        self.assertEqual(self.q.jobs[job]['status'],'sent')
    def test_three_automatic_rounds_survive_resize_and_own_receipts(self):
        self.behavior.save({'auto_send':True})
        for i in range(3):
            self.q.observe('a',[dict(id=f'incoming{i}',role='other',kind=1,text='合成来信',time=time.time())])
            job=self.q.begin('a',trigger='incoming')
            self.q.finish(job,dict(reply='原建议',reason='依据',needs_human=False))
            if i==1:self.backend.row.update(width=1000,height=800)
            self.d.submit(job['id'],self.binding,'原建议',True)
            self.receipt('原建议',identifier=f'outgoing{i}')
            self.assertEqual(self.q.jobs[job['id']]['status'],'sent');self.assertNotIn('a',self.q.manually_paused)
        self.assertEqual(len(self.backend.sent),3)
    def test_error_after_enter_still_pauses_and_never_retries(self):
        self.backend.tracks_submission=True
        def fail_after_enter(bound,text,guard):
            self.backend.trace('press_enter');raise UserError('合成按键后故障')
        self.backend.deliver=fail_after_enter;job=self.job()
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'用户修改')
        self.assertEqual(self.q.jobs[job]['status'],'unknown');self.assertIn('a',self.q.manually_paused)
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'用户修改')
    def test_main_window_is_not_bound(self):
        with self.assertRaises(UserError):self.sender.bind('b',self.binding,dict(self.backend.row,title='微信'),[100,500])
    def test_same_window_cannot_bind_different_contacts(self):
        with self.assertRaises(UserError):self.sender.bind('b',dict(self.binding,username='peer-b'),self.backend.row,[100,500])
    def test_different_internal_peer_is_rejected(self):
        with self.assertRaises(UserError):self.sender.check('a',dict(self.binding,username='other'))
    def test_unknown_result_pauses_no_learning_no_retry(self):
        self.backend.fail=True;job=self.job()
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'用户修改')
        self.assertEqual(self.q.jobs[job]['status'],'unknown');self.assertIn('a',self.q.manually_paused)
        self.assertEqual(self.store.get('settings','style:a',[]),[])
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'用户修改')
    def test_receipt_timeout(self):
        job=self.job();self.d.submit(job,self.binding,'用户修改');self.d.pending['a']['started']-=30
        self.assertEqual(self.d.expire()[0][0],'send_failed');self.assertEqual(self.q.jobs[job]['status'],'unknown')
    def test_other_contact_cannot_confirm_receipt_or_get_style(self):
        self.d.submit(self.job(),self.binding,'用户修改');self.assertEqual(self.receipt(peer='b'),[])
        self.assertIn('a',self.d.pending);self.assertEqual(self.store.get('settings','style:b',[]),[])
    def test_manual_takeover(self):
        self.d.submit(self.job(),self.binding,'用户修改');self.receipt('手动不同回复')
        self.assertIn('a',self.q.manually_paused);self.assertEqual(self.store.get('settings','style:a',[]),[])

    def test_manual_pause_allows_reviewed_send_but_still_blocks_auto(self):
        self.q.manually_paused.add('a');self.behavior.save({'auto_send':True});job=self.job()
        with self.assertRaisesRegex(UserError,'人工接管'):self.d.submit(job,self.binding,'原建议',True)
        self.d.submit(job,self.binding,'审核内容');self.receipt('审核内容')
        self.assertIn('a',self.q.manually_paused);self.assertEqual(self.backend.sent,['审核内容'])

    def test_unknown_result_blocks_even_new_manual_job_until_explicit_resume(self):
        self.backend.fail=True
        with self.assertRaises(UserError):self.d.submit(self.job(),self.binding,'用户修改')
        self.backend.fail=False;job=self.job()
        with self.assertRaisesRegex(UserError,'结果不明'):self.d.submit(job,self.binding,'已核对后的新回复')
        self.d.resume('a');self.d.submit(job,self.binding,'已核对后的新回复')
        self.assertEqual(len(self.backend.sent),1)

    def test_sender_does_not_block_queue_and_early_receipt_is_not_overwritten(self):
        acquired=[]
        def deliver(bound,text,guard):
            def check_queue():
                with self.q.lock:acquired.append(True)
            thread=threading.Thread(target=check_queue);thread.start();thread.join(1)
            self.assertFalse(thread.is_alive(),'Windows input held the reader/UI queue lock')
            guard();self.backend.sent.append(text);self.receipt(text)
        self.backend.deliver=deliver;job=self.job();self.d.submit(job,self.binding,'用户修改')
        self.assertEqual(acquired,[True]);self.assertEqual(self.q.jobs[job]['status'],'sent')

    def test_incoming_while_sender_runs_cancels_before_enter(self):
        self.backend.tracks_submission=True
        def deliver(bound,text,guard):
            self.q.observe('a',[dict(id='new-incoming',role='other',kind=1,text='更新',time=time.time())])
            guard();self.backend.sent.append(text)
        self.backend.deliver=deliver
        with self.assertRaisesRegex(UserError,'更新消息'):self.d.submit(self.job(),self.binding,'用户修改')
        self.assertEqual(self.backend.sent,[]);self.assertNotIn('a',self.q.manually_paused)
    def test_learning_can_be_disabled(self):
        self.store.save('settings','learn:a',False)
        self.d.submit(self.job(),self.binding,'用户修改');self.receipt()
        self.assertEqual(self.store.get('settings','style:a',[]),[])
    def test_learning_keeps_last_eight_and_diff(self):
        for i in range(10):
            self.d.submit(self.job(),self.binding,f'修改{i}');self.receipt(f'修改{i}',identifier=str(i))
        examples=self.store.get('settings','style:a')
        self.assertEqual(len(examples),8);self.assertEqual(examples[0]['approved'],'修改2');self.assertTrue(examples[-1]['changes'])
    def test_send_limit_includes_unknown_attempt(self):
        self.behavior.save({'daily_limit':1});self.backend.fail=True
        with self.assertRaises(UserError):self.d.submit(self.job(),self.binding,'用户修改')
        self.assertEqual(self.behavior.sends_used(),1);self.assertFalse(self.behavior.can_send()[0])
    def test_old_and_cancelled_job_not_sent(self):
        job=self.job();self.q.stop()
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'用户修改')
        self.assertEqual(self.backend.sent,[])
    def test_close_or_switch_can_cancel_during_input(self):
        cancelled=[False]
        original=self.backend.deliver
        def deliver(bound,text,guard):
            cancelled[0]=True
            original(bound,text,guard)
        self.backend.deliver=deliver
        with self.assertRaisesRegex(UserError,'取消'):
            self.d.submit(self.job(),self.binding,'用户修改',cancelled=lambda:cancelled[0])
        self.assertEqual(self.backend.sent,[])
    def test_summary_not_sent(self):
        job=self.job();self.q.jobs[job]['summary']=True
        with self.assertRaises(UserError):self.d.submit(job,self.binding,'摘要')
    def test_restart_defaults_to_review(self):
        self.behavior.save({'auto_send':True})
        restored=Behavior(self.store);self.assertFalse(restored.config['auto_send']);self.assertFalse(restored.config['enabled'])

    def test_style_examples_reach_model_as_comparison_data(self):
        from engine import Engine
        import sys
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        engine=Engine(root/'skill');captured={}
        def request(path,key,payload):
            captured.update(payload)
            return {'choices':[{'message':{'content':json.dumps(dict(reply='回复',reason='test',needs_human=False))}}]}
        engine.request=request
        example={'suggested':'您好呀','approved':'嗨','changes':[{'from':'您好呀','to':'嗨'}]}
        engine.generate([dict(kind=1,role='other',text='你好',time=1)],{'_style_examples':[example]},'synthetic','model')
        data=json.loads(captured['messages'][1]['content'])
        self.assertEqual(data['approved_edits'],[example]);self.assertIn('只学习表达风格',captured['messages'][0]['content'])
