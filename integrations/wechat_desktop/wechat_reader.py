"""只读微信本地数据库；不导入第三方发送/UI/热激活模块，不缓存解密密钥。"""
import hashlib
import importlib.util
import logging
from pathlib import Path
import re
import sys
import tempfile
import types
from core import UserError


def load_reader(resource_root):
    name='_goutou_readonly_db'
    if name in sys.modules:return sys.modules[name]
    # The upstream db.py imports only this logger from its package. Never load
    # upstream __init__, which also imports senders and process-memory writers.
    package=types.ModuleType('wechatauto');package.__path__=[]
    logger=types.ModuleType('wechatauto.logger')
    logger.wxlog=logging.getLogger('goutou.readonly')
    logger.wxlog.addHandler(logging.NullHandler());logger.wxlog.propagate=False
    sys.modules['wechatauto']=package;sys.modules['wechatauto.logger']=logger
    spec=importlib.util.spec_from_file_location(name,Path(resource_root)/'vendor/wechat_db.py')
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


class WechatReader:
    def __init__(self, resource_root, data_root, scratch_root):
        self.module=load_reader(resource_root)
        self.data=Path(data_root)
        if not self.data.is_dir():raise UserError('未找到微信数据目录，请选择包含各账号文件夹的 xwechat_files 目录。')
        Path(scratch_root).mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='session-',dir=scratch_root)
        self.obj=None
        self.binding=None
        self.peer=None
        self.snapshots={}
        self.progress=lambda text:None
        base=self.module.WeChatDB
        class ReadOnly(base):
            def _save_keys(self,*args,**kwargs):pass
            def _stable_key_dirs(self):return []
            def _stable_key_file(self,*args,**kwargs):return None
            def _refresh_db_files(self):pass
            def _auto_diagnose_key_failure(self,*args,**kwargs):
                raise UserError('微信本地数据库读取权限已失效，请停止后重新连接；未写入密钥。')
            def get_self_info(self):
                for rel,path,_ in self._db_files:
                    if Path(path).name!='contact.db':continue
                    conn=self._open(rel)
                    try:
                        row=conn.execute('SELECT username,nick_name,remark FROM contact WHERE username=? LIMIT 1',(self.wxid,)).fetchone()
                        if row:return dict(row)
                    finally:conn.close()
                return {'username':self.wxid,'nick_name':'','remark':''}
        self.cls=ReadOnly

    def make(self, account):
        obj=object.__new__(self.cls)
        obj.db_dir=str(self.data);obj.account=account;obj.account_dir=str(self.data/account)
        obj.workdir=str(Path(self.temp.name)/account);Path(obj.workdir).mkdir(parents=True,exist_ok=True)
        obj.keys_file=str(Path(self.temp.name)/'keys-not-written.json')
        obj._keys={};obj.master_key=None;obj.cfg_dword=None
        obj._db_files=obj._collect_db_files()
        return obj

    def connect(self, alias, preferred_account='', preferred_peer=''):
        bindings=self.connect_targets([alias],preferred_account)
        self.peer=bindings[0]['username'];self.binding=bindings[0]
        if preferred_peer and self.peer!=preferred_peer:raise UserError('联系人内部身份已变化，未连接。')
        return dict(self.binding)

    def connect_targets(self, aliases, preferred_account='', recent=False):
        aliases=list(dict.fromkeys(a.strip().casefold() for a in aliases if a.strip()))
        if not aliases and not recent:raise UserError('请输入一个或多个准确微信号，或选择“最近私聊”模式。')
        accounts=sorted(p.name for p in self.data.iterdir() if (p/'db_storage').is_dir())
        if preferred_account:accounts=[a for a in accounts if a==preferred_account]
        if not accounts:raise UserError('此目录没有可用微信账号。')
        seed=self.make(accounts[0])
        candidates=seed._all_key_candidates()
        self.progress('扫描完成，正在核验联系人与本机账号…')
        matches=[]
        for account in accounts:
            obj=self.make(account)
            all_files=obj._db_files
            obj._db_files=[r for r in all_files if Path(r[1]).name=='contact.db']
            obj._keys=obj._keys_from_candidates(candidates)
            for rel,_,_ in obj._db_files:
                if rel not in obj._keys:continue
                conn=obj._open(rel)
                try:
                    contacts=[];valid=True
                    if recent:
                        matches.append((obj,contacts,all_files))
                    else:
                        for alias in aliases:
                            rows=conn.execute('SELECT username,alias,nick_name,remark FROM contact WHERE alias=? COLLATE NOCASE OR username=? COLLATE NOCASE',(alias,alias)).fetchall()
                            if len(rows)!=1 or '@chatroom' in rows[0]['username']:
                                valid=False;break
                            contacts.append(dict(rows[0]))
                        if valid:matches.append((obj,contacts,all_files))
                finally:conn.close()
        if len(matches)!=1:
            raise UserError('未能唯一核实登录账号及所有联系人。请检查微信号/数据目录；如有多个可读取账号，请在“本机账号”中选择一个。未按昵称猜测绑定。')
        obj,contacts,files=matches[0]
        obj._db_files=[r for r in files if re.match(r'^message[\\/]message_\d+\.db$',r[0]) or Path(r[1]).name in ('contact.db','session.db')]
        obj._keys.update(obj._keys_from_candidates(candidates))
        self.progress('联系人已核验，正在读取消息分库；完成后自动显示聊天。')
        own=obj.get_self_info()['username']
        if not own:raise UserError('无法核实本机微信账号，未绑定。')
        self.obj=obj;self.account={'account_dir':obj.account,'account':own,'data_root':str(self.data)}
        self.contacts={}
        result=[dict(c,**self.account) for c in contacts]
        if recent:result=self.private_sessions()
        self.contacts.update({c['username']:c for c in result})
        return result

    def private_sessions(self):
        obj=self.obj
        if obj is None:raise UserError('尚未核实微信账号。')
        session_files=[r for r in obj._db_files if Path(r[1]).name=='session.db']
        if not session_files or any(r[0] not in obj._keys for r in session_files):raise UserError('无法读取会话列表；未启用最近私聊模式。')
        sessions=obj.get_sessions(limit=300)
        result=[]
        for s in sessions:
            peer=s['username']
            if ('@' in peer or peer==self.account['account'] or peer.startswith('gh_') or
                    peer in {'filehelper','weixin','fmessage','newsapp','medianote','floatbottle','qmessage','qqmail','tmessage','weibo','brandsessionholder','notifymessage','notification_messages'}):continue
            contact=getattr(self,'contacts',{}).get(peer)
            if contact is None:
                for rel,path,_ in obj._db_files:
                    if Path(path).name!='contact.db':continue
                    conn=obj._open(rel)
                    try:
                        rows=conn.execute('SELECT username,alias,nick_name,remark FROM contact WHERE username=?',(peer,)).fetchall()
                        if len(rows)==1:contact=dict(rows[0],**self.account)
                    finally:conn.close()
                    break
            if contact:
                result.append(dict(contact,activity=(s.get('last_time'),s.get('unread'),s.get('summary'))))
            if len(result)>=100:break
        return result

    def read(self):
        return self.read_peer(self.binding)

    def read_peer(self,binding,limit=None):
        if self.obj is None:raise UserError('尚未连接微信。')
        if binding['account']!=self.account['account']:raise UserError('读取账号不匹配，已停止。')
        peer=binding['username']
        obj=self.obj;table='Msg_'+hashlib.md5(peer.encode()).hexdigest()
        # Skip unchanged shards without decoding every historical row each poll.
        stamp=[]
        for rel,path,_ in obj._db_files:
            if not re.match(r'^message[\\/]message_\d+\.db$',rel):continue
            for target in (Path(path),Path(str(path)+'-wal')):
                try:
                    stat=target.stat();stamp.append((str(target),stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size))
                except FileNotFoundError:stamp.append((str(target),None))
        cache_key=(peer,limit);stamp=tuple(stamp)
        cached=self.snapshots.get(cache_key)
        if cached and cached[0]==stamp:return cached[1]
        out=[];shards=0
        for rel,_,_ in obj._db_files:
            if not re.match(r'^message[\\/]message_\d+\.db$',rel):continue
            shards+=1
            if rel not in obj._keys:raise UserError('有消息分库无法读取，已暂停；不会将不完整记录当作完整上下文。')
            conn=obj._open(rel)
            try:
                if not conn.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone():continue
                mapping=obj._name2id_map(conn)
                suffix=' ORDER BY sort_seq DESC,local_id DESC LIMIT ?' if limit else ' ORDER BY local_id'
                rows=conn.execute('SELECT local_id,local_type,server_id,real_sender_id,create_time,message_content,packed_info_data,sort_seq FROM '+table+suffix,(limit,) if limit else ()).fetchall()
                for row in rows:
                    sender=mapping.get(int(row['real_sender_id']), '')
                    role='me' if sender==binding['account'] else ('other' if sender==peer else 'unknown')
                    item=obj._export_row(row,self.module.MSG_TYPE_NAMES)
                    kind=int(item['type_code']) & 0xffffffff
                    # server_id may change from 0 to its final value after sync;
                    # local_id stays stable inside this person's shard table.
                    identity=f"{rel}:{row['local_id']}"
                    out.append({'id':identity,'time':int(row['create_time']),'seq':int(row['sort_seq'] or 0),
                                'role':role,'kind':kind,'text':item.get('content') or '',
                                'sender':sender,'type':str(item['type'])})
            finally:conn.close()
        if not shards:raise UserError('未发现本地消息分库，不能开始监听。')
        result=sorted(out,key=lambda m:(m['time'],m['seq'],m['id']))
        result=result[-limit:] if limit else result
        self.snapshots[cache_key]=(stamp,result)
        return result

    def history_batches(self,binding,positions=None,batch_size=500):
        """Keyset pagination; close each DB before yielding so polling stays usable."""
        if self.obj is None or binding['account']!=self.account['account']:raise UserError('历史读取账号不匹配。')
        obj=self.obj;peer=binding['username'];table='Msg_'+hashlib.md5(peer.encode()).hexdigest()
        for rel,_,_ in obj._db_files:
            if not re.match(r'^message[\\/]message_\d+\.db$',rel):continue
            if rel not in obj._keys:raise UserError('历史分库无法读取；导入未完成，已保留已保存的数据与进度。')
            after=int((positions or {}).get(rel,0));upper=None
            while True:
                conn=obj._open(rel)
                try:
                    if not conn.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone():break
                    if upper is None:upper=conn.execute('SELECT MAX(local_id) FROM '+table).fetchone()[0] or 0
                    rows=conn.execute('SELECT * FROM '+table+' WHERE local_id>? AND local_id<=? ORDER BY local_id LIMIT ?',
                                      (after,upper,batch_size)).fetchall()
                    mapping=obj._name2id_map(conn);batch=[]
                    for row in rows:
                        sender=mapping.get(int(row['real_sender_id']),'');item=obj._export_row(row,self.module.MSG_TYPE_NAMES)
                        batch.append({'id':f"{rel}:{row['local_id']}",'time':int(row['create_time']),
                            'seq':int(row['sort_seq'] or 0),'role':'me' if sender==binding['account'] else ('other' if sender==peer else 'unknown'),
                            'kind':int(item['type_code']) & 0xffffffff,'text':item.get('content') or '',
                            'sender':sender,'type':str(item['type'])})
                finally:conn.close()
                if not rows:break
                after=int(rows[-1]['local_id'])
                yield batch,{rel:after}

    def close(self):
        if self.obj:self.obj._keys.clear()
        self.obj=None
        self.snapshots.clear()
        self.temp.cleanup()
