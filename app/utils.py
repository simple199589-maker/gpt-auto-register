"""
工具函数模块
包含通用的辅助函数
"""

import random
import string
import csv
import os
import re
import time
import json
from datetime import datetime
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import (
    PASSWORD_LENGTH,
    PASSWORD_CHARS,
    PASSWORD_CHARS,
    TXT_FILE,
    HTTP_MAX_RETRIES,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT,
    USER_AGENT,
    MIN_AGE,
    MAX_AGE
)
from app.account_store import (
    delete_account_record as _store_delete_account_record,
    get_account_record as _store_get_account_record,
    load_account_records as _store_load_account_records,
    parse_account_record as _store_parse_account_record,
    sanitize_account_record_for_web as _store_sanitize_account_record_for_web,
    upsert_account_record as _store_upsert_account_record,
)

# 尝试导入 Faker 库
try:
    from faker import Faker
    # 创建多语言环境的 Faker 实例（英语为主，增加真实感）
    fake = Faker(['en_US', 'en_GB'])
    # 设置随机种子以确保可重复性（可选）
    # Faker.seed(0)
    FAKER_AVAILABLE = True
    print("✅ Faker 库已加载，将使用更真实的假数据")
except ImportError:
    FAKER_AVAILABLE = False
    print("⚠️ Faker 库未安装，将使用内置姓名列表")
    print("   安装命令: pip install Faker")

# ============================================================
# 常用英文名字库（用于随机生成用户姓名）
# ============================================================

FIRST_NAMES = [
    # 男性名字
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Christopher", "Daniel", "Matthew", "Anthony", "Mark",
    "Donald", "Steven", "Paul", "Andrew", "Joshua", "Kenneth", "Kevin", "Brian",
    "George", "Timothy", "Ronald", "Edward", "Jason", "Jeffrey", "Ryan",
    # 女性名字
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan",
    "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
    "Ashley", "Kimberly", "Emily", "Donna", "Michelle", "Dorothy", "Carol",
    "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon", "Laura", "Cynthia"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen",
    "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell"
]


def create_http_session():
    """
    创建带有重试机制的 HTTP Session
    
    返回:
        requests.Session: 配置好重试策略的 Session 对象
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=HTTP_MAX_RETRIES,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# 创建全局 HTTP Session
http_session = create_http_session()


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
}


def get_user_agent():
    """
    获取 User-Agent 字符串
    
    返回:
        str: User-Agent
    """
    return USER_AGENT


def generate_random_password(length=None):
    """
    生成随机密码
    确保密码包含大写字母、小写字母、数字和特殊字符
    
    参数:
        length: 密码长度，默认使用配置文件中的值
    
    返回:
        str: 生成的密码
    """
    if length is None:
        length = PASSWORD_LENGTH
    
    # 先随机生成指定长度的密码
    password = ''.join(random.choice(PASSWORD_CHARS) for _ in range(length))
    
    # 确保包含各类字符（替换前4位）
    password = (
        random.choice(string.ascii_uppercase) +   # 大写字母
        random.choice(string.ascii_lowercase) +   # 小写字母
        random.choice(string.digits) +            # 数字
        random.choice("!@#$%") +                  # 特殊字符
        password[4:]                              # 剩余部分
    )
    
    print(f"✅ 已生成密码: {password}")
    return password


def _merge_nested_dict(base: dict, updates: dict):
    """
    递归合并字典，保留未覆盖字段。

    参数:
        base: 原始字典
        updates: 更新字典
    返回:
        dict: 合并后的字典
        AI by zb
    """
    merged = dict(base or {})
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nested_dict(merged.get(key, {}), value)
        else:
            merged[key] = value
    return merged


def _normalize_account_record(record: dict):
    """
    将账号记录补全为标准结构。

    参数:
        record: 原始账号记录
    返回:
        dict: 标准化后的账号记录
        AI by zb
    """
    normalized = _merge_nested_dict(ACCOUNT_RECORD_DEFAULTS, record or {})
    normalized["email"] = str(normalized.get("email") or "").strip()
    normalized["password"] = str(normalized.get("password") or "N/A")
    normalized["time"] = str(normalized.get("time") or "")
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
    normalized["plusCalled"] = bool(normalized.get("plusCalled"))
    normalized["plusSuccess"] = bool(normalized.get("plusSuccess"))
    normalized["sub2apiUploaded"] = bool(normalized.get("sub2apiUploaded"))
    normalized["sub2apiAutoUploadEnabled"] = bool(normalized.get("sub2apiAutoUploadEnabled"))
    normalized["sessionInfo"] = (
        normalized.get("sessionInfo")
        if isinstance(normalized.get("sessionInfo"), dict)
        else {}
    )
    oauth_tokens = normalized.get("oauthTokens")
    if not isinstance(oauth_tokens, dict):
        oauth_tokens = {}
    normalized["oauthTokens"] = {
        "access_token": str(oauth_tokens.get("access_token") or ""),
        "refresh_token": str(oauth_tokens.get("refresh_token") or ""),
        "id_token": str(oauth_tokens.get("id_token") or ""),
        "account_id": str(oauth_tokens.get("account_id") or ""),
    }

    status = normalized["status"]
    if not normalized["plusStatus"] and status and (
        "Plus" in status or "激活" in status or "Token" in status
    ):
        normalized["plusStatus"] = status
    if not normalized["plusSuccess"] and "已激活Plus" in status:
        normalized["plusSuccess"] = True
        normalized["plusCalled"] = True
    if normalized["plusSuccess"]:
        normalized["plusCalled"] = True
    if not normalized["sub2apiStatus"] and "Sub2Api" in status:
        normalized["sub2apiStatus"] = status
    if not normalized["sub2apiUploaded"] and "已上传Sub2Api" in status:
        normalized["sub2apiUploaded"] = True
    if normalized["accessToken"] and not normalized["plusCalled"]:
        normalized["plusCalled"] = True
    return normalized


def parse_account_record(line: str):
    """
    解析账号记录，兼容 JSON、`----` 与 `|` 三种格式。

    参数:
        line: 文件中的原始单行记录
    返回:
        dict | None: 标准化后的账号记录
        AI by zb
    """
    return _store_parse_account_record(line)


def _serialize_account_record(record: dict) -> str:
    """
    将标准化账号记录序列化为单行 JSON，避免 accessToken 与旧分隔符冲突。

    参数:
        record: 标准化账号记录
    返回:
        str: 单行 JSON 字符串
        AI by zb
    """
    payload = _normalize_account_record(record)
    return json.dumps(payload, ensure_ascii=False)


def load_account_records():
    """
    读取全部账号记录。

    返回:
        list[dict]: 标准化账号记录列表
        AI by zb
    """
    return _store_load_account_records()


def get_account_record(email: str):
    """
    按邮箱查找账号记录。

    参数:
        email: 邮箱地址
    返回:
        dict | None: 标准化账号记录
        AI by zb
    """
    return _store_get_account_record(email)


def upsert_account_record(email: str, updates: dict):
    """
    按邮箱新增或更新账号记录。

    参数:
        email: 邮箱地址
        updates: 更新字段
    返回:
        dict: 更新后的账号记录
        AI by zb
    """
    return _store_upsert_account_record(email, updates)


def delete_account_record(email: str):
    """
    按邮箱删除账号记录。

    参数:
        email: 邮箱地址
    返回:
        bool: 是否删除成功
        AI by zb
    """
    return _store_delete_account_record(email)


def sanitize_account_record_for_web(record: dict):
    """
    生成前端可安全展示的账号数据。

    参数:
        record: 标准化账号记录
    返回:
        dict: 脱敏后的账号记录
        AI by zb
    """
    return _store_sanitize_account_record_for_web(record)


def save_to_txt(
    email: str,
    password: str = None,
    status: str = "已注册",
    access_token: str = None,
    extra: dict = None,
):
    """
    保存账号信息到 TXT 文件。

    新写入数据使用 JSON 单行格式，兼容保留旧记录的读取与更新逻辑。
    """
    try:
        updates = {
            "email": email,
            "password": password if password else "N/A",
            "status": status,
            "accessToken": access_token if access_token is not None else "",
        }
        if not password:
            updates.pop("password", None)
        if access_token is None:
            updates.pop("accessToken", None)
        if extra:
            updates = _merge_nested_dict(updates, extra)
        upsert_account_record(email, updates)
            
        print(f"💾 账号状态已更新: {status}")
        
    except Exception as e:
        print(f"❌ 保存/更新账号信息失败: {e}")

def update_account_status(
    email: str,
    new_status: str,
    password: str = None,
    access_token: str = None,
    extra: dict = None,
):
    """
    专门用于更新账号状态的快捷函数
    
    参数:
        email: 邮箱地址
        new_status: 新的状态字符串
        password: 如果需要更新密码，则传入新密码，否则为 None
        access_token: 如果需要更新 accessToken，则传入值，否则为 None
    """
    save_to_txt(email, password, new_status, access_token=access_token, extra=extra)


def extract_verification_code(content: str):
    """
    从邮件内容中提取 6 位数字验证码
    
    参数:
        content: 邮件内容（HTML 或纯文本）
    
    返回:
        str: 提取到的验证码，未找到返回 None
    """
    if not content:
        return None
    
    # 验证码匹配模式（按优先级排列）
    patterns = [
        r'代码为\s*(\d{6})',           # 中文格式
        r'code is\s*(\d{6})',          # 英文格式
        r'verification code[:\s]*(\d{6})',  # 完整英文格式
        r'(\d{6})',                     # 通用 6 位数字
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            code = matches[0]
            print(f"  ✅ 提取到验证码: {code}")
            return code
    
    return None


def generate_random_name():
    """
    生成随机英文姓名
    
    使用 Faker 库生成更真实的姓名，如果 Faker 不可用则回退到内置列表
    
    返回:
        str: 格式为 "FirstName LastName" 的随机姓名
    """
    if FAKER_AVAILABLE:
        # 使用 Faker 直接生成名和姓，避免前缀后缀问题
        # 随机选择生成男性或女性名字
        if random.choice([True, False]):
            first_name = fake.first_name_male()
        else:
            first_name = fake.first_name_female()
        
        last_name = fake.last_name()
        full_name = f"{first_name} {last_name}"
    else:
        # 回退到内置列表
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        full_name = f"{first_name} {last_name}"
    
    print(f"✅ 已生成随机姓名: {full_name}")
    return full_name


def generate_random_birthday():
    """
    生成随机生日
    确保年龄在配置的范围内（MIN_AGE 到 MAX_AGE）
    
    使用 Faker 库生成更真实的生日日期
    
    返回:
        tuple: (年份字符串, 月份字符串, 日期字符串)
               例如: ("1995", "03", "15")
    """
    if FAKER_AVAILABLE:
        # 使用 Faker 生成符合年龄范围的生日
        birthday = fake.date_of_birth(minimum_age=MIN_AGE, maximum_age=MAX_AGE)
        year_str = str(birthday.year)
        month_str = str(birthday.month).zfill(2)
        day_str = str(birthday.day).zfill(2)
    else:
        # 回退到原始逻辑
        from datetime import datetime as dt
        today = dt.now()
        
        min_birth_year = today.year - MAX_AGE
        max_birth_year = today.year - MIN_AGE
        birth_year = random.randint(min_birth_year, max_birth_year)
        birth_month = random.randint(1, 12)
        
        if birth_month in [1, 3, 5, 7, 8, 10, 12]:
            max_day = 31
        elif birth_month in [4, 6, 9, 11]:
            max_day = 30
        else:
            if (birth_year % 4 == 0 and birth_year % 100 != 0) or (birth_year % 400 == 0):
                max_day = 29
            else:
                max_day = 28
        
        birth_day = random.randint(1, max_day)
        
        year_str = str(birth_year)
        month_str = str(birth_month).zfill(2)
        day_str = str(birth_day).zfill(2)
    
    print(f"✅ 已生成随机生日: {year_str}/{month_str}/{day_str}")
    return year_str, month_str, day_str


def generate_user_info():
    """
    生成完整的随机用户信息
    
    返回:
        dict: 包含姓名和生日的字典
              {
                  'name': 'John Smith',
                  'year': '1995',
                  'month': '03',
                  'day': '15'
              }
    """
    name = generate_random_name()
    year, month, day = generate_random_birthday()
    
    return {
        'name': name,
        'year': year,
        'month': month,
        'day': day
    }


def generate_japan_address():
    """
    生成随机日本地址
    使用 Faker 生成更真实多样的日本地址
    """
    if FAKER_AVAILABLE:
        # 创建日本本地化的 Faker 实例
        fake_jp = Faker('ja_JP')
        
        # 日本主要城市的区域信息
        tokyo_wards = [
            {"ward": "Chiyoda-ku", "zip_prefix": "100"},
            {"ward": "Shibuya-ku", "zip_prefix": "150"},
            {"ward": "Shinjuku-ku", "zip_prefix": "160"},
            {"ward": "Minato-ku", "zip_prefix": "105"},
            {"ward": "Meguro-ku", "zip_prefix": "153"},
            {"ward": "Setagaya-ku", "zip_prefix": "154"},
            {"ward": "Nakano-ku", "zip_prefix": "164"},
            {"ward": "Toshima-ku", "zip_prefix": "170"},
        ]
        
        osaka_areas = [
            {"area": "Kita-ku", "zip_prefix": "530"},
            {"area": "Chuo-ku", "zip_prefix": "540"},
            {"area": "Nishi-ku", "zip_prefix": "550"},
            {"area": "Tennoji-ku", "zip_prefix": "543"},
        ]
        
        # 随机选择城市
        if random.random() < 0.7:  # 70% 东京
            ward_info = random.choice(tokyo_wards)
            addr = {
                "zip": f"{ward_info['zip_prefix']}-{random.randint(1000, 9999)}",
                "state": "Tokyo",
                "city": ward_info["ward"],
                "address1": f"{random.randint(1, 9)}-{random.randint(1, 30)}-{random.randint(1, 20)}"
            }
        else:  # 30% 大阪
            area_info = random.choice(osaka_areas)
            addr = {
                "zip": f"{area_info['zip_prefix']}-{random.randint(1000, 9999)}",
                "state": "Osaka",
                "city": area_info["area"],
                "address1": f"{random.randint(1, 9)}-{random.randint(1, 30)}-{random.randint(1, 20)}"
            }
    else:
        # 回退到旧的固定地址列表
        addresses = [
            {"zip": "100-0005", "state": "Tokyo", "city": "Chiyoda-ku", "address1": "1-1 Marunouchi"},
            {"zip": "160-0022", "state": "Tokyo", "city": "Shinjuku-ku", "address1": "3-14-1 Shinjuku"},
            {"zip": "150-0002", "state": "Tokyo", "city": "Shibuya-ku", "address1": "2-21-1 Shibuya"},
            {"zip": "530-0001", "state": "Osaka", "city": "Osaka-shi", "address1": "1-1 Umeda"},
        ]
        addr = random.choice(addresses)
        random_suffix = f"{random.randint(1, 9)}-{random.randint(1, 20)}"
        addr["address1"] = f"{addr['address1']} {random_suffix}"
    
    print(f"✅ 已生成日本地址: {addr['state']} {addr['city']} {addr['address1']}")
    return addr


def generate_us_address():
    """
    生成随机美国地址
    使用预置的真实州/城市/邮编组合，避免生成不匹配的地址
    """
    address_pool = [
        {"zip": "19801", "state": "Delaware", "state_code": "DE", "city": "Wilmington"},
        {"zip": "19901", "state": "Delaware", "state_code": "DE", "city": "Dover"},
        {"zip": "97201", "state": "Oregon", "state_code": "OR", "city": "Portland"},
        {"zip": "97301", "state": "Oregon", "state_code": "OR", "city": "Salem"},
        {"zip": "59101", "state": "Montana", "state_code": "MT", "city": "Billings"},
        {"zip": "59601", "state": "Montana", "state_code": "MT", "city": "Helena"},
        {"zip": "03101", "state": "New Hampshire", "state_code": "NH", "city": "Manchester"},
        {"zip": "03301", "state": "New Hampshire", "state_code": "NH", "city": "Concord"},
    ]
    address_base = dict(random.choice(address_pool))

    street_number = random.randint(100, 9999)
    street_names = [
        "Main St",
        "Oak Ave",
        "Maple Dr",
        "Cedar Ln",
        "Park Blvd",
        "Washington St",
        "Lincoln Ave",
        "Jefferson Dr",
        "Madison Ln",
    ]
    street = random.choice(street_names)
    addr = {
        "zip": address_base["zip"],
        "state": address_base["state"],
        "state_code": address_base["state_code"],
        "city": address_base["city"],
        "address1": f"{street_number} {street}",
    }
    
    print(f"✅ 已生成美国地址: {addr['city']}, {addr['state']} {addr['zip']}")
    return addr


def generate_billing_info(country="JP"):
    """
    生成完整的支付账单信息（姓名 + 地址）
    
    参数:
        country: 国家代码，"JP" 或 "US"
    
    返回:
        dict: 包含姓名和地址的完整账单信息
    """
    # 生成姓名
    name = generate_random_name()
    
    # 根据国家生成地址
    if country.upper() == "US":
        address = generate_us_address()
    else:
        address = generate_japan_address()
    
    billing_info = {
        "name": name,
        "zip": address["zip"],
        "state": address["state"],
        "state_code": address.get("state_code", address["state"]),
        "city": address["city"],
        "address1": address["address1"],
        "country": country.upper(),
        "country_name": "United States" if country.upper() == "US" else "Japan",
    }
    
    print(f"📋 完整账单信息已生成:")
    print(f"   姓名: {billing_info['name']}")
    print(f"   地址: {billing_info['address1']}, {billing_info['city']}")
    print(f"   州/省: {billing_info['state']}, 邮编: {billing_info['zip']}")
    
    return billing_info


