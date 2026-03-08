# itwwy/api/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from infrastructure.security import decode_token

from chitchat.responder import ChitChatResponder
from knowledge.intents import KNOWLEDGE_INTENTS
from knowledge.providers import ProductAPIProvider, OrderAPIProvider, FAQProvider, RAGProvider
from knowledge.registry import KnowledgeProviderRegistry
from knowledge.responder import KnowledgeResponder
from service.dialogue_service import DialogueService
from repository.dialogue_state_repository import DialogueStateRepository
from engine.dialogue_engine import DialogueEngine
from infrastructure import database
from plan.turn_planner import TurnPlanner
from task.action.builder import build_action_runner
from task.flow.loader import FlowLoader
from pathlib import Path
from task.handler import TaskHandler, ChitChatHandler, KnowledgeHandler
from task.command.processor import CommandProcessor
from clarify.responder import ClarifyResponder
from plan.turn_validator import TurnPlanValidator
from task.action.runner import ActionRunner
from task.flow.executor import FlowExecutor


# 拿数据库连接 操作层连接

async def get_session():
    async with database.async_session() as session:  # 异步方式获取session  获取session要网络传输（耗时的）
        yield session


async def get_dialogue_state_repository(session: AsyncSession = Depends(get_session)):
    return DialogueStateRepository(session=session)


async def get_engine():
    base = Path(__file__).resolve().parents[2]
    flow_list = FlowLoader().load_many([
        base / "flow_config" / "user_flows.yml",
        base / "flow_config" / "system_flows.yml",
    ])  # 读yml 文件

    # 调用了会话引擎
    return DialogueEngine(
        turn_planner=TurnPlanner(),  # 执行计划
        task_handler=TaskHandler(flows=flow_list, command_processor=CommandProcessor(),
                                 action_runner=build_action_runner(), flow_executor=FlowExecutor()),  # 任务处理
        clarify_responder=ClarifyResponder(),  # 澄清影响
        turn_plan_validator=TurnPlanValidator(),  # 校验器
        chitchat_handler=ChitChatHandler(ChitChatResponder()), # 闲聊
        knowledge_handler=KnowledgeHandler(
            knowledge_intents=KNOWLEDGE_INTENTS,
            knowledge_responder=KnowledgeResponder(),
            provider_registry=KnowledgeProviderRegistry(
                [
                    ProductAPIProvider(),# 商品咨询
                    OrderAPIProvider(),# 订单咨询
                    FAQProvider(),# 常见问题
                    RAGProvider(),#RAG
                ]
            ),
        ),
    )


async def get_dialogue_service(
        dialogue_state_repository: DialogueStateRepository = Depends(get_dialogue_state_repository),
        dialogue_engine: DialogueEngine = Depends(get_engine)
) -> DialogueService:
    return DialogueService(dialogue_state_repository=dialogue_state_repository, dialogue_engine=dialogue_engine)


# ───────────────────────────────────────────────────────────────
# 账号鉴权：解析 Bearer 令牌 → 校验签名/过期 → 取出当前登录用户
# ───────────────────────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        session: AsyncSession = Depends(get_session),
) -> User:
    """依赖注入：从 Authorization: Bearer <token> 取当前用户，失败抛 401。"""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供登录令牌，请先登录")
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期，请重新登录")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌缺少用户标识")
    user = await session.get(User, int(user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在或已被删除")
    return user
