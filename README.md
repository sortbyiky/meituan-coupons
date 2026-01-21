# 美团外卖红包自动领取

基于 Docker 的美团外卖红包自动领取工具，支持一键部署到服务器，内置 Web 控制台。

## 功能特性

- 自动领取外卖红包
- 自动领取团购红包
- 支持多账号管理
- 支持自定义执行时间
- **Web 控制台**：
  - 登录认证保护
  - 在线添加/管理 Token
  - 从美团 URL/Cookie 自动提取 Token
  - 查看领取历史和优惠券详情
  - 实时日志查看
  - 手动触发执行
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
  -e ADMIN_PASSWORD="你的登录密码" \
  -e RUN_ON_START="false" \
  -v $(pwd)/logs:/var/log/meituan \
  ghcr.io/sortbyiky/meituan-coupons:latest
```

启动后访问 http://localhost:5000 打开 Web 控制台，使用设置的密码登录后添加 Token。

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
      - MEITUAN_TOKEN=${MEITUAN_TOKEN:-}
      - CRON_HOURS=${CRON_HOURS:-8,14}
      - RUN_ON_START=${RUN_ON_START:-false}
      - ENABLE_WEB=${ENABLE_WEB:-true}
      - WEB_PORT=${WEB_PORT:-5000}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin123}
    volumes:
      - ./logs:/var/log/meituan
EOF

# 创建 .env 配置文件
cat > .env << EOF
# Web 控制台登录密码（必须修改！）
ADMIN_PASSWORD=你的登录密码

# 可选：美团 Token（也可通过 Web 控制台添加）
MEITUAN_TOKEN=

# 定时执行时间
CRON_HOURS=8,14
RUN_ON_START=false
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
# 只设置登录密码（之后通过 Web 控制台添加 Token）
curl -fsSL https://raw.githubusercontent.com/sortbyiky/meituan-coupons/main/install.sh | bash -s -- "你的登录密码"

# 同时设置登录密码和 Token
curl -fsSL https://raw.githubusercontent.com/sortbyiky/meituan-coupons/main/install.sh | bash -s -- "你的登录密码" "你的token值"
```

## Web 控制台

部署后访问 `http://服务器IP:5000` 即可打开 Web 控制台。

### 登录认证

Web 控制台需要密码登录，默认密码为 `admin123`，**强烈建议修改**。

通过环境变量 `ADMIN_PASSWORD` 设置登录密码。

### 功能

- **Token 管理**：
  - 在线添加、编辑、删除 Token
  - 支持直接粘贴美团 URL 或 Cookie，自动提取 Token
  - 支持为每个 Token 添加备注（如账号名称）

- **领取历史**：
  - 查看每次领取的详细记录
  - 显示领取的优惠券名称、金额、有效期等

- **实时日志**：
  - 查看执行日志，支持自动刷新
  - 日志语法高亮（成功/失败/信息）

- **手动执行**：
  - 点击按钮立即执行一次领取
  - 清空日志记录

### Token 输入说明

添加 Token 时支持多种输入格式：

1. **直接粘贴 Token**：
   ```
   AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI_TJ8W51Cbj...
   ```

2. **粘贴 Cookie 字符串**：
   ```
   token=AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI...; other=xxx
   ```
   系统会自动提取 `token=` 后面的值。

3. **粘贴完整 URL**：
   ```
   https://h5.waimai.meituan.com/...?token=AgGYIaHEzI...
   ```
   系统会自动从 URL 参数中提取 Token。

### 界面特点

- 响应式设计，支持手机访问
- 自动刷新（状态 5 秒、日志 10 秒）
- 简洁美观的界面

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `ADMIN_PASSWORD` | 建议 | `admin123` | Web 控制台登录密码，**强烈建议修改** |
| `MEITUAN_TOKEN` | 否 | - | 美团 Token（也可通过 Web 控制台添加） |
| `CRON_HOURS` | 否 | `8,14` | 定时执行的小时（北京时间） |
| `RUN_ON_START` | 否 | `false` | 启动时是否立即执行一次 |
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

**方式一（推荐）：通过 Web 控制台**
1. 访问 Web 控制台并登录
2. 在 Token 管理页面添加、编辑或删除 Token
3. 支持直接粘贴美团 URL 或 Cookie，自动提取

**方式二：修改环境变量**
```bash
# 修改 .env 文件后重启
vim .env  # 修改 MEITUAN_TOKEN
docker-compose restart
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
