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
TOKEN="$1"
if [ -z "$TOKEN" ]; then
    echo -e "${YELLOW}用法: $0 <你的美团Token>${NC}"
    echo ""
    echo "Token 获取方法:"
    echo "1. 打开 Chrome，按 F12 打开开发者工具"
    echo "2. 访问 https://h5.waimai.meituan.com"
    echo "3. 在 Network 中找到请求，复制 Cookie 中的 token 值"
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
cat > "$INSTALL_DIR/.env" << EOF
# 美团 Token（必填）
MEITUAN_TOKEN=$TOKEN

# 定时执行时间（小时），默认 8:00 和 14:00
CRON_HOURS=8,14

# 启动时立即执行一次
RUN_ON_START=true
EOF

cat > "$INSTALL_DIR/docker-compose.yml" << EOF
version: '3.8'
services:
  meituan-coupons:
    image: $IMAGE
    container_name: meituan-coupons
    restart: unless-stopped
    environment:
      - MEITUAN_TOKEN=\${MEITUAN_TOKEN}
      - CRON_HOURS=\${CRON_HOURS:-8,14}
      - RUN_ON_START=\${RUN_ON_START:-true}
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
        -e MEITUAN_TOKEN="$TOKEN" \
        -e CRON_HOURS="8,14" \
        -e RUN_ON_START="true" \
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
echo "常用命令:"
echo "  查看日志:   docker logs -f meituan-coupons"
echo "  查看状态:   docker ps | grep meituan"
echo "  手动执行:   docker exec meituan-coupons python /app/meituan.py"
echo "  停止服务:   docker stop meituan-coupons"
echo "  更新镜像:   docker pull $IMAGE && docker-compose -f $INSTALL_DIR/docker-compose.yml up -d"
echo "  更新Token:  编辑 $INSTALL_DIR/.env 后执行 docker-compose restart"
echo ""
echo -e "${YELLOW}提示: 默认每天 8:00 和 14:00 自动执行${NC}"
echo ""
