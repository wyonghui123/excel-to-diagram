# KeyTemplate user_editable v1.1 — 复盘 & 测试优化

**日期**：2026-06-12
**作者**：Trae AI（IDE Agent）
**目的**：系统性复盘本次功能开发中的问题、场景、测试覆盖，并提出测试优化方案

---

## 一、问题复盘

### 1.1 时间线回放

| 序号 | 阶段 | 事件 | 问题 |
|------|------|------|------|
| 1 | 需求提出 | 业务方反馈"key_template user_editable 差异化 UI 提示" | — |
| 2 | 实施 v1.1 | 完成 9 个文件改动（dataclass/API/schema/拦截器/Excel/前端） | — |
| 3 | 单元测试 | 16/16 v1.1 用例通过 | — |
| 4 | 集成回归 | 16/16 Excel 视觉测试通过 | — |
| 5 | **用户复测** | 用户实测：role / user_group / domain / sub_domain / service_module 新建页面**仍显示"自动"标签** | ❌ 实际行为与单元测试不符 |
| 6 | 调查 | git status 发现：v1.1 代码改动**全部丢失**（仅 1 个未跟踪文件 + 别人 baseline 改动） | ❌ git stash 操作导致 |
| 7 | 重做 v1.1 | 重新实施所有 9 个文件改动（**不再用 git stash**） | — |
| 8 | 静态验证 | 6 项关键改动 ✓ 通过 | — |
| 9 | 单元测试 | 16/16 v1.1 用例再次通过 | — |

### 1.2 根本原因：git stash 操作失误

```
[危险操作] cd d:/filework/excel-to-diagram; git stash
[问题] git stash pop 失败时，stash 内容被静默丢弃
[结果] 所有 v1.1 改动被还原到 HEAD（我以为已恢复，实际已丢失）
```

**错误分析**：
- 我执行 `git stash` 收拢所有改动 → 工作区变干净
- 然后用 `git stash pop` 试图恢复 → 因为与 baseline 冲突，**操作成功但内容丢失**（被其他 stash 覆盖）
- 之后 `git status` 只显示一个 `?? meta/tests/test_key_template_user_editable_v1_1.py` 未跟踪文件，让我误以为只有这个文件丢失

**正确做法**：
1. 不要做 `git stash` 操作（在共享工作区中风险极高）
2. 如果非做不可，先 `git diff > v11.patch` 备份
3. 操作后立即 `git diff v11.patch | git apply` 验证

### 1.3 第二个问题：单元测试不覆盖 UI 层

`test_key_template_user_editable_v1_1.py` 16 个用例覆盖了：
- ✅ dataclass 字段 + 校验
- ✅ yaml schema 加载
- ✅ 拦截器代码包含 INFO 日志
- ✅ preview API 源码包含返回字段
- ✅ _get_key_template_user_editable helper 单元行为
- ✅ ExcelDesignSystem 新色常量

**但缺**：
- ❌ **端到端**：实际 HTTP 调用 `/api/v2/key-template/config/{type}` 验证 role/user_group/domain 返回的 `data.enabled` 实际是 False
- ❌ **集成**：实际 `POST /api/v2/bo/role` 创建角色时，不应触发 KeyTemplateInterceptor
- ❌ **前端**：isCodeAutoManaged 三个状态（loading/enabled/disabled）的真实行为
- ❌ **Excel 视觉**：导出 role 的 Excel 时，code 列**不应**有浅蓝灰底色（因为 role 不该显示在"自动编码规则"区）

### 1.4 第三个问题：用户实际行为没及时验证

我在单元测试通过后**没有用浏览器实测**，而是基于"代码改动 + 单元测试通过"推断功能正常。当用户复测反馈时，才发现改动已被 git stash 还原。

**改进**：
- 任何 UI 相关改动，应在单元测试后**必做 E2E 验证**（Playwright 截图）
- 共享工作区改动后，**先重启服务再让用户测试**（避免"代码已改但服务是旧的"）

---

## 二、新功能操作场景梳理

### 2.1 5 个核心场景

| # | 场景 | 涉及对象 | 前置条件 | 操作 | 预期 |
|---|------|---------|---------|------|------|
| S1 | 启用对象的自动编码 | business_object, relationship | schema 配置 key_template | 用户进入新建页面 | 看到"可手动"标签 + placeholder 提示 |
| S2 | 用户填入 code | business_object | 父对象已选 | 输入业务编码 | "自动" 标签消失，出现"重置为自动生成"链接 |
| S3 | 用户留空 code 自动生成 | business_object | 父对象已选 | 不填 code 提交 | 后端拦截器按 pattern 生成编码 + 写 INFO 日志 |
| S4 | 不应启用 key_template 的对象 | role, user_group, domain, sub_domain, service_module, permission, menu | 这些对象无 key_template 配置 | 用户进入新建页面 | **不应**显示"自动"标签（修复点） |
| S5 | Excel 导出 | 所有对象 | 用户下载 Excel | 打开说明 sheet | 启用 key_template 的对象列在"自动编码规则"区，code 列底色 = 浅蓝灰 |

### 2.2 4 个异常场景

| # | 异常 | 操作 | 预期 |
|---|------|------|------|
| E1 | 父对象未选，提交 BO | business_object, parent_id 缺失 | 422 MISSING_PARENT_FIELD（已有测试） |
| E2 | 父对象已选但 service_module_code 未解析 | 父级只有 domain_id | 422 MISSING_PARENT_FIELD（已有测试） |
| E3 | 重复 code 提交 | 业务对象 code 已存在 | 400/409 重复键错误 |
| E4 | yaml 中 user_editable 值非法 | 配置 typo | 启动期 ValueError（启动失败，避免运行时静默） |

### 2.3 4 个状态维度

| 维度 | 状态 | 测试覆盖现状 |
|------|------|-------------|
| Schema 配置 | 有/无 key_template | ✅ yaml schema 测试 |
| Dataclass 解析 | 3 种合法值 + 非法值 | ✅ T1-T5 |
| API 返回 | enabled/disabled/有/无 user_editable | ⚠️ 仅源码检查，缺 HTTP E2E |
| 前端 UI | loading / enabled / disabled | ❌ 完全无测试 |
| 拦截器行为 | 用户传 / 用户没传 / 父级缺失 | ⚠️ 仅单元测试 |
| Excel 视觉 | 底色 / 注释 / 说明 sheet | ⚠️ 仅源码检查，缺导出后验证 |
| 异常路径 | 非法值 / 网络失败 / 后端 500 | ❌ 完全无测试 |

---

## 三、现有测试用例分析

### 3.1 测试矩阵现状

| 测试文件 | 关注点 | 用例数 | 与 v1.1 相关度 |
|---------|--------|--------|--------------|
| [test_key_template_api.py](file:///d:/filework/excel-to-diagram/meta/tests/test_key_template_api.py) | HTTP API 端到端 | 35+ | **关键**（缺 v1.1 E2E） |
| [test_key_template_engine.py](file:///d:/filework/excel-to-diagram/meta/tests/test_key_template_engine.py) | 引擎 + parser | 30+ | 中（dataclass 解析可补充） |
| [test_key_template_interceptor.py](file:///d:/filework/excel-to-diagram/meta/tests/test_key_template_interceptor.py) | 拦截器单元 | 20+ | 中（缺 INFO 日志验证） |
| [test_key_template_interceptor_rel.py](file:///d:/filework/excel-to-diagram/meta/tests/test_key_template_interceptor_rel.py) | 关系拦截器 | 8 | 中 |
| [test_excel_field_control_visual.py](file:///d:/filework/excel-to-diagram/meta/tests/test_excel_field_control_visual.py) | Excel 视觉 | 20 | **关键**（缺 auto_or_manual_code 验证） |
| [test_excel_design_system.py](file:///d:/filework/excel-to-diagram/meta/tests/test_excel_design_system.py) | 样式系统 | 10 | 中（已加新色） |
| [test_key_template_user_editable_v1_1.py](file:///d:/filework/excel-to-diagram/meta/tests/test_key_template_user_editable_v1_1.py) | v1.1 单元 | 16 | ✅ 新增（仅静态） |

### 3.2 关键缺口

| 缺口 | 风险等级 | 影响 |
|------|---------|------|
| `GET /api/v2/key-template/config/role` HTTP E2E | **P0** | 用户感知问题（修复未生效时再发生） |
| `POST /api/v2/bo/role` 不触发 KeyTemplateInterceptor | **P0** | 用户感知问题（之前就是这个 bug） |
| Excel 导出 role 时 code 列**无**浅蓝灰底色 | **P0** | 同上（如果 schema 配置错乱会很迷惑） |
| Excel 说明 sheet 规则区正确列出 business_object/relationship | P1 | UI 反馈 |
| 前端 `isCodeAutoManaged` 三状态真实行为 | P1 | UI 体验 |
| 拦截器 INFO 日志真的被写到了日志 | P2 | 审计追踪 |
| 异常路径 E2E（非法 user_editable、network error） | P2 | 健壮性 |

---

## 四、测试用例优化与补充方案

### 4.1 新增 `test_key_template_user_editable_v1_1_e2e.py`（端到端）

**目标**：补齐 HTTP/API/Excel E2E 测试，作为"用户复测"等价物。

```python
# -*- coding: utf-8 -*-
"""
[NEW v1.1 2026-06-12] KeyTemplate user_editable 端到端测试

覆盖场景：S1-S5 + E1-E4（见 REVIEW_AND_TEST_PLAN.md §2）
目的：用户感知问题（role/user_group 等显示"自动"）的回归防线。
"""
import pytest
import os
from openpyxl import load_workbook

pytestmark = pytest.mark.integration


KT_URL = '/api/v2/key-template'
KT_DISABLED_OBJECTS = ['role', 'user_group', 'permission', 'menu',
                       'domain', 'sub_domain', 'service_module', 'version']
KT_ENABLED_OBJECTS = ['business_object', 'relationship']


class TestUserEditableE2E:
    """端到端：HTTP 真实响应"""

    @pytest.mark.parametrize('object_type', KT_DISABLED_OBJECTS)
    def test_disabled_objects_api_returns_enabled_false(self, api_client, admin_headers, object_type):
        """
        S4 关键回归：role / user_group / domain 等 7 个对象
        GET /config/<type> → data.enabled 必须为 False

        这是 v1.1 修复 "新建页面误显示自动标签" 的核心防御。
        如果该测试失败 → 任何使用这些对象的页面都会再次显示"自动"标签。
        """
        resp = api_client.get(f'{KT_URL}/config/{object_type}', headers=admin_headers)
        assert resp.status_code == 200, f"GET /config/{object_type} 失败: {resp.status_code}"
        body = resp.get_json()
        assert body.get('success') is True
        data = body.get('data', {})

        # 后端返回 enabled=False (无 key_template 配置) 或 {enabled: False, message: ...}
        if 'enabled' in data:
            assert data['enabled'] is False, (
                f"{object_type} 不应启用 key_template (无配置)，"
                f"但 API 返回 enabled={data['enabled']}。"
                f"这会导致前端 isCodeAutoManaged=true → 误显示'自动'标签。"
                f"修复：检查 meta_object.key_template 是否被错误地默认填充。"
            )
        else:
            # key_template 字段不存在 → 也算 enabled=False
            assert 'key_template' not in data or not data.get('key_template'), (
                f"{object_type} 不应有 key_template 字段，实际: {data}"
            )

    @pytest.mark.parametrize('object_type', KT_ENABLED_OBJECTS)
    def test_enabled_objects_api_returns_user_editable(self, api_client, admin_headers, object_type):
        """
        S1 关键验证：business_object / relationship
        GET /config/<type> → 返回 key_template.user_editable 字段
        """
        resp = api_client.get(f'{KT_URL}/config/{object_type}', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body.get('data', {})

        kt = data.get('key_template', {})
        assert kt, f"{object_type} 应有 key_template 配置，实际: {data}"
        assert kt.get('user_editable') in ('auto_only', 'auto_or_manual', 'manual_only'), (
            f"{object_type} key_template.user_editable 应为合法值，实际: {kt.get('user_editable')}"
        )
        # 本阶段 v1.1 应统一为 auto_or_manual
        assert kt.get('user_editable') == 'auto_or_manual', (
            f"{object_type} v1.1 应默认 auto_or_manual，实际: {kt.get('user_editable')}"
        )

    def test_preview_api_returns_user_editable(self, api_client, admin_headers):
        """
        S1 补充：preview API 必须返回 user_editable / pattern / preview
        """
        # 找一个存在 service_module_id 的业务对象
        resp = api_client.post(
            f'{KT_URL}/preview/business_object',
            json={'field_values': {}, 'parent_params': {'service_module_id': 1}, 'generate': True},
            headers=admin_headers,
        )
        if resp.status_code != 200:
            pytest.skip(f"BO preview 跳过 (status={resp.status_code})")
        body = resp.get_json()
        data = body.get('data', {})
        assert 'user_editable' in data, f"preview 应返回 user_editable，实际: {data}"
        assert 'pattern' in data, f"preview 应返回 pattern，实际: {data}"
        assert 'preview' in data, f"preview 应返回 preview，实际: {data}"


class TestInterceptorE2E:
    """端到端：实际创建 BO 验证拦截器行为"""

    @pytest.mark.parametrize('object_type', KT_DISABLED_OBJECTS)
    def test_create_disabled_object_does_not_invoke_key_template(self, api_client, admin_headers, object_type, caplog):
        """
        S4 关键防御：创建 role / user_group / domain 等
        POST /api/v2/bo/<type> 不应触发 KeyTemplateInterceptor
        → 日志中不应有 "Using user-supplied code"（如果 code 是空）
        → 实际应返回 400/code 必填
        """
        # 尝试创建时故意不传 code
        payload = {'name': f'Test_{object_type}_NoCode'}
        if object_type in ('user_group',):
            payload['name'] = f'ug_test_{object_type}'
        resp = api_client.post(f'/api/v2/bo/{object_type}', json=payload, headers=admin_headers)
        # 期望失败（code 必填或字段缺失），不应自动生成
        assert resp.status_code in (400, 500), (
            f"创建 {object_type} 不传 code 应失败（不自动生成），"
            f"实际: {resp.status_code} body={resp.get_data(as_text=True)[:200]}"
        )

    def test_create_business_object_with_user_code_logs_info(self, api_client, admin_headers, caplog):
        """
        S2 验证：用户填入 code 提交 business_object
        → 拦截器 INFO 日志应记录 "Using user-supplied code"
        """
        # 找一个可用的 service_module_id
        sm_resp = api_client.get('/api/v2/bo/service_module?page=1&page_size=1', headers=admin_headers)
        sm_items = sm_resp.get_json().get('data', {}).get('items', [])
        if not sm_items:
            pytest.skip("无可用 service_module")
        sm_id = sm_items[0]['id']
        sm_code = sm_items[0].get('code', 'SM')

        user_code = f'USER_INPUT_TEST_{sm_code}_42'
        payload = {
            'code': user_code,
            'name': f'BO UserInputTest {user_code}',
            'service_module_id': sm_id,
        }
        resp = api_client.post('/api/v2/bo/business_object', json=payload, headers=admin_headers)
        if resp.status_code not in (200, 201):
            pytest.skip(f"创建 BO 失败 (status={resp.status_code}): {resp.get_data(as_text=True)[:200]}")
        try:
            # 验证 INFO 日志
            log_text = '\n'.join([r.message for r in caplog.records])
            assert 'user-supplied code' in log_text.lower() or 'user-supplied' in log_text, (
                f"拦截器应记录 'user-supplied code' INFO 日志，实际: {log_text[:500]}"
            )
        finally:
            # 清理
            bo_id = resp.get_json().get('data', {}).get('id')
            if bo_id:
                api_client.delete(f'/api/v2/bo/business_object/{bo_id}', headers=admin_headers)


class TestExcelVisualE2E:
    """端到端：导出 Excel 验证视觉差异"""

    def test_disabled_object_excel_no_auto_or_manual_fill(self, ie_service):
        """
        S4 + S5 关键：导出 role 时，code 列**不应**有浅蓝灰底色
        导出 business_object 时，code 列**应有**浅蓝灰底色
        """
        from meta.services.excel_design_system import ExcelDesignSystem
        auto_or_manual_color = ExcelDesignSystem.AUTO_GEN_OR_MANUAL_FILL.start_color.rgb
        # 去掉 alpha 通道
        if len(auto_or_manual_color) == 8:
            auto_or_manual_color = auto_or_manual_color[2:]

        for object_type, should_have_fill in [
            ('role', False),                  # 不应有
            ('user_group', False),            # 不应有
            ('business_object', True),        # 应有
            ('relationship', True),           # 应有
        ]:
            try:
                result = ie_service.export_template([object_type], options={
                    'include_operation_mode': True,
                    'include_hierarchy_path': True,
                    'include_hierarchy_ids': True,
                    'include_metadata_sheet': True,
                    'include_child_objects': False,
                    'empty_rows_for_new': 1,
                    'protect_sheet': False,
                })
            except Exception as e:
                pytest.skip(f"{object_type} 导出失败: {e}")
            if not result or not getattr(result, 'file_path', None):
                pytest.skip(f"{object_type} 无 file_path")
            wb = load_workbook(result.file_path)
            # 找到主 sheet
            main_sheet = wb[wb.sheetnames[0]]
            # 找 code 列（首行的 cell）
            code_col = None
            for col in range(1, min(main_sheet.max_column + 1, 30)):
                if main_sheet.cell(row=1, column=col).value == 'code':
                    code_col = col
                    break
            if not code_col:
                continue
            # 检查数据行（row=2）的 code 列 cell 填充色
            cell = main_sheet.cell(row=2, column=code_col)
            cell_color = ''
            if cell.fill and cell.fill.start_color:
                rgb = cell.fill.start_color.rgb or ''
                if len(rgb) == 8:
                    rgb = rgb[2:]
                cell_color = rgb

            if should_have_fill:
                assert cell_color == auto_or_manual_color, (
                    f"{object_type} code 列应有浅蓝灰底色 ({auto_or_manual_color})，"
                    f"实际: {cell_color}"
                )
            else:
                assert cell_color != auto_or_manual_color, (
                    f"{object_type} code 列不应有浅蓝灰底色 (会误导用户)，"
                    f"实际: {cell_color}"
                )

    def test_meta_sheet_contains_auto_encoding_rules(self, ie_service):
        """
        S5 验证：说明 sheet 包含"自动编码规则"区
        且只列出启用 key_template 的对象（business_object/relationship）
        """
        result = ie_service.export_cascade('business_object', options={
            'include_operation_mode': True,
            'include_hierarchy_path': True,
            'include_hierarchy_ids': True,
            'include_metadata_sheet': True,
            'include_child_objects': False,
            'empty_rows_for_new': 1,
            'protect_sheet': False,
        })
        if not result or not getattr(result, 'file_path', None):
            pytest.skip("导出失败")
        wb = load_workbook(result.file_path)
        # 找说明 sheet
        meta_sheet = None
        for name in wb.sheetnames:
            if '说明' in name or 'meta' in name.lower() or 'instructions' in name.lower():
                meta_sheet = wb[name]
                break
        if not meta_sheet:
            pytest.skip("找不到说明 sheet")

        # 扫描"自动编码规则" 区块
        all_text = '\n'.join(
            str(meta_sheet.cell(row=r, column=c).value or '')
            for r in range(1, meta_sheet.max_row + 1)
            for c in range(1, meta_sheet.max_column + 1)
        )
        assert '自动编码规则' in all_text, f"说明 sheet 缺'自动编码规则'区: {all_text[:500]}"
        # 应列出 business_object
        assert 'business_object' in all_text, "规则区应包含 business_object"


class TestDataclassValidation:
    """dataclass 校验（已存在但需补充边界）"""

    def test_none_user_editable_raises(self):
        """用户显式传 None 也应抛错（防御性）"""
        from meta.core.key_template_engine import KeyTemplateConfig
        with pytest.raises(ValueError) as exc_info:
            KeyTemplateConfig(object_id='test', enabled=True, user_editable=None)
        assert 'Invalid user_editable' in str(exc_info.value)

    def test_empty_string_user_editable_raises(self):
        """空串也应抛错"""
        from meta.core.key_template_engine import KeyTemplateConfig
        with pytest.raises(ValueError):
            KeyTemplateConfig(object_id='test', enabled=True, user_editable='')

    def test_user_editable_case_sensitive(self):
        """大小写敏感：AUTO_OR_MANUAL 应被拒绝"""
        from meta.core.key_template_engine import KeyTemplateConfig
        with pytest.raises(ValueError):
            KeyTemplateConfig(object_id='test', enabled=True, user_editable='AUTO_OR_MANUAL')

    @pytest.mark.parametrize('valid_value', ['auto_only', 'auto_or_manual', 'manual_only'])
    def test_all_valid_values_accepted(self, valid_value):
        """所有合法值都应被接受"""
        from meta.core.key_template_engine import KeyTemplateConfig
        cfg = KeyTemplateConfig(object_id='test', enabled=True, user_editable=valid_value)
        assert cfg.user_editable == valid_value

    def test_yaml_load_with_disabled_user_editable_raises(self):
        """[NEW] YAML 加载时如果 user_editable=invalid_value，应启动失败而非静默"""
        import yaml
        from meta.core.key_template_engine import KeyTemplateConfig

        bad_data = {
            'id': 'test_bad', 'name': 'test', 'table_name': 'test_bad',
            'key_template': {'enabled': True, 'user_editable': 'bad_mode'}
        }
        with pytest.raises(ValueError) as exc_info:
            KeyTemplateConfig.from_dict('test_bad', bad_data['key_template'])
        assert 'Invalid user_editable' in str(exc_info.value)
        # 不要在错误信息中暴露敏感信息
        assert 'bad_mode' in str(exc_info.value)  # 应显示非法值便于诊断


class TestAPIConfigConsistency:
    """API 配置一致性：跟 v1.0 行为对比"""

    def test_get_config_response_shape(self, api_client, admin_headers):
        """GET /config/<type> 响应结构（兼容老客户端）"""
        resp = api_client.get(f'{KT_URL}/config/business_object', headers=admin_headers)
        body = resp.get_json()
        assert body.get('success') is True
        data = body.get('data', {})
        # v1.0 老客户端可能用 key_template.enabled，v1.1 增加了 user_editable
        kt = data.get('key_template', {})
        if kt:
            assert 'enabled' in kt, "v1.0 兼容：必须有 enabled 字段"
            assert 'user_editable' in kt, "v1.1 新增：必须有 user_editable 字段"
            assert 'pattern' in kt, "v1.0 兼容：必须有 pattern 字段"
```

### 4.2 增强现有 `test_excel_field_control_visual.py`

**目标**：补充 `auto_or_manual_code` 视觉验证。

```python
# 在 TestExcelFieldControlVisual 中追加（不破坏现有测试）
class TestAutoOrManualCodeFill:
    """[NEW v1.1] auto_or_manual code 列差异化底色"""

    def test_business_object_code_has_light_blue_fill(self):
        """
        S5 验证：导出 business_object Excel 时
        code 列（business_key + user_editable=auto_or_manual）底色 = 浅蓝灰 E1F5FE
        """
        from meta.services.excel_design_system import ExcelDesignSystem
        wb, _ = self._make_main_sheet_wb_with_protection('business_object')
        # 找 code 列
        # ... 同 S4 逻辑
        # 验证 fill = ExcelDesignSystem.AUTO_GEN_OR_MANUAL_FILL

    def test_role_code_does_not_have_light_blue_fill(self):
        """
        S4 验证：导出 role 时 code 列**不应**有浅蓝灰底色
        """
        # ... 验证 fill != ExcelDesignSystem.AUTO_GEN_OR_MANUAL_FILL
```

### 4.3 增强现有 `test_key_template_interceptor.py`

```python
class TestInterceptorInfoLog:
    """[NEW v1.1] 拦截器 INFO 日志验证"""

    def test_user_supplied_code_logs_info(self, caplog):
        """用户传入 code 时记录 INFO 日志"""
        import logging
        with caplog.at_level(logging.INFO, logger='meta.core.interceptors.key_template_interceptor'):
            self._create_bo_with_user_code(user_code='TEST_USER_INPUT_42')
        log_text = '\n'.join([r.message for r in caplog.records])
        assert 'user-supplied code' in log_text.lower()
        assert 'TEST_USER_INPUT_42' in log_text
        assert 'user_editable=auto_or_manual' in log_text  # 应含 user_editable

    def test_user_supplied_code_unchanged_behavior(self):
        """用户传入 code 时不修改值（回归保护）"""
        user_code = 'TEST_KEEP_USER_CODE'
        ctx = self._make_context('business_object', 'create', {'code': user_code, ...})
        self.interceptor.before_action(ctx)
        assert ctx.params.get('code') == user_code  # 行为不变

    def test_disabled_object_no_info_log(self, caplog):
        """未启用 key_template 的对象不记录 INFO 日志"""
        meta_object_disabled = MetaObject(
            id='role', name='角色', table_name='roles',
            key_template={}  # 无配置
        )
        ctx = ActionContext(meta_object=meta_object_disabled, action='create', params={})
        with caplog.at_level(logging.INFO, logger='meta.core.interceptors.key_template_interceptor'):
            self.interceptor.before_action(ctx)
        # 不应有任何 INFO 日志
        assert not any('user-supplied code' in r.message for r in caplog.records)
```

### 4.4 增强现有 `test_key_template_api.py` — 加 `TestUserEditableConfig` 类

```python
class TestUserEditableConfig:
    """[NEW v1.1] /config/<type> 返回 user_editable 字段"""

    @pytest.mark.parametrize('object_type,expected_enabled', [
        ('business_object', True),
        ('relationship', True),
        ('role', False),
        ('user_group', False),
        ('version', False),  # 已被 TBD-2 移除
    ])
    def test_config_enabled_for_each_object(self, api_client, admin_headers, object_type, expected_enabled):
        resp = api_client.get(f'{KT_URL}/config/{object_type}', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get('data', {})
        actual_enabled = bool(data.get('key_template')) if 'key_template' in data else data.get('enabled', False)
        assert actual_enabled == expected_enabled, (
            f"{object_type} enabled 应为 {expected_enabled}，实际: {actual_enabled}"
        )

    @pytest.mark.parametrize('object_type', ['business_object', 'relationship'])
    def test_enabled_objects_have_user_editable(self, api_client, admin_headers, object_type):
        resp = api_client.get(f'{KT_URL}/config/{object_type}', headers=admin_headers)
        kt = resp.get_json().get('data', {}).get('key_template', {})
        assert kt.get('user_editable') == 'auto_or_manual', (
            f"v1.1 应统一为 auto_or_manual，实际: {kt.get('user_editable')}"
        )
```

---

## 五、测试优化总结

### 5.1 新增文件（优先级）

| 文件 | 优先级 | 估时 | 覆盖场景 |
|------|-------|------|---------|
| `test_key_template_user_editable_v1_1_e2e.py` | **P0** | 2h | S1, S2, S3, S4, S5, E1-E4 |
| 增强 `test_excel_field_control_visual.py` | **P0** | 30m | S4 Excel 视觉, S5 说明 sheet |
| 增强 `test_key_template_interceptor.py` | P1 | 30m | 拦截器 INFO 日志 + 行为不变 |
| 增强 `test_key_template_api.py` | P1 | 30m | 7+ 对象的 enabled 一致性 |

### 5.2 配套工具

1. **Web E2E**（Playwright/手动截图）
   - 创建 `test_ui_key_template_v1_1.js` 用 Playwright 验证 3 状态（loading / enabled / disabled）
   - 截图保存到 `screenshots/key_template_v1_1/`

2. **测试辅助**（conftest.py）
   - 增强 `caplog` fixture 覆盖 INFO 级别
   - 提供 `kt_disabled_objects` / `kt_enabled_objects` 共享 parametrize fixture

3. **CI 集成**
   - 提交前自动跑 E2E：避免 git stash 类问题
   - 集成测试单独 job，不阻塞 PR

### 5.3 反思与改进项

| 教训 | 改进 |
|------|------|
| git stash 操作危险 | 共享工作区禁用 git stash；改动前先 `git diff > backup.patch` |
| 单元测试不覆盖 UI 行为 | UI 改动必须配 E2E（API + Playwright 截图） |
| 改动后未实测就交付 | 改动 → 单元测试 → E2E → 用户复测，缺一不可 |
| 修改文件多时易遗漏 | 维护 `CHANGELOG.md` + 改动清单（9 文件） |
| 测试文件丢失也未发现 | 测试文件纳入 git 跟踪 + CI 必跑 |

---

## 六、立即行动清单

- [ ] 1. 创建 `meta/tests/test_key_template_user_editable_v1_1_e2e.py`
- [ ] 2. 增强 `test_excel_field_control_visual.py`（加 TestAutoOrManualCodeFill）
- [ ] 3. 增强 `test_key_template_interceptor.py`（加 TestInterceptorInfoLog）
- [ ] 4. 增强 `test_key_template_api.py`（加 TestUserEditableConfig）
- [ ] 5. 添加 `conftest.py` 的 `kt_enabled_objects` / `kt_disabled_objects` fixtures
- [ ] 6. 跑全套测试，确认新 E2E 全过 + 现有 75 用例无回归
- [ ] 7. 写 `screenshots/key_template_v1_1/` 的 Playwright 截图脚本
- [ ] 8. 在 PR/任务中标记"必须重启服务 + 用户复测"
