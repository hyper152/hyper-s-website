# -*- coding: utf-8 -*-
"""
Ollama API 代理模块 - 自注册版
"""
import json
import requests
import logging
from flask import Blueprint, request, Response, jsonify, stream_with_context

logger = logging.getLogger("ollama")

OLLAMA_URL = "http://localhost:11434"

# 创建蓝图
ollama_bp = Blueprint('ollama', __name__, url_prefix='/api/ollama')

@ollama_bp.route('/models', methods=['GET'])
def list_models():
    """获取可用模型列表"""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return jsonify(resp.json())
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        return jsonify({"error": str(e)}), 500

@ollama_bp.route('/chat', methods=['POST'])
def chat():
    """聊天接口（支持流式）"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效请求"}), 400
    
    model = data.get('model', 'qwen2.5:7b')
    messages = data.get('messages', [])
    stream = data.get('stream', True)
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream
    }
    
    if stream:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            stream=True,
            timeout=120
        )
        
        def generate():
            for chunk in resp.iter_content(chunk_size=None):
                if chunk:
                    yield chunk
        
        return Response(
            stream_with_context(generate()),
            content_type='application/x-ndjson'
        )
    else:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=120
        )
        return jsonify(resp.json())

@ollama_bp.route('/save-ai-question', methods=['POST'])
def save_ai_question():
    """保存AI提问到 data/ai.json"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'fail', 'msg': '无数据'}), 400
        # 读取原有内容
        ai_json_path = __file__.replace('src/ollama.py', 'data/ai.json')
        try:
            with open(ai_json_path, 'r', encoding='utf-8') as f:
                arr = json.load(f)
        except Exception:
            arr = []
        arr.append(data)
        with open(ai_json_path, 'w', encoding='utf-8') as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"保存AI提问失败: {e}")
        return jsonify({'status': 'fail', 'msg': str(e)}), 500

# ==================== 自注册函数 ====================
def register_ollama_routes(app):
    """手动注册 Ollama 路由（不依赖 Blueprint）"""
    
    @app.route('/api/ollama/models', methods=['GET'])
    def _list_models():
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            return jsonify(resp.json())
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/ollama/chat', methods=['POST'])
    def _chat():
        data = request.get_json()
        if not data:
            return jsonify({"error": "无效请求"}), 400
        
        model = data.get('model', 'qwen2.5:7b')
        messages = data.get('messages', [])
        stream = data.get('stream', True)
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        if stream:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                stream=True,
                timeout=120
            )
            
            def generate():
                for chunk in resp.iter_content(chunk_size=None):
                    if chunk:
                        yield chunk
            
            return Response(
                stream_with_context(generate()),
                content_type='application/x-ndjson'
            )
        else:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=120
            )
            return jsonify(resp.json())
    
    logger.info("✅ Ollama 路由注册成功")