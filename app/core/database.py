import sqlite3
import threading
from flask import g
from app.core.config import DATABASE, setup_logger

logger = setup_logger()

# 数据库连接池管理
class DatabaseManager:
    def __init__(self):
        self.connections = {}
        self.lock = threading.RLock()

    def get_connection(self, thread_id):
        with self.lock:
            if thread_id not in self.connections:
                try:
                    conn = sqlite3.connect(DATABASE, check_same_thread=False)
                    conn.row_factory = sqlite3.Row
                    # 启用外键约束
                    conn.execute('PRAGMA foreign_keys = ON')
                    # 启用 WAL 模式以提高并发性能
                    conn.execute('PRAGMA journal_mode = WAL')
                    # 设置缓存大小
                    conn.execute('PRAGMA cache_size = -64000')  # 64MB 缓存
                    self.connections[thread_id] = conn
                    logger.debug(f"Created new database connection for thread {thread_id}")
                except Exception as e:
                    logger.error(f"Error creating database connection: {e}")
                    raise
            return self.connections[thread_id]

    def close_connection(self, thread_id):
        with self.lock:
            if thread_id in self.connections:
                try:
                    self.connections[thread_id].close()
                    del self.connections[thread_id]
                    logger.debug(f"Closed database connection for thread {thread_id}")
                except Exception as e:
                    logger.error(f"Error closing database connection: {e}")

    def close_all_connections(self):
        with self.lock:
            for thread_id, conn in list(self.connections.items()):
                try:
                    conn.close()
                    del self.connections[thread_id]
                except Exception as e:
                    logger.error(f"Error closing database connection: {e}")

# 创建全局数据库管理器
db_manager = DatabaseManager()

# 获取数据库连接
def get_db():
    thread_id = str(g.get('_thread_id', threading.current_thread().name))
    return db_manager.get_connection(thread_id)

# 关闭数据库连接
def close_connection(exception):
    thread_id = str(g.get('_thread_id', threading.current_thread().name))
    db_manager.close_connection(thread_id)

# 优化数据库操作的辅助函数
def execute_query(query, params=(), commit=False):
    """执行数据库查询并返回结果"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if commit:
            conn.commit()
        return cursor
    except Exception as e:
        logger.error(f"Database query error: {query}, params: {params}, error: {e}")
        if commit:
            conn.rollback()
        raise

# 批量执行插入操作
def batch_insert(table, columns, values):
    """批量执行插入操作"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        placeholders = ','.join(['?' for _ in columns])
        column_names = ','.join(columns)
        query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"
        cursor.executemany(query, values)
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        logger.error(f"Batch insert error: {e}")
        conn.rollback()
        raise
