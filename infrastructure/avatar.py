# itwwy/infrastructure/avatar.py

"""
阿里云万相数字人(灵眸) 云渲染会话客户端。

职责：封装灵眸 OpenAPI 的 CreateChatSession 调用，把阻塞式 SDK 调用
包装成 FastAPI 可以安全 await 的异步函数，供前端初始化云渲染数字人使用。

设计要点：
1. 灵眸 Python SDK(alibabacloud_lingmou20250527 等) 为同步阻塞调用，
   通过 asyncio.to_thread 放到线程池执行，避免阻塞事件循环。
2. alibabacloud 系列 SDK 为「可选依赖」——未安装或仅未配置密钥时，
   不影响整个后端启动，相关接口会返回明确的错误提示。
3. 客户端单例复用：首次请求时惰性建立，后续复用。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from conf.config import settings

logger = logging.getLogger(__name__)

# 灵眸 OpenAPI 客户端单例（惰性建立）
_client = None


def init_avatar_client() -> None:
    """
    在 FastAPI lifespan 中调用，提前校验配置是否就绪。

    这里【不】强制建立连接、也不强制 import SDK，
    目的是避免「未安装 SDK / 仅未配置密钥」时拖垮整个应用启动。
    """
    global _client
    if _client is not None:
        return
    if not settings.avatar_access_key_id or not settings.avatar_access_key_secret:
        logger.warning(
            "灵眸 Avatar AccessKey 未配置，/api/avatar/session 将返回明确错误（不影响其他功能）。"
        )
        return
    logger.info("灵眸 Avatar 配置已就绪，将在首次请求时惰性建立客户端。")


def _build_client():
    """真正建立灵眸客户端（延迟导入，避免未安装 SDK 时模块加载失败）。"""
    from alibabacloud_lingmou20250527.client import Client as LingMouClient
    from alibabacloud_tea_openapi import models as open_api_models

    config = open_api_models.Config(
        access_key_id=settings.avatar_access_key_id,
        access_key_secret=settings.avatar_access_key_secret,
    )
    # 灵眸服务接入点（如 lingmou.cn-beijing.aliyuncs.com）
    config.endpoint = settings.avatar_endpoint or "lingmou.cn-beijing.aliyuncs.com"
    return LingMouClient(config)


def _get_client():
    """获取（惰性建立）灵眸客户端单例。"""
    global _client
    if _client is None:
        if not settings.avatar_access_key_id or not settings.avatar_access_key_secret:
            raise RuntimeError(
                "灵眸 Avatar AccessKey 未配置，请在 .env 设置 "
                "AVATAR_ACCESS_KEY_ID / AVATAR_ACCESS_KEY_SECRET"
            )
        _client = _build_client()
    return _client


def missing_avatar_settings() -> list[str]:
    """
    一次性列出云渲染所缺的全部配置项（返回中文可读名称）。

    云渲染只需 3 项：AccessKeyId/Secret + 项目ID + 实例ID；
    license 仅端渲染需要，云渲染不必填。
    """
    missing: list[str] = []
    if not settings.avatar_access_key_id:
        missing.append("AVATAR_ACCESS_KEY_ID（阿里云 AccessKey ID）")
    if not settings.avatar_access_key_secret:
        missing.append("AVATAR_ACCESS_KEY_SECRET（阿里云 AccessKey Secret）")
    if not settings.avatar_project_id:
        missing.append("AVATAR_PROJECT_ID（灵眸控制台对话项目的项目 ID）")
    if not settings.avatar_instance_id:
        missing.append("AVATAR_INSTANCE_ID（阿里云订单详情里的实例 ID）")
    return missing


def _rtc_params_to_dict(rtc) -> dict[str, Any]:
    """把 SDK 返回的 rtc_params 对象转成前端 SDK 需要的 camelCase 字典。"""
    if rtc is None:
        return {}
    return {
        "appId": getattr(rtc, "app_id", None),
        "channel": getattr(rtc, "channel", None),
        "nonce": getattr(rtc, "nonce", None),
        "timestamp": getattr(rtc, "timestamp", None),
        "token": getattr(rtc, "token", None),
        "gslb": getattr(rtc, "gslb", None),
        "clientUserId": getattr(rtc, "client_user_id", None),
        "serverUserId": getattr(rtc, "server_user_id", None),
        "avatarUserId": getattr(rtc, "avatar_user_id", None),
    }


def _avatar_assets_to_dict(assets) -> dict[str, Any]:
    """把 SDK 返回的 avatar_assets 对象转成前端需要的字典（可能缺省）。"""
    if assets is None:
        return {}
    return {
        "type": getattr(assets, "type", None),
        "url": getattr(assets, "url", None),
        "md5": getattr(assets, "md5", None),
        "secret": getattr(assets, "secret", None),
        "minRequiredVersion": getattr(assets, "min_required_version", None),
    }


def _do_create(device_id: str) -> dict[str, Any]:
    """
    执行一次 CreateChatSession（同步阻塞，由调用方放到线程池）。

    project_id 为控制台对话项目 ID，作为 create_chat_session 的位置参数传入；
    request 体里只填 instance_id 等可选字段（云渲染无需 license / platform）。
    """
    from alibabacloud_lingmou20250527 import models as lm_models
    from alibabacloud_tea_util import models as util_models

    # 先一次性把缺的项全说出来，避免用户一项项试错
    missing = missing_avatar_settings()
    if missing:
        raise RuntimeError(
            "灵眸云渲染配置不完整，缺少以下 .env 项："
            + "、".join(missing)
            + "。（云渲染不需要 AVATAR_LICENSE；AccessKey 申请见 "
              "https://ram.console.aliyun.com/manage/ak ，项目ID见百炼控制台「对话互动」，"
              "实例ID见阿里云「我的订单」的数字人实时交互服务订单详情）"
        )

    client = _get_client()
    project_id = settings.avatar_project_id

    # 按需组装请求参数（云渲染：只需 instance_id，device_id 用于并发隔离）
    req_kwargs: dict[str, Any] = {"instance_id": settings.avatar_instance_id}
    if device_id:
        req_kwargs["device_id"] = device_id
    # license / platform 仅端渲染需要，这里若配置了也一并带上（云渲染可忽略）
    if settings.avatar_license:
        req_kwargs["license"] = settings.avatar_license
    if settings.avatar_platform:
        req_kwargs["platform"] = settings.avatar_platform

    req = lm_models.CreateChatSessionRequest(**req_kwargs)

    resp = client.create_chat_session_with_options(
        project_id, req, {}, util_models.RuntimeOptions()
    )
    # 服务端业务错误（项目未发布、实例不匹配等）在此抛出，附带官方排查提示
    body = getattr(resp, "body", None)
    if body is not None and not getattr(body, "success", True):
        raise RuntimeError(
            f"灵眸 CreateChatSession 失败：code={getattr(body, 'code', None)} "
            f"message={getattr(body, 'message', None)} "
            f"request_id={getattr(body, 'request_id', None)}。"
            "常见原因：对话项目未发布、实例与资产类型不匹配、AccessKey 无权限。"
        )
    data = getattr(resp, "body", None)
    if data is None or getattr(data, "data", None) is None:
        raise RuntimeError(
            "CreateChatSession 返回空 data, request_id="
            f"{getattr(body, 'request_id', None)}"
        )
    payload = data.data
    return {
        "sessionId": payload.session_id,
        "rtcParams": _rtc_params_to_dict(payload.rtc_params),
        "avatarAssets": _avatar_assets_to_dict(payload.avatar_assets),
    }


async def create_chat_session(device_id: str | None = None) -> dict[str, Any]:
    """
    创建一次数字人云渲染会话，返回前端 SDK 初始化所需 JSON。

    通过 asyncio.to_thread 把阻塞的 SDK 调用丢到线程池，保持事件循环不被卡住。
    """
    device = device_id or str(uuid.uuid4())
    return await asyncio.to_thread(_do_create, device)
