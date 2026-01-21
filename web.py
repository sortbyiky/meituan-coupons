"""
美团红包自动领取 - 企业级 Web 控制台
"""
import os
import re
import json
import subprocess
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string
from models import db, init_db, User, MeituanAccount, GrabHistory, SystemLog, SystemConfig

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'meituan-coupons-secret-key-2024')

# 数据库配置 - 优先使用 /app/data 目录，确保数据持久化
DATA_DIR = os.environ.get('DATA_DIR', '/app/data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.environ.get('DB_PATH', f'{DATA_DIR}/meituan.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 日志文件路径
LOG_FILE = '/var/log/meituan/coupons.log'


def log_action(level: str, category: str, message: str, details: str = None):
    """记录系统日志"""
    try:
        log = SystemLog(
            level=level,
            category=category,
            message=message,
            details=details,
            ip_address=request.remote_addr if request else None,
            user_id=session.get('user_id')
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Log error: {e}")


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json or request.headers.get('Accept') == 'application/json':
                return jsonify({"success": False, "message": "请先登录", "code": 401}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def extract_token(input_str: str) -> str:
    """从各种格式中提取 Token"""
    if not input_str:
        return None
    input_str = input_str.strip()

    # 尝试从 URL 或 Cookie 中提取
    match = re.search(r'token=([^;&\s]+)', input_str)
    if match:
        return match.group(1)

    # 如果看起来像是原始 token（长度 > 50 且不包含特殊字符）
    if len(input_str) > 50 and not any(c in input_str for c in ['=', ';', '&', ' ', 'http']):
        return input_str

    return None


def parse_grab_output(output: str) -> dict:
    """解析领取输出"""
    result = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'coupons': []
    }

    lines = output.split('\n')
    for line in lines:
        if '成功' in line or '领取' in line:
            result['success'] += 1
            result['coupons'].append({'name': line.strip(), 'status': 'success'})
        elif '失败' in line or '错误' in line or '异常' in line:
            result['failed'] += 1
            result['coupons'].append({'name': line.strip(), 'status': 'failed'})

    result['total'] = result['success'] + result['failed']
    return result


# ==================== 页面路由 ====================

@app.route('/')
def index():
    """主页重定向"""
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))


@app.route('/login')
def login_page():
    """登录页面"""
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return render_template_string(LOGIN_TEMPLATE)


@app.route('/dashboard')
@login_required
def dashboard():
    """控制台主页"""
    return render_template_string(DASHBOARD_TEMPLATE)


# ==================== API 路由 ====================

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """登录 API"""
    data = request.get_json() or {}
    username = data.get('username', 'admin')
    password = data.get('password', '')

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        session['logged_in'] = True
        session['user_id'] = user.id
        session['username'] = user.username
        session['is_admin'] = user.is_admin

        user.last_login = datetime.now()
        db.session.commit()

        log_action('INFO', 'auth', f'用户 {username} 登录成功')
        return jsonify({"success": True, "message": "登录成功", "user": user.to_dict()})

    log_action('WARNING', 'auth', f'登录失败: {username}')
    return jsonify({"success": False, "message": "用户名或密码错误"}), 401


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """登出 API"""
    username = session.get('username', 'unknown')
    session.clear()
    log_action('INFO', 'auth', f'用户 {username} 已登出')
    return jsonify({"success": True, "message": "已登出"})


@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def api_change_password():
    """修改密码 API"""
    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if len(new_password) < 6:
        return jsonify({"success": False, "message": "新密码长度至少6位"}), 400

    user = User.query.get(session['user_id'])
    if not user.check_password(old_password):
        return jsonify({"success": False, "message": "原密码错误"}), 400

    user.set_password(new_password)
    db.session.commit()

    log_action('INFO', 'auth', '密码修改成功')
    return jsonify({"success": True, "message": "密码修改成功"})


@app.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    """仪表盘统计数据"""
    total_accounts = MeituanAccount.query.count()
    active_accounts = MeituanAccount.query.filter_by(is_active=True).count()
    total_grabs = GrabHistory.query.count()

    # 今日领取统计
    today = datetime.now().date()
    today_grabs = GrabHistory.query.filter(
        db.func.date(GrabHistory.grab_time) == today
    ).all()

    today_success = sum(h.success_count for h in today_grabs)
    today_failed = sum(h.failed_count for h in today_grabs)

    # 最近领取
    recent_grabs = GrabHistory.query.order_by(GrabHistory.grab_time.desc()).limit(5).all()

    # 系统状态
    cron_hours = SystemConfig.get('cron_hours', '8,14')

    return jsonify({
        "success": True,
        "data": {
            "accounts": {
                "total": total_accounts,
                "active": active_accounts
            },
            "today": {
                "total": len(today_grabs),
                "success": today_success,
                "failed": today_failed
            },
            "total_grabs": total_grabs,
            "cron_hours": cron_hours,
            "recent_grabs": [g.to_dict() for g in recent_grabs]
        }
    })


@app.route('/api/accounts', methods=['GET'])
@login_required
def api_get_accounts():
    """获取所有账号"""
    accounts = MeituanAccount.query.order_by(MeituanAccount.created_at.desc()).all()
    return jsonify({
        "success": True,
        "data": [a.to_dict() for a in accounts]
    })


@app.route('/api/accounts', methods=['POST'])
@login_required
def api_add_account():
    """添加账号"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    token_input = data.get('token', '').strip()

    if not name:
        return jsonify({"success": False, "message": "请输入账号名称"}), 400

    token = extract_token(token_input)
    if not token:
        return jsonify({"success": False, "message": "无法识别 Token，请检查输入格式"}), 400

    # 检查重复
    existing = MeituanAccount.query.filter_by(token=token).first()
    if existing:
        return jsonify({"success": False, "message": f"该 Token 已存在（账号: {existing.name}）"}), 400

    account = MeituanAccount(name=name, token=token)
    db.session.add(account)
    db.session.commit()

    log_action('INFO', 'account', f'添加账号: {name}')
    return jsonify({"success": True, "message": "添加成功", "data": account.to_dict()})


@app.route('/api/accounts/<int:account_id>', methods=['PUT'])
@login_required
def api_update_account(account_id):
    """更新账号"""
    account = MeituanAccount.query.get_or_404(account_id)
    data = request.get_json() or {}

    if 'name' in data:
        account.name = data['name'].strip()

    if 'token' in data:
        token = extract_token(data['token'].strip())
        if token:
            account.token = token

    if 'is_active' in data:
        account.is_active = data['is_active']

    db.session.commit()
    log_action('INFO', 'account', f'更新账号: {account.name}')
    return jsonify({"success": True, "message": "更新成功", "data": account.to_dict()})


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
@login_required
def api_delete_account(account_id):
    """删除账号"""
    account = MeituanAccount.query.get_or_404(account_id)
    name = account.name
    db.session.delete(account)
    db.session.commit()

    log_action('INFO', 'account', f'删除账号: {name}')
    return jsonify({"success": True, "message": "删除成功"})


@app.route('/api/grab/run', methods=['POST'])
@login_required
def api_run_grab():
    """手动执行领取"""
    data = request.get_json() or {}
    account_ids = data.get('account_ids', [])

    # 获取要执行的账号
    if account_ids:
        accounts = MeituanAccount.query.filter(
            MeituanAccount.id.in_(account_ids),
            MeituanAccount.is_active == True
        ).all()
    else:
        accounts = MeituanAccount.query.filter_by(is_active=True).all()

    if not accounts:
        return jsonify({"success": False, "message": "没有可执行的账号"}), 400

    results = []
    for account in accounts:
        account.last_run_at = datetime.now()
        account.last_run_status = 'running'
        db.session.commit()

        try:
            # 设置环境变量并执行
            env = os.environ.copy()
            env['MEITUAN_TOKEN'] = account.token

            result = subprocess.run(
                ['python', '/app/meituan.py'],
                capture_output=True,
                text=True,
                timeout=120,
                env=env
            )

            output = result.stdout + result.stderr
            parsed = parse_grab_output(output)

            # 记录历史
            history = GrabHistory(
                account_id=account.id,
                status='success' if parsed['success'] > 0 else 'failed',
                total_coupons=parsed['total'],
                success_count=parsed['success'],
                failed_count=parsed['failed'],
                details=json.dumps(parsed['coupons'], ensure_ascii=False),
                raw_output=output
            )
            db.session.add(history)

            account.last_run_status = 'success' if parsed['success'] > 0 else 'failed'
            results.append({
                'account': account.name,
                'status': account.last_run_status,
                'success': parsed['success'],
                'failed': parsed['failed']
            })

        except subprocess.TimeoutExpired:
            account.last_run_status = 'timeout'
            results.append({'account': account.name, 'status': 'timeout', 'error': '执行超时'})

        except Exception as e:
            account.last_run_status = 'failed'
            results.append({'account': account.name, 'status': 'failed', 'error': str(e)})

        db.session.commit()

    log_action('INFO', 'grab', f'手动执行领取，账号数: {len(accounts)}')
    return jsonify({"success": True, "message": "执行完成", "results": results})


@app.route('/api/history')
@login_required
def api_get_history():
    """获取领取历史"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    account_id = request.args.get('account_id', type=int)

    query = GrabHistory.query

    if account_id:
        query = query.filter_by(account_id=account_id)

    pagination = query.order_by(GrabHistory.grab_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "success": True,
        "data": [h.to_dict() for h in pagination.items],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages
        }
    })


@app.route('/api/logs')
@login_required
def api_get_logs():
    """获取系统日志"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    level = request.args.get('level', '')
    category = request.args.get('category', '')

    query = SystemLog.query

    if level:
        query = query.filter_by(level=level)
    if category:
        query = query.filter_by(category=category)

    pagination = query.order_by(SystemLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "success": True,
        "data": [l.to_dict() for l in pagination.items],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages
        }
    })


@app.route('/api/logs/file')
@login_required
def api_get_log_file():
    """获取日志文件内容"""
    lines = request.args.get('lines', 200, type=int)
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                content = ''.join(all_lines[-lines:])
        else:
            content = '暂无日志'
        return jsonify({"success": True, "data": content})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/config')
@login_required
def api_get_config():
    """获取系统配置"""
    configs = SystemConfig.query.all()
    return jsonify({
        "success": True,
        "data": {c.key: {'value': c.value, 'description': c.description} for c in configs}
    })


@app.route('/api/config', methods=['PUT'])
@login_required
def api_update_config():
    """更新系统配置"""
    data = request.get_json() or {}
    for key, value in data.items():
        SystemConfig.set(key, str(value))

    log_action('INFO', 'system', '更新系统配置')
    return jsonify({"success": True, "message": "配置已更新"})


# ==================== HTML 模板 ====================

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录 - 美团红包管理系统</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/remixicon@3.5.0/fonts/remixicon.css" rel="stylesheet">
    <style>
        .gradient-bg {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
    </style>
</head>
<body class="gradient-bg min-h-screen flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
        <div class="text-center mb-8">
            <div class="w-16 h-16 bg-gradient-to-r from-yellow-400 to-orange-500 rounded-full mx-auto flex items-center justify-center mb-4">
                <i class="ri-coupon-3-fill text-white text-3xl"></i>
            </div>
            <h1 class="text-2xl font-bold text-gray-800">美团红包管理系统</h1>
            <p class="text-gray-500 mt-2">企业级自动领取解决方案</p>
        </div>

        <form id="loginForm" class="space-y-6">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">用户名</label>
                <div class="relative">
                    <i class="ri-user-line absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"></i>
                    <input type="text" id="username" value="admin"
                        class="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent transition"
                        placeholder="请输入用户名">
                </div>
            </div>

            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">密码</label>
                <div class="relative">
                    <i class="ri-lock-line absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"></i>
                    <input type="password" id="password"
                        class="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent transition"
                        placeholder="请输入密码">
                </div>
            </div>

            <button type="submit"
                class="w-full bg-gradient-to-r from-purple-600 to-indigo-600 text-white py-3 rounded-lg font-medium hover:opacity-90 transition flex items-center justify-center">
                <i class="ri-login-box-line mr-2"></i>
                登录系统
            </button>
        </form>

        <div id="error" class="mt-4 p-3 bg-red-50 text-red-600 rounded-lg text-center hidden"></div>

        <div class="mt-6 text-center text-sm text-gray-500">
            <p>默认密码: admin123（请及时修改）</p>
        </div>
    </div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const errorDiv = document.getElementById('error');

            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password})
                });
                const data = await res.json();

                if (data.success) {
                    window.location.href = '/dashboard';
                } else {
                    errorDiv.textContent = data.message;
                    errorDiv.classList.remove('hidden');
                }
            } catch (err) {
                errorDiv.textContent = '网络错误，请重试';
                errorDiv.classList.remove('hidden');
            }
        });
    </script>
</body>
</html>
'''

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>控制台 - 美团红包管理系统</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/remixicon@3.5.0/fonts/remixicon.css" rel="stylesheet">
    <style>
        .sidebar-item.active { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .sidebar-item:hover:not(.active) { background: #f3f4f6; }
        .card-shadow { box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); }
        .status-success { color: #10b981; }
        .status-failed { color: #ef4444; }
        .status-running { color: #f59e0b; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .log-line { font-family: 'Monaco', 'Menlo', monospace; font-size: 12px; }
        .log-success { color: #10b981; }
        .log-error { color: #ef4444; }
        .log-warning { color: #f59e0b; }
        .log-info { color: #3b82f6; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <!-- 顶部导航 -->
    <nav class="bg-white shadow-sm fixed top-0 left-0 right-0 z-50">
        <div class="flex items-center justify-between px-6 py-3">
            <div class="flex items-center">
                <div class="w-10 h-10 bg-gradient-to-r from-yellow-400 to-orange-500 rounded-lg flex items-center justify-center mr-3">
                    <i class="ri-coupon-3-fill text-white text-xl"></i>
                </div>
                <span class="text-xl font-bold text-gray-800">美团红包管理系统</span>
                <span class="ml-3 px-2 py-1 bg-purple-100 text-purple-600 text-xs rounded-full">企业版</span>
            </div>
            <div class="flex items-center space-x-4">
                <span class="text-gray-600" id="current-user"><i class="ri-user-line mr-1"></i>admin</span>
                <button onclick="logout()" class="text-gray-500 hover:text-red-500 transition">
                    <i class="ri-logout-box-line text-xl"></i>
                </button>
            </div>
        </div>
    </nav>

    <div class="flex pt-16">
        <!-- 侧边栏 -->
        <aside class="w-64 bg-white shadow-sm fixed left-0 top-16 bottom-0 overflow-y-auto">
            <nav class="p-4 space-y-2">
                <a href="#" onclick="showTab('dashboard')" class="sidebar-item active flex items-center px-4 py-3 rounded-lg transition" data-tab="dashboard">
                    <i class="ri-dashboard-line text-xl mr-3"></i>
                    <span>仪表盘</span>
                </a>
                <a href="#" onclick="showTab('accounts')" class="sidebar-item flex items-center px-4 py-3 rounded-lg transition" data-tab="accounts">
                    <i class="ri-account-circle-line text-xl mr-3"></i>
                    <span>账号管理</span>
                </a>
                <a href="#" onclick="showTab('history')" class="sidebar-item flex items-center px-4 py-3 rounded-lg transition" data-tab="history">
                    <i class="ri-history-line text-xl mr-3"></i>
                    <span>领取历史</span>
                </a>
                <a href="#" onclick="showTab('logs')" class="sidebar-item flex items-center px-4 py-3 rounded-lg transition" data-tab="logs">
                    <i class="ri-file-text-line text-xl mr-3"></i>
                    <span>运行日志</span>
                </a>
                <a href="#" onclick="showTab('settings')" class="sidebar-item flex items-center px-4 py-3 rounded-lg transition" data-tab="settings">
                    <i class="ri-settings-3-line text-xl mr-3"></i>
                    <span>系统设置</span>
                </a>
                <a href="#" onclick="showTab('help')" class="sidebar-item flex items-center px-4 py-3 rounded-lg transition" data-tab="help">
                    <i class="ri-question-line text-xl mr-3"></i>
                    <span>使用帮助</span>
                </a>
            </nav>
        </aside>

        <!-- 主内容区 -->
        <main class="flex-1 ml-64 p-6">
            <!-- 仪表盘 -->
            <div id="tab-dashboard" class="tab-content active">
                <div class="flex items-center justify-between mb-6">
                    <h1 class="text-2xl font-bold text-gray-800">仪表盘</h1>
                    <button onclick="runGrab()" class="bg-gradient-to-r from-purple-600 to-indigo-600 text-white px-6 py-2 rounded-lg hover:opacity-90 transition flex items-center">
                        <i class="ri-play-fill mr-2"></i>立即执行
                    </button>
                </div>

                <!-- 统计卡片 -->
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
                    <div class="bg-white rounded-xl p-6 card-shadow">
                        <div class="flex items-center justify-between">
                            <div>
                                <p class="text-gray-500 text-sm">账号总数</p>
                                <p class="text-3xl font-bold text-gray-800 mt-1" id="stat-accounts">-</p>
                            </div>
                            <div class="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                                <i class="ri-user-line text-blue-600 text-2xl"></i>
                            </div>
                        </div>
                    </div>
                    <div class="bg-white rounded-xl p-6 card-shadow">
                        <div class="flex items-center justify-between">
                            <div>
                                <p class="text-gray-500 text-sm">今日领取</p>
                                <p class="text-3xl font-bold text-green-600 mt-1" id="stat-today">-</p>
                            </div>
                            <div class="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                                <i class="ri-gift-line text-green-600 text-2xl"></i>
                            </div>
                        </div>
                    </div>
                    <div class="bg-white rounded-xl p-6 card-shadow">
                        <div class="flex items-center justify-between">
                            <div>
                                <p class="text-gray-500 text-sm">累计领取</p>
                                <p class="text-3xl font-bold text-purple-600 mt-1" id="stat-total">-</p>
                            </div>
                            <div class="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center">
                                <i class="ri-stack-line text-purple-600 text-2xl"></i>
                            </div>
                        </div>
                    </div>
                    <div class="bg-white rounded-xl p-6 card-shadow">
                        <div class="flex items-center justify-between">
                            <div>
                                <p class="text-gray-500 text-sm">定时任务</p>
                                <p class="text-xl font-bold text-gray-800 mt-1" id="stat-cron">-</p>
                            </div>
                            <div class="w-12 h-12 bg-orange-100 rounded-full flex items-center justify-center">
                                <i class="ri-time-line text-orange-600 text-2xl"></i>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 最近领取记录 -->
                <div class="bg-white rounded-xl card-shadow">
                    <div class="px-6 py-4 border-b border-gray-100">
                        <h2 class="text-lg font-semibold text-gray-800">最近领取记录</h2>
                    </div>
                    <div class="p-6">
                        <div id="recent-grabs" class="space-y-4">
                            <p class="text-gray-500 text-center py-8">暂无记录</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 账号管理 -->
            <div id="tab-accounts" class="tab-content">
                <div class="flex items-center justify-between mb-6">
                    <h1 class="text-2xl font-bold text-gray-800">账号管理</h1>
                    <button onclick="showAddAccountModal()" class="bg-gradient-to-r from-purple-600 to-indigo-600 text-white px-6 py-2 rounded-lg hover:opacity-90 transition flex items-center">
                        <i class="ri-add-line mr-2"></i>添加账号
                    </button>
                </div>

                <div class="bg-white rounded-xl card-shadow">
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">账号名称</th>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">Token</th>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">状态</th>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">最后执行</th>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">操作</th>
                                </tr>
                            </thead>
                            <tbody id="accounts-table" class="divide-y divide-gray-100">
                                <tr><td colspan="5" class="px-6 py-8 text-center text-gray-500">加载中...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- 领取历史 -->
            <div id="tab-history" class="tab-content">
                <h1 class="text-2xl font-bold text-gray-800 mb-6">领取历史</h1>

                <div class="bg-white rounded-xl card-shadow">
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">时间</th>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">账号</th>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">状态</th>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">成功/失败</th>
                                    <th class="px-6 py-4 text-left text-sm font-semibold text-gray-600">详情</th>
                                </tr>
                            </thead>
                            <tbody id="history-table" class="divide-y divide-gray-100">
                                <tr><td colspan="5" class="px-6 py-8 text-center text-gray-500">加载中...</td></tr>
                            </tbody>
                        </table>
                    </div>
                    <div id="history-pagination" class="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
                    </div>
                </div>
            </div>

            <!-- 运行日志 -->
            <div id="tab-logs" class="tab-content">
                <div class="flex items-center justify-between mb-6">
                    <h1 class="text-2xl font-bold text-gray-800">运行日志</h1>
                    <div class="flex items-center space-x-4">
                        <select id="log-filter" onchange="loadLogs()" class="border border-gray-300 rounded-lg px-4 py-2">
                            <option value="">全部日志</option>
                            <option value="INFO">INFO</option>
                            <option value="WARNING">WARNING</option>
                            <option value="ERROR">ERROR</option>
                        </select>
                        <button onclick="loadLogFile()" class="bg-gray-100 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-200 transition">
                            <i class="ri-refresh-line mr-2"></i>刷新
                        </button>
                    </div>
                </div>

                <div class="bg-white rounded-xl card-shadow mb-6">
                    <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                        <h2 class="text-lg font-semibold text-gray-800">系统操作日志</h2>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-3 text-left text-sm font-semibold text-gray-600">时间</th>
                                    <th class="px-6 py-3 text-left text-sm font-semibold text-gray-600">级别</th>
                                    <th class="px-6 py-3 text-left text-sm font-semibold text-gray-600">类别</th>
                                    <th class="px-6 py-3 text-left text-sm font-semibold text-gray-600">消息</th>
                                </tr>
                            </thead>
                            <tbody id="logs-table" class="divide-y divide-gray-100 text-sm">
                                <tr><td colspan="4" class="px-6 py-8 text-center text-gray-500">加载中...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="bg-white rounded-xl card-shadow">
                    <div class="px-6 py-4 border-b border-gray-100">
                        <h2 class="text-lg font-semibold text-gray-800">执行输出日志</h2>
                    </div>
                    <div class="p-4 bg-gray-900 rounded-b-xl max-h-96 overflow-y-auto">
                        <pre id="log-file-content" class="text-gray-300 log-line whitespace-pre-wrap">加载中...</pre>
                    </div>
                </div>
            </div>

            <!-- 系统设置 -->
            <div id="tab-settings" class="tab-content">
                <h1 class="text-2xl font-bold text-gray-800 mb-6">系统设置</h1>

                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- 定时任务设置 -->
                    <div class="bg-white rounded-xl card-shadow">
                        <div class="px-6 py-4 border-b border-gray-100">
                            <h2 class="text-lg font-semibold text-gray-800">定时任务</h2>
                        </div>
                        <div class="p-6 space-y-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">执行时间（小时）</label>
                                <input type="text" id="config-cron-hours" class="w-full px-4 py-2 border border-gray-300 rounded-lg" placeholder="8,14">
                                <p class="text-xs text-gray-500 mt-1">多个小时用逗号分隔，如: 8,14,20</p>
                            </div>
                            <button onclick="saveConfig()" class="bg-purple-600 text-white px-6 py-2 rounded-lg hover:bg-purple-700 transition">
                                保存设置
                            </button>
                        </div>
                    </div>

                    <!-- 修改密码 -->
                    <div class="bg-white rounded-xl card-shadow">
                        <div class="px-6 py-4 border-b border-gray-100">
                            <h2 class="text-lg font-semibold text-gray-800">修改密码</h2>
                        </div>
                        <div class="p-6 space-y-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">原密码</label>
                                <input type="password" id="old-password" class="w-full px-4 py-2 border border-gray-300 rounded-lg">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">新密码</label>
                                <input type="password" id="new-password" class="w-full px-4 py-2 border border-gray-300 rounded-lg">
                            </div>
                            <button onclick="changePassword()" class="bg-purple-600 text-white px-6 py-2 rounded-lg hover:bg-purple-700 transition">
                                修改密码
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 使用帮助 -->
            <div id="tab-help" class="tab-content">
                <h1 class="text-2xl font-bold text-gray-800 mb-6">使用帮助</h1>

                <div class="space-y-6">
                    <!-- Token 获取教程 -->
                    <div class="bg-white rounded-xl card-shadow">
                        <div class="px-6 py-4 border-b border-gray-100 flex items-center">
                            <i class="ri-key-2-line text-2xl text-purple-600 mr-3"></i>
                            <h2 class="text-lg font-semibold text-gray-800">如何获取美团 Token</h2>
                        </div>
                        <div class="p-6">
                            <div class="space-y-6">
                                <!-- 方法一 -->
                                <div class="border-l-4 border-purple-500 pl-4">
                                    <h3 class="font-semibold text-gray-800 mb-3">
                                        <span class="bg-purple-100 text-purple-600 px-2 py-1 rounded text-sm mr-2">方法一</span>
                                        手机抓包（推荐）
                                    </h3>
                                    <div class="space-y-2 text-gray-600">
                                        <p><strong>准备工具：</strong></p>
                                        <ul class="list-disc list-inside ml-4 space-y-1">
                                            <li>安卓手机：HttpCanary / Packet Capture</li>
                                            <li>苹果手机：Stream / Thor</li>
                                        </ul>
                                        <p class="mt-3"><strong>操作步骤：</strong></p>
                                        <ol class="list-decimal list-inside ml-4 space-y-2">
                                            <li>安装抓包工具并配置好证书</li>
                                            <li>打开抓包，然后打开<strong>微信小程序</strong>中的「美团外卖」</li>
                                            <li>随便点击几个页面，产生网络请求</li>
                                            <li>在抓包工具中搜索 <code class="bg-gray-100 px-2 py-1 rounded">meituan.com</code> 的请求</li>
                                            <li>找到请求头（Headers）中的 <code class="bg-gray-100 px-2 py-1 rounded">token</code> 字段，复制其值</li>
                                        </ol>
                                    </div>
                                </div>

                                <!-- 方法二 -->
                                <div class="border-l-4 border-blue-500 pl-4">
                                    <h3 class="font-semibold text-gray-800 mb-3">
                                        <span class="bg-blue-100 text-blue-600 px-2 py-1 rounded text-sm mr-2">方法二</span>
                                        电脑浏览器抓包
                                    </h3>
                                    <div class="space-y-2 text-gray-600">
                                        <ol class="list-decimal list-inside ml-4 space-y-2">
                                            <li>打开 Chrome 浏览器，按 <code class="bg-gray-100 px-2 py-1 rounded">F12</code> 打开开发者工具</li>
                                            <li>切换到 <code class="bg-gray-100 px-2 py-1 rounded">Network</code>（网络）标签</li>
                                            <li>访问 <a href="https://h5.waimai.meituan.com/waimai/mindex/home" target="_blank" class="text-blue-600 hover:underline">https://h5.waimai.meituan.com</a></li>
                                            <li>如果未登录，扫码登录</li>
                                            <li>在 Network 中找到任意 <code class="bg-gray-100 px-2 py-1 rounded">meituan.com</code> 的请求</li>
                                            <li>点击请求，在 Headers 中找到 <code class="bg-gray-100 px-2 py-1 rounded">Cookie</code></li>
                                            <li>复制 <code class="bg-gray-100 px-2 py-1 rounded">token=</code> 后面的值（到下一个分号 <code class="bg-gray-100 px-2 py-1 rounded">;</code> 之前）</li>
                                        </ol>
                                    </div>
                                </div>

                                <!-- Cookie 示例 -->
                                <div class="bg-gray-50 rounded-lg p-4">
                                    <p class="font-semibold text-gray-700 mb-2">Cookie 示例：</p>
                                    <code class="block bg-gray-800 text-green-400 p-3 rounded text-sm overflow-x-auto">
                                        token=AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI_TJ8W51Cbj...; other=xxx
                                    </code>
                                    <p class="text-gray-600 mt-2">你需要复制的是：</p>
                                    <code class="block bg-gray-800 text-yellow-400 p-3 rounded text-sm mt-1">
                                        AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI_TJ8W51Cbj...
                                    </code>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Token 输入说明 -->
                    <div class="bg-white rounded-xl card-shadow">
                        <div class="px-6 py-4 border-b border-gray-100 flex items-center">
                            <i class="ri-input-method-line text-2xl text-green-600 mr-3"></i>
                            <h2 class="text-lg font-semibold text-gray-800">Token 输入格式</h2>
                        </div>
                        <div class="p-6">
                            <p class="text-gray-600 mb-4">添加账号时，系统支持以下输入格式，会自动识别并提取 Token：</p>
                            <div class="space-y-4">
                                <div class="flex items-start">
                                    <span class="bg-green-100 text-green-600 px-2 py-1 rounded text-sm font-medium mr-3">1</span>
                                    <div>
                                        <p class="font-medium text-gray-800">直接粘贴 Token</p>
                                        <code class="text-sm text-gray-500">AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI_TJ8W51Cbj...</code>
                                    </div>
                                </div>
                                <div class="flex items-start">
                                    <span class="bg-green-100 text-green-600 px-2 py-1 rounded text-sm font-medium mr-3">2</span>
                                    <div>
                                        <p class="font-medium text-gray-800">粘贴 Cookie 字符串</p>
                                        <code class="text-sm text-gray-500">token=AgGYIaHEzI...; other=xxx</code>
                                    </div>
                                </div>
                                <div class="flex items-start">
                                    <span class="bg-green-100 text-green-600 px-2 py-1 rounded text-sm font-medium mr-3">3</span>
                                    <div>
                                        <p class="font-medium text-gray-800">粘贴完整 URL</p>
                                        <code class="text-sm text-gray-500">https://h5.waimai.meituan.com/...?token=AgGYIaHEzI...</code>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 常见问题 -->
                    <div class="bg-white rounded-xl card-shadow">
                        <div class="px-6 py-4 border-b border-gray-100 flex items-center">
                            <i class="ri-question-answer-line text-2xl text-orange-600 mr-3"></i>
                            <h2 class="text-lg font-semibold text-gray-800">常见问题</h2>
                        </div>
                        <div class="p-6 space-y-4">
                            <div class="border-b border-gray-100 pb-4">
                                <p class="font-medium text-gray-800">Q: Token 多久失效？</p>
                                <p class="text-gray-600 mt-1">A: Token 有效期约 30 天，失效后需要重新获取。</p>
                            </div>
                            <div class="border-b border-gray-100 pb-4">
                                <p class="font-medium text-gray-800">Q: 提示"请求异常"怎么办？</p>
                                <p class="text-gray-600 mt-1">A: 可能原因：1. 服务器在国外（美团屏蔽海外IP）2. Token 失效 3. 网络问题</p>
                            </div>
                            <div class="border-b border-gray-100 pb-4">
                                <p class="font-medium text-gray-800">Q: 支持哪些红包？</p>
                                <p class="text-gray-600 mt-1">A: 外卖满减红包、外卖神券、闪购红包、团购红包、各类商家粮票等。</p>
                            </div>
                            <div>
                                <p class="font-medium text-gray-800">Q: 定时任务什么时候执行？</p>
                                <p class="text-gray-600 mt-1">A: 默认每天北京时间 8:00 和 14:00 执行，可在系统设置中修改。</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <!-- 添加账号弹窗 -->
    <div id="add-account-modal" class="fixed inset-0 bg-black bg-opacity-50 hidden items-center justify-center z-50">
        <div class="bg-white rounded-xl w-full max-w-lg mx-4 overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <h3 class="text-lg font-semibold text-gray-800">添加美团账号</h3>
                <button onclick="hideAddAccountModal()" class="text-gray-400 hover:text-gray-600">
                    <i class="ri-close-line text-2xl"></i>
                </button>
            </div>
            <div class="p-6 space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">账号名称 <span class="text-red-500">*</span></label>
                    <input type="text" id="account-name" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent" placeholder="如：我的账号、老婆账号">
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Token <span class="text-red-500">*</span></label>
                    <textarea id="account-token" rows="4" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent" placeholder="直接粘贴 Token、Cookie 或 URL，系统会自动识别"></textarea>
                    <p class="text-xs text-gray-500 mt-1">支持直接粘贴 Token、Cookie 字符串或完整 URL</p>
                </div>
            </div>
            <div class="px-6 py-4 bg-gray-50 flex justify-end space-x-3">
                <button onclick="hideAddAccountModal()" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 transition">取消</button>
                <button onclick="addAccount()" class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition">添加</button>
            </div>
        </div>
    </div>

    <!-- 详情弹窗 -->
    <div id="detail-modal" class="fixed inset-0 bg-black bg-opacity-50 hidden items-center justify-center z-50">
        <div class="bg-white rounded-xl w-full max-w-2xl mx-4 max-h-[80vh] overflow-hidden flex flex-col">
            <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <h3 class="text-lg font-semibold text-gray-800">领取详情</h3>
                <button onclick="hideDetailModal()" class="text-gray-400 hover:text-gray-600">
                    <i class="ri-close-line text-2xl"></i>
                </button>
            </div>
            <div id="detail-content" class="p-6 overflow-y-auto flex-1">
            </div>
        </div>
    </div>

    <!-- Toast 提示 -->
    <div id="toast" class="fixed top-4 right-4 bg-gray-800 text-white px-6 py-3 rounded-lg shadow-lg hidden z-50 transition-all transform translate-x-full">
        <span id="toast-message"></span>
    </div>

    <script>
        // ==================== 工具函数 ====================
        function showToast(message, type = 'info') {
            const toast = document.getElementById('toast');
            const toastMessage = document.getElementById('toast-message');
            toastMessage.textContent = message;

            toast.className = 'fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 transition-all transform';
            if (type === 'success') toast.classList.add('bg-green-600', 'text-white');
            else if (type === 'error') toast.classList.add('bg-red-600', 'text-white');
            else toast.classList.add('bg-gray-800', 'text-white');

            toast.classList.remove('hidden', 'translate-x-full');
            setTimeout(() => {
                toast.classList.add('translate-x-full');
                setTimeout(() => toast.classList.add('hidden'), 300);
            }, 3000);
        }

        async function api(url, options = {}) {
            try {
                const res = await fetch(url, {
                    headers: {'Content-Type': 'application/json', ...options.headers},
                    ...options
                });
                const data = await res.json();
                if (res.status === 401) {
                    window.location.href = '/login';
                    return null;
                }
                return data;
            } catch (err) {
                showToast('网络错误', 'error');
                return null;
            }
        }

        // ==================== Tab 切换 ====================
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));

            document.getElementById('tab-' + tabName).classList.add('active');
            document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

            // 加载对应数据
            if (tabName === 'dashboard') loadDashboard();
            else if (tabName === 'accounts') loadAccounts();
            else if (tabName === 'history') loadHistory();
            else if (tabName === 'logs') { loadLogs(); loadLogFile(); }
            else if (tabName === 'settings') loadConfig();
        }

        // ==================== 仪表盘 ====================
        async function loadDashboard() {
            const data = await api('/api/dashboard/stats');
            if (!data || !data.success) return;

            const stats = data.data;
            document.getElementById('stat-accounts').textContent = stats.accounts.total;
            document.getElementById('stat-today').textContent = stats.today.success;
            document.getElementById('stat-total').textContent = stats.total_grabs;
            document.getElementById('stat-cron').textContent = stats.cron_hours + ' 点';

            // 最近记录
            const container = document.getElementById('recent-grabs');
            if (stats.recent_grabs.length === 0) {
                container.innerHTML = '<p class="text-gray-500 text-center py-8">暂无记录</p>';
            } else {
                container.innerHTML = stats.recent_grabs.map(g => `
                    <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                        <div class="flex items-center">
                            <div class="w-10 h-10 bg-purple-100 rounded-full flex items-center justify-center mr-4">
                                <i class="ri-user-line text-purple-600"></i>
                            </div>
                            <div>
                                <p class="font-medium text-gray-800">${g.account_name}</p>
                                <p class="text-sm text-gray-500">${g.grab_time}</p>
                            </div>
                        </div>
                        <div class="text-right">
                            <span class="status-${g.status}">${g.status === 'success' ? '成功' : '失败'}</span>
                            <p class="text-sm text-gray-500">成功 ${g.success_count} / 失败 ${g.failed_count}</p>
                        </div>
                    </div>
                `).join('');
            }
        }

        // ==================== 账号管理 ====================
        async function loadAccounts() {
            const data = await api('/api/accounts');
            if (!data || !data.success) return;

            const tbody = document.getElementById('accounts-table');
            if (data.data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-8 text-center text-gray-500">暂无账号，点击右上角添加</td></tr>';
            } else {
                tbody.innerHTML = data.data.map(a => `
                    <tr>
                        <td class="px-6 py-4">
                            <div class="font-medium text-gray-800">${a.name}</div>
                        </td>
                        <td class="px-6 py-4">
                            <code class="text-sm text-gray-500">${a.token}</code>
                        </td>
                        <td class="px-6 py-4">
                            <span class="px-2 py-1 rounded-full text-xs ${a.is_active ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-600'}">
                                ${a.is_active ? '启用' : '禁用'}
                            </span>
                        </td>
                        <td class="px-6 py-4 text-sm text-gray-500">
                            ${a.last_run_at || '从未执行'}
                            ${a.last_run_status ? `<span class="status-${a.last_run_status} ml-2">${a.last_run_status}</span>` : ''}
                        </td>
                        <td class="px-6 py-4">
                            <button onclick="toggleAccount(${a.id}, ${!a.is_active})" class="text-blue-600 hover:text-blue-800 mr-3">
                                ${a.is_active ? '禁用' : '启用'}
                            </button>
                            <button onclick="deleteAccount(${a.id}, '${a.name}')" class="text-red-600 hover:text-red-800">
                                删除
                            </button>
                        </td>
                    </tr>
                `).join('');
            }
        }

        function showAddAccountModal() {
            document.getElementById('add-account-modal').classList.remove('hidden');
            document.getElementById('add-account-modal').classList.add('flex');
        }

        function hideAddAccountModal() {
            document.getElementById('add-account-modal').classList.add('hidden');
            document.getElementById('add-account-modal').classList.remove('flex');
            document.getElementById('account-name').value = '';
            document.getElementById('account-token').value = '';
        }

        async function addAccount() {
            const name = document.getElementById('account-name').value.trim();
            const token = document.getElementById('account-token').value.trim();

            if (!name || !token) {
                showToast('请填写完整信息', 'error');
                return;
            }

            const data = await api('/api/accounts', {
                method: 'POST',
                body: JSON.stringify({name, token})
            });

            if (data && data.success) {
                showToast('添加成功', 'success');
                hideAddAccountModal();
                loadAccounts();
            } else {
                showToast(data?.message || '添加失败', 'error');
            }
        }

        async function toggleAccount(id, isActive) {
            const data = await api(`/api/accounts/${id}`, {
                method: 'PUT',
                body: JSON.stringify({is_active: isActive})
            });

            if (data && data.success) {
                showToast('操作成功', 'success');
                loadAccounts();
            }
        }

        async function deleteAccount(id, name) {
            if (!confirm(`确定删除账号 "${name}" 吗？`)) return;

            const data = await api(`/api/accounts/${id}`, {method: 'DELETE'});
            if (data && data.success) {
                showToast('删除成功', 'success');
                loadAccounts();
            }
        }

        // ==================== 领取历史 ====================
        let historyPage = 1;

        async function loadHistory(page = 1) {
            historyPage = page;
            const data = await api(`/api/history?page=${page}&per_page=20`);
            if (!data || !data.success) return;

            const tbody = document.getElementById('history-table');
            if (data.data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-8 text-center text-gray-500">暂无历史记录</td></tr>';
            } else {
                tbody.innerHTML = data.data.map(h => `
                    <tr>
                        <td class="px-6 py-4 text-sm text-gray-600">${h.grab_time}</td>
                        <td class="px-6 py-4 font-medium text-gray-800">${h.account_name}</td>
                        <td class="px-6 py-4">
                            <span class="px-2 py-1 rounded-full text-xs ${h.status === 'success' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}">
                                ${h.status === 'success' ? '成功' : '失败'}
                            </span>
                        </td>
                        <td class="px-6 py-4 text-sm">
                            <span class="text-green-600">${h.success_count}</span> /
                            <span class="text-red-600">${h.failed_count}</span>
                        </td>
                        <td class="px-6 py-4">
                            <button onclick="showDetail(${h.id})" class="text-blue-600 hover:text-blue-800 text-sm">
                                查看详情
                            </button>
                        </td>
                    </tr>
                `).join('');
            }

            // 分页
            const pagination = data.pagination;
            const paginationEl = document.getElementById('history-pagination');
            if (pagination.pages > 1) {
                paginationEl.innerHTML = `
                    <span class="text-sm text-gray-500">共 ${pagination.total} 条记录</span>
                    <div class="flex space-x-2">
                        ${pagination.page > 1 ? `<button onclick="loadHistory(${pagination.page - 1})" class="px-3 py-1 border rounded hover:bg-gray-100">上一页</button>` : ''}
                        <span class="px-3 py-1">第 ${pagination.page} / ${pagination.pages} 页</span>
                        ${pagination.page < pagination.pages ? `<button onclick="loadHistory(${pagination.page + 1})" class="px-3 py-1 border rounded hover:bg-gray-100">下一页</button>` : ''}
                    </div>
                `;
            } else {
                paginationEl.innerHTML = '';
            }
        }

        function showDetail(historyId) {
            const modal = document.getElementById('detail-modal');
            modal.classList.remove('hidden');
            modal.classList.add('flex');

            document.getElementById('detail-content').innerHTML = '<p class="text-gray-500">加载中...</p>';

            api(`/api/history?page=1&per_page=100`).then(data => {
                if (data && data.success) {
                    const history = data.data.find(h => h.id === historyId);
                    if (history) {
                        let details = '';
                        try {
                            const coupons = JSON.parse(history.details || '[]');
                            details = coupons.map(c => `
                                <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg mb-2">
                                    <span class="text-gray-800">${c.name}</span>
                                    <span class="${c.status === 'success' ? 'text-green-600' : 'text-red-600'}">${c.status === 'success' ? '成功' : '失败'}</span>
                                </div>
                            `).join('');
                        } catch (e) {}

                        document.getElementById('detail-content').innerHTML = `
                            <div class="space-y-4">
                                <div class="grid grid-cols-2 gap-4">
                                    <div class="bg-gray-50 p-4 rounded-lg">
                                        <p class="text-sm text-gray-500">账号</p>
                                        <p class="font-medium text-gray-800">${history.account_name}</p>
                                    </div>
                                    <div class="bg-gray-50 p-4 rounded-lg">
                                        <p class="text-sm text-gray-500">时间</p>
                                        <p class="font-medium text-gray-800">${history.grab_time}</p>
                                    </div>
                                    <div class="bg-gray-50 p-4 rounded-lg">
                                        <p class="text-sm text-gray-500">成功数</p>
                                        <p class="font-medium text-green-600">${history.success_count}</p>
                                    </div>
                                    <div class="bg-gray-50 p-4 rounded-lg">
                                        <p class="text-sm text-gray-500">失败数</p>
                                        <p class="font-medium text-red-600">${history.failed_count}</p>
                                    </div>
                                </div>
                                ${details ? `<div><p class="font-medium text-gray-800 mb-2">领取详情</p>${details}</div>` : ''}
                                ${history.raw_output ? `
                                    <div>
                                        <p class="font-medium text-gray-800 mb-2">原始输出</p>
                                        <pre class="bg-gray-900 text-gray-300 p-4 rounded-lg text-sm overflow-x-auto max-h-60">${history.raw_output}</pre>
                                    </div>
                                ` : ''}
                            </div>
                        `;
                    }
                }
            });
        }

        function hideDetailModal() {
            document.getElementById('detail-modal').classList.add('hidden');
            document.getElementById('detail-modal').classList.remove('flex');
        }

        // ==================== 日志 ====================
        async function loadLogs() {
            const level = document.getElementById('log-filter').value;
            const data = await api(`/api/logs?level=${level}&per_page=50`);
            if (!data || !data.success) return;

            const tbody = document.getElementById('logs-table');
            if (data.data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-8 text-center text-gray-500">暂无日志</td></tr>';
            } else {
                tbody.innerHTML = data.data.map(l => `
                    <tr>
                        <td class="px-6 py-3 text-gray-600">${l.created_at}</td>
                        <td class="px-6 py-3">
                            <span class="log-${l.level.toLowerCase()}">${l.level}</span>
                        </td>
                        <td class="px-6 py-3 text-gray-600">${l.category}</td>
                        <td class="px-6 py-3 text-gray-800">${l.message}</td>
                    </tr>
                `).join('');
            }
        }

        async function loadLogFile() {
            const data = await api('/api/logs/file?lines=200');
            if (data && data.success) {
                const content = data.data || '暂无日志';
                const highlighted = content
                    .replace(/(成功|领取)/g, '<span class="log-success">$1</span>')
                    .replace(/(失败|错误|异常|Error)/g, '<span class="log-error">$1</span>')
                    .replace(/(警告|Warning)/g, '<span class="log-warning">$1</span>');
                document.getElementById('log-file-content').innerHTML = highlighted;
            }
        }

        // ==================== 设置 ====================
        async function loadConfig() {
            const data = await api('/api/config');
            if (data && data.success) {
                const configs = data.data;
                if (configs.cron_hours) {
                    document.getElementById('config-cron-hours').value = configs.cron_hours.value;
                }
            }
        }

        async function saveConfig() {
            const cronHours = document.getElementById('config-cron-hours').value;
            const data = await api('/api/config', {
                method: 'PUT',
                body: JSON.stringify({cron_hours: cronHours})
            });

            if (data && data.success) {
                showToast('设置已保存', 'success');
            }
        }

        async function changePassword() {
            const oldPassword = document.getElementById('old-password').value;
            const newPassword = document.getElementById('new-password').value;

            if (!oldPassword || !newPassword) {
                showToast('请填写完整', 'error');
                return;
            }

            const data = await api('/api/auth/change-password', {
                method: 'POST',
                body: JSON.stringify({old_password: oldPassword, new_password: newPassword})
            });

            if (data && data.success) {
                showToast('密码修改成功', 'success');
                document.getElementById('old-password').value = '';
                document.getElementById('new-password').value = '';
            } else {
                showToast(data?.message || '修改失败', 'error');
            }
        }

        // ==================== 执行领取 ====================
        async function runGrab() {
            showToast('开始执行...', 'info');
            const data = await api('/api/grab/run', {method: 'POST'});

            if (data && data.success) {
                const results = data.results || [];
                const successCount = results.filter(r => r.status === 'success').length;
                showToast(`执行完成，成功 ${successCount}/${results.length}`, 'success');
                loadDashboard();
            } else {
                showToast(data?.message || '执行失败', 'error');
            }
        }

        // ==================== 登出 ====================
        async function logout() {
            await api('/api/auth/logout', {method: 'POST'});
            window.location.href = '/login';
        }

        // ==================== 初始化 ====================
        document.addEventListener('DOMContentLoaded', () => {
            loadDashboard();
        });
    </script>
</body>
</html>
'''


# ==================== 初始化 ====================
init_db(app)

if __name__ == '__main__':
    port = int(os.environ.get('WEB_PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
