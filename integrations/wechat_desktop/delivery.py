"""审核/自动共用发送状态机；未知结果不重试，真实数据库回读才算已发送。"""
import difflib
import time
from core import UserError


class Delivery:
    def __init__(self,queue,store,sender,behavior,diagnostics=None):
        self.queue=queue;self.store=store;self.sender=sender;self.behavior=behavior;self.pending={}
        self.diagnostics=diagnostics
        self.unknown_people=set()

    def submit(self,job_id,binding,text,automatic=False,cancelled=lambda:False):
        with self.queue.lock:
            if cancelled():raise UserError('任务已取消。')
            job=self.queue.jobs[job_id];person=job['person']
            if not self.queue.valid(job) or job['status']!='ready':raise UserError('建议已失效，请重新生成。')
            if person in self.pending:raise UserError('此对象正在等待发送回执，请勿重复发送。')
            if person in self.unknown_people:raise UserError('此对象上次发送结果不明，请先核对微信，再点击“核对后恢复自动处理”。')
            if automatic and person in self.queue.manually_paused:raise UserError('此对象已人工接管，自动发送暂停；仍可编辑并人工确认发送。')
            if job.get('summary'):raise UserError('摘要不能作为回复发送。')
            if automatic and job['result'].get('needs_human'):raise UserError('此建议需要人工审核，未自动发送。')
            text=text.strip()
            if not text or len(text)>4000:raise UserError('发送正文须为1–4000字。')
            if automatic and text!=job['result']['reply'].strip():raise UserError('自动发送正文发生变化。')
            allowed,why=self.behavior.can_send(automatic)
            if not allowed:raise UserError(why)
            self.sender.check(person,binding)
            # Even memory-disabled contacts keep a minimal encrypted delivery key.
            # No reply body is written by this marker.
            previous=self.store.get('settings','delivery:'+job_id)
            if previous and (previous.get('state')!='not_sent' or automatic):raise UserError('此任务已尝试发送，自动重复发送已阻止；未发送的任务可修正条件后人工确认。')
            self.store.save('settings','delivery:'+job_id,{'state':'attempted','time':time.time()})
            self.behavior.reserve_send()
            attempt={'job':job_id,'person':person,'binding':dict(binding),'text':text,
                     'original':job['result']['reply'],'automatic':automatic,'started':time.time()}
            self.pending[person]=attempt;job['status']='sending';job['sent_text']=text
            self.sender.submission_started=None
            if self.diagnostics:self.diagnostics.event('send_attempt_reserved',person=person,job=job_id,mode='automatic' if automatic else 'reviewed')
        # Do not hold the queue lock across Windows/clipboard calls. The UI and
        # reader need it to process messages (including clipboard owner events).
        def guard():
            with self.queue.lock:
                if cancelled():raise UserError('任务已取消，未继续发送。')
                if self.pending.get(person) is not attempt:raise UserError('发送任务已结束或结果不明，未继续发送。')
                allowed,why=self.behavior.can_send(automatic)
                # The already reserved attempt is allowed to use the last slot.
                if why=='今日发送上限已达到':allowed=True
                if not allowed:raise UserError(why)
                if (not self.queue.running or job['epoch']!=self.queue.epoch or
                    job['revision']!=self.queue.revisions.get(person,0)):
                    raise UserError('任务已取消或有更新消息，未继续发送。')
        try:
            self.sender.send(person,binding,text,guard,reviewed=not automatic)
            with self.queue.lock:
                if self.pending.get(person) is attempt:
                    job['status']='awaiting_receipt';self.store.draft(job)
                    if self.diagnostics:self.diagnostics.event('send_waiting_receipt',person=person,job=job_id,stage='database_receipt')
        except Exception:
            with self.queue.lock:
                if self.pending.get(person) is not attempt:raise
                if self.sender.submission_started is False:
                    self.pending.pop(person,None);job['status']='ready';job.pop('sent_text',None);self.store.draft(job)
                    self.store.save('settings','delivery:'+job_id,{'state':'not_sent','time':time.time()})
                    if self.diagnostics:self.diagnostics.event('send_blocked_before_enter','WARNING',person,job_id,stage=getattr(self.sender,'last_stage','preflight'),status='not_sent')
                else:self.fail(person)
            raise

    def resume(self,person):
        with self.queue.lock:
            if person in self.pending:raise UserError('此对象正在等待发送回执，请稍后核对。')
            self.unknown_people.discard(person);self.queue.manually_paused.discard(person)

    def fail(self,person):
        attempt=self.pending.pop(person,None)
        if not attempt:return
        job=self.queue.jobs[attempt['job']];job['status']='unknown';self.queue.manually_paused.add(person);self.unknown_people.add(person)
        if self.diagnostics:self.diagnostics.event('send_result_unknown','ERROR',person,job['id'],stage='delivery',status='unknown')
        self.store.draft(job)
        self.store.save('settings','delivery:'+job['id'],{'state':'unknown','time':time.time()})

    def observe(self,person,rows):
        """Called on the reader thread before ReplyQueue.observe."""
        with self.queue.lock:
            attempt=self.pending.get(person)
            if not attempt:return []
            known=self.queue.seen.get(person,set())
            fresh=[m for m in rows if m['id'] not in known]
            outgoing=[m for m in fresh if m['role']=='me']
            matches=[m for m in outgoing if m.get('kind')==1 and m.get('text')==attempt['text']
                     and m['time']>=attempt['started']-2]
            # A simultaneous unrelated outgoing message is manual takeover.
            if len(matches)==1 and len(outgoing)==1:
                row=matches[0];known.add(row['id'])
                self.queue.seen[person]=known
                job=self.queue.jobs[attempt['job']];job['status']='sent'
                job['receipt']={'account':attempt['binding']['account'],'peer':attempt['binding']['username'],
                                'message_id':row['id'],'idempotency_key':job['id']}
                self.store.draft(job)
                self.store.remember(person,[row])
                self.store.save('settings','delivery:'+job['id'],{'state':'sent','message_id':row['id'],'time':time.time()})
                self.pending.pop(person);self.learn(attempt)
                if self.diagnostics:self.diagnostics.event('send_receipt_confirmed',person=person,job=job['id'],elapsed_ms=round((time.time()-attempt['started'])*1000))
                return [('sent',person,job['id'])]
            if outgoing or time.time()-attempt['started']>25:
                self.fail(person)
                return [('send_failed',person,'未获得唯一发送回执，已暂停此对象；请核对微信，程序不会重发。')]
            return []

    def expire(self):
        with self.queue.lock:
            expired=[]
            for person,a in list(self.pending.items()):
                if time.time()-a['started']>25:
                    self.fail(person);expired.append(('send_failed',person,'25秒内未确认发送结果，已暂停此对象；请到微信核对，勿重复发送。'))
            return expired

    def learn(self,attempt):
        if attempt['automatic'] or attempt['original'].strip()==attempt['text']:return
        person=attempt['person'];key='style:'+person
        if not self.store.get('settings','learn:'+person,True):return
        examples=self.store.get('settings',key,[])
        before=attempt['original'][:4000];after=attempt['text'][:4000]
        changes=[{'from':before[i:j],'to':after[k:l]} for op,i,j,k,l in
                 difflib.SequenceMatcher(None,before,after).get_opcodes() if op!='equal'][:20]
        examples.append({'suggested':before,'approved':after,'changes':changes,'time':time.time()})
        self.store.save('settings',key,examples[-8:])
