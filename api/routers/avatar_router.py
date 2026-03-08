# itwwy/api/routers/avatar_router.py

"""
数字人相关 HTTP 接口（凭证下发 + 会话创建 + 配置查询）。

三个接口职责：
  1. GET /api/digital-human/config
     -> 前端启动时读取：当前默认厂商、魔珐/灵眸是否已配置凭证。
        用于在 UI 上提示「未配置」而不是静默失败。
  2. GET /api/digital-human/credentials
     -> 魔珐星云 SDK 初始化凭证（app_id / app_secret / gateway_server）。
        关键安全原则：密钥只存在于后端 .env，前端动态获取，绝不硬编码源码。
  3. GET /api/avatar/session
     -> 阿里灵眸云渲染会话参数（sessionId + rtcParams + avatarAssets）。
        前端 lm-avatar-chat-sdk 初始化时需要。
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Query

from api.schemas import AvatarSessionResponse
from conf.config import settings
from infrastructure import avatar

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/digital-human/config")
async def get_digital_human_config():
    """
    前端读取数字人全局配置。

    返回: provider(默认厂商), moxia_configured(魔珐凭证是否就绪),
          lingmou_configured(灵眸凭证+项目是否就绪)。
    """
    return {
        "provider": settings.digital_human_provider,
        "moxia_configured": bool(
            settings.digital_human_app_id and settings.digital_human_app_secret
        ),
        "lingmou_configured": not avatar.missing_avatar_settings(),
    }


@router.get("/api/digital-human/credentials")
async def get_digital_human_credentials():
    """
    前端获取魔珐星云 SDK 初始化凭证。

    密钥仅存后端 .env，不暴露在前端源码中（消除代码仓库泄露风险）。
    未配置时返回 configured=false，由前端提示用户去配置。
    """
    if not settings.digital_human_app_id or not settings.digital_human_app_secret:
        return {
            "app_id": "",
            "app_secret": "",
            "gateway_server": settings.digital_human_gateway_server,
            "configured": False,
        }
    return {
        "app_id": settings.digital_human_app_id,
        "app_secret": settings.digital_human_app_secret,
        "gateway_server": settings.digital_human_gateway_server,
        "configured": True,
    }


@router.get("/api/avatar/session", response_model=AvatarSessionResponse)
async def create_avatar_session(
    sender_id: str | None = Query(default=None, description="可选: 透传作为 deviceId 用于并发隔离"),
):
    """
    创建/复用数字人云渲染会话，返回前端 lm-avatar-chat-sdk 初始化所需参数。

    依赖可选的 alibabacloud-lingmou SDK；未安装或配置缺失时返回明确错误。
    """
    try:
        data = await avatar.create_chat_session(device_id=sender_id)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="alibabacloud-lingmou SDK 未安装，请先执行 pip install alibabacloud-lingmou20250527 等依赖。",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AvatarSessionResponse(**data)
