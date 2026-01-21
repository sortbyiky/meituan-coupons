FROM python:3.11-alpine

LABEL maintainer="meituan-coupons"
LABEL description="美团外卖红包自动领取"

# 安装必要的包
RUN apk add --no-cache tzdata dcron

# 设置时区为中国
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY meituan.py .
COPY web.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# 创建日志目录
RUN mkdir -p /var/log/meituan

# Web 控制台端口
EXPOSE 5000

# 入口脚本
ENTRYPOINT ["/app/entrypoint.sh"]
