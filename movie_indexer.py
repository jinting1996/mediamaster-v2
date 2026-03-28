"""
MediaMaster V2 - 站点解析模块 (优化版)
使用 requests + BeautifulSoup 替代 Selenium
"""
import os
import re
import json
import time
import logging
import sqlite3
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlencode, urlparse, parse_qs
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============== 配置 ==============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/log/indexer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============== 常量 ==============
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 30
MAX_RETRIES = 3

# 站点配置
SITE_CONFIGS = {
    "bthd": {
        "name": "高清影视之家",
        "base_url": "https://www.btbdhd.com",
        "search_url": "https://www.btbdhd.com/search.php",
        "login_url": "https://www.btbdhd.com/member.php?mod=logging",
        "search_param": "srchtxt",
        "result_selectors": {
            "container": "#threadlist",
            "item": "li.pbw",
            "title": "h3.xs3 a",
            "popularity": "p.xg1"
        }
    },
    "gy": {
        "name": "观影",
        "base_url": "https://www.gy6y.com",
        "search_url": "https://www.gy6y.com/search",
        "login_url": "https://www.gy6y.com/user/login",
        "search_param": "q",
        "result_selectors": {
            "item": ".movie-item",
            "title": "a.title",
            "popularity": ".views"
        }
    },
    "hdtv": {
        "name": "高清剧集网",
        "base_url": "https://www.hdtv.la",
        "search_url": "https://www.hdtv.la/search",
        "login_url": "https://www.hdtv.la/login",
        "search_param": "keyword",
        "result_selectors": {
            "item": "div.resource-item",
            "title": "h3 a",
            "popularity": ".view-count"
        }
    }
}

# 分辨率映射
RESOLUTION_MAP = {
    "4k": "2160p",
    "2160p": "2160p",
    "1080p": "1080p",
    "1080i": "1080i",
    "720p": "720p",
    "720i": "720i",
    "480p": "480p"
}


@dataclass
class MediaResult:
    """媒体搜索结果"""
    title: str
    link: str
    resolution: str = "未知分辨率"
    audio_tracks: List[str] = None
    subtitles: List[str] = None
    size: str = "未知大小"
    popularity: int = 0
    source: str = ""
    
    def __post_init__(self):
        if self.audio_tracks is None:
            self.audio_tracks = []
        if self.subtitles is None:
            self.subtitles = []


class SessionManager:
    """Session 管理器 - 自动重试、连接复用"""
    
    def __init__(self):
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """创建带重试的 Session"""
        session = requests.Session()
        
        # 重试策略
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 默认头
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br"
        })
        
        return session
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET 请求"""
        kwargs.setdefault("timeout", TIMEOUT)
        kwargs.setdefault("allow_redirects", True)
        
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                logger.warning(f"请求失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {url} - {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST 请求"""
        kwargs.setdefault("timeout", TIMEOUT)
        
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.post(url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                logger.warning(f"POST失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {url} - {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise


class MediaIndexer:
    """媒体索引器"""
    
    def __init__(self, db_path: str = "/config/data.db"):
        self.db_path = db_path
        self.session_mgr = SessionManager()
        self.config: Dict = {}
    
    def load_config(self) -> Dict:
        """加载配置"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT OPTION, VALUE FROM CONFIG")
                self.config = {opt: val for opt, val in cursor.fetchall()}
            logger.debug("配置加载成功")
            return self.config
        except sqlite3.Error as e:
            logger.error(f"配置加载失败: {e}")
            return {}
    
    def search(self, site: str, keyword: str, year: str = "", max_pages: int = 3) -> List[MediaResult]:
        """搜索媒体资源"""
        site_cfg = SITE_CONFIGS.get(site)
        if not site_cfg:
            logger.error(f"未知站点: {site}")
            return []
        
        all_results = []
        query = f"{keyword} {year}".strip()
        
        for page in range(1, max_pages + 1):
            logger.info(f"[{site_cfg['name']}] 搜索第 {page} 页: {keyword}")
            
            try:
                results = self._search_page(site_cfg, query, page)
                all_results.extend(results)
                
                if not results:
                    logger.info(f"第 {page} 页无结果")
                    break
                    
            except Exception as e:
                logger.error(f"搜索第 {page} 页失败: {e}")
                break
        
        logger.info(f"[{site_cfg['name']}] 共找到 {len(all_results)} 个结果")
        return all_results
    
    def _search_page(self, site_cfg: Dict, query: str, page: int) -> List[MediaResult]:
        """搜索单页"""
        # 构建搜索参数
        params = {site_cfg["search_param"]: query}
        if page > 1:
            params["page"] = page
        
        resp = self.session_mgr.get(site_cfg["search_url"], params=params)
        return self._parse_results(resp.text, site_cfg["name"])
    
    def _parse_results(self, html: str, source: str) -> List[MediaResult]:
        """解析搜索结果"""
        results = []
        soup = BeautifulSoup(html, "html.parser")
        selectors = SITE_CONFIGS.get(source, {}).get("result_selectors", {})
        
        # 查找结果容器
        container = soup.select_one(selectors.get("container", ""))
        items = (container or soup).select(selectors.get("item", ""))
        
        for item in items:
            try:
                # 提取标题和链接
                title_elem = item.select_one(selectors.get("title", "a"))
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                link = title_elem.get("href", "")
                
                # 补全链接
                if link and not link.startswith("http"):
                    base = SITE_CONFIGS.get(source, {}).get("base_url", "")
                    link = urljoin(base, link)
                
                # 提取热度
                pop_elem = item.select_one(selectors.get("popularity", ""))
                popularity = self._extract_number(pop_elem.get_text() if pop_elem else "")
                
                # 解析详情
                details = self._parse_title(title)
                
                results.append(MediaResult(
                    title=title,
                    link=link,
                    resolution=details["resolution"],
                    audio_tracks=details["audio_tracks"],
                    subtitles=details["subtitles"],
                    size=details["size"],
                    popularity=popularity,
                    source=source
                ))
                
            except Exception as e:
                logger.warning(f"解析结果项失败: {e}")
                continue
        
        return results
    
    def _extract_number(self, text: str) -> int:
        """提取数字"""
        match = re.search(r'(\d+)', text)
        return int(match.group(1)) if match else 0
    
    def _parse_title(self, title: str) -> Dict:
        """解析标题提取信息"""
        details = {
            "resolution": "未知分辨率",
            "audio_tracks": [],
            "subtitles": [],
            "size": "未知大小"
        }
        
        # 分辨率
        title_lower = title.lower()
        for key, value in RESOLUTION_MAP.items():
            if key in title_lower:
                details["resolution"] = value
                break
        if "4k" in title_lower:
            details["resolution"] = "2160p"
        
        # 解析方括号内容
        for bracket in re.findall(r'\[([^\]]+)\]', title):
            parts = re.split(r'[+/]', bracket)
            for part in parts:
                part = part.strip()
                if "音轨" in part or "配音" in part:
                    details["audio_tracks"].append(part)
                elif "字幕" in part:
                    details["subtitles"].append(part)
        
        # 国语中字
        if "国语中字" in title:
            details["audio_tracks"].append("国语配音")
            details["subtitles"].append("中文字幕")
        
        # 文件大小
        size_match = re.search(r'(\d+\.?\d*)\s*(GB|MB|TB)', title, re.I)
        if size_match:
            details["size"] = f"{size_match.group(1)} {size_match.group(2).upper()}"
        
        return details
    
    def filter_results(self, results: List[MediaResult],
                       preferred: str = "1080p",
                       fallback: str = "720p",
                       exclude: List[str] = None) -> Dict[str, List[MediaResult]]:
        """过滤和分类结果"""
        if exclude is None:
            exclude = []
        
        categorized = {"首选": [], "备选": [], "其他": []}
        
        for r in results:
            # 排除
            if any(kw in r.title for kw in exclude):
                continue
            
            # 分类
            if r.resolution == preferred:
                categorized["首选"].append(r)
            elif r.resolution == fallback:
                categorized["备选"].append(r)
            else:
                categorized["其他"].append(r)
        
        return categorized
    
    def save_to_json(self, title: str, year: str, results: Dict[str, List[MediaResult]], 
                     output_dir: str = "/tmp/index") -> str:
        """保存结果到 JSON"""
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{title}-{year}.json"
        filepath = os.path.join(output_dir, filename)
        
        data = {k: [asdict(r) for r in v] for k, v in results.items()}
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已保存: {filepath}")
        return filepath


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="媒体资源搜索")
    parser.add_argument("--site", "-s", default="bthd", help="站点 (bthd/gy/hdtv)")
    parser.add_argument("--keyword", "-k", required=True, help="搜索关键词")
    parser.add_argument("--year", "-y", default="", help="年份")
    parser.add_argument("--pages", "-p", type=int, default=3, help="最大页数")
    args = parser.parse_args()
    
    indexer = MediaIndexer()
    indexer.load_config()
    
    # 搜索
    results = indexer.search(args.site, args.keyword, args.year, args.pages)
    
    # 配置过滤参数
    preferred = indexer.config.get("preferred_resolution", "1080p")
    fallback = indexer.config.get("fallback_resolution", "720p")
    exclude = indexer.config.get("resources_exclude_keywords", "").split(",")
    
    # 过滤
    filtered = indexer.filter_results(results, preferred, fallback, exclude)
    
    # 保存
    indexer.save_to_json(args.keyword, args.year, filtered)
    
    print(f"✅ 找到 {len(results)} 个结果")
    for cat, items in filtered.items():
        print(f"  {cat}: {len(items)} 个")


if __name__ == "__main__":
    main()
