import os
import json
from app.core.database import execute_query
from app.core.config import setup_logger

logger = setup_logger()

class ConfigManager:
    """配置管理类"""
    def __init__(self):
        self.config_cache = {}
        self.config_file = '/config/config.json'
        self.load_config_from_file()
    
    def load_config_from_file(self):
        """从配置文件加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config_cache.update(json.load(f))
                logger.info("从配置文件加载配置成功")
            else:
                logger.warning(f"配置文件不存在: {self.config_file}")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
    
    def get(self, key, default=None):
        """获取配置值"""
        # 首先从环境变量获取
        env_value = os.environ.get(key.upper())
        if env_value is not None:
            return env_value
        
        # 然后从内存缓存获取
        if key in self.config_cache:
            return self.config_cache[key]
        
        # 最后从数据库获取
        try:
            result = execute_query('SELECT VALUE FROM CONFIG WHERE OPTION = ?', (key,)).fetchone()
            if result:
                value = result['VALUE']
                self.config_cache[key] = value
                return value
        except Exception as e:
            logger.error(f"从数据库获取配置失败: {e}")
        
        return default
    
    def set(self, key, value):
        """设置配置值"""
        # 更新内存缓存
        self.config_cache[key] = value
        
        # 更新数据库
        try:
            # 检查是否已存在
            result = execute_query('SELECT VALUE FROM CONFIG WHERE OPTION = ?', (key,)).fetchone()
            if result:
                execute_query('UPDATE CONFIG SET VALUE = ? WHERE OPTION = ?', (value, key), commit=True)
            else:
                execute_query('INSERT INTO CONFIG (OPTION, VALUE) VALUES (?, ?)', (key, value), commit=True)
            logger.info(f"配置 {key} 已更新为 {value}")
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
    
    def save_to_file(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config_cache, f, ensure_ascii=False, indent=2)
            logger.info("配置已保存到文件")
        except Exception as e:
            logger.error(f"保存配置到文件失败: {e}")
    
    def reload(self):
        """重新加载配置"""
        self.config_cache.clear()
        self.load_config_from_file()
        logger.info("配置已重新加载")

# 创建全局配置管理器实例
config_manager = ConfigManager()
