# 系统性重构计划：登录到 Sub2Api 核心流程与 Outlook 邮箱分支

## 1. 背景与当前项目判断

当前项目仍以“ChatGPT 账号自动注册 + 邮箱验证码 + Plus 激活 + Sub2Api 上传”为主线，同时已经存在一部分“Codex 账密直登并上传 Sub2Api”的能力：

- `codex_login_tool.py` 是命令行直登入口。
- `app/codex/_runtime_impl.py` 已包含 `perform_http_oauth_login`、`run_codex_login`、`upload_to_sub2api` 等核心能力。
- `app/account_actions.py` 已支持手动新增账号、复用或重新获取 OAuth token 后上传 Sub2Api。
- `app/email_service.py` 当前主要对接现有邮箱 Worker，并提供收件、发件、验证码提取等能力。
- `app/web_server.py` 与 `app/static/*` 当前 Web 控制台仍保留大量注册、Plus 激活、发货等旧业务表达。
- `docs/API_INTEGRATION.md` 当前已经是 Outlook Mail Station API 文档雏形，但需要与本项目代码分支、配置和用法统一。

本次重构目标是把主业务从“注册激活”切换为“手动导入账密 → 登录验证 → 获取 OAuth token → 上传到 Sub2Api → 记录状态”的完整流程，并在邮箱模块中新增 Outlook 邮箱集成分支。

## 2. 目标流程

### 2.1 新核心流程

1. 用户手动导入账号密码。
2. 系统记录账号为待登录验证状态。
3. 执行登录验证：
   - 读取账号邮箱、密码、邮箱接码上下文或 Outlook 邮箱配置。
   - 调用现有 Codex OAuth 登录能力。
   - 自动或手动处理 OTP。
   - 获取 OAuth 三件套。
4. 本地保存 token payload（可配置）。
5. 上传账号 OAuth token 到 Sub2Api。
6. 写回账号状态：登录成功/失败、token 状态、Sub2Api 上传状态、错误信息、更新时间。
7. Web 控制台与 CLI 均围绕该流程展示和触发。

### 2.2 Outlook 邮箱分支流程

1. 配置 Outlook Mail Station 相关参数。
2. 邮箱服务根据配置选择 provider：
   - `worker`：沿用现有 Worker 邮箱逻辑。
   - `outlook`：走新增 Outlook Mail Station 分支。
3. Outlook 分支支持：
   - 随机消费/领取邮箱。
   - 拉取最新邮件。
   - 拉取邮件列表。
   - 获取有效邮件并提取验证码。
   - 发送邮件（如远端 API 支持；否则给出明确失败结果和文档说明）。
4. Codex OTP 自动模式复用统一邮箱接口，不直接关心底层 provider。

## 3. 方案对比与选型

### 方案 A：保留旧注册代码但从入口和 UI 中移除旧流程调用

优点：
- 改动风险较低。
- 可快速切换主流程。
- 旧模块可短期作为回滚参考。

缺点：
- 代码库仍残留注册、Plus 激活等历史模块。
- 长期维护成本较高。

### 方案 B：物理删除注册激活模块并全面改名重构

优点：
- 代码更干净，业务边界更清晰。
- 减少误调用旧流程的可能。

缺点：
- 涉及删除文件和大量引用调整，风险更高。
- 需要更完整的回归验证。
- 用户个人规则要求删除文件必须先获批准。

### 方案 C：分阶段重构：先主流程切换，再清理旧模块

优点：
- 兼顾稳定性与最终目标。
- 第一阶段优先完成可运行核心链路。
- 第二阶段再删除或归档旧模块，避免一次性大规模破坏。

缺点：
- 第一阶段后仍会短暂保留部分旧文件。

### 推荐方案

采用方案 C。

本计划中的执行顺序为：
1. 先完成业务入口、状态模型、配置、邮箱 provider、文档和测试脚本的主流程切换。
2. 删除或彻底移除旧注册激活模块引用前，按本计划列明范围执行；如需要物理删除文件，将以计划批准作为执行依据，不做额外无关删除。
3. 对高风险旧模块优先从入口/UI/调度中解绑，再视引用情况删除或保留为内部未使用兼容模块。

## 4. 具体实施步骤

### 4.1 梳理并隔离旧注册激活入口

涉及文件：
- `main.py`
- `app/register.py`
- `app/browser/signup.py`
- `app/plus_activation_api.py`
- `app/plus_binding.py`
- `app/web_server.py`
- `app/static/index.html`
- `app/static/script.js`
- `app/static/style.css`
- `README.md`

执行内容：
1. 将 Web 控制台“启动注册任务”的语义调整为“批量登录并上传任务”。
2. 将 `worker_thread` 从调用 `register_one_account` 改为调用新的登录上传编排函数。
3. 账号列表过滤和状态展示从 `registration/plus` 主导调整为 `login/sub2api` 主导。
4. 手动新增账号改为“导入账密”，弱化或移除 accessToken 直填作为主流程入口。
5. 从 UI 上移除或隐藏 Plus 激活、Team 激活、继续注册、重试 Plus 等旧操作。
6. 后端保留必要兼容函数时，确保新主流程不会再调用旧注册激活链路。
7. 检查并清理 README、配置模板中“批量注册、Plus 激活”的默认描述。

### 4.2 建立登录到 Sub2Api 的业务编排层

建议新增或改造模块：
- 优先新增 `app/login_sub2api.py` 作为新主流程编排层。
- 复用 `app/codex/runtime.py` 已导出的能力。
- 复用 `app/account_actions.py` 中已有账号状态写回逻辑，必要时抽取通用函数。

执行内容：
1. 定义登录上传结果结构，例如：
   - `success`
   - `email`
   - `login_success`
   - `uploaded`
   - `stage`
   - `message`
   - `output_file`
   - `tokens`
2. 新增单账号流程函数：
   - 输入账号记录或邮箱密码。
   - 加载运行配置。
   - 调用 `perform_http_oauth_login` 获取 token。
   - 调用 `save_token_payload` 保存 token。
   - 调用 `upload_to_sub2api` 上传。
   - 更新账号仓储状态。
3. 新增批量流程函数：
   - 查询待处理账号。
   - 串行执行登录上传。
   - 支持停止信号、日志输出和成功失败计数。
4. 保持最小改动原则，不重写 Codex OAuth 细节，只做业务编排封装。
5. 新增函数按用户规则添加 JSDoc 风格注释，署名 `AI by zb`。

### 4.3 调整账号数据模型与仓储状态

涉及文件：
- `app/account_store.py`
- `app/utils.py`
- `app/account_actions.py`

执行内容：
1. 在账号默认结构中新增或标准化字段：
   - `loginStatus`: `pending/success/failed`
   - `loginState`: `pending/success/failed/disabled`
   - `loginMessage`
   - `loginVerifiedAt`
   - `sub2apiState`
   - `sub2apiStatus`
   - `sub2apiMessage`
   - `sub2apiUploadedAt`
2. 保留旧字段兼容读取，但新流程写入以登录和 Sub2Api 字段为准。
3. 更新状态推断函数，避免继续依赖“注册成功/Plus 成功”判断整体状态。
4. 手动导入账号默认状态改为：
   - 登录：待验证。
   - Sub2Api：待上传或未启用。
   - 总状态：处理中。
5. 对旧数据库记录做兼容：读取时自动补齐新字段，不主动迁移数据库结构以降低风险。

### 4.4 改造 Web API

涉及文件：
- `app/web_server.py`

执行内容：
1. 新增或替换接口：
   - `POST /api/accounts/import`：导入单个账号密码。
   - `POST /api/accounts/login-sub2api`：对单个账号执行登录上传。
   - `POST /api/accounts/batch-login-sub2api` 或复用 `/api/start`：启动批量登录上传。
2. 对现有接口做兼容处理：
   - `/api/accounts/create` 可临时保留，但内部转为导入账密逻辑。
   - `/api/accounts/upload-sub2api` 改为优先执行完整登录到 Sub2Api，而不是仅上传已有 token。
3. 移除或禁用旧接口入口：
   - retry-registration
   - retry-plus
   - retry-team
   - refresh-activation
   - cancel-activation
4. 统一错误响应结构：
   - `error`
   - `stage`
   - `message`
5. 保留现有日志捕获机制，但日志内容改为登录上传流程。

### 4.5 改造前端控制台

涉及文件：
- `app/static/index.html`
- `app/static/script.js`
- `app/static/style.css`

执行内容：
1. 侧边栏“注册数量”调整为“处理数量”或“待处理账号数”。
2. “启动任务”调整为“启动登录上传”。
3. “自动流程”中移除 Plus 激活开关，保留 Sub2Api 自动上传和分组配置。
4. 账号管理页：
   - “手动新增账号”改为“导入账号”。
   - 表格列调整为：邮箱、密码、登录状态、Sub2Api 状态、时间、操作。
   - 筛选项调整为登录状态、Sub2Api 状态、总状态。
5. 操作菜单调整为：
   - 登录并上传。
   - 仅上传已有 token（如仍有 token）。
   - 删除。
   - 复制账号/密码。
6. 移除或隐藏 Plus/Team/继续注册/发货等非核心操作入口。
7. 保持现有 Vue + Ant Design Vue 写法，不引入新前端依赖。

### 4.6 增加 Outlook 邮箱配置

涉及文件：
- `app/config.py`
- `config.example.yaml`
- `README.md`

执行内容：
1. 在配置数据类中新增 Outlook 配置：
   - `email.provider`: `worker` 或 `outlook`
   - `outlook.base_url`
   - `outlook.api_key`
   - `outlook.site_code`
   - `outlook.batch_code`
   - `outlook.domain`
   - `outlook.refresh`
   - `outlook.poll_interval`
   - `outlook.wait_timeout`
2. 解析 YAML 时提供默认值。
3. 导出兼容常量，方便邮箱模块使用。
4. `config.example.yaml` 补充 Outlook 示例配置，但不写入真实密钥。
5. README 更新配置说明和运行说明。

### 4.7 实现 Outlook 邮箱服务模块

建议新增文件：
- `app/outlook_email_service.py`

执行内容：
1. 封装 Outlook Mail Station API 客户端：
   - 统一 headers：`X-API-Key` 或 `Authorization: Bearer`。
   - 统一请求超时、错误解析、日志输出。
2. 实现领取邮箱：
   - `POST /api/open/random-email`
   - 返回邮箱地址和兼容上下文，例如 `outlook::demo@outlook.com`。
3. 实现收件：
   - `GET /api/open/mailboxes/{email}/latest`
   - `GET /api/open/mailboxes/{email}/messages`
   - 标准化为项目现有邮件字段结构。
4. 实现邮件详情和有效邮件过滤：
   - 复用验证码提取逻辑。
   - 支持 since marker。
   - inbox 默认覆盖 inbox + junk 的远端行为。
5. 实现发送邮件：
   - 若 API 文档中确认有发送接口，则对接对应接口。
   - 若当前 API 不提供发送接口，则函数返回明确失败结果：`Outlook API 未提供发送接口`，并在文档写清楚能力边界。
6. 添加必要日志与错误处理，避免吞掉 HTTP 错误、JSON 解析错误和配置缺失错误。

### 4.8 统一邮箱服务门面

涉及文件：
- `app/email_service.py`
- `app/codex/otp.py`
- `scripts/manual/email_service_manual_test.py`

执行内容：
1. 在 `email_service.py` 中增加 provider 分发：
   - `worker` 走现有逻辑。
   - `outlook` 走 `outlook_email_service.py`。
2. 保持现有对外函数签名尽量不变：
   - `create_temp_email`
   - `fetch_emails`
   - `fetch_valid_emails`
   - `get_email_detail`
   - `send_single_email`
3. 更新 `app/codex/otp.py`，确保自动 OTP 能识别 `outlook::` 上下文。
4. 更新手工测试脚本，支持：
   - `--provider worker|outlook`
   - 创建/领取邮箱。
   - 拉取邮件。
   - 等待验证码。
   - 测试发送邮件。

### 4.9 更新 API_INTEGRATION.md

涉及文件：
- `docs/API_INTEGRATION.md`

执行内容：
1. 重写文档结构，使其覆盖：
   - Outlook 分支用途。
   - 配置项说明。
   - 认证方式。
   - 接口规范。
   - 请求/响应示例。
   - 项目内函数映射关系。
   - 错误处理与日志说明。
   - 使用示例。
   - 测试方法。
2. 明确 Outlook 邮箱 API 能力边界：
   - 收件支持。
   - 发送是否支持取决于 API 实际接口。
3. 保留当前文档中已有开放接口内容，但按项目集成视角重新整理。

### 4.10 测试用例与手工验证脚本

建议新增或改造：
- `scripts/manual/codex_login_manual_test.py`
- `scripts/manual/email_service_manual_test.py`
- 可新增 `scripts/manual/login_sub2api_manual_test.py`

执行内容：
1. 登录到 Sub2Api 手工测试：
   - 使用指定邮箱密码。
   - 支持 `--otp-mode auto|manual`。
   - 支持 `--skip-upload`。
   - 输出结构化 JSON 结果。
2. Outlook 邮箱手工测试：
   - 领取邮箱。
   - 拉取最新邮件。
   - 拉取邮件列表。
   - 等待验证码。
   - 发送邮件能力探测。
3. Web API 轻量验证：
   - 导入账号。
   - 单账号登录上传。
   - 查询状态。
4. 不新增外部测试依赖，优先使用项目当前 Python 标准库和已有依赖。

### 4.11 文档与使用说明更新

涉及文件：
- `README.md`
- `config.example.yaml`
- `docs/API_INTEGRATION.md`

执行内容：
1. README 标题和介绍从“账号自动注册工具”调整为“账号登录验证与 Sub2Api 上传工具”。
2. 快速开始改为：
   - 安装依赖。
   - 配置 Sub2Api。
   - 配置邮箱 provider。
   - 导入账号。
   - 启动登录上传。
3. 删除或降级注册、Plus 激活说明。
4. 补充 Outlook 分支使用说明。
5. 补充手工测试命令。

## 5. 旧模块处理策略

### 5.1 优先解绑

先从入口和 UI 中解绑以下旧流程：
- 自动注册。
- Plus 激活。
- Team 激活。
- 浏览器注册画面监控。
- 注册重试。

### 5.2 再清理文件

实施时会先检查引用。如果确认无引用，将删除或停用以下模块：
- `app/register.py`
- `app/browser/signup.py`
- `app/plus_activation_api.py`
- `app/plus_binding.py`
- 与注册激活强绑定的 Web API 和前端操作。

考虑到删除文件属于高风险操作，执行阶段会严格按本计划范围处理，不删除与新流程仍存在引用关系的模块。

## 6. 风险与控制措施

1. Codex 登录接口可能受远端登录风控、验证码、OTP 策略影响。
   - 控制：保留 `otp-mode manual`，失败时写明阶段和原因。
2. Outlook API 文档可能不包含发送接口。
   - 控制：收件能力完整实现；发送能力按接口真实能力实现或明确返回不支持。
3. 旧数据库状态字段与新字段共存。
   - 控制：读取时兼容补齐，不做破坏性迁移。
4. Web 前端改动较多。
   - 控制：保持现有 Vue/AntD 架构，不引入依赖，不重写整体样式系统。
5. 旧模块删除可能造成隐性引用断裂。
   - 控制：先解绑入口，再使用检索确认引用，最后删除或保留未使用兼容模块。

## 7. 验证计划

1. 静态检查：
   - `uv run python -m compileall app scripts`
2. 关键命令验证：
   - `uv run codex_login_tool.py --email test@example.com --password test-password --otp-mode manual --skip-upload`
   - `uv run python scripts/manual/email_service_manual_test.py create`
   - `uv run python scripts/manual/email_service_manual_test.py fetch --email demo@outlook.com`
3. Web 服务轻量验证：
   - 启动 `uv run server.py`。
   - 打开控制台。
   - 导入账号。
   - 触发单账号登录上传。
   - 查询账号状态。
4. 若项目存在 lint/type-check 命令则执行；当前 `pyproject.toml` 暂未发现专用 lint/type-check 脚本，优先执行 Python 编译检查和手工脚本验证。

## 8. 预期交付物

1. 登录到 Sub2Api 的新核心业务流程。
2. 手动导入账密与登录验证机制。
3. Outlook 邮箱 provider 分支。
4. Outlook 邮件接收和发送能力模块，发送能力按 API 实际支持情况实现或明确标注不支持。
5. Web 控制台调整为登录上传流程。
6. `docs/API_INTEGRATION.md` 完整集成文档。
7. 更新后的 `README.md` 与 `config.example.yaml`。
8. 手工测试脚本与验证说明。
9. 编译检查通过，关键流程具备可执行验证路径。
