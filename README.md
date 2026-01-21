# 美团外卖红包自动领取

基于 GitHub Actions 的美团外卖红包自动领取工具。

## 功能

- 自动领取外卖红包
- 自动领取团购红包
- 支持多账号
- 每天自动执行两次

## 使用方法

### 1. Fork 本仓库

点击右上角 Fork 按钮

### 2. 获取 Token

1. 打开美团外卖 H5 页面：https://h5.waimai.meituan.com
2. 使用浏览器开发者工具 (F12) 抓包
3. 在请求头或 Cookie 中找到 `token` 值

### 3. 配置 Token

1. 进入仓库 Settings -> Secrets and variables -> Actions
2. 点击 "New repository secret"
3. Name 填写: `MEITUAN_TOKEN`
4. Secret 填写你的 token 值
5. 多账号用 `&` 分隔

### 4. 启用 Actions

1. 进入 Actions 页面
2. 点击 "I understand my workflows, go ahead and enable them"
3. 可以手动触发测试：点击 "美团红包自动领取" -> "Run workflow"

## 执行时间

- 北京时间 8:00
- 北京时间 14:00

## 注意事项

- Token 有效期有限，失效后需要重新获取
- 请勿滥用，仅供学习交流

## 致谢

- [zyqinglong](https://github.com/linbailo/zyqinglong)
