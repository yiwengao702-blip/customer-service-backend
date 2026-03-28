# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an e-commerce intelligent customer service backend (智能客服后端) built with **FastAPI + LangChain + SQLAlchemy (async) + MySQL 8.4**. It implements a three-track dialogue engine that routes user messages through business tasks, knowledge consultation, or chitchat.

## Commands

### Running the Service

```bash
# Start MySQL (Docker - must be running first)
docker start customer-service-mysql

# Start the Mall Mock API (port 18081)
cd external/ecommerce-service-backend
.venv/Scripts/python.exe -m uvicorn app.app:app --host 127.0.0.1 --port 18081

# Start this service (port 18082)
cd D:/customer-service-backend
.venv/Scripts/python.exe main.py
```

### Installing Dependencies

```bash
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple uv sync
```

### Testing

No formal test runner is configured. The `test/` directory contains legacy/sandbox files and is not part of the main application.

## Architecture

```
HTTP Layer   → api/routers/chat_router.py (POST /api/chat, GET /api/chat/history, GET /health)
              → api/routers/dependencies.py (dependency injection)
              ↓
Service      → service/dialogue_service.py (load state → engine process → save state)
              ↓
Dialogue     → engine/dialogue_engine.py (message routing: text vs object, three-track routing)
Engine       ├── plan/turn_planner.py (LLM generates TurnPlan: task/knowledge/chitchat)
              ├── plan/turn_validator.py (hallucination validation)
              ├── clarify/responder.py (disambiguation responses)
              ├── task/handler.py (task track processor)
              │   ├── task/command/processor.py (start_flow/set_slots/cancel_flow/resume_flow)
              │   ├── task/flow/executor.py (flow progression: start/collect/action/end)
              │   └── task/action/runner.py (action execution)
              ├── knowledge/intents.py (knowledge track - placeholder)
              └── chitchat/ (chitchat track - placeholder)
              ↓
Domain       → domain/state.py (DialogueState aggregate root)
              → domain/contexts.py (TaskContext, SystemContext)
              → domain/messages.py (UserMessage, BotMessage, FocusedObject)
              ↓
Persistence  → repository/dialogue_state_repository.py (state persistence to MySQL)
              ↓
Infrastructure → infrastructure/llm.py (LLM singleton)
                 infrastructure/database.py (async DB connection pool)
                 conf/config.py (.env configuration via pydantic-settings)
```

## Three-Track Routing

The dialogue engine (`engine/dialogue_engine.py`) routes each user message through one of three tracks:

| Track | Trigger | Handler |
|-------|---------|---------|
| **task** | Business commands (start_flow, set_slots, cancel_flow, resume_flow) | TaskHandler |
| **knowledge** | Product/order/refund policy queries (placeholder) | KnowledgeHandler |
| **chitchat** | Casual conversation | ChitChatHandler |

The LLM (`plan/turn_planner.py`) generates a `TurnPlan` to determine which track to use. `plan/turn_validator.py` validates against hallucinations (invalid flows, multiple flows, missing slot objects).

## Business Flows

Defined in `flow_config/user_flows.yml`:

- **onboarding** - Welcome greeting on first visit
- **order_status_query** - Query order status (collects order_number → API call → response)
- **logistics_tracking** - Query logistics (collects order_number → API call → response)
- **refund_request** - Submit refund (collects order_number + refund_reason → response)
- **similar_product_recommendation** - Product recommendations
- **human_handoff** - Transfer to human agent

System flows in `flow_config/system_flows.yml` handle internal transitions (task started/resumed/interrupted/canceled, slot collection prompts, fallback).

## Adding New Capabilities

1. Add a new flow in `flow_config/user_flows.yml` with steps (start/collect/action/end)
2. Register new actions in `task/action/runner.py` via the `_handlers` registry
3. If calling new Mall APIs, add the call in the action function (use `httpx` with `trust_env=False` to bypass local proxy)

## Key Configuration (.env)

- `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` - LLM settings
- `DATABASE_URL` - MySQL connection string
- `COMMERCE_API_BASE_URL` - Mall Mock API base URL
- `APP_HOST`, `APP_PORT` - Service binding (default 18082)

## Known Issues

- httpx calls to the Mall API must use `trust_env=False` to bypass stale local proxy
- Mall mock must start WITHOUT `--reload` flag (fails in background environments)
- Dialogue sessions timeout after 1 hour of inactivity

## API Endpoints

- `GET /health` - Health check
- `POST /api/chat` - Send message (with `sender_id` + `text` or `object`)
- `GET /api/chat/history?sender_id=xxx` - Get chat history