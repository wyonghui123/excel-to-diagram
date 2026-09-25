"""meta 数据库路径统一解析 — [INCIDENT-2026-09-03] postmortem 改进 #11

所有需要引用数据库的代码必须经由本模块获取路径，
禁止在业务代码内直接 os.path.join(__file__ 推导) 或使用 cwd 相对路径。

平台库解析优先级:
1. 环境变量 SQLITE_DB_PATH (staging/prod 部署环境由启动脚本注入)
2. 环境变量 ARCH_DB_PATH (次级兼容项, 历史启动脚本使用)
3. 仓库内 meta/architecture.db (本地开发默认)

应用库（多产品平台，见 docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.5.1 F2）:
1. 环境变量 SQLITE_DB_DIR (部署时把整个应用库目录重定位到数据盘)
2. 仓库内 data/ (§6.1 目录结构)

> 应用库的**目录**由部署环境决定，**文件名**由 app.yaml 的 database.file 决定 ——
> 因此同一个应用包在本地与 staging 会落到不同目录，但文件名一致。
"""
import os

# db_path.py 位于 <repo>/meta/core/ → 上溯三级即 <repo>/
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_meta_db_path() -> str:
    """返回平台库（meta/architecture.db）的绝对路径（env 优先，相对路径仅本地开发兜底）

    `ARCH_DB_PATH` 为次级兼容项 —— 与 `intent_api` / `migration_runner` /
    `bo_framework` 等处既有的 `SQLITE_DB_PATH or ARCH_DB_PATH` 判断保持一致。
    """
    env = os.environ.get('SQLITE_DB_PATH') or os.environ.get('ARCH_DB_PATH')
    if env:
        return env
    # 上溯两级即 <repo>/meta/
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )


def get_app_data_dir() -> str:
    """返回应用库所在目录（不含文件名）。

    优先环境变量 SQLITE_DB_DIR，本地开发兜底 <repo>/data（§6.1）。

    **不创建目录** —— 建目录由数据源 / 迁移流程负责，本模块只做路径解析。
    """
    env = os.environ.get('SQLITE_DB_DIR')
    if env:
        return env
    return os.path.join(_REPO_ROOT, 'data')


def get_app_db_path(app_id: str, database_file: str = '') -> str:
    """返回某个应用的库文件绝对路径（§6.5.1 F2 多库路径入口）。

    文件名来源: `app.yaml` 的 `database.file` 的**文件名部分**
    （如 `'data/hello_world.db'` → `'hello_world.db'`）；未声明则用 `<app_id>.db`。
    目录来源: `get_app_data_dir()`。

    Args:
        app_id: 应用标识（须与目录名一致，见 `app_loader`）。
        database_file: `app.yaml` 中 `database.file` 的原始值，可含相对目录；
            其目录部分被忽略（目录一律由部署环境决定）。

    Raises:
        ValueError: `app_id` 为空或含路径分隔符 —— 该参数可能来自 URL 路由
            （`/api/v1/apps/<app_id>/...`），必须按不可信输入处理以阻断路径穿越。
    """
    _require_safe_app_id(app_id)
    filename = os.path.basename(database_file) if database_file else ''
    if not filename:
        filename = f'{app_id}.db'
    return os.path.join(get_app_data_dir(), filename)


def _require_safe_app_id(app_id: str) -> None:
    """校验 app_id 可作为文件名片段使用（阻断 `../` 穿越与空值）。

    显式检查反斜杠 —— 在 POSIX 上 `\\` 不是分隔符，若只依赖 basename
    判断会得到平台相关的行为。
    """
    if (not app_id or app_id in ('.', '..')
            or '\\' in app_id or os.path.basename(app_id) != app_id):
        raise ValueError(
            f'非法 app_id（为空或含路径分隔符）: {app_id!r}'
        )
