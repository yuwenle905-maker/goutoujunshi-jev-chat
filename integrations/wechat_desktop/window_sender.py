"""显式绑定独立聊天窗口；不搜索昵称、不退回微信主窗口、不注入微信进程。"""
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import time
from core import UserError


class NativeWindows:
    def __init__(self):
        self.trace=lambda *a,**k:None
        self.tracks_submission=True
        self.clipboard_owner=None
        self.u=ctypes.WinDLL('user32',use_last_error=True)
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        self.u.GetDpiForWindow.argtypes=[W.HWND];self.u.GetDpiForWindow.restype=W.UINT
        # HWND/HANDLE are pointer sized on x64; default ctypes int truncates them.
        for name,args,result in [
            ('GetForegroundWindow',[],W.HWND),('GetAncestor',[W.HWND,W.UINT],W.HWND),
            ('WindowFromPoint',[W.POINT],W.HWND),('GetWindowTextLengthW',[W.HWND],ctypes.c_int),
            ('GetWindowTextW',[W.HWND,W.LPWSTR,ctypes.c_int],ctypes.c_int),
            ('GetWindowThreadProcessId',[W.HWND,ctypes.POINTER(W.DWORD)],W.DWORD),
            ('IsWindowVisible',[W.HWND],W.BOOL),('IsWindow',[W.HWND],W.BOOL),
            ('IsIconic',[W.HWND],W.BOOL),
            ('SetForegroundWindow',[W.HWND],W.BOOL),('ShowWindow',[W.HWND,ctypes.c_int],W.BOOL),
            ('GetClientRect',[W.HWND,ctypes.POINTER(W.RECT)],W.BOOL),
            ('ClientToScreen',[W.HWND,ctypes.POINTER(W.POINT)],W.BOOL),
            ('ScreenToClient',[W.HWND,ctypes.POINTER(W.POINT)],W.BOOL),
            ('GetCursorPos',[ctypes.POINTER(W.POINT)],W.BOOL),
            ('SetCursorPos',[ctypes.c_int,ctypes.c_int],W.BOOL),
            ('OpenClipboard',[W.HWND],W.BOOL),('CloseClipboard',[],W.BOOL),
            ('GetClipboardData',[W.UINT],W.HANDLE),('SetClipboardData',[W.UINT,W.HANDLE],W.HANDLE),
            ('EmptyClipboard',[],W.BOOL),('IsClipboardFormatAvailable',[W.UINT],W.BOOL)]:
            f=getattr(self.u,name);f.argtypes=args;f.restype=result
        for name,args,result in [
            ('OpenProcess',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
            ('QueryFullProcessImageNameW',[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)],W.BOOL),
            ('CloseHandle',[W.HANDLE],W.BOOL),('GlobalAlloc',[W.UINT,ctypes.c_size_t],W.HANDLE),
            ('GlobalSize',[W.HANDLE],ctypes.c_size_t),
            ('GlobalLock',[W.HANDLE],ctypes.c_void_p),('GlobalUnlock',[W.HANDLE],W.BOOL),
            ('GlobalFree',[W.HANDLE],W.HANDLE)]:
            f=getattr(self.k,name);f.argtypes=args;f.restype=result

    def info(self,hwnd):
        if not self.u.IsWindow(hwnd):raise UserError('绑定的窗口已关闭，请重新绑定。')
        buf=ctypes.create_unicode_buffer(self.u.GetWindowTextLengthW(hwnd)+1)
        self.u.GetWindowTextW(hwnd,buf,len(buf));pid=W.DWORD()
        self.u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        process=self.k.OpenProcess(0x1000,False,pid.value)
        if not process:raise UserError('无法核实窗口所属程序。')
        try:
            exe=ctypes.create_unicode_buffer(32768);length=W.DWORD(len(exe))
            if not self.k.QueryFullProcessImageNameW(process,0,exe,ctypes.byref(length)):raise UserError('无法核实微信进程。')
        finally:self.k.CloseHandle(process)
        rect=W.RECT();self.u.GetClientRect(hwnd,ctypes.byref(rect))
        return dict(hwnd=int(hwnd),title=buf.value,pid=pid.value,exe=exe.value,width=rect.right,height=rect.bottom,dpi=int(self.u.GetDpiForWindow(hwnd)))

    def windows(self):
        result=[]
        callback_type=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
        def visit(hwnd,_):
            try:
                row=self.info(hwnd)
                if self.u.IsWindowVisible(hwnd) and Path(row['exe']).name.lower() in ('weixin.exe','wechat.exe') and row['title']:
                    result.append(row)
            except Exception:pass
            return True
        self.u.EnumWindows.argtypes=[callback_type,W.LPARAM];self.u.EnumWindows.restype=W.BOOL
        self.u.EnumWindows(callback_type(visit),0)
        return result

    def capture(self,hwnd):
        point=W.POINT();self.u.GetCursorPos(ctypes.byref(point))
        target=self.u.GetAncestor(self.u.WindowFromPoint(point),2)
        if target!=hwnd:raise UserError('鼠标不在所选微信聊天窗口内，未绑定。')
        self.u.ScreenToClient(hwnd,ctypes.byref(point))
        return [point.x,point.y]

    def foreground(self,hwnd):
        if self.u.GetForegroundWindow()!=hwnd:raise UserError('前台窗口已切换，停止发送。')

    def key(self,vk,up=False):self.u.keybd_event(vk,0,2 if up else 0,0)
    def chord(self,vk):
        self.key(0x11)
        try:self.key(vk);self.key(vk,True)
        finally:self.key(0x11,True)

    def clipboard(self,value=None):
        # Clipboard rendering and other apps can briefly hold the clipboard after
        # Ctrl+C. Retry acquisition/read only; never repeat an Enter submission.
        for attempt in range(10):
            try:return self._clipboard_once(value)
            except UserError as exc:
                if not getattr(exc,'clipboard_transient',False) or attempt==9:raise
                self.trace('clipboard_retry',attempt=attempt+1,reason=exc.clipboard_step,winerror=exc.winerror)
                time.sleep(.06)

    def clipboard_error(self,step,message,transient=True):
        exc=UserError(message);exc.winerror=ctypes.get_last_error()
        exc.clipboard_step=step;exc.clipboard_transient=transient
        return exc

    def _clipboard_once(self,value=None):
        owner=getattr(self,'clipboard_owner',None)
        if value is not None and not owner:
            raise UserError('剪贴板写入窗口未初始化，未发送。')
        ctypes.set_last_error(0)
        if not self.u.OpenClipboard(owner):raise self.clipboard_error('open','剪贴板正被占用，未发送。')
        try:
            if value is None:
                if not self.u.IsClipboardFormatAvailable(13):
                    if self.u.CountClipboardFormats():raise UserError('剪贴板含图片/文件，请先复制一段文字再发送。')
                    return ''
                handle=self.u.GetClipboardData(13)
                if not handle:raise self.clipboard_error('get_data','无法读取剪贴板：文字数据尚未就绪，未发送。')
                size=self.k.GlobalSize(handle)
                if not size:raise self.clipboard_error('size','无法读取剪贴板：文字内存不可用，未发送。')
                if size>8*1024*1024:raise UserError('无法读取剪贴板：文字超过8MB，未发送。')
                ptr=self.k.GlobalLock(handle)
                if not ptr:raise self.clipboard_error('lock','无法读取剪贴板：文字内存暂不可锁定，未发送。')
                try:
                    raw=ctypes.string_at(ptr,size)
                    end=next((i for i in range(0,len(raw)-1,2) if raw[i:i+2]==b'\0\0'),None)
                    if end is None:raise UserError('无法读取剪贴板：文字缺少结束标记，未发送。')
                    try:return raw[:end].decode('utf-16-le')
                    except UnicodeError:raise UserError('无法读取剪贴板：文字编码无效，未发送。') from None
                finally:self.k.GlobalUnlock(handle)
            raw=(value+'\0').encode('utf-16-le');handle=self.k.GlobalAlloc(0x42,len(raw))
            if not handle:raise UserError('无法准备剪贴板。')
            ptr=self.k.GlobalLock(handle)
            if not ptr:self.k.GlobalFree(handle);raise UserError('无法锁定剪贴板。')
            ctypes.memmove(ptr,raw,len(raw));self.k.GlobalUnlock(handle)
            if not self.u.EmptyClipboard():
                self.k.GlobalFree(handle);raise self.clipboard_error('empty','无法清理剪贴板，未发送。',False)
            if not self.u.SetClipboardData(13,handle):self.k.GlobalFree(handle);raise UserError('无法写入剪贴板。')
        finally:self.u.CloseClipboard()

    def read_input(self,hwnd):
        import uuid
        sentinel='GOUTOU-'+uuid.uuid4().hex
        self.clipboard(sentinel);self.foreground(hwnd);self.chord(0x41);self.chord(0x43);time.sleep(.18)
        self.foreground(hwnd);text=self.clipboard()
        return '' if text==sentinel else text

    def deliver(self,bound,text,guard):
        self.trace('clipboard_prepare')
        hwnd=bound['hwnd'];old=self.clipboard();owned=None
        try:
            self.trace('activate_window',bound_hwnd=hwnd)
            if self.u.IsIconic(hwnd):self.u.ShowWindow(hwnd,9)
            self.u.SetForegroundWindow(hwnd);time.sleep(.25)
            self.trace('verify_foreground',foreground_hwnd=int(self.u.GetForegroundWindow() or 0),bound_hwnd=hwnd)
            guard();self.foreground(hwnd)
            self.trace('focus_input')
            p=W.POINT(*bound['point']);self.u.ClientToScreen(hwnd,ctypes.byref(p))
            self.u.SetCursorPos(p.x,p.y)
            self.u.mouse_event(2,0,0,0,0);self.u.mouse_event(4,0,0,0,0);time.sleep(.1)
            guard()
            self.trace('check_existing_draft')
            existing=self.read_input(hwnd);owned=self.clipboard()
            if existing:raise UserError('微信输入框已有草稿，已停止，保留你的文字。')
            self.trace('paste_reply',expected_length=len(text))
            self.clipboard(text);owned=text;guard();self.foreground(hwnd);self.chord(0x56);time.sleep(.2)
            actual=self.read_input(hwnd)
            self.trace('verify_pasted_text',expected_length=len(text),input_length=len(actual))
            if actual.replace('\r\n','\n')!=text.replace('\r\n','\n'):raise UserError('输入框回读不符，未按发送；请检查微信草稿。')
            guard();self.foreground(hwnd)
            self.trace('press_enter')
            self.key(0x0D);self.key(0x0D,True)
            self.trace('enter_submitted')
        finally:
            # Clipboard is shared with the user. Restore text only if still ours.
            try:
                current=self.clipboard()
                if current==owned or current.startswith('GOUTOU-'):self.clipboard(old)
            except Exception:pass


class WindowSender:
    def __init__(self,backend=None,diagnostics=None):
        self.backend=backend or NativeWindows();self.bindings={};self.diagnostics=diagnostics;self.last_stage='idle';self.submission_started=None
    def candidates(self):return self.backend.windows()
    def auto_bind(self,people,windows=None):
        """Unique full-address-book names only; never assign one window twice."""
        windows=self.candidates() if windows is None else windows
        added=[];blocked={}
        for person,state in people.items():
            binding=state['binding']
            if person in self.bindings:
                try:self.check(person,binding);continue
                except UserError:self.bindings.pop(person,None)
            names=set(binding.get('auto_window_titles',[]))
            matches=[w for w in windows if w['title'] in names and w['title'] not in ('微信','Weixin','WeChat')]
            # Multiple active processes/accounts cannot be identified from titles.
            if any(not w.get('pid') for w in windows) or len({w['pid'] for w in windows})!=1:
                blocked[person]='多个微信进程，需手动关联';continue
            if len(matches)!=1:
                blocked[person]='未找到唯一窗口；请打开独立聊天窗口，重名需手动关联';continue
            window=matches[0]
            owners=[p for p,s in people.items() if window['title'] in set(s['binding'].get('auto_window_titles',[]))]
            if owners!=[person]:
                blocked[person]='联系人名称不唯一，需手动关联';continue
            try:
                now=self.backend.info(window['hwnd'])
                if any(now[k]!=window[k] for k in ('title','pid','exe')):raise UserError('窗口已变化')
                self.bind(person,binding,now,[max(1,now['width']//2),max(1,now['height']*3//4)])
                self.bindings[person]['automatic_binding']=True;added.append(person)
                if self.diagnostics:self.diagnostics.event('send_window_auto_bound',person=person,stage='binding',bound_hwnd=now['hwnd'],pid=now['pid'])
            except UserError:blocked[person]='窗口无法自动关联，请检查或手动设置'
        return added,blocked
    def bind(self,person,binding,window,point):
        if any(p!=person and b['hwnd']==window['hwnd'] for p,b in self.bindings.items()):
            raise UserError('这个窗口已关联另一位对象，不能同时绑定给不同联系人。')
        allowed={binding.get(k) for k in ('remark','nick_name','alias','username')}-{None,''}
        if window['title'] in ('微信','Weixin','WeChat') or window['title'] not in allowed:
            raise UserError('请选择标题与此联系人完全相符的独立聊天窗口；不绑定微信主窗口。')
        if Path(window['exe']).name.lower() not in ('wechat.exe','weixin.exe'):raise UserError('不是微信窗口。')
        if not (0<point[0]<window['width'] and window['height']//2<point[1]<window['height']):
            raise UserError('请把鼠标移到该聊天窗口下半部的消息输入框。')
        self.bindings[person]=dict(window,point=point,account=binding['account'],peer=binding['username'],
            anchor_x=point[0]/window['width'],anchor_bottom=window['height']-point[1])
    def check(self,person,binding):
        bound=self.bindings.get(person)
        if not bound:raise UserError('此对象尚未绑定独立发送窗口。')
        if (bound['account'],bound['peer'])!=(binding['account'],binding['username']):raise UserError('对象身份发生变化，请重新绑定。')
        now=self.backend.info(bound['hwnd'])
        if any(now.get(k)!=bound[k] for k in ('title','pid','exe')):
            raise UserError('发送窗口身份、标题或进程已改变，请重新绑定。')
        if getattr(self.backend,'background',False):return bound
        if bound.get('dpi') and now.get('dpi')!=bound['dpi']:raise UserError('窗口缩放比例已改变，请重新绑定输入框。')
        if any(now[k]!=bound[k] for k in ('width','height')):
            x=round(bound.get('anchor_x',bound['point'][0]/bound['width'])*now['width'])
            y=now['height']-bound.get('anchor_bottom',bound['height']-bound['point'][1])
            if not (0<x<now['width'] and now['height']//2<y<now['height']):
                raise UserError('窗口过小，无法确认底部输入区域；请放大窗口或重新绑定。')
            if self.diagnostics:self.diagnostics.event('send_window_resized',person=person,stage='window_geometry',expected_width=bound['width'],expected_height=bound['height'],actual_width=now['width'],actual_height=now['height'])
            bound.update(width=now['width'],height=now['height'],point=[x,y])
        return bound
    def send(self,person,binding,text,guard,reviewed=False):
        self.submission_started=False if getattr(self.backend,'tracks_submission',False) else None
        def trace(stage,**fields):
            if stage!='clipboard_retry':self.last_stage=stage
            if stage in ('press_enter','submit_background'):self.submission_started=True
            if self.diagnostics:self.diagnostics.event('send_stage',person=person,stage=stage,**fields)
        self.backend.trace=trace
        trace('verify_bound_window')
        bound=dict(self.check(person,binding),reviewed=reviewed)
        def checked():self.check(person,binding);guard()
        try:self.backend.deliver(bound,text,checked)
        except Exception as exc:
            if self.diagnostics:self.diagnostics.error('send_transport_error',exc,person=person,stage=self.last_stage)
            raise
