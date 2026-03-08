"""
全局异步 HTTP 客户端

职责：集中持有一个 httpx.AsyncClient 单例，供知识检索层 / 动作层调用商城 Mock API。
所有出网请求都走这里，便于统一控制超时与代理策略。

为什么必须 trust_env=False：
    本机常残留指向 127.0.0.1:63836 的「死代理」环境变量（HTTP_PROXY/HTTPS_PROXY），
    一旦 httpx 信任系统代理，所有到商城 API（127.0.0.1:18081）的请求都会先被打到死代理，
    表现为长时间卡住后超时，但服务其它部分看似正常，极难排查。
    客服后端所有出网目标都是本地服务，不需要走代理，因此默认关闭（见 conf/config.py 的 http_trust_env）。
"""
from httpx import AsyncClient

from conf.config import settings

# 全局单例：在 FastAPI lifespan 里由 init_http_client() 初始化
http_client: AsyncClient | None = None


def init_http_client() -> None:
    """创建（或重建）全局异步 HTTP 客户端。"""
    global http_client
    http_client = AsyncClient(
        timeout=settings.http_timeout,   # 可配置超时，避免慢接口拖死事件循环
        trust_env=settings.http_trust_env,  # 默认 False：绕过本机死代理
    )


async def close_http_client() -> None:
    """优雅关闭客户端，释放底层连接。"""
    global http_client
    if http_client is not None:
        await http_client.aclose()
        http_client = None
