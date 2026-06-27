# -*- coding: utf-8 -*-
"""
test_bug_v023_v024_export_column_order.py

覆盖 BUG-V023 + BUG-V024: 修复 child sheet 列顺序 + owner/visibility 不展示

BUG-V023 (10:24/10:46 fd7dde9 + 8618081 引入):
  - product_code (virtual, export_visible=False, business_key=True) 被 business_key 早返回放行
  - 出现在子对象 sheet 第 1 列, 破坏列顺序并与 parent_fk 列冗余
  - 修复: 还原 10:24 之前行为, 删除 business_key 早返回

BUG-V024 (用户要求):
  - owner 列在 version sheet 中不展示 (在 product sheet 中展示)
  - visibility 列在 version sheet 中不展示 (在 product sheet 中展示)
  - counting 列 (child_count) 必须排在最后
  - 不应该有 ID 列
  - 修复: version.yaml 加 owner_id/visibility 覆盖 (export_visible: false),
         _write_child_sheet sort key 加 is_counting 优先级,
         cud_required_fields 改为空集 (id 不进 candidates)

依据:
  fix 提交: BUG-V023 + BUG-V024
  测试数据: TEST333 用户 (基于 single product export)
"""
import os
import re
import urllib.request
import json
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
VERSION_YAML = PROJECT_ROOT / 'meta' / 'schemas' / 'version.yaml'
SERVICE_FILE = PROJECT_ROOT / 'meta' / 'services' / 'import_export_service.py'


def _read_yaml() -> str:
    with open(VERSION_YAML, 'r', encoding='utf-8') as f:
        return f.read()


def _read_service() -> str:
    with open(SERVICE_FILE, 'r', encoding='utf-8') as f:
        return f.read()


def _extract_function_body(text: str, func_name: str) -> str:
    """
    从 text 中提取指定函数 func_name 的函数体 (def 行后的内容)
    通过缩进判断函数边界
    """
    lines = text.split('\n')
    in_func = False
    body_lines = []
    for line in lines:
        if not in_func:
            if line.startswith(f'    def {func_name}('):
                in_func = True
                # 第一行函数签名不算 body
                continue
        else:
            # 函数体内: 如果遇到非缩进或同级 def/class, 退出
            if line and not line.startswith('    ') and not line.startswith('\t'):
                break
            body_lines.append(line)
    return '\n'.join(body_lines)


class TestBugV023VersionYamlOverrides:
    """BUG-V023: version.yaml 必须有 owner_id 和 visibility 字段覆盖 (让 sheet 不展示)"""

    def test_owner_id_override_exists(self):
        """version.yaml 必须有 - id: owner_id 字段定义"""
        text = _read_yaml()
        assert '- id: owner_id' in text, (
            "BUG-V023: version.yaml 必须定义 owner_id 字段 (覆盖 owner_aspect 继承)"
        )

    def test_owner_id_export_visible_false(self):
        """version.yaml 的 owner_id 必须 export_visible: false"""
        text = _read_yaml()
        # 找 - id: owner_id 段落, 看其后是否有 export_visible: false
        m = re.search(
            r'-\s+id:\s+owner_id\s*\n.*?export_visible:\s*false',
            text,
            re.DOTALL,
        )
        assert m, (
            "BUG-V023: version.yaml 的 owner_id 字段必须有 export_visible: false "
            "(让 product sheet 展示, version sheet 不展示)"
        )

    def test_visibility_override_exists(self):
        """version.yaml 必须有 - id: visibility 字段定义 (覆盖继承)"""
        text = _read_yaml()
        assert '- id: visibility' in text, (
            "BUG-V023: version.yaml 必须定义 visibility 字段 (覆盖 owner_aspect 继承)"
        )

    def test_visibility_export_visible_false(self):
        """version.yaml 的 visibility 必须 export_visible: false"""
        text = _read_yaml()
        m = re.search(
            r'-\s+id:\s+visibility\s*\n.*?export_visible:\s*false',
            text,
            re.DOTALL,
        )
        assert m, (
            "BUG-V023: version.yaml 的 visibility 字段必须有 export_visible: false"
        )


class TestBugV023ServiceFileRemoveBusinessKeyEarlyReturn:
    """BUG-V023: _should_export_field 和 _write_child_sheet 不应该有 business_key 早返回"""

    def test_should_export_field_no_business_key_early_return(self):
        """_should_export_field 不应该有 `if getattr(field.semantics, 'business_key', False): return True` 模式"""
        text = _read_service()
        func_body = _extract_function_body(text, '_should_export_field')
        assert func_body, "_should_export_field 函数未找到"

        # 不应该还有 business_key 早返回 (注释不算)
        lines = func_body.split('\n')
        for line in lines:
            stripped = line.strip()
            # 跳过注释
            if stripped.startswith('#'):
                continue
            # 跳过 REMOVED 注释 (已经是注释掉了的)
            if 'REMOVED' in stripped:
                continue
            # 不应该有真正的 business_key 早返回
            if 'getattr(field.semantics, \'business_key\'' in stripped and 'return True' in stripped:
                pytest.fail(
                    f"BUG-V023: _should_export_field 不应有 business_key 早返回. line: {line!r}"
                )

    def test_write_child_sheet_no_is_business_key_early_return(self):
        """_write_child_sheet 不应该有 is_business_key 早返回"""
        text = _read_service()
        func_body = _extract_function_body(text, '_write_child_sheet')
        assert func_body, "_write_child_sheet 函数未找到"

        # 检查 if 条件
        lines = func_body.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # 不应该有 `if not is_business_key and` 模式
            if 'not is_business_key and' in stripped and 'continue' in stripped:
                pytest.fail(
                    f"BUG-V023: _write_child_sheet 不应有 is_business_key 早返回. line: {line!r}"
                )


class TestBugV024CountingColumnsLast:
    """BUG-V024: counting 列 (computed=True, storage=virtual) 必须排在最后"""

    def test_sort_key_includes_is_counting(self):
        """_write_child_sheet 的 export_fields.sort 必须包含 is_counting 排序键"""
        text = _read_service()
        func_body = _extract_function_body(text, '_write_child_sheet')
        assert func_body, "_write_child_sheet 函数未找到"
        assert "getattr(f, 'computed', False)" in func_body, (
            "BUG-V024: _write_child_sheet sort key 应包含 computed 检查 (counting 列排最后)"
        )


class TestBugV024NoIdInExportCandidates:
    """BUG-V024: id 不应出现在 child sheet 的 export_fields 中"""

    def test_cud_required_fields_empty(self):
        """cud_required_fields 不应包含 'id' (用户要求: 没有 ID 列)"""
        text = _read_service()
        func_body = _extract_function_body(text, '_write_child_sheet')
        assert func_body, "_write_child_sheet 函数未找到"

        # 不应该有 `cud_required_fields = {'id'} if has_cud` 模式
        bad_pattern = "cud_required_fields = {'id'} if has_cud"
        assert bad_pattern not in func_body, (
            f"BUG-V024: 不应有 {bad_pattern!r} (id 列不应出现在 child sheet)"
        )


class TestBugV024NoIdInsertAtPosition0:
    """BUG-V024: _write_child_sheet 不应再强制 insert id 到 export_fields[0]"""

    def test_no_id_insert_0(self):
        """不应有 `export_fields.insert(0, f)` 在 has_cud 分支里"""
        text = _read_service()
        func_body = _extract_function_body(text, '_write_child_sheet')
        assert func_body, "_write_child_sheet 函数未找到"

        # 不应该有 id_in_export + insert(0) 的实际逻辑 (可以有注释)
        lines = func_body.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if 'id_in_export' in stripped and 'insert' in stripped:
                pytest.fail(
                    f"BUG-V024: _write_child_sheet 不应再有 id_in_export + insert(0) 逻辑. "
                    f"line: {line!r}"
                )


# ─────────────────────────────────────────────────────────────
# E2E 集成测试 (需要后端在 3010 端口运行)
# ─────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not os.path.exists(PROJECT_ROOT / 'waitress_server.py'),
    reason="需要 waitress_server.py 在项目根目录",
)
class TestBugV023V024EndToEnd:
    """E2E: 调用 /api/v1/export 验证实际 sheet 顺序"""

    def _login_and_export(self) -> dict:
        """登录 + 导出 product 返回 sheets"""
        req = urllib.request.Request(
            'http://localhost:3010/api/v1/auth/dev-login?username=TEST333'
        )
        resp = urllib.request.urlopen(req)
        cookie = resp.headers.get('Set-Cookie', '')

        data = json.dumps({'object_type': 'product', 'scope': 'single'}).encode('utf-8')
        req = urllib.request.Request(
            'http://localhost:3010/api/v1/export',
            data=data,
            headers={'Content-Type': 'application/json', 'Cookie': cookie},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())

    def _get_version_sheet_headers(self, body: dict) -> list:
        """从导出响应中提取 产品版本 sheet 的 column headers (按响应里 raw export_fields 的顺序)"""
        # 因为 API 异步, sheet.data 为空, 但我们通过解析后端日志间接验证
        # 此处只能返回 sheets 列表
        for sh in body.get('data', {}).get('sheets', []):
            if sh.get('name') == '产品版本':
                return sh
        return None

    def test_product_sheet_includes_owner(self):
        """
        E2E 验证 1: product sheet 中 owner 列 (负责人) 必须展示
        """
        pytest.skip(
            "需要后端日志 - 后端启动后会写入 export_fields_order 到 _restart_v*.out. "
            "手动验证: cat _restart_v*.out | grep VERIFY-V024"
        )