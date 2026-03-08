"""
知识检索 Provider

职责：把「用户聚焦的订单 / 商品」转成可供 LLM 引用的知识片段（KnowledgeChunk）。
当前接的是商城 Mock API（本地 18081）。FAQ / RAG 两个 Provider 仍是占位（TODO）。

容错约定（与 task/action/custom/shared.py 一致）：
    任何一次外部 HTTP 调用失败（商城 API 没起、网络抖动、返回非 200、字段缺失），
    都不应让整条客服链路 500；而是返回一个「检索失败」的兜底知识片段，
    让上层 LLM 据实告诉用户「暂时查不到」，而不是整请求崩掉。
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel

from conf.config import settings
from domain.state import DialogueState
from infrastructure import http_client

logger = logging.getLogger(__name__)


class KnowledgeChunk(BaseModel):
    content: str


class KnowledgeProvider(ABC):
    # 知识提供者的唯一 ID（用于注册与路由）
    provider_id = ""

    @abstractmethod
    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """提供检索方法，返回若干知识片段。"""
        pass


def _base_url() -> str:
    """商城 API 基址（去掉末尾斜杠，避免拼接出双斜杠）。"""
    return settings.commerce_api_base_url.rstrip("/")


async def _get_json(path: str) -> dict | None:
    """
    统一发起一次商城 API GET 请求并取出 data 字段。

    :return: 成功且有 data 时返回 dict；任何失败返回 None（调用方据此兜底）。
    """
    client = http_client.http_client
    if client is None:
        logger.warning("HTTP 客户端尚未初始化，无法请求商城 API：%s", path)
        return None
    try:
        # trust_env=False 在客户端创建时统一设置，这里无需再关心代理
        resp = await client.get(f"{_base_url()}{path}")
        resp.raise_for_status()
        return resp.json().get("data")
    except (httpx.HTTPError, ValueError) as exc:
        # httpx.HTTPError 覆盖网络错误 / 超时 / 非 2xx；ValueError 覆盖 JSON 解析失败
        logger.warning("商城 API 请求失败 path=%s reason=%s", path, exc)
        return None


# 商品API
class ProductAPIProvider(KnowledgeProvider):
    provider_id = 'api.product'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        product_id = state.focused_object.id
        data: dict[str, Any] = await _get_json(f"/products/{product_id}")
        if data is None:
            return [KnowledgeChunk(content="商品信息：暂时无法获取，请稍后再试或联系人工客服。")]
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=f"商品信息:\n{text}")]


# 订单API
class OrderAPIProvider(KnowledgeProvider):
    provider_id = 'api.order'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        order_number = state.focused_object.id

        # 订单与物流并发查询，缩短整体耗时
        order_payload, logistics_payload = await asyncio.gather(
            _get_json(f"/orders/{order_number}"),
            _get_json(f"/orders/{order_number}/logistics"),
        )

        if order_payload is None and logistics_payload is None:
            return [KnowledgeChunk(content="订单与物流信息：暂时无法获取，请稍后再试或联系人工客服。")]

        return [
            KnowledgeChunk(
                content="订单与物流信息：\n"
                + json.dumps(
                    {
                        "order_number": order_number,
                        "order": order_payload,
                        "logistics": logistics_payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        ]


# 常见问题API（占位）
class FAQProvider(KnowledgeProvider):
    provider_id = 'faq.default'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        # TODO: 接入真实 FAQ 检索
        return [KnowledgeChunk(content="FAQ：未检索到相关问题")]


# RAG API（占位）
class RAGProvider(KnowledgeProvider):
    provider_id = 'rag.default'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        # TODO: 接入真实 RAG 检索接口
        return [KnowledgeChunk(content="RAG：未检索到相关信息")]
