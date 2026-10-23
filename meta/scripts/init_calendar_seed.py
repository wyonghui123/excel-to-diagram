# -*- coding: utf-8 -*-
"""作业日历种子数据（calendar / calendar_day）— 演示数据

背景:
  calendars / calendar_days 两表落地后为空，作业日历页与位置页的「site → 日历」
  链路无数据可看：父日历选择器（树形弹窗）打开是空的，locations.calendar_id
  恒为 NULL（走 FR-009 兜底「周一至周五」，看不出继承语义）。

本脚本造三档演示数据:
  1. CN 国家基准日历（parent_calendar_id 为空）—— 顶层基准
  2. 两个厂区派生日历（parent 指向基准）—— 一级继承
  3. 若干例外日（calendar_days）—— holiday 非工作日 / workday 强制工作日（调休）

编码说明:
  code 沿用 key_template 的 CAL-{SEQ:6} 连续编号（CAL-000001 起）。不冲突：
  KeyTemplateEngine.auto_detect_start 会扫 calendars.code 取「尾部 6 位数字」
  的最大值 +1 作为下一个序号（prefix_filter='CAL-'），所以手工种子编号之后
  走接口新建日历会自动接着 CAL-000004，不会撞唯一索引。

幂等: by code upsert（先 SELECT → UPDATE / INSERT）；父级先于子级写入；
      例外日按 (calendar_id, date) upsert；重跑只刷新稳定属性，
      不重置 status（停用≠删除，重跑不复活 —— 沿 region / currency 种子同一约定）
"""
import logging

logger = logging.getLogger(__name__)

# 基准 + 派生日历：(code, name, country_code, parent_code, mask 覆盖项)
# mask 未列出的字段走默认：mon-fri 工作、sat-sun 休息
_CALENDARS = [
    ('CAL-000001', '中国基准日历', 'CN', None, {}),
    # 完全继承基准（周模式与父一致）
    ('CAL-000002', '上海张江厂区日历', 'CN', 'CAL-000001', {}),
    # 覆盖父值：周六也上班（六天工作制），演示「覆盖而非合并」
    ('CAL-000003', '上海临港厂区日历', 'CN', 'CAL-000001', {'day_mask_sat': True}),
]

# 例外日：(calendar_code, date, day_type, note)
# 注：日期为演示用节假日/调休样本，非官方法定节假日表（spec §10 TBD-二期）
_DAYS = [
    ('CAL-000001', '2027-01-01', 'holiday', '元旦（演示数据）'),
    ('CAL-000001', '2027-01-02', 'holiday', '元旦假期（演示数据）'),
    ('CAL-000001', '2027-01-03', 'workday', '元旦调休上班（演示数据）'),
    ('CAL-000001', '2027-10-01', 'holiday', '国庆节（演示数据）'),
    ('CAL-000001', '2027-10-02', 'holiday', '国庆假期（演示数据）'),
    ('CAL-000001', '2027-10-03', 'holiday', '国庆假期（演示数据）'),
    ('CAL-000001', '2027-10-09', 'workday', '国庆调休上班（演示数据）'),
    ('CAL-000002', '2027-02-10', 'holiday', '春节全厂停产（演示数据）'),
    ('CAL-000003', '2027-08-15', 'holiday', '设备年检全厂停工（演示数据）'),
]

# site → 日历挂接（打通「site → 日历」链路；仅 site 类型有效）
_LOCATION_CALENDARS = {
    'SITE-SH': 'CAL-000002',
}

_DAY_FIELDS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')

# 种子数据无真实操作人 → 统一记 system（audit_aspect 的 created_by/updated_by 列）
_SEED_ACTOR = 'system'


def _default_masks():
    """默认周模式：周一至周五工作、周六周日休息"""
    return {f'day_mask_{d}': d in ('mon', 'tue', 'wed', 'thu', 'fri')
            for d in _DAY_FIELDS}


def _iter_calendars():
    """产出 (code, name, country_code, parent_code, masks)"""
    for code, name, country_code, parent_code, override in _CALENDARS:
        masks = _default_masks()
        masks.update(override)
        yield code, name, country_code, parent_code, masks


def init_calendar_seed_data(data_source):
    """幂等写入作业日历种子。返回 (inserted, updated) 计数。

    不重置 status：已停用的日历重跑保持 inactive（停用≠删除）。
    """
    inserted = 0
    updated = 0

    # ---- 1. 日历本体（父先于子）----
    for code, name, country_code, parent_code, masks in _iter_calendars():
        country_id = None
        if country_code:
            rows = data_source.query(
                "SELECT id FROM regions WHERE code = ?", (country_code,))
            if not rows:
                logger.error(
                    "Calendar seed: 国家 %s 未写入, 跳过 %s", country_code, code)
                continue
            country_id = rows[0]['id']

        parent_id = None
        if parent_code:
            rows = data_source.query(
                "SELECT id FROM calendars WHERE code = ?", (parent_code,))
            if not rows:
                logger.error(
                    "Calendar seed: 父日历 %s 未写入, 跳过 %s", parent_code, code)
                continue
            parent_id = rows[0]['id']

        mask_values = [1 if masks[f'day_mask_{d}'] else 0 for d in _DAY_FIELDS]
        existing = data_source.query(
            "SELECT id FROM calendars WHERE code = ?", (code,))
        if existing:
            # 只刷新稳定属性; 不重置 status（停用≠删除, 重跑不复活）
            data_source.execute(
                "UPDATE calendars SET name = ?, parent_calendar_id = ?, "
                "country_id = ?, " +
                ", ".join(f"day_mask_{d} = ?" for d in _DAY_FIELDS) +
                " WHERE code = ?",
                [name, parent_id, country_id] + mask_values + [code])
            # created_at / created_by 只补空, 不覆盖既有值（重跑不刷新审计时间）
            data_source.execute(
                "UPDATE calendars SET created_at = COALESCE(created_at, datetime('now')), "
                "created_by = COALESCE(created_by, ?) WHERE code = ?",
                [_SEED_ACTOR, code])
            updated += 1
        else:
            data_source.execute(
                "INSERT INTO calendars "
                "(code, name, parent_calendar_id, country_id, " +
                ", ".join(f"day_mask_{d}" for d in _DAY_FIELDS) +
                ", status, created_at, created_by) "
                "VALUES (?, ?, ?, ?, " +
                ", ".join(["?"] * len(_DAY_FIELDS)) +
                ", 'active', datetime('now'), ?)",
                [code, name, parent_id, country_id] + mask_values + [_SEED_ACTOR])
            inserted += 1

    # ---- 2. 例外日（按 (calendar_id, date) upsert）----
    days_inserted = 0
    days_updated = 0
    for cal_code, date, day_type, note in _DAYS:
        rows = data_source.query(
            "SELECT id FROM calendars WHERE code = ?", (cal_code,))
        if not rows:
            logger.error("Calendar seed: 日历 %s 不存在, 跳过例外日 %s",
                         cal_code, date)
            continue
        cal_id = rows[0]['id']
        existing = data_source.query(
            "SELECT id FROM calendar_days WHERE calendar_id = ? AND date = ?",
            (cal_id, date))
        if existing:
            data_source.execute(
                "UPDATE calendar_days SET day_type = ?, note = ? "
                "WHERE calendar_id = ? AND date = ?",
                [day_type, note, cal_id, date])
            # created_at / created_by 只补空, 不覆盖既有值（重跑不刷新审计时间）
            data_source.execute(
                "UPDATE calendar_days SET created_at = COALESCE(created_at, datetime('now')), "
                "created_by = COALESCE(created_by, ?) "
                "WHERE calendar_id = ? AND date = ?",
                [_SEED_ACTOR, cal_id, date])
            days_updated += 1
        else:
            data_source.execute(
                "INSERT INTO calendar_days "
                "(calendar_id, date, day_type, note, created_at, created_by) "
                "VALUES (?, ?, ?, ?, datetime('now'), ?)",
                [cal_id, date, day_type, note, _SEED_ACTOR])
            days_inserted += 1

    # ---- 3. site → 日历挂接 ----
    linked = 0
    for loc_code, cal_code in _LOCATION_CALENDARS.items():
        loc_rows = data_source.query(
            "SELECT id, location_type FROM locations WHERE code = ?", (loc_code,))
        if not loc_rows:
            logger.info("Calendar seed: 位置 %s 不存在, 跳过挂接", loc_code)
            continue
        if loc_rows[0]['location_type'] != 'site':
            logger.info("Calendar seed: 位置 %s 非 site 类型, 跳过挂接", loc_code)
            continue
        cal_rows = data_source.query(
            "SELECT id FROM calendars WHERE code = ?", (cal_code,))
        if not cal_rows:
            logger.error("Calendar seed: 日历 %s 不存在, 跳过 %s 挂接",
                         cal_code, loc_code)
            continue
        data_source.execute(
            "UPDATE locations SET calendar_id = ? WHERE code = ?",
            [cal_rows[0]['id'], loc_code])
        linked += 1

    data_source.commit()
    logger.info(
        "Calendar seeded: %d inserted, %d updated; days %d/%d; locations linked %d",
        inserted, updated, days_inserted, days_updated, linked)
    return inserted, updated


if __name__ == '__main__':
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path

    _db_path = get_meta_db_path()
    _ds = get_data_source("sqlite", database=str(_db_path))
    _ins, _upd = init_calendar_seed_data(_ds)
    print(f'[calendar seed] db={_db_path}')
    print(f'[calendar seed] calendars: {_ins} inserted, {_upd} updated')
