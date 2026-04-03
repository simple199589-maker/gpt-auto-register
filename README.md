# ChatGPT 账号自动注册工具

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.13+-3776AB.svg?logo=python&logoColor=white)

基于 Python + Selenium 的 ChatGPT 账号自动化工具，覆盖注册、验证码处理、绑卡开通 Plus 与取消订阅等流程。

## 项目结构

```text
.
├── app/                              # 业务核心代码
│   ├── browser/                      # 浏览器自动化包
│   │   ├── driver.py
│   │   ├── signup.py
│   │   ├── subscription.py
│   │   └── common.py
│   ├── codex/                        # Codex 登录与 Sub2Api 上传
│   │   ├── auth.py
│   │   ├── otp.py
│   │   ├── tokens.py
│   │   ├── runtime.py
│   │   ├── cli.py
│   │   └── sub2api.py
│   ├── static/                       # Web 前端静态资源
│   ├── config.py
│   ├── email_service.py
│   ├── register.py
│   ├── utils.py
│   └── web_server.py
├── scripts/
│   └── manual/                       # 手工测试/调试脚本
│       ├── codex_login_manual_test.py
│       └── email_service_manual_test.py
├── docs/
│   ├── assets/
│   ├── integration/
│   └── reference/
├── main.py                           # 命令行批量注册入口
├── server.py                         # Web 控制台入口
├── codex_login_tool.py               # Codex 账密直登入口
├── config.example.yaml               # 配置模板
├── pyproject.toml
├── uv.lock
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install uv
uv sync
```

### 2. 准备配置

```bash
cp config.example.yaml config.yaml
```

然后编辑 `config.yaml`，填入邮箱服务、浏览器与支付相关配置。

### 3. 运行入口

Web 控制台：

```bash
uv run server.py
uv run server.py 5006
uv run server.py --port 5006
uv run server.py --port 5006 --api 1
```

命令行批量注册：

```bash
uv run main.py
```

Codex 账密直登：

```bash
uv run codex_login_tool.py --email your@example.com --password your-password
```

手动 OTP 模式：

```bash
uv run codex_login_tool.py --email your@example.com --password your-password --otp-mode manual
```

## 手工脚本

邮箱服务手工调试：

```bash
uv run python scripts/manual/email_service_manual_test.py create
uv run python scripts/manual/email_service_manual_test.py fetch --email test@example.com
```

Codex 手工登录脚本：

```bash
uv run python scripts/manual/codex_login_manual_test.py
```

## 配置说明

所有配置来自根目录 `config.yaml`。

```yaml
registration:
  total_accounts: 1
  min_age: 20
  max_age: 40

email:
  worker_url: "https://your-worker.workers.dev"
  domainIndex: [0, 1, 2]
  prefix_length: 10
  wait_timeout: 120
  poll_interval: 3
  admin_password: "your-password"

browser:
  max_wait_time: 600
  short_wait_time: 120
  user_agent: "..."

password:
  length: 16
  charset: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%"

retry:
  http_max_retries: 5
  http_timeout: 30
  error_page_max_retries: 5
  button_click_max_retries: 3
  manual_activation_attempts: 3

batch:
  interval_min: 5
  interval_max: 15

files:
  accounts_file: "registered_accounts.txt"
  accounts_db_file: "data/accounts.db"

payment:
  credit_card:
    number: "your-card-number"
    expiry: "MMYY"
    expiry_month: "MM"
    expiry_year: "YYYY"
    cvc: "xxx"

plus:
  mode: "activation_api"
  auto_activate: true

activation_api:
  base_url: ["https://bot.joini.cloud", "http://127.0.0.1:8000"]
  api_key: "your_activation_api_key"
  bearer: ""
  poll_interval: 3
  poll_timeout: 300

sub2api:
  base_url: "https://your-sub2api-domain"
  bearer: ""
  email: "admin@sub2api.local"
  password: "your-sub2api-admin-password"
  auto_upload_sub2api: true
  group_ids: [2]
```

必须配置：

| 配置项 | 路径 | 说明 |
|--------|------|------|
| Worker 地址 | `email.worker_url` | 你的 cloudflare_temp_email Worker 地址 |
| 管理员密码 | `email.admin_password` | 邮箱服务管理员密码 |

Sub2Api 上传说明：

- `plus.auto_activate=false` 时，注册成功后会跳过 Plus 激活并直接进入 Sub2Api 流程。
- `activation_api.base_url` 支持字符串或数组；当配置为数组时，启动 `server.py` 可用 `--api <索引>` 选择地址，索引从 `0` 开始，越界会回退到第 `0` 个。
- 手动点击“重试 Plus”或“激活 Team”时，会按 `retry.manual_activation_attempts` 配置的轮数执行，成功即停止。
- Codex 上传使用 Sub2Api 后台 `email/password` 登录获取 bearer，不走 `api_key`。
- `sub2api.base_url` 建议直接填写 `https://` 地址，避免网关 301 把 POST 改写成 GET。

账号存储说明：

- 当前默认使用本地 SQLite 数据库 `data/accounts.db`。
- 若存在旧的 `registered_accounts.txt`，启动时会自动导入数据库。

## 模块概览

- `app.config`：配置加载与兼容常量导出。
- `app.email_service`：临时邮箱创建、拉取邮件、提取验证码。
- `app.browser`：浏览器驱动、注册流程、订阅流程、公共交互辅助。
- `app.register`：注册主流程与批量运行入口。
- `app.web_server`：Web 控制台与状态接口。
- `app.codex.runtime`：Codex 登录统一门面。

## 补充文档

- API 参考：`docs/reference/api.md`
- Sub2Api 集成说明：`docs/integration/admin_payment_integration_api.md`
- 调试截图资源：`docs/assets/debug_no_plus_btn.png`

## 输出文件

- 旧账号导入源：`registered_accounts.txt`
- 账号数据库：`data/accounts.db`
- Codex token 输出目录：`output_tokens/`

## 注意事项

1. 请勿提交 `config.yaml` 等敏感配置。
2. 需要正确部署并配置临时邮箱服务。
3. 注册过程中请勿手动操作浏览器窗口。
4. 项目中的手工脚本仅用于调试，不属于自动化测试。

## 免责声明

1. 本项目仅供技术学习与研究使用。
2. 请严格遵守 OpenAI 及相关服务的使用条款。
3. 使用者需自行承担自动化行为带来的全部风险。
4. 项目按现状提供，不承诺目标站点变化后的可用性。


