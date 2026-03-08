"""
数据库引擎与连接池

职责：创建并持有 SQLAlchemy 异步引擎（async engine）与异步 session 工厂，
供 repository 层做 MySQL 读写。引擎在 FastAPI lifespan 启动时初始化一次，全程复用。

关键配置（见 conf/config.py）：
- pool_pre_ping：每次取连接前先发一个轻量 ping，自动丢弃「已断开」的过期连接，
  极大降低「MySQL server has gone away」类莫名断连报错。
- echo：是否把每条 SQL 打印到日志。生产必须关（默认 False），否则日志被刷屏且泄露数据。
- pool_size / max_overflow / pool_recycle：控制连接池规模与回收，防长连接被中间网络掐断。
"""
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from conf.config import settings

# 引擎与 session 工厂单例（首次 init_db_engine 时赋值）
engine: AsyncEngine | None = None
async_session: async_sessionmaker[AsyncSession] | None = None


def init_db_engine() -> None:
    """创建异步引擎与 session 工厂，务必在应用启动时调用一次。"""
    global engine, async_session

    engine = create_async_engine(
        settings.database_url,
        echo=settings.db_echo,                 # 生产关，调试可开
        pool_pre_ping=True,                   # 自动剔除过期连接
        pool_size=settings.db_pool_size,       # 常驻连接数
        max_overflow=settings.db_max_overflow, # 峰值溢出上限
        pool_recycle=settings.db_pool_recycle, # 连接回收周期（秒），防 stale connection
    )

    # session 工厂：每请求一个 session，所有配置收拢到一处，调用方只管「来个 session」
    async_session = async_sessionmaker(engine, expire_on_commit=False)


async def create_all_tables() -> None:
    """幂等建表：确保所有 ORM 模型（含 users 鉴权表）对应的表存在。

    SQLAlchemy 2.0 中 run_sync 只在 AsyncConnection 上、不在 AsyncEngine 上，
    因此先 engine.connect() 再 conn.run_sync 执行（aiomysql 异步驱动要求异步上下文）。
    仅当表不存在时创建，已存在的表不会被改动，对线上数据零风险。
    """
    from models.user import User  # noqa: F401  确保 users 表被纳入 metadata
    from models.base import Base
    async with engine.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db_engine() -> None:
    """应用关闭时释放连接池资源。"""
    global engine, async_session
    if engine is not None:
        await engine.dispose()
        engine = None
        async_session = None
