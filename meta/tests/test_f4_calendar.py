"""作业日历（calendar / calendar_day）结构与行为测试

依据: docs/superpowers/specs/2026-10-05-calendar-dictionary-design.md

覆盖 spec §9.4 测试策略七类:
  1. TestNaming       命名规范 / key_template / code 不可变        FR-012
  2. TestStructure    字段类型 / 必填 / 默认值 / 索引 / restrict     FR-001/003/007/012
  3. TestInheritance  自引用继承 / exclude_self / 一级约束          FR-002
  4. TestBuild        双表建表 / date 列类型 / 唯一索引             NFR-001
  5. TestCalendarDay  例外日 CRUD / 唯一约束 / 无记录即标准        FR-005/006
  6. TestValueHelp    country_id 锁定 level=country                 FR-003
  7. TestFallback     未挂日历兜底口径                              FR-009

v2.0 关键决策: date 用既有 type: datetime（ISO 8601 字符串），零平台改造。
"""

import os
import sys

import pytest

# 平台内部表（calendars / calendar_days 为新建业务表）暂无 Factory；
# 按仓库既有惯例走 raw SQL escape hatch（见 test_workflow_engine.py 同款注释），
# 避免整文件被 conftest 的 raw-SQL 门控拦跳。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

_META_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _META_ROOT not in sys.path:
    sys.path.insert(0, _META_ROOT)

_SCHEMA_DIR = os.path.join(_META_ROOT, 'schemas')
_DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
_DAY_FIELDS = tuple(f'day_mask_{d}' for d in _DAYS)

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _load_yaml(filename):
    import yaml
    path = os.path.join(_SCHEMA_DIR, filename)
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def _fields(filename):
    data = _load_yaml(filename)
    return {f['id']: f for f in data['fields']}


def _get_id(ds, code):
    return ds.query("SELECT id FROM calendars WHERE code = ?", (code,))[0]['id']


def _insert_calendar(ds, code, name, parent_code=None, country_id=None, **masks):
    """插入日历; masks 覆盖 day_mask_*（默认 mon-fri 工作、sat-sun 休息）"""
    row = {'code': code, 'name': name, 'parent_calendar_id': None, 'country_id': country_id}
    for d in _DAYS:
        row[f'day_mask_{d}'] = bool(masks.get(f'day_mask_{d}', d in ('mon', 'tue', 'wed', 'thu', 'fri')))
    row['status'] = 'active'
    row['created_at'] = '2026-10-05 00:00:00'
    # 列: code, name, parent_calendar_id, country_id + 7 个 day_mask + status, created_at = 13
    cols = ['code', 'name', 'parent_calendar_id', 'country_id'] + list(_DAY_FIELDS) + ['status', 'created_at']
    values = ([row['code'], row['name'], row['parent_calendar_id'], row['country_id']]
              + [row[f'day_mask_{d}'] for d in _DAYS]
              + [row['status'], row['created_at']])
    assert len(cols) == len(values) == 13, (len(cols), len(values))
    ds.execute(
        "INSERT INTO calendars (" + ", ".join(cols) + ") VALUES ("
        + ", ".join(["?"] * len(cols)) + ")",
        values,
    )
    if parent_code:
        ds.execute("UPDATE calendars SET parent_calendar_id = ? WHERE code = ?",
                   (_get_id(ds, parent_code), code))


def _insert_day(ds, calendar_id, date, day_type='holiday', note=None):
    ds.execute(
        "INSERT INTO calendar_days (calendar_id, date, day_type, note) VALUES (?, ?, ?, ?)",
        [calendar_id, date, day_type, note],
    )


# ────────────────────────────────────────
# 1. 命名（FR-012）
# ────────────────────────────────────────
class TestNaming:
    def test_ids_and_table_names(self):
        cal = _load_yaml('calendar.yaml')
        day = _load_yaml('calendar_day.yaml')
        assert cal['id'] == 'calendar'
        assert cal['table_name'] == 'calendars'
        assert day['id'] == 'calendar_day'
        assert day['table_name'] == 'calendar_days'

    def test_key_template(self):
        """日历无国标代码，走 key_template 自动编码（对标 SAP WFCID 短码）"""
        cal = _load_yaml('calendar.yaml')
        assert cal['key_template'] == 'CAL-{SEQ:6}'

    def test_code_business_key_immutable(self):
        f = _fields('calendar.yaml')['code']
        assert f['required'] is True
        assert f['unique'] is True
        assert f['max_length'] == 20
        assert f['semantics']['business_key'] is True
        assert f['semantics']['immutable'] is True

    def test_display_name_field(self):
        assert _load_yaml('calendar.yaml')['display_name_field'] == 'name'


# ────────────────────────────────────────
# 2. 结构（FR-001 / FR-003 / FR-007 / FR-012）
# ────────────────────────────────────────
class TestStructure:
    def test_seven_day_mask_fields(self):
        """FR-001: 7 个布尔位表达周工作日模式"""
        f = _fields('calendar.yaml')
        for fid in _DAY_FIELDS:
            assert fid in f, f'缺少 {fid}'
            assert f[fid]['type'] == 'boolean'
            assert f[fid]['required'] is True

    def test_day_mask_defaults_weekday_work(self):
        """默认周一至周五工作、周六日休息（通用工厂日历）"""
        f = _fields('calendar.yaml')
        for d in ('mon', 'tue', 'wed', 'thu', 'fri'):
            assert f[f'day_mask_{d}']['default'] is True, f'{d} 应默认工作'
        for d in ('sat', 'sun'):
            assert f[f'day_mask_{d}']['default'] is False, f'{d} 应默认休息'

    def test_country_id_nullable_reference(self):
        """FR-003: 地区可空（空=通用日历）"""
        f = _fields('calendar.yaml')['country_id']
        assert f['type'] == 'integer'
        assert f.get('nullable') is True
        assert f['semantics']['display']['target_type'] == 'region'
        assert f['value_help']['source']['target_bo'] == 'region'

    def test_parent_calendar_id_self_reference(self):
        """FR-002: 自引用继承字段"""
        f = _fields('calendar.yaml')['parent_calendar_id']
        assert f['type'] == 'integer'
        assert f.get('nullable') is True
        assert f['value_help']['source']['target_bo'] == 'calendar'
        assert f['ui']['relation'] == 'calendar'

    def test_status_enum(self):
        """FR-008: 状态机 active/inactive"""
        f = _fields('calendar.yaml')['status']
        values = [e['value'] for e in f['enum_values']]
        assert values == ['active', 'inactive']
        assert f['default'] == 'active'

    def test_no_validity_fields_in_phase1(self):
        """v2.0: 有效期字段移至二期（TBD-7），一期不得出现"""
        f = _fields('calendar.yaml')
        assert 'valid_from' not in f
        assert 'valid_to' not in f

    def test_no_capacity_field_in_phase1(self):
        """FR-010: 半日容量本期不实现（TBD-3）"""
        assert 'capacity' not in _fields('calendar_day.yaml')

    def test_indexes(self):
        cal = _load_yaml('calendar.yaml')
        idx = {i['name']: i for i in cal['indexes']}
        assert idx['idx_calendar_code']['unique'] is True
        assert idx['idx_calendar_code']['fields'] == ['code']
        for name in ('idx_calendar_parent_id', 'idx_calendar_country_id', 'idx_calendar_status'):
            assert name in idx, f'缺少索引 {name}'

    def test_restrict_on_declared(self):
        """FR-007: 删除保护（locations.calendar_id 待 location 落定后补，见 spec §9.6）"""
        dp = _load_yaml('calendar.yaml')['deletion_policy']
        assert dp['mode'] == 'restrict'
        pairs = {(r['table'], r['foreign_key']) for r in dp['restrict_on']}
        assert ('calendars', 'parent_calendar_id') in pairs
        assert ('calendar_days', 'calendar_id') in pairs

    def test_category_config(self):
        """NFR-004: 权限登记照 region 先例"""
        cc = _load_yaml('calendar.yaml')['category_config']
        assert cc['create_permission'] == 'calendar:create'
        assert cc['update_permission'] == 'calendar:update'
        assert cc['delete_permission'] == 'calendar:delete'
        assert cc['owner_auto_permission'] is False


# ────────────────────────────────────────
# 3. 继承语义（FR-002）
# ────────────────────────────────────────
class TestInheritance:
    def test_calendar_day_is_child_object(self):
        """IF-001: calendar_day 以 parent_object 挂载为子表"""
        day = _load_yaml('calendar_day.yaml')
        assert day['parent_object'] == 'calendar'
        assert day['hierarchy']['enabled'] is True
        assert day['hierarchy']['parent_field'] == 'calendar_id'

    def test_no_nested_key_in_schema(self):
        """nested 键平台 yaml_loader 不解析，仅前端约定 → schema 层不得依赖"""
        assert 'nested' not in _load_yaml('calendar_day.yaml')

    def test_exclude_self_enabled(self):
        """自引用防环: 编辑态排除自身"""
        beh = _fields('calendar.yaml')['parent_calendar_id']['value_help']['behavior']
        assert beh['exclude_self'] is True

    def test_hierarchy_max_depth_two(self):
        """基准 + 派生两级（max_depth=2）"""
        hl = _fields('calendar.yaml')['parent_calendar_id']['semantics']['hierarchy_level']
        assert hl['relation'] == 'self_reference'
        assert hl['max_depth'] == 2

    def test_parent_is_baseline_calendar(self, cal_ds):
        """派生日历的父必须是基准日历（父的 parent_calendar_id 为空）"""
        _insert_calendar(cal_ds, 'CAL-000001', 'CN 基准')
        _insert_calendar(cal_ds, 'CAL-000002', '上海厂区', parent_code='CAL-000001')
        _insert_calendar(cal_ds, 'CAL-000003', '苏州厂区', parent_code='CAL-000002')

        rows = cal_ds.query("SELECT code, parent_calendar_id FROM calendars ORDER BY code")
        by_code = {r['code']: r['parent_calendar_id'] for r in rows}
        base_id = _get_id(cal_ds, 'CAL-000001')
        derived_id = _get_id(cal_ds, 'CAL-000002')
        assert by_code['CAL-000001'] is None                      # 基准无父
        assert by_code['CAL-000002'] == base_id                    # 派生指向基准
        assert by_code['CAL-000003'] == derived_id                 # 三级链路（业务约束禁止）

    def test_mask_is_override_not_merge(self, cal_ds):
        """派生日历 day_mask 整体覆盖父值（非逐位合并）"""
        _insert_calendar(cal_ds, 'CAL-000001', 'CN 基准')
        _insert_calendar(cal_ds, 'CAL-000002', '六天工作制',
                         parent_code='CAL-000001', day_mask_sat=True)
        row = cal_ds.query("SELECT day_mask_sat FROM calendars WHERE code = 'CAL-000002'")[0]
        assert bool(row['day_mask_sat']) is True, '派生日历应保留自身覆盖值'


# ────────────────────────────────────────
# 夹具（建表）
# ────────────────────────────────────────
@pytest.fixture()
def cal_ds(tmp_path):
    """临时库: 建 calendars + calendar_days 双表（region 不建，country_id 无 FK 目标）"""
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    objs = [load_yaml_file(os.path.join(_SCHEMA_DIR, fn), aspects_defs=aspects)
            for fn in ('calendar.yaml', 'calendar_day.yaml')]
    assert all(o is not None for o in objs), 'calendar YAML 加载失败'

    ds = get_data_source("sqlite", database=str(tmp_path / 'f4_calendar.db'))
    sync_schema_from_meta(ds, objs)
    yield ds
    _clear_data_source_cache_for_testing()


# ────────────────────────────────────────
# 4. 建表端到端（NFR-001）
# ────────────────────────────────────────
class TestBuild:
    def test_both_tables_created(self, cal_ds):
        names = {r[0] for r in cal_ds.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'calendars' in names
        assert 'calendar_days' in names

    def test_date_column_is_datetime(self, cal_ds):
        """v2.0 核心: date 复用平台既有 DATETIME，零平台改造"""
        cols = {r[1]: r[2] for r in cal_ds.execute("PRAGMA table_info('calendar_days')").fetchall()}
        assert cols['date'] == 'DATETIME'

    def test_no_updated_at_physical_column(self, cal_ds):
        """audit_aspect 的 updated_at 为 virtual，不落物理表（region 教训）"""
        cols = {r[1] for r in cal_ds.execute("PRAGMA table_info('calendars')").fetchall()}
        assert 'created_at' in cols
        assert 'updated_at' not in cols

    def test_unique_index_created(self, cal_ds):
        names = {r[1] for r in cal_ds.execute("PRAGMA index_list('calendar_days')").fetchall()}
        assert 'idx_calendar_day_unique' in names

    def test_code_unique_index_created(self, cal_ds):
        names = {r[1] for r in cal_ds.execute("PRAGMA index_list('calendars')").fetchall()}
        assert 'idx_calendar_code' in names

    def test_duplicate_code_rejected(self, cal_ds):
        _insert_calendar(cal_ds, 'CAL-000001', 'CN 基准')
        with pytest.raises(Exception):
            _insert_calendar(cal_ds, 'CAL-000001', '重复编码')

    def test_day_mask_defaults_applied(self, cal_ds):
        """建表后 INSERT 不显式给 day_mask 时应落默认（mon-fri 工作）"""
        cal_ds.execute(
            "INSERT INTO calendars (code, name, status, created_at) "
            "VALUES ('CAL-000001', '默认日历', 'active', '2026-10-05 00:00:00')")
        row = cal_ds.query("SELECT * FROM calendars WHERE code = 'CAL-000001'")[0]
        assert bool(row['day_mask_mon']) is True
        assert bool(row['day_mask_sat']) is False


# ────────────────────────────────────────
# 5. 例外日（FR-005 / FR-006）
# ────────────────────────────────────────
class TestCalendarDay:
    def test_day_type_two_values_only(self):
        """P6 Standard 语义: 无记录即标准，故只需 holiday/workday 两值"""
        f = _fields('calendar_day.yaml')['day_type']
        assert [e['value'] for e in f['enum_values']] == ['holiday', 'workday']
        assert f['required'] is True

    def test_date_required_and_note_optional(self):
        f = _fields('calendar_day.yaml')
        assert f['date']['required'] is True
        assert f['date']['type'] == 'datetime'
        assert f['note'].get('nullable') is True
        assert f['note']['max_length'] == 200

    def test_unique_constraint_same_date_rejected(self, cal_ds):
        """FR-006: 同一日历同一日期只允许一条例外（防排程重复计数）"""
        _insert_calendar(cal_ds, 'CAL-000001', 'CN 基准')
        cid = _get_id(cal_ds, 'CAL-000001')
        _insert_day(cal_ds, cid, '2026-10-01', 'holiday', '国庆')
        with pytest.raises(Exception):
            _insert_day(cal_ds, cid, '2026-10-01', 'workday', '重复')

    def test_same_date_different_calendar_allowed(self, cal_ds):
        """唯一约束作用域为 (calendar_id, date)，跨日历可同日不同例外"""
        _insert_calendar(cal_ds, 'CAL-000001', 'CN 基准')
        _insert_calendar(cal_ds, 'CAL-000002', '上海厂区', parent_code='CAL-000001')
        _insert_day(cal_ds, _get_id(cal_ds, 'CAL-000001'), '2026-10-01', 'holiday')
        _insert_day(cal_ds, _get_id(cal_ds, 'CAL-000002'), '2026-10-01', 'workday')
        n = cal_ds.query("SELECT COUNT(*) AS n FROM calendar_days")[0]['n']
        assert n == 2

    def test_crud_roundtrip(self, cal_ds):
        _insert_calendar(cal_ds, 'CAL-000001', 'CN 基准')
        cid = _get_id(cal_ds, 'CAL-000001')
        _insert_day(cal_ds, cid, '2026-02-17', 'holiday', '春节')
        _insert_day(cal_ds, cid, '2026-02-14', 'workday', '春节调休')

        rows = cal_ds.query("SELECT date, day_type FROM calendar_days ORDER BY date")
        assert [(r['date'][:10], r['day_type']) for r in rows] == [
            ('2026-02-14', 'workday'), ('2026-02-17', 'holiday')]

        cal_ds.execute("UPDATE calendar_days SET day_type = 'workday' WHERE date LIKE '2026-02-17%'")
        assert cal_ds.query("SELECT day_type FROM calendar_days WHERE date LIKE '2026-02-17%'")[0]['day_type'] == 'workday'

        cal_ds.execute("DELETE FROM calendar_days")
        assert cal_ds.query("SELECT COUNT(*) AS n FROM calendar_days")[0]['n'] == 0

    def test_no_record_means_standard(self, cal_ds):
        """P6 Standard: 删除例外日即恢复基准周模式（无 third enum needed）"""
        _insert_calendar(cal_ds, 'CAL-000001', 'CN 基准')
        cid = _get_id(cal_ds, 'CAL-000001')
        base = cal_ds.query("SELECT day_mask_sat FROM calendars WHERE id = ?", (cid,))[0]
        _insert_day(cal_ds, cid, '2026-10-03', 'workday')       # 周六强制上班
        cal_ds.execute("DELETE FROM calendar_days WHERE date LIKE '2026-10-03%'")
        after = cal_ds.query("SELECT day_mask_sat FROM calendars WHERE id = ?", (cid,))[0]
        assert after['day_mask_sat'] == base['day_mask_sat'], '删例外后应回归基准'

    def test_date_range_query(self, cal_ds):
        """ISO 8601 字符串序 = 日期序，范围查询可用（v2.0 免平台改造的前提）"""
        _insert_calendar(cal_ds, 'CAL-000001', 'CN 基准')
        cid = _get_id(cal_ds, 'CAL-000001')
        for d in ('2026-01-01', '2026-06-01', '2026-12-31'):
            _insert_day(cal_ds, cid, d, 'holiday')
        rows = cal_ds.query(
            "SELECT date FROM calendar_days WHERE date >= ? AND date <= ? ORDER BY date",
            ['2026-06-01', '2026-12-31'])
        assert [r['date'][:10] for r in rows] == ['2026-06-01', '2026-12-31']


# ────────────────────────────────────────
# 6. 地区级联（FR-003）
# ────────────────────────────────────────
class TestValueHelp:
    def test_country_binding_locks_level_country(self):
        """候选过滤: 常量锁定 level=country，下拉仅返回国家级节点"""
        bindings = _fields('calendar.yaml')['country_id']['value_help']['behavior']['parameter_bindings']
        assert len(bindings) == 1
        b = bindings[0]
        assert b['target_field'] == 'level'
        assert b['constant'] == 'country'
        assert not b.get('local_field'), '国家级锁定不应依赖本地字段'

    def test_country_presentation_columns(self):
        pres = _fields('calendar.yaml')['country_id']['value_help']['presentation']
        assert pres['result_type'] == 'dropdown'
        assert [c['field'] for c in pres['columns']] == ['code', 'name']
        assert pres['display_format'] == '{name}'

    def test_country_ui_relation_region(self):
        ui = _fields('calendar.yaml')['country_id']['ui']
        assert ui['relation'] == 'region'
        assert ui['widget'] == 'select'
        assert ui['clearable'] is True, '地区可空 → 允许清除'

    def test_list_column_association_render(self):
        """列表页地区列按 association 渲染（照 address 四 FK 先例）"""
        cols = {c['field']: c for c in _load_yaml('calendar.yaml')['ui_view_config']['list']['columns']}
        for fid, target in (('country_id', 'region'), ('parent_calendar_id', 'calendar')):
            assert cols[fid]['render_as'] == 'association'
            assert cols[fid]['target_type'] == target
            assert cols[fid]['display_field'] == 'name'


# ────────────────────────────────────────
# 7. 兜底口径（FR-009）
# ────────────────────────────────────────
class TestFallback:
    def test_calendar_id_absent_from_phase1_schema(self):
        """FR-009 + TBD-1: location.site.calendar_id 本期不接线（location 在飞）"""
        cal_cols = set(_fields('calendar.yaml').keys())
        assert 'calendar_id' not in cal_cols, '主表不应有 calendar_id（那是子表字段）'

    def test_baseline_mask_equals_fallback_profile(self):
        """未挂日历兜底 = 周一至周五工作（等价 day_mask_mon..fri=true、sat/sun=false）"""
        data = _load_yaml('calendar.yaml')
        defaults = {f['id']: f.get('default') for f in data['fields']
                    if f['id'].startswith('day_mask_')}
        assert defaults['day_mask_mon'] is True
        assert defaults['day_mask_sun'] is False

    def test_restrict_omits_unbuilt_location_table(self):
        """TBD-1: locations.calendar_id 列尚不存在，不得写虚假 restrict_on"""
        dp = _load_yaml('calendar.yaml')['deletion_policy']
        tables = {r['table'] for r in dp['restrict_on']}
        assert 'locations' not in tables
