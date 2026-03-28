# itwwy 电商智能客服后端（customer-service-backend）

基于 **FastAPI + LangChain + SQLAlchemy(async) + MySQL 8.4 + 商城 Mock API** 的电商智能客服流程引擎。

一条用户消息进来，先由 LLM 做意图规划（三轨道：业务任务 / 知识咨询 / 闲聊），
命中业务任务后交给命令处理器 + 流程推进器，按 `flow_config/*.yml` 编排逐步执行：
期间完成槽位收集、商城 API 查询、LLM 话术改写，对话状态实时持久化到 MySQL。

## 一、整体架构

```
HTTP 层   api/routers/chat_router.py   POST /api/chat、GET /health、GET /api/chat/history
          api/routers/dependencies.py  依赖注入装配（get_engine 组装各组件）
   │
   ▼
服务层     service/dialogue_service.py   加载状态 → 引擎处理 → 保存状态
   │
   ▼
会话引擎   engine/dialogue_engine.py     消息分流、三轨道路由、防幻觉校验、对象消息处理
   │         ├── plan/turn_planner.py    LLM 意图规划，生成 TurnPlan
   │         ├── plan/turn_validator.py  防幻觉校验（轨道/命令/流程合法性）
   │         ├── clarify/responder.py    澄清话术（LLM 润色）
   │         ├── task/handler.py         任务轨道处理器
   │         │      ├── task/command/processor.py  命令处理器（start_flow/set_slots/cancel_flow/resume_flow + 系统过场）
   │         │      ├── task/flow/executor.py      流程推进器（start/action/collect/end）
   │         │      └── task/action/runner.py      action 执行器（查订单/查物流/推荐/回复/监听）
   │         └── knowledge/intents.py    知识意图定义（知识轨道，当前占位）
   │
   ▼
领域层     domain/state.py                DialogueState 聚合根（任务栈、会话、槽位）
          domain/contexts.py             任务上下文 / 系统过场上下文
          domain/messages.py             消息模型（UserMessage / BotMessage / FocusedObject）
持久化     repository/dialogue_state_repository.py  状态读写（INSERT ... ON DUPLICATE KEY UPDATE）
基础设施   infrastructure/llm.py          LLM 单例
          infrastructure/database.py     DB 连接池（aiomysql）
配置      conf/config.py                 .env 读取（pydantic-settings）
编排      flow_config/user_flows.yml     业务流程（6 个）
          flow_config/system_flows.yml   系统过场流程（6 个）
提示词     prompts/*.jinja2              turn_plan / clarify_respond 模板
```

## 二、环境依赖

| 依赖 | 说明 |
| ---- | ---- |
| MySQL 8.4（Docker，端口 **3306**） | 账号 `root / 123456`，库：`customer_service`（会话状态 `dialogue_states` 表）、`commerce`（8 表：users/orders/products/logistics_records/... 等） |
| 商城 Mock API（端口 **18081**） | 位于 `external/ecommerce-service-backend`，返回统一 `ApiResponse{code:0, message, data}` |
| LLM | `.env` 里配置（`LLM_BASE_URL` 指向兼容 OpenAI 协议的网关） |

> `.env` 关键配置项：`LLM_MODEL / LLM_BASE_URL / LLM_API_KEY / COMMERCE_API_BASE_URL / DATABASE_URL / APP_HOST / APP_PORT`。

## 三、启动步骤

### 1. 启动 MySQL（Docker）

```bash
docker start customer-service-mysql   # 已存在则直接 start
```

### 2. 启动商城 Mock API（端口 18081）

```bash
cd external/ecommerce-service-backend
.venv/Scripts/python.exe -m uvicorn app.app:app --host 127.0.0.1 --port 18081
# 注意：入口是 app.app:app；不要用 --reload（后台环境起不来）
```

### 3. 启动本服务（端口 18082）

```bash
cd D:/customer-service-backend
.venv/Scripts/python.exe main.py
```

- API 地址：http://127.0.0.1:18082
- 接口文档：http://127.0.0.1:18082/docs

## 四、接口说明

### GET /health

健康检查，返回 `{"status": "ok"}`。

### POST /api/chat

请求体（`text` 与 `object` 至少传一个）：

```json
{"sender_id": "u1001", "text": "我想查一下订单 A20260410001 的状态"}
```

或对象消息（前端点订单/商品卡片）：

```json
{"sender_id": "u1001", "object": {"type": "order", "id": "A20260410001", "title": "订单A20260410001", "attributes": {}}}
```

响应体：

```json
{"sender_id": "u1001", "message_id": "uuid", "messages": [{"text": "好的，我们先处理订单状态查询。", "object": null}]}
```

`sender_id` 由前端生成并保持不变（同一 id 共享同一份对话状态）。

### GET /api/chat/history?sender_id=xxx

查询某用户历史对话，按会话、轮次展开成 `user` / `bot` 消息流：

```json
{"sender_id": "u1001", "messages": [{"role": "user", "text": "我要退款", "object": null}, {"role": "bot", "text": "请告诉我你的订单号。", "object": null}]}
```

## 五、测试数据

| 用户 | 等级 |
| ---- | ---- |
| u1001 | PLUS（小李） |
| u1002 | 普通会员（王敏） |
| u1003 | PLUS（陈晨） |

| 订单号 | 状态 | 用途 |
| ------ | ---- | ---- |
| A20260410001 | 待发货 | 查订单状态 |
| A20260408002 | 运输中 | 查物流 |
| A20260405003 | 已完成 | 退款申请演示 |
| A20260407004 | 待揽收 | 发货提醒演示 |

| 商品编号 | 库存 | 用途 |
| -------- | ---- | ---- |
| SKU10001 | 有货 | iPhone 15 Pro 256G，¥8999 |
| SKU10002 | 有货 | 小米恒温电热水壶 3 |

### 完整对话示例

```
用户：我要退款
助手：好的，我们先处理退款申请。
助手：请告诉我你的订单号。
用户：A20260405003
助手：请简单说一下退款原因。
用户：不想要了
助手：好的，订单A20260405003的退款申请已提交，原因是：不想要了。后续会尽快为你处理。

用户：帮我查一下订单 A20260410001 的状态
助手：好的，我们先处理订单状态查询。
助手：订单A20260410001当前状态是：待发货。商家正在备货，预计 24 小时内发出。

用户：你好呀
助手：你好呀，我是电商小助手～ 目前支持查订单、查物流、申请退款，有什么可以帮你？
```

## 六、业务流程清单

`flow_config/user_flows.yml` 里的业务流程（LLM 可启动）：

| 流程 id | 名称 | 说明 |
| ------- | ---- | ---- |
| onboarding | 欢迎引导 | 开场欢迎 |
| order_status_query | 订单状态查询 | 收集 order_number → 查状态 → 回复 |
| logistics_tracking | 物流查询 | 收集 order_number → 查物流 → 回复 |
| refund_request | 退款申请 | 收集 order_number + refund_reason → 回复 |
| similar_product_recommendation | 相似商品推荐 | 收集 product_id → 推荐 |
| human_handoff | 人工客服 | 转人工话术 |

`flow_config/system_flows.yml` 里的系统过场流程（命令处理器内部触发，LLM 不可直接启动）：

| 流程 id | 说明 |
| ------- | ---- |
| system_task_started | 新任务开始过场 |
| system_task_resumed | 任务恢复过场 |
| system_task_interrupted | 任务打断过场 |
| system_task_canceled | 任务取消过场 |
| system_collect_information | 槽位收集发问 |
| system_cannot_handle | 无法处理兜底（rephrase 模式，当前未接线） |

## 七、意图规划三轨道

`plan/turn_planner.py` 的 LLM 对每句话输出一个 `TurnPlan`，命中三条轨道之一：

| 轨道 | 字段 | 说明 |
| ---- | ---- | ---- |
| task | `task.commands` | 业务任务轨道，命令列表（start_flow / set_slots / cancel_flow / resume_flow） |
| knowledge | `knowledge.intents` | 知识咨询轨道（商品/订单/退款政策等，当前返回占位话术） |
| chitchat | `chitchat` | 闲聊轨道（当前返回占位话术） |

`plan/turn_validator.py` 做防幻觉校验：无轨道 / 多轨道 / 命令非法 / 一次开多流程 / 流程不存在 / 知识意图缺聚焦对象 等情况，一律转 `clarify/responder.py` 澄清。

## 八、已实现的 action

| action 名 | 功能 |
| --------- | ---- |
| action_response | 统一回复，支持 static（模板直出）/ rephrase（LLM 改写）两种模式 |
| action_listen | 哨兵：结束本轮、等待用户输入 |
| action_lookup_order_status | 调商城 API 查订单状态，填 order_status / order_summary 槽位 |
| action_lookup_logistics | 调商城 API 查物流，填 logistics_company / tracking_number / logistics_status 槽位 |
| action_recommend_similar_products | 相似商品推荐（简化实现，后续可换算法） |

## 九、如何加一个新的客服能力

1. 在 `flow_config/user_flows.yml` 加一个流程（steps 用 start / collect / action / end 编排，`next` 支持字符串、条件分支 `if/then/else`）；
2. 需要新动作时，在 `task/action/runner.py` 的 `ActionRunner._handlers` 注册表加一行 `action 名 → 处理函数`；
3. 若动作要调商城新接口，接口路径拼在 `action_xxx` 函数里（注意 httpx `trust_env=False` 绕过本机代理）；
4. 重启服务即可，**引擎代码零改动**。

## 十、已知注意事项

- 装依赖用清华源：`UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple uv sync`
- 本机残留 `HTTP_PROXY/HTTPS_PROXY=127.0.0.1:63836`（死代理），httpx 调商城 API 必须 `trust_env=False`，否则超时
- 商城 mock 用 `--reload` 在后台环境起不来，用不带 reload 的 `uvicorn` 启动
- `uv.lock` / `pyproject.toml` 管理依赖，venv 在项目根 `.venv`
- 进程管理：后台起服务用 `run_in_background`；杀进程用 PowerShell `Stop-Process`（`taskkill //F` 在 Git Bash 参数解析会失败）
