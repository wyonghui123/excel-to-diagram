#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_path_resolvers.py - SymlinkNamespacePackageResolver 单测

重点: python_module 默认单发、yaml_config 双发、空列表覆盖类默认。
"""
import sys
from pathlib import Path

REPO = Path(r'D:\filework\excel-to-diagram')
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))
sys.path.insert(0, str(REPO / 'tools' / 'lib'))

from path_resolvers import SymlinkNamespacePackageResolver
from deploy_topology import ResourceType

R = SymlinkNamespacePackageResolver()
ROOT = "/opt/app/staging/deploy/current"


def test_python_module_default_double():
    """类默认 DOUBLE_PATH_PREFIXES 仍生效 (未显式 override 时双发)"""
    paths = R.resolve(ROOT, REPO / "meta/api/enum_api.py", ResourceType.PYTHON_MODULE)
    assert len(paths) == 2, paths
    assert paths == [f"{ROOT}/meta/api/enum_api.py", f"{ROOT}/api/enum_api.py"]
    print("[OK] python_module 默认双发 (类默认兜底)")


def test_python_module_empty_override_single():
    """显式 empty double_path_prefixes + target_path_template -> 单发活树"""
    override = {"double_path_prefixes": [], "target_path_template": "{deploy_root}/{relative}"}
    paths = R.resolve(ROOT, REPO / "meta/api/enum_api.py", ResourceType.PYTHON_MODULE, override)
    assert paths == [f"{ROOT}/api/enum_api.py"], paths
    print("[OK] python_module empty+template -> 单发活树")


def test_python_module_explicit_double_override():
    """显式非空 double_path_prefixes -> 双发"""
    override = {"double_path_prefixes": ["meta/api/"]}
    paths = R.resolve(ROOT, REPO / "meta/api/enum_api.py", ResourceType.PYTHON_MODULE, override)
    assert paths == [f"{ROOT}/meta/api/enum_api.py", f"{ROOT}/api/enum_api.py"], paths
    print("[OK] python_module 显式双发")


def test_python_module_no_match_prefix_single():
    """不匹配 override 前缀 -> 单发 (target_path_template 优先)"""
    override = {"double_path_prefixes": ["meta/services/"], "target_path_template": "{deploy_root}/{relative}"}
    paths = R.resolve(ROOT, REPO / "meta/api/enum_api.py", ResourceType.PYTHON_MODULE, override)
    assert paths == [f"{ROOT}/api/enum_api.py"], paths
    print("[OK] python_module 前缀不匹配 -> 单发")


def test_yaml_config_default_double():
    """yaml_config 默认双发 (schemas/config)"""
    paths = R.resolve(ROOT, REPO / "meta/schemas/audit_log.yaml", ResourceType.YAML_CONFIG)
    assert len(paths) == 2, paths
    print("[OK] yaml_config 默认双发")


def test_yaml_config_empty_override_single():
    """yaml_config 显式 empty -> 单发"""
    override = {"double_path_prefixes": [], "target_path_template": "{deploy_root}/{relative}"}
    paths = R.resolve(ROOT, REPO / "meta/schemas/audit_log.yaml", ResourceType.YAML_CONFIG, override)
    assert paths == [f"{ROOT}/schemas/audit_log.yaml"], paths
    print("[OK] yaml_config empty override -> 单发")


if __name__ == '__main__':
    test_python_module_default_double()
    test_python_module_empty_override_single()
    test_python_module_explicit_double_override()
    test_python_module_no_match_prefix_single()
    test_yaml_config_default_double()
    test_yaml_config_empty_override_single()
    print("\nALL PASS")
