# Outlook Mail Station 集成说明

本文档说明本项目如何把 Outlook Mail Station 开放接口接入“导入账密 → Codex 登录验证 → Sub2Api 上传”流程。

## 项目内用途

- `email.provider=worker`：沿用现有 Cloudflare Worker 邮箱服务。
- `email.provider=outlook`：使用 `app.outlook_email_service` 调用 Outlook Mail Station 开放接口。
- Codex 自动 OTP 只依赖 `app.email_service` 门面，不直接关心底层 provider。

## 配置

```yaml
email:
  provider: "outlook"

outlook:
  base_url: "https://your-outlook-mail-station-domain"
  api_key: "your_open_api_key"
  auth_type: "api_key"   # api_key 或 bearer
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
```

认证头支持两种方式：

```http
X-API-Key: user-owned-api-key
Authorization: Bearer user-owned-api-key
```

开启 `proxy.enabled` 后，Outlook 开放接口、Codex 登录请求和 Sub2Api 上传都会走 `http://host:port`。

## 开放接口映射

| 项目函数 | Outlook 接口 | 说明 |
| --- | --- | --- |
| `create_temp_email()` | `POST /api/open/random-email` | 随机领取邮箱，返回 `outlook::email` 上下文 |
| `fetch_emails(context)` | `GET /api/open/mailboxes/{email}/messages` | 拉取 inbox，远端按 inbox + junk 返回 |
| `fetch_valid_emails(context, since_marker)` | 同上 | 按时间标记过滤并提取验证码 |
| `get_email_detail(context, id)` | `GET /api/open/mailboxes/{email}/messages/{id}` | 若远端未提供该接口则返回空 |
| `send_single_email(...)` | 无开放接口 | 明确返回 `Outlook API 未提供发送接口` |

## 请求示例

随机领取邮箱：

```bash
curl -X POST "https://mail.example.com/api/open/random-email" \
  -H "X-API-Key: user-owned-api-key" \
  -H "Content-Type: application/json" \
  -d "{\"site_code\":\"OPENAI\",\"domain\":\"outlook.com\",\"batch_code\":\"batch-20260405\"}"
```

拉取邮件列表：

```bash
curl "https://mail.example.com/api/open/mailboxes/demo@outlook.com/messages?refresh=true&folder=inbox" \
  -H "X-API-Key: user-owned-api-key"
```

获取最新邮件：

```bash
curl "https://mail.example.com/api/open/mailboxes/demo@outlook.com/latest?refresh=true" \
  -H "X-API-Key: user-owned-api-key"
```

## 响应兼容

Outlook provider 会把远端邮件字段标准化为项目现有结构：

- `sender_email` → `sender/from/source`
- `body_text` → `content/text`
- `body_html` → `html/html_content`
- `sent_at` → `received_at/created_at/received_marker`
- `subject/body/preview` 中的 6 位数字会写入 `verification_code`

## 手工测试

```bash
uv run python scripts/manual/email_service_manual_test.py create --provider outlook
uv run python scripts/manual/email_service_manual_test.py fetch --provider outlook --email demo@outlook.com
uv run python scripts/manual/login_sub2api_manual_test.py login --email your@example.com --otp-mode auto
```

## 常见错误

- 未配置 `outlook.base_url`：请求不会发出，日志提示配置缺失。
- 未配置 `outlook.api_key`：请求不会发出，日志提示 API Key 缺失。
- 邮箱不在当前 API Key 用户池：远端通常返回 `邮箱不存在或不属于当前用户池`。
- 无可分配邮箱：远端通常返回 `目标用户池中没有可分配给当前站点的邮箱`。
- 发信：开放接口未提供发信能力，本项目不会伪造成功结果。
