"""会话代次、监听列表和行为策略；不依赖图形界面或微信。"""
import datetime as dt
import re
import threading
from core import UserError

SHANGHAI=dt.timezone(dt.timedelta(hours=8))
RELATIONSHIP_GOALS=['自然接话','重新破冰','拉近距离','轻松调情','暧昧升温','推进关系','主动邀约','确认心意','澄清关系','修复冲突','减少投入','结束联系']
RELATIONSHIP_STAGES=['刚认识','了解中','普通朋友','好朋友','暧昧','约会中','伴侣','关系冷淡','前任','断联','同事/同学']


def split_targets(value):
    values=[];seen=set()
    for item in re.split(r'[\s,，;；]+',value):
        item=item.strip()
        if item and item.casefold() not in seen:values.append(item);seen.add(item.casefold())
    if len(values)>20:raise UserError('指定联系人模式每次最多监听20人。')
    return values


class SessionGate:
    def __init__(self):self.value=0
    def next(self):self.value+=1;return self.value
    def accepts(self,token):return token==self.value


class Behavior:
    DEFAULT={'enabled':False,'auto_suggestions':True,'auto_send':False,
             'start':8,'end':23,'daily_limit':50,'default_stage':'了解中','default_goal':'自然接话'}
    def __init__(self,store):
        self.store=store;self.lock=threading.RLock()
        self.config=dict(self.DEFAULT,**store.get('settings','behavior',{}))
        self.config['enabled']=False;self.config['auto_send']=False

    def save(self,values):
        candidate=dict(self.config,**values)
        try:
            for key in ('start','end','daily_limit'):
                if isinstance(candidate[key],bool):raise ValueError()
                candidate[key]=int(candidate[key])
        except (ValueError,TypeError):raise UserError('工作时间和每日上限必须填写整数。') from None
        if not 0<=candidate['start']<=23 or not 0<=candidate['end']<=24:
            raise UserError('开始时间为0–23，结束时间为0–24；相同表示全天。')
        if not 0<=candidate['daily_limit']<=10000:raise UserError('每日上限为0–10000；0表示不限。')
        if not str(candidate['default_goal']).strip():raise UserError('默认目标不能为空。')
        with self.lock:
            self.config=candidate
            self.store.save('settings','behavior',candidate)

    def used(self,now=None):
        now=now or dt.datetime.now(SHANGHAI)
        if now.tzinfo:now=now.astimezone(SHANGHAI)
        row=self.store.get('settings','daily_suggestions',{})
        return row.get('count',0) if row.get('date')==now.date().isoformat() else 0

    def can_auto(self,now=None):
        now=now or dt.datetime.now(SHANGHAI)
        if now.tzinfo:now=now.astimezone(SHANGHAI)
        c=self.config
        if not c['enabled'] or not c['auto_suggestions']:return False,'自动建议已关闭'
        start,end=c['start'],c['end']
        inside=(True if start==end else (start<=now.hour<end if start<end else now.hour>=start or now.hour<end))
        if not inside:return False,'当前不在工作时间内（北京时间）'
        if c['daily_limit'] and self.used(now)>=c['daily_limit']:return False,'今日自动建议已达上限'
        return True,''

    def record_success(self,now=None):
        now=now or dt.datetime.now(SHANGHAI)
        if now.tzinfo:now=now.astimezone(SHANGHAI)
        with self.lock:
            self.store.save('settings','daily_suggestions',{'date':now.date().isoformat(),'count':self.used(now)+1})

    def sends_used(self):
        row=self.store.get('settings','daily_send_attempts',{})
        return row.get('count',0) if row.get('date')==dt.datetime.now(SHANGHAI).date().isoformat() else 0

    def can_send(self,automatic=False):
        c=self.config;hour=dt.datetime.now(SHANGHAI).hour
        if not c['enabled']:return False,'总开关已关闭'
        if automatic and not (c['auto_send'] and c['auto_suggestions']):return False,'自动发送已关闭'
        inside=c['start']==c['end'] or (c['start']<=hour<c['end'] if c['start']<c['end'] else hour>=c['start'] or hour<c['end'])
        if not inside:return False,'不在工作时间内'
        if c['daily_limit'] and self.sends_used()>=c['daily_limit']:return False,'今日发送上限已达到'
        return True,''

    def reserve_send(self):
        self.store.save('settings','daily_send_attempts',{'date':dt.datetime.now(SHANGHAI).date().isoformat(),'count':self.sends_used()+1})
