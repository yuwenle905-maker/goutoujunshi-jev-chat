import json
from pathlib import Path
import sys
import time
import unittest
from core import UserError
from engine import Engine


class JsonOutputTests(unittest.TestCase):
    def setUp(self):
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        self.engine=Engine(root/'skill');self.requests=[]
        self.good=json.dumps(dict(reply='自然回复',reason='依据',needs_human=False),ensure_ascii=False)
    def generate(self,responses,profile=None):
        iterator=iter(responses)
        def request(path,key,data):self.requests.append(data);return next(iterator)
        self.engine.request=request
        return self.engine.generate([dict(kind=1,role='other',text='你在忙吗',time=1)],profile or {},'synthetic','mock-model')
    def response(self,text,finish='stop',**fields):
        return {'choices':[dict(finish_reason=finish,message=dict(content=text,**fields))]}
    def test_unique_complete_json_can_be_recovered_from_wrapper_for_review(self):
        result=Engine.parse('以下是结果：\n'+self.good+'\n以上。')
        self.assertEqual(result['reply'],'自然回复');self.assertTrue(result['needs_human']);self.assertTrue(result['format_recovered'])
    def test_multiple_reply_objects_are_ambiguous(self):
        with self.assertRaises(UserError):Engine.parse(self.good+'\n'+self.good)
    def test_duplicate_flags_are_rejected(self):
        with self.assertRaisesRegex(UserError,'重复字段'):Engine.parse('{"reply":"a","reason":"b","needs_human":true,"needs_human":false}')
    def test_partial_json_is_not_completed_with_guesses(self):
        with self.assertRaises(UserError):Engine.parse('{"reply":"一半')
    def test_empty_content_retries_once_and_forces_review(self):
        result=self.generate([self.response(''),self.response(self.good)])
        self.assertEqual(len(self.requests),2);self.assertTrue(result['needs_human']);self.assertTrue(result['format_recovered'])
    def test_length_stop_retries_even_if_partial_looks_valid(self):
        result=self.generate([self.response(self.good,'length'),self.response(self.good)])
        self.assertEqual(len(self.requests),2);self.assertTrue(result['needs_human'])
    def test_two_invalid_responses_fail_without_plaintext_fallback(self):
        with self.assertRaisesRegex(UserError,'格式修复'):self.generate([self.response('整段分析'),self.response('还是整段分析')])
        self.assertEqual(len(self.requests),2)
    def test_refusal_is_not_retried(self):
        with self.assertRaisesRegex(UserError,'拒绝'):self.generate([self.response('',finish='content_filter')])
        self.assertEqual(len(self.requests),1)
    def test_reasoning_is_not_used_as_reply(self):
        result=self.generate([self.response('',reasoning_content='分析而非回复'),self.response(self.good)])
        self.assertNotEqual(result['reply'],'分析而非回复');self.assertTrue(result['needs_human'])
    def test_normal_response_is_not_duplicated_and_json_example_is_present(self):
        result=self.generate([self.response(self.good)])
        self.assertFalse(result['needs_human']);self.assertEqual(len(self.requests),1)
        request=self.requests[0];self.assertEqual(request['thinking'],{'type':'disabled'})
        self.assertEqual(request['max_tokens'],4096);self.assertIn('"needs_human": false',request['messages'][0]['content'])
        self.assertIn(self.engine.main,request['messages'][0]['content'])
    def test_insufficient_total_budget_does_not_start_repair(self):
        self.engine.deadline=time.monotonic()+5
        with self.assertRaisesRegex(UserError,'剩余等待时间不足'):self.generate([self.response('')])
        self.assertEqual(len(self.requests),1)
    def test_assessment_is_revalidated_after_repair(self):
        assessment=dict.fromkeys(('stage','signals','uncertainties','next_step','boundaries'),'不确定')
        valid=json.dumps(dict(reply='回复',reason='依据',needs_human=False,assessment=assessment),ensure_ascii=False)
        result=self.generate([self.response(self.good),self.response(valid)],dict(assess_relationship=True))
        self.assertEqual(result['assessment'],assessment);self.assertTrue(result['needs_human'])
