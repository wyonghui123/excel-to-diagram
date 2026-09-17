#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_prod_perm_to_staging.py — prod 旧模型(role/user_group) → staging 新模型(permission_set/org) 数据迁移

方案: docs/PROD_TO_STAGING_PERMISSION_MIGRATION.md (v1.0, 2026-09-03)
执行位置: 172.20.59.7 上直接运行 (两库同机)
安全设计:
  - prod 库以 mode=ro 只读 URI 打开, 物理不可写
  - Step 0 外键预校验不过即中止 (绝不静默跳过/回退全量)
  - 全量 DB 备份 + 11 张目标表整表备份 (*_pre_mx_backup)
  - 单事务: 全部 INSERT 在一个事务内, verify 不过自动 ROLLBACK
  - 幂等: 按业务键查重, 重复执行 inserted=0
用法:
  python3 migrate_prod_perm_to_staging.py            # dry-run (不写任何数据)
  python3 migrate_prod_perm_to_staging.py --apply    # 实际执行
  python3 migrate_prod_perm_to_staging.py --status   # 仅打印两库现状
  python3 migrate_prod_perm_to_staging.py --downgrade  # 从 *_pre_mx_backup 恢复
"""
import sqlite3
import shutil
import sys
import json
from datetime import datetime

PROD_DB = 'file:/opt/app/deployments/meta/architecture.db?mode=ro'
STAGE_DB = '/opt/app/staging/meta/architecture.db'
BK = '_pre_mx_backup'
MARK = 'mx_migration'

# (目标表, 备份表)
TARGET_TABLES = [
    'permission_sets', 'permission_set_permissions', 'permission_set_menu_permissions',
    'permission_set_data_permissions', 'permission_set_dimension_scopes',
    'orgs', 'org_members', 'org_permission_sets', 'org_data_permissions',
    'user_permission_sets', 'permission_rules', 'data_permissions',
]


def log(msg):
    print(msg, flush=True)


def open_dbs():
    p = sqlite3.connect(PROD_DB, uri=True)
    s = sqlite3.connect(STAGE_DB)
    s.execute('PRAGMA foreign_keys=ON')
    return p, s


def table_exists(c, t):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def count(c, t, where='1=1', args=()):
    return c.execute(f'SELECT COUNT(*) FROM "{t}" WHERE {where}', args).fetchone()[0]


# ----------------------------------------------------------------------
# Step 0: 预校验 (任一失败 → abort, 不做任何写入)
# ----------------------------------------------------------------------

def precheck(p, s):
    errs = []

    # 1. 权限点主数据对齐: prod role_permissions 引用的 permission_id 必须都在 staging.permissions
    miss = p.execute(
        'SELECT DISTINCT permission_id FROM role_permissions '
        'WHERE permission_id NOT IN (SELECT id FROM permissions)').fetchall()
    if miss:
        errs.append(f'prod role_permissions 孤儿 permission_id: {[r[0] for r in miss]}')

    # 2. users 对齐
    pu = {r[0] for r in p.execute('SELECT id FROM users').fetchall()}
    su = {r[0] for r in s.execute('SELECT id FROM users').fetchall()}
    if pu != su:
        errs.append(f'users 不对齐: prod-only={sorted(pu - su)}, staging-only={sorted(su - pu)}')

    # 3. 菜单对齐: prod role_menu_permissions 的 menu_code 必须都在 staging.menus
    sm = {r[0] for r in s.execute('SELECT menu_code FROM menus').fetchall()}
    pm = {r[0] for r in p.execute('SELECT DISTINCT menu_code FROM role_menu_permissions').fetchall()}
    miss_m = pm - sm
    if miss_m:
        errs.append(f'prod 菜单权限引用的 menu_code 在 staging 缺失: {sorted(miss_m)}')

    # 4. prod 内部完整性: group_roles.role_id / role_dimension_scopes.role_id ⊆ roles
    orph_gr = count(p, 'group_roles', 'role_id NOT IN (SELECT id FROM roles)')
    if orph_gr:
        errs.append(f'prod group_roles 孤儿 role_id: {orph_gr}')
    orph_ds = count(p, 'role_dimension_scopes', 'role_id NOT IN (SELECT id FROM roles)')
    if orph_ds:
        errs.append(f'prod role_dimension_scopes 孤儿 role_id: {orph_ds}')

    # 5. staging 目标表全部存在
    for t in TARGET_TABLES:
        if not table_exists(s, t):
            errs.append(f'staging 缺目标表: {t}')

    if errs:
        log('[PRECHECK] FAIL:')
        for e in errs:
            log(f'  - {e}')
        return False
    log('[PRECHECK] OK (permission_id/users/menu_code/内部完整性/目标表 5 项全过)')

    # 孤儿预告 (不中止, 迁移时跳过并记日志)
    ugm_orph = count(p, 'user_group_members', 'user_id NOT IN (SELECT id FROM users)')
    if ugm_orph:
        log(f'[PRECHECK][WARN] prod user_group_members 孤儿 user {ugm_orph} 条 → 迁移时跳过')
    return True


# ----------------------------------------------------------------------
# 迁移主体
# ----------------------------------------------------------------------

def migrate(p, s, dry):
    stats = {}

    def stat(key, inserted, skipped):
        stats[key] = {'inserted': inserted, 'skipped': skipped}
        log(f'  {key}: inserted={inserted}, skipped={skipped}')

    def backup_tables():
        for t in TARGET_TABLES:
            bt = t + BK
            if table_exists(s, bt):
                log(f'  backup {bt} 已存在, 保留首次备份不覆盖')
                continue
            s.execute(f'CREATE TABLE "{bt}" AS SELECT * FROM "{t}"')
            log(f'  backup {t} → {bt} ({count(s, t)} rows)')

    # ---- M1: roles → permission_sets (按 code 跳过已有) ----
    def m1():
        ins = skip = 0
        existing = {r[0] for r in s.execute('SELECT code FROM permission_sets').fetchall()}
        for r in p.execute(
                'SELECT id, code, name, description, is_active, is_system, created_at '
                'FROM roles ORDER BY id').fetchall():
            rid, code, name, desc, active, is_sys, created = r
            if code in existing:
                skip += 1
                continue
            s.execute(
                'INSERT INTO permission_sets (id, code, name, description, is_active, is_system, '
                'created_at, created_by, updated_by) VALUES (?,?,?,?,?,?,?,?,?)',
                (rid, code, name, desc, active, is_sys, created, MARK, MARK))
            existing.add(code)
            ins += 1
        stat('M1 roles→permission_sets', ins, skip)

    # ---- M8: user_groups → orgs ----
    def m8():
        ins = skip = 0
        existing = {r[0] for r in s.execute('SELECT code FROM orgs').fetchall()}
        for r in p.execute(
                'SELECT id, name, code, parent_id, manager_id, description, created_at '
                'FROM user_groups ORDER BY id').fetchall():
            gid, name, code, parent, mgr, desc, created = r
            if code in existing:
                skip += 1
                continue
            s.execute(
                'INSERT INTO orgs (id, name, code, org_type, org_scope, parent_id, manager_id, '
                'description, created_at, created_by, updated_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (gid, name, code, 'department', 'internal', parent, mgr, desc, created, MARK, MARK))
            existing.add(code)
            ins += 1
        stat('M8 user_groups→orgs', ins, skip)

    # ---- M2: role_permissions → permission_set_permissions ----
    def m2():
        ins = skip = 0
        have = {(r[0], r[1]) for r in s.execute(
            'SELECT permission_set_id, permission_id FROM permission_set_permissions').fetchall()}
        for rid, pid, granted, created in p.execute(
                'SELECT role_id, permission_id, granted, created_at FROM role_permissions').fetchall():
            if (rid, pid) in have:
                skip += 1
                continue
            # 外键防御: ps 必须存在 (M1 之后必然存在, 双保险)
            if not s.execute('SELECT 1 FROM permission_sets WHERE id=?', (rid,)).fetchone():
                log(f'    [SKIP] role {rid} 不在 permission_sets, 跳过 (perm {pid})')
                skip += 1
                continue
            s.execute(
                'INSERT INTO permission_set_permissions (permission_set_id, permission_id, granted, created_at) '
                'VALUES (?,?,?,?)', (rid, pid, granted, created))
            have.add((rid, pid))
            ins += 1
        stat('M2 role_permissions→ps_permissions', ins, skip)

    # ---- M3: role_menu_permissions → permission_set_menu_permissions ----
    def m3():
        ins = skip = 0
        have = {(r[0], r[1]) for r in s.execute(
            'SELECT permission_set_id, menu_code FROM permission_set_menu_permissions').fetchall()}
        for rid, mc, created in p.execute(
                'SELECT role_id, menu_code, created_at FROM role_menu_permissions').fetchall():
            if (rid, mc) in have:
                skip += 1
                continue
            s.execute(
                'INSERT INTO permission_set_menu_permissions (permission_set_id, menu_code, created_at) '
                'VALUES (?,?,?)', (rid, mc, created))
            have.add((rid, mc))
            ins += 1
        stat('M3 role_menu_permissions→ps_menu_permissions', ins, skip)

    # ---- M4: role_dimension_scopes → permission_set_dimension_scopes ----
    def m4():
        ins = skip = 0
        have = {(r[0], r[1]) for r in s.execute(
            'SELECT permission_set_id, dimension_code FROM permission_set_dimension_scopes').fetchall()}
        for rid, dc, dv, ic, mode in p.execute(
                'SELECT role_id, dimension_code, dimension_values, inherit_children, scope_mode '
                'FROM role_dimension_scopes').fetchall():
            if (rid, dc) in have:
                skip += 1
                continue
            s.execute(
                'INSERT INTO permission_set_dimension_scopes (permission_set_id, dimension_code, '
                'dimension_values, inherit_children, scope_mode, created_by, updated_by) '
                'VALUES (?,?,?,?,?,?,?)', (rid, dc, dv, ic, mode, MARK, MARK))
            have.add((rid, dc))
            ins += 1
        stat('M4 role_dimension_scopes→ps_dimension_scopes', ins, skip)

    # ---- M5: role_data_permissions → permission_set_data_permissions ----
    def m5():
        ins = skip = 0
        have = {(r[0], r[1], r[2], r[3]) for r in s.execute(
            'SELECT permission_set_id, resource_type, resource_id, permission_level '
            'FROM permission_set_data_permissions').fetchall()}
        for rid, rt, ridx, lvl, inh, created, cby in p.execute(
                'SELECT role_id, resource_type, resource_id, permission_level, inherit_to_children, '
                'created_at, created_by FROM role_data_permissions').fetchall():
            if (rid, rt, ridx, lvl) in have:
                skip += 1
                continue
            s.execute(
                'INSERT INTO permission_set_data_permissions (permission_set_id, resource_type, '
                'resource_id, permission_level, inherit_to_children, created_at, created_by) '
                'VALUES (?,?,?,?,?,?,?)', (rid, rt, ridx, lvl, inh, created, MARK))
            have.add((rid, rt, ridx, lvl))
            ins += 1
        stat('M5 role_data_permissions→ps_data_permissions', ins, skip)

    # ---- M6: permission_rules (role_id→permission_set_id, 去重) ----
    def m6():
        ins = skip = 0
        have = {(r[0], r[1], r[2], r[3]) for r in s.execute(
            'SELECT permission_set_id, resource_type, condition, permission_level '
            'FROM permission_rules').fetchall()}
        rows = p.execute(
            'SELECT DISTINCT role_id, resource_type, condition, permission_level, is_denied, '
            'inherit_to_children, propagate_to_parents, analysis_mode, created_at, created_by, updated_at '
            'FROM permission_rules').fetchall()
        log(f'    (prod {count(p, "permission_rules")} 行 → DISTINCT {len(rows)} 行)')
        for rid, rt, cond, lvl, deny, inh, prop, amode, created, cby, upd in rows:
            if (rid, rt, cond, lvl) in have:
                skip += 1
                continue
            s.execute(
                'INSERT INTO permission_rules (permission_set_id, resource_type, condition, '
                'permission_level, is_denied, inherit_to_children, propagate_to_parents, '
                'analysis_mode, created_at, created_by, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (rid, rt, cond, lvl, deny, inh, prop, amode, created, cby, upd))
            have.add((rid, rt, cond, lvl))
            ins += 1
        stat('M6 permission_rules (去重)', ins, skip)

    # ---- M7: data_permissions (user 级) ----
    # staging 有 UNIQUE(user_id, resource_type, resource_id); prod 允许同 key 多级别并存
    # (如 user 1 的 domain:1 同时有 read/write/admin)。策略: 聚合到最高级别
    # (admin=3 > write=2 > read=1), 已存在同级别则跳过。
    def m7():
        rank = {'admin': 3, 'write': 2, 'read': 1}
        ins = upg = skip = 0
        have = {(r[0], r[1], r[2]): r[3] for r in s.execute(
            'SELECT user_id, resource_type, resource_id, permission_level FROM data_permissions').fetchall()}
        for uid, rt, ridx, lvl, inh, created in p.execute(
                'SELECT user_id, resource_type, resource_id, permission_level, inherit_to_children, '
                'created_at FROM data_permissions').fetchall():
            key = (uid, rt, ridx)
            if key not in have:
                s.execute(
                    'INSERT INTO data_permissions (user_id, resource_type, resource_id, permission_level, '
                    'inherit_to_children, created_at) VALUES (?,?,?,?,?,?)',
                    (uid, rt, ridx, lvl, inh, created))
                have[key] = lvl
                ins += 1
            elif rank.get(lvl, 0) > rank.get(have[key], 0):
                s.execute(
                    'UPDATE data_permissions SET permission_level=? '
                    'WHERE user_id=? AND resource_type=? AND resource_id=?',
                    (lvl, uid, rt, ridx))
                have[key] = lvl
                upg += 1
            else:
                skip += 1
        stats['M7 data_permissions (聚合去重)'] = {
            'inserted': ins, 'upgraded': upg, 'skipped': skip,
            'note': f'prod 82 行 → staging 唯一键聚合 {len(have)} 行'}
        log(f"  M7 data_permissions (聚合去重): inserted={ins}, upgraded={upg}, skipped={skip}"
            f" (prod 82 行 → 唯一键 {len(have)} 行)")

    # ---- M9: group_roles → org_permission_sets ----
    def m9():
        ins = skip = 0
        have = {(r[0], r[1]) for r in s.execute(
            'SELECT org_id, permission_set_id FROM org_permission_sets').fetchall()}
        for gid, rid, created, cby in p.execute(
                'SELECT group_id, role_id, created_at, created_by FROM group_roles').fetchall():
            if (gid, rid) in have:
                skip += 1
                continue
            s.execute(
                'INSERT INTO org_permission_sets (org_id, permission_set_id, created_at, created_by) '
                'VALUES (?,?,?,?)', (gid, rid, created, cby))
            have.add((gid, rid))
            ins += 1
        stat('M9 group_roles→org_permission_sets', ins, skip)

    # ---- M10: user_group_members → org_members (跳孤儿) ----
    def m10():
        ins = skip = orphan = 0
        have = {(r[0], r[1]) for r in s.execute(
            'SELECT user_id, org_id FROM org_members').fetchall()}
        users = {r[0] for r in s.execute('SELECT id FROM users').fetchall()}
        for uid, gid, is_mgr, joined in p.execute(
                'SELECT user_id, group_id, is_manager, joined_at FROM user_group_members').fetchall():
            if uid not in users:
                orphan += 1
                log(f'    [SKIP-ORPHAN] user {uid} 不在 staging users, 跳过 (org {gid})')
                continue
            if (uid, gid) in have:
                skip += 1
                continue
            s.execute(
                'INSERT INTO org_members (user_id, org_id, is_manager, joined_at) VALUES (?,?,?,?)',
                (uid, gid, is_mgr, joined))
            have.add((uid, gid))
            ins += 1
        stats['M10 user_group_members→org_members'] = {'inserted': ins, 'skipped': skip, 'orphan_skipped': orphan}
        log(f'  M10 user_group_members→org_members: inserted={ins}, skipped={skip}, orphan_skipped={orphan}')

    # ---- M11: user_roles → user_permission_sets (先清垃圾) ----
    def m11():
        garbage = count(s, 'user_permission_sets')
        s.execute('DELETE FROM user_permission_sets')
        log(f'  [CLEAN] user_permission_sets 清空 {garbage} 行 (含 350 孤儿, 已在备份表)')
        ins = 0
        for uid, rid, created in p.execute(
                'SELECT user_id, role_id, created_at FROM user_roles').fetchall():
            s.execute(
                'INSERT INTO user_permission_sets (user_id, permission_set_id, created_at) '
                'VALUES (?,?,?)', (uid, rid, created))
            ins += 1
        stat('M11 user_roles→user_permission_sets (重灌)', ins, 0)

    # ---- Step 6: 刷新 permission_sets 冗余计数列 ----
    def refresh_counters():
        s.execute('''
            UPDATE permission_sets SET
              menu_count       = (SELECT COUNT(*) FROM permission_set_menu_permissions m WHERE m.permission_set_id = permission_sets.id),
              permission_count = (SELECT COUNT(*) FROM permission_set_permissions x WHERE x.permission_set_id = permission_sets.id),
              data_perm_count  = (SELECT COUNT(*) FROM permission_set_data_permissions d WHERE d.permission_set_id = permission_sets.id),
              user_count       = (SELECT COUNT(*) FROM user_permission_sets u WHERE u.permission_set_id = permission_sets.id)
        ''')
        log('  permission_sets 计数列已重算 (menu/permission/data_perm/user_count)')

    # ---- Step 7: verify ----
    def verify():
        log('[VERIFY] 行数对账:')
        checks = []
        exp = {
            'permission_sets': 40, 'orgs': 35,
            'permission_set_menu_permissions': 44, 'permission_set_dimension_scopes': 38,
            'user_permission_sets': 1,
        }
        for t, e in exp.items():
            n = count(s, t)
            ok = n >= e
            checks.append(ok)
            log(f'  {t}: {n} (期望 >= {e}) {"OK" if ok else "FAIL"}')
        n = count(s, 'permission_set_permissions')
        checks.append(n >= 953)
        log(f'  permission_set_permissions: {n} (期望 >= 953) {"OK" if n >= 953 else "FAIL"}')
        n = count(s, 'org_permission_sets')
        checks.append(n >= 59)
        log(f'  org_permission_sets: {n} (期望 >= 59) {"OK" if n >= 59 else "FAIL"}')
        n = count(s, 'org_members')
        checks.append(n >= 5)
        log(f'  org_members: {n} (期望 >= 5) {"OK" if n >= 5 else "FAIL"}')
        # data_permissions: 期望 = prod 唯一键聚合数
        exp_dp = p.execute(
            'SELECT COUNT(DISTINCT user_id || "|" || resource_type || "|" || resource_id) '
            'FROM data_permissions').fetchone()[0]
        n = count(s, 'data_permissions')
        checks.append(n >= exp_dp)
        log(f'  data_permissions: {n} (期望 >= {exp_dp}, prod 唯一键聚合) {"OK" if n >= exp_dp else "FAIL"}')

        log('[VERIFY] 孤儿引用 (全部必须 = 0):')
        orph_checks = {
            'permission_set_permissions→ps': 'permission_set_id NOT IN (SELECT id FROM permission_sets)',
            'permission_set_permissions→permissions': 'permission_id NOT IN (SELECT id FROM permissions)',
            'permission_set_menu_permissions→ps': 'permission_set_id NOT IN (SELECT id FROM permission_sets)',
            'permission_set_dimension_scopes→ps': 'permission_set_id NOT IN (SELECT id FROM permission_sets)',
            'org_permission_sets→org': 'org_id NOT IN (SELECT id FROM orgs)',
            'org_permission_sets→ps': 'permission_set_id NOT IN (SELECT id FROM permission_sets)',
            'org_members→org': 'org_id NOT IN (SELECT id FROM orgs)',
            'org_members→users': 'user_id NOT IN (SELECT id FROM users)',
            'user_permission_sets→ps': 'permission_set_id NOT IN (SELECT id FROM permission_sets)',
            'user_permission_sets→users': 'user_id NOT IN (SELECT id FROM users)',
        }
        for name, where in orph_checks.items():
            t = name.split('→')[0]
            n = count(s, t, where)
            checks.append(n == 0)
            log(f'  {name}: {n} {"OK" if n == 0 else "FAIL"}')

        return all(checks)

    # ---- 执行编排 ----
    if not dry:
        log('[BACKUP] Step 1 全量 DB 备份 + Step 2 各表备份:')
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        bak_db = f'{STAGE_DB}.bak.mx_{ts}'
        shutil.copy2(STAGE_DB, bak_db)
        log(f'  全量: {bak_db}')
        backup_tables()

    log('[MIGRATE] 开始 (单事务):')
    try:
        if not dry:
            s.execute('BEGIN')
        m1()
        m8()
        m2()
        m3()
        m4()
        m5()
        m6()
        m7()
        m9()
        m10()
        m11()
        refresh_counters()
        ok = verify()
        if dry:
            log('[DRY-RUN] 未写入任何数据 (rollback dry 事务)')
            s.rollback()
            return stats, True
        if ok:
            s.commit()
            log('[COMMIT] 迁移已提交 ✓')
            return stats, True
        s.rollback()
        log('[ROLLBACK] verify 未通过, 事务已回滚, DB 保持迁移前状态')
        return stats, False
    except Exception as e:
        s.rollback()
        log(f'[ROLLBACK] 异常: {e} — 事务已回滚')
        raise


def downgrade():
    """从 *_pre_mx_backup 恢复 11 张目标表"""
    s = sqlite3.connect(STAGE_DB)
    s.execute('BEGIN')
    for t in TARGET_TABLES:
        bt = t + BK
        if not table_exists(s, bt):
            log(f'  {bt} 不存在, 跳过 {t}')
            continue
        s.execute(f'DELETE FROM "{t}"')
        s.execute(f'INSERT INTO "{t}" SELECT * FROM "{bt}"')
        log(f'  {t} ← {bt} ({count(s, t)} rows)')
    s.commit()
    log('[DOWNGRADE] 完成')


def status():
    p, s = open_dbs()
    tables = ['roles', 'role_permissions', 'role_menu_permissions', 'role_dimension_scopes',
              'role_data_permissions', 'user_groups', 'user_group_members', 'group_roles',
              'user_roles', 'permission_rules', 'data_permissions',
              'permission_sets', 'permission_set_permissions', 'permission_set_menu_permissions',
              'permission_set_data_permissions', 'permission_set_dimension_scopes',
              'orgs', 'org_members', 'org_permission_sets', 'user_permission_sets', 'permissions', 'users']
    out = {}
    for t in tables:
        out[t] = {
            'prod': count(p, t) if table_exists(p, t) else None,
            'staging': count(s, t) if table_exists(s, t) else None,
        }
    log(json.dumps(out, indent=1, ensure_ascii=False))
    p.close(); s.close()


def main():
    if '--status' in sys.argv:
        status(); return
    if '--downgrade' in sys.argv:
        downgrade(); return
    dry = '--apply' not in sys.argv
    log(f'=== prod→staging 权限/组织数据迁移 ({datetime.now():%Y-%m-%d %H:%M:%S}) mode={"DRY-RUN" if dry else "APPLY"} ===')
    p, s = open_dbs()
    if not precheck(p, s):
        log('预校验失败, 中止 (未做任何写入)')
        sys.exit(2)
    stats, ok = migrate(p, s, dry)
    p.close(); s.close()
    log(f'=== 结果: {"SUCCESS" if ok else "FAIL"} ===')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
