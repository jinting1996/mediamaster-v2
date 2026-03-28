"""
MediaMaster V2 优化版 - 下载任务添加器
- 添加重试机制
- 统一错误处理
- 改进连接管理
"""
import os
import sys
import time
import logging
import sqlite3
from typing import Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============== 配置 ==============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/log/download_task_adder.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============== 配置类 ==============
@dataclass
class DownloaderConfig:
    """下载器配置"""
    type: str = "transmission"
    host: str = "127.0.0.1"
    port: int = 9091
    username: str = ""
    password: str = ""
    enabled: bool = False


class ConfigLoader:
    """配置加载器"""
    
    @staticmethod
    def load(db_path: str = "/config/data.db") -> dict:
        """从数据库加载配置"""
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT OPTION, VALUE FROM CONFIG")
                config = {opt: val for opt, val in cursor.fetchall()}
            logger.debug("配置加载成功")
            return config
        except sqlite3.Error as e:
            logger.error(f"配置加载失败: {e}")
            sys.exit(1)


class RetryableTask:
    """可重试任务装饰器"""
    
    def __init__(self, max_attempts: int = 3, delay: float = 2.0):
        self.max_attempts = max_attempts
        self.delay = delay
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, self.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < self.max_attempts:
                        wait_time = self.delay * (attempt - 1)
                        logger.warning(f"尝试 {attempt}/{self.max_attempts} 失败，{wait_time}s 后重试: {e}")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"达到最大重试次数: {e}")
            raise last_error
        return wrapper


class TransmissionAdder:
    """Transmission 任务添加器"""
    
    def __init__(self, config: DownloaderConfig):
        self.config = config
    
    @RetryableTask(max_attempts=3, delay=2.0)
    def add(self, torrent_path: str, label: str = "") -> bool:
        """添加任务到 Transmission"""
        try:
            from transmission_rpc import Client
            
            client = Client(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password
            )
            
            with open(torrent_path, "rb") as f:
                result = client.add_torrent(f.read())
            
            # 设置标签
            if label:
                try:
                    client.change_torrent(result.id, labels=[label])
                except Exception as e:
                    logger.warning(f"设置标签失败: {e}")
            
            # 设置分类
            try:
                client.change_torrent(result.id, group="mediamaster")
            except Exception as e:
                logger.warning(f"设置分类失败: {e}")
            
            logger.info(f"已添加到 Transmission: {os.path.basename(torrent_path)}")
            return True
            
        except Exception as e:
            logger.error(f"Transmission 添加失败: {e}")
            raise  # 让 RetryableTask 处理重试
    
    def test_connection(self) -> bool:
        """测试连接"""
        try:
            from transmission_rpc import Client
            client = Client(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password
            )
            client.get_session()
            return True
        except Exception as e:
            logger.error(f"Transmission 连接失败: {e}")
            return False


class QBittorrentAdder:
    """qBittorrent 任务添加器"""
    
    def __init__(self, config: DownloaderConfig):
        self.config = config
        self._client = None
    
    @property
    def client(self):
        """延迟初始化 client"""
        if self._client is None:
            from qbittorrentapi import Client
            self._client = Client(
                host=f"http://{self.config.host}:{self.config.port}",
                username=self.config.username,
                password=self.config.password
            )
        return self._client
    
    @RetryableTask(max_attempts=3, delay=2.0)
    def add(self, torrent_path: str, label: str = "") -> bool:
        """添加任务到 qBittorrent"""
        try:
            # 确保已登录
            try:
                self.client.auth_log_in()
            except Exception:
                pass  # 可能已登录
            
            with open(torrent_path, "rb") as f:
                self.client.torrents_add(
                    torrent_files=f.read(),
                    tags=label if label else None,
                    category="mediamaster"
                )
            
            logger.info(f"已添加到 qBittorrent: {os.path.basename(torrent_path)}")
            return True
            
        except Exception as e:
            logger.error(f"qBittorrent 添加失败: {e}")
            raise
    
    def test_connection(self) -> bool:
        """测试连接"""
        try:
            self.client.auth_log_in()
            return True
        except Exception as e:
            logger.error(f"qBittorrent 连接失败: {e}")
            return False


class XunleiAdder:
    """讯雷下载器（暂不支持 API）"""
    
    def add(self, torrent_path: str, label: str = "") -> bool:
        """讯雷需要手动添加"""
        logger.info(f"讯雷下载器: 请手动添加 {os.path.basename(torrent_path)}")
        return True


class DownloadTaskManager:
    """下载任务管理器"""
    
    def __init__(self, config: dict):
        self.config = config
        self.downloader_config = self._parse_config()
    
    def _parse_config(self) -> DownloaderConfig:
        """解析下载器配置"""
        return DownloaderConfig(
            type=self.config.get("download_type", "transmission").lower(),
            host=self.config.get("download_host", "127.0.0.1"),
            port=int(self.config.get("download_port", 9091)),
            username=self.config.get("download_username", ""),
            password=self.config.get("download_password", ""),
            enabled=self.config.get("download_mgmt", "False").lower() == "true"
        )
    
    def get_adder(self):
        """获取对应的添加器"""
        download_type = self.downloader_config.type
        
        if download_type == "xunlei":
            return XunleiAdder()
        elif download_type == "transmission":
            return TransmissionAdder(self.downloader_config)
        elif download_type == "qbittorrent":
            return QBittorrentAdder(self.downloader_config)
        else:
            raise ValueError(f"不支持的下载器: {download_type}")
    
    def add_task(self, torrent_path: str) -> bool:
        """添加下载任务"""
        if not self.downloader_config.enabled:
            logger.error("下载管理功能未启用")
            return False
        
        # 从种子文件名提取标签
        label = os.path.splitext(os.path.basename(torrent_path))[0]
        
        adder = self.get_adder()
        return adder.add(torrent_path, label)
    
    def test_connection(self) -> bool:
        """测试下载器连接"""
        try:
            adder = self.get_adder()
            return adder.test_connection()
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="下载任务添加器")
    parser.add_argument("torrent_file", help="种子文件路径")
    parser.add_argument("--test", "-t", action="store_true", help="测试连接")
    args = parser.parse_args()
    
    torrent_path = args.torrent_file
    
    # 检查文件
    if not os.path.isfile(torrent_path):
        logger.error(f"种子文件不存在: {torrent_path}")
        sys.exit(1)
    
    # 加载配置
    config = ConfigLoader.load()
    
    # 测试模式
    if args.test:
        manager = DownloadTaskManager(config)
        if manager.test_connection():
            logger.info("✅ 下载器连接成功")
            sys.exit(0)
        else:
            logger.error("❌ 下载器连接失败")
            sys.exit(1)
    
    # 添加任务
    manager = DownloadTaskManager(config)
    success = manager.add_task(torrent_path)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
