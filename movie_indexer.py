"""
MediaMaster V2 优化版 - 站点解析模块
用 requests + BeautifulSoup 替代 Selenium
"""
import os
import re
import json
import time
import logging
import sqlite3
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlencode
from dataclasses import dataclass
from bs4 import BeautifulSoup
import requests

# ============== 配置 ==============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/log/movie_indexer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============== 常量 ==============
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 30


@dataclass
class MovieResult:
    """电影搜索结果"""
    title: str
    link: str
    resolution: str
    audio_tracks: List[str]
    subtitles: List[str]
    size: str
    popularity: int


class SiteSearcher:
    """站点搜索器 - 使用 requests"""
    
    # 站点配置
    SITES = {
        "bthd": {
            "name": "高清影视之家",
            "base_url": "https://www.btbdhd.com",
            "search_url": "https://www.btbdhd.com/search.php",
            "login_url": "https://www.btbdhd.com/member.php?mod=logging",
            "search_box_name": "srchtxt",
            "result_container": "threadlist",
            "result_item": "li.pbw",
            "title_selector": "h3.xs3 a",
            "popularity_selector": "p.xg1"
        },
        "gy": {
            "name": "观影",
            "base_url": "https://www.gy6y.com",
            "search_url": "https://www.gy6y.com/search",
            "login_url": "https://www.gy6y.com/user/login",
        },
        "hdtv": {
            "name": "高清剧集网",
            "base_url": "https://www.hdtv.la",
            "search_url": "https://www.hdtv.la/search",
        }
    }
    
    def __init__(self, db_path: str = "/config/data.db"):
        self.db_path = db_path
        self.session: Optional[requests.Session] = None
        self.config: Dict = {}
        
    def create_session(self) -> requests.Session:
        """创建复用 Session"""
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
        return self.session
    
    def load_config(self) -> Dict:
        """加载配置"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT OPTION, VALUE FROM CONFIG")
                self.config = {opt: val for opt, val in cursor.fetchall()}
            return self.config
        except sqlite3.Error as e:
            logger.error(f"配置加载失败: {e}")
            return {}
    
    def search(self, site: str, keyword: str, year: str = "", max_pages: int = 3) -> List[MovieResult]:
        """搜索电影"""
        site_config = self.SITES.get(site)
        if not site_config:
            logger.error(f"未知站点: {site}")
            return []
        
        results = []
        session = self.create_session()
        
        for page in range(1, max_pages + 1):
            try:
                # 构建搜索 URL
                params = {site_config.get("search_box_name", "srchtxt"): f"{keyword} {year}".strip()}
                if page > 1:
                    params["page"] = page
                
                logger.info(f"搜索第 {page} 页: {keyword}")
                
                resp = session.get(site_config["search_url"], params=params, timeout=TIMEOUT)
                resp.raise_for_status()
                
                # 解析结果
                page_results = self._parse_results(resp.text, site_config)
                results.extend(page_results)
                
                if not page_results:
                    logger.info(f"第 {page} 页无结果，停止搜索")
                    break
                    
            except requests.RequestException as e:
                logger.error(f"搜索失败: {e}")
                break
        
        logger.info(f"共找到 {len(results)} 个结果")
        return results
    
    def _parse_results(self, html: str, site_config: Dict) -> List[MovieResult]:
        """解析搜索结果"""
        results = []
        soup = BeautifulSoup(html, "html.parser")
        
        # 查找结果容器
        container = soup.select_one(f"#{site_config.get('result_container', 'threadlist')}")
        if not container:
            container = soup
        
        # 查找结果项
        items = container.select(site_config.get("result_item", "li.pbw"))
        
        for item in items:
            try:
                # 提取标题和链接
                title_elem = item.select_one(site_config.get("title_selector", "h3.xs3 a"))
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                link = title_elem.get("href", "")
                
                # 提取热度
                pop_elem = item.select_one(site_config.get("popularity_selector", "p.xg1"))
                popularity = self._extract_popularity(pop_elem.get_text() if pop_elem else "")
                
                # 解析详情
                details = self._extract_details(title)
                
                results.append(MovieResult(
                    title=title,
                    link=link,
                    resolution=details["resolution"],
                    audio_tracks=details["audio_tracks"],
                    subtitles=details["subtitles"],
                    size=details["size"],
                    popularity=popularity
                ))
                
            except Exception as e:
                logger.warning(f"解析结果项失败: {e}")
                continue
        
        return results
    
    def _extract_popularity(self, text: str) -> int:
        """提取热度数据"""
        match = re.search(r'(\d+)\s*次查看', text)
        return int(match.group(1)) if match else 0
    
    def _extract_details(self, title: str) -> Dict:
        """从标题提取详情"""
        details = {
            "resolution": "未知分辨率",
            "audio_tracks": [],
            "subtitles": [],
            "size": "未知大小"
        }
        
        # 分辨率
        res_match = re.search(r'(\d{3,4}p)', title, re.I)
        if res_match:
            details["resolution"] = res_match.group(1).lower()
        elif "4K" in title.upper():
            details["resolution"] = "2160p"
        
        # 方括号内容
        for bracket in re.findall(r'\[([^\]]+)\]', title):
            parts = [p.strip() for p in re.split(r'[+/]', bracket)]
            for part in parts:
                if re.search(r'(音轨|配音)', part):
                    details["audio_tracks"].append(part)
                if re.search(r'(字幕)', part):
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
    
    def filter_results(self, results: List[MovieResult], 
                       preferred_res: str = "1080p", 
                       fallback_res: str = "720p",
                       exclude_keywords: List[str] = None) -> Dict[str, List[MovieResult]]:
        """过滤和分类结果"""
        if exclude_keywords is None:
            exclude_keywords = []
        
        categorized = {
            "首选分辨率": [],
            "备选分辨率": [],
            "其他分辨率": []
        }
        
        for result in results:
            # 排除关键词
            if any(kw in result.title for kw in exclude_keywords):
                continue
            
            # 分类
            if result.resolution == preferred_res:
                categorized["首选分辨率"].append(result)
            elif result.resolution == fallback_res:
                categorized["备选分辨率"].append(result)
            else:
                categorized["其他分辨率"].append(result)
        
        return categorized
    
    def save_results(self, title: str, year: str, results: Dict[str, List[MovieResult]], output_dir: str = "/tmp/index"):
        """保存结果到 JSON"""
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{title}-{year}-index.json"
        filepath = os.path.join(output_dir, filename)
        
        # 转换为可序列化格式
        data = {}
        for category, items in results.items():
            data[category] = [
                {
                    "title": r.title,
                    "link": r.link,
                    "resolution": r.resolution,
                    "audio_tracks": r.audio_tracks,
                    "subtitles": r.subtitles,
                    "size": r.size,
                    "popularity": r.popularity
                }
                for r in items
            ]
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"结果已保存: {filepath}")
        return filepath


def main():
    """测试入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="站点搜索器")
    parser.add_argument("--site", default="bthd", help="站点名称")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--year", default="", help="年份")
    parser.add_argument("--max-pages", type=int, default=3, help="最大页数")
    args = parser.parse_args()
    
    # 搜索
    searcher = SiteSearcher()
    results = searcher.search(args.site, args.keyword, args.year, args.max_pages)
    
    # 过滤
    searcher.load_config()
    preferred = searcher.config.get("preferred_resolution", "1080p")
    fallback = searcher.config.get("fallback_resolution", "720p")
    exclude = searcher.config.get("resources_exclude_keywords", "").split(",")
    
    filtered = searcher.filter_results(results, preferred, fallback, exclude)
    
    # 保存
    searcher.save_results(args.keyword, args.year, filtered)
    
    print(f"找到 {len(results)} 个结果，过滤后 {sum(len(v) for v in filtered.values())} 个")


if __name__ == "__main__":
    main()
