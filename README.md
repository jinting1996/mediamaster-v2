# MediaMaster V2 优化版

支持多个站点的 NAS 影视自动化订阅管理系统（优化版）

## 🚀 快速部署

### Docker Compose（推荐）

```bash
# 克隆仓库
git clone https://github.com/jinting1996/mediamaster-v2.git
cd mediamaster-v2

# 启动服务
docker-compose up -d
```

### Docker 直接运行

```bash
# 构建镜像
docker build -t jinting1996/mediamaster-v2:latest .

# 运行容器
docker run -d \
  --name mediamaster-v2 \
  -p 8888:8888 \
  -v ./config:/config \
  -v ./downloads:/Torrent \
  jinting1996/mediamaster-v2:latest
```

## 📦 Docker Hub

```bash
# 登录 Docker Hub
docker login

# 推送镜像
docker push jinting1996/mediamaster-v2:latest
```

## ⚙️ 配置

首次启动后访问 `http://your-nas:8888` 配置：

1. **站点账号** - 添加 BT 站点账号
2. **下载器** - 配置 Transmission/qBittorrent
3. **订阅** - 添加豆瓣 RSS 订阅

## 📝 优化说明

- 使用 requests 替代 Selenium（轻量高效）
- Session 复用 + 自动重试
- BeautifulSoup 解析
- 并行索引执行

## License

MIT
