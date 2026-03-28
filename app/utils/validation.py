import re
from flask import request, jsonify

# 验证用户名
def validate_username(username):
    if not username or len(username) < 3 or len(username) > 20:
        return False, "用户名长度必须在3-20个字符之间"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "用户名只能包含字母、数字和下划线"
    return True, ""

# 验证密码
def validate_password(password):
    if not password or len(password) < 6:
        return False, "密码长度至少为6个字符"
    # 可以添加更多密码强度要求
    return True, ""

# 验证邮箱
def validate_email(email):
    if not email:
        return False, "邮箱不能为空"
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return False, "邮箱格式不正确"
    return True, ""

# 验证电影/电视剧标题
def validate_title(title):
    if not title or len(title) < 1 or len(title) > 200:
        return False, "标题长度必须在1-200个字符之间"
    return True, ""

# 验证年份
def validate_year(year):
    if not year:
        return False, "年份不能为空"
    try:
        year = int(year)
        if year < 1900 or year > 2100:
            return False, "年份必须在1900-2100之间"
        return True, ""
    except ValueError:
        return False, "年份必须是数字"

# 验证季数
def validate_season(season):
    if not season:
        return False, "季数不能为空"
    try:
        season = int(season)
        if season < 1 or season > 100:
            return False, "季数必须在1-100之间"
        return True, ""
    except ValueError:
        return False, "季数必须是数字"

# 验证集数
def validate_episode(episode):
    if not episode:
        return False, "集数不能为空"
    try:
        episode = int(episode)
        if episode < 1 or episode > 1000:
            return False, "集数必须在1-1000之间"
        return True, ""
    except ValueError:
        return False, "集数必须是数字"

# 验证请求数据
def validate_request_data(data, required_fields):
    missing_fields = []
    for field in required_fields:
        if field not in data or not data[field]:
            missing_fields.append(field)
    if missing_fields:
        return False, f"缺少必要字段: {', '.join(missing_fields)}"
    return True, ""

# 验证文件上传
def validate_file_upload(file, allowed_extensions):
    if not file:
        return False, "请选择文件"
    if '.' not in file.filename:
        return False, "文件没有扩展名"
    ext = file.filename.rsplit('.', 1)[1].lower()
    if ext not in allowed_extensions:
        return False, f"不支持的文件类型，仅支持: {', '.join(allowed_extensions)}"
    return True, ""
