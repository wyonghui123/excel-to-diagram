"""
[2026-09-26 B] app 维度部署: 清单 SSOT / 路径解析 / 排除规则 / 门禁.

背景: 目标 = ① 部署时把"指定 app"传到指定 server; ② 排查时一条命令看清
      "这台服务器有哪些 app".

本测试全部离线, 不触发任何远端部署 —— 只验证本地路径解析与门禁逻辑.

覆盖:
  1. apps/<id>/... 路径识别
  2. app 包文件集展开 (排除 data/ 与 __pycache__ / *.pyc / *.db)
  3. production target 读取 apps_root / apps / db_path / health_base_url
  4. app 远端落点 = {apps_root}/<id>/... (与 meta/ 平级, 不套 meta/ 前缀)
  5. 清单门禁: 未登记的 app 在 resolve 阶段即报错
  6. 回归: 平台文件 (meta/**) 远端落点不变
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
sys.path.insert(0, str(REPO / 'tools' / 'lib'))

from deploy_topology import (  # noqa: E402
    DeployTarget,
    app_id_of,
    list_app_package_files,
    rel_to_repo,
)
import staging_round as sr  # noqa: E402


# ----------------------------------------------------------------------
# 1. 路径识别
# ----------------------------------------------------------------------
def test_app_id_of_recognizes_app_paths():
    assert app_id_of(REPO / 'apps' / 'hello_world' / 'app.yaml') == 'hello_world'
    assert app_id_of(
        REPO / 'apps' / 'warehouse' / 'blueprints' / 'inventory_api.py'
    ) == 'warehouse'
    # 平台文件 / repo 外文件都不是 app
    assert app_id_of(REPO / 'meta' / 'core' / 'app_registry.py') is None
    assert app_id_of(REPO / 'tools' / 'staging_round.py') is None


# ----------------------------------------------------------------------
# 2. app 包文件集展开 (排除规则)
# ----------------------------------------------------------------------
def test_list_app_package_files_excludes_cache_and_bytecode():
    rels = [rel_to_repo(p) for p in list_app_package_files('hello_world')]
    assert 'apps/hello_world/app.yaml' in rels
    assert any(r.endswith('blueprints/greeting_api.py') for r in rels)
    assert any(r.endswith('schemas/greeting.yaml') for r in rels)
    # 仓库里有 __pycache__ / *.pyc, 必须被排除
    assert not any('__pycache__' in r for r in rels)
    assert not any(r.endswith(('.pyc', '.pyo')) for r in rels)


def test_list_app_package_files_excludes_data_dir(tmp_path):
    """data/ 是运行数据 (应用库), 任何内容都不得上传 —— 覆盖即丢数据."""
    app = tmp_path / 'apps' / 'demo'
    (app / 'blueprints').mkdir(parents=True)
    (app / 'data').mkdir()
    (app / 'app.yaml').write_text('id: demo\n', encoding='utf-8')
    (app / 'blueprints' / 'api.py').write_text('x = 1\n', encoding='utf-8')
    (app / 'data' / 'demo.db').write_text('', encoding='utf-8')
    (app / 'data' / 'notes.txt').write_text('', encoding='utf-8')

    files = list_app_package_files('demo', root=tmp_path)
    rels = sorted(p.relative_to(app).as_posix() for p in files)
    assert rels == ['app.yaml', 'blueprints/api.py']


def test_list_app_package_files_missing_app(tmp_path):
    with pytest.raises(FileNotFoundError):
        list_app_package_files('no_such_app', root=tmp_path)


# ----------------------------------------------------------------------
# 3. target 读取清单
# ----------------------------------------------------------------------
def test_production_target_reads_app_manifest():
    t = DeployTarget.from_name('production')
    assert t.deploy_root == '/opt/app/deployments/meta'
    assert t.apps_root == '/opt/app/deployments/apps'
    assert t.apps == []
    assert t.db_path == '/opt/app/deployments/meta/architecture.db'
    assert t.health_base_url == 'http://172.20.59.7:5001'


def test_staging_target_reads_app_manifest():
    t = DeployTarget.from_name('staging')
    # [2026-09-26] get_apps_root() = Path(__file__).resolve().parents[2]/"apps".
    # 关键在 .resolve(): __file__ 走 deploy/meta symlink 不解析, 但 resolve() 会把
    # deploy/meta/current 两条 symlink 全部展开到 snapshot 实体目录, 故值 =
    # current/apps (对 symlink 漂移免疫), 而非 deploy/apps.
    assert t.apps_root == '/opt/app/staging/deploy/current/apps'
    assert t.apps == []
    assert t.db_path == '/opt/app/staging/meta/architecture.db'


# ----------------------------------------------------------------------
# 4. app 落点与 meta/ 平级
# ----------------------------------------------------------------------
def test_production_app_path_resolves_next_to_meta():
    t = DeployTarget.from_name('production')
    t.apps = ['hello_world']  # 临时登记, 不改 yaml

    assert t.resolve_remote_paths(REPO / 'apps' / 'hello_world' / 'app.yaml') == [
        '/opt/app/deployments/apps/hello_world/app.yaml'
    ]
    assert t.resolve_remote_paths(
        REPO / 'apps' / 'hello_world' / 'blueprints' / 'greeting_api.py'
    ) == ['/opt/app/deployments/apps/hello_world/blueprints/greeting_api.py']


def test_app_path_without_apps_root_raises():
    t = DeployTarget.from_name('production')
    t.apps = ['hello_world']
    t.apps_root = None
    with pytest.raises(ValueError, match='未配置 apps_root'):
        t.resolve_remote_paths(REPO / 'apps' / 'hello_world' / 'app.yaml')


# ----------------------------------------------------------------------
# 5. 清单门禁
# ----------------------------------------------------------------------
def test_unlisted_app_is_rejected_at_resolve():
    t = DeployTarget.from_name('production')
    t.apps = []  # 显式置空 (与 yaml 当前值一致)
    with pytest.raises(ValueError, match='部署清单内'):
        t.resolve_remote_paths(REPO / 'apps' / 'hello_world' / 'app.yaml')


def test_expand_app_files_gate_and_expansion():
    t = DeployTarget.from_name('production')
    t.apps = []
    with pytest.raises(SystemExit):
        sr._expand_app_files(t, ['hello_world'], verbose=False)

    t.apps = ['hello_world']
    rels = sr._expand_app_files(t, ['hello_world'], verbose=False)
    assert 'apps/hello_world/app.yaml' in rels
    assert all(r.startswith('apps/hello_world/') for r in rels)
    assert not any('__pycache__' in r for r in rels)


# ----------------------------------------------------------------------
# 6. 回归: 平台文件落点不变 (B 改造不得影响现行 prod 部署)
# ----------------------------------------------------------------------
def test_platform_paths_unchanged_regression():
    t = DeployTarget.from_name('production')
    assert t.resolve_remote_paths(REPO / 'meta' / 'core' / 'app_registry.py') == [
        '/opt/app/deployments/meta/core/app_registry.py'
    ]
    assert t.resolve_remote_paths(REPO / 'meta' / 'api' / 'bo_api.py') == [
        '/opt/app/deployments/meta/api/bo_api.py'
    ]
    assert t.resolve_remote_paths(
        REPO / 'meta' / 'migrations' / 'v090__create_installed_apps.py'
    ) == ['/opt/app/deployments/meta/migrations/v090__create_installed_apps.py']


# ----------------------------------------------------------------------
# 7. staging 平台文件必须双发 (「staging 部署路径解析」家族第 5 次复发的护栏)
# ----------------------------------------------------------------------
def test_staging_platform_paths_are_double_sent():
    """[FIX 2026-09-26] staging 平台文件必须双发.

    不双发 = 「部署成功但代码永不生效」. 该家族已复发 5 次 (09-05 / 09-13 /
    09-16 早 / 09-16 晚 / 09-26), 每次都是路径落点与实际 import 路径不一致.

    2026-09-26 远端只读实测 (决定性证据, 非推测):
      - deploy/meta -> deploy/current/meta   (2026-09-16 21:08 symlink 修复后)
      - server.py:16  sys.path.insert(0, dirname(dirname(__file__)))
                      = /opt/app/staging/deploy
      - 以该 sys.path 实测:
          meta.core.audit_derived_fields -> {root}/meta/core/audit_derived_fields.py  ← 活树
          import core.<x>                -> ModuleNotFoundError: No module named 'core'
      ⇒ 2026-09-14 的「强制单发」(落点 {root}/core/**) 写的是死目录.

    例外: server.py 是**按文件路径**启动的
      (cmdline: /opt/app/staging/deploy/current/server.py), 必须落在 {root}/ 顶层 ——
      这正是不能一刀切只写 meta/ 前缀的原因, 也是本用例断言双发的原因.
    """
    t = DeployTarget.from_name('staging')
    root = t.deploy_root

    # 业务模块: meta/X/Y 一份 (可 import) + X/Y 一份 (兼容可执行语义)
    assert t.resolve_remote_paths(REPO / 'meta' / 'core' / 'app_registry.py') == [
        f'{root}/meta/core/app_registry.py',
        f'{root}/core/app_registry.py',
    ]
    # 可执行入口: 第二份 {root}/server.py 才是 `python server.py` 的启动路径
    assert t.resolve_remote_paths(REPO / 'meta' / 'server.py') == [
        f'{root}/meta/server.py',
        f'{root}/server.py',
    ]
    # 类默认前缀 (api/core/services/blueprints) 之外的目录也必须双发:
    # 这证明 yaml 的 double_path_prefixes=["meta/"] 覆盖了整个 meta/**
    assert t.resolve_remote_paths(REPO / 'meta' / 'graphql' / '__init__.py') == [
        f'{root}/meta/graphql/__init__.py',
        f'{root}/graphql/__init__.py',
    ]
    assert t.resolve_remote_paths(
        REPO / 'meta' / 'migrations' / 'v090__create_installed_apps.py'
    ) == [
        f'{root}/meta/migrations/v090__create_installed_apps.py',
        f'{root}/migrations/v090__create_installed_apps.py',
    ]
