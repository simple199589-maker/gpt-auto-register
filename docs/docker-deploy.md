# Docker 部署说明

## 部署目标

本项目支持通过 Docker Compose 直接部署 Web 控制台。镜像内包含 Python 运行环境、项目依赖、Chromium、chromedriver 和 Xvfb。

## 目录挂载

容器内统一使用 `/data` 作为运行数据目录。

默认宿主机目录：

```text
/data/gpt-auto-register
```

默认挂载关系：

```text
/data/gpt-auto-register:/data
```

运行后会生成或使用以下文件：

- `/data/gpt-auto-register/config.yaml`：运行配置。
- `/data/gpt-auto-register/data/accounts.db`：账号数据库。
- `/data/gpt-auto-register/output_tokens/`：OAuth token 输出目录。
- `/data/gpt-auto-register/registered_accounts.txt`：历史账号文件。

## 拉取项目

服务器上建议把项目代码放到 `/opt/gpt-auto-register`，运行数据放到 `/data/gpt-auto-register`。

创建目录：

```bash
sudo mkdir -p /opt/gpt-auto-register /data/gpt-auto-register
sudo chown -R "$USER:$USER" /opt/gpt-auto-register /data/gpt-auto-register
```

拉取当前部署分支 `auth`：

```bash
git clone --branch auth --single-branch https://github.com/simple199589-maker/gpt-auto-register.git /opt/gpt-auto-register
cd /opt/gpt-auto-register
```

如果目录已经存在且为空，也可以这样拉取到当前目录：

```bash
cd /opt/gpt-auto-register
git clone --branch auth --single-branch https://github.com/simple199589-maker/gpt-auto-register.git .
```

## 构建与启动

在项目根目录执行：

```bash
docker compose build
docker compose up -d
```

默认访问地址：

```text
http://localhost:5005
```

## 首次配置

首次启动会自动从 `config.example.yaml` 生成：

```text
/data/gpt-auto-register/config.yaml
```

编辑该文件，填写邮箱、Sub2Api、Team 管理、代理等配置后重启：

其中 Web 控制台管理密码配置如下，部署前请改掉默认值：

```yaml
web:
  admin_password: "your-admin-password"
```

```bash
docker compose restart
```

## 修改端口

默认宿主机端口为 `5005`。如需改为 `5010`：

```bash
APP_PORT=5010 docker compose up -d
```

访问：

```text
http://localhost:5010
```

## 修改数据目录

默认数据目录为 `/data/gpt-auto-register`。如需改为其他宿主机目录：

```bash
DATA_DIR=/data/another-dir docker compose up -d
```

## 常用运维命令

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f
```

重启服务：

```bash
docker compose restart
```

停止服务：

```bash
docker compose down
```

更新部署：

```bash
docker compose build
docker compose up -d
```

## 生产更新方案

线上已经通过 Docker Compose 部署时，推荐按以下流程更新。该流程会保留 `/data/gpt-auto-register` 中的配置、数据库和 token，只重建并替换应用容器。

### 1. 确认部署目录和环境变量

默认部署目录为：

```bash
cd /opt/gpt-auto-register
```

如果生产环境自定义过端口或数据目录，建议在项目根目录维护 `.env`，避免更新时漏带变量：

```bash
APP_PORT=5005
DATA_DIR=/data/gpt-auto-register
```

执行前先确认当前容器状态：

```bash
docker compose ps
docker compose logs --tail=100
```

### 2. 更新前备份运行数据

至少备份运行配置、账号数据库、token 输出目录和历史账号文件：

```bash
cd /opt/gpt-auto-register
export DATA_DIR="${DATA_DIR:-/data/gpt-auto-register}"
export BACKUP_ROOT="/data/backups/gpt-auto-register/$(date +%Y%m%d-%H%M%S)"

sudo mkdir -p "$BACKUP_ROOT"
sudo tar -C "$(dirname "$DATA_DIR")" -czf "$BACKUP_ROOT/runtime-data.tgz" "$(basename "$DATA_DIR")"
git rev-parse HEAD | sudo tee "$BACKUP_ROOT/previous_commit.txt" >/dev/null
docker compose images | sudo tee "$BACKUP_ROOT/compose-images.txt" >/dev/null
```

如果更新后需要回滚，`previous_commit.txt` 用于恢复代码版本，`runtime-data.tgz` 用于必要时恢复运行数据。

### 3. 拉取最新代码

当前生产部署分支为 `auth`：

```bash
cd /opt/gpt-auto-register
git status --short
git fetch origin auth
git pull --ff-only origin auth
```

如果 `git status --short` 有本地改动，先确认这些改动是否为生产临时修改；不要直接覆盖配置、数据库或 token 文件。

### 4. 重建镜像并替换容器

构建镜像不会停止当前容器，真正短暂停服发生在 `up -d` 重新创建容器时：

```bash
docker compose build --pull
docker compose up -d --remove-orphans
```

不要执行 `docker compose down -v`，否则会删除 Compose 管理的命名卷缓存。

### 5. 更新后检查

确认容器健康状态和 Web 控制台可访问：

```bash
docker compose ps
docker compose logs -f --tail=100
curl -fsS "http://127.0.0.1:${APP_PORT:-5005}/" >/dev/null && echo "web ok"
```

重点检查：

- Web 登录页能打开，管理密码仍使用 `/data/gpt-auto-register/config.yaml` 中的配置。
- 账号列表、登录状态、Sub2Api 状态能正常读取。
- 新发起的登录上传任务能正常启动。

### 6. 回滚方案

如果更新后应用不可用，先回滚代码和镜像：

```bash
cd /opt/gpt-auto-register
export BACKUP_ROOT="/data/backups/gpt-auto-register/需要回滚的备份目录"
git checkout "$(cat "$BACKUP_ROOT/previous_commit.txt")"
docker compose build
docker compose up -d --remove-orphans
docker compose ps
```

仅当确认运行数据被错误修改或迁移失败时，再恢复数据备份。该操作会覆盖当前 `/data/gpt-auto-register`：

```bash
export DATA_DIR="${DATA_DIR:-/data/gpt-auto-register}"
export RESTORE_STASH="${DATA_DIR}.before-rollback-$(date +%Y%m%d-%H%M%S)"
docker compose down
sudo mv "$DATA_DIR" "$RESTORE_STASH"
sudo mkdir -p "$(dirname "$DATA_DIR")"
sudo tar -C "$(dirname "$DATA_DIR")" -xzf "$BACKUP_ROOT/runtime-data.tgz"
docker compose up -d
```

恢复完成后重新执行健康检查。确认无误后，再手动清理 `$RESTORE_STASH`。

## 注意事项

1. 不要把 `/data/gpt-auto-register/config.yaml`、数据库、token 目录提交到代码仓库。
2. 账号登录链路依赖 Chromium，容器已内置浏览器和虚拟显示环境。
3. 如果部署机访问 Google 驱动源不稳定，Compose 已挂载 chromedriver 与 selenium 缓存卷，后续启动会复用缓存。
4. 若使用代理，按 `config.yaml` 中的 `proxy` 配置填写；该代理仅用于 Codex OAuth 登录链路。
