"""MANIFEST //sha256  [V007.50 2026-07-14]
[L17  delta ]

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
    """Parse MANIFEST YAML content into Manifest dataclass (V007.50 L17)"""
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
    """Scan directory, return all files (excluding specified dirs)"""
    files = []
    for p in root.rglob("*"):
        if p.is_file() and not any(ex in p.parts for ex in exclude_dirs):
            files.append(p)
    return files


def get_git_head(root: Path) -> str:
    """Get git HEAD SHA"""
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return "no-git"


def get_git_branch(root: Path) -> str:
    """Get git branch name"""
    try:
        return subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return "no-git"


def generate_manifest(root: Path, version: str, deployment_type: str = "delta",
                     prev_version: str = "", base_commit: str = "") -> Manifest:
    """scan_directory_files, generate full MANIFEST"""
    files = []
    for p in scan_directory_files(root):
        try:
            files.append(FileEntry.from_path(p, root))
        except Exception as e:
            print(f"  [WARN]  {p}: {e}")

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
    """Compute diff between two MANIFESTs (V007.50 L17)

    Returns:
        {
            "modified": [path1, path2, ...],  # sha256 changed
            "added": [path1, ...],            # in new but not old
            "deleted": [path1, ...],          # in old but not new
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


def build_delta_zip(src_dir: Path, old_manifest: Optional[Manifest],
                    new_manifest: Manifest, output_zip: Path) -> dict:
    """Build delta zip (only changed files)

    Args:
        src_dir: source dir
        old_manifest: old MANIFEST (None = full)
        new_manifest: new MANIFEST
        output_zip: output zip path

    Returns:
        {"modified": [...], "added": [...], "deleted": [...], "zip_size": N}
    """
    if old_manifest is None:
        # full mode: include all files
        delta = {
            "modified": [f.path for f in new_manifest.files],
            "added": [],
            "deleted": []
        }
    else:
        delta = compute_delta(old_manifest, new_manifest)

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1. ?MANIFEST
        zf.writestr("MANIFEST", new_manifest.to_yaml())

        # 2. ?CHANGES summary
        changes_text = f"""# Delta deploy changes
# Old: {old_manifest.version if old_manifest else 'N/A'}
# New: {new_manifest.version}
# Type: {new_manifest.deployment_type}
modified: {len(delta['modified'])}
added: {len(delta['added'])}
deleted: {len(delta['deleted'])}
"""
        zf.writestr("CHANGES", changes_text)

        # 3. ?DELETED.txt
        deleted_text = "\n".join(delta["deleted"])
        zf.writestr("DELETED.txt", deleted_text)

        # 4. ?changed/ (modified + added)
        changed_paths = set(delta["modified"] + delta["added"])
        for entry in new_manifest.files:
            if entry.path in changed_paths:
                src_file = src_dir / Path(entry.path)
                if src_file.exists():
                    zf.write(src_file, f"changed/{entry.path}")

    return {
        "modified": delta["modified"],
        "added": delta["added"],
        "deleted": delta["deleted"],
        "zip_size": output_zip.stat().st_size,
    }


def verify_delta_manifest(deploy_dir: Path, manifest: Manifest) -> dict:
    """Verify yonaa sha256 == MANIFEST

    Args:
        deploy_dir: yonaa deploy dir (e.g. /opt/app/deployments/)
        manifest: new MANIFEST

    Returns:
        {
            "ok": bool,
            "checked": N,
            "mismatched": [path1, ...],  # sha256 mismatch
            "missing": [path1, ...],     # file not found
        }
    """
    mismatched = []
    missing = []
    checked = 0

    for entry in manifest.files:
        local = deploy_dir / Path(entry.path)
        if not local.exists():
            missing.append(entry.path)
            continue
        actual = hashlib.sha256()
        with open(local, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                actual.update(chunk)
        if actual.hexdigest() != entry.sha256:
            mismatched.append(entry.path)
        checked += 1

    return {
        "ok": len(mismatched) == 0 and len(missing) == 0,
        "checked": checked,
        "mismatched": mismatched,
        "missing": missing,
    }
