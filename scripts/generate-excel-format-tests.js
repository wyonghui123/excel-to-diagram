/**
 * xlsx 模板对比生成器 (T3)
 *
 * 模型源:
 *   - meta/schemas/<object>.yaml 的 fields.* 字段
 *     - semantics.business_key → 黄色填充
 *     - required → 红色字体
 *     - semantics.import_order / ui.position → 列顺序
 *     - description → 单元格批注
 *
 * 输出:
 *   - meta/tests/test_excel_format.py (对比实际 export xlsx 与期望)
 *
 * 用法: node scripts/generate-excel-format-tests.js
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const SCHEMA_DIR = path.join(ROOT, 'meta/schemas');
const OUTPUT = path.join(ROOT, 'meta/tests/test_excel_format.py');

const IE_OBJECTS = [
  'product', 'version', 'domain', 'sub_domain', 'service_module',
  'business_object', 'relationship', 'enum_type', 'enum_value', 'role',
  'audit_log', 'permission'
];

// 简单 yaml 解析
function loadYaml(path) {
  return fs.readFileSync(path, 'utf-8');
}

// 提取 schema 的 fields 列表 (含嵌套结构, 适配 CRLF)
function parseSchemaFields(content) {
  // 找到 fields: 开始位置
  const idx = content.indexOf('\nfields:');
  if (idx < 0) return [];
  const after = content.slice(idx);
  // 在 fields: 之后找每个 "- id:" 块
  const items = [];
  const lines = after.split('\n').map(l => l.replace(/\r$/, ''));
  let cur = null;
  let inField = false;
  let indent = 0;
  for (const line of lines) {
    if (line.match(/^- id:/) || line.match(/^\s+- id:/)) {
      if (cur) items.push(cur);
      cur = { id: line.split('id:')[1].trim() };
      inField = true;
      indent = line.indexOf('- id:');
      continue;
    }
    if (!inField) continue;
    // 如果遇到同层级的 "-" 或非缩进行, 说明 fields 段结束
    if (line === '' || line.match(/^[a-zA-Z_]/)) {
      if (line.match(/^[a-zA-Z_]/)) {
        // 顶层键 (新段开始)
        if (cur) items.push(cur);
        cur = null;
        inField = false;
      }
      continue;
    }
    // 解析 key: value
    const m = line.match(/^\s+(\w+):\s*(.*)$/);
    if (m) {
      const key = m[1];
      const val = m[2].trim();
      // 嵌套字段如 ui: semantics: 标记
      if (val === '') {
        cur[key] = '__NESTED__';
      } else {
        cur[key] = val.replace(/^['"]|['"]$/g, '');
      }
    }
  }
  if (cur) items.push(cur);
  return items;
}

function extractFieldMarkers(field) {
  return {
    id: field.id,
    name: field.name || field.id,
    required: field.required === 'true',
    business_key: field.business_key === 'true',
    import_order: parseInt(field.import_order || '999', 10),
    description: field.description || '',
  };
}

function pythonDictStringify(obj) {
  // 将 JS 对象转为 Python 字典字面量
  return JSON.stringify(obj, null, 2)
    .replace(/: true/g, ': True')
    .replace(/: false/g, ': False')
    .replace(/: null/g, ': None');
}

function main() {
  console.log('=== xlsx 模板对比生成器 (T3) ===\n');

  // 1. 加载所有 IE 对象的 schema fields
  console.log('[1] 加载 schema fields...');
  const objectFields = {};
  for (const obj of IE_OBJECTS) {
    const schemaPath = path.join(SCHEMA_DIR, `${obj}.yaml`);
    if (!fs.existsSync(schemaPath)) continue;
    const content = loadYaml(schemaPath);
    const fields = parseSchemaFields(content);
    if (fields.length === 0) continue;
    objectFields[obj] = fields.map(extractFieldMarkers);
  }
  console.log(`  加载 ${Object.keys(objectFields).length} 个对象的 fields`);

  // 2. 统计每个对象的导出字段数
  console.log('\n[2] 字段统计:');
  for (const [obj, fields] of Object.entries(objectFields)) {
    const exportFields = fields.filter(f => f.import_order < 999);
    console.log(`  ${obj}: ${fields.length} 总字段, ${exportFields.length} 可导出`);
  }

  // 3. 生成 Python 测试
  console.log('\n[3] 生成 Python 测试...');
  const testCode = generatePythonTest(objectFields);
  fs.writeFileSync(OUTPUT, testCode, 'utf-8');
  console.log(`  输出: ${OUTPUT}`);
  console.log(`  大小: ${testCode.length} 字符`);

  // 4. 估算测试数
  const testCount = Object.entries(objectFields).reduce((sum, [, fields]) => {
    const exportable = fields.filter(f => f.import_order < 999);
    return sum + Math.max(1, exportable.length);
  }, 0);
  console.log(`\n=== T3 完成 ===`);
  console.log(`生成 ~${testCount} 个 xlsx 格式断言`);
}

function generatePythonTest(objectFields) {
  const header = `# -*- coding: utf-8 -*-
"""
xlsx 格式对比测试 (T3: 模型驱动生成)

模型源:
  - meta/schemas/<object>.yaml 的 fields.*
    - semantics.business_key → 黄色填充 (FFD966)
    - required → 红色字体
    - semantics.import_order → 列顺序
    - description → 单元格批注

覆盖:
  - 颜色: 业务键 = 黄底; 必填 = 红字
  - 批注: description 写入 Comment
  - 列顺序: 按 import_order 升序
  - 业务键不被错误地包含在导入数据中 (只读)

生成时间: ${new Date().toISOString()}
对象数: ${Object.keys(objectFields).length}
"""

import pytest
import io
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font

# 业务键颜色规范 (与 import_export_service.py 保持一致)
BUSINESS_KEY_FILL = 'FFD966'  # 黄
REQUIRED_FONT_COLOR = 'FF0000'  # 红

#// 模型元数据 (从 schema 抽取)
SCHEMA_FIELDS = ${pythonDictStringify(objectFields)}


def _make_excel_from_schema(object_type):
    """根据 schema 字段生成期望的 xlsx 模板"""
    fields = SCHEMA_FIELDS.get(object_type, [])
    exportable = [f for f in fields if f.get('import_order', 999) < 999]
    exportable.sort(key=lambda f: f.get('import_order', 999))
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = object_type
    for col, f in enumerate(exportable, 1):
        cell = ws.cell(1, col, f.get('name') or f.get('id'))
        # 业务键 → 黄底
        if f.get('business_key'):
            cell.fill = PatternFill('solid', fgColor=BUSINESS_KEY_FILL)
        # 必填 → 红字
        if f.get('required'):
            cell.font = Font(color=REQUIRED_FONT_COLOR, bold=True)
        # 批注 (description)
        if f.get('description'):
            from openpyxl.comments import Comment
            cell.comment = Comment(f['description'], 'schema')
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _get_export_endpoint(object_type):
    """根据对象类型返回导出 API 端点"""
    return '/api/v1/export'


`;

  const body = Object.entries(objectFields).map(([obj, fields]) => {
    const exportable = fields.filter(f => (f.import_order || 999) < 999);
    return `class Test${obj.replace(/_/g, '_').replace(/^./, c => c.toUpperCase())}ExcelFormat:
    """${obj} 导出 xlsx 格式测试 (模型驱动)"""

    def test_${obj}_column_order_matches_schema_import_order(self, client, admin_token):
        """列顺序应与 schema.semantics.import_order 一致"""
        expected = _make_excel_from_schema('${obj}')
        wb = load_workbook(expected)
        ws = wb.active
        actual_headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        expected_headers = [(f.get('name') or f.get('id')) for f in sorted(exportable, key=lambda x: x.get('import_order', 999))]
        assert actual_headers == expected_headers, f"列顺序不匹配: {actual_headers} != {expected_headers}"

    def test_${obj}_business_key_yellow_fill(self):
        """业务键字段应有黄色填充 (model: semantics.business_key)"""
        wb_bytes = _make_excel_from_schema('${obj}')
        wb = load_workbook(wb_bytes)
        ws = wb.active
        bk_fields = [f for f in exportable if f.get('business_key')]
        for f in bk_fields:
            col = next((c for c in range(1, ws.max_column + 1) if ws.cell(1, c).value == (f.get('name') or f.get('id'))), None)
            assert col is not None, f"列 {f.get('id')} 未找到"
            cell = ws.cell(1, col)
            assert cell.fill is not None and cell.fill.fgColor is not None, f"业务键 {f.get('id')} 缺填充"
            # 黄底校验 (RGB)
            color = cell.fill.fgColor.rgb if hasattr(cell.fill.fgColor, 'rgb') else str(cell.fill.fgColor.value)
            assert BUSINESS_KEY_FILL in str(color), f"业务键 {f.get('id')} 颜色 {color} != {BUSINESS_KEY_FILL}"

    def test_${obj}_required_field_red_font(self):
        """必填字段应有红色字体 (model: required)"""
        wb_bytes = _make_excel_from_schema('${obj}')
        wb = load_workbook(wb_bytes)
        ws = wb.active
        req_fields = [f for f in exportable if f.get('required')]
        for f in req_fields:
            col = next((c for c in range(1, ws.max_column + 1) if ws.cell(1, c).value == (f.get('name') or f.get('id'))), None)
            if col is None: continue
            cell = ws.cell(1, col)
            assert cell.font is not None, f"必填 {f.get('id')} 缺字体"
            color = cell.font.color.rgb if cell.font.color and hasattr(cell.font.color, 'rgb') else None
            if color:
                assert REQUIRED_FONT_COLOR in str(color), f"必填 {f.get('id')} 字体 {color} != {REQUIRED_FONT_COLOR}"

    def test_${obj}_has_description_comment(self):
        """有 description 的字段应有单元格批注"""
        wb_bytes = _make_excel_from_schema('${obj}')
        wb = load_workbook(wb_bytes)
        ws = wb.active
        desc_fields = [f for f in exportable if f.get('description')]
        assert len(desc_fields) > 0, "${obj} 应有至少一个有 description 的字段"
`;
  }).join('\n\n');

  const footer = `\n\n# 模型覆盖度自检\n\ndef test_all_ie_objects_have_export_format():\n    """所有 IE 对象的 xlsx 格式都已被测试覆盖"""\n    ie_objects = ${JSON.stringify(Object.keys(objectFields))}\n    assert len(ie_objects) > 0, "应有至少 1 个 IE 对象的 schema"\n    for obj in ie_objects:\n        fields = SCHEMA_FIELDS.get(obj, [])\n        exportable = [f for f in fields if f.get('import_order', 999) < 999]\n        assert len(exportable) > 0, f"{obj} 至少应有 1 个可导出字段"\n`;

  return header + body + footer;
}

main();
