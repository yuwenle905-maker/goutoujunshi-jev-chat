import unittest
import test_runtime
from core import UserError
from window_sender import WindowSender
from wechat_reader import WechatReader


class Windows:
    def __init__(self):
        self.rows=[dict(hwnd=i,title=name,pid=9,exe=r'C:\test\Weixin.exe',width=800,height=600)
            for i,name in enumerate(('甲','乙','微信'),1)]
    def windows(self):return [dict(w) for w in self.rows]
    def info(self,hwnd):
        return dict(next(w for w in self.rows if w['hwnd']==hwnd))


class AutoBindingTests(unittest.TestCase):
    def setUp(self):
        self.backend=Windows();self.sender=WindowSender(self.backend)
        self.people={name:{'binding':dict(account='own',username='peer-'+name,remark=name,auto_window_titles=[name])}
            for name in ('甲','乙')}
    def test_all_people_bound_once_independent_of_selection(self):
        added,blocked=self.sender.auto_bind(self.people)
        self.assertEqual(set(added),{'甲','乙'});self.assertEqual(blocked,{})
        self.assertEqual({v['hwnd'] for v in self.sender.bindings.values()},{1,2})
        self.assertEqual(self.sender.auto_bind(self.people)[0],[])
    def test_duplicate_windows_not_guessed(self):
        self.backend.rows.append(dict(self.backend.rows[0],hwnd=4))
        added,_=self.sender.auto_bind(self.people)
        self.assertEqual(added,['乙']);self.assertNotIn('甲',self.sender.bindings)
    def test_multiple_processes_require_manual(self):
        self.backend.rows[1]['pid']=10
        self.assertEqual(self.sender.auto_bind(self.people)[0],[])
    def test_collision_with_unmonitored_contact_excludes_title(self):
        reader=object.__new__(WechatReader)
        reader.window_name_owners={'甲':{'peer-甲','unmonitored'}}
        reader.add_window_titles(self.people['甲']['binding'])
        self.assertEqual(self.people['甲']['binding']['auto_window_titles'],[])
        self.assertNotIn('甲',self.sender.auto_bind(self.people)[0])
    def test_missing_index_never_auto_binds(self):
        for state in self.people.values():state['binding'].pop('auto_window_titles')
        self.assertEqual(self.sender.auto_bind(self.people)[0],[])
    def test_window_closed_then_reopened_updates_handle(self):
        self.sender.auto_bind(self.people)
        self.backend.rows[0]['title']='changed'
        self.backend.rows.append(dict(self.backend.rows[0],hwnd=4,title='甲'))
        self.assertIn('甲',self.sender.auto_bind(self.people)[0])
        self.assertEqual(self.sender.bindings['甲']['hwnd'],4)
    def test_same_window_never_shared(self):
        self.people['乙']['binding']['auto_window_titles']=['甲']
        self.assertEqual(self.sender.auto_bind(self.people)[0],[])
    def test_native_identity_changed_stops_binding(self):
        rows=self.backend.windows();self.backend.rows[0]['pid']=11
        added,_=self.sender.auto_bind(self.people,rows)
        self.assertNotIn('甲',added)


class AutoBindingGuiTests(unittest.TestCase):
    setUp=test_runtime.GuiRegressionTests.setUp
    tearDown=test_runtime.GuiRegressionTests.tearDown
    add=test_runtime.GuiRegressionTests.add
    def test_refresh_binds_all_people_without_switching_selected_person(self):
        windows=Windows();windows.rows[0]['title']='alpha';windows.rows[1]['title']='beta'
        self.app.window_sender=WindowSender(windows)
        for state in self.app.people.values():
            state['binding']['auto_window_titles']=[state['binding']['username']]
        selected=self.app.person
        self.app.refresh_send_windows(quiet=True)
        self.assertEqual(set(self.app.window_sender.bindings),{self.a,self.b})
        self.assertEqual(self.app.person,selected)
        self.assertIn('2 位',self.app.inbox_status.get())
    def test_waiting_auto_job_resumes_only_after_window_appears(self):
        windows=Windows();windows.rows=[];self.app.window_sender=WindowSender(windows)
        self.app.people[self.b]['binding']['auto_window_titles']=['beta']
        self.app.waiting_window_jobs[self.b]='pending-job';calls=[]
        self.app.submit_send=lambda *a,**kw:calls.append((a,kw))
        self.app.refresh_send_windows(quiet=True);self.root.update()
        self.assertEqual(calls,[])
        windows.rows=[dict(hwnd=2,title='beta',pid=9,exe=r'C:\test\Weixin.exe',width=800,height=600)]
        self.app.refresh_send_windows(quiet=True);self.root.update()
        self.assertEqual(calls,[(('pending-job',),{'automatic':True})])
