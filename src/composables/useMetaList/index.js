/**
 * useMetaList/index.js - 子模块目录入口
 *
 * 状态: Phase 3.1 v3.8 (完成)
 *   - ✅ utils.js (3 纯函数: formatDate / truncateText / getStatusTagType)
 *   - ✅ metaConfig.js (预研文档 + createMetaConfig 草案 API, 决策: 不推荐迁移)
 *   - ⏸️ 6 子模块 (fetchState / selection / filterSort / batchActions / inlineEdit / navigation) 永久搁置
 *
 * v3 spec 决策路径:
 *   v3.0-3.5: 5 步前置 (FR-018/019/008/8 场景/4 spec) 100% 完成
 *   v3.6: 目录骨架 + utils.js MVU 抽取
 *   v3.7: metaConfig 跨依赖分析 (11 ref × 9 子模块耦合, 决策: 不推荐)
 *   v3.8: 修 4 pre-existing 失败, 154/154 全绿
 *
 * 当前策略 (保守):
 *   - useMetaList.js 保持原样, 仍是主 composable 的 source of truth
 *   - 所有外部引用路径 @/composables/useMetaList 继续指向 useMetaList.js
 *   - utils.js 作为独立子模块存在, 供未来子模块复用 (避免代码重复)
 *   - 本文件 (index.js) 当前没有外部 import, 是"未来子模块聚合入口"占位
 *
 * 拆分子模块的迁移路径 (搁置):
 *   - 需先解决 11 ref 跨 9 子模块 82% 耦合 (ctx/Pinia store 重构)
 *   - 实施成本 ~3-4h, 回归风险高, ROI 极低
 *   - 推荐: 保留 useMetaList.js 整体, 仅 utils.js 独立化作为 Phase 3.1 成果
 *
 * 测试守护:
 *   - 154/154 passed (4 个新 spec 共 41 测试守护关键路径)
 *   - 任何 useMetaList.js 改动会立即触发回归
 *
 * 详见: docs/CHANGELOG-2026-06-13-M1-phase2.md
 */

// 当前无外部 import, 仅作为 Phase 3.1 拆分的目标结构标识
// 后续若继续拆分, 这里会变成:
//   export { useMetaList } from './index' (主 composable 变薄)
//   export { formatDate, truncateText, getStatusTagType } from './utils'
//   export { createMetaConfig } from './metaConfig' (若决定实施)
export const __PHASE_3_1_STATUS__ = 'mvu-completed-v3.8'
