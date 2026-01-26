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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = '/app/data' if os.path.exists('/app') else os.path.join(SCRIPT_DIR, 'data')
DATA_DIR = os.environ.get('DATA_DIR', DEFAULT_DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.environ.get('DB_PATH', f'{DATA_DIR}/meituan.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

DEFAULT_LOG_FILE = '/var/log/meituan/coupons.log' if os.path.exists('/var/log/meituan') else os.path.join(SCRIPT_DIR, 'coupons.log')
LOG_FILE = os.environ.get('LOG_FILE', DEFAULT_LOG_FILE)


def log_action(level: str, category: str, message: str, details: str = None):
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
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json or request.headers.get('Accept') == 'application/json':
                return jsonify({"success": False, "message": "请先登录", "code": 401}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({"success": False, "message": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated_function


def get_user_account_ids():
    if session.get('is_admin'):
        return None
    accounts = MeituanAccount.query.filter_by(user_id=session['user_id']).all()
    return [a.id for a in accounts]


def extract_token(input_str: str) -> str:
    if not input_str:
        return None
    input_str = input_str.strip()
    match = re.search(r'token=([^;&\s]+)', input_str)
    if match:
        return match.group(1)
    if len(input_str) > 50 and not any(c in input_str for c in ['=', ';', '&', ' ', 'http']):
        return input_str
    return None


def parse_grab_output(output: str) -> dict:
    result = {'total': 0, 'success': 0, 'failed': 0, 'coupons': []}
    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue
        # 先检查失败，因为"领取失败"同时包含"领取"和"失败"
        if '失败' in line or '错误' in line or '异常' in line:
            result['failed'] += 1
            result['coupons'].append({'name': line, 'status': 'failed'})
        elif '成功领取' in line:
            result['success'] += 1
            result['coupons'].append({'name': line, 'status': 'success'})
    result['total'] = result['success'] + result['failed']
    return result


@app.route('/')
def index():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))


@app.route('/login')
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return render_template_string(LOGIN_TEMPLATE)


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template_string(DASHBOARD_TEMPLATE)


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username:
        return jsonify({"success": False, "message": "请输入用户名"}), 400

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


@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or len(username) < 3:
        return jsonify({"success": False, "message": "用户名至少3个字符"}), 400
    if not password or len(password) < 6:
        return jsonify({"success": False, "message": "密码至少6个字符"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "用户名已存在"}), 400

    user = User(username=username, is_admin=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    log_action('INFO', 'auth', f'新用户注册: {username}')
    return jsonify({"success": True, "message": "注册成功，请登录"})


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    username = session.get('username', 'unknown')
    session.clear()
    log_action('INFO', 'auth', f'用户 {username} 登出')
    return jsonify({"success": True, "message": "已登出"})


@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def api_change_password():
    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if len(new_password) < 6:
        return jsonify({"success": False, "message": "新密码至少6位"}), 400

    user = User.query.get(session['user_id'])
    if not user.check_password(old_password):
        return jsonify({"success": False, "message": "原密码错误"}), 400

    user.set_password(new_password)
    db.session.commit()
    log_action('INFO', 'auth', '密码修改成功')
    return jsonify({"success": True, "message": "密码修改成功"})


@app.route('/api/auth/me')
@login_required
def api_me():
    user = User.query.get(session['user_id'])
    return jsonify({"success": True, "data": user.to_dict()})


@app.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    user_id = session['user_id']
    is_admin = session.get('is_admin')

    if is_admin:
        accounts_query = MeituanAccount.query
        history_query = GrabHistory.query
    else:
        accounts_query = MeituanAccount.query.filter_by(user_id=user_id)
        account_ids = [a.id for a in accounts_query.all()]
        history_query = GrabHistory.query.filter(GrabHistory.account_id.in_(account_ids)) if account_ids else GrabHistory.query.filter(False)

    total_accounts = accounts_query.count()
    active_accounts = accounts_query.filter_by(is_active=True).count()

    today = datetime.now().date()
    today_grabs = history_query.filter(db.func.date(GrabHistory.grab_time) == today).all()
    today_success = sum(h.success_count for h in today_grabs)
    today_failed = sum(h.failed_count for h in today_grabs)

    recent_grabs = history_query.order_by(GrabHistory.grab_time.desc()).limit(5).all()
    cron_hours = SystemConfig.get('cron_hours', '8,14')

    return jsonify({
        "success": True,
        "data": {
            "accounts": {"total": total_accounts, "active": active_accounts},
            "today": {"total": len(today_grabs), "success": today_success, "failed": today_failed},
            "total_grabs": history_query.count(),
            "cron_hours": cron_hours,
            "recent_grabs": [g.to_dict() for g in recent_grabs]
        }
    })


@app.route('/api/accounts', methods=['GET'])
@login_required
def api_get_accounts():
    if session.get('is_admin'):
        accounts = MeituanAccount.query.order_by(MeituanAccount.created_at.desc()).all()
    else:
        accounts = MeituanAccount.query.filter_by(user_id=session['user_id']).order_by(MeituanAccount.created_at.desc()).all()
    return jsonify({"success": True, "data": [a.to_dict() for a in accounts]})


@app.route('/api/accounts', methods=['POST'])
@login_required
def api_add_account():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    token_input = data.get('token', '').strip()

    if not name:
        return jsonify({"success": False, "message": "请输入账号名称"}), 400

    token = extract_token(token_input)
    if not token:
        return jsonify({"success": False, "message": "无法识别 Token，请粘贴包含 token= 的 Cookie 或完整 Token 值（以 Ag 开头的长字符串）"}), 400

    existing = MeituanAccount.query.filter_by(token=token, user_id=session['user_id']).first()
    if existing:
        return jsonify({"success": False, "message": f"该 Token 已存在（账号: {existing.name}）"}), 400

    account = MeituanAccount(name=name, token=token, user_id=session['user_id'])
    db.session.add(account)
    db.session.commit()

    log_action('INFO', 'account', f'添加账号: {name}')
    return jsonify({"success": True, "message": "添加成功", "data": account.to_dict()})


@app.route('/api/accounts/<int:account_id>', methods=['PUT'])
@login_required
def api_update_account(account_id):
    if session.get('is_admin'):
        account = MeituanAccount.query.get_or_404(account_id)
    else:
        account = MeituanAccount.query.filter_by(id=account_id, user_id=session['user_id']).first_or_404()

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
    if session.get('is_admin'):
        account = MeituanAccount.query.get_or_404(account_id)
    else:
        account = MeituanAccount.query.filter_by(id=account_id, user_id=session['user_id']).first_or_404()

    name = account.name
    db.session.delete(account)
    db.session.commit()
    log_action('INFO', 'account', f'删除账号: {name}')
    return jsonify({"success": True, "message": "删除成功"})


@app.route('/api/grab/run', methods=['POST'])
@login_required
def api_run_grab():
    data = request.get_json(silent=True) or {}
    account_ids = data.get('account_ids', [])

    if session.get('is_admin'):
        base_query = MeituanAccount.query
    else:
        base_query = MeituanAccount.query.filter_by(user_id=session['user_id'])

    if account_ids:
        accounts = base_query.filter(MeituanAccount.id.in_(account_ids), MeituanAccount.is_active == True).all()
    else:
        accounts = base_query.filter_by(is_active=True).all()

    if not accounts:
        return jsonify({"success": False, "message": "没有可执行的账号"}), 400

    results = []
    for account in accounts:
        account.last_run_at = datetime.now()
        account.last_run_status = 'running'
        db.session.commit()

        try:
            env = os.environ.copy()
            env['MEITUAN_TOKEN'] = account.token
            script_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(script_dir, 'meituan.py')
            result = subprocess.run(['python', script_path], capture_output=True, text=True, timeout=120, env=env)
            output = result.stdout + result.stderr
            parsed = parse_grab_output(output)

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
            results.append({'account': account.name, 'status': account.last_run_status, 'success': parsed['success'], 'failed': parsed['failed']})

        except subprocess.TimeoutExpired:
            account.last_run_status = 'timeout'
            results.append({'account': account.name, 'status': 'timeout', 'error': '执行超时'})
        except Exception as e:
            account.last_run_status = 'failed'
            results.append({'account': account.name, 'status': 'failed', 'error': str(e)})

        db.session.commit()

    log_action('INFO', 'grab', f'执行领取，账号数: {len(accounts)}')
    return jsonify({"success": True, "message": "执行完成", "results": results})


@app.route('/api/history')
@login_required
def api_get_history():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    account_id = request.args.get('account_id', type=int)

    if session.get('is_admin'):
        query = GrabHistory.query
    else:
        account_ids = [a.id for a in MeituanAccount.query.filter_by(user_id=session['user_id']).all()]
        query = GrabHistory.query.filter(GrabHistory.account_id.in_(account_ids)) if account_ids else GrabHistory.query.filter(False)

    if account_id:
        query = query.filter_by(account_id=account_id)

    pagination = query.order_by(GrabHistory.grab_time.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "success": True,
        "data": [h.to_dict() for h in pagination.items],
        "pagination": {"page": page, "per_page": per_page, "total": pagination.total, "pages": pagination.pages}
    })


@app.route('/api/logs')
@login_required
def api_get_logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    level = request.args.get('level', '')
    category = request.args.get('category', '')

    if session.get('is_admin'):
        query = SystemLog.query
    else:
        query = SystemLog.query.filter_by(user_id=session['user_id'])

    if level:
        query = query.filter_by(level=level)
    if category:
        query = query.filter_by(category=category)

    pagination = query.order_by(SystemLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "success": True,
        "data": [l.to_dict() for l in pagination.items],
        "pagination": {"page": page, "per_page": per_page, "total": pagination.total, "pages": pagination.pages}
    })


@app.route('/api/logs/file')
@login_required
def api_get_log_file():
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
    configs = SystemConfig.query.all()
    return jsonify({"success": True, "data": {c.key: {'value': c.value, 'description': c.description} for c in configs}})


@app.route('/api/config', methods=['PUT'])
@login_required
@admin_required
def api_update_config():
    data = request.get_json() or {}
    for key, value in data.items():
        SystemConfig.set(key, str(value))
    log_action('INFO', 'system', '更新系统配置')
    return jsonify({"success": True, "message": "配置已更新"})


@app.route('/api/admin/users')
@login_required
@admin_required
def api_get_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({"success": True, "data": [u.to_dict() for u in users]})


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def api_delete_user(user_id):
    if user_id == session['user_id']:
        return jsonify({"success": False, "message": "不能删除自己"}), 400
    user = User.query.get_or_404(user_id)
    MeituanAccount.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    log_action('INFO', 'admin', f'删除用户: {user.username}')
    return jsonify({"success": True, "message": "删除成功"})


LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录 - 美团红包</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/remixicon@3.5.0/fonts/remixicon.css" rel="stylesheet">
</head>
<body class="bg-slate-100 min-h-screen flex items-center justify-center p-4">
    <div class="bg-white rounded-lg shadow-md w-full max-w-sm p-6">
        <div class="text-center mb-6">
            <div class="w-12 h-12 bg-amber-500 rounded-lg mx-auto flex items-center justify-center mb-3">
                <i class="ri-coupon-3-fill text-white text-2xl"></i>
            </div>
            <h1 class="text-xl font-semibold text-slate-800">美团红包</h1>
        </div>
        <div id="login-form">
            <div class="space-y-4">
                <div>
                    <label class="block text-sm text-slate-600 mb-1">用户名</label>
                    <input type="text" id="username" class="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:border-slate-500" placeholder="用户名">
                </div>
                <div>
                    <label class="block text-sm text-slate-600 mb-1">密码</label>
                    <input type="password" id="password" class="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:border-slate-500" placeholder="密码">
                </div>
                <button onclick="login()" class="w-full bg-slate-800 text-white py-2 rounded hover:bg-slate-700">登录</button>
            </div>
            <p class="mt-4 text-center text-slate-500 text-sm">没有账号？<a href="#" onclick="showRegister()" class="text-slate-800 hover:underline">注册</a></p>
        </div>
        <div id="register-form" class="hidden">
            <div class="space-y-4">
                <div>
                    <label class="block text-sm text-slate-600 mb-1">用户名</label>
                    <input type="text" id="reg-username" class="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:border-slate-500" placeholder="至少3个字符">
                </div>
                <div>
                    <label class="block text-sm text-slate-600 mb-1">密码</label>
                    <input type="password" id="reg-password" class="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:border-slate-500" placeholder="至少6个字符">
                </div>
                <button onclick="register()" class="w-full bg-slate-800 text-white py-2 rounded hover:bg-slate-700">注册</button>
            </div>
            <p class="mt-4 text-center text-slate-500 text-sm">已有账号？<a href="#" onclick="showLogin()" class="text-slate-800 hover:underline">登录</a></p>
        </div>
        <div id="error" class="mt-4 p-2 bg-red-50 text-red-600 rounded text-center text-sm hidden"></div>
        <div id="success" class="mt-4 p-2 bg-green-50 text-green-600 rounded text-center text-sm hidden"></div>
    </div>
    <script>
        function showRegister(){document.getElementById('login-form').classList.add('hidden');document.getElementById('register-form').classList.remove('hidden');hideMessages();}
        function showLogin(){document.getElementById('register-form').classList.add('hidden');document.getElementById('login-form').classList.remove('hidden');hideMessages();}
        function hideMessages(){document.getElementById('error').classList.add('hidden');document.getElementById('success').classList.add('hidden');}
        function showError(msg){hideMessages();document.getElementById('error').textContent=msg;document.getElementById('error').classList.remove('hidden');}
        function showSuccess(msg){hideMessages();document.getElementById('success').textContent=msg;document.getElementById('success').classList.remove('hidden');}
        async function login(){
            const username=document.getElementById('username').value.trim(),password=document.getElementById('password').value;
            if(!username||!password){showError('请填写完整');return;}
            try{const res=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});const data=await res.json();if(data.success){window.location.href='/dashboard';}else{showError(data.message);}}catch(e){showError('网络错误');}
        }
        async function register(){
            const username=document.getElementById('reg-username').value.trim(),password=document.getElementById('reg-password').value;
            if(!username||!password){showError('请填写完整');return;}
            try{const res=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});const data=await res.json();if(data.success){showSuccess(data.message);setTimeout(showLogin,1500);}else{showError(data.message);}}catch(e){showError('网络错误');}
        }
        document.addEventListener('keypress',e=>{if(e.key==='Enter'){if(!document.getElementById('login-form').classList.contains('hidden'))login();else register();}});
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
    <title>美团红包</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/remixicon@3.5.0/fonts/remixicon.css" rel="stylesheet">
    <style>
        .sidebar-item.active{background:#1e293b;color:white}
        .sidebar-item:hover:not(.active){background:#f1f5f9}
        .tab-content{display:none}.tab-content.active{display:block}
        .status-success{color:#16a34a}.status-failed{color:#dc2626}.status-running{color:#ca8a04}
        .log-success{color:#16a34a}.log-error{color:#dc2626}.log-warning{color:#ca8a04}.log-info{color:#2563eb}
    </style>
</head>
<body class="bg-slate-50 min-h-screen">
    <nav class="bg-white border-b border-slate-200 fixed top-0 left-0 right-0 z-50">
        <div class="flex items-center justify-between px-4 py-2">
            <div class="flex items-center">
                <div class="w-8 h-8 bg-amber-500 rounded flex items-center justify-center mr-2">
                    <i class="ri-coupon-3-fill text-white"></i>
                </div>
                <span class="font-semibold text-slate-800">美团红包</span>
                <span id="user-badge" class="ml-2 px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded hidden">管理员</span>
            </div>
            <div class="flex items-center space-x-3">
                <span class="text-sm text-slate-600" id="current-user">加载中...</span>
                <button onclick="logout()" class="text-slate-400 hover:text-slate-600"><i class="ri-logout-box-line"></i></button>
            </div>
        </div>
    </nav>
    <div class="flex pt-12">
        <aside class="w-48 bg-white border-r border-slate-200 fixed left-0 top-12 bottom-0">
            <nav class="p-2 space-y-1">
                <a href="#" onclick="showTab('dashboard')" class="sidebar-item active flex items-center px-3 py-2 rounded text-sm" data-tab="dashboard">
                    <i class="ri-dashboard-line mr-2"></i>仪表盘
                </a>
                <a href="#" onclick="showTab('accounts')" class="sidebar-item flex items-center px-3 py-2 rounded text-sm" data-tab="accounts">
                    <i class="ri-account-circle-line mr-2"></i>账号管理
                </a>
                <a href="#" onclick="showTab('history')" class="sidebar-item flex items-center px-3 py-2 rounded text-sm" data-tab="history">
                    <i class="ri-history-line mr-2"></i>领取历史
                </a>
                <a href="#" onclick="showTab('logs')" class="sidebar-item flex items-center px-3 py-2 rounded text-sm" data-tab="logs">
                    <i class="ri-file-text-line mr-2"></i>系统日志
                </a>
                <a href="#" onclick="showTab('settings')" class="sidebar-item flex items-center px-3 py-2 rounded text-sm" data-tab="settings">
                    <i class="ri-settings-3-line mr-2"></i>系统设置
                </a>
                <a href="#" onclick="showTab('help')" class="sidebar-item flex items-center px-3 py-2 rounded text-sm" data-tab="help">
                    <i class="ri-question-line mr-2"></i>使用帮助
                </a>
                <div id="admin-menu" class="hidden pt-2 mt-2 border-t border-slate-200">
                    <a href="#" onclick="showTab('users')" class="sidebar-item flex items-center px-3 py-2 rounded text-sm" data-tab="users">
                        <i class="ri-team-line mr-2"></i>用户管理
                    </a>
                </div>
            </nav>
        </aside>
        <main class="flex-1 ml-48 p-4">
            <div id="tab-dashboard" class="tab-content active">
                <div class="flex items-center justify-between mb-4">
                    <h1 class="text-lg font-semibold text-slate-800">仪表盘</h1>
                    <button onclick="runGrab()" class="bg-slate-800 text-white px-4 py-1.5 rounded text-sm hover:bg-slate-700">
                        <i class="ri-play-fill mr-1"></i>立即执行
                    </button>
                </div>
                <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                    <div class="bg-white rounded border border-slate-200 p-4">
                        <p class="text-slate-500 text-xs">我的账号</p>
                        <p class="text-2xl font-semibold text-slate-800 mt-1" id="stat-accounts">-</p>
                    </div>
                    <div class="bg-white rounded border border-slate-200 p-4">
                        <p class="text-slate-500 text-xs">今日领取</p>
                        <p class="text-2xl font-semibold text-green-600 mt-1" id="stat-today">-</p>
                    </div>
                    <div class="bg-white rounded border border-slate-200 p-4">
                        <p class="text-slate-500 text-xs">累计领取</p>
                        <p class="text-2xl font-semibold text-slate-800 mt-1" id="stat-total">-</p>
                    </div>
                    <div class="bg-white rounded border border-slate-200 p-4">
                        <p class="text-slate-500 text-xs">定时任务</p>
                        <p class="text-lg font-semibold text-slate-800 mt-1" id="stat-cron">-</p>
                    </div>
                </div>
                <div class="bg-white rounded border border-slate-200">
                    <div class="px-4 py-3 border-b border-slate-200"><h2 class="font-medium text-slate-800">最近记录</h2></div>
                    <div class="p-4"><div id="recent-grabs" class="space-y-2"><p class="text-slate-400 text-center py-6 text-sm">暂无记录</p></div></div>
                </div>
            </div>

            <div id="tab-accounts" class="tab-content">
                <div class="flex items-center justify-between mb-4">
                    <h1 class="text-lg font-semibold text-slate-800">账号管理</h1>
                    <button onclick="showAddAccountModal()" class="bg-slate-800 text-white px-4 py-1.5 rounded text-sm hover:bg-slate-700">
                        <i class="ri-add-line mr-1"></i>添加账号
                    </button>
                </div>
                <div class="bg-white rounded border border-slate-200">
                    <table class="w-full text-sm">
                        <thead class="bg-slate-50 border-b border-slate-200">
                            <tr>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">名称</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">Token</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">状态</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">最后执行</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">操作</th>
                            </tr>
                        </thead>
                        <tbody id="accounts-table" class="divide-y divide-slate-100">
                            <tr><td colspan="5" class="px-4 py-6 text-center text-slate-400">加载中...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <div id="tab-history" class="tab-content">
                <h1 class="text-lg font-semibold text-slate-800 mb-4">领取历史</h1>
                <div class="bg-white rounded border border-slate-200">
                    <table class="w-full text-sm">
                        <thead class="bg-slate-50 border-b border-slate-200">
                            <tr>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">时间</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">账号</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">状态</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">成功/失败</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">详情</th>
                            </tr>
                        </thead>
                        <tbody id="history-table" class="divide-y divide-slate-100">
                            <tr><td colspan="5" class="px-4 py-6 text-center text-slate-400">加载中...</td></tr>
                        </tbody>
                    </table>
                    <div id="history-pagination" class="px-4 py-2 border-t border-slate-200 flex items-center justify-between text-sm"></div>
                </div>
            </div>
            <div id="tab-logs" class="tab-content">
                <div class="flex items-center justify-between mb-4">
                    <h1 class="text-lg font-semibold text-slate-800">系统日志</h1>
                    <div class="flex items-center space-x-2">
                        <select id="log-filter" onchange="loadLogs()" class="border border-slate-300 rounded px-2 py-1 text-sm">
                            <option value="">全部</option><option value="INFO">INFO</option><option value="WARNING">WARNING</option><option value="ERROR">ERROR</option>
                        </select>
                        <button onclick="loadLogFile()" class="bg-slate-100 text-slate-600 px-3 py-1 rounded text-sm hover:bg-slate-200">刷新</button>
                    </div>
                </div>
                <div class="bg-white rounded border border-slate-200 mb-4">
                    <div class="px-4 py-2 border-b border-slate-200"><span class="font-medium text-slate-800 text-sm">操作日志</span></div>
                    <table class="w-full text-sm">
                        <thead class="bg-slate-50 border-b border-slate-200">
                            <tr><th class="px-4 py-2 text-left font-medium text-slate-600">时间</th><th class="px-4 py-2 text-left font-medium text-slate-600">级别</th><th class="px-4 py-2 text-left font-medium text-slate-600">类别</th><th class="px-4 py-2 text-left font-medium text-slate-600">消息</th></tr>
                        </thead>
                        <tbody id="logs-table" class="divide-y divide-slate-100"><tr><td colspan="4" class="px-4 py-6 text-center text-slate-400">加载中...</td></tr></tbody>
                    </table>
                </div>
                <div class="bg-white rounded border border-slate-200">
                    <div class="px-4 py-2 border-b border-slate-200"><span class="font-medium text-slate-800 text-sm">执行日志</span></div>
                    <div class="p-3 bg-slate-800 rounded-b max-h-64 overflow-y-auto"><pre id="log-file-content" class="text-slate-300 text-xs font-mono whitespace-pre-wrap">加载中...</pre></div>
                </div>
            </div>
            <div id="tab-settings" class="tab-content">
                <h1 class="text-lg font-semibold text-slate-800 mb-4">系统设置</h1>
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div class="bg-white rounded border border-slate-200">
                        <div class="px-4 py-2 border-b border-slate-200"><span class="font-medium text-slate-800 text-sm">定时任务</span></div>
                        <div class="p-4 space-y-3">
                            <div>
                                <label class="block text-sm text-slate-600 mb-1">执行时间（小时）</label>
                                <input type="text" id="config-cron-hours" class="w-full px-3 py-1.5 border border-slate-300 rounded text-sm" placeholder="8,14">
                                <p class="text-xs text-slate-400 mt-1">多个小时用逗号分隔</p>
                            </div>
                            <button onclick="saveConfig()" id="save-config-btn" class="bg-slate-800 text-white px-4 py-1.5 rounded text-sm hover:bg-slate-700">保存</button>
                            <p id="admin-only-hint" class="text-xs text-slate-400 hidden">仅管理员可修改</p>
                        </div>
                    </div>
                    <div class="bg-white rounded border border-slate-200">
                        <div class="px-4 py-2 border-b border-slate-200"><span class="font-medium text-slate-800 text-sm">修改密码</span></div>
                        <div class="p-4 space-y-3">
                            <div><label class="block text-sm text-slate-600 mb-1">原密码</label><input type="password" id="old-password" class="w-full px-3 py-1.5 border border-slate-300 rounded text-sm"></div>
                            <div><label class="block text-sm text-slate-600 mb-1">新密码</label><input type="password" id="new-password" class="w-full px-3 py-1.5 border border-slate-300 rounded text-sm"></div>
                            <button onclick="changePassword()" class="bg-slate-800 text-white px-4 py-1.5 rounded text-sm hover:bg-slate-700">修改</button>
                        </div>
                    </div>
                </div>
            </div>
            <div id="tab-help" class="tab-content">
                <h1 class="text-lg font-semibold text-slate-800 mb-4">使用帮助</h1>
                <div class="space-y-4">
                    <div class="bg-white rounded border border-slate-200">
                        <div class="px-4 py-2 border-b border-slate-200"><span class="font-medium text-slate-800 text-sm">如何获取 Token</span></div>
                        <div class="p-4 space-y-4 text-sm">
                            <div class="border-l-2 border-amber-500 pl-3">
                                <p class="font-medium text-slate-800 mb-2">方法一：手机抓包</p>
                                <p class="text-slate-600">安卓用 HttpCanary，苹果用 Stream。打开抓包后进入微信美团外卖小程序，找到 meituan.com 请求中的 token 字段。</p>
                            </div>
                            <div class="border-l-2 border-slate-400 pl-3">
                                <p class="font-medium text-slate-800 mb-2">方法二：浏览器抓包</p>
                                <p class="text-slate-600">Chrome 按 F12，切换到 Network，访问 h5.waimai.meituan.com 登录后，找到请求 Cookie 中 token= 后面的值。</p>
                            </div>
                            <div class="bg-slate-50 rounded p-3">
                                <p class="text-slate-600 mb-1">Cookie 示例：</p>
                                <code class="block bg-slate-800 text-green-400 p-2 rounded text-xs">token=AgGYIaHEzI-14y0...; other=xxx</code>
                            </div>
                        </div>
                    </div>
                    <div class="bg-white rounded border border-slate-200">
                        <div class="px-4 py-2 border-b border-slate-200"><span class="font-medium text-slate-800 text-sm">常见问题</span></div>
                        <div class="p-4 space-y-3 text-sm">
                            <div><p class="font-medium text-slate-800">Token 多久失效？</p><p class="text-slate-600">约 30 天</p></div>
                            <div><p class="font-medium text-slate-800">提示请求异常？</p><p class="text-slate-600">服务器在海外或 Token 失效</p></div>
                            <div><p class="font-medium text-slate-800">支持哪些红包？</p><p class="text-slate-600">外卖满减、神券、闪购、团购等</p></div>
                        </div>
                    </div>
                </div>
            </div>
            <div id="tab-users" class="tab-content">
                <h1 class="text-lg font-semibold text-slate-800 mb-4">用户管理</h1>
                <div class="bg-white rounded border border-slate-200">
                    <table class="w-full text-sm">
                        <thead class="bg-slate-50 border-b border-slate-200">
                            <tr>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">用户名</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">角色</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">注册时间</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">最后登录</th>
                                <th class="px-4 py-2 text-left font-medium text-slate-600">操作</th>
                            </tr>
                        </thead>
                        <tbody id="users-table" class="divide-y divide-slate-100"><tr><td colspan="5" class="px-4 py-6 text-center text-slate-400">加载中...</td></tr></tbody>
                    </table>
                </div>
            </div>
        </main>
    </div>
    <div id="add-account-modal" class="fixed inset-0 bg-black bg-opacity-50 hidden items-center justify-center z-50">
        <div class="bg-white rounded-lg w-full max-w-md mx-4">
            <div class="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
                <span class="font-medium text-slate-800">添加账号</span>
                <button onclick="hideAddAccountModal()" class="text-slate-400 hover:text-slate-600"><i class="ri-close-line text-xl"></i></button>
            </div>
            <div class="p-4 space-y-3">
                <div><label class="block text-sm text-slate-600 mb-1">账号名称</label><input type="text" id="account-name" class="w-full px-3 py-1.5 border border-slate-300 rounded text-sm" placeholder="备注名"></div>
                <div><label class="block text-sm text-slate-600 mb-1">Token</label><textarea id="account-token" rows="3" class="w-full px-3 py-1.5 border border-slate-300 rounded text-sm" placeholder="粘贴 Cookie 字符串（如 token=AgXXX...）或直接粘贴 Token 值"></textarea><p class="text-xs text-slate-400 mt-1">从浏览器开发者工具 Network → Cookie 中复制，需包含 token= 或直接复制 Token 值</p></div>
            </div>
            <div class="px-4 py-3 bg-slate-50 flex justify-end space-x-2">
                <button onclick="hideAddAccountModal()" class="px-3 py-1.5 border border-slate-300 rounded text-sm hover:bg-slate-100">取消</button>
                <button onclick="addAccount()" class="px-3 py-1.5 bg-slate-800 text-white rounded text-sm hover:bg-slate-700">添加</button>
            </div>
        </div>
    </div>
    <div id="detail-modal" class="fixed inset-0 bg-black bg-opacity-50 hidden items-center justify-center z-50">
        <div class="bg-white rounded-lg w-full max-w-xl mx-4 max-h-[80vh] overflow-hidden flex flex-col">
            <div class="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
                <span class="font-medium text-slate-800">领取详情</span>
                <button onclick="hideDetailModal()" class="text-slate-400 hover:text-slate-600"><i class="ri-close-line text-xl"></i></button>
            </div>
            <div id="detail-content" class="p-4 overflow-y-auto flex-1 text-sm"></div>
        </div>
    </div>
    <div id="toast" class="fixed top-4 right-4 bg-slate-800 text-white px-4 py-2 rounded text-sm hidden z-50 transition-all transform translate-x-full"><span id="toast-message"></span></div>

    <script>
        let currentUser = null;

        function showToast(msg, type='info') {
            const t=document.getElementById('toast'),m=document.getElementById('toast-message');
            m.textContent=msg;
            t.className='fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 transition-all transform';
            t.classList.add(type==='success'?'bg-green-600':type==='error'?'bg-red-600':'bg-gray-800','text-white');
            t.classList.remove('hidden','translate-x-full');
            setTimeout(()=>{t.classList.add('translate-x-full');setTimeout(()=>t.classList.add('hidden'),300);},3000);
        }

        async function api(url, opts={}) {
            try {
                if(opts.method==='POST'&&!opts.body)opts.body='{}';
                const r=await fetch(url,{headers:{'Content-Type':'application/json',...opts.headers},...opts});
                const d=await r.json();
                if(r.status===401){window.location.href='/login';return null;}
                return d;
            } catch(e) {showToast('网络错误','error');return null;}
        }

        function showTab(name) {
            document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
            document.querySelectorAll('.sidebar-item').forEach(e=>e.classList.remove('active'));
            document.getElementById('tab-'+name).classList.add('active');
            const item=document.querySelector(`[data-tab="${name}"]`);
            if(item)item.classList.add('active');
            if(name==='dashboard')loadDashboard();
            else if(name==='accounts')loadAccounts();
            else if(name==='history')loadHistory();
            else if(name==='logs'){loadLogs();loadLogFile();}
            else if(name==='settings')loadConfig();
            else if(name==='users')loadUsers();
        }

        async function loadCurrentUser() {
            const d=await api('/api/auth/me');
            if(d&&d.success){
                currentUser=d.data;
                document.getElementById('current-user').innerHTML='<i class="ri-user-line mr-1"></i>'+currentUser.username;
                if(currentUser.is_admin){
                    document.getElementById('user-badge').classList.remove('hidden');
                    document.getElementById('admin-menu').classList.remove('hidden');
                } else {
                    document.getElementById('save-config-btn').classList.add('hidden');
                    document.getElementById('admin-only-hint').classList.remove('hidden');
                    document.getElementById('config-cron-hours').disabled=true;
                }
            }
        }

        async function loadDashboard() {
            const d=await api('/api/dashboard/stats');
            if(!d||!d.success)return;
            const s=d.data;
            document.getElementById('stat-accounts').textContent=s.accounts.total;
            document.getElementById('stat-today').textContent=s.today.success;
            document.getElementById('stat-total').textContent=s.total_grabs;
            document.getElementById('stat-cron').textContent=s.cron_hours+' 点';
            const c=document.getElementById('recent-grabs');
            if(s.recent_grabs.length===0){c.innerHTML='<p class="text-slate-400 text-center py-6 text-sm">暂无记录</p>';}
            else{c.innerHTML=s.recent_grabs.map(g=>`<div class="flex items-center justify-between p-3 bg-slate-50 rounded"><div><p class="font-medium text-slate-800 text-sm">${g.account_name}</p><p class="text-xs text-slate-500">${g.grab_time}</p></div><div class="text-right text-sm"><span class="status-${g.status}">${g.status==='success'?'成功':'失败'}</span><p class="text-xs text-slate-500">${g.success_count}/${g.failed_count}</p></div></div>`).join('');}
        }

        async function loadAccounts() {
            const d=await api('/api/accounts');
            if(!d||!d.success)return;
            const t=document.getElementById('accounts-table');
            if(d.data.length===0){t.innerHTML='<tr><td colspan="5" class="px-6 py-8 text-center text-slate-400">暂无账号</td></tr>';}
            else{t.innerHTML=d.data.map(a=>`<tr class="border-b border-slate-100"><td class="px-6 py-4 font-medium text-slate-800">${a.name}</td><td class="px-6 py-4"><code class="text-sm text-slate-500">${a.token}</code></td><td class="px-6 py-4"><span class="px-2 py-1 rounded text-xs ${a.is_active?'bg-green-100 text-green-700':'bg-slate-100 text-slate-500'}">${a.is_active?'启用':'禁用'}</span></td><td class="px-6 py-4 text-sm text-slate-500">${a.last_run_at||'从未执行'}${a.last_run_status?` <span class="status-${a.last_run_status}">${a.last_run_status}</span>`:''}</td><td class="px-6 py-4"><button onclick="toggleAccount(${a.id},${!a.is_active})" class="text-slate-600 hover:text-slate-800 mr-3">${a.is_active?'禁用':'启用'}</button><button onclick="deleteAccount(${a.id},'${a.name}')" class="text-red-500 hover:text-red-700">删除</button></td></tr>`).join('');}
        }

        function showAddAccountModal(){document.getElementById('add-account-modal').classList.remove('hidden');document.getElementById('add-account-modal').classList.add('flex');}
        function hideAddAccountModal(){document.getElementById('add-account-modal').classList.add('hidden');document.getElementById('add-account-modal').classList.remove('flex');document.getElementById('account-name').value='';document.getElementById('account-token').value='';}

        async function addAccount() {
            const name=document.getElementById('account-name').value.trim();
            const token=document.getElementById('account-token').value.trim();
            if(!name||!token){showToast('请填写完整','error');return;}
            const d=await api('/api/accounts',{method:'POST',body:JSON.stringify({name,token})});
            if(d&&d.success){showToast('添加成功','success');hideAddAccountModal();loadAccounts();}else{showToast(d?.message||'添加失败','error');}
        }

        async function toggleAccount(id,active){const d=await api(`/api/accounts/${id}`,{method:'PUT',body:JSON.stringify({is_active:active})});if(d&&d.success){showToast('操作成功','success');loadAccounts();}}
        async function deleteAccount(id,name){if(!confirm(`确定删除 "${name}"？`))return;const d=await api(`/api/accounts/${id}`,{method:'DELETE'});if(d&&d.success){showToast('删除成功','success');loadAccounts();}}

        async function loadHistory(page=1) {
            const d=await api(`/api/history?page=${page}&per_page=20`);
            if(!d||!d.success)return;
            const t=document.getElementById('history-table');
            if(d.data.length===0){t.innerHTML='<tr><td colspan="5" class="px-6 py-8 text-center text-slate-400">暂无记录</td></tr>';}
            else{t.innerHTML=d.data.map(h=>`<tr class="border-b border-slate-100"><td class="px-6 py-4 text-sm text-slate-500">${h.grab_time}</td><td class="px-6 py-4 font-medium text-slate-800">${h.account_name}</td><td class="px-6 py-4"><span class="px-2 py-1 rounded text-xs ${h.status==='success'?'bg-green-100 text-green-700':'bg-red-100 text-red-700'}">${h.status==='success'?'成功':'失败'}</span></td><td class="px-6 py-4 text-sm"><span class="text-green-600">${h.success_count}</span> / <span class="text-red-500">${h.failed_count}</span></td><td class="px-6 py-4"><button onclick="showDetail(${h.id})" class="text-slate-600 hover:text-slate-800 text-sm">查看详情</button></td></tr>`).join('');}
            const p=d.pagination,pe=document.getElementById('history-pagination');
            if(p.pages>1){pe.innerHTML=`<span class="text-sm text-slate-500">共 ${p.total} 条</span><div class="flex space-x-2">${p.page>1?`<button onclick="loadHistory(${p.page-1})" class="px-3 py-1 border border-slate-200 rounded hover:bg-slate-50">上一页</button>`:''}<span class="px-3 py-1 text-slate-600">${p.page}/${p.pages}</span>${p.page<p.pages?`<button onclick="loadHistory(${p.page+1})" class="px-3 py-1 border border-slate-200 rounded hover:bg-slate-50">下一页</button>`:''}</div>`;}else{pe.innerHTML='';}
        }

        function showDetail(id){
            const m=document.getElementById('detail-modal');m.classList.remove('hidden');m.classList.add('flex');
            document.getElementById('detail-content').innerHTML='<p class="text-slate-400">加载中...</p>';
            api('/api/history?per_page=100').then(d=>{
                if(d&&d.success){
                    const h=d.data.find(x=>x.id===id);
                    if(h){
                        let details='';try{const cs=JSON.parse(h.details||'[]');details=cs.map(c=>`<div class="flex items-center justify-between p-3 bg-slate-50 rounded mb-2"><span class="text-slate-700">${c.name}</span><span class="${c.status==='success'?'text-green-600':'text-red-500'}">${c.status==='success'?'成功':'失败'}</span></div>`).join('');}catch(e){}
                        document.getElementById('detail-content').innerHTML=`<div class="space-y-4"><div class="grid grid-cols-2 gap-3"><div class="bg-slate-50 p-3 rounded"><p class="text-xs text-slate-500">账号</p><p class="font-medium text-slate-800">${h.account_name}</p></div><div class="bg-slate-50 p-3 rounded"><p class="text-xs text-slate-500">时间</p><p class="font-medium text-slate-800">${h.grab_time}</p></div><div class="bg-slate-50 p-3 rounded"><p class="text-xs text-slate-500">成功</p><p class="font-medium text-green-600">${h.success_count}</p></div><div class="bg-slate-50 p-3 rounded"><p class="text-xs text-slate-500">失败</p><p class="font-medium text-red-500">${h.failed_count}</p></div></div>${details?`<div><p class="font-medium text-slate-700 mb-2">详情</p>${details}</div>`:''}${h.raw_output?`<div><p class="font-medium text-slate-700 mb-2">输出</p><pre class="bg-slate-800 text-slate-300 p-3 rounded text-sm overflow-x-auto max-h-60">${h.raw_output}</pre></div>`:''}</div>`;
                    }
                }
            });
        }
        function hideDetailModal(){document.getElementById('detail-modal').classList.add('hidden');document.getElementById('detail-modal').classList.remove('flex');}

        async function loadLogs() {
            const level=document.getElementById('log-filter').value;
            const d=await api(`/api/logs?level=${level}&per_page=50`);
            if(!d||!d.success)return;
            const t=document.getElementById('logs-table');
            if(d.data.length===0){t.innerHTML='<tr><td colspan="4" class="px-6 py-8 text-center text-slate-400">暂无日志</td></tr>';}
            else{t.innerHTML=d.data.map(l=>`<tr class="border-b border-slate-100"><td class="px-6 py-3 text-slate-500 text-sm">${l.created_at}</td><td class="px-6 py-3"><span class="log-${l.level.toLowerCase()}">${l.level}</span></td><td class="px-6 py-3 text-slate-500">${l.category}</td><td class="px-6 py-3 text-slate-700">${l.message}</td></tr>`).join('');}
        }

        async function loadLogFile() {
            const d=await api('/api/logs/file?lines=200');
            if(d&&d.success){
                const c=d.data||'暂无日志';
                document.getElementById('log-file-content').innerHTML=c.replace(/(成功|领取)/g,'<span class="log-success">$1</span>').replace(/(失败|错误|异常|Error)/g,'<span class="log-error">$1</span>').replace(/(警告|Warning)/g,'<span class="log-warning">$1</span>');
            }
        }

        async function loadConfig() {
            const d=await api('/api/config');
            if(d&&d.success&&d.data.cron_hours){document.getElementById('config-cron-hours').value=d.data.cron_hours.value;}
        }

        async function saveConfig() {
            const h=document.getElementById('config-cron-hours').value;
            const d=await api('/api/config',{method:'PUT',body:JSON.stringify({cron_hours:h})});
            if(d&&d.success){showToast('已保存','success');}else{showToast(d?.message||'保存失败','error');}
        }

        async function changePassword() {
            const o=document.getElementById('old-password').value,n=document.getElementById('new-password').value;
            if(!o||!n){showToast('请填写完整','error');return;}
            const d=await api('/api/auth/change-password',{method:'POST',body:JSON.stringify({old_password:o,new_password:n})});
            if(d&&d.success){showToast('修改成功','success');document.getElementById('old-password').value='';document.getElementById('new-password').value='';}else{showToast(d?.message||'修改失败','error');}
        }

        async function runGrab() {
            showToast('开始执行...','info');
            const d=await api('/api/grab/run',{method:'POST'});
            if(d&&d.success){const r=d.results||[];const s=r.filter(x=>x.status==='success').length;showToast(`完成，成功 ${s}/${r.length}`,'success');loadDashboard();}else{showToast(d?.message||'执行失败','error');}
        }

        async function loadUsers() {
            const d=await api('/api/admin/users');
            if(!d||!d.success)return;
            const t=document.getElementById('users-table');
            t.innerHTML=d.data.map(u=>`<tr class="border-b border-slate-100"><td class="px-6 py-4 font-medium text-slate-800">${u.username}</td><td class="px-6 py-4"><span class="px-2 py-1 rounded text-xs ${u.is_admin?'bg-amber-100 text-amber-700':'bg-slate-100 text-slate-500'}">${u.is_admin?'管理员':'普通用户'}</span></td><td class="px-6 py-4 text-sm text-slate-500">${u.created_at||'-'}</td><td class="px-6 py-4 text-sm text-slate-500">${u.last_login||'-'}</td><td class="px-6 py-4">${u.is_admin?'-':`<button onclick="deleteUser(${u.id},'${u.username}')" class="text-red-500 hover:text-red-700">删除</button>`}</td></tr>`).join('');
        }

        async function deleteUser(id,name){if(!confirm(`确定删除用户 "${name}"？其所有账号和数据也会被删除！`))return;const d=await api(`/api/admin/users/${id}`,{method:'DELETE'});if(d&&d.success){showToast('删除成功','success');loadUsers();}else{showToast(d?.message||'删除失败','error');}}

        async function logout(){await api('/api/auth/logout',{method:'POST'});window.location.href='/login';}

        document.addEventListener('DOMContentLoaded',()=>{loadCurrentUser();loadDashboard();});
    </script>
</body>
</html>
'''

init_db(app)

if __name__ == '__main__':
    port = int(os.environ.get('WEB_PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
