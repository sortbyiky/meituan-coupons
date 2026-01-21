# 美团外卖红包自动领取

基于 Docker 的美团外卖红包自动领取工具，支持一键部署到服务器，内置 Web 控制台。

## 功能特性

- 自动领取外卖红包
- 自动领取团购红包
- 支持多账号（用 `&` 分隔）
- 支持自定义执行时间
- **Web 控制台**：查看日志、手动触发执行
- Docker 一键部署，支持 amd64/arm64
- 支持日志持久化

## 镜像地址

```
ghcr.io/sortbyiky/meituan-coupons:latest
```

## 快速开始

### 方式一：Docker 命令行（最简单）

```bash
docker run -d \
  --name meituan-coupons \
  --restart unless-stopped \
  -p 5000:5000 \
  -e MEITUAN_TOKEN="你的token值" \
  -e RUN_ON_START="true" \
  -v $(pwd)/logs:/var/log/meituan \
  ghcr.io/sortbyiky/meituan-coupons:latest
```

启动后访问 http://localhost:5000 打开 Web 控制台。

### 方式二：Docker Compose（推荐）

1. **创建目录和配置文件**

```bash
mkdir -p meituan-coupons && cd meituan-coupons

# 创建 docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  meituan-coupons:
    image: ghcr.io/sortbyiky/meituan-coupons:latest
    container_name: meituan-coupons
    restart: unless-stopped
    ports:
      - "${WEB_PORT:-5000}:5000"
    environment:
      - MEITUAN_TOKEN=${MEITUAN_TOKEN}
      - CRON_HOURS=${CRON_HOURS:-8,14}
      - RUN_ON_START=${RUN_ON_START:-true}
      - ENABLE_WEB=${ENABLE_WEB:-true}
      - WEB_PORT=${WEB_PORT:-5000}
    volumes:
      - ./logs:/var/log/meituan
EOF

# 创建 .env 配置文件
cat > .env << EOF
MEITUAN_TOKEN=你的token值
CRON_HOURS=8,14
RUN_ON_START=true
ENABLE_WEB=true
WEB_PORT=5000
EOF
```

2. **启动服务**

```bash
docker-compose up -d
```

3. **访问 Web 控制台**

打开浏览器访问 http://localhost:5000

### 方式三：一键部署脚本

```bash
curl -fsSL https://raw.githubusercontent.com/sortbyiky/meituan-coupons/main/install.sh | bash -s -- "你的token值"
```

## Web 控制台

部署后访问 `http://服务器IP:5000` 即可打开 Web 控制台。

### 功能

- **查看执行状态**：当前状态、上次执行时间、执行结果
- **查看日志**：实时查看领取日志，支持自动刷新
- **手动执行**：点击按钮立即执行一次领取
- **清空日志**：清除历史日志记录

### 截图

Web 控制台界面简洁美观，支持：
- 实时状态显示
- 日志语法高亮（成功/失败/信息）
- 自动刷新（状态 5 秒、日志 10 秒）
- 响应式设计，支持手机访问

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `MEITUAN_TOKEN` | 是 | - | 美团 Token，多账号用 `&` 分隔 |
| `CRON_HOURS` | 否 | `8,14` | 定时执行的小时（北京时间） |
| `RUN_ON_START` | 否 | `true` | 启动时是否立即执行一次 |
| `ENABLE_WEB` | 否 | `true` | 是否启用 Web 控制台 |
| `WEB_PORT` | 否 | `5000` | Web 控制台端口 |

## Token 获取教程

### 方法一：手机抓包（推荐）

**准备工具**：
- 安卓手机：HttpCanary / Packet Capture
- 苹果手机：Stream / Thor

**步骤**：

1. 安装抓包工具并配置好证书
2. 打开抓包，然后打开**微信小程序**中的「美团外卖」
3. 随便点击几个页面，产生网络请求
4. 在抓包工具中搜索 `meituan.com` 的请求
5. 找到请求头（Headers）中的 `token` 字段，复制其值

**示例请求头**：
```
Cookie: token=AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI...
```

只需要复制 `token=` 后面的值。

### 方法二：电脑浏览器抓包

1. 打开 Chrome 浏览器，按 `F12` 打开开发者工具
2. 切换到 `Network`（网络）标签
3. 访问 https://h5.waimai.meituan.com/waimai/mindex/home
4. 如果未登录，扫码登录
5. 在 Network 中找到任意 `meituan.com` 的请求
6. 点击请求，在 `Headers` 中找到 `Cookie`
7. 复制 `token=` 后面的值（到下一个分号 `;` 之前）

**Cookie 示例**：
```
token=AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI_TJ8W51Cbj...; other=xxx
```

你需要的是：
```
AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI_TJ8W51Cbj...
```

### 方法三：小程序开发者工具

1. 下载安装「微信开发者工具」
2. 使用「公众号网页调试」功能
3. 访问美团外卖 H5 页面
4. 在 Network 中获取 token

## 多账号配置

多个账号的 Token 用 `&` 符号连接：

```bash
MEITUAN_TOKEN="token1&token2&token3"
```

## 常用命令

```bash
# 查看运行状态
docker ps | grep meituan

# 查看日志
docker logs -f meituan-coupons

# 手动执行一次
docker exec meituan-coupons python /app/meituan.py

# 停止服务
docker stop meituan-coupons

# 删除容器
docker rm meituan-coupons

# 更新镜像
docker pull ghcr.io/sortbyiky/meituan-coupons:latest
docker-compose up -d

# 查看执行记录
cat logs/coupons.log
```

## 执行时间说明

默认每天执行两次：
- 北京时间 **8:00**
- 北京时间 **14:00**

可通过 `CRON_HOURS` 环境变量自定义，例如：
- `CRON_HOURS=9` - 每天 9:00 执行
- `CRON_HOURS=8,12,18` - 每天 8:00、12:00、18:00 执行

## 常见问题

### Q: Token 多久失效？

A: Token 有效期约 30 天，失效后需要重新获取并更新环境变量。

### Q: 提示"请求异常"怎么办？

A: 可能原因：
1. **服务器在国外** - 美团 API 屏蔽海外 IP，需要使用国内服务器
2. **Token 失效** - 重新获取 Token
3. **网络问题** - 检查服务器网络

### Q: 如何更新 Token？

A:
```bash
# 方式一：修改 .env 文件后重启
vim .env  # 修改 MEITUAN_TOKEN
docker-compose restart

# 方式二：直接用新 Token 重建容器
docker rm -f meituan-coupons
docker run -d --name meituan-coupons ... -e MEITUAN_TOKEN="新token" ...
```

### Q: 支持哪些红包？

A: 支持以下类型：
- 外卖满减红包
- 外卖神券
- 闪购红包（水果、零食、便利店等）
- 团购红包
- 各类商家粮票

### Q: 支持哪些架构？

A: 镜像支持 `linux/amd64` 和 `linux/arm64`，可在 x86 服务器和 ARM 服务器（如树莓派）上运行。

### Q: 如何禁用 Web 控制台？

A: 设置环境变量 `ENABLE_WEB=false` 即可禁用 Web 控制台。

### Q: 如何修改 Web 控制台端口？

A: 设置环境变量 `WEB_PORT=8080`（或其他端口），同时修改端口映射 `-p 8080:8080`。

## 免责声明

- 本项目仅供学习交流使用
- 请勿滥用，遵守美团平台规则
- 使用本项目产生的任何后果由用户自行承担

## 致谢

- [zyqinglong](https://github.com/linbailo/zyqinglong) - 原始脚本参考

## License

MIT
