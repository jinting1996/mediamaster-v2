"""
MediaMaster V2 优化版下载器
- 移除 Selenium，改用 requests
- 添加重试机制
- 统一错误处理
"""
import os
import re
import time
import logging
import sqlite3
import requests
from pathlib import Path
from urllib.parse import urljoin
from typing import Optional, Dict, List
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============== 配置 ==============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/log/downloader.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============== 常量 ==============
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2


@dataclass
class SiteConfig:
    """站点配置"""
    name: str
    login_url: str
    search_url: str
    login_api: str = ""  # 如果有API则优先用
    need_captcha: bool = False


SITES = {
    "bthd": SiteConfig(
        name="高清影视之家",
        login_url="https://www.btbdhd.com/member.php?mod=logging",
        search_url="https://www.btbdhd.com/search.php"
    ),
    "gy": SiteConfig(
        name="观影",
        login_url="https://www.gy6y.com/user/login",
        search_url="https://www.gy6y.com/search"
    ),
}


class DownloaderError(Exception):
    """下载器错误"""
    pass


class SessionManager:
    """Session 管理器 - 复用连接"""
    
    def __init__(self):
        self.session: Optional[requests.Session] = None
        self.cookies: Dict = {}
    
    def create_session(self) -> requests.Session:
        """创建 session"""
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
        return self.session
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET 请求 with 重试"""
        session = self.create_session()
        kwargs.setdefault("timeout", TIMEOUT)
        kwargs.setdefault("allow_redirects", True)
        
        for attempt in range(MAX_RETRIES):
            try:
                resp = session.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                logger.warning(f"请求失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    raise DownloaderError(f"请求失败: {url}") from e
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST 请求 with 重试"""
        session = self.create_session()
        kwargs.setdefault("timeout", TIMEOUT)
        
        for attempt in range(MAX_RETRIES):
            try:
                resp = session.post(url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                logger.warning(f"POST失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    raise DownloaderError(f"POST失败: {url}") from e
    
    def login(self, site: str, username: str, password: str) -> bool:
        """登录站点"""
        site_config = SITES.get(site)
        if not site_config:
            raise DownloaderError(f"未知站点: {site}")
        
        # 尝试 API 登录
        if site_config.login_api:
            try:
                resp = self.post(site_config.login_api, data={
                    "username": username,
                    "password": password
                })
                if resp.status_code == 200:
                    self.cookies.update(resp.cookies.get_dict())
                    logger.info(f"[{site_config.name}] API登录成功")
                    return True
            except Exception as e:
                logger.warning(f"API登录失败，尝试表单登录: {e}")
        
        # 表单登录回退
        try:
            resp = self.get(site_config.login_url)
            
            # 提取登录表单需要的参数
            form_hash = self._extract_form_hash(resp.text)
            
            login_data = {
                "username": username,
                "password": password,
                "loginsubmit": "true",
                "formhash": form_hash,
            }
            
            resp = self.post(site_config.login_url, data=login_data)
            
            if self._check_login_success(resp.text):
                logger.info(f"[{site_config.name}] 登录成功")
                return True
            else:
                logger.error(f"[{site_config.name}] 登录失败")
                return False
                
        except Exception as e:
            logger.error(f"[{site_config.name}] 登录异常: {e}")
            return False
    
    def _extract_form_hash(self, html: str) -> str:
        """从HTML提取 formhash"""
        match = re.search(r'name="formhash"[^>]*value="([^"]+)"', html)
        if match:
            return match.group(1)
        match = re.search(r'formhash=([^&"]+)', html)
        return match.group(1) if match else ""
    
    def _check_login_success(self, html: str) -> bool:
        """检查登录是否成功"""
        indicators = ["欢迎您回来", "登录成功", "logout", "退出登录"]
        return any(indicator in html for indicator in indicators)


class TorrentDownloader:
    """种子文件下载器"""
    
    def __init__(self, db_path: str = "/config/data.db", download_dir: str = "/Torrent"):
        self.db_path = db_path
        self.download_dir = download_dir
        self.session_mgr = SessionManager()
        self.config: Dict = {}
        
        os.makedirs(download_dir, exist_ok=True)
    
    def load_config(self) -> Dict:
        """从数据库加载配置"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT OPTION, VALUE FROM CONFIG")
                self.config = {opt: val for opt, val in cursor.fetchall()}
            logger.debug("配置加载成功")
            return self.config
        except sqlite3.Error as e:
            logger.error(f"配置加载失败: {e}")
            raise
    
    def download_torrent(self, url: str, filename: str = "") -> Optional[str]:
        """下载种子文件"""
        try:
            resp = self.session_mgr.get(url, stream=True)
            
            # 确定文件名
            if not filename:
                content_disp = resp.headers.get("Content-Disposition", "")
                match = re.search(r'filename[^=]*=["\']?([^"\'\n]+)', content_disp)
                filename = match.group(1).strip() if match else "download.torrent"
            
            # 清理文件名
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            filepath = os.path.join(self.download_dir, filename)
            
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"种子文件已下载: {filename}")
            return filepath
            
        except Exception as e:
            logger.error(f"种子下载失败: {e}")
            return None
    
    def search_and_download(self, site: str, keyword: str, quality: str = "1080p") -> Optional[str]:
        """搜索并下载种子"""
        site_config = SITES.get(site)
        if not site_config:
            raise DownloaderError(f"未知站点: {site}")
        
        # 先登录
        username = self.config.get("bt_login_username", "")
        password = self.config.get("bt_login_password", "")
        
        if username and password:
            self.session_mgr.login(site, username, password)
        
        # 搜索资源
        try:
            search_params = {"q": keyword}
            resp = self.session_mgr.get(site_config.search_url, params=search_params)
            
            # 解析搜索结果（需根据实际站点调整）
            torrent_url = self._parse_search_result(resp.text, quality)
            
            if torrent_url:
                # 下载种子
                filename = f"{keyword}.torrent"
                return self.download_torrent(torrent_url, filename)
            else:
                logger.warning(f"未找到资源: {keyword}")
                return None
                
        except Exception as e:
            logger.error(f"搜索/下载失败: {e}")
            return None
    
    def _parse_search_result(self, html: str, quality: str) -> Optional[str]:
        """解析搜索结果 - 需根据站点调整"""
        # 通用解析示例（实际需根据站点调整）
        # 1. 查找 torrent 链接
        patterns = [
            r'href="([^"]*\.torrent[^"]*)"',
            r'href="([^"]*download[^"]*)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.I)
            for match in matches:
                if "torrent" in match.lower():
                    return match
        
        return None


class DownloadTaskAdder:
    """下载任务添加器"""
    
    SUPPORTED_DOWNLOADERS = ["transmission", "qbittorrent", "xunlei"]
    
    def __init__(self, db_path: str = "/config/data.db"):
        self.db_path = db_path
        self.config: Dict = {}
    
    def load_config(self):
        """加载配置"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT OPTION, VALUE FROM CONFIG")
            self.config = {opt: val for opt, val in cursor.fetchall()}
    
    def add_to_downloader(self, torrent_path: str) -> bool:
        """添加到下载器"""
        download_type = self.config.get("download_type", "transmission").lower()
        
        if download_type == "xunlei":
            logger.info("下载器为讯雷，跳过")
            return True
        
        if download_type == "transmission":
            return self._add_to_transmission(torrent_path)
        elif download_type == "qbittorrent":
            return self._add_to_qbittorrent(torrent_path)
        else:
            logger.error(f"不支持的下载器: {download_type}")
            return False
    
    def _add_to_transmission(self, torrent_path: str) -> bool:
        """添加到 Transmission"""
        try:
            from transmission_rpc import Client
            
            host = self.config.get("download_host", "127.0.0.1")
            port = int(self.config.get("download_port", 9091))
            username = self.config.get("download_username", "")
            password = self.config.get("download_password", "")
            
            client = Client(
                host=host,
                port=port,
                username=username,
                password=password
            )
            
            with open(torrent_path, "rb") as f:
                result = client.add_torrent(f.read())
            
            # 设置分类
            try:
                client.change_torrent(result.id, group="mediamaster")
            except Exception:
                pass
            
            logger.info(f"已添加到 Transmission: {os.path.basename(torrent_path)}")
            return True
            
        except Exception as e:
            logger.error(f"添加到 Transmission 失败: {e}")
            return False
    
    def _add_to_qbittorrent(self, torrent_path: str) -> bool:
        """添加到 qBittorrent"""
        try:
            from qbittorrentapi import Client
            
            host = self.config.get("download_host", "127.0.0.1")
            port = int(self.config.get("download_port", 9091))
            username = self.config.get("download_username", "")
            password = self.config.get("download_password", "")
            
            client = Client(host=f"http://{host}:{port}", username=username, password=password)
            client.auth_log_in()
            
            with open(torrent_path, "rb") as f:
                client.torrents_add(torrent_files=f.read(), category="mediamaster")
            
            logger.info(f"已添加到 qBittorrent: {os.path.basename(torrent_path)}")
            return True
            
        except Exception as e:
            logger.error(f"添加到 qBittorrent 失败: {e}")
            return False


def main():
    """主函数示例"""
    import argparse
    
    parser = argparse.ArgumentParser(description="优化版下载器")
    parser.add_argument("--site", default="bthd", help="站点名称")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--quality", default="1080p", help="画质要求")
    args = parser.parse_args()
    
    # 初始化
    downloader = TorrentDownloader()
    downloader.load_config()
    
    # 搜索下载
    result = downloader.search_and_download(args.site, args.keyword, args.quality)
    
    if result:
        # 添加到下载器
        adder = DownloadTaskAdder()
        adder.load_config()
        adder.add_to_downloader(result)
    
    return result


if __name__ == "__main__":
    main()
