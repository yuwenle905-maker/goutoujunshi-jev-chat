import ctypes
import unittest
from unittest.mock import Mock,patch
from core import UserError
from window_sender import NativeWindows


class ClipboardRetryTests(unittest.TestCase):
    def backend(self,text='测试文字'):
        b=object.__new__(NativeWindows);b.u=Mock();b.k=Mock();b.clipboard_owner=321;b.trace=Mock()
        b.u.OpenClipboard.return_value=True;b.u.IsClipboardFormatAvailable.return_value=True
        b.u.GetClipboardData.return_value=123
        self.buffer=ctypes.create_string_buffer((text+'\0').encode('utf-16-le'))
        b.k.GlobalSize.return_value=len(self.buffer.raw);b.k.GlobalLock.return_value=ctypes.addressof(self.buffer)
        return b

    def test_busy_clipboard_is_reopened_with_owner_and_retried(self):
        b=self.backend();b.u.OpenClipboard.side_effect=[False,False,True]
        with patch('window_sender.time.sleep'):self.assertEqual(b.clipboard(),'测试文字')
        self.assertEqual(b.u.OpenClipboard.call_count,3);b.u.OpenClipboard.assert_called_with(321)
        b.u.CloseClipboard.assert_called_once();self.assertEqual(b.trace.call_count,2)

    def test_delayed_null_handle_is_retried_not_treated_as_empty(self):
        b=self.backend('有草稿');b.u.GetClipboardData.side_effect=[None,None,123]
        with patch('window_sender.time.sleep'):self.assertEqual(b.clipboard(),'有草稿')
        self.assertEqual(b.k.GlobalLock.call_count,1);self.assertEqual(b.u.CloseClipboard.call_count,3)

    def test_lock_failure_releases_clipboard_before_retry(self):
        b=self.backend();ptr=ctypes.addressof(self.buffer);b.k.GlobalLock.side_effect=[None,ptr]
        with patch('window_sender.time.sleep'):self.assertEqual(b.clipboard(),'测试文字')
        self.assertEqual(b.u.CloseClipboard.call_count,2);b.k.GlobalUnlock.assert_called_once_with(123)

    def test_permanent_failure_is_bounded_and_keeps_failure_metadata(self):
        b=self.backend();b.u.GetClipboardData.return_value=None
        with patch('window_sender.time.sleep'),patch('window_sender.ctypes.get_last_error',return_value=5):
            with self.assertRaises(UserError) as caught:b.clipboard()
        self.assertEqual(b.u.GetClipboardData.call_count,10)
        self.assertEqual(caught.exception.clipboard_step,'get_data');self.assertEqual(caught.exception.winerror,5)
        b.k.GlobalLock.assert_not_called()

    def test_invalid_or_discarded_handle_is_never_empty_draft(self):
        b=self.backend();b.k.GlobalSize.return_value=0
        with patch('window_sender.time.sleep'):
            with self.assertRaisesRegex(UserError,'文字内存不可用'):b.clipboard()
        b.k.GlobalLock.assert_not_called()

    def test_malformed_text_is_bounded_and_rejected(self):
        b=self.backend();self.buffer=ctypes.create_string_buffer(b'A\0B\0',4)
        b.k.GlobalSize.return_value=4;b.k.GlobalLock.return_value=ctypes.addressof(self.buffer)
        with self.assertRaisesRegex(UserError,'结束标记'):b.clipboard()
        b.k.GlobalUnlock.assert_called_once();self.assertEqual(b.u.GetClipboardData.call_count,1)

    def test_empty_unicode_text_is_readable(self):
        self.assertEqual(self.backend('').clipboard(),'')

    def test_write_uses_real_owner_and_checks_empty_result(self):
        b=self.backend();b.k.GlobalAlloc.return_value=123;b.u.EmptyClipboard.return_value=False
        with self.assertRaisesRegex(UserError,'无法清理'):b.clipboard('a')
        b.u.OpenClipboard.assert_called_once_with(321);b.u.SetClipboardData.assert_not_called()
        b.k.GlobalFree.assert_called_once_with(123);b.u.CloseClipboard.assert_called_once()

    def test_write_without_owner_does_not_touch_clipboard(self):
        b=self.backend();b.clipboard_owner=None
        with self.assertRaisesRegex(UserError,'未初始化'):b.clipboard('x')
        b.u.OpenClipboard.assert_not_called()

