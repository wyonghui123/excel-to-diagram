#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
release_prep.py - 变更推送到 release-prep 的半自治流程

3 层架构:

  Layer 1 (Agent 自治):
    python scripts/release_prep.py promote <wt-name> --note "<变更说明>"
      → 把 wt 当前 HEAD 标记 SELF_VERIFIED, 写到 .coord/release_pipeline.json
      → 不修改任何 git 状态, 不推送

  Layer 2 (协调/PM 触发):
    python scripts/release_prep.py integrate <wt-name>
      → 自动:
          1. cherry-pick wt 分支 → release-prep 分支
          2. _wt_service.py start-be release-prep + start-fe release-prep
          3. health check /health
          4. v33_state transition SELF_VERIFIED→CHERRY_PICKED
          5. 记录到 release_pipeline.json

  Layer 3 (PM 验证):
    python scripts/release_prep.py pm-status
      → 一次性输出: 所有 requests + integrations + 验证进度
    python scripts/release_prep.py pm-verify <wt-name>
      → v33_state transition CHERRY_PICKED→PM_VERIFIED
      → 后续: deploy_v33_hook 自动推到 main

设计原则:
  - Agent 只能 declare ready, 不能 push (防 phase13 reset 事故)
  - 协调 agent 做实际合并 (有 audit log)
  - PM 验证是人工 gate, 必须明确敲 PM_VERIFIED
  - 任何 step 失败 → 状态 INTEGRATION_FAILED + 详细错误 → PM 决策
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:\filework\excel-to-diagram")
COORD_DIR = Path(r"D:\filework\.coord")
PIPELINE_FILE = COORD_DIR / "release_pipeline.json"
LOG_DIR = COORD_DIR / "release_log"

# v33_state 状态映射 (复用现有状态机)
SELF_VERIFIED = "SELF_VERIFIED"
CHERRY_PICKED = "CHERRY_PICKED"
PM_VERIFIED = "PM_VERIFIED"
INTEGRATION_FAILED = "INTEGRATION_FAILED"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_pipeline() -> dict:
    """读取 release_pipeline.json (单源真相)"""
    if not PIPELINE_FILE.exists():
        return {
            "requests": {},      # wt_name → request data
            "integrations": {},  # wt_name → integration data
            "last_update": None,
        }
    try:
        return json.loads(PIPELINE_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"requests": {}, "integrations": {}, "last_update": None}


def _save_pipeline(data: dict):
    """原子写入 pipeline"""
    COORD_DIR.mkdir(parents=True, exist_ok=True)
    data["last_update"] = _now()
    tmp = PIPELINE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PIPELINE_FILE)


def _log_event(wt_name: str, action: str, status: str, details: dict = None):
    """写 release log (.coord/release_log/<timestamp>_<wt>_<action>.json)

    [V2026-07-22] 鲁棒性增强: log 写入失败不阻塞主流程, 主数据已写到 pipeline
    """
    log_entry = {
        "ts": _now(),
        "wt": wt_name,
        "action": action,
        "status": status,
        "details": details or {},
    }
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"{log_entry['ts'].replace(':', '').replace('-', '')}_{wt_name}_{action}.json"
        (LOG_DIR / fname).write_text(
            json.dumps(log_entry, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        # 主数据已写在 pipeline, log 失败不致命
        # 但保留警告以便诊断
        print(f"  [WARN] _log_event 失败 (主流程已成功): {e}", file=sys.stderr)


def _git(path: Path, *args: str, timeout: int = 30) -> tuple:
    """git command wrapper"""
    try:
        r = subprocess.run(
            ["git", "-C", str(path)] + list(args),
            capture_output=True, timeout=timeout
        )
        return r.returncode, r.stdout.decode("utf-8", "replace").strip(), r.stderr.decode("utf-8", "replace").strip()
    except Exception as e:
        return -1, "", str(e)


def _get_wt_path(wt_name: str) -> Path | None:
    """解析 wt 名为绝对路径"""
    candidates = [
        REPO / "worktrees" / wt_name,
        Path(r"D:\filework") / "worktrees" / wt_name,
        Path(r"D:\filework") / wt_name,
    ]
    for c in candidates:
        if (c / ".git").exists() or (c / ".git").is_file():
            return c
    return None


def cmd_promote(wt_name: str, note: str):
    """Layer 1: Agent 标记自己完成

    例:
      python scripts/release_prep.py promote agent-api-version-migration --note "v1/v2 治理完成"

    [V2026-07-22 R-X7] 支持同一 wt 多分支并存 (heads{} 结构):
      - 同一 wt 在不同分支的 promote 不再相互覆盖
      - 旧结构兼容: 保留 wt-level 字段 (head/branch/subject/note) 用于向后兼容
      - pm-status 同时显示 heads{} 中的所有分支
    """
    wt = _get_wt_path(wt_name)
    if not wt:
        print(f"  [ERROR] wt '{wt_name}' not found")
        return 1

    rc, head, _ = _git(wt, "rev-parse", "HEAD")
    if rc != 0:
        print(f"  [ERROR] cannot get HEAD for {wt}")
        return 1

    rc2, subject, _ = _git(wt, "log", "-1", "--format=%s")
    rc3, branch, _ = _git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch if rc3 == 0 else "?"
    subject = subject if rc2 == 0 else "?"

    pipeline = _load_pipeline()
    existing = pipeline["requests"].get(wt_name, {})

    # 构建 heads{} 多主题结构
    heads = existing.get("heads", {})
    new_entry = {
        "head": head,
        "branch": branch,
        "subject": subject,
        "topic": _infer_topic(note),  # 从 note 推断主题
        "note": note,
        "promoted_at": _now(),
        "status": SELF_VERIFIED,
    }
    heads[branch] = new_entry  # 同分支 promote 会覆盖该分支条目, 新分支新增

    # 顶层字段保留最近 promote 的快照 (向后兼容旧读取逻辑)
    pipeline["requests"][wt_name] = {
        "wt": wt_name,
        "wt_path": str(wt),
        "heads": heads,
        # 兼容字段 (顶层, 用最近 promote 的数据)
        "head": head,
        "branch": branch,
        "subject": subject,
        "note": note,
        "promoted_at": _now(),
        "status": SELF_VERIFIED,
    }
    _save_pipeline(pipeline)
    _log_event(wt_name, "promote", "OK", {
        "head": head, "branch": branch, "subject": subject, "note": note,
        "topic": new_entry["topic"],
    })

    print(f"  [OK] {wt_name} marked SELF_VERIFIED")
    print(f"       head   : {head[:10]}")
    print(f"       branch : {branch}")
    print(f"       subject: {subject}")
    print(f"       note   : {note}")
    # 显示同 wt 已有的其他分支 promote
    other_branches = [b for b in heads.keys() if b != branch]
    if other_branches:
        print(f"\n       同 wt 其他分支 promote:")
        for b in other_branches:
            e = heads[b]
            print(f"         - {b:40} head={e['head'][:10]} topic={e.get('topic','?')}")
    print(f"\n  Next: python scripts/release_prep.py integrate {wt_name}  (会整合所有 heads 中的分支)")
    return 0


def _infer_topic(note: str) -> str:
    """从 note 推断主题 (用于 heads{} 分类显示)"""
    note_lower = note.lower()
    if any(k in note_lower for k in ["permission", "权限", "role", "p_role"]):
        return "permission"
    if any(k in note_lower for k in ["valuehelp", "value_help", "search_refresh", "列表过滤"]):
        return "valuehelp"
    if any(k in note_lower for k in ["v1/v2", "v1_to_v2", "api-version", "deprecat", "api/v1", "api/v2"]):
        return "v1v2"
    if any(k in note_lower for k in ["infra", "基础设施", "proxy", "port"]):
        return "infra"
    return "other"


def cmd_integrate(wt_name: str, head_branch: str = None):
    """Layer 2: 协调智能体 整合变更到 release-prep

    步骤:
      1. 读取 wt HEAD + branch (或 --head 指定 branch)
      2. 在 release-prep wt 中 cherry-pick wt HEAD
      3. _wt_service.py start-be release-prep + start-fe release-prep
      4. health check /health (30s timeout)
      5. v33_state transition SELF_VERIFIED→CHERRY_PICKED

    失败回滚: cherry-pick 失败 → release-prep HEAD 不变, 状态 INTEGRATION_FAILED

    [V2026-07-22 C-A1] --head 参数:
      wt 可能 promote 多个 branch (例如 phase13-worktree 有 phase13-main + valuehelp)
      默认用 heads{} 里第一个 head 整合
      --head <branch> 指定要整合哪个 branch
    """
    pipeline = _load_pipeline()
    request = pipeline["requests"].get(wt_name)
    if not request:
        print(f"  [ERROR] {wt_name} not promoted yet. Run 'promote' first.")
        return 1
    if request.get("status") != SELF_VERIFIED:
        print(f"  [WARN] {wt_name} status is {request.get('status')}, not {SELF_VERIFIED}")
        print(f"         continuing anyway...")

    wt_path = Path(request["wt_path"])

    # [V2026-07-22 C-A1] 选 head: --head > heads{} 里指定 > heads{} 第一个
    if head_branch and "heads" in request and head_branch in request["heads"]:
        selected = request["heads"][head_branch]
        wt_head = selected["head"]
        wt_branch = head_branch
    elif "heads" in request and request["heads"]:
        # 用 heads{} 里第一个
        first_branch = next(iter(request["heads"]))
        selected = request["heads"][first_branch]
        wt_head = selected["head"]
        wt_branch = first_branch
    else:
        wt_head = request["head"]
        wt_branch = request["branch"]

    release_prep = _get_wt_path("release-prep")
    if not release_prep:
        print(f"  [ERROR] release-prep wt not found")
        return 1

    print(f"=== Integrate {wt_name} → release-prep ===")
    print(f"  Source: {wt_path} ({wt_branch} {wt_head[:10]})")
    print(f"  Target: {release_prep}")

    # 1. Snapshot release-prep HEAD before integrate
    rc, rp_before, _ = _git(release_prep, "rev-parse", "HEAD")
    print(f"\n[1/5] release-prep HEAD before: {rp_before[:10] if rc == 0 else '?'}")

    # 2. cherry-pick wt HEAD
    print(f"\n[2/5] Cherry-picking {wt_head[:10]} → release-prep")
    rc, out, err = _git(release_prep, "cherry-pick", wt_head)
    if rc != 0:
        print(f"  [ERROR] cherry-pick failed: {err[:200]}")
        _git(release_prep, "cherry-pick", "--abort")
        pipeline["integrations"][wt_name] = {
            "wt": wt_name,
            "status": INTEGRATION_FAILED,
            "stage": "cherry-pick",
            "error": err[:500],
            "ts": _now(),
        }
        _save_pipeline(pipeline)
        _log_event(wt_name, "integrate", "FAIL", {"stage": "cherry-pick", "error": err[:500]})
        print(f"\n  cherry-pick failed, release-prep HEAD unchanged (was {rp_before[:10]})")
        return 1
    print(f"  [OK] Cherry-pick successful")

    rc, rp_after, _ = _git(release_prep, "rev-parse", "HEAD")
    print(f"  release-prep HEAD after: {rp_after[:10] if rc == 0 else '?'}")

    # 3. Start release-prep services
    print(f"\n[3/5] Starting release-prep services (3006/3011)")
    wt_svc = REPO / "scripts" / "_wt_service.py"
    for cmd in (["start-be", "release-prep"], ["start-fe", "release-prep"]):
        try:
            r = subprocess.run(
                [sys.executable, str(wt_svc)] + cmd,
                capture_output=True, text=True, timeout=180,
            )
            if r.returncode == 0:
                print(f"  [OK] {cmd[0]} (port 3006/3011)")
            else:
                print(f"  [WARN] {cmd[0]} exited with {r.returncode}")
        except Exception as e:
            print(f"  [WARN] {cmd[0]} failed: {e}")

    # 4. Health check
    print(f"\n[4/5] Health check /health on 3011")
    import urllib.request
    healthy = False
    for i in range(15):  # 15 * 2s = 30s
        try:
            url = "http://localhost:3011/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    healthy = True
                    break
        except Exception:
            import time
            time.sleep(2)
    if healthy:
        print(f"  [OK] /health → 200")
    else:
        print(f"  [WARN] /health 未就绪, 但不阻塞集成")

    # 5. Update pipeline status
    print(f"\n[5/5] Update pipeline status → CHERRY_PICKED")
    pipeline["integrations"][wt_name] = {
        "wt": wt_name,
        "status": CHERRY_PICKED,
        "release_prep_before": rp_before,
        "release_prep_after": rp_after,
        "healthy": healthy,
        "head": wt_head,
        "branch": wt_branch,
        "ts": _now(),
    }
    pipeline["requests"][wt_name]["status"] = CHERRY_PICKED
    _save_pipeline(pipeline)
    _log_event(wt_name, "integrate", "OK", {
        "release_prep_after": rp_after, "healthy": healthy,
    })

    # 6. Transition v33 state
    try:
        v33_script = REPO / "scripts" / "_v33_state.py"
        if v33_script.exists():
            subprocess.run(
                [sys.executable, str(v33_script), "transition",
                 wt_name.upper(), CHERRY_PICKED, "--note", f"integrated to release-prep {rp_after[:10]}"],
                capture_output=True, text=True, timeout=30,
            )
            print(f"  [OK] v33_state → {CHERRY_PICKED}")
    except Exception as e:
        print(f"  [WARN] v33_state failed: {e}")

    print(f"\n=== Integrate done: {wt_name} → release-prep ({rp_after[:10]}) ===")
    print(f"  release-prep 服务在 3006/3011, PM 可以人工验证")
    print(f"  验证完后跑: python scripts/release_prep.py pm-verify {wt_name}")
    return 0


def cmd_pm_status(only_pending: bool = False):
    """Layer 3: PM 视图 — 所有变更的当前状态

    空态增强 [R3 V2026-07-22]:
      - 首次运行 pipeline 为空, 友好提示 + 列出"本应 promote 但没有"的 wt
      - 检查 release-prep 服务 (3006/3011) 是否运行
      - 给出明确的下一步命令
    """
    pipeline = _load_pipeline()
    requests = pipeline["requests"]
    integrations = pipeline["integrations"]

    print("=" * 80)
    print("  RELEASE PIPELINE STATUS (PM 视图)")
    print(f"  pipeline 文件: {PIPELINE_FILE}")
    print(f"  最后更新:     {pipeline.get('last_update', '(从未初始化)')}")
    print("=" * 80)

    # R3: 空态诊断 — 列出"本应 promote 但没有"的 wt
    if not requests:
        print("\n  (空态) pipeline.json 为空, 没有任何 agent 跑过 promote")
        print("\n  --- 诊断: 哪些 wt '本应有变更但没 promote'? ---")
        wt_base = REPO / "worktrees"
        phase13 = Path(r"D:\filework\phase13-worktree")
        all_wts = []
        if phase13.exists():
            all_wts.append(("phase13-worktree", phase13))
        if wt_base.exists():
            for p in wt_base.iterdir():
                if p.is_dir() and (p / ".git").exists():
                    all_wts.append((p.name, p))

        unpushed_with_changes = []
        for name, path in all_wts:
            # 检查是否有 uncommitted / unpushed commits
            rc, ahead, _ = _git(path, "rev-list", "--count", "@{u}..HEAD")
            if rc != 0:
                # 无 upstream, 跳过
                continue
            if int(ahead) > 0 if ahead.isdigit() else False:
                unpushed_with_changes.append((name, int(ahead)))

        if unpushed_with_changes:
            print("  [WARN] 以下 wt 有 unpushed commits, 可能漏 promote:")
            for name, ahead in unpushed_with_changes:
                print(f"    - {name:35} +{ahead} commits unpushed")
                print(f"        补救: python scripts/release_prep.py promote {name} --note \"...\"")
        else:
            print("  (没有未 promote 但有 unpushed commits 的 wt)")

        # R3: 检查 release-prep 服务是否运行
        print("\n  --- 诊断: release-prep 服务是否在跑? ---")
        import socket
        for port in (3006, 3011):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()
                if result == 0:
                    print(f"  [OK] port {port}: LISTENING")
                else:
                    print(f"  [DOWN] port {port}: 未监听")
            except Exception as e:
                print(f"  [ERROR] port {port}: {e}")
        print("  (release-prep 服务如未在跑, integrate 后会自动启动)")

        print("\n  --- 下一步建议 ---")
        print("  1. 让各 agent 跑 promote:")
        print("     python scripts/release_prep.py promote <wt-name> --note \"...\"")
        print("  2. 协调整合 (cherry-pick + 启服务 + health):")
        print("     python scripts/release_prep.py integrate <wt-name>")
        print("  3. PM 验证完:")
        print("     python scripts/release_prep.py pm-verify <wt-name>")
        print("\n  --- 相关 wt 列表 ---")
        for name, _ in all_wts:
            print(f"    {name}")
        return 0

    # 1. SELF_VERIFIED 但还没 INTEGRATE 的
    print("\n### 待整合 (SELF_VERIFIED → pending integrate)")
    pending = [r for r in requests.values() if r.get("status") == SELF_VERIFIED]
    if pending:
        for r in pending:
            print(f"  - {r['wt']:35} head={r['head'][:10]} note={r.get('note','')[:60]}")
            print(f"        整合命令: python scripts/release_prep.py integrate {r['wt']}")
    else:
        print("  (无)")

    # 2. CHERRY_PICKED 等 PM 验证
    print("\n### 待 PM 人工验证 (CHERRY_PICKED, 在 release-prep 3006/3011)")
    need_verify = []
    for r in requests.values():
        integ = integrations.get(r["wt"])
        if integ and integ.get("status") == CHERRY_PICKED and not integ.get("pm_verified"):
            need_verify.append(r)
    if need_verify:
        for r in need_verify:
            print(f"  - {r['wt']:35} head={r['head'][:10]} release_prep={integrations[r['wt']].get('release_prep_after','')[:10]}")
            print(f"        验证完: python scripts/release_prep.py pm-verify {r['wt']}")
    else:
        print("  (无)")

    # 3. PM_VERIFIED 已发布
    print("\n### 已发布 (PM_VERIFIED, 后续 deploy_v33_hook 会推到 main)")
    published = [r for r in requests.values() if r.get("status") == PM_VERIFIED]
    if published:
        for r in published:
            print(f"  - {r['wt']:35} head={r['head'][:10]} verified_at={r.get('pm_verified_at','-')}")
    else:
        print("  (无)")

    # 4. FAILED
    print("\n### 集成失败 (INTEGRATION_FAILED, 需 PM 决策)")
    failed = [r for r in integrations.values() if r.get("status") == INTEGRATION_FAILED]
    if failed:
        for r in failed:
            print(f"  - {r['wt']:35} stage={r.get('stage','?')} error={r.get('error','')[:100]}")
    else:
        print("  (无)")

    print("\n" + "=" * 80)
    print(f"  共 {len(requests)} 请求, {len(need_verify)} 待 PM 验证, {len(failed)} 失败")
    return 0


def cmd_pm_verify(wt_name: str, note: str = ""):
    """Layer 3: PM 验证完成 → 标记 PM_VERIFIED + 触发 deploy_v33_hook 推到 main"""
    pipeline = _load_pipeline()
    request = pipeline["requests"].get(wt_name)
    integ = pipeline["integrations"].get(wt_name)
    if not request or not integ:
        print(f"  [ERROR] {wt_name} not integrated")
        return 1
    if integ.get("pm_verified"):
        print(f"  [WARN] {wt_name} already PM_VERIFIED")
        return 0

    print(f"=== PM VERIFY: {wt_name} ===")

    # [V2026-07-22 R-F4] Schema 健康检查门控 (PM 验证前自动跑)
    # 背景: PM 报告 3006 看不到用户组/角色, 根因是 schema 缺 updated_at
    # 自动门控防止 PM 看到空白页浪费时间
    print(f"\n  [GATE 1/2] Schema health check...")
    schema_check = REPO / "scripts" / "schema_health_check.py"
    if schema_check.exists():
        # 调用 schema_health_check.py 验证 release-prep 数据库
        schema_proc = subprocess.run(
            [sys.executable, str(schema_check), "release-prep"],
            cwd=str(REPO), capture_output=True, text=True, timeout=30,
        )
        print(f"      exit={schema_proc.returncode}")
        # 只显示后 5 行 (太长看不全)
        schema_output_lines = schema_proc.stdout.strip().split("\n")
        for line in schema_output_lines[-5:]:
            print(f"      {line}")

        if schema_proc.returncode != 0:
            print(f"\n  [GATE FAIL] Schema check FAILED. PM 验证会看到空白页.")
            print(f"             请先修复 schema:")
            print(f"             python D:/filework/worktrees/release-prep/meta/scripts/migration_add_updated_at.py")
            print(f"             或: python meta/migrations/v007_53_add_role_usergroup_updated_at_baseline.py")
            return 1
        print(f"      [OK] schema healthy\n")
    else:
        print(f"      [WARN] schema_health_check.py not found, 跳过\n")

    # 1. Mark PM_VERIFIED in pipeline
    integ["pm_verified"] = True
    integ["pm_verified_at"] = _now()
    integ["pm_note"] = note
    request["status"] = PM_VERIFIED

    # [V2026-07-22 C-B2] 祖先链检查: 每个 head 必须真的在 release-prep HEAD 祖先链
    # 背景: 之前 bug 是 heads{} 里所有 head 都被标 PM_VERIFIED, 但实际上
    # 一些 head (例如 phase13-main) 从未被 cherry-pick 进 release-prep
    # 这导致 3006 看不到新代码, PM 浪费时间
    # 兼容: cherry-pick 后 hash 会变, 所以也接受"subject 等价"的 commit
    print(f"\n  [GATE 2/2] Ancestor chain check for each head...")
    release_prep_path = Path("D:/filework/worktrees/release-prep")
    heads = request.get("heads", {})
    failed_heads = []
    for branch, h in heads.items():
        head_hash = h.get("head", "")
        head_subject = h.get("subject", "")
        if not head_hash:
            print(f"      [WARN] {branch}: no head hash, skip")
            continue

        # Step 1: 原始 hash 祖先链
        anc_proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", head_hash, "HEAD"],
            cwd=str(release_prep_path), capture_output=True, text=True
        )
        short = head_hash[:8]
        if anc_proc.returncode == 0:
            print(f"      [OK ] {branch} ({short}) in release-prep")
            continue

        # Step 2: 找 branch 上任意 commit 的 subject 是否在 release-prep 中
        # 兼容 cherry-pick 后 hash 变, 但 subject 不变
        # 在 wt_path 找 branch 的所有 commit subject, 然后在 release-prep HEAD 找
        wt_path = request.get("wt_path", "")
        if wt_path and head_subject:
            # 找 branch 上所有 commit 的 subject 前 40 字
            wt_dir = wt_path.replace("\\\\", "\\")
            try:
                br_proc = subprocess.run(
                    ["git", "log", branch, "--oneline", "-15", "--format=%s"],
                    cwd=wt_dir, capture_output=True, text=True, encoding='utf-8', errors='replace',
                    timeout=10
                )
                if br_proc.returncode == 0:
                    wt_subjects = br_proc.stdout.strip().splitlines()
                    # 在 release-prep HEAD 找前 100 commit 的 subject
                    rp_proc = subprocess.run(
                        ["git", "log", "HEAD", "--oneline", "-100", "--format=%s"],
                        cwd=str(release_prep_path), capture_output=True, text=True, encoding='utf-8', errors='replace',
                        timeout=10
                    )
                    if rp_proc.returncode == 0:
                        rp_subjects = rp_proc.stdout
                        # 找任意 wt_subject 在 rp_subjects 中 (前 30 字匹配)
                        found_match = None
                        for ws in wt_subjects:
                            if not ws:
                                continue
                            key = ws[:30]
                            if key and key in rp_subjects:
                                found_match = ws[:50]
                                break
                        if found_match:
                            print(f"      [OK ] {branch} ({short}) cherry-pick equivalent: '{found_match}...'")
                            continue
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
                print(f"      [WARN] {branch}: branch subject scan failed: {e}")

        print(f"      [FAIL] {branch} ({short}) NOT in release-prep (no subject equivalent)")
        failed_heads.append((branch, head_hash))

    if failed_heads:
        print(f"\n  [GATE FAIL] {len(failed_heads)} head(s) not in release-prep!")
        print(f"             不能 PM_VERIFIED, 这些 head 还没集成:")
        for branch, h in failed_heads:
            print(f"             - {branch} ({h[:8]})")
        print(f"             修法: release_prep.py integrate <wt> --head <branch>")
        # 回滚上面的盲目标记
        integ["pm_verified"] = False
        integ["pm_verified_at"] = None
        request["status"] = CHERRY_PICKED
        _save_pipeline(pipeline)
        return 1

    # [V2026-07-22 R-V5] 同步更新 heads{} 中所有分支状态 (只更新通过祖先链的)
    for h in heads.values():
        h["status"] = PM_VERIFIED
        h["pm_verified_at"] = integ["pm_verified_at"]

    _save_pipeline(pipeline)
    _log_event(wt_name, "pm-verify", "OK", {"note": note})
    print(f"  [OK] {wt_name} → PM_VERIFIED at {integ['pm_verified_at']}")

    # 2. Transition v33_state
    v33_script = REPO / "scripts" / "_v33_state.py"
    if v33_script.exists():
        subprocess.run(
            [sys.executable, str(v33_script), "transition",
             wt_name.upper(), PM_VERIFIED, "--note", note or "PM 人工验证通过"],
            capture_output=True, text=True, timeout=30,
        )
        print(f"  [OK] v33_state → {PM_VERIFIED}")

    # 3. Trigger deploy_v33_hook
    deploy = REPO / "scripts" / "deploy_v33_hook.py"
    if deploy.exists():
        try:
            r = subprocess.run(
                [sys.executable, str(deploy), wt_name.upper(), "--mode", "verified"],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                print(f"  [OK] deploy_v33_hook 已触发 (推到 main)")
            else:
                print(f"  [WARN] deploy_v33_hook exit={r.returncode}")
        except Exception as e:
            print(f"  [WARN] deploy_v33_hook failed: {e}")

    print(f"\n=== {wt_name} 全流程完成: SELF_VERIFIED → CHERRY_PICKED → PM_VERIFIED ===")
    return 0


def main():
    p = argparse.ArgumentParser(
        description="release-prep 半自治 pipeline (3 层架构)"
    )
    sub = p.add_subparsers(dest="action", required=True)

    p_promote = sub.add_parser("promote", help="[Agent] 标记变更 SELF_VERIFIED")
    p_promote.add_argument("wt_name")
    p_promote.add_argument("--note", required=True, help="变更说明")

    p_integrate = sub.add_parser("integrate", help="[协调] cherry-pick + 启动服务")
    p_integrate.add_argument("wt_name")
    # [V2026-07-22 C-A1] 指定 branch cherry-pick (多 head 项目)
    p_integrate.add_argument("--head", help="指定要 cherry-pick 的 branch (不指定则用 head 字段的 branch)")

    sub.add_parser("pm-status", help="[PM] 查看所有变更状态")

    p_verify = sub.add_parser("pm-verify", help="[PM] 标记 PM_VERIFIED + 触发 deploy")
    p_verify.add_argument("wt_name")
    p_verify.add_argument("--note", default="", help="PM 验证备注")

    args = p.parse_args()

    if args.action == "promote":
        return cmd_promote(args.wt_name, args.note)
    elif args.action == "integrate":
        return cmd_integrate(args.wt_name, head_branch=args.head)
    elif args.action == "pm-status":
        return cmd_pm_status()
    elif args.action == "pm-verify":
        return cmd_pm_verify(args.wt_name, args.note)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
