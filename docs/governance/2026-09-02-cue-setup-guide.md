# Trae CUE 启用指南 (v5.5)

> **日期**: 2026-09-02
> **触发**: v5.5 深度研究 §5.3 建议启用 CUE 智能导入/重命名
> **范围**: excel-to-diagram 项目（Python + Vue/TypeScript）

---

## 1. CUE 是什么

[CUE](https://docs.trae.cn/ide/cue) = Context Understanding Engine，Trae IDE 的智能代码补全引擎。

### 4 大功能

| 功能 | 说明 | 适用语言 |
|------|------|---------|
| **代码补全** | 上下文理解 + 自动续写 | 全部 |
| **多行修改** | 批量修改 | 全部 |
| **修改点预测** | 预测下一个修改位置 | 全部 |
| **修改点跳转** | Tab 跳转修改点 | 全部 |
| **Cue-Pro** | 仓库级链式补全 | 全部 |
| **智能导入** | 自动识别并导入依赖 | **Python / TypeScript / Golang** |
| **智能重命名** | 跨文件重命名 | **Python / TypeScript / Golang** |

### 项目契合度

| 语言 | 用量 | 受益 |
|------|------|------|
| **Python** | ⭐⭐⭐⭐⭐ (Flask 后端) | **高** — 智能导入/重命名 |
| **TypeScript** | ⭐⭐⭐⭐ (Vue 前端) | **高** — 智能导入/重命名 |
| **Golang** | ⭐ (无) | — |

---

## 2. 启用步骤（用户 IDE 操作）

### 2.1 基础开关

1. **设置** → **CUE** → **Tab-Cue**（全局开关）
2. 打开后智能导入/重命名自动启用

### 2.2 Cue-Pro 开关

- **IDE 模式**：左侧资源管理器 → Cue-Pro 视图 → `···` → 开关
- **SOLO 模式**：工具面板 → 编辑器 → Cue-Pro 视图 → `···` → 开关

### 2.3 智能导入/重命名

- 与 Tab-Cue 同开关
- 关闭 Tab-Cue → 智能导入/重命名同步关闭

### 2.4 快捷键（Windows）

| 操作 | 快捷键 |
|------|--------|
| 跳转修改点 | `Tab` |
| 完整接受建议 | `Tab` |
| 逐字接受 | `Ctrl + →` |
| 拒绝建议 | `Esc` |
| 预览采纳 | `Alt` |
| Cue-Pro 视图 | `Shift + Win + C` |
| 下一变更 | `Alt + ↓` |
| 上一变更 | `Alt + ↑` |

### 2.5 休眠机制

- 右下角 CUE 图标 → 休眠（5/15/60 分钟）
- 适合"专注写代码不想被打扰"场景

---

## 3. 项目适配建议

### 3.1 立即可用

- **Python 后端**：`app/api/`, `excel-backend/` 模块多 → 智能导入能显著加速
- **Vue 前端**：`.vue` 文件中的 `<script setup lang="ts">` → 智能导入受益

### 3.2 需要预处理

- **代码索引必须构建**（设置 → 索引与文档 → Build）→ 否则 Cue-Pro 无法理解仓库
- **项目文件数**：项目 ~ 5000 个文件左右 → **超出 5000 阈值**，需手动 Build

### 3.3 .ignore 配置（已 v5.4.1 完成）

- `.trae/.ignore` 已配置（v5.4.1 实施）
- 包含 `__pycache__/`、`node_modules/`、`*.db`、`screenshots/` 等
- CUE 索引构建时已生效

---

## 4. 与 Subagent 配合

| 场景 | Subagent | CUE 角色 |
|------|---------|---------|
| 写新 API | backend-architect | 智能补全 boilerplate |
| 重构代码 | code-reviewer | 智能重命名跨文件 |
| 修复 bug | systematic-debugging | 跳转修改点 |
| 写测试 | api-test-pro | 智能补全 pytest 模板 |

---

## 5. 监控与调优

### 5.1 性能监控

- 右下角 CUE 状态图标：绿色（活跃）/ 黄色（休眠）/ 灰色（关闭）
- 鼠标悬停 → 自动显示摘要（需开启"自动显示摘要"）

### 5.2 调优建议

- 项目 > 5000 文件 → 必须 Build → 否则 Cue-Pro 卡顿
- 高峰期临时休眠 → 避免与大模型调用冲突

---

## 6. 不建议的 CUE 使用

- ❌ 大型一次性文件生成 → 关闭 CUE，避免干扰
- ❌ 复杂算法手写 → 关闭 CUE，建议手动设计
- ❌ 多人协作编辑 → CUE 预测可能误导

---

## 7. 参考

- [Trae CUE 官方文档](https://docs.trae.cn/ide/cue)
- [v5.5 Trae IDE 深度研究](file:///d:/filework/excel-to-diagram/docs/governance/2026-09-02-trae-ide-v5.5-deep-research.md)
- [.trae/.ignore 配置](file:///d:/filework/excel-to-diagram/.trae/.ignore)