# itwwy/models/user.py

"""
用户表模型（登录 / 注册鉴权用）。

设计要点：
- 密码绝不明文存储，只存「加盐哈希」（见 api/routers/auth_router 的哈希逻辑）。
- username 唯一且建索引，登录时按它查用户。
- 时间字段用 MySQL 的 server_default=now()，由数据库写入，避免应用层时区不一致。
- 当前仅承载「账号 + 密码哈希 + 昵称」，后续如需角色(RBAC)可在此扩展 role 字段。
"""
from datetime import datetime

from models.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, func


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 登录账号：唯一、建索引，作为登录查询的主键
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # 密码加盐哈希（格式：pbkdf2_sha256$iterations$salt$hash），永不存明文
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 昵称：可选，前端展示用，缺省时回落为 username
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 注册时间：数据库自动写入
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
