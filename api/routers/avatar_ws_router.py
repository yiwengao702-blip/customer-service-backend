# itwwy/api/routers/avatar_ws_router.py

"""
数字人(阿里灵眸) 聊天 WebSocket 接口 —— transcript 模式。

当前项目采用 transcript 模式：后端只负责生成并推送「文本」，不做 TTS、也不推 PCM 音频。
声音、唇形、画面渲染全部由阿里云灵眸服务端完成。

链路：
  用户文本 --> 本接口 --> 复用 DialogueService 生成回复文本
            --> 通过 WebSocket 把 bot_text 推回前端
            --> 前端调用 lm-avatar-chat-sdk 的 requestToRespond(transcript, text)
            --> 灵眸服务端完成 TTS + 唇形 + 云渲染，浏览器经 RTC 收到音视频流。

协议(JSON 文本帧)：
  客户端 -> 服务端:
    {"type":"user_text","sender_id":"u1","text":"...","message_id":"(可选)"}
  服务端 -> 客户端:
    {"type":"user_ack","message_id":"..."}
    {"type":"bot_text","message_id":"...","index":0,"text":"...","object":{...}}
    {"type":"turn_end","message_id":"..."}
    {"type":"interrupt"}                 # 要求前端立即停播（新消息到达）
    {"type":"error","message":"..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.routers.dependencies import get_engine
from domain.messages import FocusedObject, MessageType, UserMessage
from infrastructure import database
from repository.dialogue_state_repository import DialogueStateRepository
from service.dialogue_service import DialogueService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/avatar/chat")
async def avatar_chat_ws(ws: WebSocket) -> None:
    await ws.accept()
    # 当前正在处理的一轮对话任务（用于打断控制）
    current_turn: asyncio.Task | None = None

    async def cancel_current(reason: str) -> None:
        """取消上一轮对话任务（若有），并等待其真正停止后再继续。"""
        nonlocal current_turn
        if current_turn is None or current_turn.done():
            current_turn = None
            return
        current_turn.cancel()  # 仅发出取消请求，不立即杀掉
        try:
            await current_turn  # 等旧任务真正停下来，避免新旧回复混发
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        finally:
            current_turn = None
        logger.info("[WS /ws/avatar/chat] 取消上一轮: %s", reason)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await _safe_send(ws, {"type": "error", "message": "invalid json"})
                continue

            msg_type = payload.get("type")
            if msg_type == "user_text":
                # 新消息到达，强制打断上一轮（若仍在播报）
                await cancel_current("new user_text arrived")
                await _safe_send(ws, {"type": "interrupt"})
                current_turn = asyncio.create_task(_run_turn(ws, payload))
            else:
                await _safe_send(ws, {"type": "error", "message": f"unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("[WS /ws/avatar/chat] 客户端断开连接")
    except Exception:  # noqa: BLE001
        logger.exception("[WS /ws/avatar/chat] 处理异常")
    finally:
        await cancel_current("ws closing")


async def _run_turn(ws: WebSocket, payload: dict[str, Any]) -> None:
    """处理一次用户输入：调对话引擎拿回复文本，再逐条推给前端。"""
    sender_id = payload.get("sender_id")
    if not sender_id:
        await _safe_send(ws, {"type": "error", "message": "missing sender_id"})
        return

    text = payload.get("text") or ""
    if not text.strip():
        await _safe_send(ws, {"type": "error", "message": "empty text"})
        return

    message_id = payload.get("message_id") or str(uuid.uuid4())
    user_message = UserMessage(
        sender_id=sender_id,
        message_id=message_id,
        type=MessageType.TEXT,
        text=text,
    )

    await _safe_send(ws, {"type": "user_ack", "message_id": message_id})

    # 复用现有对话引擎（自带 DB session 生命周期）
    try:
        engine = await get_engine()
        async with database.async_session() as session:
            repository = DialogueStateRepository(session=session)
            service = DialogueService(
                dialogue_state_repository=repository,
                dialogue_engine=engine,
            )
            result = await service.process_message(user_message)
        messages = result.messages
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("[WS /ws/avatar/chat] 对话处理失败")
        await _safe_send(ws, {"type": "error", "message": "dialogue failed"})
        return

    # 逐条推送 bot 文本（前端据此驱动数字人开口）
    for index, bot_msg in enumerate(messages):
        await _safe_send(ws, {
            "type": "bot_text",
            "message_id": message_id,
            "index": index,
            "text": bot_msg.text,
            "object": _focused_to_dict(bot_msg.object),
        })

    await _safe_send(ws, {"type": "turn_end", "message_id": message_id})


def _focused_to_dict(obj: FocusedObject | None) -> dict | None:
    if obj is None:
        return None
    return {
        "id": obj.id,
        "type": obj.type,
        "title": obj.title,
        "attributes": obj.attributes,
    }


async def _safe_send(ws: WebSocket, data: dict) -> None:
    try:
        await ws.send_text(json.dumps(data, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        logger.debug("[WS /ws/avatar/chat] 发送失败（客户端可能已关闭）", exc_info=True)
