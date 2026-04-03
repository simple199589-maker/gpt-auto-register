"""
账号仓储层。
AI by zb
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import cfg


ACCOUNT_RECORD_DEFAULTS = {
    "email": "",
    "password": "N/A",
    "time": "",
    "status": "",
    "accessToken": "",
    "mailboxContext": "",
    "sessionInfo": {},
    "plusCalled": False,
    "plusSuccess": False,
    "plusStatus": "",
    "plusMessage": "",
    "plusRequestId": "",
    "plusCalledAt": "",
    "sub2apiUploaded": False,
    "sub2apiStatus": "",
    "sub2apiMessage": "",
    "sub2apiUploadedAt": "",
    "sub2apiAutoUploadEnabled": False,
    "oauthTokens": {
        "access_token": "",
        "refresh_token": "",
        "id_token": "",
        "account_id": "",
    },
    "oauthOutputFile": "",
    "deliveryInfo": {
        "delivered": False,
        "vendor": "",
        "targetEmail": "",
        "status": "",
        "message": "",
        "tempAccessUrl": "",
        "mailId": "",
        "deliveredAt": "",
    },
    "registrationStatus": "pending",
    "overallStatus": "pending",
    "plusState": "idle",
    "sub2apiState": "pending",
    "createdAt": "",
    "updatedAt": "",
    "lastError": "",
}

ALLOWED_REGISTRATION_STATES = {"pending", "success", "failed"}
ALLOWED_PLUS_STATES = {"idle", "pending", "success", "failed", "disabled"}
ALLOWED_SUB2API_STATES = {"pending", "success", "failed", "disabled"}
SCHEMA_VERSION = "2"

_INIT_LOCK = threading.Lock()
_INITIALIZED = False


def _normalize_account_email(email: str) -> str:
    """
    规范化账号邮箱主键，统一按不区分大小写处理。

    参数:
        email: 原始邮箱
    返回:
        str: 标准化后的邮箱
        AI by zb
    """
    return str(email or "").strip().lower()


def _project_root() -> Path:
    """
    获取项目根目录。

    返回:
        Path: 项目根目录
        AI by zb
    """
    return Path(__file__).resolve().parents[1]


def _current_timestamp() -> str:
    """
    获取当前时间戳。

    返回:
        str: `YYYYMMDD_HHMMSS`
        AI by zb
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _database_path() -> Path:
    """
    获取数据库路径。

    返回:
        Path: 数据库文件路径
        AI by zb
    """
    raw_path = str(getattr(cfg.files, "accounts_db_file", "data/accounts.db") or "data/accounts.db").strip()
    return _project_root() / raw_path


def _legacy_accounts_path() -> Path:
    """
    获取旧 TXT 账号路径。

    返回:
        Path: 旧账号文件路径
        AI by zb
    """
    raw_path = str(getattr(cfg.files, "accounts_file", "registered_accounts.txt") or "registered_accounts.txt").strip()
    return _project_root() / raw_path


def _connect() -> sqlite3.Connection:
    """
    创建数据库连接。

    返回:
        sqlite3.Connection: 连接对象
        AI by zb
    """
    db_path = _database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def _merge_nested_dict(base: dict, updates: dict) -> dict:
    """
    递归合并字典。

    参数:
        base: 基础字典
        updates: 更新字典
    返回:
        dict: 合并结果
        AI by zb
    """
    merged = dict(base or {})
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nested_dict(merged.get(key, {}), value)
        else:
            merged[key] = value
    return merged


def _safe_json_loads(payload: Any, default: Any) -> Any:
    """
    安全解析 JSON。

    参数:
        payload: 原始值
        default: 默认值
    返回:
        Any: 解析结果
        AI by zb
    """
    if isinstance(payload, (dict, list)):
        return payload
    text = str(payload or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _infer_registration_status(normalized: dict, prefer_explicit: bool = False) -> str:
    """
    推断注册状态分类。

    参数:
        normalized: 标准化账号记录
    返回:
        str: `pending/success/failed`
        AI by zb
    """
    explicit = str(normalized.get("registrationStatus") or "").strip().lower()
    if prefer_explicit and explicit in ALLOWED_REGISTRATION_STATES:
        return explicit

    status = str(normalized.get("status") or "").strip()
    last_error = str(normalized.get("lastError") or "").strip()

    if status == "注册中":
        return "pending"
    if status.startswith("错误") or "用户中断" in status:
        return "failed"
    if any(keyword in status for keyword in ["表单失败", "验证码失败", "创建邮箱失败", "注册失败", "资料失败"]):
        return "failed"
    if last_error:
        return "failed"
    if status:
        return "success"
    return "pending"


def _infer_plus_state(normalized: dict, prefer_explicit: bool = False) -> str:
    """
    推断 Plus 状态分类。

    参数:
        normalized: 标准化账号记录
    返回:
        str: `idle/pending/success/failed/disabled`
        AI by zb
    """
    explicit = str(normalized.get("plusState") or "").strip().lower()
    if prefer_explicit and explicit in ALLOWED_PLUS_STATES:
        return explicit

    plus_status = str(normalized.get("plusStatus") or "").strip()
    if normalized.get("plusSuccess"):
        return "success"
    if "关闭" in plus_status or "跳过" in plus_status:
        return "disabled"
    if any(keyword in plus_status for keyword in ("激活中", "处理中", "取消中", "已提交")):
        return "pending"
    if normalized.get("plusCalled"):
        return "failed"
    return "idle"


def _infer_sub2api_state(normalized: dict, prefer_explicit: bool = False) -> str:
    """
    推断 Sub2Api 状态分类。

    参数:
        normalized: 标准化账号记录
    返回:
        str: `pending/success/failed/disabled`
        AI by zb
    """
    explicit = str(normalized.get("sub2apiState") or "").strip().lower()
    if prefer_explicit and explicit in ALLOWED_SUB2API_STATES:
        return explicit

    sub2api_status = str(normalized.get("sub2apiStatus") or "").strip()
    sub2api_message = str(normalized.get("sub2apiMessage") or "").strip()

    if normalized.get("sub2apiUploaded"):
        return "success"
    if "未启用" in sub2api_status or "关闭了自动上传" in sub2api_message:
        return "disabled"
    if "失败" in sub2api_status or "失败" in sub2api_message:
        return "failed"
    return "pending"


def _infer_overall_status(normalized: dict, prefer_explicit: bool = False) -> str:
    """
    推断整体状态分类。

    参数:
        normalized: 标准化账号记录
    返回:
        str: `pending/success/failed`
        AI by zb
    """
    explicit = str(normalized.get("overallStatus") or "").strip().lower()
    if prefer_explicit and explicit in ALLOWED_REGISTRATION_STATES:
        return explicit

    registration_status = _infer_registration_status(normalized)
    plus_state = _infer_plus_state(normalized)
    sub2api_state = _infer_sub2api_state(normalized)

    if registration_status == "failed":
        return "failed"
    if registration_status == "pending":
        return "pending"
    if plus_state == "failed" or sub2api_state == "failed":
        return "failed"
    return "success"


def _normalize_account_record(record: dict) -> dict:
    """
    标准化账号记录。

    参数:
        record: 原始记录
    返回:
        dict: 标准化结果
        AI by zb
    """
    raw_record = record or {}
    has_registration_state = "registrationStatus" in raw_record
    has_plus_state = "plusState" in raw_record
    has_sub2api_state = "sub2apiState" in raw_record
    has_overall_state = "overallStatus" in raw_record

    normalized = _merge_nested_dict(ACCOUNT_RECORD_DEFAULTS, raw_record)
    normalized["email"] = str(normalized.get("email") or "").strip()
    normalized["password"] = str(normalized.get("password") or "N/A")
    normalized["status"] = str(normalized.get("status") or "")
    normalized["accessToken"] = str(normalized.get("accessToken") or "")
    normalized["mailboxContext"] = str(normalized.get("mailboxContext") or "")
    normalized["plusStatus"] = str(normalized.get("plusStatus") or "")
    normalized["plusMessage"] = str(normalized.get("plusMessage") or "")
    normalized["plusRequestId"] = str(normalized.get("plusRequestId") or "")
    normalized["plusCalledAt"] = str(normalized.get("plusCalledAt") or "")
    normalized["sub2apiStatus"] = str(normalized.get("sub2apiStatus") or "")
    normalized["sub2apiMessage"] = str(normalized.get("sub2apiMessage") or "")
    normalized["sub2apiUploadedAt"] = str(normalized.get("sub2apiUploadedAt") or "")
    normalized["oauthOutputFile"] = str(normalized.get("oauthOutputFile") or "")
    normalized["lastError"] = str(normalized.get("lastError") or "")
    normalized["plusCalled"] = bool(normalized.get("plusCalled"))
    normalized["plusSuccess"] = bool(normalized.get("plusSuccess"))
    normalized["sub2apiUploaded"] = bool(normalized.get("sub2apiUploaded"))
    normalized["sub2apiAutoUploadEnabled"] = bool(normalized.get("sub2apiAutoUploadEnabled"))

    session_info = normalized.get("sessionInfo")
    if not isinstance(session_info, dict):
        session_info = _safe_json_loads(session_info, {})
    normalized["sessionInfo"] = session_info if isinstance(session_info, dict) else {}

    oauth_tokens = normalized.get("oauthTokens")
    if not isinstance(oauth_tokens, dict):
        oauth_tokens = _safe_json_loads(oauth_tokens, {})
    normalized["oauthTokens"] = {
        "access_token": str((oauth_tokens or {}).get("access_token") or ""),
        "refresh_token": str((oauth_tokens or {}).get("refresh_token") or ""),
        "id_token": str((oauth_tokens or {}).get("id_token") or ""),
        "account_id": str((oauth_tokens or {}).get("account_id") or ""),
    }

    delivery_info = normalized.get("deliveryInfo")
    if not isinstance(delivery_info, dict):
        delivery_info = _safe_json_loads(delivery_info, {})
    normalized["deliveryInfo"] = {
        "delivered": bool((delivery_info or {}).get("delivered")),
        "vendor": str((delivery_info or {}).get("vendor") or "").strip(),
        "targetEmail": str((delivery_info or {}).get("targetEmail") or "").strip(),
        "status": str((delivery_info or {}).get("status") or "").strip(),
        "message": str((delivery_info or {}).get("message") or "").strip(),
        "tempAccessUrl": str((delivery_info or {}).get("tempAccessUrl") or "").strip(),
        "mailId": str((delivery_info or {}).get("mailId") or "").strip(),
        "deliveredAt": str((delivery_info or {}).get("deliveredAt") or "").strip(),
    }

    status = normalized["status"]
    if not normalized["plusStatus"] and status and ("Plus" in status or "激活" in status or "Token" in status):
        normalized["plusStatus"] = status
    if not normalized["sub2apiStatus"] and "Sub2Api" in status:
        normalized["sub2apiStatus"] = status
    if not normalized["plusSuccess"] and "已激活Plus" in status:
        normalized["plusSuccess"] = True
        normalized["plusCalled"] = True
    if normalized["plusSuccess"]:
        normalized["plusCalled"] = True
    if not normalized["sub2apiUploaded"] and "已上传Sub2Api" in status:
        normalized["sub2apiUploaded"] = True

    normalized["registrationStatus"] = _infer_registration_status(normalized, prefer_explicit=has_registration_state)
    normalized["plusState"] = _infer_plus_state(normalized, prefer_explicit=has_plus_state)
    normalized["sub2apiState"] = _infer_sub2api_state(normalized, prefer_explicit=has_sub2api_state)
    normalized["overallStatus"] = _infer_overall_status(normalized, prefer_explicit=has_overall_state)

    if not normalized["plusStatus"]:
        if normalized["plusState"] == "success":
            normalized["plusStatus"] = "已激活"
        elif normalized["plusState"] == "pending":
            normalized["plusStatus"] = "处理中"
        elif normalized["plusState"] == "failed":
            normalized["plusStatus"] = "失败"
        elif normalized["plusState"] == "disabled":
            normalized["plusStatus"] = "已关闭"
        else:
            normalized["plusStatus"] = "未调用"

    if not normalized["sub2apiStatus"]:
        if normalized["sub2apiState"] == "success":
            normalized["sub2apiStatus"] = "已上传"
        elif normalized["sub2apiState"] == "failed":
            normalized["sub2apiStatus"] = "上传失败"
        elif normalized["sub2apiState"] == "disabled":
            normalized["sub2apiStatus"] = "未启用"
        else:
            normalized["sub2apiStatus"] = "待上传"

    timestamp = str(
        normalized.get("updatedAt")
        or normalized.get("createdAt")
        or normalized.get("time")
        or _current_timestamp()
    )
    normalized["createdAt"] = str(normalized.get("createdAt") or normalized.get("time") or timestamp)
    normalized["updatedAt"] = timestamp
    normalized["time"] = normalized["updatedAt"]

    if not normalized["lastError"] and normalized["registrationStatus"] == "failed":
        normalized["lastError"] = normalized["status"] or normalized["plusMessage"] or normalized["sub2apiMessage"]

    return normalized


def parse_account_record(line: str) -> Optional[dict]:
    """
    解析旧账号记录。

    参数:
        line: 文件单行内容
    返回:
        Optional[dict]: 标准化账号记录
        AI by zb
    """
    record = str(line or "").strip()
    if not record:
        return None

    if record.startswith("{"):
        try:
            data = json.loads(record)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            email = str(data.get("email") or "").strip()
            if not email:
                return None
            if "accessToken" not in data and "access_token" in data:
                data["accessToken"] = data.get("access_token")
            return _normalize_account_record(data)

    if "@" not in record:
        return None

    if "----" in record:
        parts = [part.strip() for part in record.split("----")]
        if len(parts) < 2:
            return None
        return _normalize_account_record(
            {
                "email": parts[0],
                "password": parts[1],
                "time": parts[2] if len(parts) > 2 else "",
                "status": parts[3] if len(parts) > 3 else "",
                "accessToken": parts[4] if len(parts) > 4 else "",
            }
        )

    if "|" in record:
        parts = [part.strip() for part in record.split("|")]
        if len(parts) < 2:
            return None
        return _normalize_account_record(
            {
                "email": parts[0],
                "password": parts[1],
                "status": parts[2] if len(parts) > 2 else "",
                "time": parts[3] if len(parts) > 3 else "",
                "accessToken": parts[4] if len(parts) > 4 else "",
            }
        )

    return None


def _record_to_row(record: dict) -> dict:
    """
    将标准化记录转换为数据库字段。

    参数:
        record: 标准化账号记录
    返回:
        dict: 数据库字段映射
        AI by zb
    """
    normalized = _normalize_account_record(record)
    return {
        "email": normalized["email"],
        "password": normalized["password"],
        "status_text": normalized["status"],
        "overall_status": normalized["overallStatus"],
        "registration_status": normalized["registrationStatus"],
        "access_token": normalized["accessToken"],
        "mailbox_context": normalized["mailboxContext"],
        "session_info_json": json.dumps(normalized["sessionInfo"], ensure_ascii=False),
        "plus_called": 1 if normalized["plusCalled"] else 0,
        "plus_success": 1 if normalized["plusSuccess"] else 0,
        "plus_status": normalized["plusState"],
        "plus_status_text": normalized["plusStatus"],
        "plus_message": normalized["plusMessage"],
        "plus_request_id": normalized["plusRequestId"],
        "plus_called_at": normalized["plusCalledAt"],
        "sub2api_uploaded": 1 if normalized["sub2apiUploaded"] else 0,
        "sub2api_status": normalized["sub2apiState"],
        "sub2api_status_text": normalized["sub2apiStatus"],
        "sub2api_message": normalized["sub2apiMessage"],
        "sub2api_uploaded_at": normalized["sub2apiUploadedAt"],
        "sub2api_auto_upload_enabled": 1 if normalized["sub2apiAutoUploadEnabled"] else 0,
        "oauth_tokens_json": json.dumps(normalized["oauthTokens"], ensure_ascii=False),
        "oauth_output_file": normalized["oauthOutputFile"],
        "delivery_info_json": json.dumps(normalized["deliveryInfo"], ensure_ascii=False),
        "created_at": normalized["createdAt"],
        "updated_at": normalized["updatedAt"],
        "last_error": normalized["lastError"],
    }


def _row_to_record(row: sqlite3.Row) -> dict:
    """
    将数据库行转换为标准化账号记录。

    参数:
        row: 数据库行
    返回:
        dict: 标准化账号记录
        AI by zb
    """
    payload = {
        "email": row["email"],
        "password": row["password"],
        "time": row["updated_at"],
        "status": row["status_text"],
        "accessToken": row["access_token"],
        "mailboxContext": row["mailbox_context"],
        "sessionInfo": _safe_json_loads(row["session_info_json"], {}),
        "plusCalled": bool(row["plus_called"]),
        "plusSuccess": bool(row["plus_success"]),
        "plusStatus": row["plus_status_text"],
        "plusMessage": row["plus_message"],
        "plusRequestId": row["plus_request_id"],
        "plusCalledAt": row["plus_called_at"],
        "sub2apiUploaded": bool(row["sub2api_uploaded"]),
        "sub2apiStatus": row["sub2api_status_text"],
        "sub2apiMessage": row["sub2api_message"],
        "sub2apiUploadedAt": row["sub2api_uploaded_at"],
        "sub2apiAutoUploadEnabled": bool(row["sub2api_auto_upload_enabled"]),
        "oauthTokens": _safe_json_loads(row["oauth_tokens_json"], {}),
        "oauthOutputFile": row["oauth_output_file"],
        "deliveryInfo": _safe_json_loads(row["delivery_info_json"], {}),
        "registrationStatus": row["registration_status"],
        "overallStatus": row["overall_status"],
        "plusState": row["plus_status"],
        "sub2apiState": row["sub2api_status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "lastError": row["last_error"],
    }
    return _normalize_account_record(payload)


def _ensure_schema(connection: sqlite3.Connection) -> None:
    """
    初始化数据库表结构。

    参数:
        connection: 数据库连接
        AI by zb
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS accounts (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL DEFAULT 'N/A',
            status_text TEXT NOT NULL DEFAULT '',
            overall_status TEXT NOT NULL DEFAULT 'pending',
            registration_status TEXT NOT NULL DEFAULT 'pending',
            access_token TEXT NOT NULL DEFAULT '',
            mailbox_context TEXT NOT NULL DEFAULT '',
            session_info_json TEXT NOT NULL DEFAULT '{}',
            plus_called INTEGER NOT NULL DEFAULT 0,
            plus_success INTEGER NOT NULL DEFAULT 0,
            plus_status TEXT NOT NULL DEFAULT 'idle',
            plus_status_text TEXT NOT NULL DEFAULT '',
            plus_message TEXT NOT NULL DEFAULT '',
            plus_request_id TEXT NOT NULL DEFAULT '',
            plus_called_at TEXT NOT NULL DEFAULT '',
            sub2api_uploaded INTEGER NOT NULL DEFAULT 0,
            sub2api_status TEXT NOT NULL DEFAULT 'pending',
            sub2api_status_text TEXT NOT NULL DEFAULT '',
            sub2api_message TEXT NOT NULL DEFAULT '',
            sub2api_uploaded_at TEXT NOT NULL DEFAULT '',
            sub2api_auto_upload_enabled INTEGER NOT NULL DEFAULT 0,
            oauth_tokens_json TEXT NOT NULL DEFAULT '{}',
            oauth_output_file TEXT NOT NULL DEFAULT '',
            delivery_info_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_accounts_updated_at ON accounts(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_accounts_overall_status ON accounts(overall_status);
        CREATE INDEX IF NOT EXISTS idx_accounts_registration_status ON accounts(registration_status);
        CREATE INDEX IF NOT EXISTS idx_accounts_plus_status ON accounts(plus_status);
        CREATE INDEX IF NOT EXISTS idx_accounts_sub2api_status ON accounts(sub2api_status);
        """
    )
    _ensure_account_columns(connection)
    connection.execute(
        """
        INSERT INTO meta(key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (SCHEMA_VERSION,),
    )
    connection.commit()


def _ensure_account_columns(connection: sqlite3.Connection) -> None:
    """
    补齐历史数据库缺失的账号字段。

    参数:
        connection: 数据库连接
        AI by zb
    """
    existing_columns = {
        str(row["name"] or "").strip().lower()
        for row in connection.execute("PRAGMA table_info(accounts)").fetchall()
    }
    required_columns = {
        "delivery_info_json": "TEXT NOT NULL DEFAULT '{}'",
    }

    for column_name, definition in required_columns.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE accounts ADD COLUMN {column_name} {definition}")


def _migrate_legacy_accounts(connection: sqlite3.Connection) -> None:
    """
    迁移旧 TXT 账号数据。

    参数:
        connection: 数据库连接
        AI by zb
    """
    existing_count = connection.execute("SELECT COUNT(1) AS total FROM accounts").fetchone()["total"]
    if existing_count:
        return

    legacy_path = _legacy_accounts_path()
    if not legacy_path.exists():
        return

    migrated = 0
    with legacy_path.open("r", encoding="utf-8") as file:
        for line in file:
            record = parse_account_record(line)
            if not record or not record.get("email"):
                continue
            row = _record_to_row(record)
            row["email"] = _normalize_account_email(row.get("email"))
            if not row["email"]:
                continue
            connection.execute(
                """
                INSERT INTO accounts (
                    email, password, status_text, overall_status, registration_status,
                    access_token, mailbox_context, session_info_json,
                    plus_called, plus_success, plus_status, plus_status_text, plus_message,
                    plus_request_id, plus_called_at,
                    sub2api_uploaded, sub2api_status, sub2api_status_text, sub2api_message,
                    sub2api_uploaded_at, sub2api_auto_upload_enabled,
                    oauth_tokens_json, oauth_output_file, delivery_info_json,
                    created_at, updated_at, last_error
                )
                VALUES (
                    :email, :password, :status_text, :overall_status, :registration_status,
                    :access_token, :mailbox_context, :session_info_json,
                    :plus_called, :plus_success, :plus_status, :plus_status_text, :plus_message,
                    :plus_request_id, :plus_called_at,
                    :sub2api_uploaded, :sub2api_status, :sub2api_status_text, :sub2api_message,
                    :sub2api_uploaded_at, :sub2api_auto_upload_enabled,
                    :oauth_tokens_json, :oauth_output_file, :delivery_info_json,
                    :created_at, :updated_at, :last_error
                )
                ON CONFLICT(email) DO UPDATE SET
                    password = excluded.password,
                    status_text = excluded.status_text,
                    overall_status = excluded.overall_status,
                    registration_status = excluded.registration_status,
                    access_token = excluded.access_token,
                    mailbox_context = excluded.mailbox_context,
                    session_info_json = excluded.session_info_json,
                    plus_called = excluded.plus_called,
                    plus_success = excluded.plus_success,
                    plus_status = excluded.plus_status,
                    plus_status_text = excluded.plus_status_text,
                    plus_message = excluded.plus_message,
                    plus_request_id = excluded.plus_request_id,
                    plus_called_at = excluded.plus_called_at,
                    sub2api_uploaded = excluded.sub2api_uploaded,
                    sub2api_status = excluded.sub2api_status,
                    sub2api_status_text = excluded.sub2api_status_text,
                    sub2api_message = excluded.sub2api_message,
                    sub2api_uploaded_at = excluded.sub2api_uploaded_at,
                    sub2api_auto_upload_enabled = excluded.sub2api_auto_upload_enabled,
                    oauth_tokens_json = excluded.oauth_tokens_json,
                    oauth_output_file = excluded.oauth_output_file,
                    delivery_info_json = excluded.delivery_info_json,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    last_error = excluded.last_error
                """,
                row,
            )
            migrated += 1

    if migrated:
        connection.execute(
            """
            INSERT INTO meta(key, value)
            VALUES ('legacy_migrated_at', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (_current_timestamp(),),
        )
        connection.commit()


def _refresh_derived_statuses(connection: sqlite3.Connection) -> None:
    """
    回填状态分类字段，兼容旧数据或历史错误分类。

    参数:
        connection: 数据库连接
        AI by zb
    """
    rows = connection.execute("SELECT * FROM accounts").fetchall()
    for row in rows:
        raw_payload = {
            "email": row["email"],
            "password": row["password"],
            "time": row["updated_at"],
            "status": row["status_text"],
            "accessToken": row["access_token"],
            "mailboxContext": row["mailbox_context"],
            "sessionInfo": _safe_json_loads(row["session_info_json"], {}),
            "plusCalled": bool(row["plus_called"]),
            "plusSuccess": bool(row["plus_success"]),
            "plusStatus": row["plus_status_text"],
            "plusMessage": row["plus_message"],
            "plusRequestId": row["plus_request_id"],
            "plusCalledAt": row["plus_called_at"],
            "sub2apiUploaded": bool(row["sub2api_uploaded"]),
            "sub2apiStatus": row["sub2api_status_text"],
            "sub2apiMessage": row["sub2api_message"],
            "sub2apiUploadedAt": row["sub2api_uploaded_at"],
            "sub2apiAutoUploadEnabled": bool(row["sub2api_auto_upload_enabled"]),
            "oauthTokens": _safe_json_loads(row["oauth_tokens_json"], {}),
            "oauthOutputFile": row["oauth_output_file"],
            "deliveryInfo": _safe_json_loads(row["delivery_info_json"], {}),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "lastError": row["last_error"],
        }
        fresh = _normalize_account_record(raw_payload)
        row_data = _record_to_row(fresh)
        connection.execute(
            """
            UPDATE accounts
            SET overall_status = :overall_status,
                registration_status = :registration_status,
                plus_status = :plus_status,
                plus_status_text = :plus_status_text,
                sub2api_status = :sub2api_status,
                sub2api_status_text = :sub2api_status_text,
                last_error = :last_error
            WHERE email = :email
            """,
            row_data,
        )
    connection.commit()


def ensure_account_store() -> None:
    """
    确保账号数据库已初始化。

    AI by zb
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    with _INIT_LOCK:
        if _INITIALIZED:
            return
        with _connect() as connection:
            _ensure_schema(connection)
            _migrate_legacy_accounts(connection)
            _refresh_derived_statuses(connection)
        _INITIALIZED = True


def count_account_records() -> int:
    """
    统计账号总数。

    返回:
        int: 账号数量
        AI by zb
    """
    ensure_account_store()
    with _connect() as connection:
        row = connection.execute("SELECT COUNT(1) AS total FROM accounts").fetchone()
        return int(row["total"] if row else 0)


def load_account_records() -> list[dict]:
    """
    读取全部账号记录。

    返回:
        list[dict]: 标准化账号记录
        AI by zb
    """
    ensure_account_store()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM accounts
            ORDER BY updated_at DESC, email DESC
            """
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def get_account_record(email: str) -> Optional[dict]:
    """
    按邮箱查询账号记录。

    参数:
        email: 邮箱地址
    返回:
        Optional[dict]: 标准化账号记录
        AI by zb
    """
    ensure_account_store()
    target = _normalize_account_email(email)
    if not target:
        return None

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM accounts
            WHERE LOWER(email) = ?
            ORDER BY updated_at DESC, email DESC
            LIMIT 1
            """,
            (target,),
        ).fetchone()
    return _row_to_record(row) if row else None


def upsert_account_record(email: str, updates: dict) -> dict:
    """
    新增或更新账号记录。

    参数:
        email: 邮箱地址
        updates: 更新字段
    返回:
        dict: 更新后的记录
        AI by zb
    """
    ensure_account_store()
    target = _normalize_account_email(email)
    if not target:
        raise ValueError("邮箱不能为空")

    current = get_account_record(target)
    canonical_email = str((current or {}).get("email") or "").strip() or target
    base_record = current or _normalize_account_record({"email": canonical_email})
    merged = _merge_nested_dict(base_record, updates or {})
    merged["email"] = canonical_email

    current_timestamp = str((updates or {}).get("time") or _current_timestamp())
    merged["createdAt"] = str(base_record.get("createdAt") or base_record.get("time") or current_timestamp)
    merged["updatedAt"] = current_timestamp
    merged["time"] = current_timestamp

    normalized = _normalize_account_record(merged)
    row = _record_to_row(normalized)

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO accounts (
                email, password, status_text, overall_status, registration_status,
                access_token, mailbox_context, session_info_json,
                plus_called, plus_success, plus_status, plus_status_text, plus_message,
                plus_request_id, plus_called_at,
                sub2api_uploaded, sub2api_status, sub2api_status_text, sub2api_message,
                sub2api_uploaded_at, sub2api_auto_upload_enabled,
                oauth_tokens_json, oauth_output_file, delivery_info_json,
                created_at, updated_at, last_error
            )
            VALUES (
                :email, :password, :status_text, :overall_status, :registration_status,
                :access_token, :mailbox_context, :session_info_json,
                :plus_called, :plus_success, :plus_status, :plus_status_text, :plus_message,
                :plus_request_id, :plus_called_at,
                :sub2api_uploaded, :sub2api_status, :sub2api_status_text, :sub2api_message,
                :sub2api_uploaded_at, :sub2api_auto_upload_enabled,
                :oauth_tokens_json, :oauth_output_file, :delivery_info_json,
                :created_at, :updated_at, :last_error
            )
            ON CONFLICT(email) DO UPDATE SET
                password = excluded.password,
                status_text = excluded.status_text,
                overall_status = excluded.overall_status,
                registration_status = excluded.registration_status,
                access_token = excluded.access_token,
                mailbox_context = excluded.mailbox_context,
                session_info_json = excluded.session_info_json,
                plus_called = excluded.plus_called,
                plus_success = excluded.plus_success,
                plus_status = excluded.plus_status,
                plus_status_text = excluded.plus_status_text,
                plus_message = excluded.plus_message,
                plus_request_id = excluded.plus_request_id,
                plus_called_at = excluded.plus_called_at,
                sub2api_uploaded = excluded.sub2api_uploaded,
                sub2api_status = excluded.sub2api_status,
                sub2api_status_text = excluded.sub2api_status_text,
                sub2api_message = excluded.sub2api_message,
                sub2api_uploaded_at = excluded.sub2api_uploaded_at,
                sub2api_auto_upload_enabled = excluded.sub2api_auto_upload_enabled,
                oauth_tokens_json = excluded.oauth_tokens_json,
                oauth_output_file = excluded.oauth_output_file,
                delivery_info_json = excluded.delivery_info_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                last_error = excluded.last_error
            """,
            row,
        )
        connection.commit()

    refreshed = get_account_record(canonical_email)
    if refreshed is None:
        raise RuntimeError("账号记录写入失败")
    return refreshed


def delete_account_record(email: str) -> bool:
    """
    按邮箱删除账号记录。

    参数:
        email: 邮箱地址
    返回:
        bool: 是否删除成功
        AI by zb
    """
    ensure_account_store()
    target = _normalize_account_email(email)
    if not target:
        return False

    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM accounts WHERE LOWER(email) = ?",
            (target,),
        )
        connection.commit()
        return bool(cursor.rowcount)


def query_account_records(
    keyword: str = "",
    registration_status: str = "",
    overall_status: str = "",
    plus_status: str = "",
    sub2api_status: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    分页查询账号记录。

    参数:
        keyword: 关键字
        registration_status: 注册状态
        overall_status: 整体状态
        plus_status: Plus 状态
        sub2api_status: Sub2Api 状态
        page: 页码
        page_size: 每页条数
    返回:
        dict: 查询结果与分页信息
        AI by zb
    """
    ensure_account_store()

    page = max(int(page or 1), 1)
    page_size = max(min(int(page_size or 20), 100), 1)
    where_clauses = []
    params: list[Any] = []

    keyword = str(keyword or "").strip()
    registration_status = str(registration_status or "").strip().lower()
    overall_status = str(overall_status or "").strip().lower()
    plus_status = str(plus_status or "").strip().lower()
    sub2api_status = str(sub2api_status or "").strip().lower()

    if keyword:
        where_clauses.append(
            """
            (
                LOWER(email) LIKE ?
                OR LOWER(password) LIKE ?
                OR LOWER(status_text) LIKE ?
                OR LOWER(plus_status_text) LIKE ?
                OR LOWER(plus_message) LIKE ?
                OR LOWER(sub2api_status_text) LIKE ?
                OR LOWER(sub2api_message) LIKE ?
                OR LOWER(updated_at) LIKE ?
            )
            """
        )
        pattern = f"%{keyword.lower()}%"
        params.extend([pattern, pattern, pattern, pattern, pattern, pattern, pattern, pattern])

    if registration_status in ALLOWED_REGISTRATION_STATES:
        where_clauses.append("registration_status = ?")
        params.append(registration_status)
    if overall_status in ALLOWED_REGISTRATION_STATES:
        where_clauses.append("overall_status = ?")
        params.append(overall_status)
    if plus_status in ALLOWED_PLUS_STATES:
        where_clauses.append("plus_status = ?")
        params.append(plus_status)
    if sub2api_status in ALLOWED_SUB2API_STATES:
        where_clauses.append("sub2api_status = ?")
        params.append(sub2api_status)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    offset = (page - 1) * page_size

    with _connect() as connection:
        total_row = connection.execute(
            f"SELECT COUNT(1) AS total FROM accounts {where_sql}",
            params,
        ).fetchone()
        total = int(total_row["total"] if total_row else 0)
        rows = connection.execute(
            f"""
            SELECT * FROM accounts
            {where_sql}
            ORDER BY updated_at DESC, email DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    items = [_row_to_record(row) for row in rows]
    total_pages = max((total + page_size - 1) // page_size, 1)
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    }


def sanitize_account_record_for_web(record: dict) -> dict:
    """
    生成前端展示数据。

    参数:
        record: 标准化账号记录
    返回:
        dict: 前端展示数据
        AI by zb
    """
    normalized = _normalize_account_record(record)
    has_access_token = bool(normalized.get("accessToken"))
    has_password = bool(normalized.get("password")) and normalized.get("password") != "N/A"
    has_oauth_tokens = bool(
        normalized.get("oauthTokens", {}).get("access_token")
        and normalized.get("oauthTokens", {}).get("refresh_token")
        and normalized.get("oauthTokens", {}).get("id_token")
    )
    delivery_info = normalized.get("deliveryInfo") or {}
    delivery_delivered = bool(delivery_info.get("delivered"))

    return {
        "email": normalized.get("email", ""),
        "password": normalized.get("password", ""),
        "status": normalized.get("status", ""),
        "time": normalized.get("time", ""),
        "registrationStatus": normalized.get("registrationStatus", "pending"),
        "overallStatus": normalized.get("overallStatus", "pending"),
        "plusState": normalized.get("plusState", "idle"),
        "sub2apiState": normalized.get("sub2apiState", "pending"),
        "lastError": normalized.get("lastError", ""),
        "plusCalled": normalized.get("plusCalled", False),
        "plusSuccess": normalized.get("plusSuccess", False),
        "plusStatus": normalized.get("plusStatus", ""),
        "plusMessage": normalized.get("plusMessage", ""),
        "sub2apiUploaded": normalized.get("sub2apiUploaded", False),
        "sub2apiStatus": normalized.get("sub2apiStatus", ""),
        "sub2apiMessage": normalized.get("sub2apiMessage", ""),
        "sub2apiAutoUploadEnabled": normalized.get("sub2apiAutoUploadEnabled", False),
        "deliveryDelivered": delivery_delivered,
        "deliveryVendor": str(delivery_info.get("vendor") or ""),
        "deliveryTargetEmail": str(delivery_info.get("targetEmail") or ""),
        "deliveryStatus": str(delivery_info.get("status") or ("已发货" if delivery_delivered else "未发货")),
        "deliveryMessage": str(delivery_info.get("message") or ""),
        "deliveryTempAccessUrl": str(delivery_info.get("tempAccessUrl") or ""),
        "deliveryMailId": str(delivery_info.get("mailId") or ""),
        "deliveryDeliveredAt": str(delivery_info.get("deliveredAt") or ""),
        "hasAccessToken": has_access_token,
        "hasOAuthTokens": has_oauth_tokens,
        "canCopyAccessToken": has_access_token,
        "canRetryRegistration": bool(
            normalized.get("registrationStatus") != "success"
            and normalized.get("email")
            and has_password
        ),
        "canRetryPlus": bool(has_access_token or has_password),
        "canRetryTeam": bool(has_access_token or has_password),
        "canEditStatus": bool(normalized.get("email")),
        "canDeleteAccount": bool(normalized.get("email")),
        "canUploadSub2api": bool(has_oauth_tokens or has_password),
        "canDeliver": bool(normalized.get("email") and has_password),
    }
