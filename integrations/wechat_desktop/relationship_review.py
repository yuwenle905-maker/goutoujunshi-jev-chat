"""Per-contact historical evidence sampling, without long DB locks or full-history claims."""
import time
from core import UserError


def review_history(store,person,current,cancelled=lambda:False):
    started=time.monotonic();sample=[]
    with store.lock:
        if not store.get('objects',person,{}).get('memory'):raise UserError('请先为此对象开启长期记忆。')
        count=store.count(person)
    offsets=sorted({max(0,round((count-12)*i/7)) for i in range(8)})
    for offset in offsets:
        if cancelled():raise UserError('关系分析已取消。')
        if time.monotonic()-started>5:break
        with store.lock:
            rows=store.db.execute('SELECT data FROM messages WHERE person=? ORDER BY sort,rowid LIMIT 12 OFFSET ?',(person,offset)).fetchall()
        for row in rows:
            if cancelled():raise UserError('关系分析已取消。')
            sample.append(store.cipher.open(row[0]))
    # Reserve half the evidence budget for recent conversation and half for
    # chronological samples. Never split an individual message into new facts.
    def fit(rows,budget):
        chosen=[];used=0
        for row in rows:
            if row.get('kind')!=1 or row.get('role') not in ('me','other'):continue
            size=len(str(row.get('text','')))
            if size and used+size<=budget:chosen.append(row);used+=size
        return chosen
    recent=fit(reversed(current[-200:]),12000)
    recent_ids={m['id'] for m in recent}
    older=[m for m in sample if m['id'] not in recent_ids]
    if older:
        # Interleave sampled windows so a large old message does not consume
        # the entire old-history budget before later sampled periods.
        older=sorted(older,key=lambda m:(m['time'],m.get('seq',0),m['id']))
        older=older[::2]+older[1::2]
    selected={m['id']:m for m in fit(older,12000)+recent}
    messages=sorted(selected.values(),key=lambda m:(m['time'],m.get('seq',0),m['id']))
    if not messages:raise UserError('此对象没有可用于关系分析的文字消息。')
    return messages,{'saved_count':count,'provided_count':len(messages),
        'first_time':messages[0]['time'],'last_time':messages[-1]['time'],
        'sampling':'已保存历史分时段抽样、当前最近文字与已确认摘要；不是全部聊天逐条分析'}
