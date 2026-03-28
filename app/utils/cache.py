import time
import threading
from functools import lru_cache

# 简单的内存缓存实现
class Cache:
    def __init__(self):
        self.cache = {}
        self.lock = threading.RLock()
        self.default_ttl = 3600  # 默认缓存时间 1 小时

    def get(self, key):
        """获取缓存值"""
        with self.lock:
            if key in self.cache:
                value, expiry = self.cache[key]
                if time.time() < expiry:
                    return value
                # 缓存已过期，删除
                del self.cache[key]
            return None

    def set(self, key, value, ttl=None):
        """设置缓存值"""
        with self.lock:
            ttl = ttl or self.default_ttl
            expiry = time.time() + ttl
            self.cache[key] = (value, expiry)

    def delete(self, key):
        """删除缓存值"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]

    def clear(self):
        """清空所有缓存"""
        with self.lock:
            self.cache.clear()

    def get_or_set(self, key, func, ttl=None):
        """获取缓存值，如果不存在则执行函数并缓存结果"""
        value = self.get(key)
        if value is None:
            value = func()
            self.set(key, value, ttl)
        return value

# 创建全局缓存实例
cache = Cache()

# 装饰器：缓存函数结果
def cached(ttl=None):
    def decorator(func):
        @lru_cache(maxsize=None)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key = f"{func.__name__}:{args}:{kwargs}"
            return cache.get_or_set(key, lambda: func(*args, **kwargs), ttl)
        return wrapper
    return decorator
