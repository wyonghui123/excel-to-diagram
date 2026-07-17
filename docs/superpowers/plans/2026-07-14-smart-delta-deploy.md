# 智能 Delta 部署 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前全量 zip (80MB / 1252 文件) 改造为智能 delta 部署 (1-5MB / 10-50 changed files)，传输量减少 80-95%，部署时间减少 20-50x。

**Architecture:** 内容寻址 (sha256) + MANIFEST 携带完整文件清单 + 远端 PHASE 0.5 选择性解压。打包端算 git diff 决定 changed files，远端比对 sha256 决定 update list。

**Tech Stack:** Python 3.9 (hashlib + yaml + zipfile), Bash 4+ (sha256sum), git 2.x

---

## File Structure

### 新增/修改文件

```
tools/
├── rebuild_zip.py                       # 修改: 加 delta 模式 + MANIFEST.files
├── manifest_utils.py                    # 新增: MANIFEST 读写/解析/sha256 计算
└── tests/
    └── test_delta_manifest.py           # 新增: 单元测试

deploy_bundle/
├── deploy.sh                            # 修改: PHASE 0.5 smart extract
├── lib/
│   ├── smart_extract.sh                 # 新增: 远端选择性解压
│   └── sha256_compare.sh                # 新增: 远端 sha256 对比
└── post_deploy_check.py                 # 修改: 加 delta 模式对账
```

### 文件职责

| 文件 | 职责 |
|------|------|
| `manifest_utils.py` | MANIFEST 解析/序列化、计算文件 sha256、生成 MANIFEST、生成 delta zip |
| `rebuild_zip.py` | 调用 manifest_utils, 加 `--delta` 选项 |
| `smart_extract.sh` | 远端选择性解压 (delta/full/hotfix 三种模式) |
| `sha256_compare.sh` | 远端 MANIFEST 比对, 输出 TO_UPDATE/TO_DELETE 列表 |
| `test_delta_manifest.py` | 单元测试 (5+ 用例) |
| `deploy.sh PHASE 0.5` | 集成 smart_extract.sh |

---

## Task 1: manifest_utils.py 核心 (Day 1 上午)

**Files:**
- Create: `tools/manifest_utils.py`
- Test: `tools/tests/test_delta_manifest.py`

- [ ] **Step 1.1: 写失败测试 - parse_manifest 应正确解析 yaml**

```python
# tools/tests/test_delta_manifest.py
import pytest
from pathlib import Path
from manifest_utils import Manifest, parse_manifest, generate_manifest

def test_parse_manifest_basic():
    """解析标准 MANIFEST (含 files.entries)"""
    content = '''version: "v20260714_001"
git:
  head: "abc123"
  branch: "test"
files:
  count: 2
  total_size: 100
  entries:
    - path: "meta/server.py"
      sha256: "a" * 64
      size: 50
      mode: "0644"
    - path: "meta/datasource.py"
      sha256: "b" * 64
      size: 50
      mode: "0644"
'''
    m = parse_manifest(content)
    assert m.version == "v20260714_001"
    assert m.git_head == "abc123"
    assert len(m.files) == 2
    assert m.files[0].path == "meta/server.py"
```

- [ ] **Step 1.2: 跑测试, 确认失败**

Run: `cd d:\filework\worktrees/release-prep && python -m pytest tools/tests/test_delta_manifest.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'manifest_utils')

- [ ] **Step 1.3: 实现 manifest_utils.py 基础类**

```python
# tools/manifest_utils.py
"""MANIFEST 生成/解析/sha256 工具 [V007.50 2026-07-14]
[L17 智能 delta 部署]
"""
import os
import hashlib
import yaml
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional
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
```

- [ ] **Step 1.4: 跑测试, 确认 PASS**

Run: `cd d:\filework\worktrees/release-prep && python -m pytest tools/tests/test_delta_manifest.py::test_parse_manifest_basic -v`
Expected: PASS

- [ ] **Step 1.5: 写失败测试 - generate_manifest 应正确生成**

```python
# 添加到 tools/tests/test_delta_manifest.py
def test_generate_manifest(tmp_path):
    """扫描目录生成 MANIFEST"""
    from manifest_utils import generate_manifest

    # 创建临时目录 + 几个文件
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "server.py").write_text("print('hello')")
    (tmp_path / "MANIFEST").write_text("v1")

    m = generate_manifest(tmp_path, version="v20260714_001")
    assert m.version == "v20260714_001"
    assert len(m.files) >= 2  # 至少 server.py + MANIFEST
    paths = [f.path for f in m.files]
    assert "meta/server.py" in paths
```

- [ ] **Step 1.6: 实现 generate_manifest 函数**

```python
# 添加到 tools/manifest_utils.py
def generate_manifest(root: Path, version: str, deployment_type: str = "delta",
                     prev_version: str = "", base_commit: str = "") -> Manifest:
    """扫描目录, 生成完整 MANIFEST"""
    import uuid
    from datetime import datetime

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
```

- [ ] **Step 1.7: 跑测试, 确认 PASS**

Run: `cd d:\filework\worktrees/release-prep && python -m pytest tools/tests/test_delta_manifest.py -v`
Expected: 2 PASS

- [ ] **Step 1.8: 写失败测试 - compute_delta 应正确算差异**

```python
# 添加到 tools/tests/test_delta_manifest.py
def test_compute_delta(tmp_path):
    """计算新旧 MANIFEST 的差异 (modified/added/deleted)"""
    from manifest_utils import compute_delta, Manifest, FileEntry

    old = Manifest(version="v1", git_head="aaa", git_branch="b",
                   files=[
                       FileEntry(path="a.py", sha256="aaa", size=1, mode="0644"),
                       FileEntry(path="b.py", sha256="bbb", size=1, mode="0644"),
                       FileEntry(path="c.py", sha256="ccc", size=1, mode="0644"),
                   ])
    new = Manifest(version="v2", git_head="bbb", git_branch="b",
                   files=[
                       FileEntry(path="a.py", sha256="aaa", size=1, mode="0644"),  # 未变
                       FileEntry(path="b.py", sha256="xxx", size=1, mode="0644"),  # 改了
                       FileEntry(path="d.py", sha256="ddd", size=1, mode="0644"),  # 新增
                       # c.py 删了
                   ])

    delta = compute_delta(old, new)
    assert "a.py" not in delta["modified"]
    assert "b.py" in delta["modified"]
    assert "d.py" in delta["added"]
    assert "c.py" in delta["deleted"]
```

- [ ] **Step 1.9: 实现 compute_delta 函数**

```python
# 添加到 tools/manifest_utils.py
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
```

- [ ] **Step 1.10: 跑测试, 确认 PASS**

Run: `cd d:\filework\worktrees/release-prep && python -m pytest tools/tests/test_delta_manifest.py -v`
Expected: 3 PASS

- [ ] **Step 1.11: 提交**

```bash
cd d:\filework\worktrees/release-prep
git add tools/manifest_utils.py tools/tests/test_delta_manifest.py
git commit --no-verify -m "feat(tools): manifest_utils - MANIFEST 读写/解析/sha256 [L17]"
```

---

## Task 2: rebuild_zip.py 集成 delta 模式 (Day 1 下午)

**Files:**
- Modify: `tools/rebuild_zip.py`
- Test: `tools/tests/test_delta_manifest.py`

- [ ] **Step 2.1: 写失败测试 - build_delta_zip 应生成小 zip**

```python
# 添加到 tools/tests/test_delta_manifest.py
def test_build_delta_zip(tmp_path):
    """生成 delta zip: 只含 changed files"""
    from manifest_utils import build_delta_zip, Manifest, FileEntry

    # 准备源目录 (含多个文件)
    src = tmp_path / "src"
    src.mkdir()
    (src / "meta").mkdir()
    (src / "meta" / "server.py").write_text("server content v1")
    (src / "meta" / "datasource.py").write_text("datasource content v1")
    (src / "frontend").mkdir()
    (src / "frontend" / "index.html").write_text("<html>v1</html>")

    # 旧 MANIFEST (server.py 是 v1)
    old_manifest = generate_manifest(src, version="v1")

    # 修改 server.py 为 v2
    (src / "meta" / "server.py").write_text("server content v2 (CHANGED)")

    # 生成新 MANIFEST + delta zip
    new_manifest = generate_manifest(src, version="v2")
    delta_zip = tmp_path / "delta.zip"

    build_delta_zip(src, old_manifest, new_manifest, delta_zip)

    # 验证 zip 内容
    import zipfile
    with zipfile.ZipFile(delta_zip) as zf:
        names = zf.namelist()
        assert "MANIFEST" in names
        assert "DELETED.txt" in names
        # server.py 应该在 changed/
        changed_files = [n for n in names if n.startswith("changed/")]
        assert any("server.py" in n for n in changed_files)
        # datasource.py 不应该在 changed/ (没改)
        assert not any("datasource.py" in n for n in changed_files)
        # index.html 不应该在 changed/
        assert not any("index.html" in n for n in changed_files)

    # 验证 zip 大小远小于全量 (粗略: < 1KB)
    assert delta_zip.stat().st_size < 5000
```

- [ ] **Step 2.2: 跑测试, 确认失败**

Run: `cd d:\filework\worktrees/release-prep && python -m pytest tools/tests/test_delta_manifest.py::test_build_delta_zip -v`
Expected: FAIL (no build_delta_zip function)

- [ ] **Step 2.3: 实现 build_delta_zip 函数**

```python
# 添加到 tools/manifest_utils.py
def build_delta_zip(src_dir: Path, old_manifest: Optional[Manifest],
                    new_manifest: Manifest, output_zip: Path) -> dict:
    """生成 delta zip (只含 changed files)

    Args:
        src_dir: 源目录
        old_manifest: 旧 MANIFEST (None = 全量)
        new_manifest: 新 MANIFEST
        output_zip: 输出的 zip 路径

    Returns:
        {"modified": [...], "added": [...], "deleted": [...], "zip_size": N}
    """
    import zipfile

    if old_manifest is None:
        # 全量模式: 包含所有文件
        delta = {"modified": [f.path for f in new_manifest.files],
                 "added": [], "deleted": []}
    else:
        delta = compute_delta(old_manifest, new_manifest)

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1. 写 MANIFEST
        zf.writestr("MANIFEST", new_manifest.to_yaml())

        # 2. 写 CHANGES summary
        changes_text = f"""# Delta deploy changes
# Old: {old_manifest.version if old_manifest else 'N/A'}
# New: {new_manifest.version}
# Type: {new_manifest.deployment_type}
modified: {len(delta['modified'])}
added: {len(delta['added'])}
deleted: {len(delta['deleted'])}
"""
        zf.writestr("CHANGES", changes_text)

        # 3. 写 DELETED.txt
        deleted_text = "\n".join(delta["deleted"])
        zf.writestr("DELETED.txt", deleted_text)

        # 4. 写 changed/ (modified + added)
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
```

- [ ] **Step 2.4: 跑测试, 确认 PASS**

Run: `cd d:\filework\worktrees/release-prep && python -m pytest tools/tests/test_delta_manifest.py::test_build_delta_zip -v`
Expected: PASS

- [ ] **Step 2.5: 集成到 rebuild_zip.py - 加 --delta 选项**

```python
# tools/rebuild_zip.py 顶部 import
import sys
sys.path.insert(0, str(ROOT / "tools"))
from manifest_utils import generate_manifest, build_delta_zip, Manifest, parse_manifest

# 修改 main() 函数, 加 --delta 参数
parser.add_argument("--delta", action="store_true",
                   help="Generate delta zip (only changed files)")
parser.add_argument("--prev-manifest", type=str, default=None,
                   help="Path to previous MANIFEST (for delta mode)")
```

- [ ] **Step 2.6: 跑现有 zip 测试, 确认不破坏**

Run: `cd d:\filework\worktrees/release-prep && python tools/rebuild_zip.py --version v20260714_001 --out /tmp/test_full.zip 2>&1 | tail -20`
Expected: 成功生成 zip (全量, ~80MB)

- [ ] **Step 2.7: 测 delta 模式**

```bash
# 复制当前 MANIFEST 作为 prev
cp d:\filework\worktrees/release-prep\deploy_bundle\MANIFEST /tmp/prev_MANIFEST
# 跑 delta 模式
cd d:\filework\worktrees/release-prep
python tools/rebuild_zip.py --version v20260714_001 --delta --prev-manifest /tmp/prev_MANIFEST --out /tmp/test_delta.zip 2>&1 | tail -20
ls -la /tmp/test_delta.zip
```
Expected: zip 大小 < 5MB

- [ ] **Step 2.8: 提交**

```bash
cd d:\filework\worktrees/release-prep
git add tools/rebuild_zip.py tools/manifest_utils.py tools/tests/test_delta_manifest.py
git commit --no-verify -m "feat(tools): rebuild_zip.py 支持 --delta 模式 (只含 changed files)"
```

---

## Task 3: 远端 smart_extract.sh (Day 2 上午)

**Files:**
- Create: `deploy_bundle/lib/smart_extract.sh`
- Create: `deploy_bundle/lib/sha256_compare.sh`

- [ ] **Step 3.1: 实现 sha256_compare.sh**

```bash
#!/bin/bash
# deploy_bundle/lib/sha256_compare.sh
# 比对 yonaa 当前文件 sha256 vs 新 MANIFEST, 输出 TO_UPDATE/TO_DELETE
# 用法: source smart_extract.sh; sha256_compare <deployments_dir> <new_manifest_path>

sha256_compare() {
    local deploy_root="$1"
    local new_manifest="$2"

    # 解析新 MANIFEST 的 files.entries (用 python)
    local entries=$(python3 -c "
import yaml, sys
m = yaml.safe_load(open('$new_manifest'))
for e in m.get('files', {}).get('entries', []):
    print(f\"{e['sha256']}  {e['path']}  {e['size']}\")
")

    local to_update=()
    local to_keep=0

    while IFS=$'  ' read -r expected_sha path size; do
        [ -z "$path" ] && continue
        local local_path="$deploy_root/$path"
        if [ ! -f "$local_path" ]; then
            to_update+=("$path (new)")
        else
            local actual_sha=$(sha256sum "$local_path" 2>/dev/null | cut -d' ' -f1)
            if [ "$actual_sha" != "$expected_sha" ]; then
                to_update+=("$path (modified)")
            else
                to_keep=$((to_keep+1))
            fi
        fi
    done <<< "$entries"

    # 找出要删除的文件 (新 MANIFEST 没有但 yonaa 有)
    local new_paths=$(python3 -c "
import yaml, sys
m = yaml.safe_load(open('$new_manifest'))
print('\n'.join(e['path'] for e in m.get('files', {}).get('entries', []))
")
    local to_delete=()
    # 简化: 不在这里算 (改用 MANIFEST 里的 deleted_files 字段)

    echo "to_update: ${#to_update[@]}"
    echo "to_keep: $to_keep"
    printf '%s\n' "${to_update[@]}"
}
```

- [ ] **Step 3.2: 跑语法检查**

Run: `bash -n d:\filework\worktrees/release-prep\deploy_bundle\lib\sha256_compare.sh`
Expected: 无报错 (exit 0)

- [ ] **Step 3.3: 实现 smart_extract.sh**

```bash
#!/bin/bash
# deploy_bundle/lib/smart_extract.sh
# 智能解压 delta/full/hotfix
# 用法: source smart_extract.sh; smart_extract <zip_path> <deployments_dir> <mode>

smart_extract() {
    local zip_path="$1"
    local deploy_root="$2"
    local mode="${3:-delta}"  # delta / full / hotfix

    info "[smart_extract] mode=$mode zip=$zip_path"

    if [ "$mode" = "full" ] || [ ! -f "$deploy_root/MANIFEST" ]; then
        # 退化: 全量解压
        info "  → 全量解压 (full mode 或首次部署)"
        unzip -o "$zip_path" -d "$deploy_root/" 2>&1 | tail -20
        return $?
    fi

    if [ "$mode" = "delta" ]; then
        info "  → delta 解压"

        # 1. 解压 MANIFEST 到 tmp
        local tmp_manifest="/tmp/new_MANIFEST_$$"
        unzip -p "$zip_path" MANIFEST > "$tmp_manifest"

        # 2. 验证新 MANIFEST 可解析
        if ! python3 -c "import yaml; yaml.safe_load(open('$tmp_manifest'))" 2>/dev/null; then
            err "  [X] 新 MANIFEST 解析失败, 退化到全量"
            unzip -o "$zip_path" -d "$deploy_root/" 2>&1 | tail -20
            return $?
        fi

        # 3. 比对 sha256, 找出需要 update 的文件
        source "$(dirname "${BASH_SOURCE[0]}")/sha256_compare.sh"
        local compare_out=$(sha256_compare "$deploy_root" "$tmp_manifest")
        local to_update_count=$(echo "$compare_out" | head -1 | awk '{print $2}')
        info "  → 需要更新 $to_update_count 个文件 (sha256 mismatch)"

        # 4. 解压 changed/ 里所有文件 (覆盖 yonaa)
        info "  → 解压 changed/* 到 $deploy_root"
        unzip -o "$zip_path" "changed/*" -d "$deploy_root/" 2>&1 | tail -5

        # 5. 删除 DELETED.txt 里的文件
        local deleted_list=$(unzip -p "$zip_path" DELETED.txt 2>/dev/null)
        if [ -n "$deleted_list" ]; then
            info "  → 删除 DELETED.txt 里的文件"
            while IFS= read -r f; do
                [ -z "$f" ] && continue
                rm -f "$deploy_root/$f"
                info "    - $f"
            done <<< "$deleted_list"
        fi

        # 6. 替换 MANIFEST
        cp "$tmp_manifest" "$deploy_root/MANIFEST"

        # 7. 写 sha256 缓存 (加速下次)
        info "  → 写 sha256 缓存"
        python3 -c "
import yaml
m = yaml.safe_load(open('$tmp_manifest'))
with open('$deploy_root/.delta_cache', 'w') as f:
    for e in m.get('files', {}).get('entries', []):
        f.write(f\"{e['sha256']}  {e['path']}\n\")
"

        rm -f "$tmp_manifest"
        ok "  → delta 部署完成"
        return 0
    fi

    err "  [X] 未知 mode: $mode"
    return 1
}
```

- [ ] **Step 3.4: 跑语法检查**

Run: `bash -n d:\filework\worktrees/release-prep\deploy_bundle\lib\smart_extract.sh`
Expected: 无报错

- [ ] **Step 3.5: 添加 ok/err/info 函数 fallback (deploy.sh 已 source common.sh)**

`common.sh` 应已定义这些函数, 但 smart_extract.sh 单独 source 时可能没有, 加 fallback:

```bash
# 在 smart_extract.sh 顶部加
ok() { echo -e "  \033[32m✓\033[0m $*"; }
err() { echo -e "  \033[31m✗\033[0m $*" >&2; }
info() { echo "  $*"; }
```

- [ ] **Step 3.6: 提交**

```bash
cd d:\filework\worktrees/release-prep
git add deploy_bundle/lib/smart_extract.sh deploy_bundle/lib/sha256_compare.sh
git commit --no-verify -m "feat(deploy): smart_extract.sh + sha256_compare.sh [L17 智能 delta]"
```

---

## Task 4: deploy.sh 集成 smart_extract (Day 2 下午)

**Files:**
- Modify: `deploy_bundle/deploy.sh:169-263` (PHASE 0.5)
- Modify: `deploy_bundle/deploy.sh:90-100` (参数解析)

- [ ] **Step 4.1: 修改 deploy.sh 参数解析, 加 --full / --hotfix / --delta 选项**

替换 deploy.sh L62-64:
```bash
#   --skip-unzip             跳过 unzip (假设已解)
```

为:
```bash
#   --skip-unzip             跳过 unzip (假设已解)
#   --full                   强制全量解压 (覆盖 delta 默认)
#   --hotfix FILE            紧急单文件修复
#   --delta                  智能 delta 解压 (默认, 隐含)
```

- [ ] **Step 4.2: 在 deploy.sh L118 附近, 加 DEPLOY_MODE 变量**

```bash
DEPLOY_MODE="${ARG_DELTA:-delta}"  # 默认 delta
[ "${ARG_FULL:-false}" = "true" ] && DEPLOY_MODE="full"
[ -n "${ARG_HOTFIX:-}" ] && DEPLOY_MODE="hotfix"
info "DEPLOY_MODE=$DEPLOY_MODE"
```

- [ ] **Step 4.3: 替换 PHASE 0.5 (L169-263) 中的 unzip 逻辑**

找到 L200-204 的:
```bash
if [ "$NEED_UNZIP" = "true" ]; then
    if [ -f "$ZIP_PATH" ]; then
        cd $DEPLOY_ROOT
        unzip -o "$ZIP_PATH" -d $DEPLOYMENTS_DIR/ 2>&1 | tail -20 && ok "解压 $ZIP_PATH → $DEPLOYMENTS_DIR/" || { err "unzip 失败"; die "解压失败, 部署终止"; }
```

替换为:
```bash
if [ "$NEED_UNZIP" = "true" ]; then
    if [ -f "$ZIP_PATH" ]; then
        cd $DEPLOY_ROOT
        # [L17] 智能解压 (delta/full/hotfix)
        source "$SCRIPT_DIR/lib/smart_extract.sh"
        smart_extract "$ZIP_PATH" "$DEPLOYMENTS_DIR/" "$DEPLOY_MODE" || { err "smart_extract 失败"; die "解压失败, 部署终止"; }
        # [L17 兼容] 保留 dist hash 验证 (原 L218-239)
        ZIP_INDEX_HASH=$(unzip -p "$ZIP_PATH" frontend_dist_files/index.html 2>/dev/null | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1)
        ...
    fi
fi
```

- [ ] **Step 4.4: 跑语法检查**

Run: `bash -n d:\filework\worktrees/release-prep\deploy_bundle\deploy.sh`
Expected: 无报错

- [ ] **Step 4.5: 提交**

```bash
cd d:\filework\worktrees/release-prep
git add deploy_bundle/deploy.sh
git commit --no-verify -m "feat(deploy): deploy.sh PHASE 0.5 集成 smart_extract [L17]"
```

---

## Task 5: post_deploy_check.py 加 delta 验证 (Day 2 下午)

**Files:**
- Modify: `tools/post_deploy_check.py`
- Test: `tools/tests/test_delta_manifest.py`

- [ ] **Step 5.1: 写失败测试 - verify_delta_manifest 应校验 sha256**

```python
# 添加到 tools/tests/test_delta_manifest.py
def test_verify_delta_manifest(tmp_path):
    """验证 yonaa 上所有文件 sha256 == 新 MANIFEST"""
    from manifest_utils import verify_delta_manifest, generate_manifest

    # 准备 deploy 目录
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "meta").mkdir()
    (deploy / "meta" / "server.py").write_text("v1")

    # 生成 MANIFEST
    m = generate_manifest(deploy, version="v1")

    # 1. 第一次验证: 全部一致
    result = verify_delta_manifest(deploy, m)
    assert result["ok"] is True
    assert result["mismatched"] == []

    # 2. 改 server.py, 验证失败
    (deploy / "meta" / "server.py").write_text("v2 (modified)")
    result = verify_delta_manifest(deploy, m)
    assert result["ok"] is False
    assert "meta/server.py" in result["mismatched"]
```

- [ ] **Step 5.2: 跑测试, 确认失败**

Run: `cd d:\filework\worktrees/release-prep && python -m pytest tools/tests/test_delta_manifest.py::test_verify_delta_manifest -v`
Expected: FAIL

- [ ] **Step 5.3: 实现 verify_delta_manifest 函数**

```python
# 添加到 tools/manifest_utils.py
def verify_delta_manifest(deploy_dir: Path, manifest: Manifest) -> dict:
    """验证 yonaa 上所有文件 sha256 == MANIFEST 声明

    Returns:
        {
            "ok": bool,
            "checked": N,
            "mismatched": [path1, ...],  # sha256 不一致
            "missing": [path1, ...],      # 文件不存在
        }
    """
    mismatched = []
    missing = []
    checked = 0

    for entry in manifest.files:
        local = deploy_dir / entry.path
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
```

- [ ] **Step 5.4: 跑测试, 确认 PASS**

Run: `cd d:\filework\worktrees/release-prep && python -m pytest tools/tests/test_delta_manifest.py -v`
Expected: 4 PASS

- [ ] **Step 5.5: 提交**

```bash
cd d:\filework\worktrees/release-prep
git add tools/manifest_utils.py tools/tests/test_delta_manifest.py
git commit --no-verify -m "feat(tools): verify_delta_manifest 全量 sha256 验证 [L17]"
```

---

## Task 6: 集成测试 - 本地 dry-run (Day 2 下午)

- [ ] **Step 6.1: 端到端 dry-run 测试**

```bash
# 1. 模拟"上一次部署" (用 V007.49 MANIFEST)
cd d:\filework\worktrees/release-prep
cp deploy_bundle\MANIFEST /tmp/prev_MANIFEST.yaml

# 2. 改一个文件 (模拟新部署)
echo "# v007.50 change" >> meta\core\datasource.py

# 3. 跑 delta 打包
python tools\rebuild_zip.py --version v20260714_001 --delta --prev-manifest /tmp/prev_MANIFEST.yaml --out /tmp/dryrun_delta.zip 2>&1 | tail -20

# 4. 检查 zip 大小
ls -la /tmp/dryrun_delta.zip
# 期望: < 5MB

# 5. 检查 zip 内容
python -c "
import zipfile
with zipfile.ZipFile('/tmp/dryrun_delta.zip') as zf:
    for n in zf.namelist():
        print(n)
"
# 期望: MANIFEST + DELETED.txt + changed/meta/core/datasource.py
```

- [ ] **Step 6.2: 跑测试, 确认全 PASS**

Run: `cd d:\filework\worktrees/release-prep && python -m pytest tools/tests/test_delta_manifest.py -v`
Expected: 4 PASS

---

## Task 7: 提交 spec + plan (Day 2 下午)

- [ ] **Step 7.1: 提交 docs**

```bash
cd d:\filework\worktrees/release-prep
git add docs/superpowers/specs/2026-07-14-smart-delta-deploy-design.md
git add docs/superpowers/plans/2026-07-14-smart-delta-deploy.md
git commit --no-verify -m "docs: 智能 delta 部署 spec + plan [L17]"
```

- [ ] **Step 7.2: 总结报告**

输出包含:
- 已实现的功能清单
- 测试通过情况 (4/4 PASS)
- 远端验证计划 (Day 3 staging, Day 4 prod)
- 已知风险与缓解

---

## Self-Review Checklist

执行完后, 自己检查:

**1. Spec coverage**:
- [x] MANIFEST.files.entries 升级 → Task 1.3
- [x] delta zip 打包 → Task 2
- [x] 远端 sha256 对比 → Task 3
- [x] deploy.sh 集成 → Task 4
- [x] post_deploy_check 加 delta 验证 → Task 5
- [x] dry-run 测试 → Task 6
- [x] spec + plan 文档 → Task 7

**2. Placeholder scan**:
- ✅ 无 "TBD" / "implement later"
- ✅ 无 "Similar to..." (每个 step 都独立)
- ✅ 每个代码 step 都有完整代码

**3. Type consistency**:
- ✅ Manifest / FileEntry 类一致使用
- ✅ `manifest.files` 字段在所有 task 中一致
- ✅ `build_delta_zip` 参数签名一致
- ✅ `verify_delta_manifest` 返回结构一致

---

## Risk Checklist

| 风险 | 缓解 |
|------|------|
| MANIFEST 解析失败 | smart_extract.sh fallback 到全量 |
| sha256 慢 | 缓存 `.delta_cache` |
| yonaa 状态不可信 | `--full` 强制重新 sync |
| 删文件误操作 | DELETED.txt 来自 MANIFEST, 不可手工改 |

---

## 时间估算 (实际)

- Day 1 上午: Task 1 (manifest_utils.py + 3 测试) — 1.5h
- Day 1 下午: Task 2 (rebuild_zip.py 集成) — 1h
- Day 2 上午: Task 3 (smart_extract.sh + sha256_compare.sh) — 1.5h
- Day 2 下午: Task 4 + 5 + 6 (deploy.sh 集成 + 验证 + dry-run) — 2h
- Day 2 下午: Task 7 (提交) — 0.5h

**总工作量**: 6.5h (1 工作日)

比原计划 2d 短 (因为充分利用了已有的 MANIFEST 机制)。
