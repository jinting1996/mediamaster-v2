#!/bin/bash
# MediaMaster V2 优化版 - 一键部署脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 MediaMaster V2 部署脚本${NC}"

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ 请先安装 Docker${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ 请先安装 docker-compose${NC}"
    exit 1
fi

# 创建目录
echo -e "${YELLOW}📁 创建必要目录...${NC}"
mkdir -p config downloads logs

# 检查配置文件
if [ ! -f "config/data.db" ]; then
    echo -e "${YELLOW}⚠️ 配置文件不存在，创建一个默认配置...${NC}"
    echo "请在部署后手动配置数据库"
fi

# 拉取最新镜像（或构建）
echo -e "${YELLOW}🐳 拉取镜像...${NC}"
docker pull jinting1996/mediamaster-v2:latest || echo "镜像不存在，将使用现有镜像"

# 启动容器
echo -e "${YELLOW}▶️ 启动服务...${NC}"
docker-compose up -d

# 检查状态
echo -e "${YELLOW}📊 检查状态...${NC}"
sleep 3
docker-compose ps

# 完成
echo -e "${GREEN}✅ 部署完成！${NC}"
echo ""
echo "访问地址: http://<你的NAS IP>:8888"
echo ""
echo "常用命令:"
echo "  查看日志: docker-compose logs -f"
echo "  重启:     docker-compose restart"
echo "  停止:     docker-compose down"
