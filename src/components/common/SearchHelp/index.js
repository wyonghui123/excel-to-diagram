/**
 * [V1.0.0 2026-07-24] SearchHelp 语义化封装组件统一导出
 * 元数据驱动的 SearchHelp 组件库
 *
 * 4 个标准变体:
 *   - SearchHelpListSingle: List 单选 (如选择版本)
 *   - SearchHelpListMulti:  List 多选 (如选择领域)
 *   - SearchHelpTreeSingle: Tree 单选 (如选择领域)
 *   - SearchHelpTreeMulti:  Tree 多选 (如选择子领域)
 *
 * 核心设计:
 *   - 自动构建 valueHelpConfig, 使用者只需传 targetBo / dimensionId
 *   - 基于 SearchHelpDialog + HierarchicalTreePicker 的薄封装
 *   - 元数据驱动: 通过后端 value_help YAML 配置自动选择组件
 */
export { default as SearchHelpListSingle } from './SearchHelpListSingle.vue'
export { default as SearchHelpListMulti } from './SearchHelpListMulti.vue'
export { default as SearchHelpTreeSingle } from './SearchHelpTreeSingle.vue'
export { default as SearchHelpTreeMulti } from './SearchHelpTreeMulti.vue'
