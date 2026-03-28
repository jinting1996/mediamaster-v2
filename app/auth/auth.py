from functools import wraps
from flask import session, redirect, url_for, request, jsonify, g
import bcrypt
from app.core.database import get_db
from app.core.config import setup_logger
from app.utils.validation import validate_username, validate_password

logger = setup_logger()

def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember_me = request.form.get('remember') == 'on'
        
        # 验证用户名和密码
        valid_username, username_error = validate_username(username)
        valid_password, password_error = validate_password(password)
        
        if not valid_username:
            logger.warning(f"用户 {username} 登录失败: {username_error}")
            return jsonify({
                'success': False,
                'message': username_error
            })
        
        if not valid_password:
            logger.warning(f"用户 {username} 登录失败: {password_error}")
            return jsonify({
                'success': False,
                'message': password_error
            })
        
        logger.info(f"用户 {username} 尝试登录，记住我: {remember_me}")
        
        db = get_db()
        error = None
        user = db.execute('SELECT * FROM USERS WHERE USERNAME = ?', (username,)).fetchone()
        
        if user is None:
            error = '用户名或密码错误'
            logger.warning(f"用户 {username} 登录失败: 用户不存在")
        else:
            stored_password = user['PASSWORD']
            if isinstance(stored_password, str):
                stored_password = stored_password.encode('utf-8')
            elif not isinstance(stored_password, bytes):
                error = '用户数据格式异常，请重置密码！'
                logger.error(f"用户 {username} 登录失败: 用户数据格式异常，请重置密码！")
            
            if error is None:
                if not bcrypt.checkpw(password.encode('utf-8'), stored_password):
                    error = '用户名或密码错误'
                    logger.warning(f"用户 {username} 登录失败: 密码错误")
        
        if error is None:
            session.clear()
            session['user_id'] = user['ID']
            session['username'] = user['USERNAME']
            session['nickname'] = user['NICKNAME']
            session['avatar_url'] = user['AVATAR_URL']
            
            if remember_me:
                session.permanent = True
                from flask import current_app
                current_app.permanent_session_lifetime = timedelta(days=30)
                logger.info(f"用户 {username} 登录成功，已启用自动登录(30天)")
            else:
                session.permanent = False
                logger.info(f"用户 {username} 登录成功，未启用自动登录(浏览器会话级别)")

            return jsonify({
                'success': True,
                'redirect_url': '/',
                'message': '登录成功'
            })

        return jsonify({
            'success': False,
            'message': error
        })

    from app.core.config import APP_VERSION
    return render_template('login.html', version=APP_VERSION)

def logout():
    username = session.get('username')
    logger.info(f"用户 {username} 登出")
    session.clear()
    return redirect(url_for('login'))
