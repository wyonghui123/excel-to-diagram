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
 *
 * [Spec 22 2026-09-13] 增强识别 apiV2 包装格式 { success:false, message, httpStatus, code }
 * 此前仅识别 axios 风格 err.response.data.message，导致 apiV2 PUT 失败时
 * 走到 fallback，丢失后端具体错误（如 ActionPermissionInterceptor 的 403 详情）。
 *
 * 识别优先级：
 *   1. err.response?.data?.message         (原生 axios 错误)
 *   2. err.message                          (通用 Error 对象)
 *   3. err.data?.message                    (包装层 data 内嵌)
 *   4. err.message_zh / err.message_en     (i18n 多语言)
 *   5. fallback                            (兜底默认文案)
 *
 * @param {Error|object} err
 * @param {string} fallback
 * @returns {string}
 */
function extractErrorMessage(err, fallback) {
  if (!err) return fallback
  // 1. axios 原生错误
  if (err.response?.data?.message) return err.response.data.message
  // 2. apiV2 包装错误：{ success:false, message, httpStatus, code }
  if (typeof err.message === 'string' && err.message && !err.message.startsWith('Error:')) {
    return err.message
  }
  // 3. 包装层 data 内嵌
  if (err.data?.message) return err.data.message
  // 4. i18n 多语言
  if (err.message_zh) return err.message_zh
  if (err.message_en) return err.message_en
  // 5. 兜底
  return fallback
}

/**
 * [Spec 22 2026-09-13] 检测是否为 HTTP 403 权限拒绝
 * 用于 StateTransitionButtons 等详情页对 action_ref 权限不足时显示专门提示
 * @param {any} err
 * @returns {boolean}
 */
export function isPermissionDenied(err) {
  if (!err) return false
  // apiV2 包装格式
  if (err.httpStatus === 403 || err.code === 'ERR_403_FORBIDDEN') return true
  // axios 原生
  if (err.response?.status === 403) return true
  return false
}

export function useCrudMessage() {
  const message = useMessage()

  /**
   * [Spec 22 2026-09-13] 权限拒绝（403）专用反馈
   * 场景：用户点击 state_transition 按钮但未持有对应 action_ref 权限
   * 显示更友好的提示（说明缺少哪个权限 + 操作建议）
   *
   * @param {string} action - 操作名，如 '启用' / '锁定'
   * @param {Error|object} err - 错误对象（含后端 message）
   * @param {string} [actionRef] - 权限码（可选，如 'activate'），用于提示补充
   */
  const permissionDenied = (action = '此操作', err = null, actionRef = '') => {
    const backendMsg = extractErrorMessage(err, '')
    // 优先显示后端 message（包含「缺少权限 activate（state_transition: enable_user, object: user）」等具体信息）
    if (backendMsg) {
      message.error(backendMsg, err)
      return
    }
    // 兜底：前端组装
    const hint = actionRef ? `（需权限 ${actionRef}）` : ''
    message.error(`当前用户无权限${action}${hint}`, err)
  }

  /**
   * [Spec 22 2026-09-13] 状态变更失败（带权限检测）
   * 自动根据 err.httpStatus 区分 403（权限不足）与其他错误
   * 调用方只需传 err，无需判断错误类型
   *
   * @param {string} action - 操作名
   * @param {Error|object} err - 错误对象
   * @param {string} [actionRef] - 权限码（可选）
   */
  const stateChangeFailed = (action, err = null, actionRef = '') => {
    if (isPermissionDenied(err)) {
      permissionDenied(action, err, actionRef)
    } else {
      message.error(`${action}失败`, err)
    }
  }

  return {
    // ===== 成功反馈（语义化） =====

    /**
     * [Spec 22 2026-09-13] 权限拒绝（403）专用反馈（暴露给调用方）
     */
    permissionDenied,

    /**
     * [Spec 22 2026-09-13] 状态变更失败（带权限检测，暴露给调用方）
     */
    stateChangeFailed,


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