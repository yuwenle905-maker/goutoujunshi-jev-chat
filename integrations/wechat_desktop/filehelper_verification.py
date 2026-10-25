"""Fixed-scope integration test of the application's own production classes.

Only user-authorized filehelper / 后台发送测试. No model, foreground fallback,
arbitrary recipient/body parameters, automatic retry, or user settings changes.
"""
from pathlib import Path
import ctypes,json,sys,time
from ctypes import wintypes as W
from background_sender import BackgroundWindows
from window_sender import WindowSender
from wechat_reader import WechatReader
from core import Store,ReplyQueue,UserError
from runtime import Behavior
from delivery import Delivery


def _emit(value):
    if sys.stdout is not None:
        print(json.dumps(value,ensure_ascii=False),flush=True)

def run(report_path,send=False,continued=False,popup=True):
    RESOURCE_ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    HOME=Path(report_path).resolve().parent;HOME.mkdir(parents=True,exist_ok=True)
    REPORT=Path(report_path).resolve();LEDGER=HOME/'send-ledger.json'
    BODY='后台发送测试'
    attempt_count=1
    reader=None;store=None
    report={'recipient':'filehelper','real_wechat':True,'sent':False,'receipt_confirmed':False,'stages':[]}
    def save():REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def phase(text):report['phase']=text;save();_emit({'phase':text})
    def ledger(state):LEDGER.write_text(json.dumps({'state':state,'time':time.time(),'count':attempt_count}),encoding='utf-8')
    try:
        if LEDGER.exists():
            state=json.loads(LEDGER.read_text(encoding='utf-8'))['state']
            previous=json.loads(LEDGER.read_text(encoding='utf-8'))
            if state in ('attempted','unknown'):raise UserError('已有结果未知记录，禁止重复测试。')
            if state=='sent':
                if not continued or previous.get('count',1)>=4:raise UserError('固定测试预算已用完或未显式启动下一轮测试。')
                attempt_count=previous.get('count',1)+1
        backend=BackgroundWindows()
        matches=[w for w in backend.windows() if w['title']=='文件传输助手']
        if len(matches)!=1:raise UserError('未找到唯一文件传输助手独立窗口。')
        target=matches[0];phase('window_verified')
        capabilities=backend.probe(target)
        report['capabilities']=capabilities
        if capabilities['has_draft']:raise UserError('文件传输助手有草稿，未修改也未发送。')
        if not capabilities['writable'] or not capabilities['committable']:raise UserError('后台输入或发送按钮不可用。')
        phase('background_controls_verified')
        reader=WechatReader(RESOURCE_ROOT,Path.home()/'Documents/xwechat_files',HOME/'temporary')
        reader.progress=lambda message:None
        binding=reader.connect('filehelper',preferred_peer='filehelper')
        if binding['username']!='filehelper':raise UserError('内部收件人不是filehelper，未发送。')
        rows=reader.read_peer(binding,limit=200)
        report['baseline_count']=len(rows);phase('database_identity_verified')
        if not send:
            report['status']='preflight_only';save();_emit(report);return 0
        store=Store(HOME/'test.sqlite3');queue=ReplyQueue(store);queue.start()
        person=Store.person_id(binding['account'],'filehelper');queue.observe(person,rows,initial=True)
        # The fixed-scope ledger enforces the test budget; do not inherit the first
        # run's one-send quota from this isolated test database.
        policy=Behavior(store);policy.save({'enabled':True,'auto_suggestions':True,'auto_send':True,'start':0,'end':24,'daily_limit':0})
        def snapshot():
            point=W.POINT();backend.u.GetCursorPos(ctypes.byref(point))
            return {'foreground':int(backend.u.GetForegroundWindow() or 0),'cursor':[point.x,point.y],
                'clipboard_sequence':int(backend.u.GetClipboardSequenceNumber())}
        class Events:
            def event(self,event,*args,**fields):
                if event=='send_stage':report['stages'].append({'stage':fields.get('stage'),**snapshot()});save()
            def error(self,event,exc,**fields):
                report['transport_error']={'type':type(exc).__name__,'stage':fields.get('stage')};save()
        sender=WindowSender(backend,Events())
        added,blocked=sender.auto_bind({person:{'binding':binding}})
        if person not in added:raise UserError('固定测试联系人未能自动关联窗口，未发送。')
        report['automatic_binding_verified']=True
        delivery=Delivery(queue,store,sender,policy)
        job=queue.begin(person);queue.finish(job,{'reply':BODY,'reason':'user-authorized fixed-scope integration test','needs_human':False})
        if popup:
            import tkinter as tk
            from send_confirmation import SendConfirmation
            approved=[];root=tk.Tk();root.withdraw();started=time.monotonic()
            def approved_body(body,explicit):approved.append((body,explicit))
            dialog=SendConfirmation(root,'文件传输助手','固定内容后台发送自测',BODY,lambda:True,
                approved_body,lambda why:None,lambda:root.after(0,root.quit))
            root.after(30000,lambda:dialog.cancel('测试未确认，取消本轮。') if not dialog.completed else None)
            root.mainloop();root.destroy()
            report['approval_elapsed_seconds']=round(time.monotonic()-started,2)
            if not approved or approved[0][0]!=BODY:raise UserError('固定测试未获确认或正文已修改，本轮不发送。')
            report['approval_mode']='explicit' if approved[0][1] else 'idle_timeout'
            time.sleep(.25)
        before=snapshot();report['before']=before
        if before['foreground']==target['hwnd']:raise UserError('文件传输助手在前台，不能证明后台发送；本轮未发送。')
        allowed,why=policy.can_send(True)
        if not allowed:raise UserError(why)
        ledger('attempted')
        phase('authorized_send_started')
        try:delivery.submit(job['id'],binding,BODY,automatic=True)
        except Exception:
            state='not_sent' if sender.submission_started is False or (not report['stages'] and store.get('settings','delivery:'+job['id']) is None) else 'unknown'
            ledger(state)
            raise
        report['after_transport']=snapshot();report['sent']=True;phase('waiting_database_receipt')
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            current=reader.read_peer(binding,limit=200)
            events=delivery.observe(person,current)
            if queue.jobs[job['id']]['status']=='sent':
                report['receipt_confirmed']=True;break
            if queue.jobs[job['id']]['status']=='unknown':break
            time.sleep(.4)
        foregrounds=[s['foreground'] for s in report['stages']]+[report['after_transport']['foreground']]
        report['foreground_unchanged']=all(f==before['foreground'] for f in foregrounds)
        report['cursor_unchanged']=all(s['cursor']==before['cursor'] for s in report['stages']) and report['after_transport']['cursor']==before['cursor']
        report['clipboard_unchanged']=all(s['clipboard_sequence']==before['clipboard_sequence'] for s in report['stages']) and report['after_transport']['clipboard_sequence']==before['clipboard_sequence']
        report['status']='passed' if all(report[k] for k in ('receipt_confirmed','foreground_unchanged','cursor_unchanged','clipboard_unchanged')) else 'failed_or_unknown'
        ledger('sent' if report['receipt_confirmed'] else 'unknown')
        save();REPORT.with_name('result-'+str(attempt_count)+'.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        _emit({k:report[k] for k in ('status','receipt_confirmed','foreground_unchanged','cursor_unchanged','clipboard_unchanged','approval_mode','approval_elapsed_seconds') if k in report})
    except Exception as exc:
        report.update(status='blocked',exception_type=type(exc).__name__,error=str(exc) if isinstance(exc,UserError) else type(exc).__name__,
            owner_failure=getattr(exc,'probe_details',{}).get('owner_failure'))
        save();_emit(report);return 1
    finally:
        if reader:reader.close()
        if store:store.close()

    return 0 if report.get('status') in ('passed','preflight_only') else 1
