# Retrospectives 索引

> **项目** excel-to-diagram  
> **目的** 沉淀 bug 修复 / 测试方法论 / 架构决策 的复盘文档  
> **命名** `YYYY-MM-DD-<topic>.md` (按时间倒序)

---

## 2026-06

| 日期 | 主题 | 文档 | 核心要点 |
|------|------|------|---------|
| 06-15 | **Mermaid 测试方法论 + 基础设施提案** | [2026-06-15-mermaid-test-methodology.md](2026-06-15-mermaid-test-methodology.md) | 三层坐标互转 / 6 个脚本演进的胜与痛 / 4 层基础设施提案 (`meta/tests/mermaid/`) / 8 条硬约束 |
| 06-15 | **SVG edge label 居中问题 (v40.6→v40.8)** | [2026-06-15-svg-edge-label-centering.md](2026-06-15-svg-edge-label-centering.md) | xMidYMid slice 陷阱 / viewport 像素 ≠ SVG 单位 / 5 条铁律 |
| 06-11 | **Edge label 截断问题** | [2026-06-11-edge-label-truncation.md](2026-06-11-edge-label-truncation.md) | 历史, edge label 截断 |

---

## 按主题分类

### 🐛 Bug 复盘
- [2026-06-15-svg-edge-label-centering.md](2026-06-15-svg-edge-label-centering.md) — 居中问题
- [2026-06-11-edge-label-truncation.md](2026-06-11-edge-label-truncation.md) — 截断问题

### 🔧 测试方法论
- [2026-06-15-mermaid-test-methodology.md](2026-06-15-mermaid-test-methodology.md) — Mermaid 图 AI 自动化测试

### 📐 架构决策
- (暂无)

---

## 模板

新复盘文档应包含:
1. **TL;DR** — 1 段话讲清问题、根因、修复、结果
2. **问题时间线** — 关键事件按时间排序
3. **根因技术细节** — 适合有技术背景的人看
4. **修复代码** — 文件:行号 + 代码片段
5. **调试方法论** — 什么有效, 什么无效
6. **测试缺口 & 改进** — 防止类似问题再发
7. **经验教训** — 跨项目适用的铁律
8. **行动项** — 立即/短期/长期
9. **相关文件清单** — 改动 + 调试脚本 + 数据快照
