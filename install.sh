#!/bin/bash

# 美团红包自动领取 - 一键部署脚本

set -e

IMAGE="ghcr.io/sortbyiky/meituan-coupons:latest"
INSTALL_DIR="$HOME/meituan-coupons"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
echo "=================================================="
echo "   美团外卖红包自动领取 - 一键部署脚本"
echo "=================================================="
echo -e "${NC}"

# 检查参数
PASSWORD="$1"
TOKEN="$2"

if [ -z "$PASSWORD" ]; then
    echo -e "${YELLOW}用法: $0 <登录密码> [美团Token]${NC}"
    echo ""
    echo "参数说明:"
    echo "  登录密码: Web 控制台的登录密码（必填）"
    echo "  美团Token: 可选，也可以部署后通过 Web 控制台添加"
    echo ""
    echo "示例:"
    echo "  $0 mypassword123"
    echo "  $0 mypassword123 AgGYIaHEzI-14y0HtXaEk2ugpWQkAF..."
    echo ""
    exit 1
fi

# 检查 Docker
echo -e "${YELLOW}[1/4] 检查 Docker 环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: 未安装 Docker${NC}"
    echo "请先安装 Docker: https://docs.docker.com/engine/install/"
    exit 1
fi
echo -e "${GREEN}Docker 环境正常${NC}"

# 创建目录
echo -e "${YELLOW}[2/4] 创建配置目录...${NC}"
mkdir -p "$INSTALL_DIR/logs"
cd "$INSTALL_DIR"

# 创建配置文件
echo -e "${YELLOW}[3/4] 创建配置文件...${NC}"

# 设置 RUN_ON_START
if [ -n "$TOKEN" ]; then
    RUN_ON_START="true"
else
    RUN_ON_START="false"
fi

cat > "$INSTALL_DIR/.env" << EOF
# Web 控制台登录密码
ADMIN_PASSWORD=$PASSWORD

# 美团 Token（可选，也可通过 Web 控制台添加）
MEITUAN_TOKEN=$TOKEN

# 定时执行时间（小时），默认 8:00 和 14:00
CRON_HOURS=8,14

# 启动时立即执行一次
RUN_ON_START=$RUN_ON_START

# Web 控制台配置
ENABLE_WEB=true
WEB_PORT=5000
EOF

cat > "$INSTALL_DIR/docker-compose.yml" << EOF
version: '3.8'
services:
  meituan-coupons:
    image: $IMAGE
    container_name: meituan-coupons
    restart: unless-stopped
    ports:
      - "\${WEB_PORT:-5000}:5000"
    environment:
      - ADMIN_PASSWORD=\${ADMIN_PASSWORD:-admin123}
      - MEITUAN_TOKEN=\${MEITUAN_TOKEN:-}
      - CRON_HOURS=\${CRON_HOURS:-8,14}
      - RUN_ON_START=\${RUN_ON_START:-false}
      - ENABLE_WEB=\${ENABLE_WEB:-true}
      - WEB_PORT=\${WEB_PORT:-5000}
    volumes:
      - ./logs:/var/log/meituan
EOF

echo -e "${GREEN}配置文件已创建${NC}"

# 启动服务
echo -e "${YELLOW}[4/4] 拉取镜像并启动服务...${NC}"
cd "$INSTALL_DIR"

# 停止并删除旧容器（如果存在）
docker rm -f meituan-coupons 2>/dev/null || true

# 拉取最新镜像
docker pull "$IMAGE"

# 检查 docker-compose 命令
if command -v docker-compose &> /dev/null; then
    docker-compose up -d
elif docker compose version &> /dev/null; then
    docker compose up -d
else
    # 直接用 docker run
    docker run -d \
        --name meituan-coupons \
        --restart unless-stopped \
        -p 5000:5000 \
        -e ADMIN_PASSWORD="$PASSWORD" \
        -e MEITUAN_TOKEN="$TOKEN" \
        -e CRON_HOURS="8,14" \
        -e RUN_ON_START="$RUN_ON_START" \
        -e ENABLE_WEB="true" \
        -e WEB_PORT="5000" \
        -v "$INSTALL_DIR/logs:/var/log/meituan" \
        "$IMAGE"
fi

echo ""
echo -e "${GREEN}=================================================="
echo "   部署完成！"
echo "==================================================${NC}"
echo ""
echo "安装目录: $INSTALL_DIR"
echo "镜像地址: $IMAGE"
echo ""
echo -e "${GREEN}Web 控制台: http://localhost:5000${NC}"
echo -e "${YELLOW}登录密码: $PASSWORD${NC}"
echo ""
if [ -z "$TOKEN" ]; then
    echo -e "${YELLOW}提示: 请登录 Web 控制台添加美团 Token${NC}"
fi
echo ""
echo "常用命令:"
echo "  查看日志:   docker logs -f meituan-coupons"
echo "  查看状态:   docker ps | grep meituan"
echo "  停止服务:   docker stop meituan-coupons"
echo "  更新镜像:   docker pull $IMAGE && docker-compose -f $INSTALL_DIR/docker-compose.yml up -d"
echo ""
echo -e "${YELLOW}提示: 默认每天 8:00 和 14:00 自动执行${NC}"
echo -e "${YELLOW}提示: 可通过 Web 控制台管理 Token、查看领取历史${NC}"
echo ""
