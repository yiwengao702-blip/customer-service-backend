# itwwy/api/app.py

"""
定义fastapi实例

"""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from api.routers.chat_router import router
from api.routers.auth_router import router as auth_router
from api.routers.websocket_chat_router import router as ws_chat_router
from api.routers.avatar_router import router as avatar_http_router
from api.routers.avatar_ws_router import router as avatar_ws_router
from infrastructure.database import init_db_engine, close_db_engine, create_all_tables
from infrastructure.http_client import init_http_client, close_http_client
from infrastructure.avatar import init_avatar_client


# 装饰器 是 Python特有的语法 在不改变函数内部 代码的情况下 额外 增加新的功能
# 汽车 什么都不懂  拿去店里 额外 车顶 装个机关枪  封闭开放 （不主张 你去修改代码 但是 愿意让函数 有更多的功能）
@asynccontextmanager
async def lifespan(app: FastAPI):

    # 1. 应用启动
    print("启动服务器...")
    init_db_engine()  # ← 执行这里，创建数据库连接池
    await create_all_tables()  # 幂等建表（含 users 鉴权表）
    init_http_client()
    init_avatar_client()  # 数字人(灵眸) 配置校验（不强制建立连接）
    # 2. 进入 yield
    yield  # ← FastAPI 开始接收请求


    # 3. 应用关闭（Ctrl+C 或部署平台停止）
    await close_db_engine()  # ← 执行这里，关闭连接池
    await close_http_client()
    print("服务器已关闭")

# 创建应用
app = FastAPI(description="电商小二智能客服应用", lifespan=lifespan)



# 路由分发
app.include_router(router)
app.include_router(auth_router)          # 账号鉴权 /api/auth/*（注册/登录/当前用户）
app.include_router(ws_chat_router)       # WebSocket 实时对话 /ws/chat
app.include_router(avatar_http_router)   # 数字人凭证/会话/配置 HTTP 接口
app.include_router(avatar_ws_router)     # 灵眸 transcript 模式 /ws/avatar/chat




