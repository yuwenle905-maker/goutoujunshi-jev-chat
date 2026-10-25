"""独立核心：加密存储、按对象隔离、消息去重和可撤销的回复任务。"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import re
import heapq
from pathlib import Path
import sqlite3
import threading
import time
import uuid

VERSION = '0.6.3'


class UserError(Exception):
    pass


class WindowsCipher:
    """DPAPI 当前 Windows 用户保护；不是对同一用户进程或管理员的隔离。"""
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    def _call(self, data: bytes, decrypt=False) -> bytes:
        buf = ctypes.create_string_buffer(data)
        source = self.Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
        dest = self.Blob()
        crypt = ctypes.WinDLL('crypt32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(self.Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(self.Blob)]
        fn.restype = wintypes.BOOL
        # UI_FORBIDDEN: key/config errors must never trigger an authentication UI.
        if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
            raise UserError('本机加密数据无法读取；请使用创建数据的 Windows 用户，不要删除原文件。')
        try:
            return ctypes.string_at(dest.data, dest.size)
        finally:
            kernel.LocalFree(ctypes.cast(dest.data, ctypes.c_void_p))

    def seal(self, value):
        return self._call(json.dumps(value, ensure_ascii=False).encode('utf-8'))

    def open(self, data):
        return json.loads(self._call(data, decrypt=True).decode('utf-8'))


class Store:
    def __init__(self, path, cipher=None):
        self.cipher = cipher or WindowsCipher()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript('''PRAGMA journal_mode=WAL;
        PRAGMA secure_delete=ON;
        CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY, data BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(person TEXT, id TEXT, sort REAL, data BLOB NOT NULL,
          PRIMARY KEY(person,id));
        CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY, data BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, person TEXT, status TEXT, data BLOB NOT NULL);
        CREATE INDEX IF NOT EXISTS messages_person_sort ON messages(person,sort);
        ''')
        self.db.commit()

    @staticmethod
    def person_id(account, peer):
        return hashlib.sha256(('wechat\0'+account+'\0'+peer).encode()).hexdigest()

    def save(self, table, key, value):
        assert table in ('objects','settings')
        with self.lock, self.db:
            self.db.execute(f'INSERT OR REPLACE INTO {table} VALUES (?,?)', (key, self.cipher.seal(value)))

    def get(self, table, key, default=None):
        assert table in ('objects','settings')
        with self.lock:
            row = self.db.execute(f'SELECT data FROM {table} WHERE id=?',(key,)).fetchone()
            return self.cipher.open(row[0]) if row else default

    def objects(self):
        with self.lock:
            return [(r[0],self.cipher.open(r[1])) for r in self.db.execute('SELECT id,data FROM objects')]

    def remember(self, person, messages):
        with self.lock, self.db:
            if not self.get('objects', person,{}).get('memory'):return 0
            added=0
            for m in messages:
                if self.db.execute('SELECT 1 FROM messages WHERE person=? AND id=?',(person,m['id'])).fetchone():continue
                self.db.execute('INSERT INTO messages VALUES (?,?,?,?)',
                                (person,m['id'],m['time'],self.cipher.seal(m)))
                added+=1
        return added

    def archive_batch(self,person,messages,checkpoint):
        # Save the data and resume cursor together. A failed batch is retried.
        with self.lock,self.db:
            if not self.get('objects',person,{}).get('memory'):return False
            for m in messages:
                if self.db.execute('SELECT 1 FROM messages WHERE person=? AND id=?',(person,m['id'])).fetchone():continue
                self.db.execute('INSERT INTO messages VALUES (?,?,?,?)',(person,m['id'],m['time'],self.cipher.seal(m)))
            key='archive:'+person
            positions=self.get('settings',key,{})
            positions.update(checkpoint)
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,self.cipher.seal(positions)))
            return True

    def history(self, person, limit=None):
        if not self.get('objects',person,{}).get('memory'):
            return []
        with self.lock:
            sql='SELECT data FROM messages WHERE person=? ORDER BY sort DESC,rowid DESC'
            rows=self.db.execute(sql+(' LIMIT ?' if limit is not None else ''),
                                 (person,limit) if limit is not None else (person,)).fetchall()
            return [self.cipher.open(r[0]) for r in reversed(rows)]

    def related(self,person,recent,limit=12,max_seconds=None,cancelled=lambda:False):
        """Search only this person's encrypted history; no plaintext search index."""
        query=' '.join(str(m.get('text','')) for m in recent[-4:] if m.get('kind')==1)[-400:]
        terms=set()
        for word in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{3,}',query.lower()):
            if re.fullmatch(r'[\u4e00-\u9fff]+',word):terms.update(word[i:i+2] for i in range(len(word)-1))
            else:terms.add(word)
        terms-=set(('哈哈','好的','你好','谢谢','什么','怎么','这个','那个','现在','今天','一下','可以'))
        if not terms:return []
        excluded={m['id'] for m in recent};best=[];cursor=9223372036854775807;started=time.monotonic();expired=False
        while True:
            if cancelled():return []
            if max_seconds is not None and time.monotonic()-started>=max_seconds:break
            with self.lock:
                if not self.get('objects',person,{}).get('memory'):return []
                rows=self.db.execute('SELECT rowid,id,data FROM messages WHERE person=? AND rowid<? ORDER BY rowid DESC LIMIT 200',(person,cursor)).fetchall()
            if not rows:break
            cursor=rows[-1][0]
            for row in rows:
                if cancelled():return []
                if max_seconds is not None and time.monotonic()-started>=max_seconds:expired=True;break
                number,identity=row[0],row[1]
                if identity in excluded:continue
                m=self.cipher.open(row[2])
                if identity in excluded or m.get('kind')!=1 or m.get('role') not in ('me','other'):continue
                text=str(m.get('text','')).lower();score=sum(term in text for term in terms)
                if score:
                    item=(score,m['time'],number,m)
                    if len(best)<limit:heapq.heappush(best,item)
                    elif item[:3]>best[0][:3]:heapq.heapreplace(best,item)
            if expired:break
        return [x[3] for x in sorted(best,reverse=True)]

    def count(self, person):
        with self.lock:
            return self.db.execute('SELECT COUNT(*) FROM messages WHERE person=?',(person,)).fetchone()[0]

    def clear_person(self, person):
        with self.lock, self.db:
            self.db.execute('DELETE FROM messages WHERE person=?',(person,))
            self.db.execute('DELETE FROM drafts WHERE person=?',(person,))
            self.db.execute('DELETE FROM settings WHERE id=?',('archive:'+person,))
            self.db.execute('DELETE FROM settings WHERE id=?',('relationship_review:'+person,))
        profile=self.get('objects',person,{})
        profile['summary']=''
        self.save('objects',person,profile)

    def draft(self, job):
        if not self.get('objects',job['person'],{}).get('memory'):
            return
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?,?)',
                            (job['id'],job['person'],job['status'],self.cipher.seal(job)))

    def close(self):
        with self.lock:
            self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            self.db.close()


class ReplyQueue:
    """进程重启绝不恢复待发送任务；取消/手动接管使旧模型结果失效。"""
    def __init__(self, store):
        self.store=store
        self.lock=threading.RLock()
        self.epoch=0
        self.revisions={}
        self.seen={}
        self.jobs={}
        self.running=False
        self.manually_paused=set()

    def start(self):
        with self.lock:
            self.epoch+=1
            self.running=True

    def stop(self):
        with self.lock:
            self.running=False
            self.epoch+=1
            for j in self.jobs.values():
                if j['status'] in ('thinking','ready'):
                    j['status']='cancelled'
                    self.store.draft(j)

    def observe(self, person, messages, initial=False):
        with self.lock:
            known=self.seen.setdefault(person,set())
            fresh=[m for m in messages if m['id'] not in known]
            known.update(m['id'] for m in fresh)
            if initial:
                return []
            if fresh:
                self.revisions[person]=self.revisions.get(person,0)+1
                if any(m['role']=='me' for m in fresh):
                    self.manually_paused.add(person)
                for j in self.jobs.values():
                    if j['person']==person and j['status'] in ('thinking','ready'):
                        j['status']='cancelled'
                        self.store.draft(j)
            return fresh

    def begin(self, person, trigger='manual'):
        with self.lock:
            if not self.running:
                raise UserError('请先开始监听。')
            if trigger!='manual' and person in self.manually_paused:
                raise UserError('你已手动接话，自动生成已暂停；请点“恢复此对象自动建议”。')
            for old in self.jobs.values():
                if old['person']==person and old['status'] in ('thinking','ready'):
                    old['status']='cancelled';self.store.draft(old)
            job={'id':uuid.uuid4().hex,'person':person,'epoch':self.epoch,
                 'revision':self.revisions.get(person,0),'status':'thinking','created':time.time()}
            self.jobs[job['id']]=job
            self.store.draft(job)
            return dict(job)

    def valid(self, job):
        return (self.running and job['epoch']==self.epoch and
                job['revision']==self.revisions.get(job['person'],0) and
                self.jobs.get(job['id'],{}).get('status') in ('thinking','ready'))

    def finish(self, job, result):
        with self.lock:
            if not self.valid(job):return False
            job=dict(job, status='ready', result=result)
            self.jobs[job['id']]=job
            self.store.draft(job)
            return True

    def send(self, job_id, bridge, expected_account, expected_peer):
        """为验证过的发送桥预留严格契约；此版本没有微信发送桥，不能自动发送。"""
        with self.lock:
            job=self.jobs[job_id]
            if not self.valid(job) or job['status']!='ready':
                raise UserError('此建议已过期或已取消；请重新生成。')
            if job['person'] in self.manually_paused:
                raise UserError('人工接管中，未发送。')
            result=job['result']
            if result.get('needs_human') or not result.get('reply'):
                raise UserError('此建议需要人工处理，未发送。')
            if not bridge.verified_identity_transport:
                raise UserError('微信发送前身份验证尚未接通；本版只生成建议，不操作微信输入框。')
            proof=bridge.preflight(expected_account,expected_peer)
            if proof.get('account')!=expected_account or proof.get('peer')!=expected_peer:
                raise UserError('收件人身份不匹配，已阻止发送。')
            job['status']='sending';self.store.draft(job)
            # Anything after this point is an uncertain delivery unless a matching
            # receipt exists. Never retry automatically on an unknown result.
            try:
                receipt=bridge.send(expected_account,expected_peer,result['reply'],job['id'],proof)
                if (receipt.get('account')!=expected_account or receipt.get('peer')!=expected_peer
                        or receipt.get('idempotency_key')!=job['id'] or not receipt.get('message_id')):
                    raise UserError('发送回执不完整；结果未知，不会自动重发。')
                job['status']='sent';job['receipt']=receipt
            except Exception:
                job['status']='unknown';self.store.draft(job)
                self.manually_paused.add(job['person'])
                raise
            self.store.draft(job)
            return receipt


class UnverifiedWechatSender:
    verified_identity_transport=False


def atomic_json(path, value, cipher):
    path=Path(path)
    temp=path.with_name(path.name+'.new')
    temp.write_bytes(cipher.seal(value))
    os.replace(temp,path)
