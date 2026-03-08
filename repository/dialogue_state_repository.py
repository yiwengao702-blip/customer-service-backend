# itwwy/repository/dialogue_state_repository.py

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from domain.state import DialogueState
from models.dialogue_state import DialogueStateRecord

logger = logging.getLogger(__name__)


class DialogueStateRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_state(self, sender_id: str) -> DialogueState:
        """
        读操作：按 sender_id 从 dialogue_states 表加载会话状态。

        容错设计：state_json 可能因早期版本结构变更、写入中断等原因损坏，
        此时不再让整个请求 500，而是回退到一个全新的空 DialogueState（等同新用户），
        保证客服主流程不中断。损坏内容仅记录日志，便于后续排查。
        :return: 反序列化后的 DialogueState
        """
        # 1. 组装查询：SELECT * FROM dialogue_states WHERE sender_id = :sender_id
        sql = select(DialogueStateRecord).where(DialogueStateRecord.sender_id == sender_id)
        # 2. 执行查询
        result = await self.session.execute(sql)
        # 3. 取唯一行（sender_id 是主键，最多一行）
        record = result.scalar_one_or_none()

        # 没有历史记录 → 视为全新用户，返回空状态
        if record is None:
            return DialogueState(sender_id=sender_id)

        # 有记录 → 反序列化为 DialogueState，并做好损坏兜底
        try:
            state_dict = json.loads(record.state_json)
            return DialogueState.model_validate(state_dict)
        except (json.JSONDecodeError, ValueError) as exc:
            # JSON 解析失败 或 结构与模型不匹配：丢弃损坏数据，回退空状态
            logger.warning(
                "sender_id=%s 的对话状态损坏，已回退为空状态。原因：%s",
                sender_id,
                exc,
            )
            return DialogueState(sender_id=sender_id)

    async def save_state(self, dialogue_state: DialogueState):
        """
        写操作(插入、修改)
        传统：插入之前先查询该条件（sender_id）对应的记录是否存在，如果不存在 则插入，反之修改
        进阶：负责将插入sql直接升级为修改sql(主键重复机制判断)
        :return:
        """

        # 1. 得到DialogueState的json字符串
        state_json: str = json.dumps(dialogue_state.model_dump(mode="json"))

        # 2. 定义插入的sql语句
        # insert into 表 value('张三',"        ")
        # 注意这里的依赖是：sqlalchemy.dialects.mysql.insert  而不是  sqlalchemy.insert
        insert_stmt = insert(DialogueStateRecord).values(
            sender_id=dialogue_state.sender_id, state_json=state_json
        )

        # 3. 升级update语句的sql
        update_stmt = insert_stmt.on_duplicate_key_update(
            state_json=insert_stmt.inserted.state_json
        )

        # 4. 执行sql
        await  self.session.execute(update_stmt)

        # 5. 提交
        await self.session.commit()
