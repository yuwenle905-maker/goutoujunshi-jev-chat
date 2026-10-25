"""同一微信账号、多位聊天对象：会话刷新与按对象排队的界面控制器。"""
from collections import OrderedDict
import datetime as dt
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from core import Store,UserError
from runtime import Behavior,SessionGate,split_targets
from engine import Engine
from wechat_reader import WechatReader


class Controller:
    def setup_runtime(self):
        self.behavior=Behavior(self.store);self.gate=SessionGate()
        self.people={};self.latest_jobs={};self.pending_people=OrderedDict();self.pending_connection=None
        self.alias_timer=None;self.switch_timer=None;self.configuring=True;self.models_busy=False;self.model_request=0
        c=self.behavior.config
        self.enabled=tk.BooleanVar(value=False)
        self.auto_send=tk.BooleanVar(value=False)
        from window_sender import WindowSender
        from background_sender import BackgroundWindows
        from delivery import Delivery
        self.window_sender=WindowSender(backend=BackgroundWindows(),diagnostics=self.diagnostics)
        self.window_sender.backend.clipboard_owner=self.root.winfo_id()
        self.delivery=Delivery(self.reply_queue,self.store,self.window_sender,self.behavior,diagnostics=self.diagnostics)
        self.send_busy=False;self.window_candidates=[]
        self.send_window=tk.StringVar();self.send_status=tk.StringVar(value='人工审核模式；请选择对象并绑定独立聊天窗口。')
        self.transport_status=tk.StringVar(value='严格后台通道：不切前台、不使用鼠标键盘或剪贴板；不可用时停止，不降级。')
        self.learning=tk.BooleanVar(value=True)
        self.follow_messages=tk.BooleanVar(value=True)
        self.inbox_status=tk.StringVar(value='后台会同时读取全部已连接对象；新消息自动定位。')
        self.pending_views=OrderedDict();self.form_edits={};self.binding_busy=False
        self.last_edit_activity=0;self.edit_idle_seconds=2.5;self.dialog_busy=False;self.follow_target=None
        self.active_generation=None;self.model_workers={};self.generation_timeout=100
        self.review_task=None;self.review_workers={}
        self.confirmation_queue=OrderedDict();self.active_confirmation=None
        self.review_status=tk.StringVar(value='尚未分析；按对象保存，不自动修改关系设置或发送。')
        self.send_mode_status=tk.StringVar(value='人工审核模式：生成建议和绑定窗口不会自动发出，需点击上方“确认发送”。')
        self.last_send_status=tk.StringVar(value='发送状态：尚未尝试发送。可点“检查发送条件”。')
        self.log_revision=-1
        self.auto.set(c['auto_suggestions'])
        self.watch_mode=tk.StringVar(value='specified');self.account_choice=tk.StringVar(value='自动识别')
        self.hour_start=tk.StringVar(value=str(c['start']));self.hour_end=tk.StringVar(value=str(c['end']))
        self.daily_limit=tk.StringVar(value=str(c['daily_limit']))
        self.default_stage=tk.StringVar(value=c['default_stage']);self.default_goal=tk.StringVar(value=c['default_goal'])
        self.network=tk.StringVar(value=self.model_settings.get('network','直连 DeepSeek'))
        self.model_fetch_status=tk.StringVar(value='尚未获取模型，可直接输入模型名称。')
        self.conversation=tk.StringVar();self.chat_header=tk.StringVar(value='尚未连接联系人')
        self.new_message_status=tk.StringVar(value='尚未监听新消息')
        self.connection_status=tk.StringVar(value='尚未连接；首次扫描需要等待，进度显示在这里。')
        self.counter_status=tk.StringVar();self.policy_status=tk.StringVar(value='总开关已关闭')

    def install_runtime_hooks(self):
        self.root.bind_all('<KeyPress>',self.touch_editor,add='+')
        saved=self.store.get('settings','connection',{})
        if saved:
            self.data_path.set(saved.get('data_path',self.data_path.get()))
            self.alias.set(', '.join(saved.get('aliases',[])))
            self.watch_mode.set(saved.get('watch_mode','specified'))
            self.account_choice.set(saved.get('account','自动识别'))
        else:
            profiles=[p for _,p in self.store.objects() if isinstance(p,dict) and p.get('account') and (p.get('alias') or p.get('username'))]
            if profiles and len({p['account'] for p in profiles})==1 and len(profiles)<=20:
                self.alias.set(', '.join(dict.fromkeys(str(p.get('alias') or p['username']) for p in profiles)))
                self.account_choice.set(profiles[0].get('account_dir') or '自动识别')
                self.data_path.set(profiles[0].get('data_root') or self.data_path.get())
                self.report(f'已从原有档案恢复 {len(profiles)} 位对象，请核对列表后连接。未自动启动监听。')
        self.configuring=False
        self.alias.trace_add('write',self.alias_changed)
        self.refresh_accounts();self.refresh_counter()
        self.alias_widget.configure(state='normal' if self.watch_mode.get()=='specified' else 'disabled')

    def save_connection(self,quiet=False):
        try:
            aliases=split_targets(self.alias.get())
            self.store.save('settings','connection',{'data_path':self.data_path.get().strip(),'aliases':aliases,
                'watch_mode':self.watch_mode.get(),'account':self.account_choice.get()})
            if not quiet:self.report('已加密保存监听列表；下次启动会恢复，但不会自动开始监听或发送。')
        except Exception as exc:
            if quiet:raise
            self.show_error(exc)

    def import_web_settings(self):
        try:
            from settings_bridge import read_web_settings
            imported=read_web_settings(Path(os.environ['LOCALAPPDATA'])/'GoutouAutoChat/config.json')
            if self.enabled.get():self.stop()
            connection=imported['connection']
            if connection:
                self.configuring=True
                try:
                    self.data_path.set(connection['data_path']);self.alias.set(', '.join(connection['aliases']))
                    self.watch_mode.set(connection['watch_mode']);self.account_choice.set(connection['account'])
                    self.refresh_accounts();self.save_connection(quiet=True)
                finally:self.configuring=False
                self.alias_widget.configure(state='normal' if self.watch_mode.get()=='specified' else 'disabled')
            if imported['model']:
                self.key.set(imported['model']['key']);self.model.set(imported['model']['model']);self.save_model()
            self.report('已导入可兼容设置；没有导入自动发送开关，原有对象资料未覆盖。 '+imported['warning'])
        except Exception as exc:self.show_error(exc)

    def refresh_accounts(self):
        path=Path(self.data_path.get())
        try:names=sorted(p.name for p in path.iterdir() if (p/'db_storage').is_dir())
        except OSError:names=[]
        self.account_box.configure(values=['自动识别']+names)
        if self.account_choice.get() not in ['自动识别']+names:self.account_choice.set('自动识别')

    def alias_changed(self,*args):
        if self.configuring or self.watch_mode.get()!='specified':return
        if self.alias_timer:self.root.after_cancel(self.alias_timer)
        if self.monitor or self.pending_connection:
            self.invalidate('微信号已更改，正在等待输入完成后重新获取聊天…')
            if self.enabled.get():self.alias_timer=self.root.after(1000,self.connect)

    def mode_changed(self):
        self.alias_widget.configure(state='normal' if self.watch_mode.get()=='specified' else 'disabled')
        if self.enabled.get():self.connect()

    def invalidate(self,text):
        token=self.gate.next();self.stop_event.set()
        self.cancel_send_confirmations()
        self.cancel_generation(quiet=True,pump=False)
        with self.reply_queue.lock:
            for person in list(self.delivery.pending):self.delivery.fail(person)
        self.window_sender.bindings.clear()
        self.reply_queue.stop()
        self.pending_connection=None
        self.pending_people.clear();self.people.clear();self.latest_jobs.clear()
        self.pending_views.clear();self.form_edits.clear()
        self.person=None;self.binding=None;self.profile=None;self.messages=[];self.current_job=None
        self.ready_count=None
        self.conversation_box.configure(values=[]);self.conversation.set('')
        self.profile_box.configure(values=[]);self.connection_status.set(text)
        self.identity.set('未连接到当前输入的联系人');self.chat_header.set('等待重新获取聊天…')
        self.memory_status.set('尚未选择对象');self.job_status.set('旧建议已取消')
        self.new_message_status.set('等待新的监听基线；历史不会当作新消息')
        self.review_task=None
        for widget in (self.chat,self.reply,self.reason,self.notes,self.summary,self.review_text):self.put(widget,'')
        self.report(text)
        return token

    def connect(self):
        self.alias_timer=None
        try:
            aliases=split_targets(self.alias.get()) if self.watch_mode.get()=='specified' else []
            if not aliases and self.watch_mode.get()=='specified':raise UserError('请输入一个或多个微信号，以逗号分隔；无需指定微信号时请选择“最近私聊”。')
            self.save_connection(quiet=True)
            self.save_behavior(quiet=True)
            token=self.invalidate('正在切换监听对象；旧聊天和旧建议已清空。')
            self.enabled.set(True);self.behavior.save({'enabled':True})
            account=self.account_choice.get();account='' if account=='自动识别' else account
            self.pending_connection=(token,self.data_path.get().strip(),aliases,self.watch_mode.get()=='recent',account)
            self.wait_for_switch()
        except Exception as exc:self.show_error(exc)

    def wait_for_switch(self):
        self.switch_timer=None
        if not self.pending_connection or self.closing:return
        if self.monitor and self.monitor.is_alive():
            self.connection_status.set('正在等待旧读取任务停止；完成后自动连接，请勿反复点击。')
            self.switch_timer=self.root.after(100,self.wait_for_switch);return
        request=self.pending_connection;self.pending_connection=None
        if not self.gate.accepts(request[0]) or not self.enabled.get():return
        self.stop_event=threading.Event();self.reply_queue.start()
        self.report('正在核验同一登录账号与联系人；首次获取可能需要一分钟。切换输入后会自动刷新。')
        self.connection_status.set('正在扫描本机数据库读取材料；首次可能需要一分钟。')
        self.monitor=threading.Thread(target=self.monitor_loop,args=(*request,self.stop_event),daemon=True)
        self.monitor.start()

    def emit(self,token,*event):self.events.put(('session',token,event))

    def monitor_loop(self,token,data,aliases,recent,account,stop):
        reader=None;started=int(time.time());known=set();activity={};first_pass=True
        archives={};archive_next={};archive_failed=set()
        try:
            reader=WechatReader(self.resources,data,self.home/'temporary')
            reader.progress=lambda text:self.emit(token,'progress',text)
            bindings=reader.connect_targets(aliases,account,recent=recent)
            if stop.is_set():return
            while not stop.is_set():
                for raw in bindings:
                    if stop.is_set():break
                    binding={k:v for k,v in raw.items() if k!='activity'}
                    person=Store.person_id(binding['account'],binding['username'])
                    fingerprint=raw.get('activity')
                    # Identical texts within the same second may leave session
                    # metadata unchanged; always check stable message IDs.
                    rows=reader.read_peer(binding,limit=80 if recent else 200)
                    for delivery_event in self.delivery.observe(person,rows):self.emit(token,*delivery_event)
                    activity[person]=fingerprint
                    if stop.is_set():break
                    if person not in known:
                        self.reply_queue.observe(person,rows,initial=True);known.add(person)
                        self.emit(token,'person',binding,rows,person)
                        # New sessions appearing after startup may contain a real
                        # new incoming message. Startup history itself is baseline.
                        if recent and len(activity)>0 and not first_pass:
                            fresh=[m for m in rows if m['time']>=started]
                            if fresh:self.emit(token,'messages',person,rows,fresh)
                    else:
                        fresh=self.reply_queue.observe(person,rows)
                        # Always refresh the snapshot even if IDs did not change.
                        self.emit(token,'messages',person,rows,fresh)
                self.emit(token,'ready',len(known),recent)
                # At most one bounded history page per object in each polling pass.
                # Backfill never feeds the incoming-message/autoreply detector.
                for raw in bindings:
                    if stop.is_set():break
                    binding={k:v for k,v in raw.items() if k!='activity'}
                    person=Store.person_id(binding['account'],binding['username'])
                    if not self.store.get('objects',person,{}).get('memory'):
                        archives.pop(person,None);continue
                    if person in archive_failed or time.monotonic()<archive_next.get(person,0):continue
                    if person not in archives:
                        positions=self.store.get('settings','archive:'+person,{})
                        archives[person]=reader.history_batches(binding,positions)
                    try:
                        batch,checkpoint=next(archives[person])
                        if stop.is_set():break
                        if self.store.archive_batch(person,batch,checkpoint):self.emit(token,'archive',person,False)
                        else:archives.pop(person,None)
                    except StopIteration:
                        archives.pop(person,None);archive_next[person]=time.monotonic()+60
                        self.emit(token,'archive',person,True)
                    except Exception as exc:
                        archives.pop(person,None);archive_failed.add(person)
                        self.emit(token,'notice','某对象历史导入未完成，已保留已存数据和断点；重新连接可继续。'+(' '+str(exc) if isinstance(exc,UserError) else ''))
                if stop.wait(1):break
                first_pass=False
                if recent:bindings=reader.private_sessions()
        except Exception as exc:self.emit(token,'error',exc)
        finally:
            if reader:
                try:reader.close()
                except Exception:self.emit(token,'notice','临时数据库清理未完成；请检查数据目录 temporary。')
            if self.gate.accepts(token):self.reply_queue.stop()
            self.emit(token,'disconnected')

    def stop(self):
        self.pending_connection=None
        self.enabled.set(False);self.behavior.save({'enabled':False})
        self.invalidate('总开关已关闭：正在停止读取，已取消全部待生成建议。')
        self.policy_status.set('已关闭，不会自动调用模型')

    def toggle_enabled(self):
        if self.enabled.get():self.connect()
        else:self.stop()

    def save_behavior(self,quiet=False):
        try:
            if self.auto_send.get():self.auto.set(True)
            self.behavior.save({'enabled':self.enabled.get(),'auto_suggestions':self.auto.get(),
                'start':self.hour_start.get(),'end':self.hour_end.get(),'daily_limit':self.daily_limit.get(),
                'default_stage':self.default_stage.get().strip(),'default_goal':self.default_goal.get().strip(),
                'auto_send':self.auto_send.get()})
            for person,item in self.people.items():
                if not self.store.get('objects',person):
                    item['profile']['stage']=self.behavior.config['default_stage']
                    item['profile']['goal']=self.behavior.config['default_goal']
            if not self.auto.get():self.pending_people.clear()
            self.refresh_counter()
            if not quiet:self.report('行为设置已保存；'+('自动发送模式，仅向已绑定窗口的对象发送。' if self.auto_send.get() else '人工审核模式：编辑建议后点击确认发送。'))
            self.diagnostics.event('behavior_saved',mode='automatic' if self.auto_send.get() else 'manual_review',status='enabled' if self.enabled.get() else 'disabled')
        except Exception as exc:
            if quiet:raise
            self.show_error(exc)

    def refresh_counter(self):
        count=self.behavior.used();limit=self.behavior.config['daily_limit']
        self.counter_status.set(f'今日自动建议：{count}；发送尝试：{self.behavior.sends_used()} / '+(str(limit) if limit else '不限'))
        c=self.behavior.config
        self.policy_status.set(('已启用' if c['enabled'] else '已关闭')+f" · 北京时间 {c['start']}:00–{c['end']}:00 · "+('自动发送' if c['auto_send'] else '人工审核'))
        self.send_mode_status.set('弹窗自动发送：逐条显示联系人、来信和回复，5秒无操作默认确认；操作弹窗即停止倒计时。' if c['auto_send'] else '人工审核模式：先点击“确认发送”打开弹窗；5秒无操作默认确认，点击修改后须手动确认。')

    def register_person(self,binding,rows,person):
        c=self.behavior.config
        profile=self.store.get('objects',person,dict(binding,memory=False,stage=c['default_stage'],goal=c['default_goal'],notes='',summary=''))
        profile.setdefault('current_state','');profile.setdefault('assess_relationship',True)
        self.people[person]={'binding':binding,'messages':rows,'profile':profile,'new_count':0}
        self.view_keys=list(self.people)
        self.conversation_box.configure(values=[self.person_label(p) for p in self.view_keys])
        self.profile_box.configure(values=[self.person_label(p) for p in self.view_keys])
        self.store.remember(person,rows)
        if self.person is None:self.select_person(person)

    def person_label(self,person):
        b=self.people[person]['binding']
        return f"{b.get('remark') or b.get('nick_name') or '联系人'} · {b.get('alias') or b['username']}"

    def choose_person(self,event=None,widget=None):
        index=(widget or self.conversation_box).current()
        if 0<=index<len(self.view_keys):self.select_person(self.view_keys[index])

    def select_person(self,person):
        if person not in self.people:return
        self.follow_target=None
        if self.person and self.person in self.people:
            self.form_edits[self.person]={'memory':self.memory.get(),'stage':self.stage.get(),'goal':self.goal.get(),
                'current_state':self.relation_state.get(),'assess_relationship':self.assessment_enabled.get(),
                'notes':self.notes.get('1.0','end-1c'),'summary':self.summary.get('1.0','end-1c')}
            old=self.reply_queue.jobs.get(self.current_job)
            if old and old['person']==self.person and old['status']=='ready':old['edited_reply']=self.reply.get('1.0','end-1c')
        item=self.people[person]
        self.person=person;self.binding=item['binding'];self.profile=item['profile'];self.messages=item['messages']
        profile=dict(self.profile,**self.form_edits.get(person,{}))
        self.conversation.set(self.person_label(person))
        self.memory.set(profile.get('memory',False));self.stage.set(profile.get('stage','了解中'));self.goal.set(profile.get('goal','自然接话'))
        self.learning.set(self.store.get('settings','learn:'+person,True))
        self.send_status.set('此对象窗口已绑定' if person in self.window_sender.bindings else '此对象尚未绑定独立聊天窗口')
        self.last_send_status.set(self.people[person].get('last_send','发送状态：此对象尚未尝试发送。'))
        self.relation_state.set(profile.get('current_state',''));self.assessment_enabled.set(profile.get('assess_relationship',True))
        self.new_message_status.set(f"此对象本次监听检测到 {item.get('new_count',0)} 条新消息")
        self.put(self.notes,profile.get('notes',''));self.put(self.summary,profile.get('summary',''))
        b=self.binding
        self.identity.set(f"备注：{b.get('remark') or '无'} | 昵称：{b.get('nick_name') or '无'}\n微信号：{b.get('alias') or '无'} | 内部ID：{b['username']}\n本机账号：{b['account']}")
        self.chat_header.set('当前聊天：'+self.person_label(person)+'（北京时间；显示最近200条）')
        self.current_job=self.latest_jobs.get(person)
        self.render_messages();self.render_draft();self.update_memory()
        self.pending_views.pop(person,None);self.refresh_inbox();self.refresh_send_windows(quiet=True)

    def refresh_inbox(self):
        self.inbox_status.set(f'后台同时监听 {len(self.people)} 位对象 · 待查看 {len(self.pending_views)} 位 · 已绑定发送窗口 {len(self.window_sender.bindings)} 位'+(' · 正在跟随新消息' if self.follow_messages.get() else ' · 已关闭自动定位'))
        missing=[self.person_label(p) for p in self.people if p not in self.window_sender.bindings]
        status='严格后台通道：不切前台、不动鼠标、不使用剪贴板；失败不改走前台。'
        if missing:status+=' 未绑定：'+'、'.join(missing[:5])+('等' if len(missing)>5 else '')
        if self.person in self.delivery.unknown_people:status+=' 当前对象上次结果不明，核对微信后恢复。'
        elif self.person in self.reply_queue.manually_paused:status+=' 当前对象人工接管：自动暂停，人工确认仍可发送。'
        self.transport_status.set(status)

    def touch_editor(self,event):
        if self.is_editor(event.widget):self.last_edit_activity=time.monotonic()

    def is_editor(self,widget):
        try:return widget is not None and widget.winfo_class() in ('Text','Entry','TEntry','TCombobox') and str(widget.cget('state'))!='disabled'
        except (AttributeError,tk.TclError):return False

    def follow_blocked(self):
        return (self.binding_busy or self.dialog_busy or self.send_busy or
                (self.is_editor(self.root.focus_get()) and time.monotonic()-self.last_edit_activity<self.edit_idle_seconds))

    def follow_person(self,person):
        self.follow_target=person
        if person==self.person:return
        self.pending_views[person]=True;self.pending_views.move_to_end(person)
        self.pump_follow()
        self.refresh_inbox()

    def pump_follow(self):
        if not self.follow_messages.get() or self.follow_target not in self.pending_views or self.follow_blocked():return
        person=self.follow_target
        if person not in self.people:self.pending_views.pop(person,None);return
        # Focus alone is not evidence of ongoing editing. Preserve drafts via
        # select_person, then remove the old caret so further typing cannot land
        # in another person's reply accidentally.
        if self.is_editor(self.root.focus_get()):self.root.focus_set()
        self.select_person(person)
        self.diagnostics.event('follow_auto_selected',person=person,stage='inbox_follow')

    def view_latest_incoming(self):
        if self.pending_views:self.select_person(next(reversed(self.pending_views)))

    def render_messages(self):
        lines=[]
        for m in self.messages[-200:]:
            date=dt.datetime.fromtimestamp(m['time'],dt.timezone(dt.timedelta(hours=8))).strftime('%m-%d %H:%M:%S')
            role={'me':'我','other':'对方','unknown':'系统/身份未明'}[m['role']]
            body=str(m.get('text') or '') if m['kind']==1 else '['+str(m.get('type','未知消息'))+'：未转写]'
            lines.append(date+' '+role+'\n'+body+'\n')
        self.put(self.chat,'\n'.join(lines));self.chat.see('end')

    def render_draft(self):
        job=self.reply_queue.jobs.get(self.latest_jobs.get(self.person))
        if job and job['epoch']==self.reply_queue.epoch and job['status'] in ('error','cancelled','thinking'):
            self.current_job=None;self.put(self.reply,'');self.put(self.reason,job.get('error',''))
            self.job_status.set(job.get('error','正在准备生成…') if job['status']!='thinking' else '正在准备生成…')
            return
        if job and ((self.reply_queue.valid(job) and job['status']=='ready') or
                    (job['epoch']==self.reply_queue.epoch and job['status'] in ('sending','awaiting_receipt','sent','unknown'))):
            result=job['result'];self.current_job=job['id']
            assessment=result.get('assessment')
            explanation=result['reason']
            if isinstance(assessment,dict):
                explanation='\n'.join(label+'：'+str(assessment.get(key,'')) for key,label in
                    [('stage','关系判断'),('signals','依据'),('uncertainties','未知'),('next_step','下一步'),('boundaries','边界')])+'\n\n'+explanation
            self.put(self.reply,job.get('sent_text',job.get('edited_reply',result['reply'])));self.put(self.reason,explanation+'\n参考：'+'、'.join(result.get('references',[])))
            status={'sending':'正在发送','awaiting_receipt':'等待微信记录回执','sent':'已确认发送成功','unknown':'发送结果不明，请核对微信；不会自动重试'}
            self.job_status.set(status.get(job['status'],'需要人工审核' if result['needs_human'] else '建议已生成，请审核'))
            if job['status']!='ready':self.current_job=None
        else:
            self.current_job=None;self.put(self.reply,'');self.put(self.reason,'');self.job_status.set('等待此对象的新建议')

    def update_memory(self):
        if self.person:
            enabled=self.store.get('objects',self.person,{}).get('memory',False)
            self.memory_status.set(self.person_label(self.person)+' · '+('记忆已开启' if enabled else '长期记忆未启用')+f' · {self.store.count(self.person)} 条已保存')
            if hasattr(self,'review_text'):self.render_review()

    def render_review(self):
        saved=self.store.get('settings','relationship_review:'+self.person,{}) if self.person else {}
        body=saved.get('text','')
        if self.review_text.get('1.0','end-1c')!=body:self.put(self.review_text,body)
        task=self.review_task
        if task and task['person']==self.person:self.review_status.set('正在分析历史关系… '+str(int(time.monotonic()-task['started']))+' 秒；旧分析保留。')
        else:self.review_status.set(saved.get('status','尚未分析；按对象保存，不自动修改关系设置或发送。'))

    def analyze_relationship(self):
        try:
            person=self.person
            if not person or person not in self.people:raise UserError('请先选择已连接的聊天对象。')
            if not self.store.get('objects',person,{}).get('memory'):raise UserError('请先为此对象开启长期记忆。')
            if self.review_task:raise UserError('已有关系分析正在进行，可先取消后重试。')
            self.review_workers={k:t for k,t in self.review_workers.items() if t.is_alive()}
            if len(self.review_workers)>=2:raise UserError('旧关系分析请求尚未退出，请稍候重试。')
            key=self.key.get().strip();model=self.model.get().strip()
            if not key or not model:raise UserError('请先配置 API Key 和模型。')
            self.save_profile(quiet=True)
            profile=dict(self.people[person]['profile']);current=list(self.people[person]['messages'])
            task={'id':str(time.monotonic_ns()),'person':person,'started':time.monotonic(),'token':self.gate.value}
            self.review_task=task;self.render_review()
            engine=self.model_engine();engine.deadline=time.monotonic()+100
            engine.cancelled=lambda:self.closing or self.review_task is not task or not self.gate.accepts(task['token'])
            engine.diagnostics=self.diagnostics;engine.diag_person=person;engine.diag_job=task['id']
            def work():
                try:
                    from relationship_review import review_history
                    messages,scope=review_history(self.store,person,current,cancelled=engine.cancelled)
                    profile['_relationship_review']=True;profile['_review_scope']=scope
                    result=engine.generate(messages,profile,key,model,summary=True)
                    self.events.put(('relationship_review_done',task,result,scope))
                except Exception as exc:self.events.put(('relationship_review_error',task,exc))
            thread=threading.Thread(target=work,daemon=True);self.review_workers[task['id']]=thread;thread.start()
        except Exception as exc:self.show_error(exc)

    def cancel_review(self):
        self.review_task=None;self.render_review();self.review_status.set('关系分析已取消，保留上次结果；迟到结果不会保存。')

    def review_progress(self):
        task=self.review_task
        if not task:return
        if not self.gate.accepts(task['token']):self.cancel_review();return
        if time.monotonic()-task['started']>=100:
            self.cancel_review();self.review_status.set('关系分析超时（100秒），保留上次结果，可重试。');return
        if task['person']==self.person:self.render_review()

    def save_profile(self,quiet=False):
        if not self.person:
            if not quiet:self.show_error(UserError('请先连接并选择一个聊天对象。'))
            return
        self.profile.update(memory=self.memory.get(),stage=self.stage.get().strip(),goal=self.goal.get().strip(),notes=self.notes.get('1.0','end-1c'),
                            current_state=self.relation_state.get().strip(),assess_relationship=self.assessment_enabled.get())
        self.store.save('objects',self.person,self.profile)
        self.store.remember(self.person,self.messages);self.update_memory()
        if not quiet:self.report('已保存当前对象设置。其他对象使用各自档案；未设置的对象使用默认目标，不长期保存聊天。')

    def resume(self):
        if self.person:
            try:
                self.delivery.resume(self.person);self.refresh_inbox()
                self.diagnostics.event('auto_processing_resumed',person=self.person,stage='manual_resume')
                self.report('已恢复当前对象自动处理；仅下一条新消息触发，旧任务不会重发。')
            except Exception as exc:self.show_error(exc)

    def save_model(self):
        self.model_settings={'key':self.key.get().strip(),'model':self.model.get().strip(),'network':self.network.get(),
                             'models':list(self.model_box.cget('values'))}
        self.store.save('settings','model',self.model_settings)
        self.model_fetch_status.set('模型设置已加密保存。')
        self.report('模型设置已保存。')

    def model_engine(self):return Engine(self.resources/'skill',network='direct' if self.network.get()=='直连 DeepSeek' else 'system')

    def fetch_models(self):
        if self.models_busy:return
        key=self.key.get().strip()
        if not key:
            self.model_fetch_status.set('请先粘贴 DeepSeek 官方 API Key；不需要先点保存。');return
        self.models_busy=True;self.model_request+=1;request=self.model_request
        self.fetch_button.configure(state='disabled',text='获取中…')
        self.model_fetch_status.set('正在获取，最多等待15秒；结果或具体错误会显示在这里。')
        engine=self.model_engine()
        def work():
            try:self.events.put(('models_result',request,key,engine.models(key),None))
            except Exception as exc:self.events.put(('models_result',request,key,None,exc))
        threading.Thread(target=work,daemon=True).start()

    def queue_auto(self,person):
        allowed,why=self.behavior.can_auto()
        if not allowed:self.report(why+'；已读取消息，未调用模型。');return
        if person in self.reply_queue.manually_paused:
            self.set_send_result(person,'此对象已暂停，请核对微信后点击“恢复此对象自动处理”。')
            self.diagnostics.event('auto_generation_blocked','WARNING',person=person,stage='incoming_queue',reason='manual_takeover_or_unknown_delivery')
            return
        self.pending_people[person]=True;self.pump_auto()

    def pump_auto(self):
        if self.model_busy:return
        while self.pending_people:
            person,_=self.pending_people.popitem(last=False)
            if person not in self.people or person in self.reply_queue.manually_paused:continue
            if not self.behavior.can_auto()[0]:self.pending_people.clear();return
            self.generate(automatic=True,person=person);return

    def generate(self,summary=False,automatic=False,person=None):
        try:
            person=person or self.person
            if not person or person not in self.people:raise UserError('请先连接并选择聊天对象。')
            if not self.reply_queue.running or not self.enabled.get():raise UserError('功能已关闭，请先打开总开关或连接。')
            if self.model_busy:
                if automatic:self.pending_people[person]=True;return
                raise UserError('已有模型请求正在处理；其他对象按顺序排队，不会混用上下文。')
            self.model_workers={k:t for k,t in self.model_workers.items() if t.is_alive()}
            if len(self.model_workers)>=2:raise UserError('旧网络请求仍未退出，已停止新增请求；请稍候或重启程序后重试。')
            if automatic and not self.behavior.can_auto()[0]:return
            if not automatic:self.save_profile(quiet=True)
            item=self.people[person];profile=dict(item['profile'])
            profile['_style_examples']=self.store.get('settings','style:'+person,[]) if self.store.get('settings','learn:'+person,True) else []
            remembered=self.store.get('objects',person,{}).get('memory',False)
            if not remembered:profile['summary']=''
            saved=self.store.history(person,limit=200) if remembered else []
            by_id={m['id']:m for m in saved+item['messages']}
            messages=sorted(by_id.values(),key=lambda m:(m['time'],m.get('seq',0),m['id']))
            if summary:
                if not saved:raise UserError('请先为此对象开启记忆并保存聊天。')
                messages=saved
            key=self.key.get().strip();model=self.model.get().strip()
            if not key or not model:raise UserError('请先填写 API Key 并获取/选择模型。')
            engine=self.model_engine();job=self.reply_queue.begin(person,trigger='incoming' if automatic else 'manual')
            job['summary']=summary
            self.latest_jobs[person]=job['id'];self.model_busy=True
            self.active_generation={'id':job['id'],'person':person,'started':time.monotonic(),'stage':'准备聊天与历史'}
            engine.deadline=time.monotonic()+self.generation_timeout
            engine.cancelled=lambda:not self.reply_queue.valid(job)
            engine.diagnostics=self.diagnostics;engine.diag_person=person;engine.diag_job=job['id']
            engine.progress=lambda stage:self.events.put(('model_stage',job['id'],stage))
            if person==self.person:self.current_job=job['id'];self.job_status.set('正在生成…');self.put(self.reply,'');self.put(self.reason,'')
            def work():
                try:
                    self.events.put(('model_stage',job['id'],'检索相关历史（最多5秒）'))
                    if remembered and not summary:profile['_relevant_history']=self.store.related(person,messages,max_seconds=5,cancelled=engine.cancelled)
                    if not self.reply_queue.valid(job):return
                    self.events.put(('model_stage',job['id'],'等待 DeepSeek 返回（接口最多90秒）'))
                    result=engine.generate(messages,profile,key,model,summary=summary)
                    if self.reply_queue.finish(job,result):self.events.put(('generated',job['id'],result,summary,automatic))
                except Exception as exc:self.events.put(('model_error',job,exc))
                finally:self.events.put(('model_done',job['id']))
            thread=threading.Thread(target=work,daemon=True);self.model_workers[job['id']]=thread;thread.start()
            self.report('正在为 '+self.person_label(person)+' 生成建议；未向模型提交其他对象的聊天。')
        except Exception as exc:
            if automatic:self.report(str(exc) if isinstance(exc,UserError) else type(exc).__name__)
            else:self.show_error(exc)

    def cancel_generation(self,quiet=False,pump=True):
        active=self.active_generation
        if not active:return
        job=self.reply_queue.jobs.get(active['id'])
        with self.reply_queue.lock:
            if job and job['status'] in ('thinking','ready'):
                job['status']='cancelled';job['error']='已取消生成，可重新生成。';self.store.draft(job)
        self.active_generation=None;self.model_busy=False
        if job and job['person']==self.person:self.render_draft()
        if not quiet:self.report('已取消生成，迟到结果不会显示或发送；可点击重新生成。')
        if pump:self.pump_auto()

    def generation_progress(self):
        active=self.active_generation
        if not active:return
        job=self.reply_queue.jobs.get(active['id'])
        if not job:return
        elapsed=int(time.monotonic()-active['started'])
        if elapsed>=self.generation_timeout:
            error=UserError('生成超时（总计100秒），已结束等待。可检查网络或模型后重新生成；不会自动发送。')
            self.handle_event(('model_error',dict(job),error))
            self.handle_event(('model_done',job['id']))
            return
        if job['status']=='thinking' and job['person']==self.person:
            self.job_status.set(f"{active['stage']} · 已用 {elapsed} 秒 / 总上限100秒")

    def copy_reply(self):
        try:
            job=self.reply_queue.jobs.get(self.current_job)
            if not job or not self.reply_queue.valid(job) or job['status']!='ready':raise UserError('没有当前对象的有效建议，请重新生成。')
            if job['person']!=self.person:raise UserError('建议对象不匹配，已阻止复制。')
            text=self.reply.get('1.0','end-1c').strip()
            if not text:raise UserError('回复为空。')
            self.root.clipboard_clear();self.root.clipboard_append(text)
            self.report('已复制 '+self.person_label(self.person)+' 的建议，请自行核对微信收件人后发送。')
        except Exception as exc:self.show_error(exc)

    def refresh_send_windows(self,quiet=False):
        try:
            self.window_candidates=self.window_sender.candidates()
            self.window_box.configure(values=[f"{w['title']} · 窗口 {w['hwnd']}" for w in self.window_candidates])
            self.send_window.set('')
            if self.person:
                binding=self.people[self.person]['binding']
                names={binding.get(k) for k in ('remark','nick_name','alias','username')}-{None,''}
                # Auto-select a candidate, but do not treat a title as proof of ID.
                matches=[i for i,w in enumerate(self.window_candidates) if w['title'] in names and w['title'] not in ('微信','Weixin','WeChat')]
                if len(matches)==1:self.window_box.current(matches[0])
                bound=self.window_sender.bindings.get(self.person)
                if bound:
                    try:self.window_sender.check(self.person,binding);self.send_status.set('此对象发送窗口已绑定，可审核发送。');return
                    except Exception:self.window_sender.bindings.pop(self.person,None)
                self.send_status.set('发送尚未设置：'+('已找到同名独立窗口，点“设置发送窗口”核对并关联。' if len(matches)==1 else '先将此微信会话打开为独立窗口，再点“设置发送窗口”。'))
        except Exception as exc:
            if quiet:self.send_status.set('微信窗口读取失败，请点“刷新微信窗口”重试。')
            else:self.show_error(exc)

    def bind_send_window(self,after_bind=None):
        try:
            if self.binding_busy:raise UserError('正在绑定窗口，请稍候。')
            if not self.person:raise UserError('请先连接并选择对象。')
            i=self.window_box.current()
            if not 0<=i<len(self.window_candidates):raise UserError('请刷新并选择此对象的独立聊天窗口。')
            person=self.person;binding=dict(self.binding);window=dict(self.window_candidates[i]);token=self.gate.value
            from tkinter import messagebox
            self.dialog_busy=True
            try:
                confirmed=messagebox.askokcancel('绑定后台发送窗口',f"当前对象：{self.person_label(person)}\n本机账号：{binding['account']}\n窗口：{window['title']}\n\n请先在微信资料页核对微信号。窗口标题本身不能证明微信号，确认由你将此独立窗口关联到当前对象。\n后台发送不需要鼠标定位、不占用剪贴板；首次使用会验证并启用当前微信实例的控件树，不重启、不修改安装文件。控件不可用则停止，不改走前台。"+('\n绑定后继续本次已审核发送；新来信会取消旧回复。' if after_bind else ''),parent=self.root)
                if confirmed:self.binding_busy=True
            finally:self.dialog_busy=False
            if not confirmed:return
            self.send_status.set('正在关联此对象的后台发送窗口，不需要移动鼠标…')
            def capture():
                try:
                    if not self.gate.accepts(token) or person not in self.people:raise UserError('连接已切换，请重新绑定。')
                    current=self.window_sender.backend.info(window['hwnd'])
                    if any(current[k]!=window[k] for k in ('title','pid','exe')):raise UserError('窗口已改变，请刷新列表。')
                    point=[max(1,window['width']//2),max(1,window['height']*3//4)]
                    self.window_sender.bind(person,binding,window,point)
                    self.refresh_inbox()
                    self.diagnostics.event('send_window_bound',person=person,stage='binding',bound_hwnd=window['hwnd'],pid=window['pid'])
                    self.send_status.set('已关联后台窗口：'+self.person_label(person)+'；仅本次连接有效，无需保持前台。首次发送将检查后台控件能力。')
                    if after_bind and self.person==person:self.root.after(0,after_bind)
                except Exception as exc:self.show_error(exc)
                finally:self.binding_busy=False
            self.root.after(0,capture)
        except Exception as exc:self.show_error(exc)

    def probe_background(self):
        try:
            i=self.window_box.current()
            if not 0<=i<len(self.window_candidates):raise UserError('先刷新并选择一个独立微信聊天窗口。')
            window=dict(self.window_candidates[i])
            if window['title'] in ('微信','Weixin','WeChat'):raise UserError('请选择独立聊天窗口，不选择微信主窗口。')
            self.send_status.set('正在准备并检查后台控件；不输入、不发送，不切换微信前台。')
            def work():
                try:self.events.put(('background_probe_done',self.window_sender.backend.probe(window),None))
                except Exception as exc:self.events.put(('background_probe_done',None,exc))
            threading.Thread(target=work,daemon=True).start()
        except Exception as exc:self.show_error(exc)

    def save_learning(self):
        if self.person:
            self.store.save('settings','learn:'+self.person,self.learning.get())
            self.report('已保存此对象的审核修改学习开关。示例只用于该对象，可随时清空。')

    def clear_learning(self):
        if self.person:
            self.store.save('settings','style:'+self.person,[]);self.report('已清除此对象的回复风格示例。')

    def approve_send(self):
        try:
            self.diagnostics.event('approve_clicked',person=self.person,job=self.current_job,stage='manual_review')
            job=self.reply_queue.jobs.get(self.current_job)
            if not job or job['person']!=self.person:raise UserError('请先生成当前对象的回复。')
            if not self.reply_queue.valid(job):raise UserError('回复已失效，请按最新消息重新生成。')
            text=self.reply.get('1.0','end-1c').strip()
            def send_reviewed():
                if not self.reply_queue.valid(job):self.report('绑定期间聊天或回复已变化，请重新审核最新回复。');return
                self.diagnostics.event('approve_confirmed',person=job['person'],job=job['id'],stage='manual_review')
                self.submit_send(job['id'],text=text)
            try:self.window_sender.check(self.person,self.binding)
            except UserError:
                self.setup_send_window(after_bind=send_reviewed)
                return
            send_reviewed()
        except Exception as exc:self.show_error(exc)

    def setup_send_window(self,after_bind=None):
        selected=self.window_box.current()
        chosen=self.window_candidates[selected] if 0<=selected<len(self.window_candidates) else None
        self.refresh_send_windows(quiet=True)
        if chosen and self.person:
            binding=self.people[self.person]['binding']
            names={binding.get(k) for k in ('remark','nick_name','alias','username')}-{None,''}
            for i,window in enumerate(self.window_candidates):
                if window==chosen and window['title'] in names:self.window_box.current(i);break
        if self.window_box.current()<0:
            from tkinter import messagebox
            messagebox.showinfo('先设置此对象的发送窗口',
                '读取聊天与发送是两个独立步骤。\n\n1. 在微信里将这个联系人的会话打开为独立聊天窗口（可双击会话尝试）。\n2. 回到这里点击“设置发送窗口”。\n3. 核对微信号后关联窗口，不需要移动鼠标或保持前台。\n\n聊天记录仍会同时监听，不需要为读取逐个绑定窗口。',parent=self.root)
            return
        self.bind_send_window(after_bind=after_bind)

    def queue_send_confirmation(self,job_id,text,automatic):
        if self.active_confirmation and self.active_confirmation['job']==job_id:return
        self.confirmation_queue[job_id]=(text,automatic)
        self.pump_send_confirmations()

    def cancel_send_confirmations(self):
        self.confirmation_queue.clear()
        if self.active_confirmation:self.active_confirmation['dialog'].cancel('连接停止或已切换，取消本条。')

    def pump_send_confirmations(self):
        if self.closing or self.active_confirmation:return
        while self.confirmation_queue:
            job_id,(text,automatic)=self.confirmation_queue.popitem(last=False)
            job=self.reply_queue.jobs.get(job_id)
            if not job or not self.reply_queue.valid(job) or job['person'] not in self.people:continue
            from send_confirmation import SendConfirmation
            person=job['person'];token=self.gate.value
            incoming=next((m.get('text','') for m in reversed(self.people[person]['messages']) if m.get('role')=='other' and m.get('kind')==1),'')
            def valid(job=job,automatic=automatic,token=token):
                return (not self.closing and self.gate.accepts(token) and self.enabled.get() and self.reply_queue.valid(job)
                    and (not automatic or self.auto_send.get()))
            def closed():
                self.active_confirmation=None
                if not self.closing:self.root.after(0,self.pump_send_confirmations)
            def send(body,explicit,job_id=job_id,person=person,automatic=automatic):
                self.diagnostics.event('send_popup_confirmed',person=person,job=job_id,mode='explicit' if explicit else 'idle_timeout')
                self.submit_send(job_id,text=body,automatic=automatic and not explicit,confirmed=True)
            def cancel(reason,job=job,person=person):
                with self.reply_queue.lock:
                    if job['status']=='ready':job['status']='cancelled';job['error']=reason;self.store.draft(job)
                self.set_send_result(person,reason)
                self.diagnostics.event('send_popup_cancelled',person=person,job=job['id'],stage='confirmation')
            dialog=SendConfirmation(self.root,self.person_label(person),incoming,text,valid,send,cancel,closed,
                allow_timeout=not job['result'].get('needs_human',False))
            self.active_confirmation={'job':job_id,'dialog':dialog}
            self.set_send_result(person,'等待发送弹窗确认；无操作5秒默认发送，操作后停止倒计时。')
            self.diagnostics.event('send_popup_shown',person=person,job=job_id,stage='confirmation')
            return

    def submit_send(self,job_id,text=None,automatic=False,confirmed=False):
        try:
            self.diagnostics.event('send_dispatch_requested',job=job_id,mode='automatic' if automatic else 'reviewed',stage='preflight')
            job=self.reply_queue.jobs.get(job_id)
            if not job or not self.reply_queue.valid(job):return
            if job.get('summary'):raise UserError('摘要不能作为回复发送。')
            if automatic and (not self.auto_send.get() or not self.behavior.can_send(True)[0]):return
            if self.send_busy:
                self.root.after(500,lambda:self.submit_send(job_id,text=text,automatic=automatic,confirmed=confirmed));return
            person=job['person'];binding=dict(self.people[person]['binding'])
            if person in self.delivery.pending:raise UserError('此对象正在等待发送回执，请勿重复发送。')
            if person in self.delivery.unknown_people:raise UserError('此对象上次发送结果不明，请核对微信后恢复。')
            self.window_sender.check(person,binding)
            text=text if text is not None else job['result']['reply']
            if not confirmed:self.queue_send_confirmation(job_id,text,automatic);return
            self.send_busy=True;self.send_status.set('正在通过后台控件发送；不占用鼠标键盘或剪贴板。')
            self.set_send_result(person,'正在发送，完成后等待此联系人记录回执。')
            token=self.gate.value
            self.window_sender.last_stage='delivery_preflight'
            def work():
                try:
                    self.delivery.submit(job_id,binding,text,automatic,cancelled=lambda:self.closing or not self.gate.accepts(token))
                    self.emit(token,'notice','已操作发送，正在等待此联系人聊天记录回执。')
                except Exception as exc:
                    self.diagnostics.error('send_worker_error',exc,person=person,job=job_id,stage=self.window_sender.last_stage)
                    self.emit(token,'send_failed',person,str(exc) if isinstance(exc,UserError) else '发送失败（'+type(exc).__name__+'），请检查诊断日志及微信草稿。')
                finally:self.send_busy=False;self.events.put(('send_done',))
            threading.Thread(target=work,daemon=True).start()
        except Exception as exc:
            self.diagnostics.error('send_preflight_blocked',exc,job=job_id,stage='preflight')
            failed_job=self.reply_queue.jobs.get(job_id)
            if failed_job:self.set_send_result(failed_job['person'],str(exc) if isinstance(exc,UserError) else '发送前检查异常，请看诊断日志。')
            if automatic:self.report(str(exc) if isinstance(exc,UserError) else '自动发送未完成，请检查发送窗口绑定。')
            else:self.show_error(exc)

    def set_send_result(self,person,text):
        if person in self.people:self.people[person]['last_send']='发送状态：'+text
        if person==self.person:self.last_send_status.set('发送状态：'+text)
        self.refresh_inbox()

    def check_send_conditions(self):
        from tkinter import messagebox
        checks=[]
        def check(label,action):
            try:action();checks.append('通过：'+label)
            except Exception as exc:
                checks.append('未通过：'+label+' — '+(str(exc) if isinstance(exc,UserError) else type(exc).__name__))
                self.diagnostics.error('send_condition_blocked',exc,person=self.person,stage=label)
        def policy():
            allowed,why=self.behavior.can_send(False)
            if not allowed:raise UserError(why)
        def target():
            if not self.person:raise UserError('请先连接并选择联系人。')
            self.window_sender.check(self.person,self.binding)
        def reply():
            job=self.reply_queue.jobs.get(self.current_job)
            if not job or not self.reply_queue.valid(job):raise UserError('请先生成当前对象的回复。')
            if self.person in self.delivery.unknown_people:raise UserError('此对象上次结果不明；请核对微信后恢复。')
            if self.person in self.delivery.pending:raise UserError('此对象仍在等待发送回执。')
        check('总开关、工作时间和发送额度',policy);check('联系人发送窗口',target);check('有效回复与人工接管状态',reply)
        def clipboard():
            if not getattr(self.window_sender.backend,'background',False):self.window_sender.backend.clipboard()
        check('后台通道不使用剪贴板' if getattr(self.window_sender.backend,'background',False) else '剪贴板可用且为文字',clipboard)
        self.diagnostics.event('send_conditions_checked',person=self.person,stage='conditions',mode='automatic' if self.auto_send.get() else 'manual_review')
        result=('自动发送模式' if self.auto_send.get() else '人工审核模式：需要点击确认发送')+'\n\n'+'\n'.join(checks)+'\n\n此检查不会激活窗口、输入或发送消息；不代表微信输入回读和实际发送已成功。'
        self.last_send_status.set('发送条件检查完成：'+str(sum(s.startswith('未通过') for s in checks))+' 项未通过；详情已显示并记入日志。')
        messagebox.showinfo('发送条件检查（未发送）',result,parent=self.root)

    def refresh_logs(self):
        if not hasattr(self,'log_text'):return
        text=self.diagnostics.view_text()
        if self.diagnostics.file_error:text='日志文件不可写，当前事件仅保留内存；可导出诊断包。\n'+text
        self.put(self.log_text,text);self.log_text.see('end');self.log_revision=self.diagnostics.count

    def open_log_folder(self):
        try:os.startfile(str(self.diagnostics.folder))
        except Exception as exc:self.show_error(exc)

    def clear_logs(self):
        try:
            self.diagnostics.clear();self.refresh_logs()
            self.report('日志已清空，开始记录本次测试；聊天、记忆、设置和已导出诊断包不受影响。')
        except Exception as exc:self.show_error(exc)

    def export_diagnostics(self):
        from tkinter import filedialog
        path=filedialog.asksaveasfilename(parent=self.root,title='导出不含聊天正文的诊断包',defaultextension='.zip',initialfile='狗头微信助手-诊断日志.zip',filetypes=[('诊断包','*.zip')])
        if not path:return
        try:self.diagnostics.export(path);self.report('诊断包已导出，不含聊天正文、微信号或API Key。')
        except Exception as exc:self.show_error(exc)

    def callback_exception(self,kind,exc,tb):
        self.diagnostics.error('tk_callback_error',exc,stage='tk_callback')
        self.report('界面操作异常（'+kind.__name__+'），详情已写入诊断日志。')

    def tick(self):
        try:
            self.pump_follow()
            if self.book.select()==str(self.tabs['诊断日志']) and self.log_revision!=self.diagnostics.count:self.refresh_logs()
            self.generation_progress()
            self.review_progress()
            for expired in self.delivery.expire():self.handle_event(expired)
            for _ in range(100):
                try:event=self.events.get_nowait()
                except queue.Empty:break
                if self.closing:continue
                if event[0]=='session':
                    if not self.gate.accepts(event[1]):continue
                    event=event[2]
                self.handle_event(event)
        except Exception as exc:
            self.diagnostics.error('ui_event_error',exc,stage='event_loop')
            # An unexpected callback must not permanently kill all model/chat updates.
            self.report('界面事件处理失败（'+type(exc).__name__+'），将继续接收后续更新。')
        finally:
            if not self.closing:self.root.after(150,self.tick)

    def handle_event(self,event):
        kind=event[0]
        if kind=='person':self.register_person(*event[1:])
        elif kind=='messages':
            _,person,rows,fresh=event
            if person not in self.people:return
            changed=self.people[person]['messages']!=rows
            self.people[person]['messages']=rows
            if person==self.person and changed:self.messages=rows;self.render_messages()
            if not fresh:return
            self.people[person]['new_count']+=len(fresh)
            if person==self.person:self.new_message_status.set(f"此对象本次检测到 {self.people[person]['new_count']} 条新消息 · 最近检测 "+dt.datetime.now().strftime('%H:%M:%S'))
            self.latest_jobs.pop(person,None)
            if person==self.person:self.render_draft()
            try:self.store.remember(person,fresh)
            except Exception as exc:self.report(str(exc))
            if person==self.person:self.update_memory()
            if any(m['role']=='me' for m in fresh):
                with self.reply_queue.lock:self.reply_queue.manually_paused.add(person)
                self.diagnostics.event('manual_takeover_detected',person=person,stage='incoming_queue',count=sum(m['role']=='me' for m in fresh))
                self.pending_people.pop(person,None)
                self.report(self.person_label(person)+'：检测到你手动接话，暂停此对象自动建议。')
            elif any(m['role']=='other' and m['kind']==1 for m in fresh):
                self.follow_person(person);self.queue_auto(person)
            self.refresh_inbox()
        elif kind=='progress':self.connection_status.set(event[1])
        elif kind=='archive':
            _,person,complete=event
            if person==self.person:
                self.update_memory()
                self.memory_status.set(self.memory_status.get()+(' · 本轮历史扫描完成' if complete else ' · 正在分批合并历史，可继续使用'))
        elif kind=='ready':
            if getattr(self,'ready_count',None)!=event[1]:self.report(f'已连接 {event[1]} 位聊天对象，历史已加载，正在持续检测新消息。')
            self.ready_count=event[1]
            self.refresh_counter()
            self.connection_status.set(f'正在监听 {event[1]} 位对象；本轮读取完成于 '+dt.datetime.now().strftime('%H:%M:%S')+'，约每1秒检查一次变化。')
        elif kind=='models_result':
            _,request,key,names,error=event
            if request!=self.model_request:return
            self.models_busy=False;self.fetch_button.configure(state='normal',text='获取可用模型')
            if key!=self.key.get().strip():self.model_fetch_status.set('获取期间 API Key 已修改，请重新获取。');return
            if error:self.model_fetch_status.set(str(error) if isinstance(error,UserError) else '获取失败（'+type(error).__name__+'），可切换网络方式重试。');return
            self.model_box.configure(values=names)
            if self.model.get() not in names:self.model.set('deepseek-v4-pro' if 'deepseek-v4-pro' in names else names[0])
            self.save_model();self.model_fetch_status.set(f'成功获取 {len(names)} 个模型，列表和选择已保存。')
        elif kind=='background_probe_done':
            result,error=event[1:]
            if error:
                self.diagnostics.error('background_probe_error',error,stage='background_prepare')
                self.send_status.set(str(error) if isinstance(error,UserError) else '后台检查失败（'+type(error).__name__+'），详情见日志。')
            else:
                self.send_status.set(('通用“输入”标签已通过进程和独立窗口归属核验；' if result.get('identity_mode')=='window_ownership' else '')+'后台控件：输入可读；文字投递'+('可用' if result['writable'] else '不可用')+'；发送按钮定位'+('可用' if result['committable'] else '不可用/尚未出现')+'；'+('已有草稿，发送将保护原文。' if result['has_draft'] else '当前无草稿。')+' 此检查未发送消息，也不代表真实投递已验证。')
                self.diagnostics.event('background_probe_done',stage='background_prepare',status='ready' if result['writable'] and result['committable'] else 'partial',reason='writable='+str(result['writable'])+',button='+str(result['committable'])+',draft='+str(result['has_draft']))
        elif kind in ('relationship_review_done','relationship_review_error'):
            task=event[1]
            if self.review_task is not task or not self.gate.accepts(task['token']):return
            self.review_task=None;person=task['person']
            if kind=='relationship_review_error':
                exc=event[2];self.diagnostics.error('relationship_review_error',exc,person=person,job=task['id'],stage='relationship_review')
                text=str(exc) if isinstance(exc,UserError) else '关系分析失败（'+type(exc).__name__+'），旧结果保留。'
                if person==self.person:self.review_status.set(text)
                self.report(text);return
            if not self.store.get('objects',person,{}).get('memory'):return
            result,scope=event[2:]
            date=dt.datetime.now().strftime('%Y-%m-%d %H:%M')
            status=f"分析于 {date} · 已保存 {scope['saved_count']} 条，本次提供 {scope['provided_count']} 条文字证据；分时段抽样，非全量逐条分析。"
            self.store.save('settings','relationship_review:'+person,{'text':status+'\n\n'+result['reply'],'status':status,'scope':scope,'created':time.time()})
            self.diagnostics.event('relationship_review_saved',person=person,job=task['id'],count=scope['provided_count'],status='saved')
            if person==self.person:self.render_review()
            self.report('关系分析与推进建议已按对象加密保存；没有更改阶段、目标或发送消息。')
        elif kind=='generated':
            _,job_id,result,summary,automatic=event
            job=self.reply_queue.jobs.get(job_id)
            if not job or not self.reply_queue.valid(job):return
            self.diagnostics.event('reply_ready',person=job['person'],job=job_id,mode='automatic' if self.auto_send.get() else 'manual_review',status='needs_review' if result.get('needs_human') else 'ready')
            if automatic:
                if not self.behavior.can_auto()[0]:return
                self.behavior.record_success();self.refresh_counter()
                self.follow_person(job['person'])
            if job['person']==self.person:
                if summary:self.put(self.summary,result['reply']);self.book.select(self.tabs['长期记忆']);self.report('摘要草稿已生成，需核对并保存。')
                else:self.render_draft()
            else:self.report(self.person_label(job['person'])+' 的建议已生成，可在会话列表中查看。')
            if automatic and not summary and self.auto_send.get():self.submit_send(job_id,automatic=True)
        elif kind=='sent':
            _,person,job_id=event
            if person==self.person:self.job_status.set('已由此联系人聊天记录确认发送成功');self.current_job=None
            self.send_status.set('发送成功；已核对联系人记录回执。');self.report('发送成功：'+self.person_label(person));self.refresh_counter()
            self.set_send_result(person,'已核对本机发送记录。')
        elif kind=='send_failed':
            _,person,text=event
            self.send_status.set(text);self.report(text)
            if person==self.person:self.job_status.set(text)
            self.set_send_result(person,text);self.diagnostics.event('send_failed_shown','ERROR',person=person,stage='result',status='failed')
        elif kind=='send_done':self.refresh_counter()
        elif kind=='model_stage':
            if self.active_generation and self.active_generation['id']==event[1]:self.active_generation['stage']=event[2]
        elif kind=='model_done':
            if self.active_generation and self.active_generation['id']==event[1]:
                self.active_generation=None;self.model_busy=False;self.pump_auto()
        elif kind=='model_error':
            job,exc=event[1:]
            self.diagnostics.error('model_generation_error',exc,person=job['person'],job=job['id'],stage='model_request')
            if self.reply_queue.valid(job):
                text=str(exc) if isinstance(exc,UserError) else '模型请求失败（'+type(exc).__name__+'），请重新生成。'
                with self.reply_queue.lock:
                    live=self.reply_queue.jobs[job['id']];live['status']='error';live['error']=text;self.store.draft(live)
                if job['person']==self.person:self.render_draft()
                self.report(text)
        elif kind=='error':
            text=str(event[1]) if isinstance(event[1],UserError) else '微信读取失败（'+type(event[1]).__name__+'），请重新连接。'
            self.connection_status.set(text);self.report(text)
        elif kind=='notice':self.report(event[1])
        elif kind=='disconnected':self.enabled.set(False);self.behavior.config['enabled']=False;self.policy_status.set('监听已结束；请重新连接')

    def close(self):
        if self.closing:return
        self.closing=True;self.pending_connection=None;self.gate.next();self.stop_event.set();self.reply_queue.stop()
        self.cancel_send_confirmations()
        if self.alias_timer:self.root.after_cancel(self.alias_timer)
        if self.switch_timer:self.root.after_cancel(self.switch_timer)
        self.report('正在清理只读任务与临时数据库，请稍候…');self._finish_close()

    def _finish_close(self):
        if self.send_busy:self.root.after(200,self._finish_close);return
        if self.monitor and self.monitor.is_alive():self.root.after(200,self._finish_close);return
        self.diagnostics.event('app_closed',status='closed');self.diagnostics.close()
        self.store.close();self.root.destroy()
