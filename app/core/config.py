import os
import logging
from datetime import timedelta
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from app.core.config_manager import config_manager

# 配置日志
from app.utils.logging import setup_logger

# 定义版本号
def get_app_version():
    try:
        with open("versions", "r") as file:
            return file.read().strip()
    except FileNotFoundError:
        logger = setup_logger()
        logger.warning("versions 文件未找到，使用默认版本号")
        return "unknown"

# 创建Flask应用实例
def create_app():
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

    # 应用配置
    app.secret_key = config_manager.get('secret_key', 'mediamaster')
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=int(config_manager.get('session_lifetime_hours', 24)))
    app.config['SESSION_COOKIE_NAME'] = config_manager.get('session_cookie_name', 'mediamaster')
    app.config['SESSION_COOKIE_SAMESITE'] = config_manager.get('session_cookie_samesite', 'Lax')
    app.config['WTF_CSRF_ENABLED'] = config_manager.get('csrf_enabled', 'True').lower() == 'true'
    app.config['WTF_CSRF_SECRET_KEY'] = config_manager.get('csrf_secret_key', 'mediamaster-csrf-secret')

    # 初始化CSRF保护
    csrf = CSRFProtect(app)

    return app

# 全局配置
DATABASE = config_manager.get('database_path', '/config/data.db')
APP_VERSION = get_app_version()

