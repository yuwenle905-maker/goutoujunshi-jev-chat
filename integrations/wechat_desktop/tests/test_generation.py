import json
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from core import Store,UserError
from engine import Engine


class GenerationTests(unittest.TestCase):
    def setUp(self):
        from app import App
        self.tmp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.root.withdraw();self.app=App(self.root,self.tmp.name)
        self.app.reply_queue.start();self.app.enabled.set(True)
        self.person=Store.person_id('own','peer')
        self.app.register_person(dict(account='own',username='peer',alias='peer'),[],self.person)
    def tearDown(self):self.app.close();self.tmp.cleanup()
    def thinking(self):
        job=self.app.reply_queue.begin(self.person);self.app.latest_jobs[self.person]=job['id']
        self.app.active_generation=dict(id=job['id'],person=self.person,started=time.monotonic(),stage='等待模型')
        self.app.model_busy=True;self.app.current_job=job['id'];self.app.job_status.set('正在生成…')
        return job
    def test_failure_replaces_spinner_with_actionable_error(self):
        job=self.thinking();self.app.handle_event(('model_error',job,UserError('余额不足')))
        self.assertEqual(self.app.reply_queue.jobs[job['id']]['status'],'error')
        self.assertIn('余额不足',self.app.job_status.get());self.assertIn('余额不足',self.app.reason.get('1.0','end'))
        self.app.handle_event(('model_done',job['id']));self.assertFalse(self.app.model_busy)
    def test_timeout_releases_slot_and_late_result_cannot_send(self):
        job=self.thinking();self.app.active_generation['started']-=101;self.app.generation_progress()
        self.assertFalse(self.app.model_busy);self.assertIn('超时',self.app.job_status.get())
        self.assertFalse(self.app.reply_queue.finish(job,dict(reply='迟到回复',reason='x',needs_human=False)))
    def test_cancel_invalidates_result_and_allows_new_job(self):
        old=self.thinking();self.app.cancel_generation()
        self.assertFalse(self.app.model_busy);self.assertIn('取消',self.app.job_status.get())
        new=self.thinking();self.app.handle_event(('model_done',old['id']))
        self.assertTrue(self.app.model_busy);self.assertEqual(self.app.active_generation['id'],new['id'])
    def test_old_error_does_not_replace_new_request_status(self):
        old=self.thinking();self.app.cancel_generation();new=self.thinking()
        self.app.handle_event(('model_error',old,UserError('旧错误')))
        self.assertNotIn('旧错误',self.app.job_status.get());self.assertTrue(self.app.reply_queue.valid(new))
    def test_stage_and_elapsed_visible(self):
        job=self.thinking();self.app.handle_event(('model_stage',job['id'],'检索历史'))
        self.app.generation_progress();self.assertIn('检索历史',self.app.job_status.get());self.assertIn('秒',self.app.job_status.get())
    def test_switch_view_restores_failure_instead_of_spinner(self):
        job=self.thinking();self.app.handle_event(('model_error',job,UserError('网络异常')))
        self.app.select_person(self.person);self.assertIn('网络异常',self.app.job_status.get())
    def test_cancel_on_connection_invalidation(self):
        self.thinking();self.app.invalidate('切换');self.assertIsNone(self.app.active_generation);self.assertFalse(self.app.model_busy)
    def test_related_search_honors_budget_and_cancellation(self):
        self.app.store.save('objects',self.person,dict(memory=True))
        row=dict(id='one',time=1,kind=1,role='other',text='海边天气')
        self.app.store.remember(self.person,[row]);recent=[dict(row,id='new',text='海边怎么样')]
        self.assertEqual(self.app.store.related(self.person,recent,max_seconds=0),[])
        self.assertEqual(self.app.store.related(self.person,recent,cancelled=lambda:True),[])
        self.assertEqual(self.app.store.related(self.person,recent)[0]['id'],'one')
    def test_engine_refuses_cancelled_request_before_network(self):
        engine=self.app.model_engine();engine.cancelled=lambda:True
        with self.assertRaisesRegex(UserError,'取消'):engine.request('/chat/completions','synthetic',{})
    def test_engine_timeout_message_matches_operation(self):
        import urllib.request
        class TimeoutOpener:
            def open(self,*a,**k):raise TimeoutError()
        with patch.object(urllib.request,'build_opener',return_value=TimeoutOpener()):
            with self.assertRaisesRegex(UserError,'90秒'):self.app.model_engine().request('/chat/completions','synthetic',{})
            with self.assertRaisesRegex(UserError,'15秒'):self.app.model_engine().request('/models','synthetic')
    def test_worker_failure_completes_and_updates_reply_panel(self):
        engine=self.app.model_engine()
        def fail(*a,**k):raise UserError('测试网络不可达')
        engine.generate=fail;self.app.model_engine=lambda:engine
        self.app.key.set('synthetic');self.app.model.set('mock-model');self.app.generate()
        deadline=time.monotonic()+2
        while self.app.model_busy and time.monotonic()<deadline:
            self.app.tick();time.sleep(.01)
        self.assertFalse(self.app.model_busy);self.assertIn('测试网络不可达',self.app.job_status.get())
    def test_request_reads_json_in_bounded_chunks(self):
        import urllib.request
        class Response:
            def __init__(self):self.parts=[b'{"data":',b'[{"id":"mock"}]}',b'']
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read1(self,n):return self.parts.pop(0)
        class Opener:
            def open(self,*a,**k):return Response()
        with patch.object(urllib.request,'build_opener',return_value=Opener()):
            self.assertEqual(self.app.model_engine().models('synthetic'),['mock'])
