"""Strict background transport: no foreground, global input or clipboard fallback.

Qt accessibility gate location/pattern derived from Apache-2.0
fanyuantaier/wechatauto-replica (d322c4a); see vendor/LICENSE-WechatAuto.txt.
Only a validated runtime accessibility flag is enabled, never executable code.
"""
import ctypes
from contextlib import contextmanager
from ctypes import wintypes as W
from pathlib import Path
import re
import struct
import threading
import time
from core import UserError
from window_sender import NativeWindows


def validated_gate(data,version):
    rva={'4.1.15.13':0x0B135C38}.get(version)
    if rva is None:raise UserError('后台准备：当前微信版本未验证，未修改进程。')
    try:
        pe=struct.unpack_from('<I',data,0x3c)[0]
        if data[:2]!=b'MZ' or data[pe:pe+4]!=b'PE\0\0':raise ValueError()
        count=struct.unpack_from('<H',data,pe+6)[0];optional=struct.unpack_from('<H',data,pe+20)[0]
        if count>96:raise ValueError()
        sections=[]
        for i in range(count):
            pos=pe+24+optional+i*40
            size,va,rawsize,offset=struct.unpack_from('<IIII',data,pos+8)
            flags=struct.unpack_from('<I',data,pos+36)[0]
            sections.append((va,max(size,rawsize),offset,rawsize,flags))
        if not any(va<=rva<va+size and flags&0x80000000 and not flags&0x20000000 for va,size,_,_,flags in sections):raise ValueError()
        pattern=rb'\x48\x85\xc9\x0f\x84....\x80\x3d(?P<disp>.{4})\x00\x0f\x84'
        for match in re.finditer(pattern,data,re.DOTALL):
            off=match.start('disp')
            for va,size,raw,rawsize,flags in sections:
                if flags&0x20000000 and raw<=off<raw+rawsize:
                    cmp=va+off-raw-2
                    if cmp+7+struct.unpack('<i',match.group('disp'))[0]==rva:return rva
    except (ValueError,struct.error,IndexError):pass
    raise UserError('后台准备：微信DLL特征不匹配，未修改进程。')


def file_version(path):
    lib=ctypes.WinDLL('version',use_last_error=True)
    lib.GetFileVersionInfoSizeW.argtypes=[W.LPCWSTR,ctypes.POINTER(W.DWORD)];lib.GetFileVersionInfoSizeW.restype=W.DWORD
    lib.GetFileVersionInfoW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,ctypes.c_void_p]
    lib.VerQueryValueW.argtypes=[ctypes.c_void_p,W.LPCWSTR,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(W.UINT)]
    unused=W.DWORD();size=lib.GetFileVersionInfoSizeW(str(path),ctypes.byref(unused))
    if not size:raise UserError('后台准备：无法读取微信版本。')
    buf=ctypes.create_string_buffer(size)
    if not lib.GetFileVersionInfoW(str(path),0,size,buf):raise UserError('后台准备：读取微信版本失败。')
    ptr=ctypes.c_void_p();length=W.UINT()
    if not lib.VerQueryValueW(buf,'\\',ctypes.byref(ptr),ctypes.byref(length)) or length.value<52:raise UserError('后台准备：微信版本结构无效。')
    info=ctypes.cast(ptr,ctypes.POINTER(W.DWORD))
    if info[0]!=0xFEEF04BD:raise UserError('后台准备：微信版本签名无效。')
    return '.'.join(str(n) for n in (info[2]>>16,info[2]&65535,info[3]>>16,info[3]&65535))


class BackgroundWindows(NativeWindows):
    background=True

    def __init__(self):
        super().__init__();self.prepare_lock=threading.RLock()

    @contextmanager
    def dpi_context(self):
        self.u.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
        self.u.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
        previous=self.u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        if not previous:raise UserError('后台准备：无法设置本线程的坐标口径，未发送。')
        try:yield
        finally:self.u.SetThreadDpiAwarenessContext(previous)

    def _post(self,hwnd,message,wparam=0,lparam=0):
        self.u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];self.u.PostMessageW.restype=W.BOOL
        if not self.u.PostMessageW(hwnd,message,wparam,lparam):
            exc=UserError('后台投递失败，未改用前台发送。');exc.winerror=ctypes.get_last_error();raise exc

    def _native_target(self,control,bound):
        handle=int(control.NativeWindowHandle or 0)
        if handle and handle!=bound['hwnd']:
            if self.u.GetAncestor(handle,2)!=bound['hwnd']:raise UserError('后台控件身份不符，原生子窗口不属于绑定窗口。')
            return handle
        return 0

    def _post_key(self,hwnd,key):
        self.u.MapVirtualKeyW.argtypes=[W.UINT,W.UINT];self.u.MapVirtualKeyW.restype=W.UINT
        scan=int(self.u.MapVirtualKeyW(key,0))
        self._post(hwnd,0x100,key,(scan<<16)|1)
        self._post(hwnd,0x101,key,(scan<<16)|0xC0000001)

    def _click_control(self,control,bound,submit=False):
        rect=control.BoundingRectangle
        if rect.right<=rect.left or rect.bottom<=rect.top:raise UserError('后台控件不可用：当前无法定位按钮；不会恢复或切换前台。')
        point=W.POINT(round((rect.left+rect.right)/2),round((rect.top+rect.bottom)/2))
        if not self.u.ScreenToClient(bound['hwnd'],ctypes.byref(point)):raise UserError('后台投递失败：控件坐标转换失败。')
        # LPARAM client coordinates are signed 16-bit. Never wrap an offscreen
        # sentinel into an unrelated location and never move the system cursor.
        client=W.RECT()
        if not self.u.GetClientRect(bound['hwnd'],ctypes.byref(client)):raise UserError('后台控件不可用：无法读取客户区。')
        if not (0<=point.x<client.right and 0<=point.y<client.bottom and point.x<32768 and point.y<32768):raise UserError('后台控件不可用：控件位置超出客户区，未投递点击。')
        packed=(point.y<<16)|point.x
        if submit:self.trace('submit_background')
        self._post(bound['hwnd'],0x200,0,packed)
        self._post(bound['hwnd'],0x201,1,packed)
        self._post(bound['hwnd'],0x202,0,packed)

    def _write_control(self,control,bound,text,guard):
        native=self._native_target(control,bound)
        if native and ('EDIT' in (control.ClassName or '').upper()):
            # WM_SETTEXT to a verified native edit does not require keyboard
            # focus. Use synchronous system marshalling, never pointer PostMessage.
            self.u.SendMessageTimeoutW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM,W.UINT,W.UINT,ctypes.POINTER(ctypes.c_size_t)]
            self.u.SendMessageTimeoutW.restype=W.LPARAM
            buf=ctypes.create_unicode_buffer(text);result=ctypes.c_size_t()
            guard()
            if not self.u.SendMessageTimeoutW(native,0xC,0,ctypes.addressof(buf),2,2000,ctypes.byref(result)) or not result.value:raise UserError('后台投递失败：原生输入框拒绝文字，未发送。')
        else:
            # Qt custom input: only directed UTF-16 WM_CHAR. A posted mouse
            # click was observed activating real WeChat; never click to focus.
            raw=text.encode('utf-16-le')
            for offset in range(0,len(raw),2):
                guard();self._post(bound['hwnd'],0x102,int.from_bytes(raw[offset:offset+2],'little'),1)

    def _controls(self,auto,hwnd):
        root=auto.ControlFromHandle(hwnd);stack=[(root,0)];result=[];started=time.monotonic()
        while stack and len(result)<700 and time.monotonic()-started<2:
            control,depth=stack.pop();result.append(control)
            if depth>=18:continue
            aid=control.AutomationId or ''
            if 'chat_message_list' in aid or (control.ClassName or '').endswith('RecyclerListView'):continue
            stack.extend((c,depth+1) for c in reversed(control.GetChildren()))
        return result

    def _input(self,auto,bound):
        controls=self._controls(auto,bound['hwnd'])
        hits=[c for c in controls if (c.AutomationId or '').split('.')[-1]=='chat_input_field']
        details={'node_count':len(controls),'input_count':len(hits),
            'mmui_count':sum(isinstance(c.ClassName,str) and c.ClassName.startswith('mmui::') for c in controls)}
        if len(hits)!=1:
            code='input_ambiguous' if hits else 'tree_opaque' if not details['mmui_count'] and len(controls)<=3 else 'input_missing'
            exc=UserError({'tree_opaque':'后台控件不可用：微信仍仅返回窗口外壳，控件树未出现。',
                'input_missing':'后台控件不可用：控件树已返回，但没有聊天输入框。',
                'input_ambiguous':'后台控件不可用：找到多个聊天输入框，未选择或输入。'}[code])
            exc.probe_details=dict(details,input_failure=code);raise exc
        control=hits[0]
        raw=(control.Name or '').strip();expected=bound['title'].strip()
        if raw=='输入':
            # Observed on this user's independent filehelper window: this is an
            # editor label, not a contact name. Require a verified ownership chain
            # to the exact independent window instead of matching it as a name.
            try:self._verify_input_owner(control,bound)
            except UserError as exc:
                exc.probe_details=dict(getattr(exc,'probe_details',{}),**details,input_failure='input_owner_mismatch');raise
            return control
        # Qt's voice hint can end in spaces/newlines. Strip those before matching
        # its anchored suffix. Exact labels take priority (a real contact can be
        # named "语音输入"). Never accept a substring or an unknown suffix.
        name=raw if raw==expected else re.sub(r'(?:(?:长按|按住)鼠标\s*)?语音输入(?:文字)?$','',raw).strip()
        if name!=expected:
            # Display the labels locally for review, never include them in logs.
            exc=UserError('后台控件身份不符：输入框对象名称与所选窗口不一致，未发送。'
                +'\n所选窗口：'+repr(expected[:100])+'；输入框标签：'+repr(raw[:100]))
            exc.probe_details=dict(details,input_failure='input_identity_mismatch');raise exc
        return control

    def _verify_input_owner(self,control,bound):
        def blocked(code):
            exc=UserError('后台控件身份不符：通用输入框未通过独立窗口归属核验，未发送。')
            exc.probe_details={'owner_failure':code};return exc
        def verify_window():
            current=self.info(bound['hwnd'])
            if any(current.get(k)!=bound.get(k) for k in ('title','pid','exe')):raise blocked('native_window_changed')
            if Path(current['exe']).name.lower() not in ('weixin.exe','wechat.exe'):raise blocked('not_wechat_process')
        if bound['title'] in ('微信','Weixin','WeChat') or not bound.get('pid'):raise blocked('not_independent_window')
        verify_window()
        node=control
        try:
            for _ in range(32):
                if node is None:raise blocked('parent_chain_missing')
                if int(node.ProcessId or 0)!=bound['pid']:raise blocked('control_process_mismatch')
                handle=int(node.NativeWindowHandle or 0)
                if handle:
                    if handle==bound['hwnd']:
                        # UIA root Name is a provider label, not authoritative
                        # chat identity. Re-read native title/PID/path instead.
                        verify_window()
                        return
                    if self.u.GetAncestor(handle,2)!=bound['hwnd']:raise blocked('control_root_mismatch')
                node=node.GetParentControl()
        except UserError:raise
        except Exception:raise blocked('provider_unreadable') from None
        raise blocked('parent_chain_limit')

    def _value(self,control):
        for method in ('GetValuePattern','GetLegacyIAccessiblePattern'):
            try:
                pattern=getattr(control,method)()
                value=pattern.Value if pattern else None
                if isinstance(value,str):return value
            except Exception:pass
        raise UserError('后台控件不可用：无法回读输入框，未发送。')

    def _enable_tree(self,auto,bound):
        with self.prepare_lock:return self._enable_tree_unlocked(auto,bound)

    def _enable_tree_unlocked(self,auto,bound):
        try:return self._input(auto,bound)
        except UserError as exc:
            # An exposed but ambiguous/wrong-person input is not an accessibility
            # activation problem. Preserve that error; never modify the gate for it.
            if getattr(exc,'probe_details',{}).get('input_count',0):raise
        pid=bound['pid'];ps=ctypes.WinDLL('psapi',use_last_error=True)
        ps.EnumProcessModulesEx.argtypes=[W.HANDLE,ctypes.POINTER(W.HMODULE),W.DWORD,ctypes.POINTER(W.DWORD),W.DWORD]
        ps.GetModuleFileNameExW.argtypes=[W.HANDLE,W.HMODULE,W.LPWSTR,W.DWORD]
        handle=self.k.OpenProcess(0x438,False,pid)
        if not handle:raise UserError('后台准备：无法访问已绑定微信进程，未发送。')
        try:
            modules=(W.HMODULE*2048)();needed=W.DWORD();dll=None
            if not ps.EnumProcessModulesEx(handle,modules,ctypes.sizeof(modules),ctypes.byref(needed),3):raise UserError('后台准备：微信模块枚举失败。')
            for module in modules[:min(needed.value//ctypes.sizeof(W.HMODULE),2048)]:
                buf=ctypes.create_unicode_buffer(32768)
                if ps.GetModuleFileNameExW(handle,module,buf,len(buf)) and Path(buf.value).name.lower()=='weixin.dll':dll=(int(module),Path(buf.value));break
            if not dll:raise UserError('后台准备：未找到微信DLL。')
            base,path=dll;version=file_version(path)
            # Validate the exact supported binary's code reference and writable
            # section before touching its one-byte runtime flag.
            rva=validated_gate(path.read_bytes(),version)
            self.k.ReadProcessMemory.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
            self.k.WriteProcessMemory.argtypes=self.k.ReadProcessMemory.argtypes
            self.k.ReadProcessMemory.restype=W.BOOL;self.k.WriteProcessMemory.restype=W.BOOL
            value=ctypes.c_ubyte();done=ctypes.c_size_t();address=base+rva
            if not self.k.ReadProcessMemory(handle,address,ctypes.byref(value),1,ctypes.byref(done)) or done.value!=1 or value.value not in (0,1):raise UserError('后台准备：运行时标志校验失败，未修改进程。')
            original=value.value;value.value=1;changed=original!=1
            try:
                if changed and (not self.k.WriteProcessMemory(handle,address,ctypes.byref(value),1,ctypes.byref(done)) or done.value!=1):raise UserError('后台准备：无法启用微信控件树。')
                checked=ctypes.c_ubyte();done.value=0
                if not self.k.ReadProcessMemory(handle,address,ctypes.byref(checked),1,ctypes.byref(done)) or done.value!=1 or checked.value!=1:
                    raise UserError('后台准备：启用标志回读不一致，未发送。')
                last_error=None
                for _ in range(10):
                    try:return self._input(auto,bound)
                    except UserError as exc:
                        last_error=exc
                        if getattr(exc,'probe_details',{}).get('input_count',0):break
                        time.sleep(.2)
                raise last_error
            except Exception as exc:
                if changed:
                    value.value=original
                    if not self.k.WriteProcessMemory(handle,address,ctypes.byref(value),1,ctypes.byref(done)) or done.value!=1:raise UserError('后台准备失败且标志还原失败，请重启微信。') from None
                    check=ctypes.c_ubyte();done.value=0
                    if not self.k.ReadProcessMemory(handle,address,ctypes.byref(check),1,ctypes.byref(done)) or done.value!=1 or check.value!=original:raise UserError('后台准备失败且标志还原回读失败，请重启微信。') from None
                if isinstance(exc,UserError):
                    exc.probe_details=dict(getattr(exc,'probe_details',{}),gate_original=original,gate_changed=changed,gate_restored=changed)
                    exc.args=(str(exc)+(' 已还原本次标志变更；未发送。' if changed else ' 原标志未变更；未发送。'),)
                raise
        finally:self.k.CloseHandle(handle)

    def _commit(self,auto,bound,text,guard):
        buttons=[c for c in self._controls(auto,bound['hwnd']) if c.ControlTypeName=='ButtonControl' and (c.Name or '').strip() in ('发送','发送(S)','发送（S）','Send','Send(S)')]
        if len(buttons)!=1:raise UserError('后台控件不可用：未找到唯一发送按钮，未发送。')
        guard()
        if self._value(self._input(auto,bound)).replace('\r\n','\n')!=text.replace('\r\n','\n'):raise UserError('后台输入在提交前已变化，未发送。')
        button=buttons[0];native=self._native_target(button,bound)
        if native and 'BUTTON' in (button.ClassName or '').upper():
            self.u.GetParent.argtypes=[W.HWND];self.u.GetParent.restype=W.HWND
            self.u.GetDlgCtrlID.argtypes=[W.HWND];self.u.GetDlgCtrlID.restype=ctypes.c_int
            parent=self.u.GetParent(native);identifier=self.u.GetDlgCtrlID(native)
            if not parent or identifier<0:raise UserError('后台投递失败：发送按钮标识不可用。')
            self.trace('submit_background')
            self._post(parent,0x111,identifier&65535,native)
        else:
            # Directed Enter to this independently bound chat, after exact
            # readback. Posted mouse clicks can activate real Qt windows.
            self.trace('submit_background')
            self._post_key(bound['hwnd'],0x0D)
        self.trace('background_submitted')

    def _deliver_controls(self,auto,bound,text,guard):
        self.trace('background_prepare');guard();control=self._enable_tree(auto,bound)
        self.trace('background_read_draft');guard();existing=self._value(control)
        if existing and not (bound.get('reviewed') and existing.replace('\r\n','\n')==text.replace('\r\n','\n')):
            raise UserError('微信输入框已有草稿，已停止，保留你的文字。')
        if not existing:
            guard();self.trace('background_set_value',expected_length=len(text))
            self._write_control(control,bound,text,guard)
        for _ in range(10):
            guard();control=self._input(auto,bound);actual=self._value(control)
            if actual.replace('\r\n','\n')==text.replace('\r\n','\n'):break
            time.sleep(.08)
        else:raise UserError('后台输入回读不符，未发送；保留草稿供核对。')
        self.trace('verify_pasted_text',expected_length=len(text),input_length=len(actual))
        self._commit(auto,bound,text,guard)

    def deliver(self,bound,text,guard):
        import uiautomation as auto
        with self.dpi_context(),auto.UIAutomationInitializerInThread():self._deliver_controls(auto,bound,text,guard)

    def probe(self,window):
        """Prepare/access control patterns only. No text input or Invoke action."""
        import uiautomation as auto
        with self.dpi_context(),auto.UIAutomationInitializerInThread():
            control=self._enable_tree(auto,window);value=self._value(control)
            rect=control.BoundingRectangle
            writable=bool(self._native_target(control,window) or rect.right>rect.left)
            buttons=[c for c in self._controls(auto,window['hwnd']) if c.ControlTypeName=='ButtonControl' and (c.Name or '').strip() in ('发送','发送(S)','发送（S）','Send','Send(S)')]
            return {'readable':True,'writable':writable,'committable':len(buttons)==1,'has_draft':bool(value),
                'identity_mode':'window_ownership' if (control.Name or '').strip()=='输入' else 'input_label'}
