"""MANIFEST 生成/解析/sha256 工具 [V007.50 2026-07-14]
[L17 智能 delta 部署]

Provides:
  - FileEntry / Manifest dataclasses (yaml-serializable)
  - parse_manifest(content) -> Manifest
  - generate_manifest(root, version) -> Manifest (scans dir, computes sha256)
  - compute_delta(old, new) -> {modified, added, deleted}
  - build_delta_zip(src, old, new, out) -> dict  (Task 2)
  - verify_delta_manifest(deploy_dir, manifest) -> dict  (Task 5)
"""
import os
import hashlib
import yaml
import uuid
import zipfile
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime
import subprocess


@dataclass
class FileEntry:
    path: str
    sha256: str
    size: int
    mode: str

    @classmethod
    def from_path(cls, p: Path, root: Path):
        rel = str(p.relative_to(root)).replace(os.sep, "/")
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return cls(
            path=rel,
            sha256=h.hexdigest(),
            size=p.stat().st_size,
            mode=oct(p.stat().st_mode & 0o777),
        )


@dataclass
class Manifest:
    version: str
    git_head: str
    git_branch: str
    base_commit: str = ""
    deployment_type: str = "delta"  # delta / full / hotfix
    prev_version: str = ""
    deploy_id: str = ""
    files: List[FileEntry] = field(default_factory=list)

    def to_yaml(self) -> str:
        return yaml.dump({
            "version": self.version,
            "deploy_id": self.deploy_id,
            "git": {"head": self.git_head, "branch": self.git_branch, "base_commit": self.base_commit},
            "deployment_type": self.deployment_type,
            "prev_version": self.prev_version,
            "files": {
                "count": len(self.files),
                "total_size": sum(f.size for f in self.files),
                "entries": [asdict(f) for f in self.files],
            },
        }, default_flow_style=False, sort_keys=False)

    def to_changes_summary(self) -> dict:
        return {
            "deployment_type": self.deployment_type,
            "version": self.version,
            "file_count": len(self.files),
            "total_size": sum(f.size for f in self.files),
        }


def parse_manifest(content: str) -> Manifest:
    """解析 MANIFEST yaml 字符串"""
    data = yaml.safe_load(content)
    files = [FileEntry(**e) for e in data.get("files", {}).get("entries", [])]
    return Manifest(
        version=data.get("version", ""),
        git_head=data.get("git", {}).get("head", ""),
        git_branch=data.get("git", {}).get("branch", ""),
        base_commit=data.get("git", {}).get("base_commit", ""),
        deployment_type=data.get("deployment_type", "delta"),
        prev_version=data.get("prev_version", ""),
        deploy_id=data.get("deploy_id", ""),
        files=files,
    )


def scan_directory_files(root: Path, exclude_dirs: tuple = (".git", "__pycache__", "node_modules")) -> List[Path]:
    """扫描目录所有文件 (排除指定目录)"""
    files = []
    for p in root.rglob("*"):
        if p.is_file() and not any(ex in p.parts for ex in exclude_dirs):
            files.append(p)
    return files


def get_git_head(root: Path) -> str:
    """获取当前 git HEAD SHA"""
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return "no-git"


def get_git_branch(root: Path) -> str:
    """获取当前 git 分支名"""
    try:
        return subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return "no-git"


def generate_manifest(root: Path, version: str, deployment_type: str = "delta",
                     prev_version: str = "", base_commit: str = "") -> Manifest:
    """扫描目录, 生成完整 MANIFEST"""
    files = []
    for p in scan_directory_files(root):
        try:
            files.append(FileEntry.from_path(p, root))
        except Exception as e:
            print(f"  [WARN] 跳过 {p}: {e}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    head = get_git_head(root)[:8] if (root / ".git").exists() else "no-git"
    deploy_id = f"{timestamp}_{head}_{uuid.uuid4().hex[:6]}"

    return Manifest(
        version=version,
        git_head=head,
        git_branch=get_git_branch(root),
        base_commit=base_commit,
        deployment_type=deployment_type,
        prev_version=prev_version,
        deploy_id=deploy_id,
        files=files,
    )


def compute_delta(old: Manifest, new: Manifest) -> dict:
    """计算两个 MANIFEST 的差异

    Returns:
        {
            "modified": [path1, path2, ...],  # 存在但 sha256 变了
            "added": [path1, ...],            # 新 MANIFEST 有, 旧没有
            "deleted": [path1, ...],          # 旧 MANIFEST 有, 新没有
        }
    """
    old_map = {f.path: f.sha256 for f in old.files}
    new_map = {f.path: f.sha256 for f in new.files}

    modified = []
    added = []
    for path, sha in new_map.items():
        if path not in old_map:
            added.append(path)
        elif old_map[path] != sha:
            modified.append(path)

    deleted = [p for p in old_map if p not in new_map]

    return {"modified": modified, "added": added, "deleted": deleted}
