# MediaMaster V2 - 优化版 Dockerfile
# 基于 Alpine + Python，移除 Selenium 依赖（轻量级）

FROM python:3.11-slim

# 设置环境
ENV LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 创建应用目录
WORKDIR /app

# 克隆仓库（或复制本地文件）
RUN git clone https://github.com/jinting1996/mediamaster-v2.git /app

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    requests \
    beautifulsoup4 \
    lxml \
    sqlalchemy \
    flask \
    schedule \
    transmission-rpc \
    qbittorrent-api \
    urllib3

# 创建必要的目录
RUN mkdir -p /config /Torrent /tmp/log /tmp/index

# 复制配置文件（如果存在）
# COPY config/ /config/

# 暴露端口
EXPOSE 8888

# 启动命令
CMD ["python", "main.py"]
