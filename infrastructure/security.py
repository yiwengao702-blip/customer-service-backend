# itwwy/infrastructure/security.py

"""
账号安全工具：密码哈希 + 自实现 JWT（无第三方依赖）。

为什么自实现 JWT 而不引 PyJWT：
- 本项目鉴权是「自实现 JWT」约定（与电商运营门户一致），功能简单、无需重型库；
- 仅用标准库 hashlib / hmac / base64 / json，零额外依赖、零编译风险，离线可跑。

密码方案：pbkdf2_hmac('sha256', password, salt, 100000) —— 加盐慢哈希，抗暴力破解。
令牌方案：header.payload.signature 三段式，用 HMAC-SHA256 对前两段签名，结构对齐标准 JWT，
但仅依赖标准库实现，方便审计与调试。
"""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from conf.config import settings

# ── 密码哈希 ──────────────────────────────────────────────────────────────
# 存储格式：pbkdf2_sha256$<迭代次数>$<salt(base64)>$<hash(base64)>
_PBKDF2_ALG = "sha256"
_PBKDF2_ITERATIONS = 100_000


def _b64_encode(data: bytes) -> str:
    """URL 安全的 base64 编码（去掉 padding），用于令牌各段。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def hash_password(password: str) -> str:
    """对明文密码做加盐慢哈希，返回可存储的格式化字符串。"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(_PBKDF2_ALG, password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${_b64_encode(salt)}${_b64_encode(dk)}"


def verify_password(password: str, stored: str) -> bool:
    """校验明文密码是否与存储的哈希匹配（恒定时间比较，防时序攻击）。"""
    try:
        alg, iter_str, salt_b64, hash_b64 = stored.split("$")
        # 注意：stored 前缀是 "pbkdf2_sha256"（标签），真正的哈希算法名是 "sha256"，
        # 必须传给 pbkdf2_hmac，不能把整个标签当作算法名（否则会抛 UnsupportedDigestmodError）。
        if alg != f"pbkdf2_{_PBKDF2_ALG}":
            return False
        iterations = int(iter_str)
        salt = base64.urlsafe_b64decode(salt_b64 + "=" * (-len(salt_b64) % 4))
        expected = base64.urlsafe_b64decode(hash_b64 + "=" * (-len(hash_b64) % 4))
    except (ValueError, base64.binascii.Error):
        return False
    dk = hashlib.pbkdf2_hmac(_PBKDF2_ALG, password.encode("utf-8"), salt, iterations)
    # hmac.compare_digest：恒定时间比较，避免泄露哈希是否逐字节匹配
    return hmac.compare_digest(dk, expected)


# ── 自实现 JWT ──────────────────────────────────────────────────────────
def _b64url_json(obj: Any) -> str:
    return _b64_encode(json.dumps(obj, separators=(",", ":")).encode("utf-8"))


def _sign(signing_input: str) -> str:
    sig = hmac.new(
        settings.auth_secret.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64_encode(sig)


def create_token(sub: int | str, username: str, extra: dict | None = None) -> str:
    """签发令牌：payload 含 sub(用户ID)、username、exp(过期时间戳)。"""
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": sub,
        "username": username,
        "exp": int(time.time()) + settings.jwt_expire_minutes * 60,
    }
    if extra:
        payload.update(extra)
    signing_input = f"{_b64url_json(header)}.{_b64url_json(payload)}"
    return f"{signing_input}.{_sign(signing_input)}"


def decode_token(token: str) -> dict | None:
    """校验并解码令牌：签名不符或过期返回 None（调用方据此判 401）。"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signing_input = f"{parts[0]}.{parts[1]}"
        expected_sig = _sign(signing_input)
        # 恒定时间比较签名，防时序侧信道
        if not hmac.compare_digest(expected_sig, parts[2]):
            return None
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        if "exp" in payload and payload["exp"] < int(time.time()):
            return None  # 已过期
        return payload
    except (ValueError, base64.binascii.Error, json.JSONDecodeError):
        return None
