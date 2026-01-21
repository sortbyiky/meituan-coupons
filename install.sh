#!/bin/bash

# 美团红包自动领取 - 一键部署脚本

set -e

REPO_URL="https://github.com/sortbyiky/meituan-coupons.git"
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
echo -e "${YELLOW}[1/5] 检查 Docker 环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: 未安装 Docker${NC}"
    echo "请先安装 Docker: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}错误: 未安装 Docker Compose${NC}"
    echo "请先安装 Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi
echo -e "${GREEN}Docker 环境正常${NC}"

# 检查 Git
echo -e "${YELLOW}[2/5] 检查 Git...${NC}"
if ! command -v git &> /dev/null; then
    echo -e "${YELLOW}Git 未安装，尝试安装...${NC}"
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y git
    elif command -v yum &> /dev/null; then
        sudo yum install -y git
    elif command -v apk &> /dev/null; then
        apk add --no-cache git
    else
        echo -e "${RED}无法自动安装 Git，请手动安装${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}Git 正常${NC}"

# 克隆或更新项目
echo -e "${YELLOW}[3/5] 获取项目代码...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo "目录已存在，更新代码..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "克隆项目..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
echo -e "${GREEN}代码获取完成${NC}"

# 创建配置文件
echo -e "${YELLOW}[4/5] 创建配置文件...${NC}"
cat > "$INSTALL_DIR/.env" << EOF
# 美团 Token（必填）
MEITUAN_TOKEN=$TOKEN

# 定时执行时间（小时），默认 8:00 和 14:00
CRON_HOURS=8,14

# 启动时立即执行一次
RUN_ON_START=true
EOF
echo -e "${GREEN}配置文件已创建: $INSTALL_DIR/.env${NC}"

# 启动服务
echo -e "${YELLOW}[5/5] 启动服务...${NC}"
cd "$INSTALL_DIR"

# 检查 docker-compose 命令
if command -v docker-compose &> /dev/null; then
    docker-compose up -d --build
else
    docker compose up -d --build
fi

echo ""
echo -e "${GREEN}=================================================="
echo "   部署完成！"
echo "==================================================${NC}"
echo ""
echo "安装目录: $INSTALL_DIR"
echo ""
echo "常用命令:"
echo "  查看日志:   docker logs -f meituan-coupons"
echo "  查看状态:   docker ps | grep meituan"
echo "  手动执行:   docker exec meituan-coupons python /app/meituan.py"
echo "  停止服务:   cd $INSTALL_DIR && docker-compose down"
echo "  更新Token:  编辑 $INSTALL_DIR/.env 后重启"
echo ""
echo -e "${YELLOW}提示: 默认每天 8:00 和 14:00 自动执行${NC}"
echo ""
