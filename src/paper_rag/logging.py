"""CLI 命令使用的日志配置。"""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """为 CLI 进程一次性配置根日志。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)


def get_logger(name: str) -> logging.Logger:
    """返回模块级日志记录器。"""
    return logging.getLogger(name)
