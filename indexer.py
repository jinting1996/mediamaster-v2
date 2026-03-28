"""
MediaMaster V2 - 统一索引调度器 (优化版)
并行执行多站点索引，使用优化后的模块
"""
import subprocess
import logging
import os
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/log/indexer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def clear_index_directory():
    """清理索引目录"""
    index_dir = "/tmp/index/"
    if os.path.exists(index_dir):
        logger.info(f"清理目录: {index_dir}")
        for file in glob.glob(os.path.join(index_dir, "*.json")):
            try:
                os.remove(file)
                logger.info(f"已删除: {file}")
            except Exception as e:
                logger.error(f"删除失败: {file} - {e}")
    else:
        os.makedirs(index_dir, exist_ok=True)
        logger.info(f"创建目录: {index_dir}")


def run_indexer(script_name: str, friendly_name: str, instance_id: str) -> bool:
    """运行索引器"""
    try:
        result = subprocess.run(
            ["python", script_name, "--instance-id", instance_id],
            capture_output=True,
            text=True,
            timeout=600  # 10分钟超时
        )
        
        if result.returncode == 0:
            logger.info(f"✅ {friendly_name} 索引完成")
            return True
        else:
            logger.error(f"❌ {friendly_name} 失败: {result.stderr[:200]}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"⏱️ {friendly_name} 超时")
        return False
    except Exception as e:
        logger.error(f"💥 {friendly_name} 异常: {e}")
        return False


def main():
    """主函数 - 并行执行多站点索引"""
    clear_index_directory()
    
    # 索引任务配置
    scripts = {
        "movie_indexer.py": "高清影视之家",      # 优化版
        "tvshow_hdtv.py": "高清剧集网",
        "movie_tvshow_btys.py": "BT影视",
        "movie_tvshow_bt0.py": "不太灵影视",
        "movie_tvshow_gy.py": "观影"
    }
    
    max_workers = min(len(scripts), 5)
    results = {}
    
    logger.info(f"🚀 开始并行索引 {len(scripts)} 个站点...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        
        for i, (script, name) in enumerate(scripts.items()):
            instance_id = str(i)
            future = executor.submit(run_indexer, script, name, instance_id)
            futures[future] = name
            time.sleep(1)  # 避免并发冲突
        
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                logger.error(f"❌ {name} 执行异常: {e}")
                results[name] = False
    
    # 统计结果
    success = sum(1 for v in results.values() if v)
    total = len(results)
    
    logger.info(f"📊 索引完成: {success}/{total} 成功")
    
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        logger.info(f"  {status} {name}")


if __name__ == "__main__":
    main()
