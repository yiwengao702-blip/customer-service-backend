# itwwy/api/routers/auth_router.py

"""
账号鉴权路由：注册 / 登录 / 当前用户。

接口一览：
- POST /api/auth/register  注册新账号（用户名唯一），返回令牌 + 用户信息
- POST /api/auth/login     账号密码登录，返回令牌 + 用户信息
- GET  /api/auth/me        携带 Bearer 令牌返回当前用户信息（前端探活 / 刷新会话用）

安全约定：
- 密码用 pbkdf2_hmac 加盐慢哈希存储（见 infrastructure/security.py），从不落库明文。
- 令牌为自实现 JWT（HMAC-SHA256 签名），前端存于 localStorage，后续请求带 Authorization。
- 所有接口在 app/api/routers/dependencies.py 的 get_current_user 统一校验令牌。
"""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from api.routers.dependencies import get_current_user, get_session
from infrastructure.security import hash_password, verify_password, create_token
from models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 用户名规则：3-32 位，仅允许字母/数字/下划线
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")


class RegisterRequest(BaseModel):
    username: str
    password: str
    nickname: str | None = None

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("用户名需为 3-32 位字母/数字/下划线")
        return v

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少 6 位")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    """对外返回的用户信息（绝不携带 password_hash）。"""
    id: int
    username: str
    nickname: str | None


class AuthResult(BaseModel):
    token: str
    user: UserInfo


def _to_user_info(user: User) -> UserInfo:
    return UserInfo(id=user.id, username=user.username, nickname=user.nickname)


# ───────────────────────────────────────────────────────────────
# 注册
# ───────────────────────────────────────────────────────────────
@router.post("/register", response_model=AuthResult)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)):
        # 用户名唯一性校验
        existing = await session.scalar(select(User).where(User.username == req.username))
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"用户名「{req.username}」已被注册",
            )
        user = User(
            username=req.username,
            password_hash=hash_password(req.password),
            nickname=req.nickname or req.username,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_token(sub=user.id, username=user.username)
        return AuthResult(token=token, user=_to_user_info(user))


# ───────────────────────────────────────────────────────────────
# 登录
# ───────────────────────────────────────────────────────────────
@router.post("/login", response_model=AuthResult)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)):
        user = await session.scalar(select(User).where(User.username == req.username))
        # 账号不存在 或 密码不符，统一返回 401（不暴露具体是哪一项，防账号枚举）
        if user is None or not verify_password(req.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        token = create_token(sub=user.id, username=user.username)
        return AuthResult(token=token, user=_to_user_info(user))


# ───────────────────────────────────────────────────────────────
# 当前用户（探活 / 前端启动恢复会话）
# ───────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserInfo)
async def me(current_user: User = Depends(get_current_user)):
    return _to_user_info(current_user)
