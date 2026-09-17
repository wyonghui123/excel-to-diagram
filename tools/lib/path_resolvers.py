#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[2026-09-13] path_resolvers.py - 可插拔路径解析器

为什么需要这个:
  staging 部署中, `meta/` 是 symlink (meta -> current -> v20260905_staging_align_head),
  Python namespace package 解析时, `from meta.api.bo_api` 实际加载的是
  `current/api/bo_api.py` (顶层路径, 因为 namespace package 把 meta 当成命名空间
  而不是普通 package). 这是 staging 上 spec22 上传失败 5 次的根因.

抽象:
  PathResolver.resolve(deploy_root, local_path, resource_type, override) -> List[str]

内置 resolvers:
  - LocalResolver: 本地 copy, 不绕路
  - SymlinkNamespacePackageResolver: symlink + namespace package 场景, 默认双发
  - VolumeMountResolver: docker volume mount, 容器内路径
  - GitSubmoduleResolver: git submodule 场景
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------
# 抽象基类
# --------------------------------------------------------------------------
class PathResolver(ABC):
    """路径解析器抽象基类.

    实现 resolve() 返回该本地文件需要上传到的远端路径列表.
    """
    name: str = "base"

    @abstractmethod
    def resolve(
        self,
        deploy_root: str,
        local_path: Path,
        resource_type: Any = None,
        override: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        ...


# --------------------------------------------------------------------------
# 本地 (dev 环境)
# --------------------------------------------------------------------------
class LocalResolver(PathResolver):
    """本地 copy: 远端路径 == 本地路径 (绝对)."""
    name = "local"

    def resolve(self, deploy_root, local_path, resource_type=None, override=None):
        # deploy_root 在本地模式 = "" 或 None, 直接返回 local_path
        return [str(local_path)]


# --------------------------------------------------------------------------
# staging 关键: symlink + namespace package
# --------------------------------------------------------------------------
class SymlinkNamespacePackageResolver(PathResolver):
    """staging 用 symlink + namespace package, 需要双发.

    核心规则:
      - 如果本地路径含 'meta/' (且属于源码目录), 解析出双份:
        1. meta/X/Y      <- 业务 package 路径 (直观)
        2. X/Y           <- Python namespace 实际加载路径 (绕过 symlink)
      - 否则返回单份

    资源类型 overrides:
      python_module:
        双发 pattern: "{deploy_root}/meta/{relative} + {deploy_root}/{relative}"
      yaml_config:
        schemas: "{deploy_root}/meta/schemas/{name} + {deploy_root}/schemas/{name}"
        config:  "{deploy_root}/meta/config/{relative} + {deploy_root}/config/{relative}"
    """
    name = "symlink_namespace_package"

    # 双发触发前缀 (相对 REPO 根)
    DOUBLE_PATH_PREFIXES = (
        "meta/api/",
        "meta/core/",
        "meta/services/",
        "meta/blueprints/",
    )
    # YAML config 双发触发前缀
    YAML_DOUBLE_PATH_PREFIXES = (
        "meta/schemas/",
        "meta/config/",
    )

    def resolve(self, deploy_root, local_path, resource_type=None, override=None):
        override = override or {}
        rel = self._relative_to_repo(local_path)
        if rel is None:
            # 非 repo 内文件, 退化到单发
            return [f"{deploy_root.rstrip('/')}/{local_path.name}"]

        # rel 形如 "meta/api/bo_api.py", 我们要拼两份:
        #   1. {deploy_root}/meta/api/bo_api.py   (业务直观)
        #   2. {deploy_root}/api/bo_api.py        (Python namespace 实际加载)
        # 所以拿到 stripped = 去掉 meta/ 前缀
        if rel.startswith("meta/"):
            stripped = rel[len("meta/"):]
        else:
            stripped = rel

        rt_name = resource_type.value if hasattr(resource_type, "value") else str(resource_type)
        root = deploy_root.rstrip('/')
        double = [
            f"{root}/meta/{stripped}",
            f"{root}/{stripped}",
        ]

        # [FIX 2026-09-14] override 显式提供 double_path_prefixes 时必须尊重空列表 (单发),
        # 不能用 `or` 兜底类默认——空列表会触发 falsy 短路, 这是历史 bug。
        # [P1 2026-09-13 二次检查] 双发前缀: override["double_path_prefixes"] 优先,
        # 缺省回落类内默认 (此前 YAML resource_overrides 是死配置, 现已接通)
        if rt_name == "python_module":
            if "double_path_prefixes" in override:
                prefixes = tuple(override["double_path_prefixes"])
            else:
                prefixes = self.DOUBLE_PATH_PREFIXES
            if prefixes and any(rel.startswith(p) for p in prefixes):
                return double
        elif rt_name == "yaml_config":
            if "double_path_prefixes" in override:
                prefixes = tuple(override["double_path_prefixes"])
            else:
                prefixes = self.YAML_DOUBLE_PATH_PREFIXES
            if prefixes and any(rel.startswith(p) for p in prefixes):
                return double

        # 单发: 显式 target_path_template 优先 ({relative}=去 meta/ 前缀的相对路径)
        tpl = override.get("target_path_template")
        if tpl:
            return [tpl.format(deploy_root=root, relative=stripped, rel=rel)]

        # override 可强制双发
        if override.get("force_double"):
            return double
        return [f"{root}/{stripped}"]

    def _relative_to_repo(self, local_path: Path) -> Optional[str]:
        """转换为相对 repo 根的路径, 非 repo 内返回 None."""
        s = str(local_path).replace("\\", "/")
        # 尝试从常见 REPO 根推断
        for marker in ("/excel-to-diagram/", "/filework/excel-to-diagram/"):
            idx = s.rfind(marker)
            if idx != -1:
                return s[idx + len(marker):]
        # 退化: 用绝对路径文件名
        return None


# --------------------------------------------------------------------------
# Docker volume mount
# --------------------------------------------------------------------------
class VolumeMountResolver(PathResolver):
    """docker volume mount: deploy_root 是容器内路径, 单发."""
    name = "volume_mount"

    def resolve(self, deploy_root, local_path, resource_type=None, override=None):
        override = override or {}
        rel = self._relative_to_repo(local_path) or local_path.name
        return [f"{deploy_root.rstrip('/')}/{rel}"]

    def _relative_to_repo(self, local_path: Path) -> Optional[str]:
        s = str(local_path).replace("\\", "/")
        for marker in ("/excel-to-diagram/", "/filework/excel-to-diagram/"):
            idx = s.rfind(marker)
            if idx != -1:
                return s[idx + len(marker):]
        return None


# --------------------------------------------------------------------------
# Git submodule
# --------------------------------------------------------------------------
class GitSubmoduleResolver(PathResolver):
    """git submodule: 单发, 路径需要包含 submodule 目录."""
    name = "git_submodule"

    def resolve(self, deploy_root, local_path, resource_type=None, override=None):
        override = override or {}
        rel = self._relative_to_repo(local_path) or local_path.name
        return [f"{deploy_root.rstrip('/')}/{rel}"]

    def _relative_to_repo(self, local_path: Path) -> Optional[str]:
        s = str(local_path).replace("\\", "/")
        for marker in ("/excel-to-diagram/", "/filework/excel-to-diagram/"):
            idx = s.rfind(marker)
            if idx != -1:
                return s[idx + len(marker):]
        return None


# --------------------------------------------------------------------------
# prod: deploy_root 本身就是 meta 包根 (扁平布局, 单写)
# --------------------------------------------------------------------------
class FlatMetaPackageResolver(PathResolver):
    """prod 布局: deploy_root = meta 包目录本身 (例 /opt/app/deployments/meta).

    机制 (2026-09-14 实测):
      - server.py 在 {deploy_root}/server.py, L72 sys.path.insert 指向其父目录
      - `import meta` 命中 {deploy_root} (含 __init__.py)
      - 所以 repo 文件 meta/X/Y 单写到 {deploy_root}/X/Y (去 meta/ 前缀)
      - prod 无嵌套 meta/ 死镜像 (与 staging 双发场景不同)
    """
    name = "flat_meta_package"

    def resolve(self, deploy_root, local_path, resource_type=None, override=None):
        override = override or {}
        rel = self._relative_to_repo(local_path) or local_path.name
        stripped = rel[len("meta/"):] if rel.startswith("meta/") else rel
        tpl = override.get("target_path_template")
        if tpl:
            return [tpl.format(deploy_root=deploy_root.rstrip('/'), relative=stripped, rel=rel)]
        return [f"{deploy_root.rstrip('/')}/{stripped}"]

    def _relative_to_repo(self, local_path: Path) -> Optional[str]:
        s = str(local_path).replace("\\", "/")
        for marker in ("/excel-to-diagram/", "/filework/excel-to-diagram/"):
            idx = s.rfind(marker)
            if idx != -1:
                return s[idx + len(marker):]
        return None


# --------------------------------------------------------------------------
# 注册表
# --------------------------------------------------------------------------
_REGISTRY: Dict[str, PathResolver] = {
    cls.name: cls()
    for cls in (LocalResolver, SymlinkNamespacePackageResolver, VolumeMountResolver, GitSubmoduleResolver, FlatMetaPackageResolver)
}


def get_resolver(name: str) -> PathResolver:
    if name not in _REGISTRY:
        raise KeyError(f"unknown resolver: {name}; available: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]


def list_resolvers() -> List[str]:
    return list(_REGISTRY.keys())


# --------------------------------------------------------------------------
# CLI 调试
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--test", default=None,
                   help="本地路径, 演示解析结果")
    args = p.parse_args()
    if args.list:
        print("Available resolvers:")
        for n in list_resolvers():
            print(f"  {n}")
    if args.test:
        for rn in list_resolvers():
            r = get_resolver(rn)
            paths = r.resolve(
                deploy_root="/opt/app/staging/deploy/current",
                local_path=Path(args.test),
                resource_type=None,
            )
            print(f"\n[{rn}] {args.test} ->")
            for pp in paths:
                print(f"  {pp}")
