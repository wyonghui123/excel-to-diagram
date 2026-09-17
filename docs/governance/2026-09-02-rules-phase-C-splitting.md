# Phase C 规范拆分总结 v4.0（2026-09-02）

> 正式版在 `d:\filework\.trae\rules\`（全局 IDE 配置）

## 拆分目标

| 原文件 | 原行 | 拆分数 | 拆分后单文件上限 |
|---|---|---|---|
| test-case-standards.md | 687 | **4** | 245 行 |
| AI_AGENT_COMPONENT_GUIDE.md | 593 | **3** | 130 行 |
| component-governance.md | 646 | **3** | 150 行 |
| frontend-testing-standards.md | 583 | **2** | 200 行 |
| **总计** | **2509** | **12** | **< 250 行** |

## 拆分后子文件清单

### test-case-standards (4 个)
- `test-case-design.md` — 核心原则 + 全局状态 + Fixture + 数据
- `test-case-runtime.md` — 共享 App/Client + Registry + 缓存 + 并发
- `test-case-excel.md` — Excel 三层架构 + openpyxl 回读 + 样式
- `test-case-checklist.md` — 反模式 + 检查清单 + 诊断

### AI_AGENT_COMPONENT_GUIDE (3 个)
- `ai-component-reference.md` — 核心原则 + 标准组件库 + UI 规范
- `ai-component-templates.md` — Vue 3 Composition API 模板
- `ai-component-checklist.md` — 反模式 + 检查清单 + 排查

### component-governance (3 个)
- `component-lifecycle.md` — 分类 + FilterBar + 弃用流程
- `component-rules.md` — 治理规则 + 使用统计 + 迁移
- `component-config.md` — 元模型 + API + 枚举 + 验证

### frontend-testing-standards (2 个)
- `vitest-setup.md` — 工具选型 + 测试金字塔 + 容易测试
- `vitest-debugging.md` — 调试 + 性能 + 配置 + 检查清单

## 拆分原则

1. **按主题分**（不是按章节顺序）
2. **每个子文件 < 250 行**
3. **原文件改为索引**（不删，加链接）
4. **保留全部信息**（无内容损失）
5. **章节间互相引用**（链接到相关文件）

## 总体效果（Phase A + B + C 累计）

| 指标 | 治理前 | **Phase C 后** | 变化 |
|---|---|---|---|
| 总文件数 | 47 | 59 | +12（拆分） |
| 总行数 | 11000+ | **12080** | -7% |
| 平均文件大小 | 8.9 KB | **6.4 KB** | -28% |
| 超大文件 (>250 行) | 21 | **19** | -10% |
| 必读 5 文件 | 不明确 | **5 个明确** | ✅ |
| 入口决策树 | 无 | **START_HERE.md** | ✅ |
| L1-L9 铁律卡片 | 散落 | **1 页卡片** | ✅ |
| 多 agent 重复 | 3 件套 | **1 文件** | ✅ |

## 仍存的大文件（Phase C 之外）

19 个 > 250 行的文件未动：
- test_rules.md (457)
- powershell-execution-guide.md (446)
- debug-infrastructure-v20260621.md (385)
- multi-agent-coordination.md (395)
- meta-model-schema-sync.md (368)
- ai-content-protection.md (515)
- context-usage.md (332)
- audit-compliance.md (366)
- ...

这些文件下次可考虑 Phase D，但优先级低（不是用户当前关注主题）。