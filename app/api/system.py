from flask import request, jsonify, session
import psutil
import time
import os
import json
from transmission_rpc import Client as TransmissionClient
from qbittorrentapi import Client as QbittorrentClient
from app.core.database import get_db
from app.core.config import setup_logger
from app.auth.auth import login_required
from app.utils.cache import cache

logger = setup_logger()

# 获取系统资源信息
def system_resources():
    # 尝试从缓存获取
    cached_data = cache.get('system_resources')
    if cached_data:
        return jsonify(cached_data)
    
    # 获取存储空间信息
    disk_usage = psutil.disk_usage('/Media')
    disk_total_gb = disk_usage.total / (1024 ** 3)
    disk_used_gb = disk_usage.used / (1024 ** 3)
    disk_usage_percent = disk_usage.percent

    # 获取 CPU 利用率
    cpu_usage_percent = psutil.cpu_percent(interval=0.5)  # 减少间隔以提高响应速度

    # 获取 CPU 数量和核心数
    cpu_count_logical = psutil.cpu_count(logical=True)
    cpu_count_physical = psutil.cpu_count(logical=False)

    # 获取内存信息
    memory = psutil.virtual_memory()
    memory_total_gb = memory.total / (1024 ** 3)
    memory_used_gb = memory.used / (1024 ** 3)
    memory_usage_percent = memory.percent

    # 获取下载器客户端
    try:
        client = get_downloader_client()
        if isinstance(client, TransmissionClient):
            torrents = client.get_torrents()
            net_io_recv_per_sec = sum(t.rate_download for t in torrents) / 1024
            net_io_sent_per_sec = sum(t.rate_upload for t in torrents) / 1024
        elif isinstance(client, QbittorrentClient):
            torrents = client.torrents_info()
            net_io_recv_per_sec = sum(t.dlspeed for t in torrents) / 1024
            net_io_sent_per_sec = sum(t.upspeed for t in torrents) / 1024
        else:
            net_io_sent_per_sec = 0
            net_io_recv_per_sec = 0
    except Exception as e:
        logger.error(f"获取下载器信息失败: {e}")
        net_io_sent_per_sec = 0
        net_io_recv_per_sec = 0

    # 准备响应数据
    response_data = {
        "disk_total_gb": round(disk_total_gb, 2),
        "disk_used_gb": round(disk_used_gb, 2),
        "disk_usage_percent": disk_usage_percent,
        "net_io_sent": round(net_io_sent_per_sec, 2),
        "net_io_recv": round(net_io_recv_per_sec, 2),
        "cpu_usage_percent": cpu_usage_percent,
        "cpu_count_logical": cpu_count_logical,
        "cpu_count_physical": cpu_count_physical,
        "memory_total_gb": round(memory_total_gb, 2),
        "memory_used_gb": round(memory_used_gb, 2),
        "memory_usage_percent": memory_usage_percent
    }
    
    # 缓存结果（10秒）
    cache.set('system_resources', response_data, ttl=10)
    
    # 返回系统资源数据
    return jsonify(response_data)

# 获取系统进程信息
def system_processes():
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_percent', 'create_time']):
        try:
            # 计算运行时长（秒）
            uptime = time.time() - proc.info['create_time']
            
            # 格式化运行时长为天、小时、分钟、秒
            days = int(uptime // (3600 * 24))
            hours = int((uptime % (3600 * 24)) // 3600)
            minutes = int((uptime % 3600) // 60)
            seconds = int(uptime % 60)

            if days > 0:
                uptime_formatted = f"{days}天{hours:02d}小时"
            else:
                uptime_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            # 获取命令行参数
            cmdline = proc.info['cmdline']
            
            # 初始化文件名为 None
            file_name = None
            
            # 如果进程名为 'python' 或 'python3'，且 cmdline 不为 None，则尝试获取文件名
            if proc.info['name'] in ['python', 'python3'] and cmdline and len(cmdline) > 1:
                file_name = os.path.basename(cmdline[1])
            
            # 添加进程信息到列表
            processes.append({
                "pid": proc.info['pid'],
                "name": proc.info['name'],
                "file_name": file_name,
                "cpu_percent": proc.info['cpu_percent'],
                "memory_percent": proc.info['memory_percent'],
                "uptime": uptime_formatted
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # 忽略不存在的进程、访问被拒绝的进程和僵尸进程
            continue

    return jsonify({
        "processes": processes
    })

# 获取站点状态信息
def site_status():
    try:
        # 导入站点测试模块
        import sys
        sys.path.append('/app')
        
        # 动态导入站点测试模块
        if 'site_test' in sys.modules:
            import importlib
            importlib.reload(sys.modules['site_test'])
            site_test_module = sys.modules['site_test']
        else:
            import site_test
            site_test_module = site_test
            
        # 创建站点测试实例并获取配置
        tester = site_test_module.SiteTester()
        sites = tester.load_sites_config()
        
        # 读取站点启用状态
        db = get_db()
        enabled_sites = {}
        for site_name in sites.keys():
            option_name = f"{site_name.lower()}_enabled"
            try:
                result = db.execute('SELECT VALUE FROM CONFIG WHERE OPTION = ?', (option_name,)).fetchone()
                enabled_sites[site_name] = result['VALUE'] == 'True' if result else False
            except Exception as e:
                logger.error(f"读取站点 {site_name} 启用状态失败: {e}")
                enabled_sites[site_name] = False
        
        # 读取站点状态文件
        status_file_path = '/tmp/site_status.json'
        site_status_data = {}
        last_checked = None
        
        if os.path.exists(status_file_path):
            try:
                with open(status_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    site_status_data = data.get('status', {})
                    last_checked = data.get('last_checked')
            except json.JSONDecodeError as e:
                logger.error(f"解析站点状态文件失败: {e}")
            except Exception as e:
                logger.error(f"读取站点状态文件失败: {e}")
        else:
            logger.warning("站点状态文件不存在")
        
        # 返回站点信息
        site_info = []
        for site_name, site_config in sites.items():
            site_info.append({
                'name': site_name,
                'url': site_config['base_url'],
                'keyword': site_config['keyword'],
                'enabled': enabled_sites.get(site_name, False)
            })
        
        return jsonify({
            'sites': site_info,
            'last_checked': last_checked,
            'status': site_status_data
        })
    except Exception as e:
        logger.error(f"获取站点状态失败: {e}")
        return jsonify({'error': '获取站点状态失败'}), 500

# 手动检查站点状态并更新状态文件
def check_site_status():
    try:
        import sys
        import os
        import json
        sys.path.append('/app')
        
        # 动态导入站点测试模块
        if 'site_test' in sys.modules:
            import importlib
            importlib.reload(sys.modules['site_test'])
            site_test_module = sys.modules['site_test']
        else:
            import site_test
            site_test_module = site_test
            
        # 运行站点测试
        tester = site_test_module.SiteTester()
        results = tester.run_tests()
        
        # 保存结果到文件
        status_data = {
            'status': results,
            'last_checked': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open('/tmp/site_status.json', 'w', encoding='utf-8') as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'status': results,
            'last_checked': status_data['last_checked']
        })
    except Exception as e:
        logger.error(f"检查站点状态失败: {e}")
        return jsonify({'error': '检查站点状态失败'}), 500
