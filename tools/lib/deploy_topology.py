#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[2026-09-13] deploy_topology.py - 通用部署目标抽象

设计目标:
  - 把"部署目标"（staging/prod/dev/preview）抽象为统一对象
  - 把"资源类型"（python_module/yaml_config/static_asset/db_migration）抽象为枚举
  - 把"路径解析策略"（symlink_namespace_package/volume_mount/git_submodule/local）
    通过 PathResolver 抽象, 允许运行时切换

核心 API:
  DeployTarget.from_name('staging') -> DeployTarget
  deploy_target.resolve_remote_paths(local_path, resource_type=None) -> List[str]
  deploy_target.upload(local_path, resource_type=None) -> List[UploadResult]
  deploy_target.verify(local_path, remote_paths) -> VerifyResult

[2026-09-13] Lessons Learned:
  - staging 用 symlink + namespace package, Python import 会绕过 meta/X/Y
    直接解析到顶层 X/Y (v0905 旧版), 导致上传到 meta/X/Y 的 spec22 新版不被加载
  - 必须声明式配置 resolver + 资源类型映射, 避免硬编码
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 依赖同目录 path_resolvers
sys.path.insert(0, str(Path(__file__).parent))
from path_resolvers import PathResolver, get_resolver  # noqa: E402

# --------------------------------------------------------------------------
# 资源类型
# --------------------------------------------------------------------------
class ResourceType(str, Enum):
    PYTHON_MODULE = "python_module"
    YAML_CONFIG = "yaml_config"
    JSON_CONFIG = "json_config"
    STATIC_ASSET = "static_asset"
    DB_MIGRATION = "db_migration"
    SHELL_SCRIPT = "shell_script"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------
# repo 相对路径 + app 包 (2026-09-26 B)
# --------------------------------------------------------------------------
#: app 包内不上传的目录名 (运行数据 / 字节码缓存)
APP_EXCLUDE_DIRS = frozenset({"data", "__pycache__", ".pytest_cache", ".cache"})
#: app 包内不上传的后缀 (运行数据库 / 编译产物)
APP_EXCLUDE_SUFFIXES = frozenset({
    ".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".db-journal", ".db-wal", ".db-shm",
})


def repo_root() -> Path:
    """本仓库根目录 (tools/lib/deploy_topology.py -> 上溯 3 层)."""
    return Path(__file__).resolve().parents[2]


def rel_to_repo(local_path: Path | str) -> Optional[str]:
    """转成相对 repo 根的 posix 相对路径; 非 repo 内文件返回 None."""
    s = str(local_path).replace("\\", "/")
    root = str(repo_root()).replace("\\", "/").rstrip("/")
    if s.startswith(root + "/"):
        return s[len(root) + 1:]
    marker = "/excel-to-diagram/"
    idx = s.rfind(marker)
    if idx != -1:
        return s[idx + len(marker):]
    return None


def app_id_of(local_path: Path | str) -> Optional[str]:
    """`apps/<id>/...` -> `<id>`; 不在此结构下返回 None."""
    rel = rel_to_repo(local_path)
    if not rel:
        return None
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "apps":
        return parts[1]
    return None


def list_app_package_files(app_id: str, root: Optional[Path] = None) -> List[Path]:
    """展开一个 app 包内"应部署"的全部文件.

    排除项 (硬规则):
      - data/ 等运行期目录 —— 应用库 *.db 属运行数据, 覆盖即丢数据
      - __pycache__ / *.pyc / *.pyo —— 字节码缓存
      - *.db / *.sqlite* —— 任何位置的数据库文件, 双保险
    """
    base = (Path(root) if root else repo_root()) / "apps" / app_id
    if not base.is_dir():
        raise FileNotFoundError(f"app 包不存在: {base}")
    out: List[Path] = []
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(base).parts
        if any(part in APP_EXCLUDE_DIRS for part in rel_parts[:-1]):
            continue
        if p.suffix.lower() in APP_EXCLUDE_SUFFIXES:
            continue
        out.append(p)
    return out


# --------------------------------------------------------------------------
# 部署目标
# --------------------------------------------------------------------------
@dataclass
class UploadResult:
    local_path: str
    remote_path: str
    success: bool
    md5_match: Optional[bool] = None
    error: Optional[str] = None
    method: str = "remote_upload"  # remote_upload / local_copy / skip


@dataclass
class VerifyResult:
    local_path: str
    remote_path: str
    success: bool
    details: str = ""
    md5_local: Optional[str] = None
    md5_remote: Optional[str] = None


@dataclass
class DeployTarget:
    """通用部署目标抽象.

    Attributes:
        name: 人类可读名称 (staging / production / dev)
        host: 远端主机; None 表示本地
        gw_port: 网关端口; None 表示走直连
        deploy_root: 远端部署根 (例 /opt/app/staging/deploy/current)
        resolver_name: 路径解析器名 (symlink_namespace_package / volume_mount /
                       git_submodule / local)
        resource_overrides: 每个资源类型的额外路径模式, 留空走 resolver 默认
        exec_fn: 远端执行函数 (cmd: str, timeout: int) -> dict
        upload_fn: 远端上传函数 (local: Path, remote: str) -> dict
        md5_fn: 远端 md5 函数 (remote_path: str) -> Optional[str]
    """
    name: str
    host: Optional[str]
    gw_port: Optional[int]
    deploy_root: str
    resolver_name: str
    gw_https: bool = False
    resource_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # [2026-09-26 B] app 清单 SSOT: apps_root = app 包根 (与 meta/ 平级);
    # apps = 该 target 应部署的 app id 列表; 清单外的 app 文件 resolve 直接报错
    apps_root: Optional[str] = None
    apps: List[str] = field(default_factory=list)
    # [2026-09-26 B] 平台库绝对路径 (远端). 由它推导同目录的 runtime_apps.json;
    # 未配置则 app-status 跳过事实副本对比
    db_path: Optional[str] = None
    # [2026-09-26 B] 健康检查基址 (yaml health_check.base_url), 供 app-status 探 /health
    health_base_url: Optional[str] = None
    # 默认注入 staging_round 的远端函数 (本机 dev 可注入 None 用本地 fs)
    exec_fn: Optional[Any] = None
    upload_fn: Optional[Any] = None
    md5_fn: Optional[Any] = None

    # ------------------------------------------------------------------
    # 工厂
    # ------------------------------------------------------------------
    @classmethod
    def from_name(cls, name: str) -> "DeployTarget":
        """从配置加载指定 name 的部署目标."""
        config_path = Path(__file__).parent.parent / "config" / "deploy_topology.yaml"
        if not config_path.exists():
            raise FileNotFoundError(
                f"deploy_topology config not found: {config_path}\n"
                f"请先创建 {config_path} 或直接使用 DeployTarget(...) 构造"
            )
        import yaml  # type: ignore
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if name not in cfg:
            raise KeyError(f"deploy target '{name}' not in {config_path}; available: {list(cfg.keys())}")
        t = cfg[name]
        return cls._from_dict(name, t)

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "DeployTarget":
        return cls._from_dict(name, d)

    @classmethod
    def _from_dict(cls, name: str, d: dict) -> "DeployTarget":
        # 默认绑定 staging_round 的远端函数
        exec_fn = d.get("exec_fn")
        upload_fn = d.get("upload_fn")
        md5_fn = d.get("md5_fn")
        if not exec_fn or not upload_fn or not md5_fn:
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent))
                import staging_round as _sr
                # [2026-09-14] gw_https=true → prod 网关 (9200/HTTPS/专用 secret)
                if d.get("gw_https"):
                    _sr.use_prod_gateway()
                exec_fn = exec_fn or _sr.remote_exec
                upload_fn = upload_fn or _sr.remote_upload
                md5_fn = md5_fn or _sr.remote_md5
            except ImportError:
                pass
        return cls(
            name=name,
            host=d.get("host"),
            gw_port=d.get("gw_port"),
            deploy_root=d["deploy_root"],
            resolver_name=d["resolver"],
            gw_https=bool(d.get("gw_https", False)),
            resource_overrides=d.get("resource_overrides", {}),
            apps_root=d.get("apps_root"),
            apps=list(d.get("apps") or []),
            db_path=d.get("db_path"),
            health_base_url=(d.get("health_check") or {}).get("base_url"),
            exec_fn=exec_fn,
            upload_fn=upload_fn,
            md5_fn=md5_fn,
        )

    # ------------------------------------------------------------------
    # 路径解析
    # ------------------------------------------------------------------
    def _detect_resource_type(self, local_path: Path) -> ResourceType:
        """根据文件后缀 / 路径特征推断资源类型."""
        suffix = local_path.suffix.lower()
        s = str(local_path).replace("\\", "/")
        if suffix == ".py":
            # 排除 tools/ 测试脚本: 业务代码都是 meta/core/ meta/api/ 等
            if "/meta/core/" in s or "/meta/api/" in s or "/meta/services/" in s:
                return ResourceType.PYTHON_MODULE
            # 默认也归 PYTHON_MODULE (测试脚本一般不走 topology 上传)
            return ResourceType.PYTHON_MODULE
        if suffix in (".yaml", ".yml"):
            if "/schemas/" in s or "/config/" in s:
                return ResourceType.YAML_CONFIG
            return ResourceType.YAML_CONFIG
        if suffix == ".json":
            return ResourceType.JSON_CONFIG
        if suffix in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
            return ResourceType.STATIC_ASSET
        if "/migrations/" in s or suffix in (".sql",):
            return ResourceType.DB_MIGRATION
        if suffix == ".sh":
            return ResourceType.SHELL_SCRIPT
        return ResourceType.UNKNOWN

    def resolve_remote_paths(
        self,
        local_path: Path | str,
        resource_type: Optional[ResourceType] = None,
    ) -> List[str]:
        """解析出该本地文件需要上传的所有远端路径.

        不同 resolver 可能返回 1 个或多个路径:
          - local resolver: 1 个 (同路径)
          - symlink_namespace_package: 2 个 (meta/X/Y + 顶层 X/Y)
          - volume_mount: 1 个 (容器内路径)
          - git_submodule: 1 个 (主仓路径)
        """
        local_path = Path(local_path)
        if not local_path.is_absolute():
            raise ValueError(f"local_path must be absolute: {local_path}")

        # [2026-09-26 B] app 包路径: apps/<id>/X → {apps_root}/<id>/X
        # 不能套 deploy_root 规则 —— deploy_root 是 meta/ 包根 (prod 下 =
        # /opt/app/deployments/meta), app 包根是它的兄弟目录
        # (/opt/app/deployments/apps), 由 apps_root 单独声明.
        app_id = app_id_of(local_path)
        if app_id is not None:
            if not self.apps_root:
                raise ValueError(
                    f"target '{self.name}' 未配置 apps_root, 无法解析 app 文件: {local_path}"
                )
            if app_id not in self.apps:
                raise ValueError(
                    f"app '{app_id}' 不在 target '{self.name}' 的部署清单内 "
                    f"(当前清单: {self.apps or '[]'}). 如确需部署, 先在 "
                    f"tools/config/deploy_topology.yaml 的 {self.name}.apps 中登记 app id."
                )
            rel = rel_to_repo(local_path) or local_path.name
            sub = rel[len("apps/"):] if rel.startswith("apps/") else rel
            return [f"{self.apps_root.rstrip('/')}/{sub}"]

        # 推断资源类型
        rt = resource_type or self._detect_resource_type(local_path)

        # 拿 resolver
        resolver = get_resolver(self.resolver_name)
        override = self.resource_overrides.get(rt.value, {})
        paths = resolver.resolve(
            deploy_root=self.deploy_root,
            local_path=local_path,
            resource_type=rt,
            override=override,
        )
        # 去重保序
        seen, out = set(), []
        for p in paths:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    # ------------------------------------------------------------------
    # 上传
    # ------------------------------------------------------------------
    def upload(
        self,
        local_path: Path | str,
        resource_type: Optional[ResourceType] = None,
        skip_verify: bool = False,
    ) -> List[UploadResult]:
        """上传到所有解析出的远端路径, 并校验 md5."""
        local_path = Path(local_path)
        remote_paths = self.resolve_remote_paths(local_path, resource_type=resource_type)
        results: List[UploadResult] = []
        for rp in remote_paths:
            if self.host is None:
                # 本地模式: copy
                try:
                    rp_p = Path(rp)
                    rp_p.parent.mkdir(parents=True, exist_ok=True)
                    rp_p.write_bytes(local_path.read_bytes())
                    md5_match = None
                    if not skip_verify and self.md5_fn:
                        local_md5 = __import__("hashlib").md5(local_path.read_bytes()).hexdigest()
                        remote_md5 = self.md5_fn(rp)
                        md5_match = (local_md5 == remote_md5)
                    results.append(UploadResult(
                        local_path=str(local_path),
                        remote_path=rp,
                        success=True,
                        md5_match=md5_match,
                        method="local_copy",
                    ))
                except Exception as e:
                    results.append(UploadResult(
                        local_path=str(local_path),
                        remote_path=rp,
                        success=False,
                        error=str(e),
                        method="local_copy",
                    ))
            else:
                if not self.upload_fn:
                    results.append(UploadResult(
                        local_path=str(local_path),
                        remote_path=rp,
                        success=False,
                        error="no upload_fn bound",
                    ))
                    continue
                up = self.upload_fn(local_path, rp)
                if isinstance(up, dict) and up.get("error"):
                    results.append(UploadResult(
                        local_path=str(local_path),
                        remote_path=rp,
                        success=False,
                        error=str(up.get("reason") or up),
                    ))
                    continue
                md5_match = None
                if not skip_verify and self.md5_fn:
                    local_md5 = __import__("hashlib").md5(local_path.read_bytes()).hexdigest()
                    remote_md5 = self.md5_fn(rp)
                    md5_match = (local_md5 == remote_md5)
                results.append(UploadResult(
                    local_path=str(local_path),
                    remote_path=rp,
                    success=True,
                    md5_match=md5_match,
                    method="remote_upload",
                ))
        return results

    # ------------------------------------------------------------------
    # 验证 (上传后 / 独立)
    # ------------------------------------------------------------------
    def verify(
        self,
        local_path: Path | str,
        remote_paths: Optional[List[str]] = None,
    ) -> List[VerifyResult]:
        """验证远端文件与本地一致 (md5)."""
        local_path = Path(local_path)
        if remote_paths is None:
            remote_paths = self.resolve_remote_paths(local_path)
        import hashlib
        local_md5 = hashlib.md5(local_path.read_bytes()).hexdigest()
        results: List[VerifyResult] = []
        for rp in remote_paths:
            if self.md5_fn is None:
                results.append(VerifyResult(
                    local_path=str(local_path), remote_path=rp,
                    success=False, details="no md5_fn bound"))
                continue
            remote_md5 = self.md5_fn(rp)
            ok = (remote_md5 == local_md5)
            results.append(VerifyResult(
                local_path=str(local_path),
                remote_path=rp,
                success=ok,
                md5_local=local_md5,
                md5_remote=remote_md5,
                details="" if ok else f"md5 mismatch (local={local_md5}, remote={remote_md5})",
            ))
        return results


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _main():
    import argparse
    p = argparse.ArgumentParser(
        description="通用部署拓扑工具 (上传 / 解析路径 / 验证)"
    )
    p.add_argument("--target", "-t", default="staging",
                   help="部署目标 (staging/production/dev/...)")
    p.add_argument("--dry-run", action="store_true",
                   help="只解析路径, 不真正上传")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_resolve = sub.add_parser("resolve", help="解析远端路径")
    sp_resolve.add_argument("local_path")

    sp_upload = sub.add_parser("upload", help="上传本地文件到所有远端路径")
    sp_upload.add_argument("local_path")
    sp_upload.add_argument("--resource-type", "-r", default=None,
                           help="手动指定资源类型")
    sp_upload.add_argument("--skip-verify", action="store_true")

    sp_verify = sub.add_parser("verify", help="校验本地 vs 远端 md5")
    sp_verify.add_argument("local_path")
    sp_verify.add_argument("--remote", action="append", default=None,
                           help="指定要校验的远端路径 (可多次), 默认自动 resolve")

    args = p.parse_args()
    target = DeployTarget.from_name(args.target)
    local_path = Path(args.local_path)
    if args.cmd == "resolve":
        paths = target.resolve_remote_paths(local_path)
        print(f"[{target.name}] {local_path} -> {len(paths)} 路径:")
        for p in paths:
            print(f"  {p}")
    elif args.cmd == "upload":
        if args.dry_run:
            paths = target.resolve_remote_paths(local_path)
            print(f"[DRY-RUN] {local_path} -> {len(paths)} 路径:")
            for p in paths:
                print(f"  {p}")
            return
        results = target.upload(local_path,
                                resource_type=ResourceType(args.resource_type) if args.resource_type else None,
                                skip_verify=args.skip_verify)
        for r in results:
            status = "OK" if r.success else "FAIL"
            md5 = f" md5={'match' if r.md5_match else 'MISMATCH'}" if r.md5_match is not None else ""
            err = f" err={r.error}" if r.error else ""
            print(f"  [{status}]{md5}{err} {r.remote_path}")
        any_fail = any(not r.success or r.md5_match is False for r in results)
        sys.exit(1 if any_fail else 0)
    elif args.cmd == "verify":
        results = target.verify(local_path, remote_paths=args.remote)
        for r in results:
            status = "OK" if r.success else "FAIL"
            print(f"  [{status}] {r.remote_path} {r.details}")
        sys.exit(1 if any(not r.success for r in results) else 0)


if __name__ == "__main__":
    _main()
