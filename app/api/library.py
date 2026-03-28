from flask import request, jsonify, session, render_template
from werkzeug.exceptions import InternalServerError
from app.core.database import get_db
from app.core.config import setup_logger, APP_VERSION
from app.auth.auth import login_required

logger = setup_logger()

# 搜索接口
def api_search():
    db = get_db()
    query = request.args.get('q', '').strip()
    results = {
        'movies': [],
        'tvs': []
    }

    if query:
        # 查询电影并按年份排序
        movies = db.execute('SELECT * FROM LIB_MOVIES WHERE title LIKE ? ORDER BY year ASC', ('%' + query + '%',)).fetchall()
        
        # 查询电视剧并获取其季信息
        tvs = db.execute('SELECT * FROM LIB_TVS WHERE title LIKE ? ORDER BY title ASC', ('%' + query + '%',)).fetchall()

        # 处理电影结果
        for movie in movies:
            results['movies'].append({
                'type': 'movie',
                'id': movie['id'],
                'title': movie['title'],
                'year': movie['year'],
                'tmdb_id': movie['tmdb_id']
            })

        # 处理电视剧结果
        for tv in tvs:
            # 获取该电视剧的所有季信息，并按季数排序
            seasons = db.execute('SELECT season, episodes FROM LIB_TV_SEASONS WHERE tv_id = ? ORDER BY season ASC', (tv['id'],)).fetchall()
            results['tvs'].append({
                'type': 'tv',
                'id': tv['id'],
                'title': tv['title'],
                'year': tv['year'],
                'tmdb_id': tv['tmdb_id'],
                'seasons': [{'season': s['season'], 'episodes': s['episodes']} for s in seasons]
            })
    
    # 获取TMDB配置信息
    tmdb_config = {
        'tmdb_api_key': db.execute('SELECT VALUE FROM CONFIG WHERE OPTION = ?', ('tmdb_api_key',)).fetchone()['VALUE']
    }
    
    return jsonify({
        'query': query,
        'results': results,
        'tmdb_config': tmdb_config
    })

# 媒体库接口
def library():
    try:
        db = get_db()
        page = int(request.args.get('page', 1))
        per_page = 24
        offset = (page - 1) * per_page
        media_type = request.args.get('type', 'movies')

        # 获取电影或电视剧的总数
        total_movies = db.execute('SELECT COUNT(*) FROM LIB_MOVIES').fetchone()[0]
        total_tvs = db.execute('SELECT COUNT(DISTINCT id) FROM LIB_TVS').fetchone()[0]

        if media_type == 'movies':
            movies = db.execute('SELECT id, title, year, tmdb_id FROM LIB_MOVIES ORDER BY year DESC LIMIT ? OFFSET ?', (per_page, offset)).fetchall()
            tv_data = []
        elif media_type == 'tvs':
            movies = []
            # 查询电视剧基本信息
            tv_ids = db.execute('SELECT id FROM LIB_TVS ORDER BY year DESC LIMIT ? OFFSET ?', (per_page, offset)).fetchall()
            tv_ids = [tv['id'] for tv in tv_ids]

            # 获取这些电视剧的所有季信息
            tv_seasons = db.execute('''
                SELECT t1.id, t1.title, t2.season, t2.episodes, t1.year, t1.tmdb_id
                FROM LIB_TVS AS t1 
                JOIN LIB_TV_SEASONS AS t2 ON t1.id = t2.tv_id 
                WHERE t1.id IN ({})
                ORDER BY t1.year DESC, t1.id, t2.season 
            '''.format(','.join(['?'] * len(tv_ids))), tv_ids).fetchall()

            # 将相同电视剧的季信息合并，并计算总集数
            tv_data = {}
            for tv in tv_seasons:
                if tv['id'] not in tv_data:
                    tv_data[tv['id']] = {
                        'id': tv['id'],
                        'title': tv['title'],
                        'year': tv['year'],
                        'tmdb_id': tv['tmdb_id'],
                        'seasons': [],
                        'total_episodes': 0
                    }
                
                # 兼容处理 episodes 字段（可能是整数或字符串）
                episodes = tv['episodes']
                if isinstance(episodes, int):
                    episodes = str(episodes)

                # 解析 episodes 字符串，计算总集数
                episodes_list = episodes.split(',')
                num_episodes = len(episodes_list)

                tv_data[tv['id']]['seasons'].append({
                    'season': tv['season'],
                    'episodes': num_episodes  # 季的集数
                })
                tv_data[tv['id']]['total_episodes'] += num_episodes  # 累加总集数
            tv_data = list(tv_data.values())
        else:
            movies = []
            tv_data = []

        # 从数据库中读取 tmdb_api_key
        tmdb_api_key = db.execute('SELECT VALUE FROM CONFIG WHERE OPTION = ?', ('tmdb_api_key',)).fetchone()
        tmdb_api_key = tmdb_api_key['VALUE'] if tmdb_api_key else None

        # 从会话中获取用户昵称和头像
        nickname = session.get('nickname')
        avatar_url = session.get('avatar_url')

        return render_template('library.html', 
                               movies=movies, 
                               tv_data=tv_data, 
                               page=page, 
                               per_page=per_page, 
                               total_movies=total_movies, 
                               total_tvs=total_tvs, 
                               media_type=media_type, 
                               tmdb_api_key=tmdb_api_key,
                               nickname=nickname,
                               avatar_url=avatar_url,
                               version=APP_VERSION)
    except Exception as e:
        logger.error(f"发生错误: {e}")
        raise InternalServerError("发生意外错误，请稍后再试。")
