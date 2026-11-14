/**
 * attachmentService - 平台级附件 API 封装
 *
 * 后端：meta/api/attachment_api.py（/api/v1/attachments*）
 * - 内容层 attachments（不可变字节 + sha256 CAS）
 * - 链接层 attachment_links（target_type + target_id 多态）
 *
 * 约定：所有函数返回 httpClient 结果对象 { success, data, message, code, businessCode, traceId }
 */
import { apiV1, downloadBlob } from '@/utils/httpClient'
import { getEnum } from '@/services/metaEnumService'

/**
 * 附件分类下拉项（fail-closed：唯一来源为后端 attachment_category 枚举）
 * @returns {Promise<Array<{value: string, label: string}>>}
 */
export async function getAttachmentCategories() {
  return getEnum('attachment_category')
}

/**
 * 上传文件并挂接到目标对象（multipart/form-data）
 * @param {object} params
 * @param {File} params.file
 * @param {string} params.targetType - BO id，如 'sales_order'
 * @param {number|string} params.targetId
 * @param {string} [params.linkRole='supporting']
 * @param {string} [params.category='other']
 * @param {string} [params.displayName]
 * @param {string} [params.description]
 * @param {boolean} [params.isPrimary=false]
 * @param {string} [params.visibility='internal']
 */
export function uploadAttachment({
  file,
  targetType,
  targetId,
  linkRole = 'supporting',
  category = 'other',
  displayName,
  description,
  isPrimary = false,
  visibility = 'internal',
} = {}) {
  const form = new FormData()
  form.append('file', file)
  form.append('target_type', targetType)
  form.append('target_id', String(targetId))
  form.append('link_role', linkRole)
  form.append('category', category)
  if (displayName) form.append('display_name', displayName)
  if (description) form.append('description', description)
  form.append('is_primary', isPrimary ? '1' : '0')
  form.append('visibility', visibility)
  return apiV1.post('/attachments', form, { timeout: 120000 })
}

/**
 * 查询目标对象下的附件列表
 * @returns {Promise<{success:boolean, data:{items:Array,total:number}}>}
 */
export function queryByTarget(targetType, targetId, { includeHidden = false, linkRole } = {}) {
  return apiV1.get('/attachments/by-target', {
    params: {
      target_type: targetType,
      target_id: targetId,
      include_hidden: includeHidden ? 1 : undefined,
      link_role: linkRole || undefined,
    },
  })
}

/**
 * 把已存在的附件挂接到另一个目标（复用已有字节）
 */
export function createLink(attachmentId, {
  targetType,
  targetId,
  linkRole = 'supporting',
  isPrimary = false,
  description,
  visibility = 'internal',
} = {}) {
  return apiV1.post(`/attachments/${attachmentId}/links`, {
    target_type: targetType,
    target_id: targetId,
    link_role: linkRole,
    is_primary: isPrimary,
    description,
    visibility,
  })
}

/** 解除挂接（幂等） */
export function unlinkAttachment(linkId) {
  return apiV1.delete(`/attachment-links/${linkId}`)
}

/** 删除整个附件（仍被引用的附件后端会返回 attachment_in_use） */
export function deleteAttachment(attachmentId) {
  return apiV1.delete(`/attachments/${attachmentId}`)
}

/**
 * 下载/预览附件字节
 * @returns {Promise<{success:boolean, data:Blob, message:string}>}
 */
export function fetchAttachmentBlob(item, { targetType, targetId, inline = false } = {}) {
  return apiV1.download(`/attachments/${item.id}/content`, {
    params: {
      target_type: targetType,
      target_id: targetId,
      inline: inline ? 1 : undefined,
    },
    timeout: 120000,
  })
}

/** 下载并触发浏览器保存 */
export async function downloadAttachment(item, { targetType, targetId } = {}) {
  const res = await fetchAttachmentBlob(item, { targetType, targetId })
  if (!res.success) return res
  downloadBlob(res.data, item.file_name || item.original_file_name || 'attachment')
  return res
}

export default {
  getAttachmentCategories,
  uploadAttachment,
  queryByTarget,
  createLink,
  unlinkAttachment,
  deleteAttachment,
  fetchAttachmentBlob,
  downloadAttachment,
}