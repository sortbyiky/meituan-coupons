#!/bin/sh

# 美团红包自动领取 - Docker 入口脚本

LOG_FILE="/var/log/meituan/coupons.log"

# Token 可通过 Web 控制台添加，不再强制要求环境变量
if [ -z "$MEITUAN_TOKEN" ]; then
    echo "提示: 未设置 MEITUAN_TOKEN 环境变量"
    echo "您可以通过 Web 控制台添加和管理 Token"
fi

echo "=================================================="
echo "美团外卖红包自动领取 - Docker 版"
echo "=================================================="
echo "时区: $(date +%Z)"
echo "当前时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 设置定时任务时间，默认 8:00 和 14:00
CRON_HOURS="${CRON_HOURS:-8,14}"
echo "定时执行时间: 每天 ${CRON_HOURS} 点"

# 创建定时任务
# 将环境变量写入文件供 cron 使用
echo "MEITUAN_TOKEN=$MEITUAN_TOKEN" > /app/.env

# 创建 cron 任务
CRON_SCHEDULE="0 ${CRON_HOURS} * * *"
echo "${CRON_SCHEDULE} cd /app && export \$(cat /app/.env | xargs) && python meituan.py >> ${LOG_FILE} 2>&1" > /etc/crontabs/root

echo "定时任务已配置: ${CRON_SCHEDULE}"
echo ""

# 是否立即执行一次
if [ "$RUN_ON_START" = "true" ] || [ "$RUN_ON_START" = "1" ]; then
    echo "正在立即执行一次..."
    echo ""
    python /app/meituan.py 2>&1 | tee -a ${LOG_FILE}
    echo ""
    echo "首次执行完成，等待下次定时任务..."
else
    echo "提示: 设置 RUN_ON_START=true 可在启动时立即执行一次"
fi

echo ""
echo "日志文件: ${LOG_FILE}"

# Web 控制台
WEB_PORT="${WEB_PORT:-5000}"
ENABLE_WEB="${ENABLE_WEB:-true}"

if [ "$ENABLE_WEB" = "true" ] || [ "$ENABLE_WEB" = "1" ]; then
    echo ""
    echo "=================================================="
    echo "Web 控制台已启用"
    echo "访问地址: http://localhost:${WEB_PORT}"
    echo "=================================================="

    # 后台启动 Web 服务
    gunicorn -b 0.0.0.0:${WEB_PORT} -w 1 --timeout 120 web:app &
fi

echo ""
echo "=================================================="
echo "容器已启动，定时任务运行中..."
echo "使用 docker logs -f 查看日志"
echo "=================================================="

# 启动 cron 守护进程（前台运行）
crond -f -l 2
