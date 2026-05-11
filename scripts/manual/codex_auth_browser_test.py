#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By

from app.browser import _legacy as legacy_browser

DEFAULT_AUTH_URL = "https://auth.openai.com/oauth/authorize?client_id=app_EMoamEEZ73f0CkXaXp7hrann&code_challenge=45LRcvzT7_eHXAW_4fhVl8AASfJoVHapprxFbKqcy1U&code_challenge_method=S256&codex_cli_simplified_flow=true&id_token_add_organizations=true&redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback&response_type=code&scope=openid+profile+email+offline_access&state=522af7a73c9dd82031017e8c2f2d0172e5a046b2ad1bb401fc959e8ef5d49914"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Codex OAuth 可见浏览器真实登录流程测试脚本")
    parser.add_argument("--url", default=DEFAULT_AUTH_URL, help="Codex OAuth authorize URL")
    parser.add_argument("--email", default="", help="自动填入的登录邮箱")
    parser.add_argument("--password", default="", help="可选：自动填入的密码")
    parser.add_argument("--otp", default="", help="可选：直接传入 6 位邮箱验证码")
    parser.add_argument("--otp-file", default="", help="可选：从文件读取 6 位验证码，文件出现后自动填入")
    parser.add_argument("--interactive-otp", action="store_true", help="到验证码页后在终端提示输入验证码")
    parser.add_argument("--wait", type=int, default=300, help="最长观察秒数")
    parser.add_argument("--headless", action="store_true", help="使用旧注册流程的伪无头模式")
    parser.add_argument("--keep-open", action="store_true", help="测试结束后保留浏览器窗口")
    parser.add_argument("--no-auto-consent", action="store_true", help="遇到 Codex 授权/组织页时不自动点击继续")
    parser.add_argument("--capture-network", action="store_true", help="采集 Chrome performance network 日志")
    parser.add_argument("--output", default="", help="可选：将结果 JSON 写入指定文件")
    return parser.parse_args()


def short_text(value: str, limit: int = 1000) -> str:
    return " ".join(str(value or "").split())[:limit]


def get_body_text(driver) -> str:
    try:
        return str(driver.find_element(By.TAG_NAME, "body").text or "")
    except Exception:
        return ""


def collect_controls(driver) -> list[dict[str, str]]:
    controls: list[dict[str, str]] = []
    for element in driver.find_elements(By.CSS_SELECTOR, "input, button, a")[:100]:
        try:
            controls.append(
                {
                    "tag": str(element.tag_name or ""),
                    "type": str(element.get_attribute("type") or ""),
                    "name": str(element.get_attribute("name") or ""),
                    "aria": str(element.get_attribute("aria-label") or ""),
                    "placeholder": str(element.get_attribute("placeholder") or ""),
                    "text": short_text(element.text, 120),
                    "href": short_text(str(element.get_attribute("href") or ""), 180),
                }
            )
        except Exception:
            pass
    return controls


def get_visible_elements(driver, selector: str):
    elements = []
    try:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            try:
                if element.is_displayed() and element.is_enabled():
                    elements.append(element)
            except StaleElementReferenceException:
                continue
    except Exception:
        pass
    return elements


def wait_visible(driver, selectors: list[str], timeout: int = 20):
    deadline = time.time() + max(timeout, 1)
    while time.time() < deadline:
        for selector in selectors:
            elements = get_visible_elements(driver, selector)
            if elements:
                return elements[0]
        time.sleep(0.25)
    raise TimeoutException(f"未找到可见元素: {selectors}")


def click_element(driver, element) -> bool:
    try:
        element.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False


def click_submit(driver) -> bool:
    selectors = [
        "button[type='submit']",
        "button[name='intent']",
        "button[name='action']",
        "button",
    ]
    for selector in selectors:
        for element in get_visible_elements(driver, selector):
            if click_element(driver, element):
                return True
    return False


def click_text_button(driver, labels: list[str]) -> bool:
    normalized_labels = [label.strip().lower() for label in labels if label.strip()]
    for element in driver.find_elements(By.CSS_SELECTOR, "button, a, [role='button']"):
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            text = short_text(element.text, 120).lower()
            aria = str(element.get_attribute("aria-label") or "").strip().lower()
            candidate = f"{text} {aria}".strip()
            if any(label in candidate for label in normalized_labels):
                return click_element(driver, element)
        except Exception:
            continue
    return False


def fill_input(element, value: str, delay: float = 0.03) -> None:
    element.clear()
    time.sleep(0.2)
    legacy_browser.type_slowly(element, value, delay=delay)


def enable_network_logging() -> None:
    original_build_options = legacy_browser._build_chrome_options

    def patched_build_options(headless: bool, detach: bool):
        options = original_build_options(headless, detach)
        options.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})
        return options

    legacy_browser._build_chrome_options = patched_build_options


def should_capture_detail(url: str) -> bool:
    targets = [
        "/api/accounts/authorize/continue",
        "/api/accounts/email-otp/validate",
        "/api/accounts/workspace/select",
        "/api/accounts/organization/select",
        "/api/accounts/client_auth_session_dump",
        "/api/oauth/oauth2/auth",
        "/api/accounts/consent",
        "/sign-in-with-chatgpt/codex/consent",
    ]
    return any(target in url for target in targets)


def compact_headers(headers: dict[str, object]) -> dict[str, str]:
    useful = [
        "accept",
        "content-type",
        "origin",
        "referer",
        "oai-device-id",
        "openai-sentinel-token",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "user-agent",
    ]
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    result: dict[str, str] = {}
    for key in useful:
        value = lowered.get(key)
        if value:
            result[key] = short_text(value, 500)
    return result


def try_get_response_body(driver, request_id: str) -> str:
    if not request_id:
        return ""
    try:
        body_payload = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
        body = str((body_payload or {}).get("body") or "")
        if bool((body_payload or {}).get("base64Encoded")):
            return "<base64>"
        return short_text(body, 1600)
    except Exception:
        return ""


def drain_network_logs(driver, network_events: list[dict[str, object]]) -> None:
    try:
        entries = driver.get_log("performance")
    except Exception:
        return
    for entry in entries:
        try:
            message = json.loads(str(entry.get("message") or "{}")).get("message", {})
        except Exception:
            continue
        method = str(message.get("method") or "")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "Network.requestWillBeSent":
            request = params.get("request") if isinstance(params.get("request"), dict) else {}
            url = str(request.get("url") or "")
            if "auth.openai.com" not in url and "localhost:1455" not in url:
                continue
            event: dict[str, object] = {
                "kind": "request",
                "requestId": str(params.get("requestId") or ""),
                "method": str(request.get("method") or ""),
                "url": short_text(url, 700),
            }
            if should_capture_detail(url):
                post_data = str(request.get("postData") or "")
                if post_data:
                    event["postData"] = short_text(post_data, 1600)
                headers = request.get("headers") if isinstance(request.get("headers"), dict) else {}
                event["headers"] = compact_headers(headers)
                initiator = params.get("initiator") if isinstance(params.get("initiator"), dict) else {}
                if initiator:
                    event["initiatorType"] = str(initiator.get("type") or "")
            network_events.append(event)
        elif method == "Network.responseReceived":
            response = params.get("response") if isinstance(params.get("response"), dict) else {}
            url = str(response.get("url") or "")
            if "auth.openai.com" not in url and "localhost:1455" not in url:
                continue
            request_id = str(params.get("requestId") or "")
            event = {
                "kind": "response",
                "requestId": request_id,
                "status": response.get("status"),
                "url": short_text(url, 700),
                "mimeType": str(response.get("mimeType") or ""),
            }
            if should_capture_detail(url):
                headers = response.get("headers") if isinstance(response.get("headers"), dict) else {}
                event["headers"] = compact_headers(headers)
                body = try_get_response_body(driver, request_id)
                if body:
                    event["body"] = body
            network_events.append(event)
        elif method == "Network.loadingFinished":
            request_id = str(params.get("requestId") or "")
            if not request_id:
                continue
            target_event = None
            for existing in reversed(network_events):
                if existing.get("requestId") == request_id and existing.get("kind") == "response":
                    target_event = existing
                    break
            if not target_event:
                continue
            url = str(target_event.get("url") or "")
            if not should_capture_detail(url):
                continue
            body = try_get_response_body(driver, request_id)
            if body:
                target_event["body"] = body


def detect_stage(driver) -> str:
    current_url = str(driver.current_url or "").lower()
    body = get_body_text(driver).lower()
    if "localhost:1455/auth/callback" in current_url and "code=" in current_url:
        return "callback"
    if "challenge" in body and ("ray id" in body or "enable javascript and cookies" in body):
        return "cloudflare"
    if get_visible_elements(driver, "input[type='email'], input[name='email'], input[name='username'], input[autocomplete='email'], #email-input"):
        return "email"
    if get_visible_elements(driver, "input[type='password'], input[name='password'], input[autocomplete='current-password'], input[autocomplete='new-password']"):
        return "password"
    if get_visible_elements(driver, "input[name='code'], input[autocomplete='one-time-code'], input[inputmode='numeric'], input[type='tel']"):
        return "otp"
    if "consent" in current_url or "authorize" in body or "授权" in body or "codex" in body:
        return "consent"
    if "organization" in current_url or "workspace" in current_url or "选择" in body:
        return "organization"
    return "unknown"


def build_summary(
    driver,
    elapsed: float,
    events: list[dict[str, str]],
    network_events: list[dict[str, object]],
) -> dict[str, object]:
    current_url = str(driver.current_url or "")
    parsed = urlparse(current_url)
    query = parse_qs(parsed.query)
    body_text = get_body_text(driver)
    lowered_text = body_text.lower()
    code = query.get("code", [""])[0]
    state = query.get("state", [""])[0]
    return {
        "elapsed_sec": round(elapsed, 2),
        "title": str(driver.title or ""),
        "final_url": current_url,
        "final_path": parsed.path,
        "stage": detect_stage(driver),
        "has_callback_code": bool(code),
        "code_preview": code[:16] if code else "",
        "has_state": bool(state),
        "state_preview": state[:16] if state else "",
        "is_cloudflare_challenge": any(
            marker in lowered_text
            for marker in ("正在进行安全验证", "enable javascript and cookies to continue", "ray id")
        ),
        "is_login_page": any(
            marker in lowered_text
            for marker in ("email", "电子邮件", "log in", "login", "continue", "继续", "验证码", "password", "密码")
        ),
        "body_preview": short_text(body_text, 1200),
        "events": events[-80:],
        "network_events": network_events[-160:],
        "controls": collect_controls(driver),
    }


def record_event(driver, events: list[dict[str, str]], action: str) -> None:
    event = {
        "elapsed": f"{time.time():.3f}",
        "action": action,
        "stage": detect_stage(driver),
        "title": short_text(str(driver.title or ""), 120),
        "url": short_text(str(driver.current_url or ""), 260),
        "body": short_text(get_body_text(driver), 220),
    }
    events.append(event)
    print(json.dumps(event, ensure_ascii=False))


def submit_email(driver, email: str) -> bool:
    if not email:
        return False
    email_input = wait_visible(
        driver,
        [
            "input[type='email']",
            "input[name='email']",
            "input[name='username']",
            "input[autocomplete='email']",
            "#email-input",
        ],
        timeout=30,
    )
    fill_input(email_input, email)
    time.sleep(0.8)
    return click_submit(driver)


def submit_password(driver, password: str) -> bool:
    if not password:
        return False
    password_input = wait_visible(
        driver,
        [
            "input[type='password']",
            "input[name='password']",
            "input[autocomplete='current-password']",
            "input[autocomplete='new-password']",
        ],
        timeout=10,
    )
    fill_input(password_input, password)
    time.sleep(0.8)
    return click_submit(driver)


def read_otp_from_file(path_text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text).expanduser()
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[:6] if len(digits) >= 6 else ""


def resolve_otp(args: argparse.Namespace) -> str:
    digits = "".join(ch for ch in str(args.otp or "") if ch.isdigit())
    if len(digits) >= 6:
        return digits[:6]
    file_otp = read_otp_from_file(str(args.otp_file or ""))
    if file_otp:
        return file_otp
    if bool(args.interactive_otp):
        raw = input("请输入 OpenAI 邮箱验证码（6位，直接回车跳过由浏览器手填）: ").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) >= 6:
            return digits[:6]
    return ""


def submit_otp(driver, code: str) -> bool:
    if not code:
        return False
    single_inputs = get_visible_elements(
        driver,
        "input[name='code'], input[autocomplete='one-time-code'], input[inputmode='numeric'], input[type='tel']",
    )
    digit_inputs = [
        element
        for element in get_visible_elements(driver, "input")
        if str(element.get_attribute("maxlength") or "") == "1"
    ]
    if len(digit_inputs) >= 6:
        for index, digit in enumerate(code[:6]):
            digit_inputs[index].clear()
            digit_inputs[index].send_keys(digit)
            time.sleep(0.08)
    elif single_inputs:
        fill_input(single_inputs[0], code, delay=0.08)
    else:
        return False
    time.sleep(0.8)
    return click_submit(driver)


def auto_continue_auth(driver) -> bool:
    labels = [
        "continue",
        "allow",
        "authorize",
        "confirm",
        "select",
        "继续",
        "允许",
        "授权",
        "确认",
        "选择",
    ]
    if click_text_button(driver, labels):
        return True
    return click_submit(driver)


def run_flow(
    driver,
    args: argparse.Namespace,
    events: list[dict[str, str]],
    network_events: list[dict[str, object]],
) -> None:
    handled_email = False
    handled_password = False
    handled_otp = False
    handled_auto_continue_at = 0.0
    last_signature = ""
    deadline = time.time() + max(int(args.wait or 0), 1)

    while time.time() < deadline:
        if bool(args.capture_network):
            drain_network_logs(driver, network_events)
        stage = detect_stage(driver)
        signature = f"{stage}|{driver.current_url}|{driver.title}"
        if signature != last_signature:
            record_event(driver, events, f"observe:{stage}")
            last_signature = signature

        if stage == "callback":
            return
        if stage == "email" and args.email and not handled_email:
            if submit_email(driver, str(args.email)):
                handled_email = True
                record_event(driver, events, "submit_email")
                time.sleep(3)
                continue
        if stage == "password" and args.password and not handled_password:
            if submit_password(driver, str(args.password)):
                handled_password = True
                record_event(driver, events, "submit_password")
                time.sleep(5)
                continue
        if stage == "otp" and not handled_otp:
            code = resolve_otp(args)
            if code and submit_otp(driver, code):
                handled_otp = True
                record_event(driver, events, "submit_otp")
                time.sleep(5)
                continue
            record_event(driver, events, "wait_manual_otp")
            handled_otp = True
        if stage in {"consent", "organization"} and not bool(args.no_auto_consent):
            if time.time() - handled_auto_continue_at > 5:
                if auto_continue_auth(driver):
                    handled_auto_continue_at = time.time()
                    record_event(driver, events, f"auto_continue:{stage}")
                    time.sleep(4)
                    continue
        time.sleep(1)


def main() -> int:
    args = parse_args()
    driver = None
    events: list[dict[str, str]] = []
    network_events: list[dict[str, object]] = []
    started = time.time()
    try:
        if bool(args.capture_network):
            enable_network_logging()
        driver = legacy_browser.create_driver(headless=bool(args.headless), detach=bool(args.keep_open))
        if bool(args.capture_network):
            try:
                driver.execute_cdp_cmd("Network.enable", {})
            except Exception:
                pass
        driver.set_page_load_timeout(90)
        print(f"🌐 打开 Codex OAuth URL: {str(args.url)[:180]}")
        driver.get(str(args.url))
        run_flow(driver, args, events, network_events)
        if bool(args.capture_network):
            drain_network_logs(driver, network_events)
        summary = build_summary(driver, time.time() - started, events, network_events)
        if str(args.output or "").strip():
            Path(str(args.output)).expanduser().write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc), "events": events}, ensure_ascii=False, indent=2))
        return 1
    finally:
        if driver and not bool(getattr(args, "keep_open", False)):
            try:
                driver.quit()
            except Exception:
                pass
        elif driver:
            input("浏览器已保留，按回车结束脚本...")


if __name__ == "__main__":
    raise SystemExit(main())
