from flask import render_template, session, Response, stream_with_context, request, jsonify
import os
import time
import subprocess
from werkzeug.exceptions import InternalServerError
from app.core.config import APP_VERSION, setup_logger
from app.auth.auth import login, logout, login_required
from app.api.profile import update_profile, change_password
from app.api.system import system_resources, system_processes, site_status, check_site_status
from app.api.subscriptions import (
    add_subscription, cancel_subscription, tmdb_subscriptions, check_subscriptions,
    edit_subscription, delete_subscription, douban_subscriptions_json,
    tv_alias_list_json, tv_alias_edit_json, tv_alias_add_api, tv_alias_edit_api, tv_alias_delete_api
)
from app.api.library import api_search, library
from app.core.database import get_db, close_connection

# 存储进程ID的字典
running_services = {}

# 存储日志传输状态的字典
log_streaming_status = {}

logger = setup_logger()

# 注册所有路由
def register_routes(app):
    # 认证路由
    app.route('/login', methods=['GET', 'POST'])(login)
    app.route('/logout')(logout)
    
    # 个人资料路由
    app.route('/api/update_profile', methods=['POST'])(update_profile)
    app.route('/api/change_password', methods=['POST'])(change_password)
    
    # 系统路由
    app.route('/api/system_resources', methods=['GET'])(system_resources)
    app.route('/api/system_processes', methods=['GET'])(system_processes)
    app.route('/api/site_status', methods=['GET'])(site_status)
    app.route('/api/check_site_status', methods=['POST'])(check_site_status)
    
    # 订阅路由
    app.route('/add_subscription', methods=['POST'])(add_subscription)
    app.route('/cancel_subscription', methods=['POST'])(cancel_subscription)
    app.route('/tmdb_subscriptions', methods=['POST'])(tmdb_subscriptions)
    app.route('/check_subscriptions', methods=['POST'])(check_subscriptions)
    app.route('/edit_subscription/<type>/<int:id>', methods=['GET', 'POST'])(edit_subscription)
    app.route('/delete_subscription/<type>/<int:id>', methods=['POST'])(delete_subscription)
    app.route('/douban_subscriptions_json')(douban_subscriptions_json)
    app.route('/tv_alias_list_json')(tv_alias_list_json)
    app.route('/tv_alias_edit_json/<int:alias_id>')(tv_alias_edit_json)
    app.route('/tv_alias_add', methods=['POST'])(tv_alias_add_api)
    app.route('/tv_alias_edit/<int:alias_id>', methods=['POST'])(tv_alias_edit_api)
    app.route('/tv_alias_delete/<int:alias_id>', methods=['POST'])(tv_alias_delete_api)
    
    # 媒体库路由
    app.route('/api/search', methods=['GET'])(api_search)
    app.route('/library')(library)
    
    # 其他路由
    @app.errorhandler(InternalServerError)
    def handle_500(error):
        logger.error(f"服务器错误: {error}")
        return render_template('500.html'), 500
    
    @app.route('/')
    @login_required
    def dashboard():
        db = get_db()
        
        # 获取电影数量
        total_movies = db.execute('SELECT COUNT(*) FROM LIB_MOVIES').fetchone()[0]
        
        # 获取电视剧数量
        total_tvs = db.execute('SELECT COUNT(DISTINCT id) FROM LIB_TVS').fetchone()[0]
        
        # 获取剧集数量
        total_episodes = db.execute("SELECT SUM(LENGTH(episodes) - LENGTH(REPLACE(episodes, ',', '')) + 1) FROM LIB_TV_SEASONS").fetchone()[0] or 0
        
        # 从会话中获取用户昵称和头像
        username = session.get('username')
        nickname = session.get('nickname')
        avatar_url = session.get('avatar_url')

        return render_template('dashboard.html', 
                               total_movies=total_movies, 
                               total_tvs=total_tvs, 
                               total_episodes=total_episodes, 
                               nickname=nickname, 
                               username=username, 
                               avatar_url=avatar_url, 
                               version=APP_VERSION)
    
    @app.route('/recommendations')
    @login_required
    def recommendations():
        nickname = session.get('nickname')
        avatar_url = session.get('avatar_url')
        db = get_db()
        # 从数据库中读取 tmdb_api_key
        tmdb_api_key = db.execute('SELECT VALUE FROM CONFIG WHERE OPTION = ?', ('tmdb_api_key',)).fetchone()
        tmdb_api_key = tmdb_api_key['VALUE'] if tmdb_api_key else None
        return render_template('recommendations.html', nickname=nickname, avatar_url=avatar_url, tmdb_api_key=tmdb_api_key, version=APP_VERSION)
    
    @app.route('/search', methods=['GET'])
    @login_required
    def search():
        query = request.args.get('q', '').strip()
        nickname = session.get('nickname')
        avatar_url = session.get('avatar_url')
        return render_template('search.html', query=query, nickname=nickname, avatar_url=avatar_url, version=APP_VERSION)
    
    @app.route('/subscriptions')
    @login_required
    def subscriptions():
        db = get_db()
        miss_movies = db.execute('SELECT * FROM MISS_MOVIES').fetchall()
        miss_tvs = db.execute('SELECT * FROM MISS_TVS').fetchall()
        # 从数据库中读取 tmdb_api_key
        tmdb_api_key = db.execute('SELECT VALUE FROM CONFIG WHERE OPTION = ?', ('tmdb_api_key',)).fetchone()
        tmdb_api_key = tmdb_api_key['VALUE'] if tmdb_api_key else None
        # 从会话中获取用户昵称和头像
        nickname = session.get('nickname')
        avatar_url = session.get('avatar_url')
        return render_template('subscriptions.html', 
                             miss_movies=miss_movies, 
                             miss_tvs=miss_tvs, 
                             tmdb_api_key=tmdb_api_key,
                             nickname=nickname, 
                             avatar_url=avatar_url, 
                             version=APP_VERSION)
    
    @app.route('/service_control')
    @login_required
    def service_control():
        # 从会话中获取用户昵称和头像
        nickname = session.get('nickname')
        avatar_url = session.get('avatar_url')
        return render_template('service_control.html', nickname=nickname, avatar_url=avatar_url, version=APP_VERSION)
    
    @app.route('/run_service', methods=['POST'])
    @login_required
    def run_service():
        data = request.get_json()
        service = data.get('service')
        try:
            logger.info(f"尝试启动服务: {service}")
            log_file_path = f'/tmp/log/{service}.log'
            os.makedirs(os.path.dirname(log_file_path), exist_ok=True)  # 确保日志目录存在
            with open(log_file_path, 'w', encoding='utf-8') as log_file:
                process = subprocess.Popen(['python3', f'/app/{service}.py'], stdout=log_file, stderr=log_file)
                pid = process.pid
                running_services[service] = pid
            logger.info(f"服务 {service} 启动成功，PID: {pid}")
            return jsonify({"message": "服务运行成功！", "pid": pid}), 200
        except Exception as e:
            logger.error(f"服务 {service} 启动失败: {e}")
            return jsonify({"message": str(e)}), 500
    
    @app.route('/realtime_log/<string:service>')
    @login_required
    def realtime_log(service):
        @stream_with_context
        def generate():
            log_file_path = f'/tmp/log/{service}.log'
            if not os.path.exists(log_file_path):
                logger.warning(f"实时日志文件不存在: {log_file_path}")
                yield 'data: 当前没有实时运行日志，请检查服务是否正在运行！\n\n'.encode('utf-8')
                return
            
            # 检查文件是否为空
            if os.path.getsize(log_file_path) == 0:
                logger.warning(f"实时日志文件为空: {log_file_path}")
                yield 'data: 当前日志文件为空\n\n'.encode('utf-8')
                return

            logger.info(f"开始读取实时日志: {log_file_path}")
            with open(log_file_path, 'r', encoding='utf-8') as log_file:
                while True:
                    line = log_file.readline()
                    if not line:
                        time.sleep(0.1)
                        # 检查是否需要停止日志传输
                        if not log_streaming_status.get(service, True):
                            logger.info(f"停止读取日志: {log_file_path}")
                            break
                        continue
                    yield f"data: {line}\n\n".encode('utf-8')
        
        return Response(generate(), mimetype='text/event-stream')
