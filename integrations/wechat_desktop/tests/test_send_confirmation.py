import tkinter as tk
import unittest
from send_confirmation import SendConfirmation


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw();self.now=0;self.allowed=True
        self.sent=[];self.cancelled=[];self.closed=[]
        self.dialog=SendConfirmation(self.root,'对象甲','对方来信','拟发送回复',lambda:self.allowed,
            lambda body,explicit:self.sent.append((body,explicit)),self.cancelled.append,lambda:self.closed.append(True),
            clock=lambda:self.now,show=False)
    def tearDown(self):
        if not self.dialog.completed:self.dialog.cancel()
        self.root.destroy()
    def test_idle_five_seconds_confirms_exact_body_once(self):
        self.dialog.deadline=5;self.now=4.99;self.dialog.tick();self.assertEqual(self.sent,[])
        self.now=5;self.dialog.tick();self.dialog.accept(True)
        self.assertEqual(self.sent,[('拟发送回复',False)]);self.assertEqual(len(self.closed),1)
    def test_interaction_pauses_default_send(self):
        self.dialog.deadline=5;self.dialog.interact();self.now=50;self.dialog.tick()
        self.assertEqual(self.sent,[]);self.assertIsNone(self.dialog.deadline)
    def test_modify_stops_timer_and_confirm_uses_edited_reply(self):
        self.dialog.deadline=5;self.dialog.modify();self.dialog.text.delete('1.0','end');self.dialog.text.insert('1.0','用户修改')
        self.now=20;self.dialog.tick();self.assertEqual(self.sent,[])
        self.dialog.accept(True);self.assertEqual(self.sent,[('用户修改',True)])
    def test_new_message_or_disabled_session_cancels_instead_of_default_sending(self):
        self.dialog.deadline=5;self.allowed=False;self.now=5;self.dialog.tick()
        self.assertEqual(self.sent,[]);self.assertTrue(self.cancelled);self.assertTrue(self.dialog.completed)
    def test_close_is_cancel_not_default_confirmation(self):
        self.dialog.deadline=5;self.dialog.cancel();self.now=5;self.dialog.tick()
        self.assertEqual(self.sent,[]);self.assertEqual(len(self.cancelled),1)
    def test_needs_human_has_no_automatic_deadline(self):
        self.dialog.allow_timeout=False;self.now=60;self.dialog.tick()
        self.assertEqual(self.sent,[]);self.assertIn('需要人工复核',self.dialog.status.get())
