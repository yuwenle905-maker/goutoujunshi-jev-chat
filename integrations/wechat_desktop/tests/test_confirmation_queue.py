import unittest
from unittest.mock import patch
import test_runtime


class ConfirmationQueueTests(unittest.TestCase):
    setUp=test_runtime.GuiRegressionTests.setUp
    tearDown=test_runtime.GuiRegressionTests.tearDown
    add=test_runtime.GuiRegressionTests.add

    def ready(self,person):
        if not getattr(self,'started',False):self.app.reply_queue.start();self.started=True
        self.app.enabled.set(True);self.app.auto_send.set(True)
        job=self.app.reply_queue.begin(person)
        self.app.reply_queue.finish(job,dict(reply='reply-'+person,reason='test',needs_human=False))
        return job

    def dialogs(self):
        created=[]
        class FakeDialog:
            def __init__(self,root,contact,incoming,reply,valid,send,cancel,close,**kwargs):
                self.contact=contact;self.incoming=incoming;self.reply=reply
                self.valid=valid;self.send=send;self.on_cancel=cancel;self.close=close
                created.append(self)
            def cancel(self,reason='cancelled'):
                self.close();self.on_cancel(reason)
        return created,FakeDialog

    def test_contacts_queue_serially_and_only_approved_body_dispatches(self):
        a=self.ready(self.a);b=self.ready(self.b);created,fake=self.dialogs();sent=[]
        self.app.submit_send=lambda *args,**kwargs:sent.append((args,kwargs))
        with patch('send_confirmation.SendConfirmation',fake):
            self.app.queue_send_confirmation(a['id'],'draft-a',True)
            self.app.queue_send_confirmation(b['id'],'draft-b',True)
            self.assertEqual(len(created),1);self.assertEqual(sent,[])
            first=created[0];self.assertIn('alpha',first.contact);self.assertEqual(first.incoming,'A-only-text')
            first.close();first.send('edited-a',True);self.app.pump_send_confirmations()
            self.assertEqual(sent,[((a['id'],),dict(text='edited-a',automatic=False,confirmed=True))])
            self.assertEqual(len(created),2);self.assertIn('beta',created[1].contact)
            self.assertEqual(created[1].incoming,'B-only-text');self.assertEqual(created[1].reply,'draft-b')

    def test_new_message_revision_invalidates_visible_confirmation(self):
        job=self.ready(self.a);created,fake=self.dialogs()
        with patch('send_confirmation.SendConfirmation',fake):
            self.app.queue_send_confirmation(job['id'],'draft',True)
            self.assertTrue(created[0].valid())
            self.app.reply_queue.begin(self.a)
            self.assertFalse(created[0].valid())

    def test_disabled_auto_mode_invalidates_idle_confirmation(self):
        job=self.ready(self.a);created,fake=self.dialogs()
        with patch('send_confirmation.SendConfirmation',fake):
            self.app.queue_send_confirmation(job['id'],'draft',True)
            self.app.auto_send.set(False)
            self.assertFalse(created[0].valid())
