import os
import json
import subprocess
import time
import logging
import sys
import signal
import sqlite3
import psutil
import threading
import concurrent.futures

# 配置日志
from app.utils.logging import setup_logger, log_error, log_info, log_warning, log_debug
logger = setup_logger(name="MainLogger", log_file="/tmp/log/main.log")

# 创建线程池
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

def get_run_interval_from_db():
    try:
        conn = sqlite3.connect('/config/data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT VALUE FROM CONFIG WHERE OPTION = 'run_interval_hours';")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result:
            return int(result[0])
        else:
            log_warning(logger, "未找到 run_interval_hours 配置项，使用默认值 6 小时。")
            return 6
    except Exception as e:
        log_error(logger, "无法从数据库读取 run_interval_hours，使用默认值 6 小时。", e)
        return 6

def run_script(script_name):
    """异步执行脚本"""
    def execute_script():
        try:
            result = subprocess.run(['python', script_name], check=True, capture_output=True, text=True)
            log_debug(logger, f"{script_name} 已执行完毕。")
            return True
        except subprocess.CalledProcessError as e:
            log_error(logger, f"{script_name} 执行失败", e)
            log_error(logger, f"错误输出: {e.stderr}")
            return False
    
    # 提交到线程池执行
    future = executor.submit(execute_script)
    return future

def start_app():
    try:
        with open(os.devnull, 'w') as devnull:
            process = subprocess.Popen(['python', '-m', 'app'], stdout=devnull, stderr=devnull)
            log_info(logger, "WEB管理已启动。")
            return process.pid
    except Exception as e:
        log_error(logger, "无法启动WEB管理程序", e)
        sys.exit(0)

def start_sync():
    def delayed_start():
        try:
            # 延时2分钟启动
            time.sleep(120)
            process = subprocess.Popen(['python', 'sync.py'])
            log_info(logger, "目录监控服务已启动。")
            # 保存进程ID供后续使用
            global sync_pid
            sync_pid = process.pid
        except Exception as e:
            log_error(logger, "无法启动目录监控服务", e)
    
    # 使用线程启动延时任务，不阻塞主线程
    thread = threading.Thread(target=delayed_start, daemon=True)
    thread.start()
    log_info(logger, "目录监控服务将在2分钟后启动...")
    # 返回None，因为实际的PID会在延时后设置
    return None

def start_xunlei_torrent():
    try:
        process = subprocess.Popen(['python', 'xunlei_torrent.py'])
        log_info(logger, "迅雷-种子监听服务已启动。")
        return process.pid
    except Exception as e:
        log_error(logger, "无法启动迅雷-种子监听服务", e)
        sys.exit(0)

def start_check_db_dir():
    try:
        process = subprocess.Popen(['python', 'check_db_dir.py'])
        log_info(logger, "启动数据库和目录检查服务")
        return process.pid
    except Exception as e:
        log_error(logger, "无法启动数据库和目录检查服务", e)
        sys.exit(0)

def report_versions():
    try:
        process = subprocess.Popen(['python', 'report_versions.py'])
        log_info(logger, "启动版本检测及统计服务")
        return process.pid
    except Exception as e:
        log_error(logger, "无法启动版本检测及统计服务", e)
        sys.exit(0)

def monitor_chrome_process():
    chrome_started_time = None
    chromedriver_started_time = None

    for proc in psutil.process_iter(['pid', 'name', 'create_time']):
        try:
            process_name = proc.info['name'].lower()
            create_time = proc.info['create_time']

            if 'chrome' in process_name:
                if chrome_started_time is None or create_time < chrome_started_time:
                    chrome_started_time = create_time
            if 'chromedriver' in process_name:
                if chromedriver_started_time is None or create_time < chromedriver_started_time:
                    chromedriver_started_time = create_time

        except psutil.NoSuchProcess:
            continue

    def terminate_process(process_name_filter, started_time, threshold_seconds, log_prefix):
        if started_time:
            run_time = time.time() - started_time
            if run_time > threshold_seconds:
                log_warning(logger, f"{log_prefix} 进程已运行超过 {threshold_seconds // 60} 分钟，判定为异常，正在终止。")
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if process_name_filter in proc.info['name'].lower():
                            p = psutil.Process(proc.info['pid'])
                            p.terminate()
                            log_info(logger, f"已终止 {log_prefix} 进程 PID: {proc.info['pid']}")
                    except psutil.NoSuchProcess:
                        pass

    # 监控 Chrome 进程
    terminate_process('chrome', chrome_started_time, 20 * 60, "Chrome")

    # 监控 Chromedriver 进程
    terminate_process('chromedriver', chromedriver_started_time, 20 * 60, "Chromedriver")

    def kill_zombie_processes():
        """
        检测并记录僵尸进程
        僵尸进程只能由其父进程清理，这里仅做记录
        """
        zombie_count = 0
        for proc in psutil.process_iter(['pid', 'name', 'status']):
            try:
                if proc.info['status'] == psutil.STATUS_ZOMBIE:
                    zombie_count += 1
                    log_debug(logger, f"检测到僵尸进程 PID: {proc.info['pid']}, NAME: {proc.info['name']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
                # 忽略进程已不存在、无访问权限或键不存在的情况
                pass
        
        if zombie_count > 0:
            log_info(logger, f"检测到 {zombie_count} 个僵尸进程，等待系统自动清理")

    # 调用清理僵尸进程函数
    kill_zombie_processes()

def chrome_monitor_thread():
    while running:
        monitor_chrome_process()
        time.sleep(300)  # 每5分钟检查一次

def start_chrome_monitor():
    thread = threading.Thread(target=chrome_monitor_thread, daemon=True)
    thread.start()
    log_info(logger, "Chrome 进程监控已启动")

def check_site_status_and_save():
    """检查站点状态并保存到文件"""
    try:
        # 导入站点测试模块
        import sys
        sys.path.append('/app')
        
        import site_test
            
        # 运行站点测试
        tester = site_test.SiteTester()
        results = tester.run_tests()
        
        # 保存结果到文件
        status_data = {
            'status': results,
            'last_checked': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open('/tmp/site_status.json', 'w', encoding='utf-8') as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
            
        log_info(logger, "站点状态检测完成并已保存到 /tmp/site_status.json")
        
    except Exception as e:
        log_error(logger, "站点状态检测失败", e)

# 全局变量
running = True
app_pid = None
sync_pid = None
xunlei_started = False

# 信号处理函数
def shutdown_handler(signum, frame):
    global running, app_pid, sync_pid
    log_info(logger, f"收到信号 {signum}，正在关闭程序...")

    running = False

    if app_pid:
        log_info(logger, f"终止 app.py 进程 (PID: {app_pid})")
        try:
            os.kill(app_pid, signal.SIGTERM)
        except ProcessLookupError:
            log_warning(logger, f"进程 {app_pid} 不存在，跳过终止操作。")

    if sync_pid:
        log_info(logger, f"终止 sync.py 进程 (PID: {sync_pid})")
        try:
            os.kill(sync_pid, signal.SIGTERM)
        except ProcessLookupError:
            log_warning(logger, f"进程 {sync_pid} 不存在，跳过终止操作。")

    # 关闭线程池
    log_info(logger, "关闭线程池...")
    executor.shutdown(wait=True, cancel_futures=True)

    time.sleep(5)
    log_info(logger, "程序已关闭。")
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

def main():
    global app_pid, sync_pid, running, xunlei_started

    run_interval_hours = get_run_interval_from_db()
    run_interval_seconds = run_interval_hours * 3600

    app_pid = start_app()
    sync_pid = start_sync()
    start_chrome_monitor()  # 启动 Chrome 监控线程

    while running:
        # 在主循环中定期执行站点状态检测
        check_site_status_and_save()
        log_info(logger, "-" * 80)
        log_info(logger, "站点状态检测：已执行完毕，等待5秒...")
        log_info(logger, "-" * 80)
        time.sleep(5)

        # 提交所有脚本到线程池
        futures = {
            'scan_media': run_script('scan_media.py'),
            'subscr': run_script('subscr.py'),
            'check_subscr': run_script('check_subscr.py'),
            'indexer': run_script('indexer.py'),
            'downloader': run_script('downloader.py'),
            'tmdb_id': run_script('tmdb_id.py'),
            'dateadded': run_script('dateadded.py'),
            'actor_nfo': run_script('actor_nfo.py'),
            'episodes_nfo': run_script('episodes_nfo.py'),
            'auto_delete_tasks': run_script('auto_delete_tasks.py')
        }

        # 等待所有脚本执行完成
        log_info(logger, "开始执行所有任务...")
        for script_name, future in futures.items():
            try:
                result = future.result(timeout=3600)  # 1小时超时
                if result:
                    log_info(logger, f"{script_name} 执行成功")
                else:
                    log_warning(logger, f"{script_name} 执行失败")
            except concurrent.futures.TimeoutError:
                log_error(logger, f"{script_name} 执行超时")
            except Exception as e:
                log_error(logger, f"{script_name} 执行异常", e)

        if not xunlei_started:
            start_xunlei_torrent()
            xunlei_started = True

        log_info(logger, "-" * 80)
        log_info(logger, "所有任务已执行完毕")
        log_info(logger, "-" * 80)

        log_info(logger, f"所有任务已完成，等待 {run_interval_hours} 小时后再次运行...")
        time.sleep(run_interval_seconds)

if __name__ == "__main__":
    start_check_db_dir()
    report_versions()
    log_info(logger, "等待初始化检查...")
    time.sleep(8)
    main()
