from flask import request, jsonify, session, redirect, url_for
import sqlite3
from app.core.database import get_db
from app.core.config import setup_logger
from app.auth.auth import login_required

logger = setup_logger()

# 手动添加订阅
def add_subscription():
    try:
        # 获取请求数据
        data = request.json
        subscription_type = data.get('type')
        title = data.get('title')
        year = data.get('year')
        season = data.get('season', 1)
        start_episode = data.get('start_episode')
        end_episode = data.get('end_episode')

        # 检查必要字段
        if not subscription_type or not title or not year:
            return jsonify({"success": False, "message": "缺少必要的订阅信息"}), 400

        db = get_db()

        if subscription_type == 'tv':  # 电视剧订阅
            # 验证剧集信息
            if start_episode is None or end_episode is None:
                return jsonify({"success": False, "message": "电视剧订阅需要提供起始集和结束集"}), 400
            
            try:
                start_episode = int(start_episode)
                end_episode = int(end_episode)
                season = int(season)
            except (ValueError, TypeError):
                return jsonify({"success": False, "message": "季、起始集和结束集必须是数字"}), 400
                
            if start_episode <= 0 or end_episode <= 0 or start_episode > end_episode:
                return jsonify({"success": False, "message": "起始集和结束集必须是正整数，且起始集不能大于结束集"}), 400

            # 生成缺失的集数字符串，例如 "1,2,3,...,episodes"
            missing_episodes = ','.join(map(str, range(start_episode, end_episode + 1)))

            # 生成手动订阅的douban_id
            # 获取当前最大的manual编号
            max_id_row = db.execute(
                "SELECT MAX(CAST(SUBSTR(douban_id, 8) AS INTEGER)) as max_id FROM MISS_TVS WHERE douban_id LIKE 'manual-%'"
            ).fetchone()
            
            max_id = max_id_row['max_id'] if max_id_row['max_id'] else 0
            new_douban_id = f"manual-{max_id + 1}"

            # 检查是否已存在相同的订阅
            existing_tv = db.execute(
                'SELECT * FROM MISS_TVS WHERE title = ? AND year = ? AND season = ?',
                (title, year, season)
            ).fetchone()

            if existing_tv:
                return jsonify({"success": False, "message": "该电视剧订阅已存在"}), 400

            # 插入电视剧订阅
            db.execute(
                'INSERT INTO MISS_TVS (douban_id, title, year, season, missing_episodes) VALUES (?, ?, ?, ?, ?)',
                (new_douban_id, title, year, season, missing_episodes)
            )
            db.commit()
            logger.info(f"用户添加电视剧订阅: {title} ({year}) 季{season} 集{start_episode}-{end_episode} DOUBAN_ID: {new_douban_id}")
            return jsonify({"success": True, "message": "电视剧订阅添加成功"})

        elif subscription_type == 'movie':  # 电影订阅
            # 生成手动订阅的douban_id
            # 获取当前最大的manual编号
            max_id_row = db.execute(
                "SELECT MAX(CAST(SUBSTR(douban_id, 8) AS INTEGER)) as max_id FROM MISS_MOVIES WHERE douban_id LIKE 'manual%'"
            ).fetchone()
            
            max_id = max_id_row['max_id'] if max_id_row['max_id'] else 0
            new_douban_id = f"manual{max_id + 1}"

            # 检查是否已存在相同的订阅
            existing_movie = db.execute(
                'SELECT * FROM MISS_MOVIES WHERE title = ? AND year = ?',
                (title, year)
            ).fetchone()

            if existing_movie:
                return jsonify({"success": False, "message": "该电影订阅已存在"}), 400

            # 插入电影订阅
            db.execute(
                'INSERT INTO MISS_MOVIES (douban_id, title, year) VALUES (?, ?, ?)',
                (new_douban_id, title, year)
            )
            db.commit()
            logger.info(f"用户添加电影订阅: {title} ({year}) DOUBAN_ID: {new_douban_id}")
            return jsonify({"success": True, "message": "电影订阅添加成功"})

        else:
            return jsonify({"success": False, "message": "无效的订阅类型"}), 400

    except Exception as e:
        logger.error(f"添加订阅失败: {e}")
        return jsonify({"success": False, "message": "添加订阅失败，请稍后再试"}), 500

# 取消热门推荐中的订阅
def cancel_subscription():
    try:
        # 获取请求数据
        data = request.json
        title = data.get('title')
        year = data.get('year')
        season = data.get('season')
        media_type = data.get('mediaType')

        # 检查必要字段
        if not title or not year or not media_type:
            return jsonify({"success": False, "message": "缺少必要的参数"}), 400

        db = get_db()

        if media_type == 'tv':  # 电视剧取消订阅
            # 检查是否存在该订阅
            existing_tv = db.execute(
                'SELECT * FROM MISS_TVS WHERE title = ? AND year = ? AND season = ?',
                (title, year, season)
            ).fetchone()

            if not existing_tv:
                return jsonify({"success": False, "message": "未找到该电视剧订阅"}), 404

            # 删除订阅
            db.execute(
                'DELETE FROM MISS_TVS WHERE title = ? AND year = ? AND season = ?',
                (title, year, season)
            )
            db.commit()
            logger.info(f"用户取消电视剧订阅: {title} ({year}) 季{season}")
            return jsonify({"success": True, "message": "电视剧订阅已取消"})

        elif media_type == 'movie':  # 电影取消订阅
            # 检查是否存在该订阅
            existing_movie = db.execute(
                'SELECT * FROM MISS_MOVIES WHERE title = ? AND year = ?',
                (title, year)
            ).fetchone()

            if not existing_movie:
                return jsonify({"success": False, "message": "未找到该电影订阅"}), 404

            # 删除订阅
            db.execute(
                'DELETE FROM MISS_MOVIES WHERE title = ? AND year = ?',
                (title, year)
            )
            db.commit()
            logger.info(f"用户取消电影订阅: {title} ({year})")
            return jsonify({"success": True, "message": "电影订阅已取消"})

        else:
            return jsonify({"success": False, "message": "无效的媒体类型"}), 400

    except Exception as e:
        logger.error(f"取消订阅失败: {e}")
        return jsonify({"success": False, "message": "取消订阅失败，请稍后再试"}), 500

# 从热门推荐中添加订阅
def tmdb_subscriptions():
    try:
        # 获取请求数据
        data = request.json
        title = data.get('title')
        year = data.get('year')
        season = data.get('season')  # 如果是电视剧，获取季编号
        episodes = data.get('episodes')  # 如果是电视剧，获取总集数

        # 检查必要字段
        if not title or not year:
            return jsonify({"success": False, "message": "缺少必要的订阅信息"}), 400

        db = get_db()

        if season and episodes:  # 如果包含季编号和集数，则为电视剧订阅
            # 生成缺失的集数字符串，例如 "1,2,3,...,episodes"
            missing_episodes = ','.join(map(str, range(1, episodes + 1)))

            # 检查是否已存在相同的订阅（标题、年份和季数的组合）
            existing_tv = db.execute(
                'SELECT * FROM MISS_TVS WHERE title = ? AND year = ? AND season = ?',
                (title, year, season)
            ).fetchone()

            if existing_tv:
                return jsonify({"success": False, "message": "该电视剧订阅已存在"}), 400

            # 插入电视剧订阅
            db.execute(
                'INSERT INTO MISS_TVS (title, year, season, missing_episodes) VALUES (?, ?, ?, ?)',
                (title, year, season, missing_episodes)
            )
            db.commit()
            return jsonify({"success": True, "message": "电视剧订阅成功"})

        else:  # 否则为电影订阅
            # 检查是否已存在相同的订阅
            existing_movie = db.execute(
                'SELECT * FROM MISS_MOVIES WHERE title = ? AND year = ?',
                (title, year)
            ).fetchone()

            if existing_movie:
                return jsonify({"success": False, "message": "该电影订阅已存在"}), 400

            # 插入电影订阅
            db.execute(
                'INSERT INTO MISS_MOVIES (title, year) VALUES (?, ?)',
                (title, year)
            )
            db.commit()
            return jsonify({"success": True, "message": "电影订阅成功"})

    except Exception as e:
        logger.error(f"订阅处理失败: {e}")
        return jsonify({"success": False, "message": "订阅失败，请稍后再试"}), 500

# 检查热门推荐中的订阅状态（是否已订阅或已入库）
def check_subscriptions():
    try:
        data = request.json
        title = data.get('title')
        year = data.get('year')
        season = data.get('season')  # 如果是电视剧，获取季编号

        db = get_db()

        # 检查是否已订阅
        if season:  # 检查电视剧订阅（特定季）
            existing_tv = db.execute(
                'SELECT * FROM MISS_TVS WHERE title = ? AND year = ? AND season = ?',
                (title, year, season)
            ).fetchone()
            if existing_tv:
                return jsonify({"subscribed": True, "status": "subscribed"})

            # 检查是否已入库（特定季）
            existing_tv_in_library = db.execute(
                '''
                SELECT t1.id FROM LIB_TVS AS t1
                JOIN LIB_TV_SEASONS AS t2 ON t1.id = t2.tv_id
                WHERE t1.title = ? AND t1.year = ? AND t2.season = ?
                ''',
                (title, year, season)
            ).fetchone()
            if existing_tv_in_library:
                return jsonify({"subscribed": True, "status": "in_library"})
        else:  # 检查电影订阅或电视剧整体订阅
            # 检查电影订阅
            existing_movie = db.execute(
                'SELECT * FROM MISS_MOVIES WHERE title = ? AND year = ?',
                (title, year)
            ).fetchone()
            if existing_movie:
                return jsonify({"subscribed": True, "status": "subscribed"})

            # 检查是否已入库（电影）
            existing_movie_in_library = db.execute(
                'SELECT id FROM LIB_MOVIES WHERE title = ? AND year = ?',
                (title, year)
            ).fetchone()
            if existing_movie_in_library:
                return jsonify({"subscribed": True, "status": "in_library"})

        return jsonify({"subscribed": False, "status": "not_found"})
    except Exception as e:
        logger.error(f"检查订阅状态失败: {e}")
        return jsonify({"subscribed": False, "error": "检查失败"}), 500

# 编辑订阅
def edit_subscription(type, id):
    db = get_db()
    if type == 'movie':
        subscription = db.execute('SELECT * FROM MISS_MOVIES WHERE id = ?', (id,)).fetchone()
    elif type == 'tv':
        subscription = db.execute('SELECT * FROM MISS_TVS WHERE id = ?', (id,)).fetchone()
    else:
        return jsonify(success=False, message="Invalid subscription type"), 400

    if request.method == 'POST':
        title = request.form['title']
        year = request.form.get('year')
        season = request.form.get('season')
        missing_episodes = request.form.get('missing_episodes')

        try:
            if type == 'movie':
                db.execute('UPDATE MISS_MOVIES SET title = ?, year = ? WHERE id = ?', (title, year, id))
            elif type == 'tv':
                db.execute('UPDATE MISS_TVS SET title = ?, season = ?, missing_episodes = ? WHERE id = ?', 
                          (title, season, missing_episodes, id))
            db.commit()
            logger.info(f"用户更新订阅: {type} ID={id}")
            return jsonify(success=True, message="订阅更新成功")
        except Exception as e:
            db.rollback()
            logger.error(f"更新订阅失败: {e}")
            return jsonify(success=False, message="更新失败，请稍后再试"), 500

    # GET 请求时返回 JSON 数据
    if subscription:
        return jsonify(dict(subscription))
    else:
        return jsonify(success=False, message="未找到订阅"), 404

# 删除订阅
def delete_subscription(type, id):
    db = get_db()
    if type == 'movie':
        db.execute('DELETE FROM MISS_MOVIES WHERE id = ?', (id,))
    elif type == 'tv':
        db.execute('DELETE FROM MISS_TVS WHERE id = ?', (id,))
    else:
        return "Invalid subscription type", 400
    db.commit()
    return redirect(url_for('subscriptions'))

# 获取豆瓣想看数据的JSON接口
def douban_subscriptions_json():
    try:
        db = get_db()
        
        # 获取电影订阅数据
        rss_movies = db.execute('SELECT * FROM RSS_MOVIES').fetchall()
        # 获取电视剧订阅数据
        rss_tvs = db.execute('SELECT * FROM RSS_TVS').fetchall()
        
        # 转换为字典列表并添加状态字段
        movies_data = []
        for movie in rss_movies:
            movie_dict = dict(movie)
            # 确保包含 STATUS 字段，默认为 "想看"
            movie_dict['STATUS'] = movie_dict.get('STATUS', '想看')
            movies_data.append(movie_dict)
            
        tvs_data = []
        for tv in rss_tvs:
            tv_dict = dict(tv)
            # 确保包含 STATUS 字段，默认为 "想看"
            tv_dict['STATUS'] = tv_dict.get('STATUS', '想看')
            tvs_data.append(tv_dict)
        
        # 返回JSON响应
        return jsonify({
            "rss_movies": movies_data,
            "rss_tvs": tvs_data
        })
    except Exception as e:
        logger.error(f"获取豆瓣订阅数据失败: {e}")
        return jsonify({"error": "获取数据失败"}), 500

# 获取剧集关联列表的JSON接口
def tv_alias_list_json():
    try:
        db = get_db()
        alias_list = db.execute('SELECT * FROM LIB_TV_ALIAS ORDER BY id DESC').fetchall()
        # 将Row对象转换为字典列表
        alias_list_dict = [dict(row) for row in alias_list]
        return jsonify({"alias_list": alias_list_dict})
    except Exception as e:
        logger.error(f"获取剧集关联列表失败: {e}")
        return jsonify({"error": "获取剧集关联列表失败"}), 500

# 获取单个剧集关联信息的JSON接口
def tv_alias_edit_json(alias_id):
    try:
        db = get_db()
        alias = db.execute('SELECT * FROM LIB_TV_ALIAS WHERE id = ?', (alias_id,)).fetchone()
        if alias:
            return jsonify({"alias": dict(alias)})
        else:
            return jsonify({"error": "未找到该关联"}), 404
    except Exception as e:
        logger.error(f"获取剧集关联信息失败: {e}")
        return jsonify({"error": "获取剧集关联信息失败"}), 500

# 添加剧集关联的API接口
def tv_alias_add_api():
    try:
        data = request.json
        alias = data.get('alias', '').strip()
        target_title = data.get('target_title', '').strip()
        target_season = data.get('target_season', None)
        
        if not alias or not target_title:
            return jsonify({"success": False, "message": "别名和目标名称不能为空"}), 400
            
        db = get_db()
        try:
            db.execute('INSERT INTO LIB_TV_ALIAS (ALIAS, TARGET_TITLE, TARGET_SEASON) VALUES (?, ?, ?)', 
                      (alias, target_title, target_season))
            db.commit()
            return jsonify({"success": True, "message": "添加成功"})
        except sqlite3.IntegrityError:
            return jsonify({"success": False, "message": "该别名已存在"}), 400
    except Exception as e:
        logger.error(f"添加剧集关联失败: {e}")
        return jsonify({"success": False, "message": "添加失败，请稍后再试"}), 500

# 编辑剧集关联的API接口
def tv_alias_edit_api(alias_id):
    try:
        data = request.json
        alias = data.get('alias', '').strip()
        target_title = data.get('target_title', '').strip()
        target_season = data.get('target_season', None)
        
        if not alias or not target_title:
            return jsonify({"success": False, "message": "别名和目标名称不能为空"}), 400
            
        db = get_db()
        existing_alias = db.execute('SELECT * FROM LIB_TV_ALIAS WHERE id = ?', (alias_id,)).fetchone()
        if not existing_alias:
            return jsonify({"success": False, "message": "未找到该关联"}), 404
            
        try:
            db.execute('UPDATE LIB_TV_ALIAS SET ALIAS = ?, TARGET_TITLE = ?, TARGET_SEASON = ? WHERE id = ?', 
                      (alias, target_title, target_season, alias_id))
            db.commit()
            return jsonify({"success": True, "message": "更新成功"})
        except sqlite3.IntegrityError:
            return jsonify({"success": False, "message": "该别名已存在"}), 400
    except Exception as e:
        logger.error(f"更新剧集关联失败: {e}")
        return jsonify({"success": False, "message": "更新失败，请稍后再试"}), 500

# 删除剧集关联的API接口
def tv_alias_delete_api(alias_id):
    try:
        db = get_db()
        existing_alias = db.execute('SELECT * FROM LIB_TV_ALIAS WHERE id = ?', (alias_id,)).fetchone()
        if not existing_alias:
            return jsonify({"success": False, "message": "未找到该关联"}), 404
            
        db.execute('DELETE FROM LIB_TV_ALIAS WHERE id = ?', (alias_id,))
        db.commit()
        return jsonify({"success": True, "message": "删除成功"})
    except Exception as e:
        logger.error(f"删除剧集关联失败: {e}")
        return jsonify({"success": False, "message": "删除失败，请稍后再试"}), 500
