"""
数据库模型 - 企业级数据持久化
"""
import os
import hashlib
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def hash_password(password: str) -> str:
    """密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()


class User(db.Model):
    """用户表"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(64), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime)

    def set_password(self, password: str):
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        return self.password_hash == hash_password(password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'is_admin': self.is_admin,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'last_login': self.last_login.strftime('%Y-%m-%d %H:%M:%S') if self.last_login else None
        }


class MeituanAccount(db.Model):
    """美团账号表"""
    __tablename__ = 'meituan_accounts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 账号备注名
    token = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    last_run_at = db.Column(db.DateTime)
    last_run_status = db.Column(db.String(20))  # success, failed, running

    # 关联领取历史
    grab_histories = db.relationship('GrabHistory', backref='account', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'token': self.token[:20] + '...' if len(self.token) > 20 else self.token,
            'token_full': self.token,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
            'last_run_at': self.last_run_at.strftime('%Y-%m-%d %H:%M:%S') if self.last_run_at else None,
            'last_run_status': self.last_run_status
        }


class GrabHistory(db.Model):
    """领取历史表"""
    __tablename__ = 'grab_histories'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('meituan_accounts.id'), nullable=False)
    grab_time = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), nullable=False)  # success, failed, partial
    total_coupons = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    details = db.Column(db.Text)  # JSON 格式的详细信息
    raw_output = db.Column(db.Text)  # 原始输出日志

    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'account_name': self.account.name if self.account else 'Unknown',
            'grab_time': self.grab_time.strftime('%Y-%m-%d %H:%M:%S') if self.grab_time else None,
            'status': self.status,
            'total_coupons': self.total_coupons,
            'success_count': self.success_count,
            'failed_count': self.failed_count,
            'details': self.details,
            'raw_output': self.raw_output
        }


class SystemLog(db.Model):
    """系统日志表"""
    __tablename__ = 'system_logs'

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(10), nullable=False)  # INFO, WARNING, ERROR, DEBUG
    category = db.Column(db.String(50), nullable=False)  # auth, grab, system, api
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text)  # 额外详情
    ip_address = db.Column(db.String(50))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship('User', backref='logs')

    def to_dict(self):
        return {
            'id': self.id,
            'level': self.level,
            'category': self.category,
            'message': self.message,
            'details': self.details,
            'ip_address': self.ip_address,
            'user': self.user.username if self.user else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class SystemConfig(db.Model):
    """系统配置表"""
    __tablename__ = 'system_configs'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.String(200))
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @staticmethod
    def get(key: str, default=None):
        config = SystemConfig.query.filter_by(key=key).first()
        return config.value if config else default

    @staticmethod
    def set(key: str, value: str, description: str = None):
        config = SystemConfig.query.filter_by(key=key).first()
        if config:
            config.value = value
            if description:
                config.description = description
        else:
            config = SystemConfig(key=key, value=value, description=description)
            db.session.add(config)
        db.session.commit()
        return config


def init_db(app):
    """初始化数据库"""
    db.init_app(app)
    with app.app_context():
        db.create_all()

        # 创建默认管理员账号
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', is_admin=True)
            admin.set_password(os.environ.get('ADMIN_PASSWORD', 'admin123'))
            db.session.add(admin)
            db.session.commit()

        # 初始化默认配置
        default_configs = [
            ('cron_hours', os.environ.get('CRON_HOURS', '8,14'), '定时执行时间（小时）'),
            ('run_on_start', os.environ.get('RUN_ON_START', 'false'), '启动时是否执行'),
            ('auto_refresh_interval', '30', '自动刷新间隔（秒）'),
        ]
        for key, value, desc in default_configs:
            if not SystemConfig.query.filter_by(key=key).first():
                db.session.add(SystemConfig(key=key, value=value, description=desc))

        db.session.commit()
