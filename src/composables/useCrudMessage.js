/**
 * useCrudMessage - CRUD 操作语义化反馈封装
 *
 * 解决问题：
 *   - 当前项目 save/lock/activate 等操作反馈五花八门（"已保存"/"保存成功"/"更新成功"并存）
 *   - 散落使用 ElMessage，在 high-z modal 场景下被遮挡（PermissionConfigPanel 注释里踩过坑）
 *   - 全项目文案不集中，未来 i18n 需全部返工
 *
 * 设计目标：
 *   - 调用点简洁：message.saved('用户') vs message.success('用户保存成功')
 *   - 文案集中：未来 i18n 零成本（替换为 t('crud.saved', { entity })）
 *   - 错误自动提取：从 err.response.data.message 智能取 message
 *   - 全用 useMessage 内部走 NotificationContainer (z-index 1700, teleport to body)
 *
 * 使用示例：
 *   const message = useCrudMessage()
 *   message.saved('用户')              // → "用户保存成功"
 *   message.stateChanged('锁定', '用户') // → "用户已锁定"
 *   try { await api() } catch (err) { message.error('保存失败', err) }
 *
 * @see docs/superpowers/specs/2026-06-09-user-lock-and-feedback-design.md
 */
import { useMessage } from './useMessage'

/**
 * 从 err 对象提取后端错误消息
 * @param {Error|object} err
 * @param {string} fallback
 * @returns {string}
 */
function extractErrorMessage(err, fallback) {
  if (!err) return fallback
  // axios 风格: err.response.data.message
  if (err.response?.data?.message) return err.response.data.message
  // fetch 包装: err.message
  if (err.message) return err.message
  return fallback
}

export function useCrudMessage() {
  const message = useMessage()

  return {
    // ===== 成功反馈（语义化） =====

    /**
     * 保存成功（创建/更新统称）
     * @param {string} entity - 实体名称，如 '用户' / '角色' / '数据'
     */
    saved: (entity = '数据') => message.success(`${entity}已保存`),

    /**
     * 创建成功
     */
    created: (entity = '数据') => message.success(`${entity}已创建`),

    /**
     * 更新成功
     */
    updated: (entity = '数据') => message.success(`${entity}已更新`),

    /**
     * 删除成功
     */
    deleted: (entity = '数据') => message.success(`${entity}已删除`),

    /**
     * 启用成功
     */
    enabled: (entity = '数据') => message.success(`${entity}已启用`),

    /**
     * 禁用成功
     */
    disabled: (entity = '数据') => message.success(`${entity}已禁用`),

    /**
     * 状态变更成功
     * @param {string} action - 动作，如 '锁定' / '激活' / '启用'
     * @param {string} entity - 实体名称，如 '用户'
     */
    stateChanged: (action, entity = '数据') =>
      message.success(`${entity}已${action}`),

    /**
     * 偏好设置保存成功
     */
    preferencesSaved: () => message.success('偏好设置已保存'),

    /**
     * 密码修改成功
     */
    passwordChanged: () => message.success('密码修改成功'),

    /**
     * 个人信息更新成功（display_name/email）
     */
    profileUpdated: () => message.success('个人信息已更新'),

    /**
     * 导入完成
     */
    imported: (count) => message.success(`导入完成，共处理 ${count} 条数据`),

    /**
     * 导出完成
     */
    exported: (count) => message.success(`已导出 ${count} 条数据`),

    // ===== 错误反馈 =====

    /**
     * 通用错误反馈（智能提取后端消息）
     * @param {string} defaultMsg - 默认文案
     * @param {Error|object} err - 错误对象（可选）
     */
    error: (defaultMsg = '操作失败', err = null) => {
      const msg = extractErrorMessage(err, defaultMsg)
      message.error(msg, err)
    },

    /**
     * 网络错误
     */
    networkError: () => message.error('网络连接失败，请检查网络后重试'),

    /**
     * 加载失败
     */
    loadFailed: (entity = '数据') => message.error(`加载${entity}失败，请稍后重试`),

    /**
     * 保存失败
     */
    saveFailed: (entity = '数据') => message.error(`保存${entity}失败，请稍后重试`),

    /**
     * 创建失败
     */
    createFailed: (entity = '数据') => message.error(`创建${entity}失败，请稍后重试`),

    /**
     * 更新失败
     */
    updateFailed: (entity = '数据') => message.error(`更新${entity}失败，请稍后重试`),

    /**
     * 删除失败
     */
    deleteFailed: (entity = '数据') => message.error(`删除${entity}失败，请稍后重试`),

    // ===== P3 长消息 =====

    /**
     * 长消息：主+副标题
     * @param {string} title 主标题
     * @param {string} subtitle 副标题
     * @param {string} [type='info'] 类型
     */
    detail: (title, subtitle, type = 'info') => message.detail(title, subtitle, type),

    // ===== 透传 useMessage（向后兼容 + 特殊场景） =====

    /** @deprecated 优先用 saved/created/updated/deleted/stateChanged */
    success: (msg) => message.success(msg),
    /** @deprecated 优先用 error(msg, err) */
    error_raw: (msg) => message.error(msg),
    warning: (msg) => message.warning(msg),
    info: (msg) => message.info(msg),
    confirm: (opts) => message.confirm(opts),
  }
}