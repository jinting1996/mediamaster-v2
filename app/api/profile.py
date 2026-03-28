from flask import request, jsonify, session
import os
import bcrypt
from werkzeug.utils import secure_filename
from app.core.database import get_db
from app.core.config import setup_logger
from app.auth.auth import login_required
from app.utils.validation import validate_password

logger = setup_logger()

# 配置允许上传的文件类型
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# 检查文件扩展名是否合法
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 更新用户资料路由
def update_profile():
    try:
        user_id = session['user_id']
        nickname = session.get('nickname')
        logger.info(f"用户 {nickname} 更新个人资料")
        db = get_db()

        # 获取表单数据
        username = request.form.get('username')
        nickname_input = request.form.get('nickname')
        avatar_file = request.files.get('avatar')
        
        updated_avatar = False
        
        # 更新用户名和昵称（如果有提供）
        if username or nickname_input:
            if username and nickname_input:
                # 同时更新用户名和昵称
                db.execute('UPDATE USERS SET USERNAME = ?, NICKNAME = ? WHERE ID = ?', 
                          (username, nickname_input, user_id))
                logger.info(f"用户 {nickname} 更新了用户名和昵称: {username}, {nickname_input}")
            elif username:
                # 只更新用户名
                db.execute('UPDATE USERS SET USERNAME = ? WHERE ID = ?', (username, user_id))
                logger.info(f"用户 {nickname} 更新了用户名: {username}")
            elif nickname_input:
                # 只更新昵称
                db.execute('UPDATE USERS SET NICKNAME = ? WHERE ID = ?', (nickname_input, user_id))
                logger.info(f"用户 {nickname} 更新了昵称: {nickname_input}")
        
        # 更新头像
        if avatar_file and allowed_file(avatar_file.filename):
            upload_folder = 'static/uploads/avatars'
            os.makedirs(upload_folder, exist_ok=True)
            filename = secure_filename(avatar_file.filename)
            file_path = os.path.join(upload_folder, filename)
            avatar_file.save(file_path)
            avatar_url = f"/{upload_folder}/{filename}"
            # 注意：这里使用大写字段名 'AVATAR_URL'
            db.execute('UPDATE USERS SET AVATAR_URL = ? WHERE ID = ?', (avatar_url, user_id))
            logger.info(f"用户 {nickname} 更新了头像: {avatar_url}")
            updated_avatar = True
        elif not avatar_file:
            logger.info(f"用户 {nickname} 未选择新头像，跳过头像更新")

        # 提交数据库更改
        db.commit()
        logger.info(f"用户 {nickname} 个人资料更新成功")

        # 更新会话中的信息
        if username:
            session['username'] = username
        if nickname_input:
            session['nickname'] = nickname_input
            nickname = nickname_input
        if updated_avatar:
            session['avatar_url'] = avatar_url

        return jsonify({"success": True, "message": "个人资料更新成功"})
    except Exception as e:
        logger.error(f"更新个人资料失败: {e}")
        return jsonify({"success": False, "message": "更新失败，请稍后再试"}), 500

# 修改密码路由
def change_password():
    try:
        user_id = session['user_id']
        nickname = session.get('nickname')
        logger.info(f"用户 {nickname} 请求修改密码")

        # 获取表单数据
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 验证输入
        if not old_password or not new_password:
            logger.warning(f"用户 {nickname} 密码修改失败: 缺少必要参数")
            return jsonify(success=False, message='请提供当前密码和新密码。'), 400
            
        # 验证确认密码
        if new_password != confirm_password:
            logger.warning(f"用户 {nickname} 密码修改失败: 新密码和确认密码不一致")
            return jsonify(success=False, message='新密码和确认密码不一致。'), 400
        
        # 验证新密码强度
        valid_password, password_error = validate_password(new_password)
        if not valid_password:
            logger.warning(f"用户 {nickname} 密码修改失败: {password_error}")
            return jsonify(success=False, message=password_error), 400

        db = get_db()
        
        # 获取当前用户信息
        user = db.execute('SELECT * FROM USERS WHERE ID = ?', (user_id,)).fetchone()
        if not user:
            logger.error(f"用户 {nickname} 密码修改失败: 用户不存在")
            return jsonify(success=False, message='用户不存在。'), 400

        # 验证当前密码 (使用 bcrypt 验证)
        hashed_password = user['PASSWORD']
        if not isinstance(hashed_password, str):
            hashed_password = hashed_password.decode('utf-8')
            
        if not bcrypt.checkpw(old_password.encode('utf-8'), hashed_password.encode('utf-8')):
            logger.warning(f"用户 {nickname} 密码修改失败: 当前密码错误")
            return jsonify(success=False, message='当前密码错误。'), 400

        # 更新密码 (使用 bcrypt 生成新密码)
        new_hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(12))  # 使用更高的工作因子
        if isinstance(new_hashed_password, bytes):
            new_hashed_password = new_hashed_password.decode('utf-8')
            
        db.execute('UPDATE USERS SET PASSWORD = ? WHERE ID = ?', (new_hashed_password, user_id))
        db.commit()
        
        logger.info(f"用户 {nickname} 密码修改成功")
        return jsonify(success=True, message='密码修改成功！'), 200
        
    except Exception as e:
        logger.error(f"修改密码失败: {e}")
        return jsonify(success=False, message='密码修改失败，请稍后再试。'), 500
