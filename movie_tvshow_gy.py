"""
MediaMaster V2 - 观影站点解析模块
使用 requests + BeautifulSoup 替代 Selenium
"""
import os
import re
import json
import logging
import sqlite3
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlencode
from dataclasses import dataclass
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/log/movie_tvshow_gy.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 30
MAX_RETRIES = 3

# 观影站点配置
GY_CONFIG = {
    "name": "观影",
    "base_url": "https://www.gy6y.com",
    "login_url": "https://www.gy6y.com/user/login",
    "search_url": "https://www.gy6y.com/search",
    "search_param": "q"
}


@dataclass
class GyResult:
    """观影搜索结果"""
    title: str
    link: str
    resolution: str = "未知"
    audio_tracks: List[str] = None
    subtitles: List[str] = None
    size: str = "未知"
    popularity: int = 0
    source: str = "gy"

    def __post_init__(self):
        if self.audio_tracks is None:
            self.audio_tracks = []
        if self.subtitles is None:
            self.subtitles = []


class GySessionManager:
    """观影 Session 管理器"""
    
    def __init__(self):
        self.session: Optional[requests.Session] = None
        self.is_logged_in = False
    
    def get_session(self) -> requests.Session:
        if self.session is None:
            self.session = requests.Session()
            retry = Retry(total=MAX_RETRIES, backoff_factor=1)
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
            self.session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
        return self.session
    
    def login(self, username: str, password: str) -> bool:
        """登录"""
        session = self.get_session()
        
        try:
            resp = session.get(GY_CONFIG["login_url"], timeout=TIMEOUT)
            
            # 提取 token
            token_match = re.search(r'name="token"[^>]*value="([^"]+)"', resp.text)
            
            login_data = {
                "username": username,
                "password": password,
                "token": token_match.group(1) if token_match else "",
                "loginsubmit": "true"
            }
            
            resp = session.post(GY_CONFIG["login_url"], data=login_data, timeout=TIMEOUT)
            
            if "logout" in resp.text.lower():
                self.is_logged_in = True
                logger.info("登录成功")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return False
    
    def search(self, keyword: str, max_pages: int = 3) -> List[GyResult]:
        """搜索"""
        session = self.get_session()
        results = []
        
        for page in range(1, max_pages + 1):
            try:
                params = {GY_CONFIG["search_param"]: keyword}
                if page > 1:
                    params["page"] = page
                
                resp = session.get(GY_CONFIG["search_url"], params=params, timeout=TIMEOUT)
                page_results = self._parse_results(resp.text)
                results.extend(page_results)
                
                if not page_results:
                    break
                    
                logger.info(f"第 {page} 页: {len(page_results)} 个")
                
            except Exception as e:
                logger.error(f"搜索失败: {e}")
                break
        
        return results
    
    def _parse_results(self, html: str) -> List[GyResult]:
        """解析结果"""
        results = []
        soup = BeautifulSoup(html, "html.parser")
        
        items = soup.select("div.movie-item, li.movie-item, div.search-item")
        
        for item in items:
            try:
                title_elem = item.select_one("h3 a, a.title, h2 a")
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                link = title_elem.get("href", "")
                
                if link and not link.startswith("http"):
                    link = urljoin(GY_CONFIG["base_url"], link)
                
                details = self._parse_title(title)
                
                pop_elem = item.select_one(".views, .popularity")
                popularity = 0
                if pop_elem:
                    match = re.search(r'(\d+)', pop_elem.get_text())
                    if match:
                        popularity = int(match.group(1))
                
                results.append(GyResult(
                    title=title,
                    link=link,
                    resolution=details["resolution"],
                    audio_tracks=details["audio_tracks"],
                    subtitles=details["subtitles"],
                    size=details["size"],
                    popularity=popularity
                ))
                
            except Exception as e:
                logger.warning(f"解析失败: {e}")
                continue
        
        return results
    
    def _parse_title(self, title: str) -> Dict:
        """解析标题"""
        details = {
            "resolution": "未知",
            "audio_tracks": [],
            "subtitles": [],
            "size": "未知"
        }
        
        title_lower = title.lower()
        
        if "2160p" in title_lower or "4k" in title_lower:
            details["resolution"] = "2160p"
        elif "1080p" in title_lower:
            details["resolution"] = "1080p"
        elif "720p" in title_lower:
            details["resolution"] = "720p"
        
        for bracket in re.findall(r'\[([^\]]+)\]', title):
            parts = re.split(r'[+/]', bracket)
            for part in parts:
                part = part.strip()
                if "音轨" in part or "配音" in part:
                    details["audio_tracks"].append(part)
                elif "字幕" in part:
                    details["subtitles"].append(part)
        
        if "国语中字" in title:
            details["audio_tracks"].append("国语配音")
            details["subtitles"].append("中文字幕")
        
        size_match = re.search(r'(\d+\.?\d*)\s*(GB|MB|TB)', title, re.I)
        if size_match:
            details["size"] = f"{size_match.group(1)} {size_match.group(2).upper()}"
        
        return details
    
    def filter_by_resolution(self, results: List[GyResult],
                           preferred: str = "1080p",
                           fallback: str = "720p") -> Dict[str, List[GyResult]]:
        """分类"""
        categorized = {"首选": [], "备选": [], "其他": []}
        
        for r in results:
            if r.resolution == preferred:
                categorized["首选"].append(r)
            elif r.resolution == fallback:
                categorized["备选"].append(r)
            else:
                categorized["其他"].append(r)
        
        return categorized
    
    def save_results(self, keyword: str, results: List[GyResult], 
                    output_dir: str = "/tmp/index"):
        """保存"""
        os.makedirs(output_dir, exist_ok=True)
        
        filepath = os.path.join(output_dir, f"{keyword}-GY.json")
        
        data = [
            {
                "title": r.title,
                "link": r.link,
                "resolution": r.resolution,
                "audio_tracks": r.audio_tracks,
                "subtitles": r.subtitles,
                "size": r.size,
                "popularity": r.popularity
            }
            for r in results
        ]
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已保存: {filepath}")


class GyIndexer:
    """观影索引器"""
    
    def __init__(self, db_path: str = "/config/data.db"):
        self.db_path = db_path
        self.session_mgr = GySessionManager()
        self.config: Dict = {}
    
    def load_config(self) -> Dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT OPTION, VALUE FROM CONFIG")
                self.config = {opt: val for opt, val in cursor.fetchall()}
            return self.config
        except sqlite3.Error as e:
            logger.error(f"配置加载失败: {e}")
            return {}
    
    def run(self, keywords: List[str], max_pages: int = 3):
        self.load_config()
        
        username = self.config.get("bt_login_username", "")
        password = self.config.get("bt_login_password", "")
        
        if username and password:
            self.session_mgr.login(username, password)
        
        preferred = self.config.get("preferred_resolution", "1080p")
        fallback = self.config.get("fallback_resolution", "720p")
        
        for keyword in keywords:
            results = self.session_mgr.search(keyword, max_pages)
            self.session_mgr.save_results(keyword, results)
            logger.info(f"{keyword}: {len(results)} 个结果")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="观影解析器")
    parser.add_argument("--keyword", "-k", required=True)
    parser.add_argument("--pages", "-p", type=int, default=3)
    args = parser.parse_args()
    
    mgr = GySessionManager()
    results = mgr.search(args.keyword, args.pages)
    print(f"找到 {len(results)} 个结果")


if __name__ == "__main__":
    main()
