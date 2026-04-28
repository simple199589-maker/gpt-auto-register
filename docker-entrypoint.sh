#!/usr/bin/env sh
set -eu

RUNTIME_DIR="${APP_RUNTIME_DIR:-/data}"

mkdir -p "$RUNTIME_DIR/data" "$RUNTIME_DIR/output_tokens"

if [ ! -f "$RUNTIME_DIR/config.yaml" ]; then
    cp /app/config.example.yaml "$RUNTIME_DIR/config.yaml"
fi

touch "$RUNTIME_DIR/registered_accounts.txt"

# 创建运行目录软链，保护已有非空路径不被覆盖。AI by zb
ensure_runtime_link() {
    target_path="$1"
    link_path="$2"

    if [ -L "$link_path" ]; then
        rm "$link_path"
    elif [ -d "$link_path" ]; then
        if [ "$(find "$link_path" -mindepth 1 -maxdepth 1 | wc -l)" -gt 0 ]; then
            echo "启动失败: $link_path 已存在且非空，无法替换为挂载目录软链" >&2
            exit 1
        fi
        rmdir "$link_path"
    elif [ -e "$link_path" ]; then
        echo "启动失败: $link_path 已存在，无法替换为挂载目录软链" >&2
        exit 1
    fi

    ln -s "$target_path" "$link_path"
}

ensure_runtime_link "$RUNTIME_DIR/config.yaml" /app/config.yaml
ensure_runtime_link "$RUNTIME_DIR/data" /app/data
ensure_runtime_link "$RUNTIME_DIR/output_tokens" /app/output_tokens
ensure_runtime_link "$RUNTIME_DIR/registered_accounts.txt" /app/registered_accounts.txt

if command -v Xvfb >/dev/null 2>&1 && [ -z "${DISPLAY:-}" ]; then
    export DISPLAY="${XVFB_DISPLAY:-:99}"
    Xvfb "$DISPLAY" -screen 0 "${XVFB_SCREEN:-1920x1080x24}" -nolisten tcp >/tmp/xvfb.log 2>&1 &
fi

exec "$@"
