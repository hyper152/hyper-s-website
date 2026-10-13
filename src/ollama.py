# -*- coding: utf-8 -*-
"""Ollama 代理与服务端完整问答记录，支持流式、非流式和失败记录。"""
import codecs
from datetime import datetime
import ipaddress
import json
import logging
import time
import uuid

import requests
from flask import Blueprint, request, Response, jsonify, stream_with_context
from src.auth import check_login_status, get_current_user
from src.storage import get_store

logger = logging.getLogger('ollama')
OLLAMA_URL = 'http://localhost:11434'
ollama_bp = Blueprint('ollama', __name__, url_prefix='/api/ollama')


def request_identity():
    session = request.cookies.get('session_id', '')
    authorization = request.headers.get('Authorization', '')
    if not session and authorization.startswith('Session '):
        session = authorization[8:].strip()
    user = get_current_user(session) if check_login_status(session) else {}
    try:
        ip = str(ipaddress.ip_address(request.remote_addr))
    except (ValueError, TypeError):
        ip = None
    return user.get('username') or '游客', ip


class ChatRecord:
    def __init__(self, model, messages, conversation_id):
        user, ip = request_identity()
        self.store = get_store()
        self.inputs = messages
        self.assistant = {'role': 'assistant', 'content': ''}
        self.metadata = {}
        self.finished = False
        self.finalized = False
        self.error = None
        self.last_saved = time.monotonic()
        self.item = {
            'id': str(uuid.uuid4()), 'conversation_id': conversation_id,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'user': user, 'ip': ip, 'model': model,
            'question': next(message['content'] for message in reversed(messages) if message['role'] == 'user'),
            'messages': messages, 'answer': '', 'thinking': '', 'status': 'pending',
        }
        self.row_id = self.store.append('ai_questions', self.item)

    def accept(self, packet, streaming=True):
        if not isinstance(packet, dict):
            raise ValueError('模型返回的内容不是 JSON 对象')
        if packet.get('error'):
            self.error = str(packet['error'])
        message = packet.get('message') or {}
        if not isinstance(message, dict):
            raise ValueError('模型返回的消息格式无效')
        for key, value in message.items():
            if streaming and key in ('content', 'thinking') and isinstance(value, str):
                self.assistant[key] = self.assistant.get(key, '') + value
            elif streaming and key == 'tool_calls' and isinstance(value, list):
                self.assistant.setdefault(key, []).extend(value)
            else:
                self.assistant[key] = value
        self.finished = self.finished or packet.get('done') is True
        self.metadata.update({key: value for key, value in packet.items() if key not in ('message', 'error')})

    def save(self, status, error=None, final=False):
        self.item.update(answer=self.assistant.get('content', ''), thinking=self.assistant.get('thinking', ''),
                         assistant_message=dict(self.assistant),
                         messages=[*self.inputs, dict(self.assistant)], status=status,
                         response_metadata=dict(self.metadata))
        if error:
            self.item['error'] = error
        if final:
            self.item['completed_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.store.update_ai_question(self.row_id, self.item)
        self.last_saved = time.monotonic()
        self.finalized = final

    def finish(self, error=None):
        if self.finalized:
            return
        error = error or self.error
        status = 'error' if error else 'completed' if self.finished else 'interrupted'
        self.save(status, error=error, final=True)


@ollama_bp.route('/models', methods=['GET'])
def list_models():
    try:
        with requests.get(f'{OLLAMA_URL}/api/tags', timeout=5) as response:
            response.raise_for_status()
            return jsonify(response.json())
    except requests.RequestException:
        logger.exception('获取模型列表失败')
        return jsonify({'error': '无法连接模型服务'}), 502


@ollama_bp.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': '无效请求'}), 400
    model, messages, stream = data.get('model', 'qwen2.5:7b'), data.get('messages'), data.get('stream', True)
    if (not isinstance(model, str) or not model.strip() or not isinstance(stream, bool)
            or not isinstance(messages, list) or not messages
            or any(not isinstance(message, dict) or message.get('role') not in ('system', 'user', 'assistant', 'tool')
                   or not isinstance(message.get('content'), str) for message in messages)
            or not any(message['role'] == 'user' for message in messages)):
        return jsonify({'error': '模型或对话内容格式无效'}), 400
    conversation_id = data.get('conversation_id')
    if not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 100:
        conversation_id = str(uuid.uuid4())
    record = ChatRecord(model, messages, conversation_id)
    payload = {'model': model, 'messages': messages, 'stream': stream}
    upstream = None
    try:
        upstream = requests.post(f'{OLLAMA_URL}/api/chat', json=payload, stream=stream, timeout=120)
        upstream.raise_for_status()
    except requests.RequestException as error:
        if upstream is not None:
            upstream.close()
        record.finish(error=str(error) or type(error).__name__)
        logger.exception('模型请求失败')
        return jsonify({'error': '无法连接模型服务，请稍后重试'}), 502

    if not stream:
        try:
            packet = upstream.json()
            record.accept(packet, streaming=False)
            record.finish()
            return jsonify(packet), 502 if record.error else 200
        except (ValueError, requests.RequestException) as error:
            record.finish(error=str(error) or type(error).__name__)
            return jsonify({'error': '模型返回的数据无效'}), 502
        finally:
            upstream.close()

    def generate():
        decoder = codecs.getincrementaldecoder('utf-8')()
        buffer = ''
        failure = None
        try:
            for chunk in upstream.iter_content(chunk_size=None):
                if not chunk:
                    continue
                buffer += decoder.decode(chunk)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        record.accept(json.loads(line))
                if time.monotonic() - record.last_saved >= 1:
                    record.save('streaming', error=record.error)
                yield chunk
            buffer += decoder.decode(b'', final=True)
            if buffer.strip():
                record.accept(json.loads(buffer))
        except (requests.RequestException, ValueError, UnicodeError) as error:
            failure = str(error) or type(error).__name__
            logger.exception('模型流式回答中断')
            yield (json.dumps({'error': '回答生成中断，请重试'}, ensure_ascii=False) + '\n').encode('utf-8')
        finally:
            upstream.close()
            record.finish(error=failure)

    response = Response(stream_with_context(generate()), content_type='application/x-ndjson')
    def close_response():
        upstream.close()
        record.finish()
    response.call_on_close(close_response)
    return response


@ollama_bp.route('/save-ai-question', methods=['POST'])
def save_ai_question():
    """兼容旧的提问保存调用；新聊天直接由 /chat 保存完整问答。"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('question'), str) or not data['question'].strip():
        return jsonify({'status': 'fail', 'msg': '无有效问题'}), 400
    user, ip = request_identity()
    record = dict(data, user=user, ip=ip, time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), status='question_only')
    get_store().append('ai_questions', record)
    return jsonify({'status': 'ok'})


def register_ollama_routes(app):
    app.register_blueprint(ollama_bp)
    logger.info('✅ Ollama 路由注册成功')
