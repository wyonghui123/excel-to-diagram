---
alwaysApply: false
description: "AI 在执行远程 staging 服务重启、PID 杀除、DB 直接变更或 staging 部署时查阅此规则。源自 2026-09-01 spec16 Plan D staging 事故：pkill -f 误杀 core_service + DB symlink 自环丢数据。强制 7 条铁律：禁 pkill -f / 双重确认 PID / staging_services.sh / check_db_symlink.sh / verify-before-completion / DB 变更 24h 内迁移化 / BEFORE-AFTER 行数断言。"
globs: "**/staging*"
---

# Delta Deployment Safety Rules (v5.2)

> **Active rule** (since 2026-09-01 incident)
> **Owner**: PM review before any modification
> **Audience**: ALL AI Agents + human deployers
> **Migrated from**: [excel-to-diagram/.trae/rules/active/delta-deployment-safety.md](file:///d:/filework/excel-to-diagram/.trae/rules/active/delta-deployment-safety.md) v1.0 (2026-09-01)

This rule captures lessons from the 2026-09-01 spec16 Plan D staging deployment,
where the AI Agent inadvertently killed core_service 19200 by using a too-broad
`pkill -f "python.*server.py"` pattern. The 4-service staging stack depends on
core_service for both upload and exec APIs - killing it breaks deployment.

---

## Rule 1: NEVER use `pkill -f "python"` patterns

> **[!!!] Prohibition: do not use pkill with broad python patterns [!!!]**

The pattern `pkill -f "python.*server.py"` matches EVERY python service
including core_service, log_service, unified_proxy, and meta_backend. Killing
the wrong service can:
- Break the deployment script (no exec/upload endpoint)
- Take down unrelated services (502 to end users)
- Require manual recovery (no remote way to start them)

### Required pattern (use EXACT service name)

```bash
# [X] WRONG - too broad, kills all python services
pkill -f "python.*server.py"

# [X] WRONG - matches any python
pkill -f "python"

# [OK] CORRECT - exact match by full command line
pkill -f "/opt/miniconda3-py39/bin/python.*server.py --port 13011"

# [OK] BETTER - PID file based (preferred)
PID_FILE=/var/run/staging/13011.pid
[ -f "$PID_FILE" ] && kill -TERM $(cat $PID_FILE)

# [OK] BEST - service manager (start_staging.sh)
bash /opt/app/staging/scripts/start_staging.sh restart meta_backend
```

## Rule 2: Pre-kill verification (mandatory)

> **[!!!] Before sending SIGTERM to any process: [!!!]**

1. Confirm PID is the intended service: `ps -p <PID> -o pid,cmd`
2. Confirm PORT matches expected: `ss -tlnp | grep <PID>` or `lsof -p <PID> | grep LISTEN`
3. Confirm PARENT process (avoid killing parent which would orphan children)

```bash
# Step 1: confirm what we're about to kill
TARGET_PID=12983
ps -p $TARGET_PID -o pid,cmd | head -2
ss -tlnp 2>&1 | grep ":18081" | grep "pid=$TARGET_PID"

# Only proceed if BOTH checks pass
if ss -tlnp 2>&1 | grep ":18081" | grep -q "pid=$TARGET_PID"; then
    kill -TERM $TARGET_PID
    echo "killed PID $TARGET_PID on port 18081"
else
    echo "[FAIL] PID $TARGET_PID is NOT on port 18081, ABORT"
fi
```

## Rule 3: Use staging_services wrapper

> **[!!!] Always use /opt/app/staging/bin/staging_services.sh (recommended) [!!!]**

This wrapper script handles the 4-service dependency graph:

```bash
# List all staging services with PIDs and ports
bash /opt/app/staging/bin/staging_services.sh list

# Restart only meta_backend (keeps core_service alive)
bash /opt/app/staging/bin/staging_services.sh restart meta_backend

# Health check all 4 services
bash /opt/app/staging/bin/staging_services.sh health
```

> **[DONE 2026-09-01] P1-3 created staging_services.sh at tools/staging_services.sh [DONE]**
>
> Features: `list / status / health / start / stop / restart / restart-deps / topo / help`.
> Built-in safety:
>   - `stop core_service` and `stop --all` REFUSE to kill core (it's the /api/exec channel)
>   - `get_pid` falls back to ps grep when ss can't show owner pid (non-root case)
>   - `health` uses port-LISTEN check (not pid check), tolerates non-root ss
>   - Reverse topo order: unified_18081 → meta_backend → log_service → core_service
>   - Forward topo order: core_service → log_service → meta_backend → unified_18081
>
> Deploy: include in deploy bundle at `tools/staging_services.sh`, install to `/opt/app/staging/bin/staging_services.sh` via deploy.sh.

## Rule 4: Always run check_db_symlink.sh before backend restart

> **[!!!] Mandatory pre-check before any backend restart [!!!]**

```bash
# Before restart:
bash /opt/app/staging/deploy/current/tools/check_db_symlink.sh
# exit 0 = safe to restart
# exit 1 = symlink loop, FIX FIRST
# exit 2 = DB too small, RESTORE FROM BACKUP FIRST
# exit 3 = DB missing, FIX PATH
# exit 4 = DB not writable, FIX PERMISSIONS
# exit 5 = SQLite integrity error, RESTORE
```

**Never** restart backend if check_db_symlink.sh returns non-zero.
The 2026-09-01 incident was caused by a self-loop symlink `architecture.db ->
architecture.db` which made the restart truncate the DB to 0 bytes.

## Rule 5: Always check_db_symlink.sh + AI Agent "verify-before-completion"

> **[!!!] Cross-reference: verify-before-completion skill [!!!]**

Before claiming a deployment is complete:

1. `bash check_db_symlink.sh` returns 0
2. `python db_fingerprint.py verify <DB> <EXPECTED>` returns ok=True
3. `curl /api/v2/health` (or appropriate health endpoint) returns 200
4. `curl /api/v1/menu-permission/visible` returns expected leaf_menus count
5. Manual smoke test on key user flow (login + 1 main action)

If ANY check fails, the deployment is NOT complete. Do not claim success.

## Rule 6: DB direct changes must be wrapped in a migration within 24h

> **[!!!] DB-DELETE / DB-INSERT outside a migration = tech debt [!!!]**

The 2026-09-01 staging deployment did direct SQL DELETE on 6 legacy menus
because the init_menu_permissions.py script didn't handle the cleanup case.
This is acceptable for emergency hotfix, but within 24h:

1. Wrap the SQL in `meta/migrations/v<N+1>__<desc>.py`
2. Add backup-then-delete pattern (preserves rollback capability)
3. Add idempotent check (skip if backup table already exists)
4. Add verify() function
5. Add to migration runner test suite

The migration v078__drop_legacy_user_list_menus.py was created on
2026-09-01 to encapsulate the staging cleanup. New envs (prod) running this
sequence will get the same cleanup automatically.

## Rule 7: AI Agent must pre-declare expected state before any DB mutation

> **[!!!] Before DELETE/INSERT/TRUNCATE: state expected vs actual [!!!]**

```python
# BEFORE running any DB mutation, output this:
print("[BEFORE]")
for table in CRITICAL_TABLES:
    n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {n} rows")

# Run mutation

# AFTER mutation, output this:
print("[AFTER]")
for table in CRITICAL_TABLES:
    n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {n} rows")
print(f"[DRIFT] delta should be -N for {table_name}, got: ...")
```

This is the "expected vs actual" assertion that should ALWAYS accompany a
DB modification. If drift is unexpected, abort and restore from backup.

---

## References

- 2026-09-01 staging incident timeline (this conversation)
- `tools/check_db_symlink.sh` - DB safety pre-check
- `tools/db_fingerprint.py` - schema/data diff verification
- `tools/manifest_utils.py` - file-level SHA256 delta
- `meta/migrations/v078__drop_legacy_user_list_menus.py` - migration example
- `verify-before-completion` skill - generic verification pattern

## CHANGELOG

| Date | Version | Change |
|------|---------|--------|
| 2026-09-02 | v5.2 | 迁移到全局 v5.2 + 智能生效 description + globs: **/staging* |
| 2026-09-01 | v1.0 | Initial rule after staging incident (项目内 active/) |
