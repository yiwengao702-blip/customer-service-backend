# itwwy/conf/config.py
"""
全局配置中心

职责：
- 通过 pydantic-settings 读取项目根目录的 .env（或真实环境变量），
  统一对外暴露为单例 `settings`，全项目用 `from conf.config import settings` 取用。
- 所有「环境相关、可能随部署变化」的参数都集中在这里，避免散落到业务代码里硬编码。

设计要点：
- 必填项（LLM / DB / 商城 API / 服务端口）保持无默认值，缺失时启动即报错，
  用失败早点暴露配置问题，而不是运行时莫名其妙 500。
- 可调项（echo / 连接池 / 超时 / 代理）给出安全默认值，既能跑通又便于按需微调。
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 固定放在项目根目录（conf 的上一级）
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """应用配置模型，pydantic-settings 会自动做类型转换与校验。"""

    # ---------- LLM ----------
    llm_api_key: str
    llm_model: str
    llm_base_url: str

    # ---------- 数据库 ----------
    database_url: str
    # SQL 回显：True 会把每条发往 MySQL 的 SQL 打到日志（调试用）。
    # 生产环境务必保持 False，否则日志会被 SQL 刷屏、且可能泄露业务数据。
    db_echo: bool = False
    # 异步连接池容量：保持连接的对象数（默认 5，常见 Web 服务够用）。
    db_pool_size: int = 5
    # 连接池溢出上限：pool_size 用满后最多再临时借出的连接数。
    db_max_overflow: int = 10
    # 连接回收周期（秒）：超过该时长的连接会被丢弃重建。
    # MySQL 默认 wait_timeout 约 8 小时，但中间网络设备/代理常更早掐掉空闲连接，
    # 设 3600 可避免拿到「已断开」的 stale connection 导致查询偶发失败。
    db_pool_recycle: int = 3600

    # ---------- 商城 Mock API ----------
    commerce_api_base_url: str

    # ---------- HTTP 客户端（调商城 API 用） ----------
    # 请求超时（秒）。商城 API 是本地 Mock，10s 足够；若以后接真实慢接口可调大。
    http_timeout: float = 10.0
    # 是否信任系统代理环境变量（HTTP_PROXY/HTTPS_PROXY）。
    # 本机常残留指向 127.0.0.1:63836 的「死代理」，一旦信任会导致所有出网请求卡死超时。
    # 客服后端所有出网请求都指向本地服务（商城 API / 灵眸网关），不需要走代理，
    # 因此默认 False（绕过系统代理）最稳妥；只有明确需要代理时才改 True。
    http_trust_env: bool = False

    # ---------- 服务器 ----------
    app_host: str
    app_port: int

    # ---------- 数字人（魔珐星云 XmovAvatar，纯前端 SDK，密钥仅存后端 .env） ----------
    digital_human_app_id: str = ""
    digital_human_app_secret: str = ""
    digital_human_gateway_server: str = "https://nebula-agent.xingyun3d.com/user/v1/ttsa/session"

    # ---------- 数字人（阿里云万相 / 灵眸 云渲染，后端 CreateChatSession） ----------
    avatar_access_key_id: str = ""
    avatar_access_key_secret: str = ""
    avatar_endpoint: str = ""
    avatar_project_id: str = ""
    avatar_instance_id: str = ""
    avatar_license: str = ""
    avatar_platform: str = ""

    # ---------- 前端默认使用的数字人厂商: moxia(魔珐星云) / lingmou(阿里灵眸) ----------
    digital_human_provider: str = "moxia"

    # ---------- 账号鉴权（自实现 JWT，不依赖第三方库） ----------
    # 令牌签名密钥：生产务必改用强随机值（如 openssl rand -hex 32）并通过环境变量注入，
    # 一旦泄露等于任何人可伪造令牌。此处仅为本地开发默认值。
    auth_secret: str = "dev-only-change-me-in-production"
    # 令牌有效期（分钟）：默认 7 天，便于本地调试；生产可缩短。
    jwt_expire_minutes: int = 60 * 24 * 7

    # 从 .env 文件读取配置；extra="ignore" 让 .env 里多余字段（如注释占位）不报错。
    # env_file_encoding 防止中文路径/注释乱码。
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        extra="ignore",
        env_file_encoding="utf-8",
    )


# 全局单例：全项目统一从这里取配置
settings = Settings()
