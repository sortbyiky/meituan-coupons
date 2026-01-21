# -*- coding:utf-8 -*-
"""
美团红包自动领取 - Web 控制台
"""
import os
import subprocess
import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

app = Flask(__name__)

LOG_FILE = "/var/log/meituan/coupons.log"
SCRIPT_PATH = "/app/meituan.py"

# 执行状态
execution_status = {
    "running": False,
    "last_run": None,
    "last_result": None
}

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
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
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
        .header p {
            opacity: 0.9;
            font-size: 14px;
        }
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
        }
        .card-header h2 {
            font-size: 16px;
            color: #333;
        }
        .card-body {
            padding: 20px;
        }
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .status-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .status-item .label {
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }
        .status-item .value {
            font-size: 16px;
            font-weight: 600;
            color: #333;
        }
        .status-item .value.running {
            color: #f59e0b;
        }
        .status-item .value.success {
            color: #10b981;
        }
        .status-item .value.error {
            color: #ef4444;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .btn-primary:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .btn-secondary {
            background: #e5e7eb;
            color: #374151;
        }
        .btn-secondary:hover {
            background: #d1d5db;
        }
        .log-container {
            background: #1e1e1e;
            border-radius: 8px;
            padding: 15px;
            max-height: 500px;
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
        .log-line {
            padding: 2px 0;
        }
        .log-line.success {
            color: #4ade80;
        }
        .log-line.error {
            color: #f87171;
        }
        .log-line.info {
            color: #60a5fa;
        }
        .log-line.separator {
            color: #6b7280;
        }
        .toolbar {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #9ca3af;
        }
        .empty-state svg {
            width: 48px;
            height: 48px;
            margin-bottom: 15px;
            opacity: 0.5;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #fff;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
            vertical-align: middle;
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
        .toast.show {
            opacity: 1;
            transform: translateY(0);
        }
        .toast.success {
            background: #10b981;
        }
        .toast.error {
            background: #ef4444;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>美团红包自动领取</h1>
            <p>Web 控制台 | 查看日志 & 手动触发</p>
        </div>

        <div class="card">
            <div class="card-header">
                <h2>执行状态</h2>
                <div class="toolbar">
                    <button class="btn btn-primary" id="runBtn" onclick="runNow()">
                        立即执行
                    </button>
                    <button class="btn btn-secondary" onclick="refreshStatus()">
                        刷新状态
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
                        <div class="label">当前时间</div>
                        <div class="value" id="currentTime">-</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2>执行日志</h2>
                <div class="toolbar">
                    <button class="btn btn-secondary" onclick="refreshLogs()">
                        刷新日志
                    </button>
                    <button class="btn btn-secondary" onclick="clearLogs()">
                        清空日志
                    </button>
                </div>
            </div>
            <div class="card-body">
                <div class="log-container" id="logContainer">
                    <div class="empty-state" id="emptyState">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <p>暂无日志记录</p>
                    </div>
                    <div class="log-content" id="logContent"></div>
                </div>
            </div>
        </div>
    </div>

    <div class="toast" id="toast"></div>

    <script>
        function showToast(message, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast show ' + type;
            setTimeout(() => {
                toast.className = 'toast';
            }, 3000);
        }

        function formatLogLine(line) {
            if (!line.trim()) return '';

            let className = '';
            if (line.includes('成功') || line.includes('Success')) {
                className = 'success';
            } else if (line.includes('失败') || line.includes('错误') || line.includes('Error')) {
                className = 'error';
            } else if (line.includes('===') || line.includes('---')) {
                className = 'separator';
            } else if (line.includes('[') && line.includes(']')) {
                className = 'info';
            }

            return '<div class="log-line ' + className + '">' + escapeHtml(line) + '</div>';
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function updateTime() {
            document.getElementById('currentTime').textContent =
                new Date().toLocaleString('zh-CN', { hour12: false });
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
                    runBtn.innerHTML = '<span class="spinner"></span>执行中...';
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

        async function refreshLogs() {
            try {
                const response = await fetch('/api/logs');
                const data = await response.json();

                const logContent = document.getElementById('logContent');
                const emptyState = document.getElementById('emptyState');

                if (data.logs && data.logs.length > 0) {
                    emptyState.style.display = 'none';
                    logContent.innerHTML = data.logs.map(formatLogLine).join('');

                    const container = document.getElementById('logContainer');
                    container.scrollTop = container.scrollHeight;
                } else {
                    emptyState.style.display = 'block';
                    logContent.innerHTML = '';
                }
            } catch (e) {
                console.error('Failed to refresh logs:', e);
                showToast('刷新日志失败', 'error');
            }
        }

        async function runNow() {
            const runBtn = document.getElementById('runBtn');
            runBtn.disabled = true;
            runBtn.innerHTML = '<span class="spinner"></span>执行中...';

            try {
                const response = await fetch('/api/run', { method: 'POST' });
                const data = await response.json();

                if (data.success) {
                    showToast('开始执行，请稍候...', 'success');

                    // 轮询状态直到完成
                    const pollInterval = setInterval(async () => {
                        await refreshStatus();
                        const statusResponse = await fetch('/api/status');
                        const statusData = await statusResponse.json();

                        if (!statusData.running) {
                            clearInterval(pollInterval);
                            await refreshLogs();

                            if (statusData.last_result === 'success') {
                                showToast('执行完成！', 'success');
                            } else {
                                showToast('执行完成，请查看日志', 'error');
                            }
                        }
                    }, 2000);
                } else {
                    showToast(data.message || '执行失败', 'error');
                    runBtn.disabled = false;
                    runBtn.innerHTML = '立即执行';
                }
            } catch (e) {
                console.error('Failed to run:', e);
                showToast('请求失败', 'error');
                runBtn.disabled = false;
                runBtn.innerHTML = '立即执行';
            }
        }

        async function clearLogs() {
            if (!confirm('确定要清空所有日志吗？')) return;

            try {
                const response = await fetch('/api/logs/clear', { method: 'POST' });
                const data = await response.json();

                if (data.success) {
                    showToast('日志已清空', 'success');
                    await refreshLogs();
                } else {
                    showToast('清空失败', 'error');
                }
            } catch (e) {
                console.error('Failed to clear logs:', e);
                showToast('请求失败', 'error');
            }
        }

        // 初始化
        updateTime();
        setInterval(updateTime, 1000);
        refreshStatus();
        refreshLogs();

        // 自动刷新
        setInterval(refreshStatus, 5000);
        setInterval(refreshLogs, 10000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def get_status():
    return jsonify(execution_status)

@app.route('/api/logs')
def get_logs():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 返回最后 500 行
                return jsonify({"logs": lines[-500:]})
        return jsonify({"logs": []})
    except Exception as e:
        return jsonify({"logs": [], "error": str(e)})

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w') as f:
                f.write('')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/run', methods=['POST'])
def run_script():
    if execution_status["running"]:
        return jsonify({"success": False, "message": "任务正在执行中"})

    def execute():
        execution_status["running"] = True
        execution_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # 写入分隔符
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"手动执行 - {execution_status['last_run']}\n")
                f.write(f"{'='*50}\n")

            # 执行脚本
            result = subprocess.run(
                ['python', SCRIPT_PATH],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ}
            )

            # 写入输出
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                if result.stdout:
                    f.write(result.stdout)
                if result.stderr:
                    f.write(result.stderr)

            execution_status["last_result"] = "success" if result.returncode == 0 else "error"
        except subprocess.TimeoutExpired:
            execution_status["last_result"] = "error"
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write("执行超时（120秒）\n")
        except Exception as e:
            execution_status["last_result"] = "error"
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"执行异常: {str(e)}\n")
        finally:
            execution_status["running"] = False

    thread = threading.Thread(target=execute)
    thread.start()

    return jsonify({"success": True, "message": "任务已开始执行"})

if __name__ == '__main__':
    # 确保日志目录存在
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    port = int(os.environ.get('WEB_PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
