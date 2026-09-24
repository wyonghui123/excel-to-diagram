# -*- coding: utf-8 -*-
"""[多产品平台] 应用包（.bip）打包 / 校验 / 解包（PoC 1 步骤 2）

职责:
- build_package():        apps/<app_id>/ → <app_id>-<version>.bip
- read_package_manifest(): 只读包元数据（不解包）
- extract_package():      校验 sha256 后安全解包

设计约束:
- 纯文件操作, 不碰 Flask / DB → 可独立单测
- 包内 manifest.json 是**构建产物**; app.yaml 仍是唯一事实源
  (安装后会重新 load_manifest 校验, 见 app_installer)

包结构:
    hello_world-1.0.0.bip (zip)
    ├── manifest.json      # 构建产物: 元数据 + 每个文件的 sha256
    ├── app.yaml
    ├── schemas/
    ├── blueprints/
    ├── components/
    └── migrations/

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md
  - §6.1  目录结构
  - §10   PoC 1 步骤 2
"""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from meta.core.app_loader import (
    AppManifest,
    AppManifestError,
    get_apps_root,
    load_manifest,
)

# 包格式版本: 结构不兼容变更时 +1, 由 install 侧拒绝未知版本
BIP_FORMAT_VERSION = 1
BIP_SUFFIX = ".bip"
PACKAGE_MANIFEST_NAME = "manifest.json"

# 打包排除项（运行时产物 / 缓存 / 版本控制目录）
_EXCLUDE_DIRS = {"__pycache__", ".git", ".pytest_cache", ".idea", ".vscode", "data"}
_EXCLUDE_SUFFIXES = {".pyc", ".pyo", BIP_SUFFIX}
_EXCLUDE_FILES = {".DS_Store"}


class AppPackageError(ValueError):
    """应用包构建 / 读取 / 解包失败。"""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_files(app_dir: Path) -> List[Path]:
    """收集待打包文件, 返回相对 app_dir 的路径（排序, 保证包内容稳定）。

    用 os.walk 而非 Path.glob —— Python 3.14 起 glob 不再支持绝对路径模式。
    """
    collected: List[Path] = []
    for root, dirnames, filenames in os.walk(app_dir):
        root_path = Path(root)
        dirnames[:] = sorted(
            d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if name in _EXCLUDE_FILES or name.startswith("."):
                continue
            if Path(name).suffix in _EXCLUDE_SUFFIXES:
                continue
            collected.append((root_path / name).relative_to(app_dir))
    return collected


def read_bo_ids(manifest: AppManifest) -> List[str]:
    """从应用 schema YAML 中提取 BO id。

    用途: 安装时记录到 installed_apps.bo_ids, 卸载时据此定位要清理的菜单
    —— 这样卸载**不依赖应用目录是否还存在**（purge 后仍能清菜单）。
    """
    bo_ids: List[str] = []
    for schema_path in manifest.schema_paths():
        try:
            raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise AppPackageError(f"schema 解析失败 {schema_path}: {e}") from e
        if isinstance(raw, dict) and isinstance(raw.get("id"), str) and raw["id"].strip():
            bo_ids.append(raw["id"].strip())
    return sorted(set(bo_ids))


def build_package(app_dir: Path, out_dir: Optional[Path] = None) -> Path:
    """把应用目录打成 .bip 包, 返回包文件路径。

    Args:
        app_dir: 应用目录（须含 app.yaml, 且目录名 == app.id）
        out_dir: 输出目录, 默认 <repo>/dist

    Raises:
        AppPackageError: app.yaml 校验失败 / 目录不存在
    """
    app_dir = Path(app_dir).resolve()
    if not app_dir.is_dir():
        raise AppPackageError(f"应用目录不存在: {app_dir}")

    # 复用 loader 的校验: app_id 规范 / 目录名一致 / 声明文件存在
    # 统一转成 AppPackageError, 让调用方只需处理一种异常
    try:
        manifest = load_manifest(app_dir)
    except AppManifestError as e:
        raise AppPackageError(f"应用描述符校验失败: {e}") from e

    out_dir = Path(out_dir) if out_dir else (get_apps_root().parent / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)
    bip_path = out_dir / f"{manifest.app_id}-{manifest.version}{BIP_SUFFIX}"

    rel_files = _collect_files(app_dir)
    entries = [
        {
            "path": rel.as_posix(),
            "size": (app_dir / rel).stat().st_size,
            "sha256": _sha256_file(app_dir / rel),
        }
        for rel in rel_files
    ]

    package_manifest: Dict[str, Any] = {
        "format_version": BIP_FORMAT_VERSION,
        "app_id": manifest.app_id,
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "vendor": manifest.vendor,
        "platform": {
            "min_version": manifest.platform_min_version,
            "max_version": manifest.platform_max_version,
        },
        "permission_namespace": manifest.permission_namespace,
        "product_binding": (
            {"mode": manifest.product_binding.mode,
             "product_code": manifest.product_binding.product_code}
            if manifest.product_binding else None
        ),
        "database_file": manifest.database_file,
        "bo_ids": read_bo_ids(manifest),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": entries,
    }

    with zipfile.ZipFile(bip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            PACKAGE_MANIFEST_NAME,
            json.dumps(package_manifest, ensure_ascii=False, indent=2),
        )
        for rel in rel_files:
            zf.write(app_dir / rel, rel.as_posix())

    return bip_path


def read_package_manifest(bip_path: Path) -> Dict[str, Any]:
    """只读包内 manifest.json（不解包）。

    Raises:
        AppPackageError: 文件不存在 / 非法 zip / 缺 manifest.json / 格式版本不支持
    """
    bip_path = Path(bip_path)
    if not bip_path.is_file():
        raise AppPackageError(f"应用包不存在: {bip_path}")

    try:
        with zipfile.ZipFile(bip_path) as zf:
            raw = zf.read(PACKAGE_MANIFEST_NAME).decode("utf-8")
    except KeyError as e:
        raise AppPackageError(f"应用包缺少 {PACKAGE_MANIFEST_NAME}: {bip_path}") from e
    except zipfile.BadZipFile as e:
        raise AppPackageError(f"应用包不是合法 zip: {bip_path}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AppPackageError(f"{PACKAGE_MANIFEST_NAME} 非法 JSON: {e}") from e

    if not isinstance(data, dict):
        raise AppPackageError(f"{PACKAGE_MANIFEST_NAME} 顶层需为对象")
    version = data.get("format_version")
    if version != BIP_FORMAT_VERSION:
        raise AppPackageError(
            f"不支持的包格式版本 {version}（本平台支持 {BIP_FORMAT_VERSION}）"
        )
    return data


def _safe_target(dest_dir: Path, rel_path: str) -> Path:
    """防路径穿越: 解包目标必须落在 dest_dir 内。"""
    target = (dest_dir / rel_path).resolve()
    if not str(target).startswith(str(dest_dir.resolve()) + os.sep):
        raise AppPackageError(f"包内路径越界: {rel_path}")
    return target


def extract_package(bip_path: Path, dest_dir: Path) -> Dict[str, Any]:
    """校验每个文件的 sha256 后解包到 dest_dir, 返回 manifest。

    先全量校验再落盘, 避免半解包状态。
    """
    package_manifest = read_package_manifest(bip_path)
    entries = package_manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise AppPackageError("manifest.json 的 files 为空, 包内容不完整")

    dest_dir = Path(dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(bip_path) as zf:
        names = set(zf.namelist())
        for entry in entries:
            rel_path = entry.get("path")
            if not rel_path:
                raise AppPackageError("manifest.json 存在无 path 的文件条目")
            if rel_path not in names:
                raise AppPackageError(f"包内缺少文件: {rel_path}")
            actual = hashlib.sha256(zf.read(rel_path)).hexdigest()
            if actual != entry.get("sha256"):
                raise AppPackageError(
                    f"文件校验失败: {rel_path}"
                    f"（期望 {str(entry.get('sha256'))[:12]}…, 实际 {actual[:12]}…）"
                )

        for entry in entries:
            rel_path = entry["path"]
            target = _safe_target(dest_dir, rel_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(rel_path))

    return package_manifest
