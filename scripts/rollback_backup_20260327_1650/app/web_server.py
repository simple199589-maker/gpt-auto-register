import logging
import threading
import time
import builtins
import os
import random
from datetime import datetime
from pathlib import Path
from flask import Flask, Response, jsonify, request

# 导入业务逻辑
import app.register as main
import app.browser as browser
import app.browser._legacy as browser_impl
import app.email_service as email_service
import app.plus_activation_api as plus_activation_api
import app.plus_binding as plus_binding
import app.account_actions as account_actions
from app.config import cfg
from app.utils import load_account_records, parse_account_record, sanitize_account_record_for_web

STATIC_DIR = Path(__file__).resolve().with_name("static")

app = Flask(__name__, static_url_path="", static_folder=str(STATIC_DIR))

# ==========================================
# 🔧 状态管理与日志捕获
# ==========================================

# ==========================================
# 🔧 状态管理与日志捕获
# ==========================================

# 全局状态
class AppState:
    def __init__(self):
        self.is_running = False
        self.stop_requested = False
        self.success_count = 0
        self.fail_count = 0
        self.current_action = "等待启动"
        self.logs = []
        self.lock = threading.Lock()
        
        # MJPEG 流缓冲区
        self.last_frame = None
        self.frame_version = 0
        self.frame_lock = threading.Lock()

    def add_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.logs.append(f"[{timestamp}] {message}")
            if len(self.logs) > 1000:
                self.logs.pop(0)

    def get_logs(self, start_index=0):
        with self.lock:
            return list(self.logs[start_index:])
            
    def update_frame(self, frame_bytes):
        with self.frame_lock:
            self.last_frame = frame_bytes
            self.frame_version += 1

    def clear_frame(self):
        with self.frame_lock:
            self.last_frame = None
            self.frame_version = 0
            
    def get_frame(self):
        with self.frame_lock:
            return self.last_frame

    def get_frame_snapshot(self):
        """
        获取当前最新画面及其版本号。

        返回:
            tuple[bytes | None, int]: 当前画面与版本号
            AI by zb
        """
        with self.frame_lock:
            return self.last_frame, self.frame_version

    def get_frame_version(self):
        with self.frame_lock:
            return self.frame_version

state = AppState()


def capture_driver_frame(driver):
    """
    从当前浏览器会话抓取一帧画面。

    参数:
        driver: Selenium WebDriver
    返回:
        bytes | None: PNG 二进制内容
        AI by zb
    """
    try:
        return driver.get_screenshot_as_png()
    except Exception:
        return None


def build_monitor_callback(allow_stop: bool = False):
    """
    创建浏览器监控回调，统一处理停止信号与实时画面采集。

    参数:
        allow_stop: 是否响应批量任务停止请求
    返回:
        callable: 监控回调函数
        AI by zb
    """
    def monitor(driver, step):
        if allow_stop and state.stop_requested and step != "driver_closing":
            main.print("🛑 检测到停止请求，正在中断任务...")
            raise InterruptedError("用户请求停止")

        if not driver:
            return

        if step == "driver_ready":
            browser_impl.attach_monitor_callback(driver, monitor)
            frame_bytes = capture_driver_frame(driver)
            if frame_bytes:
                state.update_frame(frame_bytes)
            return

        if step == "driver_closing":
            browser_impl.detach_monitor_callback(driver)
            return

        last_step = getattr(driver, "_zb_monitor_last_step", "")
        last_capture_at = float(getattr(driver, "_zb_monitor_last_capture_at", 0.0) or 0.0)
        now = time.monotonic()
        debounce_seconds = max(float(cfg.browser.preview_interval_ms or 300) / 1000.0, 0.1)
        if step == last_step and now - last_capture_at < debounce_seconds:
            return

        frame_bytes = capture_driver_frame(driver)
        if frame_bytes:
            state.update_frame(frame_bytes)
            driver._zb_monitor_last_step = step
            driver._zb_monitor_last_capture_at = now

    return monitor

# Hack: 劫持 print 函数以捕获日志
original_print = builtins.print
def hooked_print(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    msg = sep.join(map(str, args))
    state.add_log(msg)
    original_print(*args, **kwargs)

# 应用劫持
main.print = hooked_print
browser.print = hooked_print
browser_impl.print = hooked_print
email_service.print = hooked_print
plus_activation_api.print = hooked_print
plus_binding.print = hooked_print
account_actions.print = hooked_print

# ==========================================
# 🧵 后台工作线程
# ==========================================
def worker_thread(count):
    state.is_running = True
    state.stop_requested = False
    state.success_count = 0
    state.fail_count = 0
    state.current_action = f"🚀 任务启动，目标: {count}"
    
    # 清空上一轮的画面，避免显示残留
    state.clear_frame()
    
    main.print(f"🚀 开始批量任务，计划注册: {count} 个")
    
    try:
        monitor = build_monitor_callback(allow_stop=True)

        for i in range(count):
            if state.stop_requested:
                main.print("🛑 用户停止了任务")
                break
            
            state.current_action = f"正在注册 ({i+1}/{count})..."
            
            try:
                # 调用核心逻辑，传入回调
                email, password, success = main.register_one_account(monitor_callback=monitor)
                
                if success:
                    state.success_count += 1
                else:
                    state.fail_count += 1
            except InterruptedError:
                main.print("🛑 任务已中断")
                break
            except Exception as e:
                state.fail_count += 1
                main.print(f"❌ 异常: {str(e)}")
            
            # 间隔等待
            if i < count - 1 and not state.stop_requested:
                wait_time = random.randint(cfg.batch.interval_min, cfg.batch.interval_max)
                main.print(f"⏳ 冷却中，等待 {wait_time} 秒...")
                for _ in range(wait_time):
                    if state.stop_requested: break
                    time.sleep(1)
                    
    except Exception as e:
        main.print(f"💥 严重错误: {e}")
    finally:
        state.is_running = False
        state.current_action = "任务已完成"
        main.print("🏁 任务结束")

# ==========================================
# 🌊 MJPEG 流生成器
# ==========================================
def gen_frames():
    """生成流数据的生成器"""
    last_sent_version = -1
    while True:
        frame, frame_version = state.get_frame_snapshot()
        if frame and frame_version != last_sent_version:
            last_sent_version = frame_version
            yield (b'--frame\r\n'
                   b'Content-Type: image/png\r\n\r\n' + frame + b'\r\n')
            continue

        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return app.response_class(gen_frames(),
                              mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/frame')
def latest_frame():
    frame = state.get_frame()
    if not frame:
        return Response(status=204)
    return Response(frame, mimetype='image/png')


def parse_account_line(line):
    """
    解析账号文件单行记录，兼容 JSON、`|` 与 `----` 三种存储格式。
    Author: AI by zb
    """
    record = parse_account_record(line)
    return sanitize_account_record_for_web(record) if record else None


def _run_manual_account_action(action_name, handler):
    """
    统一执行账号手动动作，并更新全局状态提示。
    Author: AI by zb
    """
    if state.is_running:
        return None, (jsonify({"error": "批量任务运行中，请稍后再试"}), 400)

    data = request.json or {}
    email = str(data.get("email") or "").strip()
    if not email:
        return None, (jsonify({"error": "缺少邮箱参数"}), 400)

    previous_action = state.current_action
    state.current_action = f"{action_name}: {email}"
    try:
        result = handler(email)
        return email, result
    finally:
        state.current_action = previous_action if previous_action else "等待启动"

# ==========================================
# 🌐 API 接口
# ==========================================

@app.route('/')
def index():
    return app.send_static_file("index.html")

@app.route('/api/status')
def get_status():
    # 获取库存数
    total_inventory = 0
    if os.path.exists(cfg.files.accounts_file):
        try:
            with open(cfg.files.accounts_file, 'r', encoding='utf-8') as f:
                total_inventory = sum(1 for line in f if parse_account_line(line))
        except:
            pass

    return jsonify({
        "is_running": state.is_running,
        "current_action": state.current_action,
        "success": state.success_count,
        "fail": state.fail_count,
        "total_inventory": total_inventory,
        "sub2api_auto_upload_enabled": bool(cfg.sub2api.auto_upload_sub2api),
        "has_frame": state.get_frame() is not None,
        "frame_version": state.get_frame_version(),
        "logs": state.get_logs(int(request.args.get('log_index', 0)))
    })

@app.route('/api/start', methods=['POST'])
def start_task():
    if state.is_running:
        return jsonify({"error": "Already running"}), 400
    
    data = request.json
    count = data.get('count', 1)
    
    threading.Thread(target=worker_thread, args=(count,), daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/api/stop', methods=['POST'])
def stop_task():
    if not state.is_running:
        return jsonify({"error": "Not running"}), 400
    
    state.stop_requested = True
    return jsonify({"status": "stopping"})

@app.route('/api/accounts')
def get_accounts():
    try:
        accounts = [sanitize_account_record_for_web(item) for item in load_account_records()]
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    # 反转列表，最新的在前
    return jsonify(accounts[::-1])


@app.route('/api/accounts/retry-plus', methods=['POST'])
def retry_account_plus():
    email, maybe_error = _run_manual_account_action(
        "手动重试Plus",
        lambda target_email: account_actions.run_plus_retry_for_account(
            target_email,
            monitor_callback=build_monitor_callback(allow_stop=False),
        ),
    )
    if email is None:
        return maybe_error

    result = maybe_error
    upload_result = None
    latest_account = account_actions.get_account_record(email)
    if (
        result.success
        and account_actions.is_sub2api_auto_upload_enabled()
        and latest_account
        and not bool(latest_account.get("sub2apiUploaded"))
    ):
        upload_result = account_actions.run_sub2api_upload_for_account(email)

    account = account_actions.get_account_record(email)
    return jsonify(
        {
            "success": bool(result.success),
            "message": result.message or ("Plus 调用成功" if result.success else "Plus 调用失败"),
            "plus": {
                "success": result.success,
                "stage": result.stage,
                "status": result.status,
                "message": result.message,
                "requestId": result.request_id,
            },
            "sub2api": {
                "triggered": bool(upload_result is not None),
                "success": bool(upload_result.uploaded) if upload_result else False,
                "message": upload_result.message if upload_result else "",
            },
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )


@app.route('/api/accounts/upload-sub2api', methods=['POST'])
def upload_account_sub2api():
    email, maybe_error = _run_manual_account_action("手动上传Sub2Api", account_actions.run_sub2api_upload_for_account)
    if email is None:
        return maybe_error

    result = maybe_error
    account = account_actions.get_account_record(email)
    return jsonify(
        {
            "success": bool(result.uploaded),
            "message": result.message,
            "stage": result.stage,
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )

if __name__ == '__main__':
    from waitress import serve
    print("🌐 Web Server started at http://localhost:5000")
    # 使用生产级服务器 Waitress
    # threads=6 支持并发：前端页面 + API轮询 + MJPEG流 + 后台任务
    serve(app, host='0.0.0.0', port=5000, threads=6)
