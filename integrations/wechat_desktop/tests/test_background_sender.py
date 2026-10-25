import ctypes
import struct
import unittest
from unittest.mock import Mock,patch
from core import UserError
from background_sender import BackgroundWindows,validated_gate


class Value:
    IsReadOnly=False
    def __init__(self,text=''):self.Value=text
    def SetValue(self,text):self.Value=text


class BackgroundTests(unittest.TestCase):
    def test_bundled_com_runtime_can_initialize_without_reading_windows(self):
        import uiautomation as auto
        from uiautomation.uiautomation import _AutomationClient
        with auto.UIAutomationInitializerInThread():
            self.assertIsNotNone(_AutomationClient.instance().IUIAutomation)

    def setup_backend(self,text=''):
        b=object.__new__(BackgroundWindows);self.value=Value(text)
        self.input=Mock(AutomationId='Main.chat_input_field',Name='甲按住鼠标 语音输入文字',ControlTypeName='EditControl')
        self.input.GetValuePattern.return_value=self.value
        self.button=Mock(AutomationId='send_button',Name='发送(S)',ControlTypeName='ButtonControl')
        self.commits=Mock();self.button.GetInvokePattern.side_effect=AssertionError('UIA Invoke may activate windows')
        b._controls=lambda *a:[self.input,self.button]
        b._enable_tree=lambda auto,bound:b._input(auto,bound);b.trace=Mock()
        b._native_target=lambda *args:0
        def click(control,bound,submit=False):
            if submit:b.trace('submit_background');self.commits()
        b._click_control=Mock(side_effect=click)
        b._post_key=Mock(side_effect=lambda hwnd,key:self.commits())
        units=[]
        def post(hwnd,msg,wparam,lparam):
            units.append(wparam)
            self.value.Value=b''.join(n.to_bytes(2,'little') for n in units).decode('utf-16-le',errors='ignore')
        b._post=Mock(side_effect=post);b.u=Mock()
        for method in ('clipboard','foreground','chord','key','capture'):
            setattr(b,method,Mock(side_effect=AssertionError('foreground/global input is forbidden')))
        self.bound={'hwnd':123,'title':'甲','width':800,'height':600}
        return b

    def test_background_writes_reads_and_invokes_without_frontend_or_clipboard(self):
        b=self.setup_backend();b._deliver_controls(None,self.bound,'后台文字😀',lambda:None)
        self.assertEqual(self.value.Value,'后台文字😀');self.commits.assert_called_once()
        self.assertTrue(all(c.args[1]==0x102 for c in b._post.call_args_list));b.u.assert_not_called()
        self.button.GetInvokePattern.assert_not_called()
        for method in ('clipboard','foreground','chord','key','capture'):getattr(b,method).assert_not_called()
        self.assertIn('submit_background',[c.args[0] for c in b.trace.call_args_list])

    def test_existing_draft_is_preserved_and_never_sent_automatically(self):
        b=self.setup_backend('用户草稿')
        with self.assertRaisesRegex(UserError,'已有草稿'):b._deliver_controls(None,self.bound,'建议',lambda:None)
        self.assertEqual(self.value.Value,'用户草稿');self.commits.assert_not_called()

    def test_qt_delivery_never_posts_mouse_click_or_activation(self):
        b=self.setup_backend();b._deliver_controls(None,self.bound,'后台文字',lambda:None)
        b._click_control.assert_not_called()
        b._post_key.assert_called_once_with(123,0x0D)
        self.assertTrue(all(c.args[1]==0x102 for c in b._post.call_args_list))

    def test_directed_enter_has_scan_code_and_keyup_without_global_input(self):
        b=self.setup_backend();b.u.MapVirtualKeyW.return_value=0x1C;b._post=Mock()
        BackgroundWindows._post_key(b,123,0x0D)
        self.assertEqual([c.args for c in b._post.call_args_list],
            [(123,0x100,0x0D,(0x1C<<16)|1),(123,0x101,0x0D,(0x1C<<16)|0xC0000001)])
        b.key.assert_not_called();b.foreground.assert_not_called()

    def test_reviewed_identical_draft_can_be_committed_without_retyping(self):
        b=self.setup_backend('已审核');self.value.SetValue=Mock(side_effect=AssertionError())
        b._deliver_controls(None,dict(self.bound,reviewed=True),'已审核',lambda:None)
        self.commits.assert_called_once();self.value.SetValue.assert_not_called();b._post.assert_not_called()

    def test_unknown_value_does_not_become_empty(self):
        b=self.setup_backend();self.input.GetValuePattern.side_effect=RuntimeError();self.input.GetLegacyIAccessiblePattern.side_effect=RuntimeError()
        with self.assertRaisesRegex(UserError,'无法回读'):b._deliver_controls(None,self.bound,'建议',lambda:None)
        self.commits.assert_not_called();b._post.assert_not_called()

    def test_wrong_input_identity_never_writes_or_invokes(self):
        b=self.setup_backend();self.input.Name='乙';self.value.SetValue=Mock()
        with self.assertRaisesRegex(UserError,'身份不符'):b._deliver_controls(None,self.bound,'建议',lambda:None)
        self.value.SetValue.assert_not_called();self.commits.assert_not_called()

    def generic_input(self):
        b=self.setup_backend();bound=dict(self.bound,pid=7,exe='C:/Weixin.exe')
        root=Mock(ProcessId=7,NativeWindowHandle=123,Name='甲')
        self.input.Name='输入';self.input.ProcessId=7;self.input.NativeWindowHandle=0
        self.input.GetParentControl.return_value=root;b.info=Mock(return_value=dict(bound))
        return b,bound,root

    def test_generic_input_requires_exact_process_and_root_ownership(self):
        b,bound,root=self.generic_input()
        self.assertIs(b._input(None,bound),self.input)
        self.assertEqual(b.info.call_count,2)

    def test_generic_input_from_another_process_is_rejected(self):
        b,bound,root=self.generic_input();self.input.ProcessId=8
        with self.assertRaisesRegex(UserError,'归属核验'):b._input(None,bound)
        self.commits.assert_not_called()

    def test_generic_input_from_another_window_is_rejected(self):
        b,bound,root=self.generic_input();root.NativeWindowHandle=456;b.u.GetAncestor.return_value=456
        with self.assertRaisesRegex(UserError,'归属核验'):b._input(None,bound)
        self.commits.assert_not_called()

    def test_generic_input_does_not_allow_main_window(self):
        b,bound,root=self.generic_input();bound['title']='微信'
        with self.assertRaisesRegex(UserError,'归属核验'):b._input(None,bound)

    def test_generic_input_rejects_changed_native_window(self):
        b,bound,root=self.generic_input();b.info.return_value['title']='乙'
        with self.assertRaisesRegex(UserError,'归属核验'):b._input(None,bound)

    def test_generic_input_accepts_provider_root_label_with_verified_native_identity(self):
        b,bound,root=self.generic_input();root.Name='微信控件根标签'
        self.assertIs(b._input(None,bound),self.input)
        self.assertEqual(b.info.call_count,2)

    def test_generic_input_rechecks_native_title_after_parent_walk(self):
        b,bound,root=self.generic_input();b.info.side_effect=[dict(bound),dict(bound,title='乙')]
        with self.assertRaises(UserError) as caught:b._input(None,bound)
        self.assertEqual(caught.exception.probe_details['owner_failure'],'native_window_changed')
        self.commits.assert_not_called()

    def test_generic_input_missing_or_looping_parent_is_rejected(self):
        b,bound,root=self.generic_input();self.input.GetParentControl.return_value=None
        with self.assertRaisesRegex(UserError,'归属核验'):b._input(None,bound)
        self.input.GetParentControl.return_value=self.input
        with self.assertRaisesRegex(UserError,'归属核验'):b._input(None,bound)

    def test_voice_hint_trailing_whitespace_does_not_block_exact_contact(self):
        b=self.setup_backend()
        for suffix in ('按住鼠标 语音输入文字  ','长按鼠标 语音输入\r\n\t','语音输入文字\u00a0'):
            with self.subTest(suffix=suffix):
                self.input.Name='甲'+suffix
                self.assertIs(b._input(None,self.bound),self.input)

    def test_literal_voice_hint_contact_name_is_not_stripped(self):
        b=self.setup_backend();self.input.Name='语音输入'
        self.assertIs(b._input(None,dict(self.bound,title='语音输入')),self.input)

    def test_known_hint_never_allows_different_contact_or_unknown_suffix(self):
        b=self.setup_backend()
        for label in ('乙按住鼠标 语音输入文字  ','甲额外内容','乙甲'):
            self.input.Name=label
            with self.assertRaisesRegex(UserError,'身份不符'):b._input(None,self.bound)
        self.commits.assert_not_called();b._post.assert_not_called()

    def test_mismatch_has_local_labels_but_diagnostics_only_have_counts(self):
        b=self.setup_backend();self.input.Name='private-input-canary'
        with self.assertRaises(UserError) as caught:b._input(None,self.bound)
        self.assertIn('private-input-canary',str(caught.exception))
        self.assertNotIn('private-input-canary',str(caught.exception.probe_details))

    def test_failed_readback_has_no_enter_or_foreground_fallback(self):
        b=self.setup_backend();b._post.side_effect=None
        with patch('background_sender.time.sleep'):
            with self.assertRaisesRegex(UserError,'回读不符'):b._deliver_controls(None,self.bound,'建议',lambda:None)
        self.commits.assert_not_called();b.key.assert_not_called()

    def test_missing_button_stops_instead_of_pressing_global_enter(self):
        b=self.setup_backend();b._controls=lambda *args:[self.input]
        with self.assertRaisesRegex(UserError,'唯一发送按钮'):b._deliver_controls(None,self.bound,'建议',lambda:None)
        b.key.assert_not_called();self.commits.assert_not_called()

    def test_posted_unicode_is_targeted_and_uses_utf16_units_without_activate(self):
        b=self.setup_backend();self.value.IsReadOnly=True;units=[]
        self.value.Value=''
        def post(hwnd,msg,wparam,lparam):
            units.append(wparam)
            raw=b''.join(n.to_bytes(2,'little') for n in units)
            self.value.Value=raw.decode('utf-16-le',errors='ignore')
            self.assertEqual((hwnd,msg,lparam),(123,0x102,1))
        b._post=post;b._deliver_controls(None,self.bound,'😀好',lambda:None)
        self.assertEqual(len(units),3);self.assertEqual(self.value.Value,'😀好');self.commits.assert_called_once()

    def test_gate_rejects_unknown_versions_and_invalid_binary(self):
        with self.assertRaisesRegex(UserError,'版本未验证'):validated_gate(b'','9.9')
        with self.assertRaisesRegex(UserError,'特征不匹配'):validated_gate(b'fake','4.1.15.13')

    def test_opaque_shell_and_missing_input_are_distinguished_without_names(self):
        b=self.setup_backend()
        b._controls=lambda *args:[Mock(AutomationId='',ClassName='Qt51514QWindowIcon')]
        with self.assertRaises(UserError) as caught:b._input(None,self.bound)
        self.assertEqual(caught.exception.probe_details['input_failure'],'tree_opaque')
        self.assertNotIn('甲',str(caught.exception.probe_details))
        b._controls=lambda *args:[Mock(AutomationId='',ClassName='mmui::MainWindow')]
        with self.assertRaises(UserError) as caught:b._input(None,self.bound)
        self.assertEqual(caught.exception.probe_details['input_failure'],'input_missing')

    def test_wrong_identity_does_not_attempt_gate_activation(self):
        b=self.setup_backend();b.prepare_lock=__import__('threading').RLock();b.k=Mock()
        b._enable_tree=lambda auto,bound:BackgroundWindows._enable_tree(b,auto,bound)
        self.input.Name='另一对象'
        with self.assertRaises(UserError) as caught:b._enable_tree(None,self.bound)
        self.assertEqual(caught.exception.probe_details['input_failure'],'input_identity_mismatch')
        b.k.OpenProcess.assert_not_called();b._post.assert_not_called()

    def test_ambiguous_inputs_do_not_attempt_gate_activation(self):
        b=self.setup_backend();b.prepare_lock=__import__('threading').RLock();b.k=Mock()
        b._enable_tree=lambda auto,bound:BackgroundWindows._enable_tree(b,auto,bound)
        b._controls=lambda *args:[self.input,self.input]
        with self.assertRaises(UserError) as caught:b._enable_tree(None,self.bound)
        self.assertEqual(caught.exception.probe_details['input_failure'],'input_ambiguous')
        b.k.OpenProcess.assert_not_called()

    def test_controls_changing_at_final_commit_stop(self):
        b=self.setup_backend();old=b._commit
        def commit(auto,bound,text,guard):self.value.Value='人工新草稿';return old(auto,bound,text,guard)
        b._commit=commit
        with self.assertRaisesRegex(UserError,'提交前已变化'):b._deliver_controls(None,self.bound,'建议',lambda:None)
        self.commits.assert_not_called()

    def test_offscreen_invalid_rect_never_wraps_into_target_coordinates(self):
        b=self.setup_backend();self.input.BoundingRectangle=Mock(left=-32000,top=-32000,right=-32000,bottom=-32000)
        with self.assertRaisesRegex(UserError,'无法定位'):BackgroundWindows._click_control(b,self.input,self.bound)
        b._post.assert_not_called()

    def test_child_window_from_another_root_is_rejected(self):
        b=self.setup_backend();self.input.NativeWindowHandle=777;b.u.GetAncestor.return_value=456
        with self.assertRaisesRegex(UserError,'不属于绑定'):BackgroundWindows._native_target(b,self.input,self.bound)
