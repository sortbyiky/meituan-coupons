# -*- coding:utf-8 -*-
"""
美团红包自动领取 - Web 控制台
支持登录、Token 管理、自动提取 Token、优惠券日志
"""
import os
import re
import json
import subprocess
import threading
import hashlib
import secrets
from datetime import datetime
from functools import wraps
from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

LOG_FILE = "/var/log/meituan/coupons.log"
SCRIPT_PATH = "/app/meituan.py"
DATA_DIR = "/var/log/meituan"
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

# 默认管理员密码，可通过环境变量设置
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# 执行状态
execution_status = {
    "running": False,
    "last_run": None,
    "last_result": None
}

def load_tokens():
    """加载保存的 Token"""
    try:
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return []

def save_tokens(tokens):
    """保存 Token"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TOKENS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)

def load_history():
    """加载领取历史"""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return []

def save_history(history):
    """保存领取历史"""
    os.makedirs(DATA_DIR, exist_ok=True)
    # 只保留最近 100 条
    history = history[-100:]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def extract_token_from_url(url_or_cookie):
    """从 URL 或 Cookie 中提取 Token"""
    # 匹配 token=xxx 格式
    match = re.search(r'token=([^;&\s]+)', url_or_cookie)
    if match:
        return match.group(1)
    # 如果没有 token= 前缀，检查是否本身就是 token
    if url_or_cookie and len(url_or_cookie) > 50 and not url_or_cookie.startswith('http'):
        return url_or_cookie.strip()
    return None

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json:
                return jsonify({"success": False, "message": "请先登录"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>美团红包自动领取</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 28px;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        .header p { opacity: 0.9; font-size: 14px; }
        .header-actions {
            margin-top: 15px;
        }
        .header-actions a {
            color: white;
            text-decoration: none;
            opacity: 0.8;
            font-size: 14px;
        }
        .header-actions a:hover { opacity: 1; }
        .card {
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            margin-bottom: 20px;
            overflow: hidden;
        }
        .card-header {
            background: #f8f9fa;
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }
        .card-header h2 { font-size: 16px; color: #333; }
        .card-body { padding: 20px; }
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .status-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .status-item .label { font-size: 12px; color: #666; margin-bottom: 5px; }
        .status-item .value { font-size: 16px; font-weight: 600; color: #333; }
        .status-item .value.running { color: #f59e0b; }
        .status-item .value.success { color: #10b981; }
        .status-item .value.error { color: #ef4444; }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .btn-secondary { background: #e5e7eb; color: #374151; }
        .btn-secondary:hover { background: #d1d5db; }
        .btn-danger { background: #ef4444; color: white; }
        .btn-danger:hover { background: #dc2626; }
        .btn-success { background: #10b981; color: white; }
        .btn-success:hover { background: #059669; }
        .btn-sm { padding: 6px 12px; font-size: 12px; }
        .toolbar { display: flex; gap: 10px; flex-wrap: wrap; }
        .form-group { margin-bottom: 15px; }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-size: 14px;
            color: #374151;
            font-weight: 500;
        }
        .form-control {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.2s;
        }
        .form-control:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .form-hint { font-size: 12px; color: #6b7280; margin-top: 5px; }
        .token-list { margin-top: 15px; }
        .token-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 15px;
            background: #f8f9fa;
            border-radius: 8px;
            margin-bottom: 10px;
            gap: 10px;
        }
        .token-item .token-info { flex: 1; min-width: 0; }
        .token-item .token-name { font-weight: 600; color: #333; margin-bottom: 3px; }
        .token-item .token-value {
            font-size: 12px;
            color: #6b7280;
            font-family: monospace;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .token-item .token-actions { display: flex; gap: 5px; }
        .log-container {
            background: #1e1e1e;
            border-radius: 8px;
            padding: 15px;
            max-height: 400px;
            overflow-y: auto;
        }
        .log-content {
            font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
            font-size: 13px;
            line-height: 1.6;
            color: #d4d4d4;
            white-space: pre-wrap;
            word-break: break-all;
        }
        .log-line { padding: 2px 0; }
        .log-line.success { color: #4ade80; }
        .log-line.error { color: #f87171; }
        .log-line.info { color: #60a5fa; }
        .log-line.separator { color: #6b7280; }
        .history-item {
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .history-item .history-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .history-item .history-time { font-size: 12px; color: #6b7280; }
        .history-item .history-status {
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .history-item .history-status.success { background: #d1fae5; color: #059669; }
        .history-item .history-status.error { background: #fee2e2; color: #dc2626; }
        .coupon-list { display: flex; flex-wrap: wrap; gap: 10px; }
        .coupon-item {
            padding: 8px 12px;
            background: white;
            border-radius: 6px;
            font-size: 13px;
            border: 1px solid #e5e7eb;
        }
        .coupon-item .coupon-name { font-weight: 600; color: #333; }
        .coupon-item .coupon-amount { color: #ef4444; font-weight: 600; }
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #9ca3af;
        }
        .tabs {
            display: flex;
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 20px;
        }
        .tab {
            padding: 12px 20px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            color: #6b7280;
            font-weight: 500;
            transition: all 0.2s;
        }
        .tab:hover { color: #374151; }
        .tab.active {
            color: #667eea;
            border-bottom-color: #667eea;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid currentColor;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            background: #333;
            color: white;
            border-radius: 8px;
            font-size: 14px;
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.3s;
            z-index: 1000;
        }
        .toast.show { opacity: 1; transform: translateY(0); }
        .toast.success { background: #10b981; }
        .toast.error { background: #ef4444; }
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .modal.show { display: flex; }
        .modal-content {
            background: white;
            border-radius: 16px;
            width: 90%;
            max-width: 500px;
            max-height: 90vh;
            overflow-y: auto;
        }
        .modal-header {
            padding: 20px;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-header h3 { font-size: 18px; color: #333; }
        .modal-close {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #6b7280;
        }
        .modal-body { padding: 20px; }
        .modal-footer {
            padding: 15px 20px;
            border-top: 1px solid #e5e7eb;
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }
        @media (max-width: 600px) {
            .status-grid { grid-template-columns: repeat(2, 1fr); }
            .toolbar { flex-direction: column; }
            .btn { width: 100%; justify-content: center; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>美团红包自动领取</h1>
            <p>Web 控制台 | 管理 Token、查看日志、手动执行</p>
            <div class="header-actions">
                <a href="/logout">退出登录</a>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2>执行状态</h2>
                <div class="toolbar">
                    <button class="btn btn-primary" id="runBtn" onclick="runNow()">
                        立即执行
                    </button>
                    <button class="btn btn-secondary" onclick="refreshStatus()">
                        刷新
                    </button>
                </div>
            </div>
            <div class="card-body">
                <div class="status-grid">
                    <div class="status-item">
                        <div class="label">当前状态</div>
                        <div class="value" id="statusText">加载中...</div>
                    </div>
                    <div class="status-item">
                        <div class="label">上次执行</div>
                        <div class="value" id="lastRunText">-</div>
                    </div>
                    <div class="status-item">
                        <div class="label">执行结果</div>
                        <div class="value" id="lastResultText">-</div>
                    </div>
                    <div class="status-item">
                        <div class="label">Token 数量</div>
                        <div class="value" id="tokenCount">0</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-body">
                <div class="tabs">
                    <div class="tab active" onclick="switchTab('tokens')">Token 管理</div>
                    <div class="tab" onclick="switchTab('history')">领取记录</div>
                    <div class="tab" onclick="switchTab('logs')">执行日志</div>
                </div>

                <div id="tab-tokens" class="tab-content active">
                    <div class="form-group">
                        <label>添加 Token</label>
                        <input type="text" class="form-control" id="tokenInput"
                               placeholder="粘贴 Token 或包含 token= 的 Cookie/URL">
                        <div class="form-hint">
                            支持直接粘贴 Token、Cookie 字符串或美团页面 URL，系统会自动提取 Token
                        </div>
                    </div>
                    <div class="form-group">
                        <input type="text" class="form-control" id="tokenName"
                               placeholder="备注名称（可选，如：账号1）">
                    </div>
                    <button class="btn btn-success" onclick="addToken()">
                        添加 Token
                    </button>

                    <div class="token-list" id="tokenList">
                        <div class="empty-state">暂无 Token，请添加</div>
                    </div>
                </div>

                <div id="tab-history" class="tab-content">
                    <div id="historyList">
                        <div class="empty-state">暂无领取记录</div>
                    </div>
                </div>

                <div id="tab-logs" class="tab-content">
                    <div class="toolbar" style="margin-bottom: 15px;">
                        <button class="btn btn-secondary btn-sm" onclick="refreshLogs()">刷新日志</button>
                        <button class="btn btn-secondary btn-sm" onclick="clearLogs()">清空日志</button>
                    </div>
                    <div class="log-container" id="logContainer">
                        <div class="log-content" id="logContent"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="toast" id="toast"></div>

    <div class="modal" id="editModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>编辑 Token</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label>备注名称</label>
                    <input type="text" class="form-control" id="editTokenName">
                </div>
                <div class="form-group">
                    <label>Token</label>
                    <input type="text" class="form-control" id="editTokenValue">
                </div>
                <input type="hidden" id="editTokenIndex">
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeModal()">取消</button>
                <button class="btn btn-primary" onclick="saveEditToken()">保存</button>
            </div>
        </div>
    </div>

    <script>
        let tokens = [];

        function showToast(message, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast show ' + type;
            setTimeout(() => { toast.className = 'toast'; }, 3000);
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function formatLogLine(line) {
            if (!line.trim()) return '';
            let className = '';
            if (line.includes('成功') || line.includes('Success')) className = 'success';
            else if (line.includes('失败') || line.includes('错误') || line.includes('Error')) className = 'error';
            else if (line.includes('===') || line.includes('---')) className = 'separator';
            else if (line.includes('[') && line.includes(']')) className = 'info';
            return '<div class="log-line ' + className + '">' + escapeHtml(line) + '</div>';
        }

        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelector(`.tab[onclick="switchTab('${tabName}')"]`).classList.add('active');
            document.getElementById('tab-' + tabName).classList.add('active');

            if (tabName === 'history') loadHistory();
            if (tabName === 'logs') refreshLogs();
        }

        async function refreshStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                const statusText = document.getElementById('statusText');
                const lastRunText = document.getElementById('lastRunText');
                const lastResultText = document.getElementById('lastResultText');
                const runBtn = document.getElementById('runBtn');

                if (data.running) {
                    statusText.textContent = '执行中...';
                    statusText.className = 'value running';
                    runBtn.disabled = true;
                    runBtn.innerHTML = '<span class="spinner"></span> 执行中...';
                } else {
                    statusText.textContent = '空闲';
                    statusText.className = 'value';
                    runBtn.disabled = false;
                    runBtn.innerHTML = '立即执行';
                }

                lastRunText.textContent = data.last_run || '-';
                if (data.last_result === 'success') {
                    lastResultText.textContent = '成功';
                    lastResultText.className = 'value success';
                } else if (data.last_result === 'error') {
                    lastResultText.textContent = '失败';
                    lastResultText.className = 'value error';
                } else {
                    lastResultText.textContent = '-';
                    lastResultText.className = 'value';
                }
            } catch (e) {
                console.error('Failed to refresh status:', e);
            }
        }

        async function loadTokens() {
            try {
                const response = await fetch('/api/tokens');
                const data = await response.json();
                tokens = data.tokens || [];
                renderTokens();
                document.getElementById('tokenCount').textContent = tokens.length;
            } catch (e) {
                console.error('Failed to load tokens:', e);
            }
        }

        function renderTokens() {
            const list = document.getElementById('tokenList');
            if (tokens.length === 0) {
                list.innerHTML = '<div class="empty-state">暂无 Token，请添加</div>';
                return;
            }
            list.innerHTML = tokens.map((t, i) => `
                <div class="token-item">
                    <div class="token-info">
                        <div class="token-name">${escapeHtml(t.name || '账号 ' + (i + 1))}</div>
                        <div class="token-value">${escapeHtml(t.token.substring(0, 30))}...</div>
                    </div>
                    <div class="token-actions">
                        <button class="btn btn-secondary btn-sm" onclick="editToken(${i})">编辑</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteToken(${i})">删除</button>
                    </div>
                </div>
            `).join('');
        }

        async function addToken() {
            const input = document.getElementById('tokenInput').value.trim();
            const name = document.getElementById('tokenName').value.trim();

            if (!input) {
                showToast('请输入 Token', 'error');
                return;
            }

            try {
                const response = await fetch('/api/tokens', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ input, name })
                });
                const data = await response.json();

                if (data.success) {
                    showToast('Token 添加成功', 'success');
                    document.getElementById('tokenInput').value = '';
                    document.getElementById('tokenName').value = '';
                    loadTokens();
                } else {
                    showToast(data.message || '添加失败', 'error');
                }
            } catch (e) {
                showToast('请求失败', 'error');
            }
        }

        function editToken(index) {
            const token = tokens[index];
            document.getElementById('editTokenName').value = token.name || '';
            document.getElementById('editTokenValue').value = token.token;
            document.getElementById('editTokenIndex').value = index;
            document.getElementById('editModal').classList.add('show');
        }

        function closeModal() {
            document.getElementById('editModal').classList.remove('show');
        }

        async function saveEditToken() {
            const index = parseInt(document.getElementById('editTokenIndex').value);
            const name = document.getElementById('editTokenName').value.trim();
            const token = document.getElementById('editTokenValue').value.trim();

            if (!token) {
                showToast('Token 不能为空', 'error');
                return;
            }

            try {
                const response = await fetch('/api/tokens/' + index, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, token })
                });
                const data = await response.json();

                if (data.success) {
                    showToast('保存成功', 'success');
                    closeModal();
                    loadTokens();
                } else {
                    showToast(data.message || '保存失败', 'error');
                }
            } catch (e) {
                showToast('请求失败', 'error');
            }
        }

        async function deleteToken(index) {
            if (!confirm('确定要删除这个 Token 吗？')) return;

            try {
                const response = await fetch('/api/tokens/' + index, { method: 'DELETE' });
                const data = await response.json();

                if (data.success) {
                    showToast('删除成功', 'success');
                    loadTokens();
                } else {
                    showToast(data.message || '删除失败', 'error');
                }
            } catch (e) {
                showToast('请求失败', 'error');
            }
        }

        async function loadHistory() {
            try {
                const response = await fetch('/api/history');
                const data = await response.json();
                const list = document.getElementById('historyList');

                if (!data.history || data.history.length === 0) {
                    list.innerHTML = '<div class="empty-state">暂无领取记录</div>';
                    return;
                }

                list.innerHTML = data.history.reverse().map(h => `
                    <div class="history-item">
                        <div class="history-header">
                            <span class="history-time">${escapeHtml(h.time)}</span>
                            <span class="history-status ${h.success ? 'success' : 'error'}">
                                ${h.success ? '成功' : '失败'}
                            </span>
                        </div>
                        ${h.coupons && h.coupons.length > 0 ? `
                            <div class="coupon-list">
                                ${h.coupons.map(c => `
                                    <div class="coupon-item">
                                        <span class="coupon-name">${escapeHtml(c.name)}</span>
                                        <span class="coupon-amount">${c.amount}元</span>
                                    </div>
                                `).join('')}
                            </div>
                        ` : `<div style="color: #6b7280; font-size: 13px;">${escapeHtml(h.message || '无优惠券信息')}</div>`}
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to load history:', e);
            }
        }

        async function refreshLogs() {
            try {
                const response = await fetch('/api/logs');
                const data = await response.json();
                const logContent = document.getElementById('logContent');

                if (data.logs && data.logs.length > 0) {
                    logContent.innerHTML = data.logs.map(formatLogLine).join('');
                    const container = document.getElementById('logContainer');
                    container.scrollTop = container.scrollHeight;
                } else {
                    logContent.innerHTML = '<div class="empty-state">暂无日志记录</div>';
                }
            } catch (e) {
                console.error('Failed to refresh logs:', e);
            }
        }

        async function clearLogs() {
            if (!confirm('确定要清空所有日志吗？')) return;
            try {
                const response = await fetch('/api/logs/clear', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    showToast('日志已清空', 'success');
                    refreshLogs();
                }
            } catch (e) {
                showToast('请求失败', 'error');
            }
        }

        async function runNow() {
            const runBtn = document.getElementById('runBtn');
            runBtn.disabled = true;
            runBtn.innerHTML = '<span class="spinner"></span> 执行中...';

            try {
                const response = await fetch('/api/run', { method: 'POST' });
                const data = await response.json();

                if (data.success) {
                    showToast('开始执行，请稍候...', 'success');
                    const pollInterval = setInterval(async () => {
                        await refreshStatus();
                        const statusResponse = await fetch('/api/status');
                        const statusData = await statusResponse.json();
                        if (!statusData.running) {
                            clearInterval(pollInterval);
                            loadHistory();
                            refreshLogs();
                            showToast(statusData.last_result === 'success' ? '执行完成！' : '执行完成，请查看日志',
                                      statusData.last_result === 'success' ? 'success' : 'error');
                        }
                    }, 2000);
                } else {
                    showToast(data.message || '执行失败', 'error');
                    runBtn.disabled = false;
                    runBtn.innerHTML = '立即执行';
                }
            } catch (e) {
                showToast('请求失败', 'error');
                runBtn.disabled = false;
                runBtn.innerHTML = '立即执行';
            }
        }

        // 初始化
        refreshStatus();
        loadTokens();
        setInterval(refreshStatus, 5000);
    </script>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录 - 美团红包自动领取</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .login-card {
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
            padding: 40px;
        }
        .login-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .login-header h1 { font-size: 24px; color: #333; margin-bottom: 10px; }
        .login-header p { color: #6b7280; font-size: 14px; }
        .form-group { margin-bottom: 20px; }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-size: 14px;
            color: #374151;
            font-weight: 500;
        }
        .form-control {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            font-size: 14px;
        }
        .form-control:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .btn {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .btn:hover { transform: translateY(-2px); }
        .error-message {
            background: #fee2e2;
            color: #dc2626;
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="login-header">
            <h1>美团红包自动领取</h1>
            <p>请输入管理员密码登录</p>
        </div>
        {% if error %}
        <div class="error-message">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label>管理员密码</label>
                <input type="password" name="password" class="form-control"
                       placeholder="请输入密码" autofocus required>
            </div>
            <button type="submit" class="btn">登录</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = '密码错误'
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
@login_required
def get_status():
    return jsonify(execution_status)

@app.route('/api/tokens', methods=['GET'])
@login_required
def get_tokens():
    return jsonify({"tokens": load_tokens()})

@app.route('/api/tokens', methods=['POST'])
@login_required
def add_token():
    data = request.get_json()
    input_str = data.get('input', '').strip()
    name = data.get('name', '').strip()

    token = extract_token_from_url(input_str)
    if not token:
        return jsonify({"success": False, "message": "无法从输入中提取 Token"})

    tokens = load_tokens()
    # 检查是否已存在
    for t in tokens:
        if t['token'] == token:
            return jsonify({"success": False, "message": "该 Token 已存在"})

    tokens.append({
        "name": name or f"账号 {len(tokens) + 1}",
        "token": token,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_tokens(tokens)

    # 更新环境变量文件
    update_env_tokens(tokens)

    return jsonify({"success": True, "token": token[:30] + "..."})

@app.route('/api/tokens/<int:index>', methods=['PUT'])
@login_required
def update_token(index):
    data = request.get_json()
    tokens = load_tokens()

    if index < 0 or index >= len(tokens):
        return jsonify({"success": False, "message": "Token 不存在"})

    tokens[index]['name'] = data.get('name', tokens[index]['name'])
    tokens[index]['token'] = data.get('token', tokens[index]['token'])
    save_tokens(tokens)
    update_env_tokens(tokens)

    return jsonify({"success": True})

@app.route('/api/tokens/<int:index>', methods=['DELETE'])
@login_required
def delete_token(index):
    tokens = load_tokens()

    if index < 0 or index >= len(tokens):
        return jsonify({"success": False, "message": "Token 不存在"})

    tokens.pop(index)
    save_tokens(tokens)
    update_env_tokens(tokens)

    return jsonify({"success": True})

def update_env_tokens(tokens):
    """更新环境变量中的 Token"""
    token_str = "&".join([t['token'] for t in tokens])
    os.environ['MEITUAN_TOKEN'] = token_str
    # 同时写入 .env 文件供 cron 使用
    try:
        with open('/app/.env', 'w') as f:
            f.write(f"MEITUAN_TOKEN={token_str}\n")
    except:
        pass

@app.route('/api/history')
@login_required
def get_history():
    return jsonify({"history": load_history()})

@app.route('/api/logs')
@login_required
def get_logs():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                return jsonify({"logs": lines[-500:]})
        return jsonify({"logs": []})
    except Exception as e:
        return jsonify({"logs": [], "error": str(e)})

@app.route('/api/logs/clear', methods=['POST'])
@login_required
def clear_logs():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w') as f:
                f.write('')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/run', methods=['POST'])
@login_required
def run_script():
    if execution_status["running"]:
        return jsonify({"success": False, "message": "任务正在执行中"})

    tokens = load_tokens()
    if not tokens:
        # 检查环境变量
        env_token = os.environ.get('MEITUAN_TOKEN', '').strip()
        if not env_token:
            return jsonify({"success": False, "message": "请先添加 Token"})

    def execute():
        execution_status["running"] = True
        execution_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        history_entry = {
            "time": execution_status["last_run"],
            "success": False,
            "coupons": [],
            "message": ""
        }

        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"手动执行 - {execution_status['last_run']}\n")
                f.write(f"{'='*50}\n")

            result = subprocess.run(
                ['python', SCRIPT_PATH],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ}
            )

            output = result.stdout + result.stderr

            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(output)

            # 解析输出获取优惠券信息
            coupons = []
            for line in output.split('\n'):
                if '|' in line and '元' in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 2:
                        coupons.append({
                            "name": parts[0].strip(),
                            "amount": parts[1].replace('元', '').strip()
                        })

            history_entry["success"] = result.returncode == 0 or '成功领取' in output
            history_entry["coupons"] = coupons
            if not history_entry["success"]:
                history_entry["message"] = "执行失败，请查看日志"

            execution_status["last_result"] = "success" if history_entry["success"] else "error"

        except subprocess.TimeoutExpired:
            execution_status["last_result"] = "error"
            history_entry["message"] = "执行超时（120秒）"
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write("执行超时（120秒）\n")
        except Exception as e:
            execution_status["last_result"] = "error"
            history_entry["message"] = str(e)
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"执行异常: {str(e)}\n")
        finally:
            execution_status["running"] = False
            # 保存历史记录
            history = load_history()
            history.append(history_entry)
            save_history(history)

    thread = threading.Thread(target=execute)
    thread.start()

    return jsonify({"success": True, "message": "任务已开始执行"})

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)

    # 从环境变量加载初始 Token
    env_token = os.environ.get('MEITUAN_TOKEN', '').strip()
    if env_token and not os.path.exists(TOKENS_FILE):
        tokens = []
        for i, t in enumerate(env_token.split('&')):
            if t.strip():
                tokens.append({
                    "name": f"账号 {i + 1}",
                    "token": t.strip(),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        if tokens:
            save_tokens(tokens)

    port = int(os.environ.get('WEB_PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
