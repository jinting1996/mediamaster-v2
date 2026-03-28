import logging
import os
import traceback
from datetime import datetime

class CustomFormatter(logging.Formatter):
    """自定义日志格式化器"""
    def format(self, record):
        # 添加时间戳
        record.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 添加进程ID
        record.process_id = os.getpid()
        # 添加线程名称
        import threading
        record.thread_name = threading.current_thread().name
        # 格式化异常信息
        if record.exc_info:
            record.exc_details = '\n' + ''.join(traceback.format_exception(*record.exc_info))
        else:
            record.exc_details = ''
        return super().format(record)

def setup_logger(name="MediaMasterLogger", log_file="/tmp/log/app.log"):
    """设置日志记录器"""
    # 确保日志目录存在
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    
    # 如果日志记录器已有处理器，先清除
    if logger.handlers:
        logger.handlers.clear()
    
    # 创建文件处理器
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 定义日志格式
    log_format = "%(timestamp)s - %(levelname)s - [PID: %(process_id)s] [Thread: %(thread_name)s] - %(message)s%(exc_details)s"
    formatter = CustomFormatter(log_format)
    
    # 设置处理器的格式化器
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加处理器到日志记录器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def log_error(logger, message, error=None):
    """记录错误信息"""
    if error:
        logger.error(f"{message}: {str(error)}")
        # 记录完整的异常信息
        import traceback
        logger.error(traceback.format_exc())
    else:
        logger.error(message)

def log_info(logger, message):
    """记录信息"""
    logger.info(message)

def log_warning(logger, message):
    """记录警告信息"""
    logger.warning(message)

def log_debug(logger, message):
    """记录调试信息"""
    logger.debug(message)
