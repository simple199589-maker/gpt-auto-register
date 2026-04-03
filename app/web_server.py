import argparse
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
from app.account_store import count_account_records, query_account_records
from app.config import cfg, select_activation_api_base_url, update_automation_settings
from app.utils import get_account_record, parse_account_record, sanitize_account_record_for_web

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
        self.activation_lock = threading.Lock()
        self.activation_owner = ""
        
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

    def try_acquire_activation(self, owner: str) -> tuple[bool, str]:
        """
        尝试占用整站激活线路。

        参数:
            owner: 当前激活动作标识
        返回:
            tuple[bool, str]: (是否成功，占用中的动作标识)
            AI by zb
        """
        acquired = self.activation_lock.acquire(blocking=False)
        with self.lock:
            if acquired:
                self.activation_owner = owner
                return True, self.activation_owner
            return False, self.activation_owner

    def release_activation(self) -> None:
        """
        释放整站激活线路占用状态。

        返回:
            None
            AI by zb
        """
        with self.lock:
            self.activation_owner = ""
        if self.activation_lock.locked():
            try:
                self.activation_lock.release()
            except RuntimeError:
                pass

    def get_activation_owner(self) -> str:
        """
        获取当前占用激活线路的动作标识。

        返回:
            str: 当前激活动作标识
            AI by zb
        """
        with self.lock:
            return str(self.activation_owner or "")
            
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
        if allow_stop and state.stop_requested:
            main.print("🛑 检测到停止请求，正在中断任务...")
            raise InterruptedError("用户请求停止")

        if not driver:
            return

        frame_bytes = capture_driver_frame(driver)
        if frame_bytes:
            state.update_frame(frame_bytes)

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
    while True:
        frame = state.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/png\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.5)

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


def coerce_bool(value, default: bool) -> bool:
    """
    将接口传入值转换为布尔值。

    参数:
        value: 原始值
        default: 默认值
    返回:
        bool: 解析后的布尔值
        AI by zb
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def build_automation_settings_payload() -> dict:
    """
    生成自动流程开关响应数据。

    返回:
        dict: 开关状态
        AI by zb
    """
    return {
        "plus_auto_activate_enabled": bool(cfg.plus.auto_activate),
        "sub2api_auto_upload_enabled": bool(cfg.sub2api.auto_upload_sub2api),
        "sub2api_group_ids": list(cfg.sub2api.group_ids or [2]),
    }


def is_activation_request_accepted(result) -> bool:
    """
    判断激活动作是否已经成功提交到远端服务。

    参数:
        result: 激活结果对象
    返回:
        bool: 是否已提交成功
        AI by zb
    """
    return bool(getattr(result, "success", False) or getattr(result, "accepted", False))


def build_activation_response_status(result) -> str:
    """
    将激活结果映射为接口层统一状态，便于调用方区分处理中和终态。

    参数:
        result: 激活结果对象
    返回:
        str: `success/processing/cancelled/failed`
        AI by zb
    """
    if getattr(result, "success", False):
        return "success"

    stage = str(getattr(result, "stage", "") or "").strip().lower()
    if stage == "cancelled":
        return "cancelled"
    if is_activation_request_accepted(result):
        return "processing"
    return "failed"


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


def _run_manual_activation_action(action_name, handler):
    """
    统一执行手动激活动作，并串行化整站激活线路。

    参数:
        action_name: 当前动作名称
        handler: 业务处理函数
    返回:
        tuple[str | None, object]: (邮箱, 处理结果或错误响应)
        AI by zb
    """
    if state.is_running:
        return None, (jsonify({"error": "批量任务运行中，请稍后再试"}), 400)

    data = request.json or {}
    email = str(data.get("email") or "").strip()
    if not email:
        return None, (jsonify({"error": "缺少邮箱参数"}), 400)

    owner = f"{action_name}: {email}"
    acquired, busy_owner = state.try_acquire_activation(owner)
    if not acquired:
        busy_text = busy_owner or "当前已有其它 Plus / Team 激活任务在执行"
        return None, (jsonify({"error": f"激活线路忙碌中，请稍后再试：{busy_text}"}), 409)

    previous_action = state.current_action
    state.current_action = owner
    try:
        result = handler(email)
        return email, result
    finally:
        state.current_action = previous_action if previous_action else "等待启动"
        state.release_activation()

# ==========================================
# 🌐 API 接口
# ==========================================

@app.route('/')
def index():
    return app.send_static_file("index.html")

@app.route('/api/status')
def get_status():
    try:
        total_inventory = count_account_records()
    except Exception:
        total_inventory = 0

    return jsonify({
        "is_running": state.is_running,
        "current_action": state.current_action,
        "success": state.success_count,
        "fail": state.fail_count,
        "total_inventory": total_inventory,
        **build_automation_settings_payload(),
        "has_frame": state.get_frame() is not None,
        "frame_version": state.get_frame_version(),
        "logs": state.get_logs(int(request.args.get('log_index', 0)))
    })


@app.route('/api/settings', methods=['GET', 'POST'])
def automation_settings():
    if request.method == 'GET':
        return jsonify(build_automation_settings_payload())

    if state.is_running:
        return jsonify({"error": "任务运行中，请先停止后再修改设置"}), 400

    data = request.json or {}
    plus_auto_activate = coerce_bool(
        data.get("plus_auto_activate_enabled"),
        bool(cfg.plus.auto_activate),
    )
    sub2api_auto_upload = coerce_bool(
        data.get("sub2api_auto_upload_enabled"),
        bool(cfg.sub2api.auto_upload_sub2api),
    )
    raw_group_ids = data.get("sub2api_group_ids")
    if isinstance(raw_group_ids, list):
        sub2api_group_ids = [int(item) for item in raw_group_ids if str(item).strip().lstrip("-").isdigit()]
    else:
        raw_group_text = str(raw_group_ids or "").replace("，", ",")
        sub2api_group_ids = [int(item.strip()) for item in raw_group_text.split(",") if item.strip().lstrip("-").isdigit()]

    update_automation_settings(
        plus_auto_activate=plus_auto_activate,
        sub2api_auto_upload=sub2api_auto_upload,
        sub2api_group_ids=sub2api_group_ids or list(cfg.sub2api.group_ids or [2]),
    )
    return jsonify(
        {
            "success": True,
            "message": "设置已保存",
            **build_automation_settings_payload(),
        }
    )

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
        page = int(request.args.get('page', 1) or 1)
        page_size = int(request.args.get('page_size', 10) or 10)
        query_result = query_account_records(
            keyword=str(request.args.get('keyword') or '').strip(),
            registration_status=str(request.args.get('registration_status') or '').strip(),
            overall_status=str(request.args.get('overall_status') or '').strip(),
            plus_status=str(request.args.get('plus_status') or '').strip(),
            sub2api_status=str(request.args.get('sub2api_status') or '').strip(),
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(
        {
            "items": [sanitize_account_record_for_web(item) for item in query_result["items"]],
            "pagination": query_result["pagination"],
        }
    )


@app.route('/api/accounts/create', methods=['POST'])
def create_account_manually():
    """
    手动新增账号记录接口。

    返回:
        Response: JSON 响应
        AI by zb
    """
    if state.is_running:
        return jsonify({"error": "批量任务运行中，请稍后再试"}), 400

    data = request.json or {}
    email = str(data.get("email") or "").strip()
    password = str(data.get("password") or "").strip()
    access_token = str(data.get("accessToken") or "").strip()

    previous_action = state.current_action
    state.current_action = f"手动新增账号: {email or '未命名'}"
    try:
        account = account_actions.run_manual_account_create(
            email=email,
            password=password,
            access_token=access_token,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        state.current_action = previous_action if previous_action else "等待启动"

    return jsonify(
        {
            "success": True,
            "message": "账号已添加",
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )


@app.route('/api/accounts/deliver', methods=['POST'])
def deliver_account():
    """
    向当前发货邮箱发送账号密码，并生成临时访问链接。

    返回:
        Response: JSON 响应
        AI by zb
    """
    if state.is_running:
        return jsonify({"error": "批量任务运行中，请稍后再试"}), 400

    data = request.json or {}
    email = str(data.get("email") or "").strip()
    vendor = str(data.get("vendor") or "").strip() or "咸鱼"
    if not email:
        return jsonify({"error": "缺少邮箱参数"}), 400

    previous_action = state.current_action
    state.current_action = f"发货账号: {email}"
    try:
        result = account_actions.run_delivery_for_account(
            email=email,
            vendor=vendor,
        )
    finally:
        state.current_action = previous_action if previous_action else "等待启动"

    account = get_account_record(email)
    return jsonify(
        {
            "success": bool(result.success),
            "delivered": bool(result.delivered),
            "message": result.message,
            "stage": result.stage,
            "vendor": result.vendor,
            "deliveryEmail": result.delivery_email,
            "tempAccessUrl": result.temp_access_url,
            "tempAccessReady": bool(result.temp_access_ready),
            "mailId": result.mail_id,
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )


@app.route('/api/accounts/access-token', methods=['POST'])
def get_account_access_token():
    """
    按邮箱读取已保存的 accessToken。

    返回:
        Response: JSON 响应
        AI by zb
    """
    data = request.json or {}
    email = str(data.get("email") or "").strip()
    if not email:
        return jsonify({"error": "缺少邮箱参数"}), 400

    account = get_account_record(email)
    if not account:
        return jsonify({"error": "账号不存在"}), 404

    access_token = str(account.get("accessToken") or "").strip()
    if not access_token:
        return jsonify({"error": "当前账号未保存 accessToken"}), 400

    return jsonify(
        {
            "success": True,
            "message": "accessToken 获取成功",
            "email": email,
            "accessToken": access_token,
        }
    )


@app.route('/api/accounts/retry-plus', methods=['POST'])
def retry_account_plus():
    email, maybe_error = _run_manual_activation_action(
        "手动重试Plus",
        account_actions.run_plus_retry_for_account,
    )
    if email is None:
        return maybe_error

    result = maybe_error
    accepted = is_activation_request_accepted(result)
    response_status = build_activation_response_status(result)
    cancelled = str(getattr(result, "stage", "") or "").strip().lower() == "cancelled"
    upload_result = None
    latest_account = get_account_record(email)
    if (
        result.success
        and account_actions.is_sub2api_auto_upload_enabled()
        and latest_account
        and not bool(latest_account.get("sub2apiUploaded"))
    ):
        upload_result = account_actions.run_sub2api_upload_for_account(email)

    account = get_account_record(email)
    return jsonify(
        {
            "success": accepted,
            "accepted": accepted,
            "status": response_status,
            "cancelled": cancelled,
            "requestId": result.request_id,
            "message": ("Plus 激活成功" if result.success else ("Plus 激活已提交" if accepted else ("Plus 激活已取消" if cancelled else (result.message or "Plus 调用失败")))),
            "plus": {
                "success": accepted,
                "accepted": accepted,
                "finalSuccess": result.success,
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


@app.route('/api/accounts/retry-team', methods=['POST'])
def retry_account_team():
    email, maybe_error = _run_manual_activation_action(
        "手动激活Team",
        account_actions.run_team_retry_for_account,
    )
    if email is None:
        return maybe_error

    result = maybe_error
    accepted = is_activation_request_accepted(result)
    response_status = build_activation_response_status(result)
    cancelled = str(getattr(result, "stage", "") or "").strip().lower() == "cancelled"
    account = get_account_record(email)
    return jsonify(
        {
            "success": accepted,
            "accepted": accepted,
            "status": response_status,
            "cancelled": cancelled,
            "requestId": result.request_id,
            "message": ("Team 激活成功" if result.success else ("Team 激活已提交" if accepted else ("Team 激活已取消" if cancelled else (result.message or "Team 激活失败")))),
            "team": {
                "success": accepted,
                "accepted": accepted,
                "finalSuccess": result.success,
                "stage": result.stage,
                "status": result.status,
                "message": result.message,
                "requestId": result.request_id,
            },
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )


@app.route('/api/accounts/refresh-activation', methods=['POST'])
def refresh_account_activation():
    """
    按账号 requestId 刷新当前激活状态。

    返回:
        Response: JSON 响应
        AI by zb
    """
    data = request.json or {}
    email = str(data.get("email") or "").strip()
    if not email:
        return jsonify({"error": "缺少邮箱参数"}), 400

    try:
        account = account_actions.refresh_activation_status_for_account(email)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "success": True,
            "message": "激活状态已刷新",
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )


@app.route('/api/accounts/cancel-activation', methods=['POST'])
def cancel_account_activation():
    data = request.json or {}
    email = str(data.get("email") or "").strip()
    if not email:
        return jsonify({"error": "缺少邮箱参数"}), 400

    current_action = str(state.current_action or "").strip()
    normalized_action = current_action.lower()
    action_label = normalized_action.split(":", 1)[0].split("：", 1)[0]
    if not current_action:
        return jsonify({"error": "当前没有可取消的激活动作"}), 400
    if email.lower() not in normalized_action:
        return jsonify({"error": "当前账号没有正在进行的 Plus/Team 激活"}), 400
    if not any(keyword in action_label for keyword in ("plus", "team", "激活")):
        return jsonify({"error": "当前动作不是可取消的 Plus/Team 激活"}), 400

    previous_action = state.current_action
    state.current_action = f"取消激活: {email}"
    try:
        result = account_actions.run_cancel_activation_for_account(email)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        state.current_action = previous_action if previous_action else "等待启动"

    account = get_account_record(email)
    return jsonify(
        {
            "success": True,
            "cancelled": True,
            "message": str(result.get("message") or "已提交取消请求"),
            "requestId": str(result.get("requestId") or ""),
            "activeAction": str(result.get("activeAction") or ""),
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )


@app.route('/api/accounts/update-status', methods=['POST'])
def update_account_status_manually():
    if state.is_running:
        return jsonify({"error": "批量任务运行中，请稍后再试"}), 400

    data = request.json or {}
    email = str(data.get("email") or "").strip()
    status_text = str(data.get("status") or "").strip()
    if not email:
        return jsonify({"error": "缺少邮箱参数"}), 400
    if not status_text:
        return jsonify({"error": "缺少状态参数"}), 400

    previous_action = state.current_action
    state.current_action = f"手动修改状态: {email}"
    try:
        account = account_actions.run_manual_status_update_for_account(email, status_text)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        state.current_action = previous_action if previous_action else "等待启动"

    return jsonify(
        {
            "success": True,
            "message": "账号状态已更新",
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )


@app.route('/api/accounts/delete', methods=['POST'])
def delete_account():
    if state.is_running:
        return jsonify({"error": "批量任务运行中，请稍后再试"}), 400

    data = request.json or {}
    email = str(data.get("email") or "").strip()
    if not email:
        return jsonify({"error": "缺少邮箱参数"}), 400

    previous_action = state.current_action
    state.current_action = f"删除账号: {email}"
    try:
        deleted = account_actions.run_delete_account_for_email(email)
    finally:
        state.current_action = previous_action if previous_action else "等待启动"

    if not deleted:
        return jsonify({"error": "账号不存在或已删除"}), 404

    return jsonify(
        {
            "success": True,
            "message": "账号已删除",
            "email": email,
        }
    )


@app.route('/api/accounts/retry-registration', methods=['POST'])
def retry_account_registration():
    email, maybe_error = _run_manual_account_action(
        "手动继续注册",
        lambda account_email: main.run_registration_retry_for_account(
            account_email,
            monitor_callback=build_monitor_callback(allow_stop=False),
        ),
    )
    if email is None:
        return maybe_error

    result = maybe_error
    account = get_account_record(email)
    return jsonify(
        {
            "success": bool(result.get("success")),
            "message": result.get("message") or ("继续注册成功" if result.get("success") else "继续注册失败"),
            "stage": result.get("stage", ""),
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )


@app.route('/api/accounts/upload-sub2api', methods=['POST'])
def upload_account_sub2api():
    email, maybe_error = _run_manual_account_action("手动上传Sub2Api", account_actions.run_sub2api_upload_for_account)
    if email is None:
        return maybe_error

    result = maybe_error
    account = get_account_record(email)
    return jsonify(
        {
            "success": bool(result.uploaded),
            "message": result.message,
            "stage": result.stage,
            "account": sanitize_account_record_for_web(account) if account else None,
        }
    )


def parse_server_startup_options(
    argv: list[str] | None = None,
    default_port: int = 5000,
) -> argparse.Namespace:
    """
    解析 Web 服务启动参数，支持端口和 activation_api 索引。

    参数:
        argv: 命令行参数列表
        default_port: 默认监听端口
    返回:
        argparse.Namespace: 解析后的启动参数
        AI by zb
    """
    parser = argparse.ArgumentParser(description="启动 Web 控制台")
    parser.add_argument("port", nargs="?", type=int, help="监听端口")
    parser.add_argument("-p", "--port", dest="port_option", type=int, help="监听端口，优先级高于位置参数")
    parser.add_argument("--api", dest="activation_api_index", type=int, help="选择 activation_api.base_url 的索引，从 0 开始")
    args = parser.parse_args(argv)

    port = args.port_option if args.port_option is not None else args.port
    if port is None:
        port = default_port
    if not 1 <= port <= 65535:
        parser.error("端口号必须在 1 到 65535 之间")

    args.port = port
    return args


def parse_server_port(argv: list[str] | None = None, default_port: int = 5000) -> int:
    """
    解析 Web 服务启动端口，支持位置参数和 `--port` 选项。

    参数:
        argv: 命令行参数列表
        default_port: 默认监听端口
    返回:
        int: 最终监听端口
        AI by zb
    """
    return int(parse_server_startup_options(argv=argv, default_port=default_port).port)


def start_web_server(port: int = 5000, activation_api_index: int | None = None) -> None:
    """
    使用 Waitress 启动 Web 控制台服务。

    参数:
        port: Web 服务监听端口
    返回:
        None
        AI by zb
    """
    from waitress import serve

    selected_base_url, selected_index = select_activation_api_base_url(activation_api_index)
    if activation_api_index is None:
        print(f"🔌 activation_api 默认使用索引 {selected_index}: {selected_base_url}")
    elif activation_api_index == selected_index:
        print(f"🔌 activation_api 已切换到索引 {selected_index}: {selected_base_url}")
    else:
        print(f"⚠️ activation_api 索引 {activation_api_index} 不存在，已回退到索引 {selected_index}: {selected_base_url}")

    print(f"🌐 Web Server started at http://localhost:{port}")
    # 使用生产级服务器 Waitress
    # threads=6 支持并发：前端页面 + API轮询 + MJPEG流 + 后台任务
    serve(app, host='0.0.0.0', port=port, threads=6)


if __name__ == '__main__':
    startup_options = parse_server_startup_options(default_port=5000)
    start_web_server(
        port=int(startup_options.port),
        activation_api_index=startup_options.activation_api_index,
    )
