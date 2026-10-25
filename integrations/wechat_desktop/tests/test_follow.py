from pathlib import Path
import tempfile
import tkinter as tk
import unittest
import time
from unittest.mock import patch
from core import Store


class FollowTests(unittest.TestCase):
    def setUp(self):
        from app import App
        self.tmp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.root.withdraw()
        self.app=App(self.root,self.tmp.name);self.app.reply_queue.start();self.app.enabled.set(True)
        self.peers=[]
        for peer in ('alpha','beta','gamma'):
            binding=dict(account='own',username=peer,alias=peer,remark=peer)
            person=Store.person_id('own',peer);self.peers.append(person)
            self.app.register_person(binding,[],person)
        self.app.queue_auto=lambda p:None
    def tearDown(self):self.app.close();self.tmp.cleanup()
    def incoming(self,person):
        row=dict(id=person+'-1',role='other',kind=1,type='文本',text='新来信'+person,time=1,seq=1)
        self.app.handle_event(('messages',person,[row],[row]))
    def ready(self,person,text='建议'):
        job=self.app.reply_queue.begin(person)
        self.app.reply_queue.finish(job,dict(reply=text,reason='依据',needs_human=False))
        self.app.latest_jobs[person]=job['id'];return job
    def test_incoming_switches_to_matching_peer_without_combobox_click(self):
        self.incoming(self.peers[1]);self.assertEqual(self.app.person,self.peers[1])
        self.assertIn('beta',self.app.conversation.get());self.assertIn('新来信',self.app.chat.get('1.0','end'))
        self.incoming(self.peers[2]);self.assertEqual(self.app.person,self.peers[2])
        self.assertEqual(self.app.people[self.peers[1]]['new_count'],1)
    def test_snapshot_history_alone_does_not_change_view(self):
        a,b,_=self.peers
        self.app.handle_event(('messages',b,[],[]));self.assertEqual(self.app.person,a)
    def test_follow_toggle_keeps_background_updates_and_pending_button(self):
        a,b,_=self.peers;self.app.follow_messages.set(False);self.incoming(b)
        self.assertEqual(self.app.person,a);self.assertTrue(self.app.people[b]['messages']);self.assertIn(b,self.app.pending_views)
        self.app.view_latest_incoming();self.assertEqual(self.app.person,b)
    def test_switch_preserves_edited_reply_and_unsaved_relationship_form(self):
        a,b,_=self.peers;job=self.ready(a);self.app.render_draft()
        self.app.put(self.app.reply,'我修改的回复');self.app.put(self.app.notes,'未保存背景');self.app.goal.set('主动邀约')
        self.incoming(b);self.assertEqual(self.app.person,b)
        self.app.select_person(a)
        self.assertEqual(self.app.reply.get('1.0','end-1c'),'我修改的回复')
        self.assertEqual(self.app.notes.get('1.0','end-1c'),'未保存背景');self.assertEqual(self.app.goal.get(),'主动邀约')
    def test_typing_is_not_interrupted_and_other_peer_still_reads(self):
        a,b,_=self.peers
        self.app.last_edit_activity=time.monotonic()
        with patch.object(self.root,'focus_get',return_value=self.app.reply):self.incoming(b)
        self.assertEqual(self.app.person,a);self.assertEqual(self.app.people[b]['new_count'],1)
    def test_unique_title_selected_without_claiming_identity_binding(self):
        windows=[dict(hwnd=123,title='alpha',pid=1,exe=r'C:\Weixin.exe',width=800,height=600)]
        self.app.window_sender.candidates=lambda:windows
        self.app.refresh_send_windows(quiet=True)
        self.assertEqual(self.app.window_box.current(),0);self.assertNotIn(self.peers[0],self.app.window_sender.bindings)
    def test_duplicate_titles_not_auto_selected(self):
        self.app.window_sender.candidates=lambda:[dict(hwnd=i,title='alpha') for i in (1,2)]
        self.app.refresh_send_windows(quiet=True);self.assertEqual(self.app.window_box.current(),-1)
    def test_explicit_selection_survives_setup_refresh(self):
        self.app.window_sender.candidates=lambda:[dict(hwnd=i,title='alpha') for i in (1,2)]
        self.app.refresh_send_windows(quiet=True);self.app.window_box.current(1)
        bound=[];self.app.bind_send_window=lambda **kw:bound.append(self.app.window_box.current())
        self.app.setup_send_window();self.assertEqual(bound,[1])
    def test_unbound_approve_enters_setup_instead_of_submit_or_error(self):
        self.ready(self.peers[0]);self.app.render_draft();setup=[];sent=[]
        self.app.setup_send_window=lambda **kwargs:setup.append(kwargs)
        self.app.submit_send=lambda *a,**k:sent.append(a)
        self.app.approve_send();self.assertEqual(len(setup),1);self.assertEqual(sent,[])
        self.assertTrue(callable(setup[0]['after_bind']))
    def test_matching_window_changes_when_selected_person_changes(self):
        self.app.window_sender.candidates=lambda:[dict(hwnd=i,title=p) for i,p in enumerate(('alpha','beta'),1)]
        self.app.select_person(self.peers[1]);self.assertIn('beta',self.app.send_window.get())
        self.app.select_person(self.peers[0]);self.assertIn('alpha',self.app.send_window.get())


    def test_stale_textbox_focus_does_not_block_follow_forever(self):
        a,b,_=self.peers
        self.app.last_edit_activity=time.monotonic()-10
        with patch.object(self.root,'focus_get',return_value=self.app.reply):self.incoming(b)
        self.assertEqual(self.app.person,b)

    def test_deferred_follow_resumes_without_latest_button_after_idle(self):
        a,b,_=self.peers;self.ready(a);self.app.render_draft();self.app.put(self.app.reply,'未发送修改稿')
        self.app.last_edit_activity=time.monotonic()
        with patch.object(self.root,'focus_get',return_value=self.app.reply):
            self.incoming(b);self.assertEqual(self.app.person,a)
            self.app.last_edit_activity-=3;self.app.pump_follow()
        self.assertEqual(self.app.person,b)
        self.app.select_person(a);self.assertEqual(self.app.reply.get('1.0','end-1c'),'未发送修改稿')

    def test_manual_view_is_not_undone_by_old_pending_messages(self):
        a,b,c=self.peers;self.app.follow_messages.set(False);self.incoming(b);self.incoming(c)
        self.app.select_person(b);self.app.follow_messages.set(True);self.app.pump_follow()
        self.assertEqual(self.app.person,b)

    def test_review_binding_callback_does_not_send_a_new_unreviewed_job(self):
        a,_,_=self.peers;old=self.ready(a);self.app.render_draft();callbacks=[];sent=[]
        self.app.setup_send_window=lambda **kw:callbacks.append(kw['after_bind'])
        self.app.submit_send=lambda *args,**kw:sent.append(args)
        self.app.approve_send();self.ready(a,'新回复');callbacks[0]()
        self.assertEqual(sent,[])
