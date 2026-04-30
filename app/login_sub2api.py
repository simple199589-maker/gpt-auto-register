"""
登录验证到 Sub2Api 上传的业务编排层。
AI by zb
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Optional

from app.account_store import load_account_records, query_account_records
from app.codex.runtime import (
    OAUTH_CLIENT_ID,
    build_token_dict,
    create_session,
    get_logger,
    load_runtime_config,
    perform_http_oauth_login,
    resolve_proxy,
    save_token_payload,
    upload_to_sub2api,
)
from app.config import cfg
from app.email_service import is_outlook_email_address
from app.team_manage import TeamManageConfig, TeamManageUploader
from app.utils import get_account_record, upsert_account_record


@dataclass
class LoginSub2ApiResult:
    """
    登录到 Sub2Api 编排结果。

    AI by zb
    """

    success: bool
    email: str = ""
    login_success: bool = False
    uploaded: bool = False
    stage: str = ""
    message: str = ""
    output_file: str = ""
    tokens: Dict[str, Any] = field(default_factory=dict)
    token_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        将结果转换为接口响应字典。

        返回:
            Dict[str, Any]: 结果字典
            AI by zb
        """
        return asdict(self)


def _current_timestamp() -> str:
    """
    获取账号状态更新时间戳。

    返回:
        str: `YYYYMMDD_HHMMSS`
        AI by zb
    """
    return time.strftime("%Y%m%d_%H%M%S")


def _normalize_email(email: str) -> str:
    """
    规范化账号邮箱。

    参数:
        email: 原始邮箱
    返回:
        str: 小写邮箱
        AI by zb
    """
    return str(email or "").strip().lower()


def _is_valid_email(email: str) -> bool:
    """
    判断邮箱格式是否可用于账号主键。

    参数:
        email: 邮箱地址
    返回:
        bool: 是否有效
        AI by zb
    """
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(email or "").strip()))


def _normalize_account_category(value: str) -> str:
    """
    规范化账号分类。

    参数:
        value: 原始分类
    返回:
        str: `normal/mother/plus/pro`
        AI by zb
    """
    normalized = str(value or "").strip().lower()
    if normalized in {"mother", "母号", "team"}:
        return "mother"
    if normalized in {"plus"}:
        return "plus"
    if normalized in {"pro"}:
        return "pro"
    return "normal"


def _has_complete_oauth_tokens(account: dict) -> bool:
    """
    判断账号是否已保存完整 OAuth 三件套。

    参数:
        account: 账号记录
    返回:
        bool: 是否具备可上传 token
        AI by zb
    """
    oauth_tokens = (account or {}).get("oauthTokens") or {}
    return bool(
        str(oauth_tokens.get("access_token") or "").strip()
        and str(oauth_tokens.get("refresh_token") or "").strip()
        and str(oauth_tokens.get("id_token") or "").strip()
    )


def _is_sub2api_configured(config: Dict[str, Any]) -> bool:
    """
    判断当前运行配置是否具备 Sub2Api 上传条件。

    参数:
        config: 运行配置
    返回:
        bool: 是否可上传
        AI by zb
    """
    sub2api_config = (config or {}).get("sub2api") or {}
    return bool(str(sub2api_config.get("base_url") or "").strip())


def _is_team_manage_configured(config: Dict[str, Any]) -> bool:
    """
    判断 Team 管理导入是否已配置。

    参数:
        config: 运行配置
    返回:
        bool: 是否具备上传条件
        AI by zb
    """
    team_config = (config or {}).get("team_manage") or {}
    return bool(
        str(team_config.get("base_url") or "").strip()
        and str(team_config.get("api_key") or "").strip()
    )


def _normalize_upload_targets(upload_targets: Optional[list[str]], skip_upload: bool) -> list[str]:
    """
    规范化登录后的上传目标。

    参数:
        upload_targets: 原始上传目标
        skip_upload: 是否跳过上传
    返回:
        list[str]: 上传目标列表
        AI by zb
    """
    if skip_upload:
        return []
    allowed_targets = {"sub2api", "team_manage"}
    if not upload_targets:
        return ["sub2api"]
    targets = []
    for item in upload_targets:
        normalized = str(item or "").strip().lower()
        if normalized in allowed_targets and normalized not in targets:
            targets.append(normalized)
    return targets or ["sub2api"]


def build_team_manage_config(config: Dict[str, Any]) -> TeamManageConfig:
    """
    从运行配置构建 Team 管理配置。

    参数:
        config: 运行配置
    返回:
        TeamManageConfig: Team 管理配置
        AI by zb
    """
    team_config = (config or {}).get("team_manage") or {}
    return TeamManageConfig(
        base_url=str(team_config.get("base_url") or "https://team.joini.cloud").strip().rstrip("/"),
        api_key=str(team_config.get("api_key") or "").strip(),
        client_id=OAUTH_CLIENT_ID,
    )


def upload_to_team_manage(
    email: str,
    tokens: Dict[str, Any],
    config: Dict[str, Any],
    logger: Optional[Any] = None,
) -> bool:
    """
    上传单个账号到 Team 管理。

    参数:
        email: 账号邮箱
        tokens: OAuth token 字典
        config: 运行配置
        logger: 日志器
    返回:
        bool: 是否上传成功
        AI by zb
    """
    uploaded, _message = upload_to_team_manage_with_message(email, tokens, config, logger=logger)
    return uploaded


def upload_to_team_manage_with_message(
    email: str,
    tokens: Dict[str, Any],
    config: Dict[str, Any],
    logger: Optional[Any] = None,
) -> tuple[bool, str]:
    """
    上传单个账号到 Team 管理并返回失败原因。

    参数:
        email: 账号邮箱
        tokens: OAuth token 字典
        config: 运行配置
        logger: 日志器
    返回:
        tuple[bool, str]: 是否上传成功与失败原因
        AI by zb
    """
    active_logger = logger or get_logger("team-manage")
    uploader = TeamManageUploader(
        create_session(),
        build_team_manage_config(config),
        active_logger,
    )
    uploaded = uploader.import_single_account(email, tokens)
    return uploaded, str(uploader.last_error_message or "").strip()


def import_login_account(
    email: str,
    password: str,
    mailbox_context: str = "",
    account_category: str = "normal",
    remark: str = "",
) -> dict:
    """
    导入待登录验证账号。

    参数:
        email: 账号邮箱
        password: 账号密码
        mailbox_context: 可选邮箱接码上下文
        account_category: 账号分类
        remark: 备注
    返回:
        dict: 写入后的账号记录
        AI by zb
    """
    normalized_email = _normalize_email(email)
    normalized_password = str(password or "").strip()
    if not normalized_email:
        raise ValueError("邮箱不能为空")
    if not _is_valid_email(normalized_email):
        raise ValueError("邮箱格式不正确")
    if not normalized_password:
        raise ValueError("密码不能为空")

    current = get_account_record(normalized_email) or {}
    context = str(mailbox_context or current.get("mailboxContext") or "").strip()
    if not context and is_outlook_email_address(normalized_email):
        context = f"outlook::{normalized_email}"
    return upsert_account_record(
        normalized_email,
        {
            "password": normalized_password,
            "accountCategory": _normalize_account_category(account_category),
            "status": "待登录验证",
            "registrationStatus": "success",
            "loginState": "pending",
            "loginStatus": "pending",
            "loginMessage": "",
            "loginVerifiedAt": "",
            "mailboxContext": context,
            "sub2apiUploaded": False,
            "sub2apiState": "pending",
            "sub2apiStatus": "待上传",
            "sub2apiMessage": "",
            "sub2apiUploadedAt": "",
            "sub2apiAutoUploadEnabled": bool(cfg.sub2api.auto_upload_sub2api),
            "teamManageUploaded": False,
            "teamManageState": "pending",
            "teamManageStatus": "待上传",
            "teamManageMessage": "",
            "teamManageUploadedAt": "",
            "overallStatus": "pending",
            "lastError": "",
            "remark": str(remark or current.get("remark") or "").strip(),
        },
    )


def upload_existing_tokens_to_sub2api(email: str, config_path: str = "") -> LoginSub2ApiResult:
    """
    仅复用已保存 OAuth 三件套上传 Sub2Api，不触发重新登录。

    参数:
        email: 账号邮箱
        config_path: 可选配置文件路径
    返回:
        LoginSub2ApiResult: 上传结果
        AI by zb
    """
    normalized_email = _normalize_email(email)
    account = get_account_record(normalized_email)
    if not account:
        return LoginSub2ApiResult(success=False, email=normalized_email, stage="account", message="账号不存在")
    if not _has_complete_oauth_tokens(account):
        return LoginSub2ApiResult(
            success=False,
            email=normalized_email,
            stage="token",
            message="当前账号没有可上传的 OAuth 三件套",
        )

    config = load_runtime_config(config_path)
    if not _is_sub2api_configured(config):
        message = "Sub2Api 未配置，无法上传"
        upsert_account_record(
            normalized_email,
            {
                "sub2apiUploaded": False,
                "sub2apiState": "disabled",
                "sub2apiStatus": "未启用",
                "sub2apiMessage": message,
                "overallStatus": "success" if account.get("loginState") == "success" else "pending",
            },
        )
        return LoginSub2ApiResult(
            success=False,
            email=normalized_email,
            login_success=bool(account.get("loginState") == "success"),
            stage="config",
            message=message,
            tokens=dict(account.get("oauthTokens") or {}),
            token_payload=build_token_dict(normalized_email, account.get("oauthTokens") or {}),
        )

    logger = get_logger("login-sub2api")
    tokens = dict(account.get("oauthTokens") or {})
    uploaded = upload_to_sub2api(normalized_email, tokens, config, logger=logger)
    message = "上传成功" if uploaded else "上传失败"
    upsert_account_record(
        normalized_email,
        {
            "status": "已上传Sub2Api" if uploaded else "Sub2Api上传失败",
            "sub2apiUploaded": bool(uploaded),
            "sub2apiState": "success" if uploaded else "failed",
            "sub2apiStatus": "已上传" if uploaded else "上传失败",
            "sub2apiMessage": message,
            "sub2apiUploadedAt": _current_timestamp() if uploaded else "",
            "overallStatus": "success" if uploaded else "failed",
            "lastError": "" if uploaded else message,
        },
    )
    return LoginSub2ApiResult(
        success=bool(uploaded),
        email=normalized_email,
        login_success=bool(account.get("loginState") == "success" or tokens),
        uploaded=bool(uploaded),
        stage="upload",
        message=message,
        tokens=tokens,
        token_payload=build_token_dict(normalized_email, tokens),
    )


def upload_existing_tokens_to_team_manage(email: str, config_path: str = "") -> LoginSub2ApiResult:
    """
    仅复用已保存 OAuth 三件套上传 Team 管理，不触发重新登录。

    参数:
        email: 账号邮箱
        config_path: 可选配置文件路径
    返回:
        LoginSub2ApiResult: 上传结果
        AI by zb
    """
    normalized_email = _normalize_email(email)
    account = get_account_record(normalized_email)
    if not account:
        return LoginSub2ApiResult(success=False, email=normalized_email, stage="account", message="账号不存在")
    if _normalize_account_category(str(account.get("accountCategory") or "")) != "mother":
        return LoginSub2ApiResult(
            success=False,
            email=normalized_email,
            stage="category",
            message="仅母号允许上传 Team 管理",
        )
    if not _has_complete_oauth_tokens(account):
        return LoginSub2ApiResult(
            success=False,
            email=normalized_email,
            stage="token",
            message="当前母号没有可上传的 OAuth 三件套",
        )

    config = load_runtime_config(config_path)
    if not _is_team_manage_configured(config):
        message = "Team 管理 API Key 未配置"
        upsert_account_record(
            normalized_email,
            {
                "teamManageUploaded": False,
                "teamManageState": "disabled",
                "teamManageStatus": "未启用",
                "teamManageMessage": message,
            },
        )
        return LoginSub2ApiResult(
            success=False,
            email=normalized_email,
            login_success=bool(account.get("loginState") == "success"),
            stage="config",
            message=message,
            tokens=dict(account.get("oauthTokens") or {}),
            token_payload=build_token_dict(normalized_email, account.get("oauthTokens") or {}),
        )

    logger = get_logger("team-manage")
    tokens = dict(account.get("oauthTokens") or {})
    uploaded, upload_error = upload_to_team_manage_with_message(normalized_email, tokens, config, logger=logger)
    message = "Team 管理上传成功" if uploaded else (upload_error or "Team 管理上传失败")
    upsert_account_record(
        normalized_email,
        {
            "teamManageUploaded": bool(uploaded),
            "teamManageState": "success" if uploaded else "failed",
            "teamManageStatus": "已上传" if uploaded else "上传失败",
            "teamManageMessage": message,
            "teamManageUploadedAt": _current_timestamp() if uploaded else "",
            "lastError": "" if uploaded else message,
        },
    )
    return LoginSub2ApiResult(
        success=bool(uploaded),
        email=normalized_email,
        login_success=bool(account.get("loginState") == "success" or tokens),
        uploaded=bool(uploaded),
        stage="team_manage",
        message=message,
        tokens=tokens,
        token_payload=build_token_dict(normalized_email, tokens),
    )


def login_and_upload_account(
    email: str,
    otp_mode: str = "auto",
    skip_upload: bool = False,
    config_path: str = "",
    proxy: str = "",
    output_dir: str = "",
    upload_targets: Optional[list[str]] = None,
    otp_provider: Optional[Callable[[str, int, Any], Optional[str]]] = None,
) -> LoginSub2ApiResult:
    """
    执行单账号登录验证、保存 token，并按需上传 Sub2Api。

    参数:
        email: 账号邮箱
        otp_mode: OTP 模式，支持 `auto/manual`
        skip_upload: 是否跳过 Sub2Api 上传
        config_path: 可选配置路径
        proxy: 可选代理
        output_dir: token 输出目录
        upload_targets: 登录成功后的上传目标
        otp_provider: 手填验证码提供器
    返回:
        LoginSub2ApiResult: 编排结果
        AI by zb
    """
    normalized_email = _normalize_email(email)
    account = get_account_record(normalized_email)
    if not account:
        return LoginSub2ApiResult(success=False, email=normalized_email, stage="account", message="账号不存在")

    password = str(account.get("password") or "").strip()
    if not password or password == "N/A":
        message = "账号未保存可用密码，无法登录验证"
        upsert_account_record(
            normalized_email,
            {
                "status": "登录失败",
                "loginState": "failed",
                "loginStatus": "failed",
                "loginMessage": message,
                "overallStatus": "failed",
                "lastError": message,
            },
        )
        return LoginSub2ApiResult(success=False, email=normalized_email, stage="login", message=message)

    upsert_account_record(
        normalized_email,
        {
            "status": "登录验证中",
            "loginState": "pending",
            "loginStatus": "pending",
            "loginMessage": "",
            "overallStatus": "pending",
            "lastError": "",
        },
    )

    config = load_runtime_config(config_path)
    logger = get_logger("login-sub2api")
    effective_proxy = resolve_proxy(config, proxy)
    mailbox_context = str(account.get("mailboxContext") or "").strip()
    normalized_otp_mode = str(otp_mode or "auto").strip().lower()
    if normalized_otp_mode not in {"auto", "manual"}:
        normalized_otp_mode = "auto"

    tokens = perform_http_oauth_login(
        email=normalized_email,
        password=password,
        proxy=effective_proxy,
        otp_mode=normalized_otp_mode,
        mailbox_context=mailbox_context,
        otp_provider=otp_provider,
        logger=logger,
    )
    if not tokens:
        message = "未获取到 OAuth 三件套"
        upsert_account_record(
            normalized_email,
            {
                "status": "登录失败",
                "loginState": "failed",
                "loginStatus": "failed",
                "loginMessage": message,
                "loginVerifiedAt": "",
                "sub2apiUploaded": False,
                "sub2apiState": "pending",
                "sub2apiStatus": "待上传",
                "sub2apiMessage": "",
                "overallStatus": "failed",
                "lastError": message,
            },
        )
        return LoginSub2ApiResult(
            success=False,
            email=normalized_email,
            login_success=False,
            stage="login",
            message=message,
        )

    token_payload = build_token_dict(normalized_email, tokens)
    output_file = save_token_payload(normalized_email, token_payload, output_dir=output_dir)
    login_updates = {
        "status": "登录成功",
        "loginState": "success",
        "loginStatus": "success",
        "loginMessage": "登录验证成功",
        "loginVerifiedAt": _current_timestamp(),
        "oauthTokens": tokens,
        "oauthOutputFile": output_file,
        "overallStatus": "pending",
        "lastError": "",
    }

    normalized_upload_targets = _normalize_upload_targets(upload_targets, skip_upload=skip_upload)

    if not normalized_upload_targets:
        upsert_account_record(
            normalized_email,
            {
                **login_updates,
                "sub2apiUploaded": False,
                "sub2apiState": "disabled",
                "sub2apiStatus": "已跳过",
                "sub2apiMessage": "本次手动跳过上传",
                "overallStatus": "success",
            },
        )
        return LoginSub2ApiResult(
            success=True,
            email=normalized_email,
            login_success=True,
            uploaded=False,
            stage="save",
            message="登录成功，已跳过上传",
            output_file=output_file,
            tokens=tokens,
            token_payload=token_payload,
        )

    upload_results: list[tuple[str, bool, str]] = []

    if "sub2api" in normalized_upload_targets:
        if not _is_sub2api_configured(config):
            upload_results.append(("sub2api", False, "Sub2Api 未配置"))
            upsert_account_record(
                normalized_email,
                {
                    **login_updates,
                    "sub2apiUploaded": False,
                    "sub2apiState": "disabled",
                    "sub2apiStatus": "未启用",
                    "sub2apiMessage": "Sub2Api 未配置",
                    "overallStatus": "success",
                },
            )
        else:
            sub2api_uploaded = upload_to_sub2api(normalized_email, tokens, config, logger=logger)
            upload_results.append(
                (
                    "sub2api",
                    bool(sub2api_uploaded),
                    "Sub2Api 上传成功" if sub2api_uploaded else "Sub2Api 上传失败",
                )
            )
            upsert_account_record(
                normalized_email,
                {
                    **login_updates,
                    "status": "已上传Sub2Api" if sub2api_uploaded else "Sub2Api上传失败",
                    "sub2apiUploaded": bool(sub2api_uploaded),
                    "sub2apiState": "success" if sub2api_uploaded else "failed",
                    "sub2apiStatus": "已上传" if sub2api_uploaded else "上传失败",
                    "sub2apiMessage": "登录成功并上传成功" if sub2api_uploaded else "登录成功但上传失败",
                    "sub2apiUploadedAt": _current_timestamp() if sub2api_uploaded else "",
                    "overallStatus": "success" if sub2api_uploaded else "failed",
                    "lastError": "" if sub2api_uploaded else "登录成功但上传失败",
                },
            )

    if "team_manage" in normalized_upload_targets:
        latest_account = get_account_record(normalized_email) or account
        if _normalize_account_category(str(latest_account.get("accountCategory") or "")) != "mother":
            upload_results.append(("team_manage", False, "仅母号允许上传 Team 管理"))
        elif not _is_team_manage_configured(config):
            upload_results.append(("team_manage", False, "Team 管理 API Key 未配置"))
            upsert_account_record(
                normalized_email,
                {
                    **login_updates,
                    "teamManageUploaded": False,
                    "teamManageState": "disabled",
                    "teamManageStatus": "未启用",
                    "teamManageMessage": "Team 管理 API Key 未配置",
                },
            )
        else:
            team_uploaded, team_error = upload_to_team_manage_with_message(
                normalized_email,
                tokens,
                config,
                logger=get_logger("team-manage"),
            )
            team_message = "Team 管理上传成功" if team_uploaded else (team_error or "Team 管理上传失败")
            upload_results.append(
                (
                    "team_manage",
                    bool(team_uploaded),
                    team_message,
                )
            )
            upsert_account_record(
                normalized_email,
                {
                    **login_updates,
                    "teamManageUploaded": bool(team_uploaded),
                    "teamManageState": "success" if team_uploaded else "failed",
                    "teamManageStatus": "已上传" if team_uploaded else "上传失败",
                    "teamManageMessage": team_message,
                    "teamManageUploadedAt": _current_timestamp() if team_uploaded else "",
                    "lastError": "" if team_uploaded else team_message,
                },
            )

    if not upload_results:
        message = "登录成功，Sub2Api 未配置，未上传"
        upsert_account_record(
            normalized_email,
            {
                **login_updates,
                "sub2apiUploaded": False,
                "sub2apiState": "disabled",
                "sub2apiStatus": "未启用",
                "sub2apiMessage": "Sub2Api 未配置",
                "overallStatus": "success",
            },
        )
        return LoginSub2ApiResult(
            success=True,
            email=normalized_email,
            login_success=True,
            uploaded=False,
            stage="config",
            message=message,
            output_file=output_file,
            tokens=tokens,
            token_payload=token_payload,
        )

    uploaded = all(item[1] for item in upload_results)
    message = "登录成功，" + "；".join(item[2] for item in upload_results)
    return LoginSub2ApiResult(
        success=bool(uploaded),
        email=normalized_email,
        login_success=True,
        uploaded=bool(uploaded),
        stage="upload",
        message=message,
        output_file=output_file,
        tokens=tokens,
        token_payload=token_payload,
    )


def list_pending_accounts(limit: int = 0) -> list[dict]:
    """
    查询待处理账号列表。

    参数:
        limit: 最大返回数量，0 表示不限
    返回:
        list[dict]: 待处理账号
        AI by zb
    """
    records = load_account_records()
    pending = []
    for account in records:
        if _normalize_account_category(str(account.get("accountCategory") or "")) == "mother":
            continue
        login_state = str(account.get("loginState") or account.get("loginStatus") or "pending").strip().lower()
        sub2api_state = str(account.get("sub2apiState") or "pending").strip().lower()
        if login_state == "pending" or (login_state == "success" and sub2api_state == "pending"):
            pending.append(account)
        if limit and len(pending) >= int(limit):
            break
    return pending


def run_batch_login_sub2api(
    count: int = 0,
    should_stop: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[str, dict], None]] = None,
    otp_mode: str = "auto",
) -> Dict[str, Any]:
    """
    批量执行待处理账号的登录上传流程。

    参数:
        count: 处理数量，0 表示处理全部待处理账号
        should_stop: 停止检查回调
        progress_callback: 进度回调
        otp_mode: OTP 模式
    返回:
        Dict[str, Any]: 批量统计结果
        AI by zb
    """
    limit = max(int(count or 0), 0)
    accounts = list_pending_accounts(limit=limit)
    summary = {
        "total": len(accounts),
        "success": 0,
        "fail": 0,
        "stopped": False,
        "results": [],
    }
    for index, account in enumerate(accounts, start=1):
        if should_stop and should_stop():
            summary["stopped"] = True
            break
        email = str(account.get("email") or "").strip()
        if progress_callback:
            progress_callback("start", {"index": index, "total": len(accounts), "email": email})
        if _has_complete_oauth_tokens(account) and str(account.get("loginState") or "") == "success":
            result = upload_existing_tokens_to_sub2api(email)
        else:
            result = login_and_upload_account(email, otp_mode=otp_mode)
        summary["results"].append(result.to_dict())
        if result.success:
            summary["success"] += 1
        else:
            summary["fail"] += 1
        if progress_callback:
            progress_callback("done", {"index": index, "total": len(accounts), "email": email, "result": result.to_dict()})
    return summary


__all__ = [
    "LoginSub2ApiResult",
    "import_login_account",
    "list_pending_accounts",
    "login_and_upload_account",
    "query_account_records",
    "run_batch_login_sub2api",
    "upload_existing_tokens_to_team_manage",
    "upload_existing_tokens_to_sub2api",
    "upload_to_team_manage_with_message",
]
