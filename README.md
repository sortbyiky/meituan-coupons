# 美团外卖红包自动领取

基于 Docker 的美团外卖红包自动领取工具，支持一键部署到服务器。

## 功能特性

- 自动领取外卖红包
- 自动领取团购红包
- 支持多账号（用 `&` 分隔）
- 支持自定义执行时间
- Docker 一键部署
- 支持日志持久化

## 快速开始

### 方式一：Docker Compose（推荐）

1. **克隆项目**

```bash
git clone https://github.com/sortbyiky/meituan-coupons.git
cd meituan-coupons
```

2. **配置 Token**

创建 `.env` 文件：

```bash
# 必填：你的美团 Token
MEITUAN_TOKEN=你的token值

# 可选：定时执行时间（小时），默认 8,14
CRON_HOURS=8,14

# 可选：启动时立即执行一次
RUN_ON_START=true
```

3. **启动服务**

```bash
docker-compose up -d
```

4. **查看日志**

```bash
# 查看容器日志
docker logs -f meituan-coupons

# 查看执行日志
cat logs/coupons.log
```

### 方式二：Docker 命令行

```bash
docker run -d \
  --name meituan-coupons \
  --restart unless-stopped \
  -e MEITUAN_TOKEN="你的token值" \
  -e CRON_HOURS="8,14" \
  -e RUN_ON_START="true" \
  -v $(pwd)/logs:/var/log/meituan \
  $(docker build -q .)
```

### 方式三：一键部署脚本

```bash
# 下载并运行
curl -fsSL https://raw.githubusercontent.com/sortbyiky/meituan-coupons/main/install.sh | bash -s -- "你的token值"
```

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `MEITUAN_TOKEN` | 是 | - | 美团 Token，多账号用 `&` 分隔 |
| `CRON_HOURS` | 否 | `8,14` | 定时执行的小时（北京时间） |
| `RUN_ON_START` | 否 | `true` | 启动时是否立即执行一次 |

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
token=AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI_TJ8W51CbjmnaK8E8akf7IFnJGXU7gL2KGcU7FB2Sp0gAAAADlMAAACNSA1wH7Ff0yhfqXaSMsNY8TMahfSjy2ULwxho_vtQU9VpbG708c8p_9EdmhGvY-; other=xxx
```

你需要的是：
```
AgGYIaHEzI-14y0HtXaEk2ugpWQkAF-chI_TJ8W51CbjmnaK8E8akf7IFnJGXU7gL2KGcU7FB2Sp0gAAAADlMAAACNSA1wH7Ff0yhfqXaSMsNY8TMahfSjy2ULwxho_vtQU9VpbG708c8p_9EdmhGvY-
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
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 手动执行一次
docker exec meituan-coupons python /app/meituan.py

# 更新到最新版本
git pull && docker-compose up -d --build
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

A: Token 有效期约 30 天，失效后需要重新获取。

### Q: 提示"请求异常"怎么办？

A: 可能是网络问题或 Token 失效，检查：
1. 服务器是否能访问美团（需要国内服务器）
2. Token 是否正确、是否过期
3. 查看详细日志 `logs/coupons.log`

### Q: 如何查看领取了哪些红包？

A: 查看日志文件：
```bash
cat logs/coupons.log
```

### Q: 支持哪些红包？

A: 支持以下类型：
- 外卖满减红包
- 外卖神券
- 闪购红包（水果、零食、便利店等）
- 团购红包
- 各类商家粮票

## 免责声明

- 本项目仅供学习交流使用
- 请勿滥用，遵守美团平台规则
- 使用本项目产生的任何后果由用户自行承担

## 致谢

- [zyqinglong](https://github.com/linbailo/zyqinglong) - 原始脚本参考

## License

MIT
