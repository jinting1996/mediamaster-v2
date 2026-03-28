from app.core.config import create_app, setup_logger
from app.core.routes import register_routes
from app.core.database import close_connection

# 创建Flask应用实例
app = create_app()

# 注册数据库连接关闭处理
app.teardown_appcontext(close_connection)

# 注册所有路由
register_routes(app)

# 启动应用
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, debug=False)
