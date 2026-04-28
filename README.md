# 账号登录验证与 Sub2Api 上传工具

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.13+-3776AB.svg?logo=python&logoColor=white)

本项目当前主流程为：手动导入账号密码，执行 Codex OAuth 登录验证，保存 OAuth token，并按配置上传到 Sub2Api。历史注册、Plus 激活、Team 激活模块仍保留在代码中作为兼容参考，但 Web 控制台入口已经切换到登录上传流程。

## 快速开始

```bash
pip install uv
uv sync
cp config.example.yaml config.yaml
```

编辑 `config.yaml` 后启动 Web 控制台：

```bash
uv run server.py
uv run server.py --port 5006
```

在控制台中进入“账号管理”，导入邮箱和密码，然后点击“启动登录上传”或对单个账号执行“登录并上传”。

## 命令行验证

Codex 账密直登：

```bash
uv run codex_login_tool.py --email your@example.com --password your-password --otp-mode auto
uv run codex_login_tool.py --email your@example.com --password your-password --otp-mode manual --skip-upload
```

登录到 Sub2Api 编排脚本：

```bash
uv run python scripts/manual/login_sub2api_manual_test.py import --email your@example.com --password your-password
uv run python scripts/manual/login_sub2api_manual_test.py login --email your@example.com --otp-mode auto
uv run python scripts/manual/login_sub2api_manual_test.py upload --email your@example.com
```

邮箱 provider 调试：

```bash
uv run python scripts/manual/email_service_manual_test.py create --provider worker
uv run python scripts/manual/email_service_manual_test.py create --provider outlook
uv run python scripts/manual/email_service_manual_test.py fetch --provider outlook --email demo@outlook.com
```

## 关键配置

```yaml
email:
  provider: "worker"  # worker 或 outlook
  worker_url: "https://your-worker-name.your-subdomain.workers.dev"
  domainIndex: [0]
  wait_timeout: 120
  poll_interval: 3
  admin_password: "your-worker-admin-password"

outlook:
  base_url: "https://your-outlook-mail-station-domain"
  api_key: "your_outlook_open_api_key"
  auth_type: "api_key"
  site_code: "OPENAI"
  batch_code: ""
  domain: "outlook.com"
  refresh: true
  wait_timeout: 120
  poll_interval: 3

proxy:
  enabled: false
  host: "127.0.0.1"
  port: 7890

sub2api:
  base_url: "https://your-sub2api-domain"
  bearer: ""
  email: "admin@sub2api.local"
  password: "your-sub2api-admin-password"
  auto_upload_sub2api: true
  group_ids: [2]

team_manage:
  base_url: "https://team.joini.cloud"
  api_key: "your_team_manage_api_key"
```

Sub2Api 上传使用后台 `email/password` 登录获取 bearer；`base_url` 建议填写最终 `https://` 地址，避免网关重定向改写 POST。

母号支持使用已保存的 OAuth 三件套单账号导入 Team 管理；导入接口使用 `X-API-Key` 认证，API Key 填写在 `team_manage.api_key`。

代理开关可在 Web 设置中调整；开启后，Codex 登录、邮箱接口和 Sub2Api 上传请求会使用 `http://host:port`。

## 模块概览

- `app.login_sub2api`：导入账号、登录验证、保存 token、上传 Sub2Api 的主编排层。
- `app.codex.runtime`：Codex OAuth 登录和 Sub2Api 上传底层能力。
- `app.email_service`：邮箱服务门面，按 `email.provider` 分发到 worker 或 Outlook。
- `app.outlook_email_service`：Outlook Mail Station 开放接口 provider。
- `app.account_store`：SQLite 账号仓储与登录/Sub2Api 状态字段。
- `app.web_server`：Web 控制台与 API。

## 状态字段

- 登录状态：`loginState/loginStatus`，可取 `pending/success/failed/disabled`。
- Sub2Api 状态：`sub2apiState`，可取 `pending/success/failed/disabled`。
- token 输出目录：`output_tokens/`。
- 账号数据库：`data/accounts.db`。

## 文档

- Outlook 集成说明：`docs/API_INTEGRATION.md`
- Sub2Api 参考：`docs/integration/admin_payment_integration_api.md`

## 注意事项

1. 请勿提交 `config.yaml`、真实 API Key、账号密码或 token。
2. Outlook 开放接口当前用于收件和验证码提取；发信能力未在开放接口中提供时会明确返回不支持。
3. 历史注册/激活模块未在本阶段删除，但 Web 主入口不再调用。
4. 本项目仅供技术学习与研究使用，请遵守相关服务条款。
