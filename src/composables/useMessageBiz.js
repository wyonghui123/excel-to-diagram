/**
 * useMessageBiz - 业务消息 API (P2 业务术语优化)
 *
 * 提供语义化的业务消息方法，避免在 .vue 中散落"操作成功/失败"等通用文案。
 * 设计原则（DP-1）：业务消息 = 状态 + 对象 + 动作
 *
 * @see docs/specs/spec-biz-msg-ux-2026-06-19-v1.0.md
 */
import { useMessage } from './useMessage'

export function useMessageBiz() {
  const m = useMessage()
  return {
    // 成功反馈
    saved: (entity = '数据') => m.success(`${entity}已保存`),
    created: (entity = '数据') => m.success(`${entity}已创建`),
    updated: (entity = '数据') => m.success(`${entity}已更新`),
    deleted: (entity = '数据') => m.success(`${entity}已删除`),
    enabled: (entity = '数据') => m.success(`${entity}已启用`),
    disabled: (entity = '数据') => m.success(`${entity}已禁用`),
    stateChanged: (action, entity = '数据') => m.success(`${entity}已${action}`),
    imported: (count) => m.success(`导入完成，共处理 ${count} 条数据`),
    exported: (count) => m.success(`已导出 ${count} 条数据`),
    // 失败反馈
    loadFailed: (entity = '数据') => m.error(`加载${entity}失败，请稍后重试`),
    saveFailed: (entity = '数据') => m.error(`保存${entity}失败，请稍后重试`),
    createFailed: (entity = '数据') => m.error(`创建${entity}失败，请稍后重试`),
    updateFailed: (entity = '数据') => m.error(`更新${entity}失败，请稍后重试`),
    deleteFailed: (entity = '数据') => m.error(`删除${entity}失败，请稍后重试`),
    importFailed: () => m.error('导入失败，请检查文件内容后重试'),
    exportFailed: () => m.error('导出失败，请稍后重试'),
    // 系统级
    networkError: () => m.error('网络连接失败，请检查网络后重试'),
    sessionExpired: () => m.error('会话已过期，请重新登录'),
    noPermission: () => m.error('您没有执行此操作的权限'),
    serverBusy: (traceId) => m.error(`系统繁忙，请稍后重试${traceId ? `（错误编号: ${traceId}）` : ''}`),
    contactAdmin: (traceId) => m.error(`请联系管理员${traceId ? `（错误编号: ${traceId}）` : ''}`),
  }
}
