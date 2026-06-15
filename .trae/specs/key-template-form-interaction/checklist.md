# KeyTemplate 表单交互增强 - 验证清单

## Schema 改动验证

- [ ] `meta/schemas/business_object.yaml` L128 pattern 改为 `{service_module_code}{SEQ:2}`
- [ ] 移除 `separator: "_"` 字段
- [ ] segments 中移除 `type: separator` 段
- [ ] sequence padding 从 4 改为 2
- [ ] preview 字段从 `ORDER_SVC_0001` 改为 `PUM01`
- [ ] `python -m meta.tools.sync_schema --diff` 无报错
- [ ] `python -m meta.tools.sync_schema --dry-run` 无 DDL 变更（仅 pattern 调整）

## Service 验证

- [ ] `keyTemplateService.js` 新增 `shouldSkipSuggestionForForm` 导出
- [ ] `keyTemplateService.js` 新增 `resetKeyTemplateCode` 导出
- [ ] `applyKeyTemplateSuggestion` 接受新参数 `formDirtyFields`（可选，向后兼容）
- [ ] 当 `formDirtyFields.has('code')` 为真时返回 `skipped: 'user_edited_form'`
- [ ] 现有 15 个单测全部通过：`npm run test:unit -- keyTemplateService`
- [ ] 新增 4 个表单场景单测全部通过

## Composable 验证

- [ ] `src/composables/useKeyTemplateFormSync.js` 文件存在
- [ ] 导出 `useKeyTemplateFormSync()` 函数
- [ ] 返回 `{ formDirtyFields, markFieldDirty, resetFieldDirty, isFieldDirty, clearAll }`
- [ ] formDirtyFields 是响应式 Set
- [ ] markFieldDirty / resetFieldDirty / clearAll 触发响应式更新
- [ ] 新增 composable 单测（至少 5 个场景）

## UI 改造验证

### ObjectPageField.vue

- [ ] 新增 props: `isCodeAutoManaged`, `isFieldDirty`, `markFieldDirty`, `onCodeReset`
- [ ] code 字段（且 `isCodeAutoManaged=true`）suffix 槽位显示
- [ ] AUTO 态：显示"自动"角标
- [ ] CUSTOMIZED 态：显示"重置为自动生成"链接
- [ ] 非 code 字段不显示
- [ ] editing=false 时不显示
- [ ] 点击"重置为自动生成"调 `onCodeReset`
- [ ] SCSS: `.kt-badge--auto` 浅绿底、`.kt-reset-link` 主题色

### ObjectPageShell.vue

- [ ] 实例化 `useKeyTemplateFormSync()`
- [ ] `isCodeAutoManaged` 从 `metaObject.key_template.auto_suggest` 读取
- [ ] `handleFieldUpdate` 加 `*_id` 变化 hook
- [ ] 仅 `isNewRow=true` 时触发重建议
- [ ] 仅 `!isFieldDirty('code')` 时触发重建议
- [ ] `triggerKeyTemplateResuggest` 调 `suggestKeyTemplateCode` 并写回 formData.code
- [ ] 失败时静默 + console.warn
- [ ] `onCodeReset` 调 `resetFieldDirty('code')` + `triggerKeyTemplateResuggest`

## 业务功能验证

### 业务对象（BO）

- [ ] **F-1**: 新建 BO，列表 filter=service_module_id=X，进入表单后 code 自动填 `X01`
- [ ] **F-2**: 切换 service_module_id 到 Y，code 自动更新为 `Y01`
- [ ] **F-3**: 手动改 code 为 `MY-CUSTOM-01`，再切换 service_module，code 保持 `MY-CUSTOM-01`
- [ ] **F-4**: 手动改 code 后，suffix 显示"重置为自动生成"
- [ ] **F-5**: 点击"重置为自动生成"，code 回到新建议值（如 `Y02`）
- [ ] **F-6**: 保存时 code 非空 → 服务端不覆盖（interceptor 兜底）
- [ ] **F-7**: 保存时 code 为空 → 服务端按新 pattern 生成 `PUM01`

### 关系（REL）

- [ ] **F-8**: 新建 REL，source=ORDER，target=USER，code 自动填 `ORDER-USER-01`
- [ ] **F-9**: 切换 source/target，code 自动重算
- [ ] **F-10**: 手动改 code 后切换 source/target，code 不变
- [ ] **F-11**: 点击"重置为自动生成"，code 回到新建议值

### 详情表单 vs Inline Edit 对照

- [ ] **F-12**: Inline edit 模式（list 表格内新建）行为不变（rowDrafts 保护）
- [ ] **F-13**: 详情表单模式走 formDirtyFields 保护（新增）
- [ ] **F-14**: 两种模式可同时存在不冲突

## 兼容性验证

- [ ] 已有 BO 数据（`PUM_0001` 风格）保留不动
- [ ] 已有 REL 数据保留不动
- [ ] 现有 15 个 keyTemplateService 单测全部通过
- [ ] 现有 ObjectPage 单测全部通过
- [ ] `python d:\filework\test.py --failed` 串行验证无新增失败
- [ ] `npm run test:unit` 全部通过

## 错误处理验证

- [ ] suggestKeyTemplateCode 失败（network/500）时，code 留空，用户可手动填
- [ ] 重置时调 suggestKeyTemplateCode 失败，弹 ElMessage.warning，code 保留原值
- [ ] 无 service_module_id 时，跳过建议（沿用现有 invalid_parent 逻辑）
- [ ] service_module_code 解析失败时，跳过建议

## 性能验证

- [ ] 父对象变化触发建议是异步的，不阻塞 UI
- [ ] 多次连续切换 service_module，最后一次响应（无竞态）
- [ ] 建议响应时间 < 300ms（不感知）

## 边界场景验证

- [ ] 切换到同一 service_module（值未变），不触发重新建议
- [ ] 用户清空 code 后保存，服务端生成新值
- [ ] formDirtyFields 跨表单切换时清空（`clearAll`）
- [ ] 不存在的对象类型（无 key_template 配置）不显示 suffix

## 文档验证

- [ ] `meta/schemas/business_object.yaml` 注释更新
- [ ] `keyTemplateService.js` JSDoc 补全新函数
- [ ] `useKeyTemplateFormSync.js` JSDoc 完整
- [ ] 提交 commit message 描述本 spec 范围

---

## TBD-2 Resolution (2026-06-10): 移除 version 的 key_template

**决策**: 移除 `meta/schemas/version.yaml` 的 `key_template` 块。

**原因**:
1. version code 是有业务含义的版本名（`v1.0` / `2024-Q4` / `R2024.1`），不是 BO/REL 那样的系统枚举
2. 自动生成 `{product_code}_{SEQ:2}` (例 `SCM_01`) 与 `field.examples` (v1.0/2024Q4/R2024.1) 设计意图冲突
3. 实际数据中用户已多次手动覆盖（`V1`/`V2`），证明自动建议无价值

**验证**:
- [x] `version.yaml` 移除 `key_template` 块（保留位置为注释说明）
- [x] 创建 version 不传 `code` 应报"不能为空"（不再自动生成）
- [x] `GET /api/v2/key-template/config/version` 返回 `enabled=False`
- [x] `GET /api/v2/key-template/list-objects` 不包含 `version`
- [x] 新增 4 个回归测试 `TestVersionNoKeyTemplate` 全部通过

**附注（未做）**: `version.code` 字段的 `pattern: ^[A-Z][A-Z0-9_]*$` 同样会拒绝 `v1.0` / `2024-Q4` / `R2024.1`，与 field.examples 仍然冲突。建议后续单独处理：放宽 pattern 或更新 examples 保持一致。

## 提交验证

- [ ] 所有改动文件已 git add
- [ ] commit message 格式合规
- [ ] 关联 spec 路径写明
- [ ] `git log` 看到 commit
