# KeyTemplate 表单交互增强 - 实现计划

## [ ] Task 1: Schema 改动 (BO pattern 变更)

- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 修改 `meta/schemas/business_object.yaml` L125-142
  - pattern: `{service_module_code}_{SEQ:4}` → `{service_module_code}{SEQ:2}`
  - 移除 `separator: "_"`
  - segments 中移除 separator 段
  - sequence padding: 4 → 2
  - preview: `ORDER_SVC_0001` → `PUM01`
- **Acceptance Criteria Addressed**: FR-001
- **Test Requirements**:
  - `programmatic` TR-1.1: pattern 解析正确（`python -c "import yaml; ..."`）
  - `programmatic` TR-1.2: 同步 schema 后无 DDL 变更
  - `human-judgement` TR-1.3: 启动后端后 `python -c "from meta.schemas.business_object import ..."` 验证加载
- **Notes**:
  - 已有 BO 数据（`PUM_0001` 风格）保留，不迁移
  - 不改 `key_template_interceptor.py`

## [ ] Task 2: Service 扩展 (formDirtyFields 路径)

- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 扩 `src/services/keyTemplateService.js`
  - 新增导出 `shouldSkipSuggestionForForm(codeFieldName, formDirtyFields)`
  - 新增导出 `resetKeyTemplateCode(formData, codeValue, formDirtyFields)`
  - `applyKeyTemplateSignature` 增加第 4 个可选参数 `formDirtyFields = null`
  - 当 `formDirtyFields.has('code')` 为真时返回 `skipped: 'user_edited_form'`
  - 保持向后兼容：现有调用不传 `formDirtyFields`，行为不变
- **Acceptance Criteria Addressed**: FR-002, FR-005
- **Test Requirements**:
  - `programmatic` TR-2.1: 现有 15 个单测全部通过
  - `programmatic` TR-2.2: 新增 4 个 case（formDirtyFields 路径）
    - TC-12d: formDirtyFields.has('code') 跳过
    - TC-12e: formDirtyFields 空正常应用
    - TC-12f: shouldSkipSuggestionForForm 返回 true/false
    - TC-12g: resetKeyTemplateCode 清除 dirty + 写值
- **Notes**:
  - 不修改现有函数签名
  - JSDoc 补全新函数

## [ ] Task 3: 新增 Composable

- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 新增 `src/composables/useKeyTemplateFormSync.js`
  - 导出 `useKeyTemplateFormSync()` 函数
  - 返回 `{ formDirtyFields, markFieldDirty, resetFieldDirty, isFieldDirty, clearAll }`
  - formDirtyFields 是响应式 Set
  - 触发响应式更新（新 Set 替换）
- **Acceptance Criteria Addressed**: FR-002
- **Test Requirements**:
  - `programmatic` TR-3.1: composable 单测（5 场景）
    - markFieldDirty 触发响应式
    - resetFieldDirty 触发响应式
    - isFieldDirty 正确读取
    - clearAll 清空
    - 重复 markFieldDirty 不重复添加
- **Notes**:
  - 独立 composable，无依赖
  - 可被 ObjectPageShell / ObjectPageField / 其他组件复用

## [ ] Task 4: ObjectPageField UI 改造

- **Priority**: P0
- **Depends On**: Task 3
- **Description**:
  - 改 `src/components/common/ObjectPage/ObjectPageField.vue`
  - 新增 props: `isCodeAutoManaged: boolean`, `isFieldDirty: Function`, `markFieldDirty: Function`, `onCodeReset: Function`
  - el-input 块加 `suffix` 槽位（仅 code 字段 + isCodeAutoManaged=true）
  - AUTO 态：`<span class="kt-badge kt-badge--auto">自动</span>`
  - CUSTOMIZED 态：`<a class="kt-reset-link" @click.prevent="onCodeReset">重置为自动生成</a>`
  - 用户输入时调 `markFieldDirty('code')`
  - 加 SCSS: `.kt-badge`, `.kt-badge--auto`, `.kt-reset-link`
- **Acceptance Criteria Addressed**: FR-004
- **Test Requirements**:
  - `programmatic` TR-4.1: 组件测试 (vitest + happy-dom)
    - AUTO 态渲染 "自动" 标签
    - CUSTOMIZED 态渲染 "重置" 链接
    - 点击 "重置" 触发 onCodeReset
    - 用户输入触发 markFieldDirty
    - 非 code 字段不渲染 suffix
    - editing=false 时不渲染 suffix
- **Notes**:
  - 沿用 Element Plus suffix 槽位（不引入新组件）
  - 复用项目 SCSS 变量（参考 `.kt-badge` 设计）

## [ ] Task 5: ObjectPageShell 父组件接线

- **Priority**: P0
- **Depends On**: Task 2, Task 3, Task 4
- **Description**:
  - 改 `src/components/common/ObjectPage/ObjectPageShell.vue`
  - 实例化 `useKeyTemplateFormSync()`
  - 计算属性 `isCodeAutoManaged` 从 `metaObject.key_template.auto_suggest` 读取
  - 改写 `handleFieldUpdate`：
    - 原有逻辑保留
    - 新增：当 `key.endsWith('_id') && value && isNewRow && !isFieldDirty('code')` 时调 `triggerKeyTemplateResuggest()`
  - 新增 `triggerKeyTemplateResuggest()` 函数
  - 新增 `onCodeReset()` 函数（清除 dirty + 重新建议）
  - 关闭/取消时调 `clearAll()`
  - 传给 `ObjectPageField` 的新 props 接线
- **Acceptance Criteria Addressed**: FR-003, FR-004, FR-005
- **Test Requirements**:
  - `programmatic` TR-5.1: 集成测试 (vitest)
    - service_module_id 变化触发 resuggest
    - target_bo_id 变化触发 resuggest
    - 用户已编辑 code 时不触发
    - 非 *_id 字段不触发
    - isNewRow=false 不触发
    - onCodeReset 正确清除 + 重建议
- **Notes**:
  - 失败时静默 + console.warn（避免干扰用户）
  - 防止 request race（最近一次响应为准，可选防抖）

## [ ] Task 6: Inline Edit 回归测试

- **Priority**: P0
- **Depends On**: Task 2
- **Description**:
  - 验证 `useMetaList.addNewRow` + `_suggestKeyTemplateCode` 行为不变
  - rowDrafts 保护路径不受 formDirtyFields 参数影响
  - 跑现有 `keyTemplateService.spec.js` 15 个 case
- **Acceptance Criteria Addressed**: FR-006
- **Test Requirements**:
  - `programmatic` TR-6.1: 现有 15 个单测全部通过
  - `programmatic` TR-6.2: 不传 formDirtyFields 时行为等价原版
- **Notes**:
  - `formDirtyFields` 是可选参数
  - inline 路径不传 formDirtyFields 即可

## [ ] Task 7: 端到端验证

- **Priority**: P1
- **Depends On**: All previous
- **Description**:
  - 启动后端 + 前端
  - 手动验证 6 个核心场景（F-1 到 F-6, F-8 到 F-11）
  - 用 Playwright 截图留证
- **Acceptance Criteria Addressed**: 全部 FR
- **Test Requirements**:
  - `human-judgement` TR-7.1: BO 新建 → code 自动填 `PUM01`
  - `human-judgement` TR-7.2: 切 service_module → code 重算
  - `human-judgement` TR-7.3: 手动改 code → 不被覆盖
  - `human-judgement` TR-7.4: 点 "重置" → code 回到新建议值
  - `human-judgement` TR-7.5: REL 新建 → code 自动填 `ORDER-USER-01`
  - `human-judgement` TR-7.6: 切 source/target → code 重算
- **Notes**:
  - 走 `service_manager.ps1 start`
  - 用 `python d:\filework\test.py --failed` 串行跑

## [ ] Task 8: 提交与文档

- **Priority**: P1
- **Depends On**: All previous
- **Description**:
  - git add 所有改动文件
  - git commit (待用户确认)
  - commit message 关联 spec 路径
- **Acceptance Criteria Addressed**: NFR
- **Test Requirements**:
  - `programmatic` TR-8.1: `git status` 无 untracked
  - `programmatic` TR-8.2: `git log` 看到 commit
- **Notes**:
  - 不在本次自动 commit，等用户确认
  - spec.md / checklist.md / tasks.md 一并提交

---

**任务依赖图**：

```
T1 (Schema) ─┐
T2 (Service) ─┼─→ T5 (Shell) ─→ T7 (E2E) ─→ T8 (Commit)
T3 (Compos) ─┘        ↑
                  T4 (Field) ─┘
                       │
                  T6 (Inline 回归) ─┘
```

**总工时估算**：M1 (0.5d) + M2 (1d) + M3 (0.5d) = 2 天
