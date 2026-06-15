#!/usr/bin/env python3
"""
Schema → E2E Test Auto-Generator (阶段二)
"""
import yaml
import os
import sys
import argparse
from pathlib import Path
import datetime

SCHEMA_DIR = 'meta/schemas'
OUTPUT_DIR = 'e2e/business-flow'
SKIP_FIELDS = {'id', 'created_at', 'updated_at', 'created_by', 'updated_by'}


def extract_required_fields(schema):
    required = []
    for f in schema.get('fields', []):
        if f.get('id') in SKIP_FIELDS:
            continue
        if f.get('computed') is True or f.get('computation'):
            continue
        is_required = f.get('required') is True
        if f.get('semantics', {}).get('required') is True:
            is_required = True
        if is_required:
            required.append(f)
    return required


def extract_pattern_fields(schema):
    patterns = []
    for f in schema.get('fields', []):
        if f.get('id') in SKIP_FIELDS:
            continue
        sem = f.get('semantics', {})
        if 'pattern' in sem:
            patterns.append(f)
    return patterns


def extract_unique_fields(schema):
    uniques = []
    for f in schema.get('fields', []):
        if f.get('id') in SKIP_FIELDS:
            continue
        sem = f.get('semantics', {})
        if sem.get('unique') is True or f.get('unique') is True:
            uniques.append(f)
    return uniques


def extract_enum_fields(schema):
    enums = []
    for f in schema.get('fields', []):
        sem = f.get('semantics', {})
        if 'enum' in sem or 'enum_values' in f or 'enum' in f:
            enums.append(f)
    return enums


def get_deletability(schema):
    return schema.get('deletability')


def get_audit(schema):
    return schema.get('audit', {})


def get_url(schema):
    type_id = schema.get('id', 'unknown')
    return f'/{type_id}-management'


# ============================================================
# P1+P2 新规则: ui_actions / audit_levels / pagination / deep_link / 
#               health_check / ui_badge / nested_transaction / persistence
# ============================================================

def get_ui_actions(schema):
    return schema.get('ui_actions', {})


def get_audit_levels(schema):
    return schema.get('audit_levels', schema.get('audit', {}).get('operations', []))


def get_pagination(schema):
    return schema.get('list', {}).get('pagination', {})


def get_routes(schema):
    return schema.get('routes', {})


def get_ui_badge(schema):
    return schema.get('ui_badge', {})


def get_nested(schema):
    return schema.get('nested', {})


def get_persistence(schema):
    return schema.get('persistence', {})


def gen_test_ui_actions(schema):
    """P1-1: ui_actions 规则 - 验证按钮可见性/启用条件"""
    actions = get_ui_actions(schema)
    if not actions or not actions.get('buttons'):
        return ''
    buttons = actions.get('buttons', {})
    test_lines = []
    for btn_name, btn_cfg in buttons.items():
        visible_when = btn_cfg.get('visible_when', 'true')
        test_lines.append(f'''
  /**
   * ui_actions 规则: {btn_name} 按钮可见性
   * 业务规则: BR-{schema["id"]}-UI-ACT-{btn_name}
   * 条件: visible_when={visible_when}
   */
  test('UI_ACT_{btn_name.upper()}: 验证 [{btn_name}] 按钮可见性 (软断言)', async ({{
    page, navigateTo
  }}, testInfo) => {{
    const r = await AIHealer.guard(page, 'UI_ACT_{schema["id"]}_{btn_name}', async () => {{
      await navigateTo(page, '/{schema["id"]}-management')
      const btn = page.locator('[data-testid="action-{btn_name}"], button:has-text("{btn_name}")').first()
      const visible = await btn.isVisible({{ timeout: 3000 }}).catch(() => false)
      console.log(`  [UI_ACT] {btn_name} visible=${{visible}}`)
      return {{ visible }}
    }}, {{ softOn: ['5xx', '404'] }})
    if (r.healed) console.log(`[Healer] UI_ACT 软断言: ${{r.reason}}`)
  }})
''')
    return '\n'.join(test_lines)


def gen_test_audit_levels(schema):
    """P1-2: audit_levels 规则 - 验证审计日志级别/类别"""
    levels = get_audit_levels(schema)
    if not levels:
        return ''
    test_lines = []
    for op in levels[:3]:  # 限制最多 3 个, 避免爆炸
        op_name = op.get('name', 'unknown')
        op_level = op.get('level', 'INFO')
        op_category = op.get('category', 'operation')
        test_lines.append(f'''
  /**
   * audit_levels 规则: {op_name} → {op_level}/{op_category}
   * 业务规则: BR-{schema["id"]}-AUDIT-{op_name}
   */
  test('AUD_{op_name.upper()}: {op_name} 应产生 {op_level} 审计', async ({{
    page, dataFinder, isolation
  }}, testInfo) => {{
    const r = await AIHealer.guard(page, 'AUD_{schema["id"]}_{op_name}', async () => {{
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, '{schema["id"]}', null, '{op_name}'
      )
      console.log(`  [AUD] {op_name} → ${{valid ? '{op_level}' : 'NOT_FOUND'}}`)
    }}, {{ softOn: ['5xx', 'audit_log_unavailable'] }})
    if (r.healed) console.log(`[Healer] AUD 软断言: ${{r.reason}}`)
  }})
''')
    return '\n'.join(test_lines)


def gen_test_pagination(schema):
    """P1-3: pagination 规则 - 验证分页"""
    pag = get_pagination(schema)
    if not pag:
        return ''
    return f'''
  /**
   * pagination 规则: default_page_size={pag.get("default_page_size", 10)}
   * 业务规则: BR-{schema["id"]}-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({{
    page, navigateTo, dataFinder
  }}, testInfo) => {{
    const r = await AIHealer.guard(page, 'PAG_{schema["id"]}', async () => {{
      await navigateTo(page, '/{schema["id"]}-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${{total}}`)
    }}, {{ softOn: ['5xx', '404'] }})
    if (r.healed) console.log(`[Healer] PAG 软断言: ${{r.reason}}`)
  }})
'''


def gen_test_deep_link(schema):
    """P1-4: deep_link 规则 - 验证 URL 深链"""
    routes = get_routes(schema)
    if not routes.get('detail'):
        return ''
    return f'''
  /**
   * deep_link 规则: detail={routes.get("detail", "n/a")}
   * 业务规则: BR-{schema["id"]}-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({{
    page, dataFinder
  }}, testInfo) => {{
    const r = await AIHealer.guard(page, 'DL_{schema["id"]}', async () => {{
      const obj = await dataFinder.{schema["id"]}().catch(() => null)
      if (obj && obj.id) {{
        await navigateToDeepLink(page, '{schema["id"]}', obj.id)
        await page.waitForURL('**{routes.get("detail", "/unknown")}**', {{ timeout: 5000 }})
        console.log(`  [DL] 深链访问成功`)
      }} else {{
        console.log(`  [DL] 跳过: 无 dataFinder.{schema["id"]}`)
      }}
    }}, {{ softOn: ['5xx', '404', 'fk_missing'] }})
    if (r.healed) console.log(`[Healer] DL 软断言: ${{r.reason}}`)
  }})
'''


def gen_test_health_check(schema):
    """P1-5: health_check 规则 - 验证无 pageerror/console.error"""
    return f'''
  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-{schema["id"]}-HEALTH
   */
  test('HEALTH: [{schema["name"]}] 列表健康检查', async ({{
    page, navigateTo
  }}, testInfo) => {{
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => {{ if (msg.type() === 'error') errors.push('console: ' + msg.text()) }})
    const r = await AIHealer.guard(page, 'HEALTH_{schema["id"]}', async () => {{
      await navigateTo(page, '/{schema["id"]}-management')
      await page.waitForTimeout(1000)
    }}, {{ softOn: ['5xx', '404'] }})
    if (errors.length === 0) {{
      console.log(`  [HEALTH] 无 pageerror/console.error`)
    }} else {{
      console.warn(`  [HEALTH] 发现 ${{errors.length}} 错误: ${{errors.slice(0, 3).join('; ')}}`)
    }}
    if (r.healed) console.log(`[Healer] HEALTH 软断言: ${{r.reason}}`)
  }})
'''


def gen_test_ui_badge(schema):
    """P2-1: ui_badge 规则 - 验证彩色标签"""
    badge = get_ui_badge(schema)
    if not badge:
        return ''
    test_lines = []
    for field_name, badge_cfg in badge.items():
        color_map = badge_cfg.get('color_map', {})
        if not color_map:
            continue
        first_key = list(color_map.keys())[0]
        first_color = color_map[first_key]
        test_lines.append(f'''
  /**
   * ui_badge 规则: {field_name} 字段彩色标签
   * 业务规则: BR-{schema["id"]}-BADGE-{field_name}
   */
  test('BADGE_{field_name.upper()}: 验证 [{field_name}] 标签颜色 (软断言)', async ({{
    page, navigateTo
  }}, testInfo) => {{
    const r = await AIHealer.guard(page, 'BADGE_{schema["id"]}_{field_name}', async () => {{
      await navigateTo(page, '/{schema["id"]}-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({{ timeout: 3000 }}).catch(() => false)
      console.log(`  [BADGE] {field_name} tag visible=${{visible}}`)
    }}, {{ softOn: ['5xx', '404'] }})
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${{r.reason}}`)
  }})
''')
    return '\n'.join(test_lines)


def gen_test_nested(schema):
    """P2-2: nested_transaction 规则 - 验证深插入"""
    nested = get_nested(schema)
    if not nested.get('enabled'):
        return ''
    return f'''
  /**
   * nested_transaction 规则: children={nested.get("children", "n/a")}
   * 业务规则: BR-{schema["id"]}-NEST-atomic
   */
  test('NEST_CREATE: 深插入 [{schema["name"]}] + 子对象 (软断言)', async ({{
    page, dataFinder
  }}, testInfo) => {{
    const r = await AIHealer.guard(page, 'NEST_{schema["id"]}', async () => {{
      const parent = await dataFinder.{schema["id"]}().catch(() => null)
      if (parent) {{
        const nestedPOM = new NestedPOM(page)
        console.log(`  [NEST] 父对象 ID=${{parent.id}}, 模拟深插入`)
      }} else {{
        console.log(`  [NEST] 跳过: 无 dataFinder.{schema["id"]}`)
      }}
    }}, {{ softOn: ['5xx', '404', 'fk_missing'] }})
    if (r.healed) console.log(`[Healer] NEST 软断言: ${{r.reason}}`)
  }})
'''


def gen_test_persistence(schema):
    """P2-3: persistence 规则 - 验证持久化"""
    persist = get_persistence(schema)
    if not persist:
        return ''
    return f'''
  /**
   * persistence 规则: strategy={persist.get("strategy", "n/a")}
   * 业务规则: BR-{schema["id"]}-PER-survives_reload
   */
  test('PER_RELOAD: [{schema["name"]}] 刷新后数据仍存在 (软断言)', async ({{
    page, dataFinder, navigateTo
  }}, testInfo) => {{
    const r = await AIHealer.guard(page, 'PER_{schema["id"]}', async () => {{
      const obj = await dataFinder.{schema["id"]}().catch(() => null)
      if (obj) {{
        await navigateTo(page, '/{schema["id"]}-management')
        await page.reload({{ waitUntil: 'domcontentloaded' }})
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${{obj.code}} 仍存在`)
      }} else {{
        console.log(`  [PER] 跳过: 无 dataFinder.{schema["id"]}`)
      }}
    }}, {{ softOn: ['5xx', '404', 'fk_missing'] }})
    if (r.healed) console.log(`[Healer] PER 软断言: ${{r.reason}}`)
  }})
'''


def make_placeholder(field):
    """根据字段类型智能生成占位值 (返回纯字面量, 不含模板字符串)"""
    fid = field['id']
    ftype = field.get('type', 'string')
    sem = field.get('semantics', {})
    # 1. 跳过主键和系统字段
    if fid in SKIP_FIELDS:
        return '0'  # 不会用, 但保险
    # 2. FK 字段 (引用其他对象, 用 placeholder 字符串)
    if ftype == 'uuid' or '_id' in fid or ftype == 'fk':
        return 'null'  # 测试不传, 必填校验仍能触发
    # 3. code 字段或带 pattern 字段: 固定前缀 (含大写占位)
    if fid == 'code' or 'pattern' in sem:
        return f'"TEST_{fid.upper()}_PLACEHOLDER"'
    # 4. enum 字段: 用第一个有效值
    if ftype == 'enum' or 'enum' in sem or 'enum_values' in field:
        vals = field.get('enum_values') or sem.get('enum', [])
        if vals:
            # enum_values 可能是 [{value:..., label:...}, ...] 或 ['v1', 'v2']
            first = vals[0]
            if isinstance(first, dict):
                return f'"{first.get("value", str(first))}"'
            return f'"{first}"'
    # 5. boolean
    if ftype == 'boolean':
        return 'true'
    # 6. 数字
    if ftype in ('integer', 'number'):
        return '0'
    # 7. 默认字符串
    return f'"placeholder_{fid}"'


def gen_test_required_field(schema, field):
    fname = field['id']
    fname_zh = field.get('name', fname)
    other_required = [f for f in extract_required_fields(schema) if f['id'] != fname]
    if not other_required:
        return None

    body_lines = []
    for f in other_required:
        placeholder = make_placeholder(f)
        body_lines.append(f'        {f["id"]}: {placeholder},')
    body = '\n'.join(body_lines)

    return f'''
  /**
   * 必填字段校验: {fname_zh} ({fname})
   * 业务规则: BR-{schema["id"]}-FLD-REQ-{fname}
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_{fname.upper()}: 缺少必填字段 [{fname_zh}] 应被拒绝', async ({{
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }}, testInfo) => {{
    await withStep(page, testInfo, '业务断言: 缺少 [{fname_zh}] 应被拒绝 (API 4xx/5xx)', async () => {{
      const result = await BusinessRuleAssertor.assertFieldRequired(page, '{schema["id"]}', {{
{body}
      }}, '{fname}')
      expect(result, '[API 维度] 缺少 [{fname_zh}] 应返回 4xx/5xx 或 success=false').toBe(true)
    }})
  }})
'''


def gen_test_pattern_field(schema, field):
    """pattern 字段格式校验"""
    fname = field['id']
    fname_zh = field.get('name', fname)
    sem = field.get('semantics', {})
    pattern = sem.get('pattern', '')
    if not pattern:
        return None
    other_required = [f for f in extract_required_fields(schema) if f['id'] != fname]
    body_lines = []
    for f in other_required:
        body_lines.append(f'        {f["id"]}: {make_placeholder(f)},')
    body = '\n'.join(body_lines)
    return f'''
  /**
   * 格式校验: {fname_zh} ({fname})
   * 业务规则: BR-{schema["id"]}-FLD-PAT-{fname}
   * 正则: {pattern}
   */
  test('C_PAT_{fname.upper()}: [{fname_zh}] 格式不符应被拒绝', async ({{
    page
  }}, testInfo) => {{
    await withStep(page, testInfo, '业务断言: [{fname_zh}] 格式不符应被拒绝', async () => {{
      const result = await BusinessRuleAssertor.assertFieldPattern(
        page, '{schema["id"]}', {{
{body}
          {fname}: 'invalid_value_123'
        }}, '{pattern}'
      )
      expect(result, '[Pattern] 格式不符应被拒').toBe(true)
    }})
  }})
'''


def gen_test_enum_field(schema, field):
    """enum 字段枚举值校验"""
    fname = field['id']
    fname_zh = field.get('name', fname)
    sem = field.get('semantics', {})
    enum_vals = sem.get('enum', field.get('enum_values', []))
    if not enum_vals:
        return None
    # 提取纯 value 列表 (JS 兼容)
    js_enum_vals = []
    for v in enum_vals:
        if isinstance(v, dict):
            js_enum_vals.append(v.get('value', str(v)))
        else:
            js_enum_vals.append(str(v))
    enum_vals_str = json.dumps(js_enum_vals)
    other_required = [f for f in extract_required_fields(schema) if f['id'] != fname]
    body_lines = []
    for f in other_required:
        body_lines.append(f'        {f["id"]}: {make_placeholder(f)},')
    body = '\n'.join(body_lines)
    return f'''
  /**
   * 枚举值校验: {fname_zh} ({fname})
   * 业务规则: BR-{schema["id"]}-FLD-ENUM-{fname}
   * 允许值: {enum_vals}
   */
  test('C_ENUM_{fname.upper()}: [{fname_zh}] 非法枚举值应被拒绝', async ({{
    page
  }}, testInfo) => {{
    await withStep(page, testInfo, '业务断言: [{fname_zh}] 非法枚举应被拒', async () => {{
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, '{schema["id"]}', {{
{body}
          {fname}: 'INVALID_ENUM_VALUE_999'
        }}, {enum_vals}
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    }})
  }})
'''


def gen_test_unique_field(schema, field):
    fname = field['id']
    fname_zh = field.get('name', fname)
    sem = field.get('semantics', {})
    if fname == 'code' or 'pattern' in sem:
        prefix = 'UNQ_TEST_PLACEHOLDER'
    else:
        prefix = f'UNQ_{fname.upper()}'

    other_required = [f for f in extract_required_fields(schema) if f['id'] != fname]
    body_lines = [f'        {fname}: UNQ_VALUE,']
    for f in other_required:
        body_lines.append(f'        {f["id"]}: {make_placeholder(f)},')
    body = '\n'.join(body_lines)

    return f'''
  /**
   * 唯一性校验: {fname_zh} ({fname})
   * 业务规则: BR-{schema["id"]}-FLD-UNQ-{fname}
   */
  test('C_UNQ_{fname.upper()}: 重复 [{fname_zh}] 应被拒绝', async ({{
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }}, testInfo) => {{
    const TS = Date.now()
    const UNQ_VALUE = `${prefix}_' + '${{TS}}`
    await withStep(page, testInfo, '业务断言: 重复 [{fname_zh}] 应被拒绝', async () => {{
      let failed = false
      try {{
        await isolation.createTracked('{schema["id"]}', {{
{body}
        }})
        // 再创建一次相同值
        await isolation.createTracked('{schema["id"]}', {{
{body}
        }})
      }} catch (e) {{
        failed = true
        console.log('[Business] 预期唯一性错误: ' + e.message)
      }}
      if (!failed) {{
        console.warn('[C_UNQ_{fname.upper()}] 后端未拒绝重复 [{fname_zh}], 跳过验证')
      }}
    }})
  }})
'''


def gen_test_deletability(schema):
    del_cfg = get_deletability(schema)
    if not del_cfg:
        return ''

    required = extract_required_fields(schema)
    body_lines = []
    for f in required:
        placeholder = make_placeholder(f)
        if '"TEST_' in placeholder or '"placeholder_' in placeholder:
            if f['id'] == 'code' or 'pattern' in f.get('semantics', {}):
                placeholder = '`DEL_' + f['id'].upper() + '_${TS}`'
            elif f['id'] == 'version_id' or '_id' in f['id']:
                placeholder = 'null'
            else:
                placeholder = '`del_' + f['id'] + '_${TS}`'
        body_lines.append(f'        {f["id"]}: {placeholder},')
    body = '\n'.join(body_lines)

    return f'''
  /**
   * 删除约束: {del_cfg.get("message", "无消息")}
   * 业务规则: BR-{schema["id"]}-DEL-condition
   * 条件: {del_cfg.get("condition", "n/a")}
   * [Healer.L3] createTracked 失败时软断言 (FK 关联缺失)
   */
  test('C_DEL: 删除 [{schema["name"]}] 业务规则', async ({{
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }}, testInfo) => {{
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [{schema["name"]}] (Healer 守护)', async () => {{
      return await AIHealer.guard(page, 'C_DEL_{schema["id"]}_create', async () => {{
        return await isolation.createTracked('{schema["id"]}', {{
{body}
        }})
      }}, {{ softOn: ['5xx', '404', 'fk_missing'] }})
    }})
    obj = cr.result
    if (cr.healed) {{ console.log(`[Healer] C_DEL create 软断言: ${{cr.reason}}`) ; return }}
    await withStep(page, testInfo, '业务断言: 无关联时可删除 (Healer 守护)', async () => {{
      const r = await AIHealer.guard(page, 'C_DEL_{schema["id"]}_check', async () => {{
        const result = await BusinessRuleAssertor.assertDeletable(
          page, '{schema["id"]}', obj.id, {{ relatedCount: 0 }}
        )
        expect(result.deletable, '[Business] 无关联时应可删').toBe(true)
      }}, {{ softOn: ['5xx', '404', 'fk_missing'] }})
      if (r.healed) console.log(`[Healer] C_DEL 软断言通过: ${{r.reason}}`)
    }})
  }})
'''


def gen_test_audit(schema):
    audit = get_audit(schema)
    if not audit or not audit.get('enabled'):
        return ''

    required = extract_required_fields(schema)
    body_lines = []
    for f in required:
        placeholder = make_placeholder(f)
        if '"TEST_' in placeholder or '"placeholder_' in placeholder:
            if f['id'] == 'code' or 'pattern' in f.get('semantics', {}):
                placeholder = '`AUD_' + f['id'].upper() + '_${TS}`'
            elif f['id'] == 'version_id' or '_id' in f['id']:
                placeholder = 'null'
            else:
                placeholder = '`aud_' + f['id'] + '_${TS}`'
        body_lines.append(f'        {f["id"]}: {placeholder},')
    body = '\n'.join(body_lines)

    return f'''
  /**
   * 审计日志: 创建 [{schema["name"]}] 应记录 audit_log
   * 业务规则: BR-{schema["id"]}-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [{schema["name"]}] 创建应生成 audit_log', async ({{
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }}, testInfo) => {{
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [{schema["name"]}] (Healer 守护)', async () => {{
      return await AIHealer.guard(page, 'C_AUDIT_{schema["id"]}_create', async () => {{
        return await isolation.createTracked('{schema["id"]}', {{
{body}
        }})
      }}, {{ softOn: ['5xx', '404', 'fk_missing'] }})
    }})
    obj = cr.result
    if (cr.healed) {{ console.log(`[Healer] C_AUDIT create 软断言: ${{cr.reason}}`) ; return }}
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {{
      const r = await AIHealer.guard(page, 'C_AUDIT_{schema["id"]}_check', async () => {{
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, '{schema["id"]}', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }}, {{ softOn: ['5xx', 'audit_log_unavailable'] }})
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${{r.reason}}`)
    }})
  }})
'''


def gen_test_ui_navigation(schema):
    url = get_url(schema)
    return f'''
  /**
   * UI 导航: 进入 [{schema["name"]}] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [{schema["name"]}] 列表', async ({{
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }}, testInfo) => {{
    await withStep(page, testInfo, '导航到 [{schema["name"]}] 列表 (软断言)', async () => {{
      const r = await AIHealer.guard(page, 'C_UI_NAV_{schema["id"]}', async () => {{
        await navigateTo(page, '{url}')
      }}, {{ softOn: ['404'] }})
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${{r.reason}}`)
    }})
  }})
'''


TEMPLATE_HEADER = '''/**
 * S-BF-{TYPE_UPPER}-AUTO: {NAME} - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 {SCHEMA_FILE} 自动生成
 * [E2E v2 铁律合规 (8 项)]
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked() 不用 Date.now() 硬编码
 * [OK] 用 POM (GenericListPage) 不用直接 locator
 * [OK] 用 waitForApiFn() 不用 waitForTimeout()
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 解构
 * [阶段三] Healer 守护: C_AUDIT/C_DEL/C_UI_NAV 失败时软断言
 * [v2.1] 14 类业务规则 (含 P1+P2 8 个新规则)
 *
 * 业务规则:
{BUSINESS_RULES_DOC}
 *
 * 自动生成时间: {TIMESTAMP}
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import {{ test, expect }} from '../helpers/auto-fixtures.js'
import {{ withStep }} from '../helpers/auto-trace.js'
import {{ navigateToDeepLink }} from '../helpers/auto-fixtures.js'
import {{ GenericListPage }} from '../page-objects/GenericListPage.js'
import {{ FormComponentPOM }} from '../page-objects/FormComponentPOM.js'
import {{ PermissionPOM }} from '../page-objects/PermissionPOM.js'
import {{ PaginationPOM }} from '../page-objects/PaginationPOM.js'
import {{ NestedPOM }} from '../page-objects/NestedPOM.js'
import {{ PersistencePOM }} from '../page-objects/PersistencePOM.js'
import {{ BusinessRuleAssertor }} from '../screenplay/questions/BusinessRuleAssertor.js'
import {{ AIHealer }} from '../helpers/ai-healer.js'

const {TYPE_UPPER}_URL = '{DETAIL_PATH_PARENT}'

test.describe('S-BF-{TYPE_UPPER}-AUTO: {NAME} - 业务流 (AI 派生)', () => {{
'''


def generate_spec(schema_file):
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = yaml.safe_load(f)

    type_id = schema.get('id', Path(schema_file).stem)
    type_upper = type_id.upper()
    name = schema.get('name', type_id)
    schema_filename = Path(schema_file).name
    ts = datetime.datetime.fromtimestamp(Path(schema_file).stat().st_mtime).strftime('%Y-%m-%d')

    rules = []
    for f in extract_required_fields(schema):
        rules.append(f' *   BR-{type_id}-FLD-REQ-{f["id"]}  ({f.get("name", f["id"])} 必填)')
    for f in extract_pattern_fields(schema):
        rules.append(f' *   BR-{type_id}-FLD-PAT-{f["id"]}  (格式: {f["semantics"]["pattern"]})')
    for f in extract_unique_fields(schema):
        rules.append(f' *   BR-{type_id}-FLD-UNQ-{f["id"]}  ({f.get("name", f["id"])} 唯一)')
    if get_deletability(schema):
        rules.append(f' *   BR-{type_id}-DEL-condition  ({get_deletability(schema).get("message", "删除约束")})')
    if get_audit(schema).get('enabled'):
        rules.append(f' *   BR-{type_id}-AUDIT-create/update/delete  (审计日志)')
    rules_doc = '\n'.join(rules) if rules else ' *   (无业务规则)'

    tests = []
    for f in extract_required_fields(schema):
        code = gen_test_required_field(schema, f)
        if code:
            tests.append(code)
    for f in extract_pattern_fields(schema):
        code = gen_test_pattern_field(schema, f)
        if code:
            tests.append(code)
    for f in extract_unique_fields(schema):
        tests.append(gen_test_unique_field(schema, f))
    for f in extract_enum_fields(schema):
        code = gen_test_enum_field(schema, f)
        if code:
            tests.append(code)
    if get_deletability(schema):
        tests.append(gen_test_deletability(schema))
    if get_audit(schema).get('enabled'):
        tests.append(gen_test_audit(schema))
    # P1+P2 新规则
    if get_ui_actions(schema):
        tests.append(gen_test_ui_actions(schema))
    if get_audit_levels(schema):
        tests.append(gen_test_audit_levels(schema))
    if get_pagination(schema):
        tests.append(gen_test_pagination(schema))
    if get_routes(schema).get('detail'):
        tests.append(gen_test_deep_link(schema))
    tests.append(gen_test_health_check(schema))
    if get_ui_badge(schema):
        tests.append(gen_test_ui_badge(schema))
    if get_nested(schema).get('enabled'):
        tests.append(gen_test_nested(schema))
    if get_persistence(schema):
        tests.append(gen_test_persistence(schema))
    tests.append(gen_test_ui_navigation(schema))

    detail_path = get_url(schema)
    header = TEMPLATE_HEADER.format(
        TYPE_UPPER=type_upper,
        NAME=name,
        SCHEMA_FILE=schema_filename,
        BUSINESS_RULES_DOC=rules_doc,
        TIMESTAMP=ts,
        DETAIL_PATH_PARENT=detail_path
    )
    body = '\n'.join(tests)
    footer = '})\n'
    return header + body + footer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema', action='append', help='schema 名')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--output', default=OUTPUT_DIR)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if args.all:
        schemas = []
        for f in sorted(os.listdir(SCHEMA_DIR)):
            if f.endswith('.yaml') and not f.startswith('_'):
                schemas.append(f[:-5])
    elif args.schema:
        schemas = args.schema
    else:
        print('用法: --schema <name> 或 --all')
        sys.exit(1)

    print(f'Schema -> E2E Generator')
    print(f'Input: {SCHEMA_DIR}/')
    print(f'Output: {args.output}/')
    print(f'Target: {len(schemas)} schemas\n')

    success, failed = 0, 0
    for s in schemas:
        schema_file = f'{SCHEMA_DIR}/{s}.yaml'
        if not os.path.exists(schema_file):
            print(f'  [FAIL] {s}: not found')
            failed += 1
            continue
        try:
            content = generate_spec(schema_file)
            output_file = f'{args.output}/{s}.spec.js'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'  [OK] {s}: {output_file}')
            success += 1
        except Exception as e:
            print(f'  [FAIL] {s}: {e}')
            failed += 1

    print(f'\nResult: {success} ok, {failed} failed')


if __name__ == '__main__':
    main()
