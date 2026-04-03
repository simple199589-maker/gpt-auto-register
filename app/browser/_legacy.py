"""
浏览器自动化模块
使用 undetected-chromedriver 实现 ChatGPT 注册流程
"""

import os
import re
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

try:
    import winreg
except ImportError:  # pragma: no cover - 仅在非 Windows 环境兜底
    winreg = None

from app.config import (
    MAX_WAIT_TIME,
    SHORT_WAIT_TIME,
    ERROR_PAGE_MAX_RETRIES,
    BUTTON_CLICK_MAX_RETRIES,
    CREDIT_CARD_INFO
)
from app.utils import generate_user_info, generate_billing_info

_CHROME_MAJOR_VERSION_CACHE = None
_CHROMEDRIVER_MAJOR_VERSION_CACHE: dict[str, int | None] = {}
VISIBLE_WINDOW_X = 24
VISIBLE_WINDOW_Y = 24
VISIBLE_WINDOW_WIDTH = 1440
VISIBLE_WINDOW_HEIGHT = 960
OFFSCREEN_WINDOW_X = -10000
OFFSCREEN_WINDOW_Y = -10000
OFFSCREEN_WINDOW_WIDTH = 1920
OFFSCREEN_WINDOW_HEIGHT = 1080
CHATGPT_HOME_URLS = [
    "https://chatgpt.com/",
    "https://chatgpt.com",
    "https://chat.openai.com/chat",
]
CHATGPT_LOGIN_URLS = [
    "https://chatgpt.com/auth/login",
    "https://chatgpt.com/",
    "https://chat.openai.com/auth/login",
]


class SafeChrome(uc.Chrome):
    """
    自定义 Chrome 类，修复 Windows 下退出时的 WinError 6
    """
    def __del__(self):
        if getattr(self, "_skip_auto_quit", False):
            return
        try:
            self.quit()
        except OSError:
            pass
        except Exception:
            pass

    def quit(self):
        try:
            super().quit()
        except OSError:
            pass
        except Exception:
            pass


def get_local_chrome_major_version():
    """
    检测本机 Chrome 主版本号。

    返回:
        int | None: Chrome 主版本号，检测失败时返回 None
        AI by zb
    """
    global _CHROME_MAJOR_VERSION_CACHE
    if _CHROME_MAJOR_VERSION_CACHE is not None:
        return _CHROME_MAJOR_VERSION_CACHE or None

    chrome_paths = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]

    registry_candidates = [
        (getattr(winreg, "HKEY_CURRENT_USER", None), r"Software\Google\Chrome\BLBeacon", "version"),
        (getattr(winreg, "HKEY_LOCAL_MACHINE", None), r"Software\Google\Chrome\BLBeacon", "version"),
        (getattr(winreg, "HKEY_CURRENT_USER", None), r"Software\Chromium\BLBeacon", "version"),
        (getattr(winreg, "HKEY_LOCAL_MACHINE", None), r"Software\Chromium\BLBeacon", "version"),
    ]

    if winreg:
        for root, sub_key, value_name in registry_candidates:
            if root is None:
                continue
            try:
                with winreg.OpenKey(root, sub_key) as registry_key:
                    version_value, _ = winreg.QueryValueEx(registry_key, value_name)
                match = re.search(r"(\d+)\.\d+\.\d+\.\d+", str(version_value or "").strip())
                if match:
                    _CHROME_MAJOR_VERSION_CACHE = int(match.group(1))
                    return _CHROME_MAJOR_VERSION_CACHE
            except Exception:
                continue

    for chrome_path in chrome_paths:
        if not chrome_path or not os.path.exists(chrome_path):
            continue

        try:
            result = subprocess.run(
                [chrome_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                encoding="utf-8",
                errors="ignore"
            )
            output = (result.stdout or result.stderr or "").strip()
            match = re.search(r"(\d+)\.\d+\.\d+\.\d+", output)
            if match:
                _CHROME_MAJOR_VERSION_CACHE = int(match.group(1))
                return _CHROME_MAJOR_VERSION_CACHE
        except Exception:
            continue

    _CHROME_MAJOR_VERSION_CACHE = 0
    return None


def _get_uc_data_path() -> Path:
    """
    获取 undetected-chromedriver 使用的数据目录。

    返回:
        Path: 数据目录
        AI by zb
    """
    data_path = str(getattr(uc.Patcher, "data_path", "") or "").strip()
    if data_path:
        return Path(os.path.abspath(os.path.expanduser(data_path)))
    return Path.home() / "AppData" / "Roaming" / "undetected_chromedriver"


def _extract_major_version_from_text(text: str) -> int | None:
    """
    从文本中提取主版本号。

    参数:
        text: 原始文本
    返回:
        int | None: 主版本号
        AI by zb
    """
    match = re.search(r"(\d+)\.\d+\.\d+\.\d+", str(text or "").strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _read_chromedriver_major_version(driver_path: Path) -> int | None:
    """
    读取指定 chromedriver 可执行文件的主版本号。

    参数:
        driver_path: chromedriver 路径
    返回:
        int | None: 主版本号
        AI by zb
    """
    cache_key = str(driver_path.resolve()) if driver_path.exists() else str(driver_path)
    if cache_key in _CHROMEDRIVER_MAJOR_VERSION_CACHE:
        return _CHROMEDRIVER_MAJOR_VERSION_CACHE[cache_key]

    major_version = None
    try:
        result = subprocess.run(
            [str(driver_path), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            encoding="utf-8",
            errors="ignore",
        )
        output = (result.stdout or result.stderr or "").strip()
        major_version = _extract_major_version_from_text(output)
    except Exception:
        major_version = None

    if major_version is None:
        for part in driver_path.parts:
            major_version = _extract_major_version_from_text(part)
            if major_version is not None:
                break

    _CHROMEDRIVER_MAJOR_VERSION_CACHE[cache_key] = major_version
    return major_version


def _iter_chromedriver_candidates():
    """
    枚举本机可能可复用的 chromedriver 可执行文件。

    返回:
        list[Path]: 候选路径列表
        AI by zb
    """
    candidates: list[Path] = []
    seen_paths: set[str] = set()

    direct_candidates = [
        shutil.which("chromedriver"),
        str((Path(__file__).resolve().parents[2] / "drivers" / "chromedriver.exe")),
    ]
    search_roots = [
        _get_uc_data_path(),
        Path.home() / ".cache" / "selenium" / "chromedriver",
        Path.home() / "AppData" / "Roaming" / "undetected_chromedriver",
    ]

    for raw_path in direct_candidates:
        if not raw_path:
            continue
        candidate = Path(str(raw_path)).expanduser()
        normalized = str(candidate).lower()
        if normalized in seen_paths or not candidate.exists():
            continue
        seen_paths.add(normalized)
        candidates.append(candidate)

    for root in search_roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*chromedriver*.exe"):
            normalized = str(candidate).lower()
            if normalized in seen_paths or not candidate.is_file():
                continue
            seen_paths.add(normalized)
            candidates.append(candidate)

    return candidates


def _find_reusable_chromedriver(chrome_major_version: int | None) -> Path | None:
    """
    查找可直接复用的本地 chromedriver。

    参数:
        chrome_major_version: 本机 Chrome 主版本号
    返回:
        Path | None: 最佳候选路径
        AI by zb
    """
    exact_matches: list[tuple[float, Path]] = []
    fallback_matches: list[tuple[float, Path]] = []

    for candidate in _iter_chromedriver_candidates():
        major_version = _read_chromedriver_major_version(candidate)
        try:
            sort_key = candidate.stat().st_mtime
        except Exception:
            sort_key = 0.0

        if chrome_major_version and major_version == chrome_major_version:
            exact_matches.append((sort_key, candidate))
        elif not chrome_major_version and major_version is not None:
            fallback_matches.append((sort_key, candidate))

    if exact_matches:
        return max(exact_matches, key=lambda item: item[0])[1]
    if fallback_matches:
        return max(fallback_matches, key=lambda item: item[0])[1]
    return None


def _prepare_local_chromedriver_copy(source_path: Path, chrome_major_version: int | None) -> Path:
    """
    将可复用的 chromedriver 复制到 UC 自身缓存目录，避免直接修改第三方缓存。

    参数:
        source_path: 源驱动路径
        chrome_major_version: 本机 Chrome 主版本号
    返回:
        Path: UC 可直接使用的本地副本路径
        AI by zb
    """
    uc_data_path = _get_uc_data_path()
    target_dir = uc_data_path / "local_cache"
    target_dir.mkdir(parents=True, exist_ok=True)

    target_name = f"chromedriver_{chrome_major_version or 'auto'}.exe"
    target_path = target_dir / target_name

    try:
        if source_path.resolve() == target_path.resolve():
            return target_path
    except Exception:
        pass

    should_copy = True
    if target_path.exists():
        try:
            should_copy = (
                source_path.stat().st_size != target_path.stat().st_size
                or source_path.stat().st_mtime > target_path.stat().st_mtime
            )
        except Exception:
            should_copy = True

    if should_copy:
        shutil.copy2(source_path, target_path)

    return target_path


def _is_chromedriver_download_error(exc: Exception) -> bool:
    """
    判断异常是否属于在线获取 ChromeDriver 时的网络错误。

    参数:
        exc: 捕获到的异常
    返回:
        bool: 是否为驱动下载类错误
        AI by zb
    """
    message = str(exc or "").lower()
    keywords = [
        "urlopen error",
        "unexpected eof while reading",
        "ssl:",
        "googlechromelabs.github.io",
        "chrome-for-testing-public",
        "storage.googleapis.com",
    ]
    return any(keyword in message for keyword in keywords)


def _build_chrome_options(headless: bool, detach: bool):
    """
    构建 ChromeOptions，避免在重试启动时复用已消费的配置对象。

    参数:
        headless: 是否使用伪无头模式
        detach: 是否请求注册成功后暂时保留浏览器
    返回:
        uc.ChromeOptions: 新建的浏览器配置对象
        AI by zb
    """
    options = uc.ChromeOptions()

    # 某些 ChromeDriver / undetected-chromedriver 组合不识别 detach，
    # 这里不直接注入实验参数，改由上层保留 driver 引用控制窗口生命周期。
    if detach:
        print("ℹ️ 保留浏览器模式由脚本控制，不向 ChromeDriver 注入 detach 参数")

    if headless:
        print("  👻 使用'伪无头'模式 (Off-screen) 以绕过检测...")
        options.add_argument(f"--window-position={OFFSCREEN_WINDOW_X},{OFFSCREEN_WINDOW_Y}")
        options.add_argument(f"--window-size={OFFSCREEN_WINDOW_WIDTH},{OFFSCREEN_WINDOW_HEIGHT}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        
        # 仍然可以加一些伪装，虽然不是必需的，因为已经是真浏览器了
        options.add_argument("--lang=zh-CN,zh;q=0.9,en;q=0.8")

    return options


def _set_browser_window_bounds(driver, x: int, y: int, width: int, height: int) -> None:
    """
    尽量统一设置浏览器窗口的位置与尺寸。

    参数:
        driver: 浏览器驱动
        x: 左上角横坐标
        y: 左上角纵坐标
        width: 窗口宽度
        height: 窗口高度
        AI by zb
    """
    target_x = int(x)
    target_y = int(y)
    target_width = max(int(width), 1)
    target_height = max(int(height), 1)

    try:
        driver.set_window_rect(
            x=target_x,
            y=target_y,
            width=target_width,
            height=target_height,
        )
        return
    except Exception:
        pass

    try:
        driver.set_window_position(target_x, target_y)
    except Exception:
        pass

    try:
        driver.set_window_size(target_width, target_height)
    except Exception:
        pass


def _activate_browser_page(driver) -> None:
    """
    尽量激活当前浏览器窗口与标签页，减少显示模式下的失焦问题。

    参数:
        driver: 浏览器驱动
        AI by zb
    """
    try:
        current_handle = driver.current_window_handle
        driver.switch_to.window(current_handle)
    except Exception:
        pass

    try:
        driver.execute_cdp_cmd("Page.bringToFront", {})
    except Exception:
        pass

    try:
        driver.execute_script("window.focus();")
    except Exception:
        pass


def _stabilize_browser_window(driver, visible: bool) -> None:
    """
    根据显示模式整理浏览器窗口状态，避免可见模式失焦或隐藏模式误弹窗。

    参数:
        driver: 浏览器驱动
        visible: 是否应显示浏览器窗口
        AI by zb
    """
    if visible:
        _set_browser_window_bounds(
            driver,
            VISIBLE_WINDOW_X,
            VISIBLE_WINDOW_Y,
            VISIBLE_WINDOW_WIDTH,
            VISIBLE_WINDOW_HEIGHT,
        )
        try:
            driver.maximize_window()
        except Exception:
            pass
        time.sleep(0.2)
        _activate_browser_page(driver)
        return

    _set_browser_window_bounds(
        driver,
        OFFSCREEN_WINDOW_X,
        OFFSCREEN_WINDOW_Y,
        OFFSCREEN_WINDOW_WIDTH,
        OFFSCREEN_WINDOW_HEIGHT,
    )


def create_driver(headless=False, detach=False):
    """
    创建 undetected Chrome 浏览器驱动
    
    参数:
        headless (bool): 是否使用无头模式
        detach (bool): 是否在驱动退出后保留浏览器窗口
        
    返回:
        uc.Chrome: 浏览器驱动实例
    """
    print(f"🌐 正在初始化浏览器 (Headless: {headless}, Detach: {detach})...")
    
    # === 伪无头模式 (Fake Headless) ===
    # 真正的 Headless 很难过 Cloudflare，我们使用"移出屏幕"的策略
    # 这样既拥有完整的浏览器指纹，用户又看不到窗口
    real_headless = False

    chrome_major_version = get_local_chrome_major_version()
    if chrome_major_version:
        print(f"🔍 检测到本机 Chrome 主版本: {chrome_major_version}")
    else:
        print("⚠️ 未能检测到本机 Chrome 主版本，将使用 undetected-chromedriver 默认匹配")

    # 使用自定义的 SafeChrome (注意: 传入 real_headless=False)
    options = _build_chrome_options(headless=headless, detach=detach)
    driver_kwargs = {
        "options": options,
        "use_subprocess": True,
        "headless": real_headless,
    }
    if chrome_major_version:
        driver_kwargs["version_main"] = chrome_major_version
    cached_driver_source = _find_reusable_chromedriver(chrome_major_version)
    cached_driver_copy = None
    if cached_driver_source:
        try:
            cached_driver_copy = _prepare_local_chromedriver_copy(
                cached_driver_source,
                chrome_major_version,
            )
            driver_kwargs["driver_executable_path"] = str(cached_driver_copy)
            print(f"♻️ 复用本地 ChromeDriver: {cached_driver_source}")
        except Exception as exc:
            cached_driver_copy = None
            print(f"⚠️ 准备本地 ChromeDriver 缓存失败，将尝试在线方式: {exc}")

    try:
        driver = SafeChrome(**driver_kwargs)
    except Exception as cached_exc:
        if cached_driver_copy:
            print(f"⚠️ 本地 ChromeDriver 启动失败，准备回退在线方式: {cached_exc}")
            fallback_options = _build_chrome_options(headless=headless, detach=detach)
            fallback_kwargs = {
                "options": fallback_options,
                "use_subprocess": True,
                "headless": real_headless,
            }
            if chrome_major_version:
                fallback_kwargs["version_main"] = chrome_major_version
            try:
                driver = SafeChrome(**fallback_kwargs)
            except Exception as online_exc:
                if _is_chromedriver_download_error(online_exc):
                    raise RuntimeError(
                        "ChromeDriver 在线获取失败，请检查到 Google 驱动源的网络连通性；"
                        "也可预先准备本地 chromedriver 缓存。"
                    ) from online_exc
                raise
        else:
            if _is_chromedriver_download_error(cached_exc):
                raise RuntimeError(
                    "ChromeDriver 在线获取失败，请检查到 Google 驱动源的网络连通性；"
                    "也可预先准备本地 chromedriver 缓存。"
                ) from cached_exc
            raise
    
    # === 深度伪装 (针对 Headless 模式) ===
    if headless:
        print("🎭 应用深度指纹伪装...")
        
        # 1. 伪造 WebGL 供应商 (让它看起来像有真实显卡)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    // 37445: UNMASKED_VENDOR_WEBGL
                    // 37446: UNMASKED_RENDERER_WEBGL
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel(R) Iris(R) Xe Graphics';
                    }
                    return getParameter(parameter);
                };
            """
        })
        
        # 2. 伪造插件列表 (Headless 默认是空的)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en'],
                });
            """
        })
        
        # 3. 绕过常见的检测属性
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                // 覆盖 window.chrome
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // 伪造 permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                    Promise.resolve({ state: 'denied' }) :
                    originalQuery(parameters)
                );
            """
        })

    _stabilize_browser_window(driver, visible=not headless)
    if headless:
        print("🪟 浏览器窗口保持离屏运行")
    else:
        print("🪟 浏览器窗口已切换到可见交互模式")

    return driver


def check_and_handle_error(driver, max_retries=None):
    """
    检测页面错误并自动重试
    
    参数:
        driver: 浏览器驱动
        max_retries: 最大重试次数
    
    返回:
        bool: 是否检测到错误并处理
    """
    if max_retries is None:
        max_retries = ERROR_PAGE_MAX_RETRIES
    
    for attempt in range(max_retries):
        try:
            page_source = driver.page_source.lower()
            error_keywords = ['出错', 'error', 'timed out', 'operation timeout', 'route error', 'invalid content']
            has_error = any(keyword in page_source for keyword in error_keywords)
            
            if has_error:
                try:
                    retry_btn = driver.find_element(By.CSS_SELECTOR, 'button[data-dd-action-name="Try again"]')
                    print(f"⚠️ 检测到错误页面，正在重试（第 {attempt + 1}/{max_retries} 次）...")
                    driver.execute_script("arguments[0].click();", retry_btn)
                    wait_time = 5 + (attempt * 2)
                    print(f"  等待 {wait_time} 秒后继续...")
                    time.sleep(wait_time)
                    return True
                except Exception:
                    time.sleep(2)
                    continue
            return False
            
        except Exception as e:
            print(f"  错误检测异常: {e}")
            return False
    
    return False


def click_button_with_retry(driver, selector, max_retries=None):
    """
    带重试机制的按钮点击
    
    参数:
        driver: 浏览器驱动
        selector: CSS 选择器
        max_retries: 最大重试次数
    
    返回:
        bool: 是否成功点击
    """
    if max_retries is None:
        max_retries = BUTTON_CLICK_MAX_RETRIES
    
    for attempt in range(max_retries):
        try:
            button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            driver.execute_script("arguments[0].click();", button)
            return True
        except Exception as e:
            print(f"  第 {attempt + 1} 次点击失败，正在重试...")
            time.sleep(2)
    
    return False


def type_slowly(element, text, delay=0.05):
    """
    模拟人工缓慢输入
    
    参数:
        element: 输入框元素
        text: 要输入的文本
        delay: 每个字符之间的延迟（秒）
    """
    for char in text:
        element.send_keys(char)
        time.sleep(delay)


def _find_first_visible_element(driver, by, selectors: list[str]):
    """
    在多个选择器中查找第一个可见元素。

    参数:
        driver: 浏览器驱动
        by: Selenium 定位方式
        selectors: 选择器列表
    返回:
        WebElement | None: 首个可见元素
        AI by zb
    """
    for selector in selectors:
        try:
            elements = driver.find_elements(by, selector)
            for element in elements:
                try:
                    if element.is_displayed():
                        return element
                except Exception:
                    continue
        except Exception:
            continue
    return None


def _page_contains_any_text(driver, keywords: list[str]) -> bool:
    """
    判断当前页面源码中是否包含任一关键文本。

    参数:
        driver: 浏览器驱动
        keywords: 关键文本列表
    返回:
        bool: 是否命中
        AI by zb
    """
    try:
        page_source = str(driver.page_source or "").lower()
    except Exception:
        return False

    for keyword in keywords:
        if str(keyword or "").strip().lower() in page_source:
            return True
    return False


def _get_signup_verification_markers():
    """
    返回注册流程中“邮件验证码页”的识别标记。

    返回:
        tuple[list[str], list[str], list[str]]: CSS 选择器、XPath、文本关键字
        AI by zb
    """
    css_selectors = [
        'input[name="code"]',
        'input[placeholder*="代码"]',
        'input[placeholder*="code"]',
        'input[aria-label*="代码"]',
        'input[aria-label*="code"]',
    ]
    xpath_selectors = [
        '//button[contains(normalize-space(.), "重新发送电子邮件")]',
        '//button[contains(normalize-space(.), "重新发送邮件")]',
        '//button[contains(normalize-space(.), "重新发送")]',
        '//button[contains(normalize-space(.), "Resend email")]',
        '//button[contains(normalize-space(.), "Resend")]',
        '//a[contains(normalize-space(.), "重新发送电子邮件")]',
        '//a[contains(normalize-space(.), "重新发送")]',
        '//a[contains(normalize-space(.), "Resend email")]',
        '//a[contains(normalize-space(.), "Resend")]',
    ]
    text_keywords = [
        "检查您的收件箱",
        "check your inbox",
        "输入验证码",
        "enter code",
        "verification code",
        "重新发送电子邮件",
        "resend email",
        "we sent a code",
        "we've sent a code",
        "输入代码",
        "继续使用邮箱",
    ]
    return css_selectors, xpath_selectors, text_keywords


def _get_signup_password_switch_xpaths():
    """
    返回注册流程中“切换到密码继续”的按钮选择器。

    返回:
        list[str]: XPath 列表
        AI by zb
    """
    return [
        '//button[contains(normalize-space(.), "使用密码继续")]',
        '//button[contains(normalize-space(.), "使用密码")]',
        '//button[contains(normalize-space(.), "继续使用密码")]',
        '//button[contains(normalize-space(.), "Use password")]',
        '//button[contains(normalize-space(.), "Continue with password")]',
        '//button[contains(normalize-space(.), "Enter password")]',
        '//button[contains(normalize-space(.), "password instead")]',
        '//a[contains(normalize-space(.), "使用密码继续")]',
        '//a[contains(normalize-space(.), "Use password")]',
        '//a[contains(normalize-space(.), "Enter password")]',
        '//a[contains(normalize-space(.), "password instead")]',
    ]


def _detect_signup_next_step(driver) -> str:
    """
    检测注册邮箱提交后的下一步页面状态。

    返回:
        str: `verification` / `password` / `password_switch` / 空字符串
        AI by zb
    """
    verification_css, verification_xpaths, verification_texts = _get_signup_verification_markers()
    password_switch = _find_first_visible_element(driver, By.XPATH, _get_signup_password_switch_xpaths())
    password_input = _find_first_visible_element(
        driver,
        By.CSS_SELECTOR,
        ['input[autocomplete="new-password"]', 'input[name="password"]', 'input[type="password"]'],
    )

    if _find_first_visible_element(driver, By.CSS_SELECTOR, verification_css):
        return "verification"
    if _find_first_visible_element(driver, By.XPATH, verification_xpaths):
        return "verification"
    if _page_contains_any_text(driver, verification_texts):
        return "verification"
    if password_input:
        return "password"
    if password_switch:
        return "password_switch"
    return ""


def _wait_signup_next_step(driver, timeout_seconds: int = 15) -> str:
    """
    等待注册邮箱提交后的下一步状态稳定出现。

    参数:
        driver: 浏览器驱动
        timeout_seconds: 最长等待时间
    返回:
        str: 页面状态
        AI by zb
    """
    deadline = time.time() + max(int(timeout_seconds or 0), 1)
    while time.time() < deadline:
        step = _detect_signup_next_step(driver)
        if step:
            return step
        while check_and_handle_error(driver):
            time.sleep(1)
        time.sleep(0.5)
    return ""


def _click_signup_password_switch(driver) -> bool:
    """
    点击注册流程中的“使用密码继续”入口。

    参数:
        driver: 浏览器驱动
    返回:
        bool: 是否点击成功
        AI by zb
    """
    switch_button = _find_first_visible_element(driver, By.XPATH, _get_signup_password_switch_xpaths())
    if not switch_button:
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", switch_button)
        time.sleep(0.5)
    except Exception:
        pass

    try:
        switch_button.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", switch_button)
            return True
        except Exception:
            return False


def open_first_reachable_url(driver, urls: list[str], scene_name: str) -> str:
    """
    依次尝试打开候选地址，直到成功进入可用页面。

    参数:
        driver: 浏览器驱动
        urls: 候选地址列表
        scene_name: 场景名，用于日志输出
    返回:
        str: 最终成功打开的地址
        AI by zb
    """
    errors = []

    for index, url in enumerate(urls, 1):
        try:
            print(f"🌐 正在打开 {scene_name} 页面 ({index}/{len(urls)}): {url}")
            driver.get(url)
            time.sleep(3)
            current_url = str(driver.current_url or "").strip()
            title = str(driver.title or "").strip()
            if current_url:
                print(f"✅ 已进入页面: {current_url or url}")
                if title:
                    print(f"   标题: {title}")
                return url
            raise RuntimeError("页面未返回有效 URL")
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            errors.append(f"{url} -> {message}")
            print(f"⚠️ 打开失败: {url}")
            print(f"   原因: {message}")
            continue

    raise RuntimeError(
        f"{scene_name} 页面全部尝试失败: " + " | ".join(errors)
    )


def fill_signup_form(driver, email: str, password: str):
    """
    填写注册表单
    适配 ChatGPT 新版统一登录/注册页面
    
    参数:
        driver: 浏览器驱动
        email: 邮箱地址
        password: 密码
    
    返回:
        bool: 是否成功填写
    """
    wait = WebDriverWait(driver, MAX_WAIT_TIME)
    
    try:
        # 1. 等待邮箱输入框出现
        print(f"DEBUG: 当前页面标题: {driver.title}")
        print(f"DEBUG: 当前页面URL: {driver.current_url}")
        print("📧 等待邮箱输入框...")
        
        # 检查是否是 Cloudflare 验证页
        if "Just a moment" in driver.title or "Ray ID" in driver.page_source or "请稍候" in driver.title:
             print("⚠️ 检测到 Cloudflare 验证页面...")
             # 尝试等待
             time.sleep(10)
             if "Just a moment" in driver.title or "请稍候" in driver.title:
                 print("  🔄 尝试刷新页面以突破验证...")
                 driver.refresh()
                 time.sleep(10)
                 
             # 再次检查，尝试点击验证框
             try:
                 # 寻找 CF 验证 iframe
                 frames = driver.find_elements(By.TAG_NAME, "iframe")
                 for frame in frames:
                     try:
                         driver.switch_to.frame(frame)
                         # 常见的验证框 ID 或 Class
                         checkbox = driver.find_elements(By.CSS_SELECTOR, "#checkbox, .checkbox, input[type='checkbox'], #challenge-stage")
                         if checkbox:
                             print("  🖱️ 尝试点击验证框...")
                             driver.execute_script("arguments[0].click();", checkbox[0])
                             time.sleep(5)
                         driver.switch_to.default_content()
                     except:
                         driver.switch_to.default_content()
             except: pass

        # 0. 检查是否在着陆页，需要点击注册/登录
        print("🔍 检查是否需要点击 注册/登录 按钮...")
        try:
            # 寻找 Sign up / Log in 按钮
            signup_btns = driver.find_elements(By.XPATH, '//button[contains(., "Sign up")] | //button[contains(., "注册")] | //div[contains(text(), "Sign up")] | //div[contains(text(), "注册")]')
            login_btns = driver.find_elements(By.XPATH, '//button[contains(., "Log in")] | //button[contains(., "登录")] | //div[contains(text(), "Log in")] | //div[contains(text(), "登录")]')
            
            target_btn = None
            if signup_btns:
                target_btn = signup_btns[0]
                print("  -> 找到 注册(Sign up) 按钮")
            elif login_btns:
                target_btn = login_btns[0]
                print("  -> 找到 登录(Log in) 按钮")
                
            if target_btn and target_btn.is_displayed():
                driver.execute_script("arguments[0].click();", target_btn)
                print("  ✅ 已点击入口按钮")
                time.sleep(3)
        except Exception as e:
            print(f"  ⚠️ 检查入口按钮时出错 (非致命): {e}")

        email_input = WebDriverWait(driver, SHORT_WAIT_TIME).until(
            EC.visibility_of_element_located((
                By.CSS_SELECTOR, 
                'input[type="email"], input[name="email"], input[autocomplete="email"]'
            ))
        )
        
        # 使用 ActionChains 模拟真实用户操作
        print("📝 正在输入邮箱...")
        actions = ActionChains(driver)
        actions.move_to_element(email_input)
        actions.click()
        actions.pause(0.3)
        actions.send_keys(email)
        actions.perform()
        
        time.sleep(1)
        
        # 验证输入是否成功
        actual_value = email_input.get_attribute('value')
        if actual_value == email:
            print(f"✅ 已输入邮箱: {email}")
        else:
            print(f"⚠️ 输入可能不完整，实际值: {actual_value}")
        
        time.sleep(1)
        
        # 2. 点击继续按钮
        print("🔘 点击继续按钮...")
        continue_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
        )
        actions = ActionChains(driver)
        actions.move_to_element(continue_btn)
        actions.click()
        actions.perform()
        print("✅ 已点击继续")
        time.sleep(3)

        next_step = _wait_signup_next_step(driver, timeout_seconds=min(int(SHORT_WAIT_TIME or 15), 20))
        if next_step == "verification":
            print("✅ 邮箱提交后已进入邮件验证步骤")
            return True

        if next_step == "password_switch":
            print("ℹ️ 当前页面提供“使用密码继续”，准备切换到密码设置流程...")
            if not _click_signup_password_switch(driver):
                raise RuntimeError("未能点击“使用密码继续”按钮")
            time.sleep(2)
            next_step = _wait_signup_next_step(driver, timeout_seconds=10)
            if next_step == "verification":
                print("✅ 点击切换前后已进入邮件验证步骤")
                return True

        if next_step != "password":
            raise RuntimeError(
                f"邮箱提交后未识别到密码页或邮件验证页，当前URL: {driver.current_url}"
            )

        # 4. 输入密码
        print("🔑 等待密码输入框...")
        password_input = WebDriverWait(driver, SHORT_WAIT_TIME).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="new-password"], input[name="password"], input[type="password"]'))
        )
        password_input.clear()
        time.sleep(0.5)
        type_slowly(password_input, password)
        print("✅ 已输入密码")
        time.sleep(2)
        
        # 5. 点击继续
        print("🔘 点击继续按钮...")
        if not click_button_with_retry(driver, 'button[type="submit"]'):
            print("❌ 点击继续按钮失败")
            return False
        print("✅ 已点击继续")
        
        time.sleep(3)
        while check_and_handle_error(driver):
            time.sleep(2)
        
        return True
    except InterruptedError:
        raise
    except Exception as e:
        print(f"❌ 填写表单失败: {e}")
        return False



def login(driver, email, password):
    """
    登录 ChatGPT
    """
    print(f"🔐 正在登录 {email}...")
    wait = WebDriverWait(driver, 30)
    
    try:
        open_first_reachable_url(driver, CHATGPT_LOGIN_URLS, "login")
        
        # 0. 点击初始页面的 Log in / 登录 按钮
        print("🔘 寻找 Log in / 登录 按钮...")
        try:
            # 尝试多种选择器，支持中文
            xpaths = [
                '//button[@data-testid="login-button"]',
                '//button[contains(., "Log in")]',
                '//button[contains(., "登录")]',
                '//div[contains(text(), "Log in")]',
                '//div[contains(text(), "登录")]'
            ]
            
            login_btn = None
            for xpath in xpaths:
                try:
                    btns = driver.find_elements(By.XPATH, xpath)
                    for btn in btns:
                        if btn.is_displayed():
                            login_btn = btn
                            break
                    if login_btn:
                        break
                except:
                    continue
            
            if login_btn:
                # 确保点击
                try:
                    login_btn.click()
                except:
                    driver.execute_script("arguments[0].click();", login_btn)
                print("✅ 点击了登录按钮")
            else:
                print("⚠️ 未找到显式的登录按钮，尝试直接寻找输入框")
        except Exception as e:
            print(f"⚠️ 点击登录按钮出错: {e}")
            
        time.sleep(3)
        
        # 1. 输入邮箱
        print("📧 输入邮箱...")
        # 增加等待时间
        email_input = wait.until(EC.visibility_of_element_located((
            By.CSS_SELECTOR, 
            'input[name="username"], input[name="email"], input[id="email-input"]'
        )))
        email_input.clear()
        type_slowly(email_input, email)
        
        # 点击继续
        print("🔘 点击继续...")
        continue_btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"], button[class*="continue-btn"]')
        continue_btn.click()
        time.sleep(3)
        
        # ⚠️ 关键修正：检查是否进入了验证码模式，如果是，切换回密码模式
        print("🔍 检查登录方式...")
        try:
            # 寻找所有包含 "密码" 或 "Password" 的文本元素，只要它们看起来像链接或按钮
            # 排除掉密码输入框本身的 label
            switch_candidates = driver.find_elements(By.XPATH, 
                '//*[contains(text(), "密码") or contains(text(), "Password")]'
            )
            
            clicked_switch = False
            for el in switch_candidates:
                if not el.is_displayed():
                    continue
                    
                tag_name = el.tag_name.lower()
                text = el.text
                
                # 排除 label 和 title
                if tag_name in ['h1', 'h2', 'label', 'span'] and '输入' not in text and 'Enter' not in text and '使用' not in text:
                    continue
                    
                # 尝试点击看起来像切换链接的元素
                if '输入密码' in text or 'Enter password' in text or '使用密码' in text or 'password instead' in text:
                    print(f"⚠️ 尝试点击切换链接: '{text}' ({tag_name})...")
                    try:
                        el.click()
                        clicked_switch = True
                        time.sleep(2)
                        break
                    except:
                        # 可能是被遮挡，尝试 JS 点击
                        driver.execute_script("arguments[0].click();", el)
                        clicked_switch = True
                        time.sleep(2)
                        break
            
            if not clicked_switch:
                print("  ℹ️ 未找到明显的'切换密码'链接，假设在密码输入页或强制验证码页")
                
        except Exception as e:
            print(f"  检查登录方式出错: {e}")
        
        # 2. 输入密码
        print("🔑 等待密码输入框...")
        try:
            password_input = wait.until(EC.visibility_of_element_located((
                By.CSS_SELECTOR, 
                'input[name="password"], input[type="password"]'
            )))
            password_input.clear()
            type_slowly(password_input, password)
            
            # 点击继续/登录
            print("🔘 点击登录...")
            continue_btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"], button[name="action"]')
            continue_btn.click()
            
            print("⏳ 等待登录完成...")
            time.sleep(10)
        
        except Exception as e:
            print("❌ 未找到密码输入框。")
            print("  可能原因: 1. 强制验证码登录; 2. 页面加载过慢; 3. 选择器失效")
            print("  尝试手动干预或检查页面...")
            raise e # 抛出异常以终止测试
        
        # 检查是否登录成功
        if "auth" not in driver.current_url:
            print("✅ 登录成功")
            return True
        else:
            print("⚠️ 可能还在登录页面 (URL包含 auth)")
            # 再次检查是否有错误提示
            try:
                err = driver.find_element(By.CSS_SELECTOR, '.error-message, [role="alert"]')
                print(f"❌登录错误提示: {err.text}")
            except:
                pass
            return True
    except InterruptedError:
        raise
    except Exception as e:
        print(f"❌ 登录失败: {e}")
        return False


def enter_verification_code(driver, code: str):
    """
    输入验证码
    
    参数:
        driver: 浏览器驱动
        code: 验证码
    
    返回:
        bool: 是否成功
    """
    try:
        print("🔢 正在输入验证码...")
        
        # 先检查错误
        while check_and_handle_error(driver):
            time.sleep(2)
        
        code_input = WebDriverWait(driver, 60).until(
            EC.visibility_of_element_located((
                By.CSS_SELECTOR, 
                'input[name="code"], input[placeholder*="代码"], input[aria-label*="代码"]'
            ))
        )
        code_input.clear()
        time.sleep(0.5)
        type_slowly(code_input, code, delay=0.1)
        print(f"✅ 已输入验证码: {code}")
        time.sleep(2)
        
        # 点击继续
        print("🔘 点击继续按钮...")
        if not click_button_with_retry(driver, 'button[type="submit"]'):
            print("❌ 点击继续按钮失败")
            return False
        print("✅ 已点击继续")
        
        time.sleep(3)
        while check_and_handle_error(driver):
            time.sleep(2)
        
        return True
    except InterruptedError:
        raise
    except Exception as e:
        print(f"❌ 输入验证码失败: {e}")
        return False


def click_resend_verification_email(driver):
    """
    点击验证码页面的“重新发送电子邮件”按钮。

    参数:
        driver: 浏览器驱动

    返回:
        bool: 是否点击成功
        AI by zb
    """
    print("📨 尝试点击“重新发送电子邮件”按钮...")
    button_xpaths = [
        '//button[contains(normalize-space(.), "重新发送电子邮件")]',
        '//button[contains(normalize-space(.), "重新发送邮件")]',
        '//button[contains(normalize-space(.), "重新发送")]',
        '//button[contains(normalize-space(.), "Resend email")]',
        '//button[contains(normalize-space(.), "Resend")]',
        '//*[@role="button"][contains(normalize-space(.), "重新发送电子邮件")]',
        '//*[@role="button"][contains(normalize-space(.), "重新发送")]',
        '//*[@role="button"][contains(normalize-space(.), "Resend email")]',
        '//*[@role="button"][contains(normalize-space(.), "Resend")]',
        '//a[contains(normalize-space(.), "重新发送电子邮件")]',
        '//a[contains(normalize-space(.), "重新发送")]',
        '//a[contains(normalize-space(.), "Resend email")]',
        '//a[contains(normalize-space(.), "Resend")]',
    ]

    deadline = time.time() + 15
    try:
        while time.time() < deadline:
            while check_and_handle_error(driver):
                time.sleep(1)

            for xpath in button_xpaths:
                elements = driver.find_elements(By.XPATH, xpath)
                for element in elements:
                    if not element.is_displayed():
                        continue

                    try:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});",
                            element
                        )
                        time.sleep(0.5)
                        if element.is_enabled():
                            try:
                                element.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", element)
                            button_text = str(element.text or "").strip() or "重新发送电子邮件"
                            print(f"✅ 已点击按钮: {button_text}")
                            time.sleep(2)
                            return True
                    except Exception:
                        continue

            time.sleep(1)
    except InterruptedError:
        raise
    except Exception as e:
        print(f"⚠️ 点击“重新发送电子邮件”按钮失败: {e}")
        return False

    print("⚠️ 未找到“重新发送电子邮件”按钮")
    return False


def fill_profile_info(driver):
    """
    填写用户资料（随机生成的姓名和年龄相关字段）
    
    参数:
        driver: 浏览器驱动
    
    返回:
        bool: 是否成功
    """
    wait = WebDriverWait(driver, MAX_WAIT_TIME)
    
    # 生成随机用户信息
    user_info = generate_user_info()
    user_name = user_info['name']
    birthday_year = user_info['year']
    birthday_month = user_info['month']
    birthday_day = user_info['day']
    user_age = _calculate_age_from_birthdate(birthday_year, birthday_month, birthday_day)
    
    try:
        # 1. 输入姓名
        print("👤 等待姓名输入框...")
        name_input = _wait_profile_input(
            driver,
            'input[name="name"], input[autocomplete="name"]',
            "姓名",
            timeout=60,
        )
        _fill_profile_text_input(driver, name_input, user_name, "姓名")
        print(f"✅ 已输入姓名: {user_name}")
        time.sleep(1)

        # 2. 按实际字段结构填写年龄信息
        profile_mode = _wait_profile_form_mode(driver, timeout_seconds=10)
        if profile_mode == "age":
            print("🎯 当前资料页为年龄输入模式，正在输入年龄...")
            _fill_profile_age_field(driver, user_age)
            print(f"✅ 已输入年龄: {user_age}")
        else:
            print("🎂 当前资料页为生日输入模式，正在输入生日...")
            _fill_birthdate_fields(driver, birthday_year, birthday_month, birthday_day)
            print(f"✅ 已输入生日: {birthday_year}/{birthday_month}/{birthday_day}")
        time.sleep(1)
        
        # 3. 点击最后的继续按钮
        print("🔘 点击最终提交按钮...")
        before_submit_url = str(driver.current_url or "")
        continue_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
        )
        try:
            continue_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", continue_btn)
        print("✅ 已提交注册信息")

        if not _wait_profile_submission_success(driver, before_submit_url, profile_mode=profile_mode):
            raise RuntimeError("资料页提交后仍停留在当前表单，未检测到成功跳转")
        
        return True
    except InterruptedError:
        raise
    except Exception as e:
        print(f"❌ 填写资料失败: {e}")
        return False


def _calculate_age_from_birthdate(year: str, month: str, day: str) -> str:
    """
    根据生日计算当前年龄，保证年龄页与生日页使用同一份随机资料。

    参数:
        year: 年份
        month: 月份
        day: 日期
    返回:
        str: 当前年龄
        AI by zb
    """
    try:
        birth_year = int(str(year).strip())
        birth_month = int(str(month).strip())
        birth_day = int(str(day).strip())
        today = date.today()
        age_value = today.year - birth_year - ((today.month, today.day) < (birth_month, birth_day))
        return str(max(age_value, 0))
    except Exception:
        try:
            return str(max(date.today().year - int(str(year).strip()), 0))
        except Exception:
            return "18"


def _detect_profile_form_mode(driver) -> str:
    """
    根据资料页实际可见字段识别当前表单模式。

    参数:
        driver: 浏览器驱动
    返回:
        str: `birthdate` / `age` / 空字符串
        AI by zb
    """
    birthdate_input = _find_first_visible_element(
        driver,
        By.CSS_SELECTOR,
        ['[data-type="year"]', '[data-type="month"]', '[data-type="day"]'],
    )
    if birthdate_input:
        return "birthdate"

    if _find_profile_age_input(driver):
        return "age"

    return ""


def _wait_profile_form_mode(driver, timeout_seconds: int = 10) -> str:
    """
    等待资料页字段稳定出现，并识别应填写生日还是年龄。

    参数:
        driver: 浏览器驱动
        timeout_seconds: 最大等待时长
    返回:
        str: `birthdate` 或 `age`
        AI by zb
    """
    deadline = time.time() + max(int(timeout_seconds or 0), 1)
    while time.time() < deadline:
        profile_mode = _detect_profile_form_mode(driver)
        if profile_mode:
            return profile_mode

        while check_and_handle_error(driver):
            time.sleep(1)
        time.sleep(0.4)

    print("⚠️ 未能及时识别资料页字段模式，默认按生日模式处理")
    return "birthdate"


def _find_profile_age_input(driver):
    """
    查找资料页中的年龄输入框，仅按实际字段结构判断，不依赖页面标题文案。

    参数:
        driver: 浏览器驱动
    返回:
        WebElement | None: 年龄输入框
        AI by zb
    """
    age_css_selectors = [
        'input[name="age"]',
        'input[id*="age"]',
        'input[autocomplete="age"]',
        'input[aria-label*="年龄"]',
        'input[placeholder*="年龄"]',
        'input[aria-label*="Age"]',
        'input[placeholder*="Age"]',
        'input[aria-label*="age"]',
        'input[placeholder*="age"]',
    ]
    explicit_age_input = _find_first_visible_element(driver, By.CSS_SELECTOR, age_css_selectors)
    if explicit_age_input:
        return explicit_age_input

    age_xpaths = [
        '//*[self::label or self::div or self::span][normalize-space(.)="年龄"]/following::*[self::input or self::textarea][1]',
        '//*[self::label or self::div or self::span][translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")="age"]/following::*[self::input or self::textarea][1]',
    ]
    explicit_age_input = _find_first_visible_element(driver, By.XPATH, age_xpaths)
    if explicit_age_input:
        return explicit_age_input

    if _find_first_visible_element(
        driver,
        By.CSS_SELECTOR,
        ['[data-type="year"]', '[data-type="month"]', '[data-type="day"]'],
    ):
        return None

    name_input = _find_first_visible_element(
        driver,
        By.CSS_SELECTOR,
        ['input[name="name"]', 'input[autocomplete="name"]'],
    )
    name_editable = _resolve_profile_editable_element(name_input) if name_input else None
    has_age_related_text = _page_contains_any_text(
        driver,
        ["年龄", "how old are you", "confirm your age", "你的年龄是多少", "确认一下你的年龄"],
    )
    if not name_editable and not has_age_related_text:
        return None

    try:
        candidates = driver.find_elements(
            By.CSS_SELECTOR,
            'input:not([type="hidden"]):not([type="submit"]):not([type="email"]):not([type="password"]), textarea',
        )
    except Exception:
        return None

    fallback_candidates = []
    for candidate in candidates:
        try:
            editable = _resolve_profile_editable_element(candidate)
            if not editable.is_displayed() or not editable.is_enabled():
                continue

            if name_editable and getattr(editable, "id", "") == getattr(name_editable, "id", ""):
                continue

            data_type = str(
                editable.get_attribute("data-type")
                or candidate.get_attribute("data-type")
                or ""
            ).strip().lower()
            if data_type in {"year", "month", "day"}:
                continue

            field_hint = " ".join(
                [
                    str(editable.get_attribute("name") or ""),
                    str(editable.get_attribute("autocomplete") or ""),
                    str(editable.get_attribute("aria-label") or ""),
                    str(editable.get_attribute("placeholder") or ""),
                ]
            ).strip().lower()
            if any(keyword in field_hint for keyword in ("name", "full name", "姓名", "全名")):
                continue

            input_type = str(editable.get_attribute("type") or "").strip().lower()
            input_mode = str(editable.get_attribute("inputmode") or "").strip().lower()
            if input_type == "number" or input_mode == "numeric":
                return editable

            fallback_candidates.append(editable)
        except Exception:
            continue

    if len(fallback_candidates) == 1:
        return fallback_candidates[0]
    return None


def _wait_profile_age_input(driver, timeout: int = 30):
    """
    等待资料页年龄输入框可见并返回元素。

    参数:
        driver: 浏览器驱动
        timeout: 超时时间
    返回:
        WebElement: 年龄输入框
        AI by zb
    """
    deadline = time.time() + max(int(timeout or 0), 1)
    while time.time() < deadline:
        age_input = _find_profile_age_input(driver)
        if age_input:
            return age_input

        while check_and_handle_error(driver):
            time.sleep(1)
        time.sleep(0.4)

    raise RuntimeError("年龄输入框未出现")


def _fill_profile_age_field(driver, age: str):
    """
    填写并校验年龄字段，避免年龄页仍按生日页流程处理。

    参数:
        driver: 浏览器驱动
        age: 年龄值
        AI by zb
    """
    expected_value = str(age).strip()
    for attempt in range(1, 4):
        age_input = _wait_profile_age_input(driver, timeout=30)
        _fill_profile_text_input(
            driver,
            age_input,
            expected_value,
            "年龄",
            focus_pause_seconds=0.5,
            before_type_pause_seconds=0.1,
            strategies=("keyboard", "native", "keyboard"),
            typing_delay=0.12,
            manual_clear_only=False,
            blur_after_input=True,
        )
        time.sleep(0.3)

        actual_value = _read_profile_element_value(
            _resolve_profile_editable_element(_wait_profile_age_input(driver, timeout=5))
        )
        if actual_value == expected_value:
            return

        print(f"⚠️ 年龄校验失败，第 {attempt}/3 次实际值: {actual_value or '?'}")

    raise RuntimeError(f"年龄输入后校验失败，当前值为: {actual_value or '?'}")


def _wait_profile_input(driver, selector: str, field_name: str, timeout: int = 30):
    """
    等待资料页输入框可见并返回元素。

    参数:
        driver: 浏览器驱动
        selector: CSS 选择器
        field_name: 字段名
        timeout: 超时时间
    返回:
        WebElement: 输入框元素
        AI by zb
    """
    try:
        return WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
        )
    except Exception as exc:
        raise RuntimeError(f"{field_name}输入框未出现") from exc


def _fill_profile_text_input(
    driver,
    element,
    value: str,
    field_name: str,
    focus_pause_seconds: float = 0.2,
    before_type_pause_seconds: float = 0.0,
    strategies: tuple[str, ...] | None = None,
    typing_delay: float = 0.05,
    manual_clear_only: bool = False,
    blur_after_input: bool = True,
):
    """
    强韧填写资料页文本输入框。

    参数:
        driver: 浏览器驱动
        element: 输入框元素
        value: 要填写的值
        field_name: 字段名
        focus_pause_seconds: 聚焦后的稳定等待时长
        before_type_pause_seconds: 输入前额外等待时长
        strategies: 输入策略顺序
        typing_delay: 手动输入时的逐字间隔
        manual_clear_only: 是否只允许手动清空，不使用脚本写值
        blur_after_input: 输入后是否立刻失焦
        AI by zb
    """
    target_element = _resolve_profile_editable_element(element)
    expected_value = str(value).strip()
    if not strategies:
        strategies = ("native", "keyboard", "native")

    for strategy in strategies:
        try:
            _focus_profile_input(driver, target_element, focus_pause_seconds)

            if strategy == "native":
                _set_profile_input_value(driver, target_element, "")
                if before_type_pause_seconds:
                    time.sleep(max(float(before_type_pause_seconds or 0), 0.0))
                _set_profile_input_value(driver, target_element, expected_value)
            else:
                _clear_profile_input(driver, target_element, manual_only=manual_clear_only)
                if before_type_pause_seconds:
                    time.sleep(max(float(before_type_pause_seconds or 0), 0.0))
                type_slowly(target_element, expected_value, delay=typing_delay)

            if blur_after_input:
                time.sleep(0.2)
                _blur_profile_input(driver, target_element)
                time.sleep(0.35)
            else:
                time.sleep(0.15)

            current_value = _read_profile_element_value(target_element)
            if current_value == expected_value:
                return
        except Exception:
            pass

    raise RuntimeError(f"{field_name}填写失败")


def _resolve_profile_editable_element(element):
    """
    获取资料页字段对应的真实可编辑节点。

    参数:
        element: 字段元素或其容器
    返回:
        WebElement: 可直接输入的节点
        AI by zb
    """
    try:
        tag_name = str(element.tag_name or "").strip().lower()
        if tag_name in {"input", "textarea"}:
            return element
    except Exception:
        pass

    try:
        editable_candidates = element.find_elements(
            By.CSS_SELECTOR,
            'input:not([type="hidden"]), textarea, [contenteditable="true"]',
        )
        for candidate in editable_candidates:
            try:
                if candidate.is_displayed():
                    return candidate
            except Exception:
                continue
    except Exception:
        pass

    return element


def _focus_profile_input(driver, element, focus_pause_seconds: float):
    """
    聚焦资料页输入节点，并等待页面稳定。

    参数:
        driver: 浏览器驱动
        element: 可编辑节点
        focus_pause_seconds: 聚焦后等待时长
        AI by zb
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    except Exception:
        pass

    time.sleep(0.3)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    time.sleep(max(float(focus_pause_seconds or 0), 0.0))


def _clear_profile_input(driver, element, manual_only: bool = False):
    """
    清空资料页输入节点当前值。

    参数:
        driver: 浏览器驱动
        element: 可编辑节点
        manual_only: 是否只允许手动清空
        AI by zb
    """
    try:
        element.clear()
    except Exception:
        pass

    for _ in range(8):
        try:
            element.send_keys(Keys.BACKSPACE)
            time.sleep(0.02)
        except Exception:
            break

    for _ in range(4):
        try:
            element.send_keys(Keys.DELETE)
            time.sleep(0.02)
        except Exception:
            break

    try:
        element.send_keys(Keys.CONTROL + "a")
        element.send_keys(Keys.BACKSPACE)
    except Exception:
        pass

    if not manual_only:
        try:
            _set_profile_input_value(driver, element, "")
        except Exception:
            pass


def _set_profile_input_value(driver, element, value: str):
    """
    通过原生 setter 与事件分发写入资料页字段。

    参数:
        driver: 浏览器驱动
        element: 可编辑节点
        value: 目标值
        AI by zb
    """
    driver.execute_script(
        """
        const el = arguments[0];
        const nextValue = arguments[1];
        el.focus();

        if (el.isContentEditable) {
            el.textContent = nextValue;
        } else {
            const prototype = Object.getPrototypeOf(el);
            const valueSetter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
            if (valueSetter) {
                valueSetter.call(el, nextValue);
            } else {
                el.value = nextValue;
            }
        }

        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        element,
        str(value),
    )


def _blur_profile_input(driver, element):
    """
    让资料页输入节点失焦，促使页面提交分段字段状态。

    参数:
        driver: 浏览器驱动
        element: 可编辑节点
        AI by zb
    """
    try:
        driver.execute_script("arguments[0].blur();", element)
    except Exception:
        pass

    try:
        body = driver.find_element(By.TAG_NAME, "body")
        driver.execute_script("arguments[0].click();", body)
    except Exception:
        pass


def _read_profile_element_value(element) -> str:
    """
    读取资料页字段当前值，优先读取输入值，再回退到可见文本。

    参数:
        element: 可编辑节点
    返回:
        str: 当前值
        AI by zb
    """
    try:
        value = str(element.get_attribute("value") or "").strip()
        if value:
            return value
    except Exception:
        pass

    try:
        text = str(element.text or "").strip()
        if text:
            return text
    except Exception:
        pass

    try:
        return str(element.get_attribute("textContent") or "").strip()
    except Exception:
        return ""


def _fill_profile_segment(
    driver,
    selector: str,
    value: str,
    field_name: str,
    blur_after_input: bool = True,
    verify_immediately: bool = True,
):
    """
    填写资料页分段日期输入框。

    参数:
        driver: 浏览器驱动
        selector: CSS 选择器
        value: 要填写的值
        field_name: 字段名
        blur_after_input: 输入后是否立刻失焦
        verify_immediately: 是否在单字段输入后立即校验
        AI by zb
    """
    element = _wait_profile_input(driver, selector, field_name, timeout=30)
    print(f"⏳ {field_name}输入框已聚焦，等待稳定后再输入...")
    _fill_profile_text_input(
        driver,
        element,
        value,
        field_name,
        focus_pause_seconds=0.65,
        before_type_pause_seconds=0.2,
        strategies=("keyboard", "keyboard", "keyboard"),
        typing_delay=0.16,
        manual_clear_only=True,
        blur_after_input=blur_after_input,
    )

    if verify_immediately:
        current_value = _read_profile_element_value(_resolve_profile_editable_element(element))
        if current_value != str(value).strip():
            raise RuntimeError(f"{field_name}校验失败，当前值为: {current_value}")

    time.sleep(0.4)


def _read_profile_input_value(driver, selector: str) -> str:
    """
    读取资料页输入框当前值。

    参数:
        driver: 浏览器驱动
        selector: CSS 选择器
    返回:
        str: 当前值
        AI by zb
    """
    try:
        element = driver.find_element(By.CSS_SELECTOR, selector)
        return _read_profile_element_value(_resolve_profile_editable_element(element))
    except Exception:
        return ""


def _fill_birthdate_fields(driver, year: str, month: str, day: str):
    """
    填写并校验生日字段；若发现字段被页面吞字，会自动重试一次。

    参数:
        driver: 浏览器驱动
        year: 年份
        month: 月份
        day: 日期
        AI by zb
    """
    expected = (str(year).strip(), str(month).strip(), str(day).strip())
    field_specs = [
        ("年份", '[data-type="year"]', expected[0]),
        ("月份", '[data-type="month"]', expected[1]),
        ("日期", '[data-type="day"]', expected[2]),
    ]

    for field_name, selector, value in field_specs:
        _fill_profile_segment(
            driver,
            selector,
            value,
            field_name,
            blur_after_input=False,
            verify_immediately=False,
        )

    for attempt in range(1, 4):
        _commit_birthdate_fields(driver)
        time.sleep(0.6)
        actual = _read_birthdate_values(driver)
        if actual == expected:
            return

        print(
            f"⚠️ 生日校验失败，第 {attempt}/3 次实际值: "
            f"{actual[0] or '?'} / {actual[1] or '?'} / {actual[2] or '?'}"
        )

        mismatched_fields = [
            (field_name, selector, expected_value)
            for index, (field_name, selector, expected_value) in enumerate(field_specs)
            if actual[index] != expected_value
        ]
        if not mismatched_fields:
            continue

        print(
            "🔧 仅修正异常字段: "
            + " / ".join(field_name for field_name, _, _ in mismatched_fields)
        )
        for field_name, selector, expected_value in mismatched_fields:
            _fill_profile_segment(
                driver,
                selector,
                expected_value,
                field_name,
                blur_after_input=False,
                verify_immediately=False,
            )

    raise RuntimeError(
        f"生日输入后校验失败，当前值为: {actual[0] or '?'} / {actual[1] or '?'} / {actual[2] or '?'}"
    )


def _read_birthdate_values(driver) -> tuple[str, str, str]:
    """
    读取生日三个分段字段的当前值。

    参数:
        driver: 浏览器驱动
    返回:
        tuple[str, str, str]: 年、月、日
        AI by zb
    """
    return (
        _read_profile_input_value(driver, '[data-type="year"]'),
        _read_profile_input_value(driver, '[data-type="month"]'),
        _read_profile_input_value(driver, '[data-type="day"]'),
    )


def _commit_birthdate_fields(driver):
    """
    触发生日字段的失焦与状态提交，避免点击提交时页面才回写旧值。

    参数:
        driver: 浏览器驱动
        AI by zb
    """
    try:
        day_element = driver.find_element(By.CSS_SELECTOR, '[data-type="day"]')
        editable = _resolve_profile_editable_element(day_element)
        try:
            editable.send_keys(Keys.TAB)
        except Exception:
            _blur_profile_input(driver, editable)
    except Exception:
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            body.click()
        except Exception:
            pass


def _profile_submission_has_error(driver) -> str:
    """
    检查资料页提交后是否出现明显错误提示。

    参数:
        driver: 浏览器驱动
    返回:
        str: 错误摘要；为空表示暂未发现
        AI by zb
    """
    try:
        error_elements = driver.find_elements(
            By.XPATH,
            '//*[contains(normalize-space(.), "出错了") or contains(normalize-space(.), "要重试吗") or contains(normalize-space(.), "Something went wrong") or contains(normalize-space(.), "Try again")]',
        )
        for element in error_elements:
            if element.is_displayed():
                return str(element.text or "").strip() or "资料页出现错误提示"
    except Exception:
        pass

    for selector in ('[data-type="year"][aria-invalid="true"]', '[data-type="month"][aria-invalid="true"]', '[data-type="day"][aria-invalid="true"]'):
        try:
            if driver.find_elements(By.CSS_SELECTOR, selector):
                return f"字段校验失败: {selector}"
        except Exception:
            continue

    age_input = _find_profile_age_input(driver)
    if age_input:
        try:
            if str(age_input.get_attribute("aria-invalid") or "").strip().lower() == "true":
                return "字段校验失败: 年龄"
        except Exception:
            pass

    return ""


def _profile_form_still_visible(driver, profile_mode: str) -> bool:
    """
    判断资料页表单是否仍停留在当前页面，兼容生日页与年龄页两种结构。

    参数:
        driver: 浏览器驱动
        profile_mode: 资料页模式
    返回:
        bool: 是否仍能看到当前资料页表单
        AI by zb
    """
    if str(profile_mode or "").strip().lower() == "age":
        return _find_profile_age_input(driver) is not None

    return _find_first_visible_element(
        driver,
        By.CSS_SELECTOR,
        ['[data-type="year"]', '[data-type="month"]', '[data-type="day"]'],
    ) is not None


def _wait_profile_submission_success(driver, before_submit_url: str, profile_mode: str = "birthdate") -> bool:
    """
    等待资料页真正提交成功，避免仅点击按钮就误判为成功。

    参数:
        driver: 浏览器驱动
        before_submit_url: 提交前 URL
        profile_mode: 资料页模式
    返回:
        bool: 是否确认成功
        AI by zb
    """
    deadline = time.time() + 15
    while time.time() < deadline:
        error_text = _profile_submission_has_error(driver)
        if error_text:
            raise RuntimeError(error_text)

        current_url = str(driver.current_url or "")
        if current_url and current_url != before_submit_url and "auth" not in current_url:
            return True

        try:
            if driver.find_elements(By.ID, "prompt-textarea"):
                return True
        except Exception:
            pass

        if not _profile_form_still_visible(driver, profile_mode):
            return True

        time.sleep(0.5)

    return False


def handle_stripe_input(driver, field_name, input_selectors, value):
    """
    智能填写 Stripe 字段
    逻辑：先在主文档找 -> 找不到则递归遍历所有 iframe 找
    """
    selectors = [s.strip() for s in input_selectors.split(',')]
    
    # 辅助函数：在当前上下文尝试查找并输入
    def try_fill():
        for selector in selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                if el.is_displayed():
                    # 滚动到可见
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                    except:
                        pass
                    type_slowly(el, value)
                    return True
            except:
                continue
        return False

    # 1. 尝试主文档
    if try_fill():
        print(f"  ✅ 在主文档找到 {field_name}")
        return True
        
    # 2. 递归遍历 iframe (支持 2 层嵌套)
    def traverse_frames(driver, depth=0, max_depth=2):
        if depth >= max_depth:
            return False
            
        # 获取当前上下文的所有 iframe
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        
        for i, frame in enumerate(frames):
            try:
                # 只有可见的 iframe 才可能是包含输入框的
                if not frame.is_displayed():
                    continue
                    
                driver.switch_to.frame(frame)
                
                # 尝试在当前 frame 填写
                if try_fill():
                    print(f"  ✅ 在 iframe (d={depth}, i={i}) 中找到 {field_name}")
                    driver.switch_to.default_content() # 找到后彻底重置回主文档
                    return True
                
                # 递归查找子 frame
                if traverse_frames(driver, depth + 1, max_depth):
                    return True
                    
                # 回退到父 frame
                driver.switch_to.parent_frame()
                
            except Exception as e:
                # 发生异常，尝试回退并继续
                try: driver.switch_to.parent_frame()
                except: pass
                continue
        
        return False

    driver.switch_to.default_content()
    if traverse_frames(driver):
        return True
                
    print(f"  ❌ 未找到 {field_name}")
    return False


def subscribe_plus_trial(driver):
    """
    订阅 ChatGPT Plus 免费试用 (日本地址版)
    """
    print("\n" + "=" * 50)
    print("💳 开始 Plus 试用订阅流程")
    print("   将自动检测页面国家并生成对应地址")
    print("=" * 50)
    
    wait = WebDriverWait(driver, 30)
    
    try:
        # 1. 访问 Pricing 页面
        url = "https://chatgpt.com/#pricing"
        print(f"🌐 正在打开 {url}...")
        driver.get(url)
        time.sleep(5)
        
        # 2. 点击 Plus 订阅按钮 (确保选择 Plus 而不是 Team)
        print("🔘 寻找 Plus 订阅按钮...")
        subscribe_btn = None
        
        def find_and_click_subscribe(retry_count=0):
            if retry_count > 3: return False

            # 尝试清理路上的弹窗：Next, Back, Done, Okay, Tips, Get started
            # 新用户的导览通常是一系列的，需要循环清理
            try:
                print("  🧹 扫描并清理可能的导览弹窗...")
                for _ in range(3): # 最多尝试清理3次（针对多步导览）
                    # 查找虽然不是 Plus 按钮，但是像导览控制的按钮
                    # 增加中文关键词：下一步，知道了，开始，跳过，好的，明白
                    guides = driver.find_elements(By.XPATH, '//button[contains(., "Next") or contains(., "Okay") or contains(., "Done") or contains(., "Start") or contains(., "Get started") or contains(., "Next tip") or contains(., "Later") or contains(., "下一步") or contains(., "知道了") or contains(., "开始") or contains(., "跳过") or contains(., "好的") or contains(., "Got it") or contains(., "Close") or contains(., "Dismiss")]')
                    
                    clicked_any = False
                    for btn in guides:
                        if btn.is_displayed():
                            txt = btn.text.lower()
                            # 排除掉升级按钮本身
                            if "upgrade" not in txt and "plus" not in txt and "trial" not in txt:
                                try:
                                    driver.execute_script("arguments[0].click();", btn)
                                    print(f"    -> 点击了导览按钮: {btn.text}")
                                    time.sleep(0.5)
                                    clicked_any = True
                                except: pass
                    
                    if not clicked_any:
                        break
                    time.sleep(1)
            except:
                pass

            # 确保在 Personal/个人 标签页（不是 Business/Team）
            try:
                print("  🔘 确保选择 个人 标签...")
                # 查找并点击 个人 标签（排除 Business）
                tabs = driver.find_elements(By.XPATH, '//button')
                for tab in tabs:
                    txt = tab.text.strip()
                    # 精确匹配 "个人" 或 "Personal"，排除 Business
                    if txt in ['个人', 'Personal'] and 'Business' not in txt:
                        if tab.is_displayed():
                            driver.execute_script("arguments[0].click();", tab)
                            print(f"  -> 已点击 '{txt}' 标签")
                            time.sleep(1)
                            break
            except Exception as e:
                print(f"  ⚠️ 切换个人标签时: {e}")

            # 寻找 Plus 套餐的 "领取免费试用" 按钮
            # 页面结构：三列（免费版、Plus、Pro），我们要点中间那个
            print("  🔘 寻找 Plus 套餐的订阅按钮...")
            buttons_xpaths = [
                # 优先：中间的 Plus 卡片内的按钮
                '//div[contains(., "Plus") and contains(., "$20")]//button[contains(., "领取免费试用") or contains(., "Start trial") or contains(., "Get Plus")]',
                '//button[contains(., "领取免费试用")]',  # 中文版
                '//button[contains(., "Get Plus")]',
                '//button[contains(., "Start trial")]',
                '//button[contains(., "Upgrade to Plus")]'
            ]
            
            for xpath in buttons_xpaths:
                try:
                    btns = driver.find_elements(By.XPATH, xpath)
                    for btn in btns:
                        if btn.is_displayed():
                            print(f"  找到按钮: {btn.text}")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(1)
                            try:
                                btn.click()
                                return True
                            except Exception as e:
                                print(f"  ⚠️ 点击被拦截，尝试再次清理弹窗... {e}")
                                # 递归重试
                                time.sleep(2)
                                return find_and_click_subscribe(retry_count + 1)
                except:
                    continue
            
            # 如果还没找到，可能是弹窗层级太深，或者需要刷新
            if retry_count == 0:
                 print("  ⚠️ 未直接找到按钮，尝试刷新页面...")
                 driver.refresh()
                 time.sleep(5)
                 return find_and_click_subscribe(retry_count + 1)
                 
            return False

        if not find_and_click_subscribe():
             print("❌ 经多次重试仍未找到 Plus 订阅按钮")
             try: driver.save_screenshot("debug_no_plus_btn.png")
             except: pass
             return False
        
        print("✅ 已点击 Plus 订阅按钮")     
            
        print("⏳ 等待支付页面加载 (智能检测)...")
        # 替换固定的 sleep(10)，改为动态监测表单元素
        page_loaded = False
        start_wait = time.time()
        while time.time() - start_wait < 30:
            # 检查是否有输入框或 iframe
            inputs = driver.find_elements(By.CSS_SELECTOR, "input, iframe")
            if len(inputs) > 3:
                # 进一步检查是否有支付相关的特征
                page_source = driver.page_source.lower()
                if "stripe" in page_source or "card" in page_source or "payment" in page_source or "支付" in page_source:
                    print("  ✅ 检测到支付表单元素，页面已就绪")
                    page_loaded = True
                    break
            time.sleep(1)
        
        if not page_loaded:
            print("⚠️ 页面加载似乎超时，尝试继续填写...")
        
        time.sleep(2) # 额外缓冲
        
        # -------------------------------------------------------------------------
        # 3. 填写支付表单
        # -------------------------------------------------------------------------
        print("💳 开始填写支付信息...")
        wait_input = WebDriverWait(driver, 15)
        
        # 辅助函数：在当前上下文查找元素
        def find_visible(selector):
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                if el.is_displayed(): return el
            except: 
                pass
            try:
                el = driver.find_element(By.XPATH, selector) # 兼容 XPATH
                if el.is_displayed(): return el
            except:
                pass
            return None

        def find_visible_in_list(selectors):
            for selector in selectors:
                el = find_visible(selector)
                if el:
                    return el
            return None

        def wait_for_visible_in_list(selectors, timeout: float = 8.0, poll_interval: float = 0.25):
            """
            等待候选控件出现并可见。

            参数:
                selectors: 候选选择器列表
                timeout: 最长等待时间（秒）
                poll_interval: 轮询间隔（秒）
            返回:
                WebElement | None: 命中的控件
                AI by zb
            """
            deadline = time.time() + max(timeout, 0)
            while time.time() <= deadline:
                element = find_visible_in_list(selectors)
                if element:
                    return element
                time.sleep(poll_interval)
            return None

        def normalize_field_text(value: str) -> str:
            return re.sub(r"[\s\-_/]+", "", str(value or "").strip().lower())

        def value_matches_candidates(value: str, candidates: list[str]) -> bool:
            """
            判断字段当前值是否已匹配目标候选值。

            参数:
                value: 当前字段值
                candidates: 候选值列表
            返回:
                bool: 是否匹配
                AI by zb
            """
            normalized_value = normalize_field_text(value)
            if not normalized_value:
                return False
            for candidate in candidates:
                normalized_candidate = normalize_field_text(candidate)
                if normalized_candidate and (
                    normalized_value == normalized_candidate
                    or normalized_candidate in normalized_value
                    or normalized_value in normalized_candidate
                ):
                    return True
            return False

        def clear_and_type_value(element, value: str, delay: float = 0.06):
            try:
                element.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                except Exception:
                    pass
            try:
                element.send_keys(Keys.CONTROL + "a")
                element.send_keys(Keys.BACKSPACE)
            except Exception:
                try:
                    element.clear()
                except Exception:
                    pass
            type_slowly(element, value, delay=delay)

        def read_element_value(element) -> str:
            for attr_name in ["value", "data-value", "aria-valuetext", "aria-label"]:
                try:
                    value = str(element.get_attribute(attr_name) or "").strip()
                    if value:
                        return value
                except Exception:
                    pass
            try:
                text = str(element.text or "").strip()
                if text:
                    return text
            except Exception:
                pass
            return ""

        def select_form_value(element, candidates: list[str]) -> bool:
            candidate_values = [str(item).strip() for item in candidates if str(item).strip()]
            if not candidate_values:
                return False

            if value_matches_candidates(read_element_value(element), candidate_values):
                return True

            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            except Exception:
                pass

            try:
                if element.tag_name.lower() == "select":
                    select = Select(element)
                    options = [
                        (
                            str(option.text or "").strip(),
                            str(option.get_attribute("value") or "").strip(),
                        )
                        for option in select.options
                    ]
                    for candidate in candidate_values:
                        normalized_candidate = normalize_field_text(candidate)
                        for text, value in options:
                            if (
                                normalize_field_text(text) == normalized_candidate
                                or normalize_field_text(value) == normalized_candidate
                            ):
                                try:
                                    select.select_by_visible_text(text)
                                except Exception:
                                    select.select_by_value(value)
                                time.sleep(0.5)
                                if value_matches_candidates(
                                    read_element_value(element),
                                    candidate_values + [text, value],
                                ):
                                    return True
            except Exception:
                pass

            for candidate in candidate_values:
                try:
                    clear_and_type_value(element, candidate)
                    time.sleep(0.5)
                    try:
                        element.send_keys(Keys.ARROW_DOWN)
                    except Exception:
                        pass
                    time.sleep(0.2)
                    element.send_keys(Keys.ENTER)
                    time.sleep(1)
                    current_value = read_element_value(element)
                    if value_matches_candidates(current_value, [candidate]):
                        return True
                except Exception:
                    continue

            try:
                element.click()
            except Exception:
                pass

            normalized_candidates = [normalize_field_text(item) for item in candidate_values]
            option_elements = driver.find_elements(
                By.XPATH,
                '//*[@role="option" or @role="menuitem" or contains(@class, "Option") or contains(@class, "option")]',
            )
            for option_element in option_elements:
                try:
                    if not option_element.is_displayed():
                        continue
                    option_text = normalize_field_text(option_element.text)
                    if any(candidate == option_text or candidate in option_text for candidate in normalized_candidates):
                        try:
                            option_element.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", option_element)
                        time.sleep(1)
                        if value_matches_candidates(
                            read_element_value(element),
                            candidate_values + [option_element.text],
                        ):
                            return True
                        try:
                            selected_flag = str(
                                option_element.get_attribute("aria-selected")
                                or option_element.get_attribute("data-selected")
                                or ""
                            ).strip().lower()
                            if selected_flag in ["true", "1", "yes", "selected"]:
                                return True
                        except Exception:
                            pass
                except Exception:
                    continue

            return False

        # 辅助函数：遍历查找并执行操作
        def run_in_all_frames(action_name, action_func):
            # 1. 主文档
            if action_func():
                print(f"  ✅ {action_name} (主文档)")
                return True
            
            # 2. 遍历 iframe
            driver.switch_to.default_content()
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for i, frame in enumerate(iframes):
                try:
                    driver.switch_to.frame(frame)
                    if action_func():
                        print(f"  ✅ {action_name} (iframe[{i}])")
                        driver.switch_to.default_content()
                        return True
                    driver.switch_to.default_content()
                except:
                    try: driver.switch_to.default_content()
                    except: pass
            
            print(f"  ⚠️ 未能完成: {action_name}")
            return False

        # ============== 1. 自动检测当前国家 ==============
        current_country_code = "JP" # 默认兜底
        detected_country_name = "Unknown"

        def detect_country():
            nonlocal current_country_code, detected_country_name
            
            # 尝试查找国家下拉框
            # 1. 查找 Select
            try:
                sel = find_visible('select[name="billingAddressCountry"], select[id^="Field-countryInput"]')
                if sel:
                    val = sel.get_attribute('value')
                    if val in ["US", "United States", "美国"]:
                        current_country_code = "US"
                        detected_country_name = "United States"
                    elif val in ["JP", "Japan", "日本"]:
                        current_country_code = "JP"
                        detected_country_name = "Japan"
                    else:
                        current_country_code = "JP" # 其他国家暂且当做 JP 处理（或根据需求扩展）
                        detected_country_name = val
                    return True
            except: pass

            # 2. 查找 Div 模拟的下拉框
            try:
                 # 查找包含 "国家" 或 "Country" 标签附近的 Div
                 dropdown_div = find_visible('//label[contains(text(), "国家") or contains(text(), "Country")]/following::div[contains(@class, "Select")][1]')
                 if not dropdown_div:
                     # 尝试找包含已知国家名的 Div
                     dropdown_div = find_visible('//*[contains(text(), "United States") or contains(text(), "美国") or contains(text(), "Japan") or contains(text(), "日本")]/ancestor::div[contains(@class, "Select") or contains(@class, "Input")][1]')
                 
                 if dropdown_div:
                     text = dropdown_div.text
                     if any(k in text for k in ["United States", "美国", "US"]):
                         current_country_code = "US"
                         detected_country_name = "United States"
                     elif any(k in text for k in ["Japan", "日本"]):
                         current_country_code = "JP"
                         detected_country_name = "Japan"
                     else:
                        current_country_code = "JP"
                        detected_country_name = text
                     return True
            except: pass
            
            # 3. 兜底：直接找页面上有没有显示 "美国" 或 "United States" 的独立文本，且位置靠前
            try:
                # 寻找表单区域内的 "美国" 文本
                us_text = find_visible('//form//div[contains(text(), "美国") or contains(text(), "United States")]')
                if us_text:
                     current_country_code = "US"
                     detected_country_name = "United States (Text Match)"
                     return True
            except: pass
            
            return False

        print("🌏 自动检测当前国家...")
        run_in_all_frames("检测国家", detect_country)
        print(f"   -> 检测结果: {detected_country_name} (Code: {current_country_code})")
        print("   -> 将生成该国家的真实地址进行填写")

        # 生成对应国家的随机账单信息
        billing_info = generate_billing_info(current_country_code)

        country_candidates = {
            "US": [billing_info["country_name"], "United States", "US", "美国"],
            "JP": [billing_info["country_name"], "Japan", "JP", "日本"],
        }
        country_field_selectors = [
            'select[name="billingAddressCountry"]',
            'select[name="country"]',
            'select[name="countryCode"]',
            'select[autocomplete="country"]',
            'select[id^="Field-countryInput"]',
            '#Field-countryInput',
            'input[name="billingAddressCountry"]',
            'input[name="country"]',
            'input[name="countryCode"]',
            'input[autocomplete="country"]',
            'input[id^="Field-countryInput"]',
            '//label[contains(normalize-space(.), "Country")]/following::*[self::select or self::input][1]',
            '//label[contains(normalize-space(.), "国家")]/following::*[self::select or self::input][1]',
            '//*[@role="combobox" and (contains(@aria-label, "Country") or contains(@aria-label, "国家"))]',
        ]
        region_field_selectors = [
            '#Field-administrativeAreaInput',
            '#Field-koreanAdministrativeDistrictInput',
            'select[name="state"]',
            'input[name="state"]',
            'select[name="province"]',
            'input[name="province"]',
            'select[name="administrativeArea"]',
            'input[name="administrativeArea"]',
            'select[autocomplete="address-level1"]',
            'input[autocomplete="address-level1"]',
            '//label[contains(normalize-space(.), "State")]/following::*[self::select or self::input][1]',
            '//label[contains(normalize-space(.), "Province")]/following::*[self::select or self::input][1]',
            '//label[contains(normalize-space(.), "Region")]/following::*[self::select or self::input][1]',
            '//label[contains(normalize-space(.), "区域")]/following::*[self::select or self::input][1]',
            '//label[contains(normalize-space(.), "州")]/following::*[self::select or self::input][1]',
            '//*[@role="combobox" and (contains(@aria-label, "State") or contains(@aria-label, "Province") or contains(@aria-label, "Region") or contains(@aria-label, "州") or contains(@aria-label, "区域"))]',
        ]
        zip_field_selectors = [
            '#Field-postalCodeInput',
            'input[name="postalCode"]',
            'input[autocomplete="postal-code"]',
            'input[placeholder="邮政编码"]',
            'input[placeholder="Zip code"]',
        ]
        city_field_selectors = [
            '#Field-localityInput',
            'input[name="city"]',
            'input[autocomplete="address-level2"]',
            'input[placeholder="城市"]',
            'input[placeholder="City"]',
        ]
        line1_field_selectors = [
            '#Field-addressLine1Input',
            'input[name="addressLine1"]',
            'input[autocomplete="address-line1"]',
            'input[placeholder="地址第 1 行"]',
            'input[placeholder="Address line 1"]',
        ]

        def ensure_country_selection():
            country_element = wait_for_visible_in_list(country_field_selectors, timeout=2.5)
            if not country_element:
                print("  ℹ️ 未找到显式国家选择控件")
                return False

            candidates = country_candidates.get(current_country_code, [billing_info["country_name"], current_country_code])
            success = select_form_value(country_element, candidates)
            if success:
                print(f"  ✅ 已选择国家/地区: {billing_info['country_name']}")
                time.sleep(1.5)
            else:
                print(f"  ⚠️ 国家/地区选择失败: {billing_info['country_name']}")
            return success

        def ensure_region_selection(force_fill: bool = False):
            wait_timeout = 8.0 if force_fill else 2.0
            region_element = wait_for_visible_in_list(region_field_selectors, timeout=wait_timeout)
            if not region_element:
                print("  ℹ️ 当前支付表单未显示区域选择控件")
                return False

            current_value = normalize_field_text(read_element_value(region_element))
            expected_values = [
                normalize_field_text(billing_info["state"]),
                normalize_field_text(billing_info.get("state_code", "")),
            ]
            if not force_fill and current_value and any(
                expected and expected in current_value for expected in expected_values
            ):
                print(f"  ✅ 当前区域已匹配: {billing_info['state']}")
                return True

            candidates = [
                billing_info["state"],
                billing_info.get("state_code", ""),
            ]
            success = select_form_value(region_element, candidates)
            if success:
                print(f"  ✅ 已选择区域: {billing_info['state']}")
                time.sleep(1)
            else:
                print(f"  ⚠️ 区域选择失败: {billing_info['state']}")
            return success
        
        # ============== 2. 填写姓名 ==============
        def fill_name():
            selectors = [
                 # Stripe 常见 ID
                 '#Field-nameInput', '#Field-billingNameInput', '#billingName',
                 'input[id^="Field-nameInput"]',
                 # 通用属性
                 'input[name="name"]', 'input[name="billingName"]', 
                 'input[id="billingName"]', 
                 # 中文和英文 Placeholder
                 'input[placeholder="全名"]', 'input[placeholder="Full name"]',
                 'input[autocomplete="name"]', 'input[autocomplete="cc-name"]'
            ]
            for s in selectors:
                el = find_visible(s)
                if el:
                    el.clear()
                    type_slowly(el, billing_info["name"])
                    return True
            return False
            
        print(f"👤 寻找并填写姓名: {billing_info['name']}...")
        run_in_all_frames("填写姓名", fill_name)
        time.sleep(1)

        # ============== 3. 填写地址 ==============
        def fill_address():
            ensure_country_selection()

            # 1. 邮编 (Zip)
            zip_el = find_visible_in_list(zip_field_selectors)
            if zip_el:
                clear_and_type_value(zip_el, billing_info["zip"])
                try:
                    zip_el.send_keys(Keys.TAB)
                except Exception:
                    pass
                print(f"  ✅ 填写邮编: {billing_info['zip']}")

                # 邮编变化后常会异步加载区域/城市控件，显式等待一次，避免只填到 Zip。
                print("  ⏳ 等待区域/城市字段加载...")
                if wait_for_visible_in_list(region_field_selectors + city_field_selectors, timeout=8.0):
                    print("  ✅ 二级地址字段已出现")
                else:
                    print("  ⚠️ 未等到二级地址字段，继续尝试补填")
            
            # 2. 州/省 (State)
            ensure_region_selection(force_fill=True)

            # 3. 城市 (City)
            city_el = find_visible_in_list(city_field_selectors)
            if city_el:
                clear_and_type_value(city_el, billing_info["city"])
                print(f"  ✅ 填写城市: {billing_info['city']}")

            # 4. 地址行1
            line1_el = find_visible_in_list(line1_field_selectors)
            if line1_el:
                clear_and_type_value(line1_el, billing_info["address1"])
                time.sleep(0.5)
                # 有些自动完成弹窗需要 ESC 关闭
                try: ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                except: pass
                print(f"  ✅ 填写地址行1: {billing_info['address1']}")
                
            return True

        print("🏠 寻找并填写地址...")
        run_in_all_frames("填写地址", fill_address)
        time.sleep(1)

        # ============== 4. 填写信用卡 ==============
        print("💳 正在填写信用卡信息...")
        card = CREDIT_CARD_INFO
        
        # 卡号
        if not handle_stripe_input(driver, '卡号', 'input[name="cardnumber"], input[placeholder*="Card number"], input[placeholder*="0000"], input[autocomplete="cc-number"]', card["number"]):
             print("❌ 卡号输入失败")
        
        time.sleep(1)
        
        # 有效期
        if not handle_stripe_input(driver, '有效期', 
            'input[name="exp-date"], input[name="expirationDate"], input[id="cardExpiry"], input[placeholder="MM / YY"], input[autocomplete="cc-exp"]', 
            card["expiry"]):
            print("❌ 有效期输入失败")
            
        time.sleep(1)
        
        # CVC
        if not handle_stripe_input(driver, 'CVC', 'input[name="cvc"], input[name="securityCode"], input[id="cardCvc"], input[placeholder="CVC"]', card["cvc"]):
             print("❌ CVC 输入失败")

        time.sleep(2)
        
        # ============== 5. 循环提交与补全 ==============
        def loop_submit_and_fix():
            max_attempts = 5
            for attempt in range(max_attempts):
                print(f"🔄 尝试提交 ({attempt + 1}/{max_attempts})...")
                
                # 1. 点击提交
                driver.switch_to.default_content() # 按钮通常在主文档
                try:
                    submit_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit'], button[class*='Subscribe']")))
                    driver.execute_script("arguments[0].click();", submit_btn)
                    print("  🔘 已点击提交按钮")
                except:
                    print("  ⚠️ 未找到提交按钮")
                
                time.sleep(3) # 等待校验结果
                
                # -------------------------------
                # 新增: 检查是否有验证码 (hCaptcha/Cloudflare)
                # -------------------------------
                try:
                    # 查找可能的验证码 iframe
                    captcha_frames = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='hcaptcha'], iframe[src*='challenges'], iframe[title*='widget'], iframe[title*='验证']")
                    for frame in captcha_frames:
                        if frame.is_displayed():
                            print("  ⚠️ 发现验证码，尝试点击...")
                            driver.switch_to.frame(frame)
                            try:
                                # hCaptcha / Cloudflare 常见的 Checkbox
                                checkbox = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#checkbox, .checkbox, #challenge-stage")))
                                checkbox.click()
                                print("    ✅ 已点击验证码复选框")
                                time.sleep(5) # 等待验证通过
                            except Exception as e:
                                print(f"    ⚠️ 点击验证码失败: {e}")
                            
                            driver.switch_to.default_content()
                except:
                    driver.switch_to.default_content()

                # 2. 检查是否有 '该字段不完整' / 'Incomplete field'
                # 需要遍历 iframe 检查
                has_error = False
                driver.switch_to.default_content()
                frames = driver.find_elements(By.TAG_NAME, "iframe")
                all_frames = [None] + frames # None 表示主文档
                
                for frame in all_frames:
                    if frame:
                        try: driver.switch_to.frame(frame)
                        except: continue
                    else:
                        driver.switch_to.default_content()
                        
                    # 查找红字错误
                    errors = driver.find_elements(By.XPATH, '//*[contains(text(), "该字段不完整") or contains(text(), "Incomplete field") or contains(text(), "Required")]')
                    
                    if errors:
                        print(f"  ⚠️ 发现 {len(errors)} 个未完成字段，正在补全...")
                        has_error = True

                        ensure_country_selection()
                        ensure_region_selection(force_fill=False)
                        
                        # --- US 补全策略 ---

                        # 1. 检查地址行1 (最常见的遗漏)
                        try:
                             line1_inputs = driver.find_elements(By.CSS_SELECTOR, '#Field-addressLine1Input, input[name="addressLine1"], input[placeholder="地址第 1 行"], input[placeholder="Address line 1"]')
                             for el in line1_inputs:
                                 if el.is_displayed() and not el.get_attribute('value'):
                                      print(f"    -> 补填 Address Line 1 ({billing_info['address1']})")
                                      clear_and_type_value(el, billing_info['address1'])
                                      # 有时候填完需要回车
                                      try: el.send_keys(Keys.ENTER)
                                      except: pass
                        except Exception as e:
                            print(f"    debug: 补填 address1 异常 {e}")

                        # 2. 检查州/State
                        state_inputs = driver.find_elements(By.CSS_SELECTOR, '#Field-administrativeAreaInput, select[name="state"], input[name="state"]')
                        for el in state_inputs:
                            try:
                                if el.is_displayed() and not read_element_value(el):
                                    print(f"    -> 补填区域 ({billing_info['state']})")
                                    select_form_value(el, [billing_info["state"], billing_info.get("state_code", "")])
                            except: pass

                        # 检查邮编
                        zip_inputs = driver.find_elements(By.CSS_SELECTOR, '#Field-postalCodeInput, input[name="postalCode"]')
                        for el in zip_inputs:
                            try:
                                if el.is_displayed() and not el.get_attribute('value'):
                                    print(f"    -> 补填 Zip ({billing_info['zip']})")
                                    clear_and_type_value(el, billing_info["zip"])
                            except: pass
                            
                        # 检查城市
                        city_inputs = driver.find_elements(By.CSS_SELECTOR, '#Field-localityInput, input[name="city"]')
                        for el in city_inputs:
                            try:
                                if el.is_displayed() and not el.get_attribute('value'):
                                    print(f"    -> 补填 City ({billing_info['city']})")
                                    clear_and_type_value(el, billing_info["city"])
                            except: pass
                            
                    driver.switch_to.default_content()
                    if has_error: break # 只要发现错误就跳出 iframe 循环去点击提交
                
                if not has_error:
                    print("✅ 似乎没有表单错误了，等待结果...")
                    return True
                
                time.sleep(1)
            
            return False

        print("🚀 进入提交循环...")
        check_result = loop_submit_and_fix()

        print("✅ 表单提交流程结束，正在等待支付结果/页面跳转...")
        
        # 支付可能需要较长时间验证
        # 我们轮询检查 URL 变化
        start_time = time.time()
        while time.time() - start_time < 30:
            current_url = driver.current_url
            print(f"  当前 URL: {current_url}")
            
            # 成功信号 1: 回到主页
            if ("chatgpt.com" in current_url or "chat.openai.com" in current_url) and "pricing" not in current_url and "payment" not in current_url:
                 print("✅ 检测到跳转回主页，订阅成功！")
                 
                 # 顺便处理一下那个 "好的，开始吧" 弹窗，方便后续取消操作
                 try:
                    okay_btn = driver.find_element(By.XPATH, '//button[contains(., "Okay") or contains(., "开始") or contains(., "Let")]')
                    okay_btn.click()
                    print("  -> 已关闭欢迎弹窗")
                 except: pass
                 
                 return True

            # 成功信号 2: 出现 "Welcome" 弹窗
            try:
                if driver.find_element(By.XPATH, '//div[contains(text(), "ChatGPT")]//div[contains(text(), "Tips")]').is_displayed():
                    print("✅ 检测到欢迎弹窗，订阅成功！")
                    return True
            except: pass
            
            # 失败信号
            try:
                 error_msg = driver.find_element(By.CSS_SELECTOR, '.StripeElement--invalid, .error-message, [role="alert"]')
                 if error_msg and error_msg.is_displayed():
                     print(f"❌ 支付遇到错误: {error_msg.text}")
                     # 不要立即放弃，有时候是临时的
            except:
                 pass
                 
            time.sleep(2)

        print("❌ 等待跳转超时，且仍在支付页面，订阅可能失败。")
        return False
            
    except Exception as e:
        print(f"❌ 订阅流程出错: {e}")
        return False


def cancel_subscription(driver):
    """
    取消订阅
    """
    print("\n" + "=" * 50)
    print("🛑 开始取消订阅流程")
    print("=" * 50)
    
    wait = WebDriverWait(driver, 20)
    
    try:
        # 确保回到主页
        if "chatgpt.com" not in driver.current_url:
            driver.get("https://chatgpt.com")
        
        # ===== 等待页面完全加载 =====
        print("⏳ 等待页面完全加载...")
        for _ in range(10):  # 最多等 20 秒
            try:
                # 标志性元素：输入框或头像按钮
                driver.find_element(By.ID, "prompt-textarea")
                print("  ✅ 页面加载完成")
                break
            except:
                time.sleep(2)
        
        time.sleep(2)  # 额外缓冲
            
        # 🧹 清理可能存在的欢迎弹窗 (Critical!)
        print("🧹 检查并清理欢迎弹窗...")
        for _ in range(3):
            try:
                welcomes = driver.find_elements(By.XPATH, '//button[contains(., "Okay") or contains(., "开始") or contains(., "Let")]')
                clicked = False
                for btn in welcomes:
                    if btn.is_displayed():
                        print(f"  -> 点击关闭欢迎弹窗: {btn.text}")
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1)
                        clicked = True
                if not clicked:
                     break
            except:
                pass
            time.sleep(1)
        
        # ===== 打开个人菜单 (带重试) =====
        print("🔘 打开个人菜单...")
        menu_opened = False
        for attempt in range(3):
            try:
                # 尝试多种选择器找头像/菜单
                selectors = [
                    'div[data-testid="user-menu"]',
                    '.text-token-text-secondary',
                    '//div[contains(@class, "group relative")]'
                ]
                
                for sel in selectors:
                    try:
                        if sel.startswith('//'):
                            btn = driver.find_element(By.XPATH, sel)
                        else:
                            btn = driver.find_element(By.CSS_SELECTOR, sel)
                        btn.click()
                        menu_opened = True
                        break
                    except:
                        continue
                
                if menu_opened:
                    print(f"  ✅ 菜单打开成功 (第 {attempt+1} 次尝试)")
                    break
                    
            except Exception as e:
                print(f"  ⚠️ 第 {attempt+1} 次尝试失败: {e}")
            
            if not menu_opened:
                print(f"  🔄 等待 2s 后重试...")
                time.sleep(2)
        
        if not menu_opened:
            print("❌ 经多次重试仍无法打开个人菜单")
            return False
            
        
        time.sleep(2)
        
        # 调试：打印菜单内容
        try:
            menu = driver.find_element(By.CSS_SELECTOR, '[role="menu"], div[data-testid*="menu"]')
            print(f" 菜单内容:\n{menu.text}")
        except:
            pass
        
        print("🔘 点击 My Plan / 我的套餐...")
        found_my_plan = False
        try:
            # 优先找 "我的套餐" / "My plan"
            my_plan_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//div[contains(text(), "My plan") or contains(text(), "我的套餐")]')))
            my_plan_btn.click()
            found_my_plan = True
        except:
            print("⚠️ 未找到 '我的套餐'，尝试通过 '设置' 进入...")
            
            try:
                # 1. 点击 "设置" / "Settings"
                settings_btn = driver.find_element(By.XPATH, '//div[contains(text(), "Settings") or contains(text(), "设置")]')
                settings_btn.click()
                print("  -> 已点击 '设置'")
                time.sleep(2)
                
                # 2. 点击左侧 "帐户" / "Account" (如果是 Tab)
                # 3. 在设置弹窗中，点击 "Account" / "帐户" 标签
                print("  -> 切换到 '帐户' 标签...")
                
                from selenium.webdriver.common.action_chains import ActionChains
                
                try:
                    # 用 Selenium 精确查找帐户按钮
                    account_btns = driver.find_elements(By.XPATH, '//div[@role="dialog"]//button')
                    
                    for btn in account_btns:
                        try:
                            txt = btn.text.strip()
                            if txt == '帐户' or txt == '账户' or txt.lower() == 'account':
                                print(f"  -> 找到并点击帐户按钮: '{txt}'")
                                actions = ActionChains(driver)
                                actions.move_to_element(btn).click().perform()
                                time.sleep(1)
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"  ⚠️ 点击帐户标签时出错: {e}")
                
                time.sleep(1)  # 等待页面切换

                # 3. 检查状态或点击 "管理"
                # 截图显示如果已取消，会提示 "将于...取消"。
                try:
                    status_text = driver.find_element(By.XPATH, '//*[contains(text(), "你的套餐将于") or contains(text(), "Your plan will be canceled")]')
                    print(f"  ℹ️ 检测到订阅状态: {status_text.text}")
                    print("  ✅ 订阅似乎已经取消，不再继续。")
                    return True
                except:
                    pass

                # 4. 点击 "管理" / "Manage" 按钮 (ChatGPT Plus 区域的那个)
                print("  -> 寻找 ChatGPT Plus 区域的 '管理' 按钮...")
                try:
                    # 方法1：找包含 "ChatGPT Plus" 的区域，然后在其中找管理按钮
                    manage_btn = driver.find_element(By.XPATH, 
                        '//*[contains(text(), "ChatGPT Plus")]/ancestor::div[1]//button[contains(., "管理") or contains(., "Manage")]')
                    manage_btn.click()
                    print("  -> 已点击 ChatGPT Plus 区域的 '管理'")
                except:
                    try:
                        # 方法2：找标题"帐户"下方第一个管理按钮
                        manage_btn = driver.find_element(By.XPATH, 
                            '//h2[contains(., "帐户") or contains(., "Account")]/following::button[contains(., "管理") or contains(., "Manage")][1]')
                        manage_btn.click()
                        print("  -> 已点击标题下方的 '管理'")
                    except:
                        try:
                            # 方法3：找页面顶部区域的管理按钮（排除付款区域）
                            manage_btns = driver.find_elements(By.XPATH, '//button[contains(., "管理") or contains(., "Manage")]')
                            for btn in manage_btns:
                                # 检查这个按钮是否在页面上半部分（ChatGPT Plus 区域通常在上面）
                                location = btn.location
                                if location['y'] < 400 and btn.is_displayed():  # 假设上半部分 y < 400
                                    btn.click()
                                    print(f"  -> 已点击位置靠上的 '管理' (y={location['y']})")
                                    break
                        except Exception as e:
                            print(f"  ❌ 未找到管理按钮: {e}")
                            return False
                
                time.sleep(2)
                
                # ---------------------------------------------------------
                # 新分支：检测是否是应用内下拉菜单 (In-App Cancellation)
                # ---------------------------------------------------------
                print("  -> 等待下拉菜单出现...")
                time.sleep(2)  # 等待菜单动画
                
                try:
                    # 尝试多种选择器找 "取消订阅" / "Cancel subscription"
                    cancel_xpaths = [
                        '//*[contains(text(), "取消订阅")]',
                        '//*[contains(text(), "Cancel subscription")]',
                        '//div[contains(text(), "取消订阅")]',
                        '//span[contains(text(), "取消订阅")]',
                        '//button[contains(., "取消订阅")]'
                    ]
                    
                    cancel_item = None
                    for xp in cancel_xpaths:
                        try:
                            items = driver.find_elements(By.XPATH, xp)
                            for item in items:
                                if item.is_displayed():
                                    cancel_item = item
                                    print(f"  -> 找到取消按钮: {item.text}")
                                    break
                        except: pass
                        if cancel_item: break
                    
                    if cancel_item:
                        print("  -> 点击 '取消订阅'...")
                        driver.execute_script("arguments[0].click();", cancel_item)
                        time.sleep(2)
                        
                        # 处理确认弹窗
                        print("  -> 等待确认弹窗...")
                        confirm_xpaths = [
                            '//button[contains(., "取消订阅")]',
                            '//button[contains(., "Cancel subscription")]',
                            '//div[@role="dialog"]//button[contains(@class, "danger")]'
                        ]
                        
                        for xp in confirm_xpaths:
                            try:
                                confirm_btns = driver.find_elements(By.XPATH, xp)
                                for btn in confirm_btns:
                                    if btn.is_displayed() and ("取消" in btn.text or "Cancel" in btn.text):
                                        driver.execute_script("arguments[0].click();", btn)
                                        print("✅ 已点击最终确认取消！")
                                        return True
                            except: pass
                        
                        print("  ⚠️ 未能点击确认按钮")
                    else:
                        print("  ℹ️ 未检测到应用内取消菜单")
                        
                except Exception as e:
                    print(f"  ℹ️ 应用内取消流程异常: {e}")
                
                # ---------------------------------------------------------
                # 旧分支：Stripe Billing Portal 跳转
                # ---------------------------------------------------------
                # 如果上面没找到菜单，可能是旧版，跳转到了新标签页
                pass
                
            except Exception as e:
                print(f"❌ 通过设置页面取消失败: {e}")
                return False
        else:
             print("🔘 点击管理订阅 (My Plan 路径)...")
             try:
                manage_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[contains(text(), "Manage my subscription") or contains(text(), "管理我的订阅")]')))
                manage_btn.click()
             except:
                print("❌ 未找到管理订阅按钮")
                return False

        time.sleep(5)
        print("🌐 跳转到 Billing Portal...")
        
        print("🔘 寻找取消按钮...")
        try:
             # Stripe Portal 页面
             # 有时需要先切 iframe? 通常是新窗口或当前页跳转
            cancel_btn = wait.until(EC.presence_of_element_located((By.XPATH, '//button[contains(., "Cancel plan") or contains(., "取消方案")]')))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cancel_btn)
            time.sleep(1)
            cancel_btn.click()
        except:
             # 有时候是 "Cancel trial"
            try:
                cancel_btn = driver.find_element(By.XPATH, '//button[contains(., "Cancel trial") or contains(., "取消试用")]')
                cancel_btn.click()
            except:
                print("⚠️ 未找到取消按钮，可能已经取消或需要人工干预")
                return False
            
        time.sleep(2)
        print("🔘 确认取消...")
        try:
            confirm_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(., "Cancel plan") or contains(., "Confirm cancellation")]')))
            confirm_btn.click()
            print("✅ 订阅已取消！")
        except:
            print("⚠️ 未找到确认取消按钮")
            
        time.sleep(3)
        return True
        
    except Exception as e:
        print(f"❌ 取消订阅失败: {e}")
        return False
