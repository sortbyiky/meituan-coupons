#!/bin/sh

# 美团红包自动领取 - Docker 入口脚本

LOG_FILE="/var/log/meituan/coupons.log"

# 检查 Token
if [ -z "$MEITUAN_TOKEN" ]; then
    echo "错误: 未设置 MEITUAN_TOKEN 环境变量"
    echo "请使用 -e MEITUAN_TOKEN=你的token 参数启动容器"
    exit 1
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
echo "=================================================="
echo "容器已启动，定时任务运行中..."
echo "使用 docker logs -f 查看日志"
echo "=================================================="

# 启动 cron 守护进程（前台运行）
crond -f -l 2
