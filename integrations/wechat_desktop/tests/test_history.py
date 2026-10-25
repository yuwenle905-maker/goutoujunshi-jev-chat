"""Large synthetic histories only; no real WeChat, model or credentials."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from core import Store
from wechat_reader import WechatReader


class SyntheticCipher:
    # Only synthetic test data uses this fast codec. Application defaults to DPAPI.
    def seal(self,value):return json.dumps(value).encode()
    def open(self,value):return json.loads(value)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=Store(self.root/'test.sqlite',cipher=SyntheticCipher())
        self.person=Store.person_id('account','peer');self.other=Store.person_id('account','other')
        for p in (self.person,self.other):self.store.save('objects',p,{'memory':True})
    def tearDown(self):self.store.close();self.temp.cleanup()
    def row(self,i,text='synthetic'):
        return {'id':f'shard:{i}','time':i,'seq':i,'text':text,'kind':1,'role':'other'}
    def test_over_ten_thousand_kept_and_deduplicated(self):
        messages=[self.row(i) for i in range(11005)]
        self.assertEqual(self.store.remember(self.person,messages),11005)
        self.assertEqual(len(self.store.history(self.person)),11005)
        self.assertEqual(self.store.remember(self.person,messages),0)
        self.assertEqual(self.store.count(self.other),0)
    def test_disabled_memory_does_not_advance_checkpoint(self):
        self.store.save('objects',self.person,{'memory':False})
        self.assertFalse(self.store.archive_batch(self.person,[self.row(1)],{'shard':1}))
        self.assertIsNone(self.store.get('settings','archive:'+self.person))
    def test_batch_failure_rolls_back_data_and_resume_cursor(self):
        with self.assertRaises(KeyError):
            self.store.archive_batch(self.person,[self.row(1),{'id':'bad'}],{'shard':99})
        self.assertEqual(self.store.count(self.person),0)
        self.assertIsNone(self.store.get('settings','archive:'+self.person))
    def test_clear_also_resets_history_cursor(self):
        self.store.archive_batch(self.person,[self.row(1)],{'shard':1})
        self.store.clear_person(self.person)
        self.assertIsNone(self.store.get('settings','archive:'+self.person))
    def test_old_relevant_messages_are_recalled_without_crossing_contacts(self):
        self.store.remember(self.person,[self.row(1,'周末想去海边看日落'),self.row(2,'普通旧消息')])
        self.store.remember(self.other,[self.row(3,'海边 only-other-person')])
        recent=[self.row(900,'海边天气好吗')]
        related=self.store.related(self.person,recent)
        self.assertEqual([m['id'] for m in related],['shard:1'])
    def test_keyset_reader_over_limit_and_resumes_without_gap(self):
        path=self.root/'source.sqlite';table='Msg_'+hashlib.md5(b'peer').hexdigest()
        conn=sqlite3.connect(path)
        conn.execute('CREATE TABLE '+table+' (local_id INTEGER PRIMARY KEY,real_sender_id INTEGER,create_time INTEGER,sort_seq INTEGER,local_type INTEGER,message_content TEXT,packed_info_data BLOB,server_id INTEGER)')
        conn.executemany('INSERT INTO '+table+' VALUES (?,2,?,?,1,?,NULL,0)',((i,i,i,'test') for i in range(1,11006)))
        conn.commit();conn.close()
        def open_db(rel):
            c=sqlite3.connect(path);c.row_factory=sqlite3.Row;return c
        obj=types.SimpleNamespace(_db_files=[('message/message_0.db',str(path),None)],_keys={'message/message_0.db':b'test'},
            _open=open_db,_name2id_map=lambda c:{2:'peer'},
            _export_row=lambda r,n:{'type_code':1,'content':r['message_content'],'type':'文本'})
        reader=object.__new__(WechatReader);reader.obj=obj;reader.account={'account':'account'}
        reader.module=types.SimpleNamespace(MSG_TYPE_NAMES={1:'文本'})
        binding={'account':'account','username':'peer'}
        iterator=reader.history_batches(binding,batch_size=500)
        first,checkpoint=next(iterator);iterator.close()
        remaining=list(reader.history_batches(binding,checkpoint,batch_size=500))
        all_rows=first+[m for batch,_ in remaining for m in batch]
        self.assertEqual(len(all_rows),11005)
        self.assertEqual(len({m['id'] for m in all_rows}),11005)
        self.assertTrue(all(len(batch)<=500 for batch,_ in remaining))
        self.assertEqual(remaining[-1][1],{'message/message_0.db':11005})

