"""meta 数据库路径统一解析 — [INCIDENT-2026-09-03] postmortem 改进 #11

所有需要引用 meta/architecture.db 的代码必须经由本模块获取路径，
禁止在业务代码内直接 os.path.join(__file__ 推导) 或使用 cwd 相对路径。

解析优先级:
1. 环境变量 SQLITE_DB_PATH (staging/prod 部署环境由启动脚本注入)
2. 仓库内 meta/architecture.db (本地开发默认)
"""
import os


def get_meta_db_path() -> str:
    """返回 meta/architecture.db 的绝对路径（env 优先，相对路径仅本地开发兜底）"""
    env = os.environ.get('SQLITE_DB_PATH')
    if env:
        return env
    # db_path.py 位于 <repo>/meta/core/ → 上溯两级即 <repo>/meta/
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )
