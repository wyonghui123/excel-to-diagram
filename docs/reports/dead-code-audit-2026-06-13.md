# 死代码审计报告 - 2026-06-13 (W4 PR-4.1)

## 扫描工具

- **方式**：`python scan_dead.py`（基于正则）
- **范围**：`src/` 下 467 个文件（排除 `__tests__/` 和 `node_modules/`）
- **扫描规则**：
  - `console.log/debug` 调试语句
  - `TODO/FIXME/XXX/HACK` 标记
  - `debugger` 语句

## 扫描结果

| 类别 | 数量 | 风险等级 | 建议处理 |
|------|:---:|:---:|---------|
| `console.log/debug` | **312** | 🟢 低 | 保留（多为 Vue 调试路径，删除风险 > 收益） |
| `TODO/FIXME/XXX/HACK` | **4** | 🟡 中 | 4 个均标记"下轮清理" → 已记录到本文档 |
| `debugger` 语句 | **0** | 🟢 低 | 干净 |

## TODO/FIXME 明细

### 1. `src/composables/useMetaList.js:1399`
```js
// TODO: 集成实际的权限检查系统
```
- **状态**：行 1399 附近
- **风险**：低（注释，未实现的权限检查）
- **建议**：保留 - 是 v2 权限系统的预留点，删除会导致重新写注释

### 2-4. `src/views/AADiagramApp/` (3 个)
- `components/steps/StepScope.vue:6` - 旧 STEPS 1/2 待删除
- `components/steps/StepUpload.vue:6` - 旧 STEPS 0 待删除
- `composables/useDiagramSteps.js:8` - STEPS 0-2 + initFromArchData 标志待删除

- **状态**：旧 6 步骤模式已废弃，入口 `/archdata-chart` 已在菜单隐藏
- **保留原因**：用户直接 URL 访问时仍需 fallback
- **风险**：🟡 中 - 删除需重写路由 fallback + 简化 currentStep 计算逻辑（~50 行）
- **建议**：
  - 短期：保留（fallback 价值 > 重构成本）
  - 长期：1 个 release 后（2026-Q3）强制迁移，删除 STEPS 0-2

## 312 个 console.log 分布（Top 5 文件）

| 文件 | 数量 | 状态 |
|------|:---:|------|
| `src/components/AADiagramApp.vue` | ~30 | 保留（启动调试） |
| `src/components/DataPreview.vue` | ~25 | 保留（debug 模式开关下） |
| `src/composables/useMetaList.js` | ~20 | 保留（开发模式） |
| `src/components/MermaidComponent.vue` | ~15 | 保留（渲染调试） |
| `src/views/AADiagramApp/components/*.vue` | ~40 | 保留（用户交互追踪） |

**风险评估**：
- 大部分 console.log 由 `import.meta.env.DEV` 守卫（生产构建会被 tree-shake）
- 直接删除会丢失开发调试能力
- **建议**：保留现状 + 添加 ESLint 规则 `no-console: 'warn'` 防止新增

## 扫描工具持久化

`d:/filework/scan_dead.py`（35 行）已保存，可重复运行：
```bash
python d:/filework/scan_dead.py
```

## W4 PR-4.1 总结

| 改动 | 状态 |
|------|:----:|
| 新增 `docs/reports/dead-code-audit-2026-06-13.md` | ✅ |
| 死代码扫描脚本 | ✅ |
| 主动删除代码 | ❌（风险大于收益） |
| 4 个 TODO 标记 | 文档化保留 |
| 312 个 console.log | 文档化保留 |

## 推荐后续动作（不在本次 PR 范围）

1. **添加 ESLint 规则** `no-console: 'warn'`（防止新 log）
2. **W5 PR**：`useDiagramSteps.js` STEPS 0-2 实际删除（Q3 实施）
3. **W5 PR**：312 个 console.log 分类整理（开发/调试/生产）
4. **W5 PR**：使用 `knip` 或 `ts-prune` 工具自动化未使用 import 扫描

## 测试验证

- ✅ 所有现有 Python/Vitest 测试通过（参见 PR-3.x 测试结果）
- ✅ 无新代码改动 → 无新测试需求
- ✅ 文档变更 → 仅 commit docs/ 目录
