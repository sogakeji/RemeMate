"""Gunicorn 配置。

启动：gunicorn -c gunicorn.conf.py wsgi:app

关键：gevent worker 下，psycopg2 默认是阻塞的 C 扩展——一次 DB 查询会卡住
该 worker 的整个 gevent hub，连带卡住同 worker 上所有 SSE 长连接。
psycogreen 的 patch_psycopg() 注册 gevent 等待回调，让 DB 调用让出协程。

⚠ 禁用 --preload：preload 会在 master 进程 import app（早于 worker 的
monkey-patch），导致 SQLAlchemy/psycopg2 在未打补丁状态下被导入。
gevent worker 在 fork 后才 monkey.patch_all()，所以 app 必须在 worker 内导入。
"""
import multiprocessing

from app.safe_access_logging import RedactingAccessLogger

bind = "127.0.0.1:8891"
worker_class = "gevent"
workers = 2                      # 见 v0.1 §6：P1 即 -k gevent -w 2
preload_app = False              # 必须 False（见上）
timeout = 60                     # SSE 长连接交给协程，worker 超时放宽
graceful_timeout = 30
keepalive = 5
logger_class = RedactingAccessLogger
accesslog = "-"


def post_fork(server, worker):
    """每个 worker fork 后、处理请求前，给 psycopg2 打 gevent 补丁。"""
    from psycogreen.gevent import patch_psycopg

    patch_psycopg()
    worker.log.info("psycogreen: psycopg2 已 patch 为 gevent 非阻塞")
