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

## 注意事项

1. 不要把 `/data/gpt-auto-register/config.yaml`、数据库、token 目录提交到代码仓库。
2. 账号登录链路依赖 Chromium，容器已内置浏览器和虚拟显示环境。
3. 如果部署机访问 Google 驱动源不稳定，Compose 已挂载 chromedriver 与 selenium 缓存卷，后续启动会复用缓存。
4. 若使用代理，按 `config.yaml` 中的 `proxy` 配置填写；该代理仅用于 Codex OAuth 登录链路。
