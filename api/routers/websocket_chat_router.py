# itwwy/api/routers/websocket_chat_router.py

"""
智能客服 WebSocket 实时对话接口。

与 POST /api/chat 功能等价，但额外支持：
  - 流式逐条返回 Bot 消息（bot_message）
  - 服务端主动推送状态（thinking / done / error）
  - 客户端中途取消（cancel）
  - 连接保持，多轮对话无需重复建连

消息协议(JSON)：
  客户端 -> 服务端:
    {"type":"message","sender_id":"u1","message_id":"(可选)","text":"你好","object":{...}}
    {"type":"cancel","sender_id":"u1"}
  服务端 -> 客户端:
    {"type":"bot_message","sender_id":"u1","message_id":"...","data":{"text":"...","object":{...}}}
    {"type":"status","sender_id":"u1","data":{"status":"thinking|done|error|cancelled"}}
    {"type":"error","sender_id":"u1","data":{"code":"...","message":"..."}}

复用关系：业务逻辑完全复用现有 DialogueService + DialogueEngine，不重复造轮子。
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from api.routers.dependencies import get_dialogue_service
from api.schemas import ChatObject  # noqa: F401  (供将来对象消息扩展)
from domain.messages import FocusedObject, MessageType, UserMessage
from service.dialogue_service import DialogueService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    dialogue_service: DialogueService = Depends(get_dialogue_service),
) -> None:
    """
    WebSocket 聊天端点。

    Depends(get_dialogue_service) 在「连接建立时」解析一次，
    得到一个绑定该连接的对话服务实例（自带 DB 会话生命周期）。
    """
    await websocket.accept()
    logger.info("[WS /ws/chat] 客户端已连接")

    try:
        while True:
            # 1. 接收原始文本
            raw = await websocket.receive_text()

            # 2. 解析 JSON
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await _safe_send(websocket, {
                    "type": "error",
                    "data": {"code": "INVALID_JSON", "message": "消息格式错误，需要 JSON"},
                })
                continue

            msg_type = payload.get("type")

            # 3. 取消生成
            if msg_type == "cancel":
                await _safe_send(websocket, {
                    "type": "status", "data": {"status": "cancelled"},
                })
                continue

            # 4. 仅处理 message 类型
            if msg_type != "message":
                await _safe_send(websocket, {
                    "type": "error",
                    "data": {"code": "UNKNOWN_TYPE", "message": f"未知消息类型: {msg_type}"},
                })
                continue

            sender_id = payload.get("sender_id")
            text = payload.get("text")
            message_id = payload.get("message_id") or str(uuid.uuid4())
            obj_payload = payload.get("object")

            # 5. 构造领域消息对象（与 HTTP 接口完全一致）
            user_message = UserMessage(
                sender_id=sender_id,
                message_id=message_id,
                type=MessageType.TEXT if text else MessageType.OBJECT,
                text=text,
                object=FocusedObject(
                    id=obj_payload["id"],
                    type=obj_payload["type"],
                    title=obj_payload.get("title"),
                    attributes=obj_payload.get("attributes") or {},
                ) if obj_payload else None,
            )

            # 6. 通知「正在思考」
            await _safe_send(websocket, {
                "type": "status", "data": {"status": "thinking"},
            })

            # 7. 复用对话引擎处理
            try:
                process_result = await dialogue_service.process_message(user_message)

                # 8. 逐条推送 Bot 消息
                for bot_msg in process_result.messages:
                    await _safe_send(websocket, {
                        "type": "bot_message",
                        "sender_id": process_result.sender_id,
                        "message_id": process_result.message_id,
                        "data": {
                            "text": bot_msg.text,
                            "object": _focused_to_dict(bot_msg.object),
                        },
                    })

                # 9. 通知「完成」
                await _safe_send(websocket, {
                    "type": "status", "data": {"status": "done"},
                })

            except Exception as e:  # noqa: BLE001
                logger.exception("[WS /ws/chat] 处理消息失败")
                await _safe_send(websocket, {
                    "type": "error",
                    "data": {"code": "PROCESS_ERROR", "message": str(e)},
                })

    except WebSocketDisconnect:
        logger.info("[WS /ws/chat] 客户端断开连接")
    except Exception:  # noqa: BLE001
        logger.exception("[WS /ws/chat] 连接异常")
        try:
            await _safe_send(websocket, {
                "type": "error",
                "data": {"code": "INTERNAL_ERROR", "message": "服务器内部错误"},
            })
        except Exception:
            pass
        await websocket.close()


def _focused_to_dict(obj: FocusedObject | None) -> dict | None:
    """把 FocusedObject 转成可 JSON 序列化的字典（object 为 None 时返回 None）。"""
    if obj is None:
        return None
    return {
        "id": obj.id,
        "type": obj.type,
        "title": obj.title,
        "attributes": obj.attributes,
    }


async def _safe_send(websocket: WebSocket, data: dict[str, Any]) -> None:
    """安全发送：客户端已断开时静默忽略异常。"""
    try:
        await websocket.send_json(data)
    except Exception:  # noqa: BLE001
        logger.debug("[WS /ws/chat] 发送失败（客户端可能已关闭）", exc_info=True)
