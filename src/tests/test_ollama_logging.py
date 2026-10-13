import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from flask import Flask
import requests
from src import ollama
from src.storage import Store
from src.admin_db import browse


class ChatLoggingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, SITE_DB_PATH=str(Path(self.temp.name) / 'site.db'))
        self.env.start()
        self.store = Store(Path(self.temp.name) / 'site.db')
        self.store.create_user('hyper@example.invalid', {'username': 'hyper'})
        self.store.put_session('test-session', {'email': 'hyper@example.invalid', 'expire_time': time.time() + 3600})
        app = Flask(__name__)
        ollama.register_ollama_routes(app)
        self.client = app.test_client()
        self.logger = patch.object(ollama.logger, 'exception')
        self.logger.start()

    def tearDown(self):
        self.logger.stop()
        self.env.stop()
        self.temp.cleanup()

    def payload(self, stream=True):
        return {'model': 'test-model', 'conversation_id': 'conversation-one', 'stream': stream,
                'messages': [{'role': 'system', 'content': '系统设定'},
                             {'role': 'user', 'content': '前一问'},
                             {'role': 'assistant', 'content': '前一答'},
                             {'role': 'user', 'content': '最后的问题\n' + '完整保存' * 600}]}

    def post(self, payload, **kwargs):
        return self.client.post('/api/ollama/chat', json=payload,
                                headers={'Authorization': 'Session test-session'},
                                environ_overrides={'REMOTE_ADDR': '2409:8a2b::1'}, **kwargs)

    def record(self):
        records = self.store.records('ai_questions')
        self.assertEqual(len(records), 1)
        return records[0]

    def test_split_utf8_json_and_final_packet_without_newline_are_saved_losslessly(self):
        answer = '你好，\n```python\nprint("完整回答")\n```\n' + '长回答' * 1000
        packets = [{'message': {'role': 'assistant', 'content': answer[:100], 'thinking': '思考一'}, 'done': False},
                   {'message': {'role': 'assistant', 'content': answer[100:], 'thinking': '思考二'}, 'done': False},
                   {'message': {'role': 'assistant', 'content': ''}, 'done': True, 'eval_count': 123}]
        raw = '\n'.join(json.dumps(packet, ensure_ascii=False) for packet in packets).encode('utf-8')
        upstream = Mock()
        upstream.iter_content.return_value = [raw[index:index + 7] for index in range(0, len(raw), 7)]
        with patch.object(ollama.requests, 'post', return_value=upstream):
            response = self.post(self.payload())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, raw)
            response.close()
        record = self.record()
        self.assertEqual(record['answer'], answer)
        self.assertEqual(record['thinking'], '思考一思考二')
        self.assertEqual(record['messages'][:-1], self.payload()['messages'])
        self.assertEqual(record['messages'][-1]['content'], answer)
        self.assertEqual(record['question'], self.payload()['messages'][-1]['content'])
        self.assertEqual(record['status'], 'completed')
        self.assertEqual(record['response_metadata']['eval_count'], 123)
        self.assertEqual((record['user'], record['ip']), ('hyper', '2409:8a2b::1'))
        self.assertEqual(browse('ai_questions', query='print("完整回答")')['total'], 1)
        upstream.close.assert_called()

    def test_nonstreaming_response_saves_answer_and_full_message(self):
        packet = {'model': 'test-model', 'message': {'role': 'assistant', 'content': '非流式完整答案',
                                                   'thinking': '完整思考', 'tool_calls': [{'function': {'name': 'test'}}]},
                  'done': True, 'done_reason': 'stop'}
        upstream = Mock()
        upstream.json.return_value = packet
        with patch.object(ollama.requests, 'post', return_value=upstream) as post:
            response = self.post(self.payload(stream=False))
        self.assertEqual(response.get_json(), packet)
        self.assertFalse(post.call_args.kwargs['stream'])
        record = self.record()
        self.assertEqual(record['assistant_message'], packet['message'])
        self.assertEqual(record['answer'], '非流式完整答案')
        self.assertEqual(record['status'], 'completed')
        upstream.close.assert_called_once()

    def test_failed_connection_still_saves_question_and_error(self):
        with patch.object(ollama.requests, 'post', side_effect=requests.ConnectionError('model offline')):
            response = self.post(self.payload())
        self.assertEqual(response.status_code, 502)
        record = self.record()
        self.assertEqual(record['status'], 'error')
        self.assertEqual(record['error'], 'model offline')
        self.assertEqual(record['question'], self.payload()['messages'][-1]['content'])
        self.assertEqual(record['answer'], '')

    def test_stream_timeout_preserves_partial_answer(self):
        def chunks(**kwargs):
            yield b'{"message":{"content":"partial answer"},"done":false}\n'
            raise requests.Timeout('stream timeout')
        upstream = Mock()
        upstream.iter_content.side_effect = chunks
        with patch.object(ollama.requests, 'post', return_value=upstream):
            response = self.post(self.payload())
            self.assertIn(b'"error"', response.data)
            response.close()
        record = self.record()
        self.assertEqual(record['answer'], 'partial answer')
        self.assertEqual(record['status'], 'error')
        self.assertEqual(record['error'], 'stream timeout')

    def test_eof_without_done_and_client_disconnect_are_marked_interrupted(self):
        for disconnect in (False, True):
            with self.store.connection(write=True) as db:
                db.execute('DELETE FROM ai_questions')
            upstream = Mock()
            upstream.iter_content.return_value = iter([
                b'{"message":{"content":"partial"},"done":false}\n',
                b'{"message":{"content":" remaining"},"done":false}\n'])
            with patch.object(ollama.requests, 'post', return_value=upstream):
                response = self.post(self.payload(), buffered=False)
                if not disconnect:
                    response.get_data()
                response.close()
            record = self.record()
            self.assertEqual(record['status'], 'interrupted')
            self.assertEqual(record['answer'], 'partial' if disconnect else 'partial remaining')
            upstream.close.assert_called()

    def test_multiple_turns_are_correlated_and_old_records_are_preserved(self):
        old = {'question': '历史问题', 'time': '2026-01-01 00:00:00'}
        self.store.append('ai_questions', old)
        upstream = Mock()
        upstream.json.return_value = {'message': {'role': 'assistant', 'content': '第一答'}, 'done': True}
        first = self.payload(stream=False)
        with patch.object(ollama.requests, 'post', return_value=upstream):
            self.post(first)
            second = dict(first, messages=[*first['messages'], {'role': 'assistant', 'content': '第一答'},
                                         {'role': 'user', 'content': '继续提问'}])
            upstream.json.return_value = {'message': {'role': 'assistant', 'content': '第二答'}, 'done': True}
            self.post(second)
        records = self.store.records('ai_questions')
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0], old)
        self.assertEqual(records[1]['conversation_id'], records[2]['conversation_id'])
        self.assertNotEqual(records[1]['id'], records[2]['id'])
        self.assertEqual(records[2]['messages'][:-1], second['messages'])

    def test_invalid_requests_are_rejected_without_polluting_records(self):
        with patch.object(ollama.requests, 'post') as post:
            for payload in ({}, [], {'messages': []}, {'messages': [{'role': 'user', 'content': 10}]},
                            {'messages': [{'role': 'assistant', 'content': '没有提问'}]}):
                self.assertEqual(self.post(payload).status_code, 400)
            post.assert_not_called()
        self.assertEqual(self.store.records('ai_questions'), [])

    def test_legacy_question_endpoint_uses_verified_identity(self):
        response = self.client.post('/api/ollama/save-ai-question', json={'question': '兼容提问', 'user': 'hyper', 'ip': '1.1.1.1'},
                                    environ_overrides={'REMOTE_ADDR': '198.51.100.20'})
        self.assertEqual(response.get_json()['status'], 'ok')
        record = self.record()
        self.assertEqual((record['user'], record['ip']), ('游客', '198.51.100.20'))
        self.assertEqual(record['status'], 'question_only')
