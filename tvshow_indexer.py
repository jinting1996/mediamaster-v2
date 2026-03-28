"""
MediaMaster V2 - 电视剧站点解析模块 (优化版)
使用 requests + BeautifulSoup 替代 Selenium
"""
import os
import re
import json
import time
import logging
import sqlite3
from typing import List, Dict, Optional, Tuple
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
        logging.FileHandler("/tmp/log/tvshow_indexer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 30

# 站点配置
TVSHOW_SITES = {
    "hdtv": {
        "name": "高清剧集网",
        "base_url": "https://www.hdtv.la",
        "search_url": "https://www.hdtv.la/search",
        "search_param": "keyword"
    },
    "btys": {
        "name": "BT影视",
        "base_url": "https://www.btys.com",
        "search_url": "https://www.btys.com/search",
        "search_param": "q"
    },
    "bt0": {
        "name": "不太灵影视",
        "base_url": "https://www.bt0.com",
        "search_url": "https://www.bt0.com/search",
        "search_param": "keyword"
    },
    "gy": {
        "name": "观影",
        "base_url": "https://www.gy6y.com",
        "search_url": "https://www.gy6y.com/search",
        "search_param": "q"
    }
}


@dataclass
class TvshowResult:
    """电视剧搜索结果"""
    title: str
    link: str
    season: str = ""
    episode: str = ""
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
    """Session 管理器"""
    def __init__(self):
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({"User-Agent": USER_AGENT})
        return session

    def get(self, url, **kwargs):
        kwargs.setdefault("timeout", TIMEOUT)
        return self.session.get(url, **kwargs)


class TvshowIndexer:
    """电视剧索引器"""

    def __init__(self, db_path: str = "/config/data.db"):
        self.db_path = db_path
        self.session_mgr = SessionManager()
        self.config: Dict = {}

    def load_config(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT OPTION, VALUE FROM CONFIG")
                self.config = {opt: val for opt, val in cursor.fetchall()}
            return self.config
        except sqlite3.Error as e:
            logger.error(f"配置加载失败: {e}")
            return {}

    def search(self, site: str, keyword: str, year: str = "", max_pages: int = 3) -> List[TvshowResult]:
        """搜索电视剧"""
        site_cfg = TVSHOW_SITES.get(site)
        if not site_cfg:
            logger.error(f"未知站点: {site}")
            return []

        all_results = []
        query = f"{keyword} {year}".strip()

        for page in range(1, max_pages + 1):
            logger.info(f"[{site_cfg['name']}] 第 {page} 页: {keyword}")
            try:
                results = self._search_page(site_cfg, query, page)
                all_results.extend(results)
                if not results:
                    break
            except Exception as e:
                logger.error(f"搜索失败: {e}")
                break

        logger.info(f"[{site_cfg['name']}] 共 {len(all_results)} 个结果")
        return all_results

    def _search_page(self, site_cfg: Dict, query: str, page: int) -> List[TvshowResult]:
        params = {site_cfg["search_param"]: query}
        if page > 1:
            params["page"] = page
        
        resp = self.session_mgr.get(site_cfg["search_url"], params=params)
        return self._parse_results(resp.text, site_cfg["name"])

    def _parse_results(self, html: str, source: str) -> List[TvshowResult]:
        results = []
        soup = BeautifulSoup(html, "html.parser")

        # 通用选择器（需要根据实际站点调整）
        items = soup.select("div.resource-item, li.movie-item, div.search-result-item")

        for item in items:
            try:
                title_elem = item.select_one("h3 a, a.title, h2 a")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                link = title_elem.get("href", "")

                if link and not link.startswith("http"):
                    base = TVSHOW_SITES.get(source, {}).get("base_url", "")
                    link = urljoin(base, link)

                # 解析季和集
                season, episode, clean_title = self._parse_season_episode(title)

                # 解析详情
                details = self._parse_title_details(title)

                results.append(TvshowResult(
                    title=clean_title,
                    link=link,
                    season=season,
                    episode=episode,
                    resolution=details["resolution"],
                    audio_tracks=details["audio_tracks"],
                    subtitles=details["subtitles"],
                    size=details["size"],
                    source=source
                ))
            except Exception as e:
                logger.warning(f"解析失败: {e}")
                continue

        return results

    def _parse_season_episode(self, title: str) -> Tuple[str, str, str]:
        """解析季和集信息"""
        # 季
        season_match = re.search(r'第?(\d+)季', title)
        season = season_match.group(1) if season_match else "1"

        # 集
        episode_match = re.search(r'第?(\d+)集', title)
        episode = episode_match.group(1) if episode_match else ""

        # 清理标题
        clean_title = re.sub(r'第?\d+季.*?第?\d+集', '', title)
        clean_title = re.sub(r'第?\d+集', '', clean_title)
        clean_title = clean_title.strip()

        return season, episode, clean_title

    def _parse_title_details(self, title: str) -> Dict:
        """解析标题详情"""
        details = {
            "resolution": "未知分辨率",
            "audio_tracks": [],
            "subtitles": [],
            "size": "未知大小"
        }

        # 分辨率
        title_lower = title.lower()
        if "2160p" in title_lower or "4k" in title_lower:
            details["resolution"] = "2160p"
        elif "1080p" in title_lower:
            details["resolution"] = "1080p"
        elif "720p" in title_lower:
            details["resolution"] = "720p"

        # 方括号内容
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

    def save_to_json(self, title: str, year: str, results: List[TvshowResult], output_dir: str = "/tmp/index"):
        """保存结果"""
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{title}-{year}-TV.json"
        filepath = os.path.join(output_dir, filename)
        
        data = [
            {
                "title": r.title,
                "link": r.link,
                "season": r.season,
                "episode": r.episode,
                "resolution": r.resolution,
                "audio_tracks": r.audio_tracks,
                "subtitles": r.subtitles,
                "size": r.size,
                "source": r.source
            }
            for r in results
        ]
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已保存: {filepath}")
        return filepath


def main():
    import argparse
    parser = argparse.ArgumentParser(description="电视剧索引器")
    parser.add_argument("--site", "-s", default="hdtv", help="站点")
    parser.add_argument("--keyword", "-k", required=True, help="关键词")
    parser.add_argument("--year", "-y", default="", help="年份")
    parser.add_argument("--pages", "-p", type=int, default=3, help="页数")
    args = parser.parse_args()

    indexer = TvshowIndexer()
    indexer.load_config()
    results = indexer.search(args.site, args.keyword, args.year, args.pages)
    indexer.save_to_json(args.keyword, args.year, results)
    print(f"✅ 找到 {len(results)} 个结果")


if __name__ == "__main__":
    main()
