import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
import zipfile
from diagnostics import Diagnostics
from core import Store,UserError


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.log=Diagnostics(Path(self.tmp.name)/'logs','test')
    def tearDown(self):self.log.close();self.tmp.cleanup()
    def test_no_credentials_chat_or_contact_fields_or_exception_messages(self):
        self.log.event('test',person='private-peer-canary',job='private-job-canary',reply='private-chat-canary',key='private-key-canary')
        try:raise RuntimeError('private-error-key-canary')
        except Exception as exc:self.log.error('test_error',exc)
        text=self.log.text()
        for secret in ('private-peer-canary','private-job-canary','private-chat-canary','private-key-canary','private-error-key-canary'):
            self.assertNotIn(secret,text)
        self.assertIn('RuntimeError',text);self.assertIn('frames',text)
    def test_export_contains_current_and_persisted_metadata(self):
        self.log.event('send_stage',stage='press_enter');dest=Path(self.tmp.name)/'diagnostic.zip';self.log.export(dest)
        with zipfile.ZipFile(dest) as z:
            self.assertIsNone(z.testzip());self.assertIn('current-session.jsonl',z.namelist())
            self.assertIn(b'press_enter',z.read('current-session.jsonl'))
    def test_last_session_can_be_seen_after_restart(self):
        folder=self.log.folder;self.log.event('previous_run');self.log.close();self.log=Diagnostics(folder,'test')
        self.assertIn('previous_run',self.log.text())
    def test_rotation_is_bounded(self):
        self.log.handler.maxBytes=200
        for i in range(20):self.log.event('bounded',count=i)
        self.assertLessEqual(len(list(self.log.folder.glob('events.jsonl*'))),3)
    def test_friendly_reason_and_chinese_stage(self):
        self.log.error('send_transport_error',UserError('剪贴板含图片/文件，请先复制一段文字再发送。'),stage='clipboard_prepare')
        self.assertIn('剪贴板非文字',self.log.view_text());self.assertIn('检查剪贴板',self.log.view_text())

    def test_clear_removes_owned_logs_and_memory_but_preserves_other_files(self):
        self.log.handler.maxBytes=200
        for i in range(20):self.log.event('old_canary',count=i)
        keep=self.log.folder/'events.jsonl-export.zip';keep.write_bytes(b'keep')
        revision=self.log.count;self.log.clear()
        self.assertGreater(self.log.count,revision);self.assertNotIn('old_canary',self.log.text())
        self.assertEqual(keep.read_bytes(),b'keep')
        self.assertFalse((self.log.folder/'events.jsonl.1').exists())
        self.assertFalse((self.log.folder/'events.jsonl.2').exists())
        self.log.event('after_clear');self.log.close();self.log=Diagnostics(self.log.folder,'test')
        self.assertIn('after_clear',self.log.text());self.assertNotIn('old_canary',self.log.text())
        dest=Path(self.tmp.name)/'after.zip';self.log.export(dest)
        with zipfile.ZipFile(dest) as z:self.assertNotIn(b'old_canary',z.read('logs/events.jsonl'))

    def test_clear_file_error_is_reported_and_logging_can_continue(self):
        with patch('diagnostics.Path.unlink',side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):self.log.clear()
        self.log.event('after_failure');self.assertIn('after_failure',self.log.text())

    def test_clipboard_failure_reports_useful_static_reason(self):
        self.log.error('test',UserError('无法读取剪贴板：文字数据尚未就绪，未发送。'))
        self.assertIn('剪贴板文字读取失败',self.log.view_text())

    def test_background_probe_keeps_counts_and_failure_code_without_input_names(self):
        error=UserError('private-window-name')
        error.probe_details={'node_count':2,'input_count':0,'mmui_count':0,'input_failure':'tree_opaque',
            'gate_original':0,'gate_changed':True,'gate_restored':True,'input_name':'private-input-name'}
        self.log.error('background_probe_error',error)
        text=self.log.view_text()
        self.assertIn('tree_opaque',text);self.assertIn('node_count',text)
        self.assertNotIn('private-window-name',text);self.assertNotIn('private-input-name',text)


class DiagnosticGuiTests(unittest.TestCase):
    def setUp(self):
        from app import App
        self.tmp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.root.withdraw();self.app=App(self.root,self.tmp.name)
        self.person=Store.person_id('own','peer')
        self.app.register_person(dict(account='own',username='peer',alias='peer'),[],self.person)
    def tearDown(self):self.app.close();self.tmp.cleanup()
    def test_send_actions_are_outside_expanding_text_panes(self):
        row=self.app.approve_button.master
        self.assertEqual(row.master,self.app.tabs['回复工作台'])
        children=row.master.pack_slaves()
        panes=next(w for w in children if w.winfo_class()=='TPanedwindow')
        self.assertLess(children.index(row),children.index(panes))
    def test_condition_check_does_not_input_or_send_and_logs_failures(self):
        sent=[];self.app.submit_send=lambda *a,**k:sent.append(a)
        with patch('tkinter.messagebox.showinfo') as show:self.app.check_send_conditions()
        self.assertEqual(sent,[]);self.assertIn('未通过',show.call_args.args[1])
        self.assertIn('send_condition_blocked',self.app.diagnostics.text())
    def test_failed_send_status_survives_switching_view(self):
        self.app.handle_event(('send_failed',self.person,'前台窗口已切换，停止发送。'))
        self.app.select_person(self.person);self.assertIn('前台窗口',self.app.last_send_status.get())
    def test_log_page_has_events_and_manual_mode_is_explicit(self):
        self.assertIn('诊断日志',self.app.tabs);self.app.refresh_logs()
        self.assertIn('app_start',self.app.log_text.get('1.0','end'));self.assertIn('人工审核',self.app.send_mode_status.get())

    def test_clear_logs_button_clears_view_and_preserves_settings(self):
        self.app.store.save('settings','clear_test',{'keep':True})
        self.app.diagnostics.event('old_canary');self.app.clear_logs()
        self.assertNotIn('old_canary',self.app.log_text.get('1.0','end'))
        self.assertIn('logs_cleared',self.app.log_text.get('1.0','end'))
        self.assertEqual(self.app.store.get('settings','clear_test'),{'keep':True})
        row=self.app.tabs['诊断日志'].pack_slaves()[2]
        self.assertTrue(any(w.cget('text')=='清空日志' for w in row.pack_slaves()))


class NativeSequenceTests(unittest.TestCase):
    def backend(self,actual):
        from window_sender import NativeWindows
        class User32:
            def __getattr__(self,name):return lambda *a:123 if name=='GetForegroundWindow' else True
        b=object.__new__(NativeWindows);b.u=User32();b.trace=lambda *a,**k:None
        b.foreground=lambda hwnd:None;b.chord=lambda vk:None;b.key=lambda *a:None
        b.clipboard=lambda value=None:'';values=iter(['',actual]);b.read_input=lambda hwnd:next(values)
        return b
    def test_paste_mismatch_never_presses_enter(self):
        b=self.backend('different');keys=[];stages=[];b.key=lambda *a:keys.append(a);b.trace=lambda stage,**kw:stages.append(stage)
        with patch('window_sender.time.sleep'):
            with self.assertRaisesRegex(UserError,'回读不符'):b.deliver(dict(hwnd=123,point=[1,2]),'expected',lambda:None)
        self.assertEqual(keys,[]);self.assertIn('verify_pasted_text',stages);self.assertNotIn('press_enter',stages)
    def test_windows_line_endings_can_be_verified_then_enter_submitted(self):
        b=self.backend('a\r\nb');keys=[];stages=[];b.key=lambda *a:keys.append(a);b.trace=lambda stage,**kw:stages.append(stage)
        with patch('window_sender.time.sleep'):b.deliver(dict(hwnd=123,point=[1,2]),'a\nb',lambda:None)
        self.assertEqual(keys,[(13,),(13,True)]);self.assertIn('enter_submitted',stages)
    def test_non_minimized_window_is_not_restored_or_unmaximized(self):
        b=self.backend('expected');restores=[]
        b.u.IsIconic=lambda hwnd:False;b.u.ShowWindow=lambda *a:restores.append(a)
        with patch('window_sender.time.sleep'):b.deliver(dict(hwnd=123,point=[1,2]),'expected',lambda:None)
        self.assertEqual(restores,[])
