/**
 * printService - 单据打印平台 API 封装（spec-print-platform §8）
 *
 * 职责:
 *   · 可打印清单（派生）、模板 CRUD/校验/发布/分叉默认版式；
 *   · 绑定 CRUD、模板解析试算；
 *   · 预览渲染、打印/下载归档、重打、打印记录、批量打印。
 *
 * 边界:
 *   · 打印动作权限由后端判目标 BO `read`；模板/绑定管理判
 *     `print_template:{create,update,delete}`，前端只做按钮显隐，不替代鉴权；
 *   · 归档 PDF 走附件平台（link target = print_run），重打复用归档字节。
 *
 * @module services/printService
 */

import { apiRoot, apiV1, downloadBlob } from '@/utils/httpClient'

const BASE = '/api/print'
const PDF_TIMEOUT = 120000

// ------------------------------------------------------------------ 可打印清单

/** 可打印接入点清单（已按当前用户可读 BO 过滤，含绑定摘要）。 */
export function fetchPrintable() {
  return apiRoot.get(`${BASE}/printable`)
}

// ------------------------------------------------------------------ 模板

/** @param {{bo_code?:string,type_code?:string,status?:string,page?:number,page_size?:number}} [params] */
export function fetchTemplates(params) {
  return apiRoot.get(`${BASE}/templates`, { params })
}

export function fetchTemplate(templateId) {
  return apiRoot.get(`${BASE}/templates/${encodeURIComponent(templateId)}`)
}

export function createTemplate(payload) {
  return apiRoot.post(`${BASE}/templates`, payload)
}

export function updateTemplate(templateId, payload) {
  return apiRoot.put(`${BASE}/templates/${encodeURIComponent(templateId)}`, payload)
}

export function validateTemplate(templateId) {
  return apiRoot.post(`${BASE}/templates/${encodeURIComponent(templateId)}/validate`, {})
}

export function publishTemplate(templateId) {
  return apiRoot.post(`${BASE}/templates/${encodeURIComponent(templateId)}/publish`, {})
}

/**
 * 把合成默认版式另存为 draft；`templateId=0` 时由 payload 提供 bo_code/type_code。
 */
export function forkDefaultTemplate(templateId, payload) {
  return apiRoot.post(
    `${BASE}/templates/${encodeURIComponent(templateId)}/fork-default`,
    payload || {}
  )
}

// ------------------------------------------------------------------ 绑定

export function fetchBindings(boCode, typeCode) {
  return apiRoot.get(`${BASE}/bindings`, {
    params: { bo_code: boCode, type_code: typeCode || undefined },
  })
}

export function createBinding(payload) {
  return apiRoot.post(`${BASE}/bindings`, payload)
}

export function updateBinding(bindingId, payload) {
  return apiRoot.put(`${BASE}/bindings/${encodeURIComponent(bindingId)}`, payload)
}

/** 下架绑定（物理行保留，is_active=0）。 */
export function deleteBinding(bindingId) {
  return apiRoot.delete(`${BASE}/bindings/${encodeURIComponent(bindingId)}`)
}

// ------------------------------------------------------------------ 解析

/** 模板命中试算（排障）：返回 template/binding/reason/candidates/rejected。 */
export function resolveTemplate(payload) {
  return apiRoot.post(`${BASE}/resolve`, payload)
}

// ------------------------------------------------------------------ 渲染 / 打印

/** 预览渲染：直接返回 PDF 字节（不归档）。 */
export function renderPreview(payload) {
  return apiRoot.post(`${BASE}/render`, payload, {
    responseType: 'blob',
    timeout: PDF_TIMEOUT,
  })
}

/** 打印/下载：渲染 → 归档附件 → 写 print_runs；返回 run 与 attachment_id。 */
export function runPrint(payload) {
  return apiRoot.post(`${BASE}/run`, payload)
}

/** 重打：新增 REPRINT 记录并返回原归档 PDF 字节。 */
export function reprintRun(printRunId) {
  return apiRoot.post(
    `${BASE}/reprint`,
    { print_run_id: printRunId },
    { responseType: 'blob', timeout: PDF_TIMEOUT }
  )
}

/** 打印记录（按单据或 BO）。 */
export function fetchRuns({ bo_code, doc_id, limit, offset } = {}) {
  return apiRoot.get(`${BASE}/runs`, {
    params: { bo_code, doc_id, limit, offset },
  })
}

/** 批量打印（统一作业账本），返回 { task_run_id, run_id }。 */
export function batchPrint(payload) {
  return apiRoot.post(`${BASE}/batch`, payload)
}

// ------------------------------------------------------------------ 归档字节

/**
 * 读取打印归档 PDF（附件平台唯一字节真源，link target = print_run）。
 * @param {number} attachmentId
 * @param {number} runId print_runs.id
 * @param {{inline?:boolean}} [options]
 */
export function fetchArchivedPdf(attachmentId, runId, { inline = true } = {}) {
  return apiV1.download(`/attachments/${encodeURIComponent(attachmentId)}/content`, {
    params: {
      target_type: 'print_run',
      target_id: runId,
      inline: inline ? 1 : undefined,
    },
    timeout: PDF_TIMEOUT,
  })
}

/** 新窗口打开 PDF（预览/重打/打印），60s 后释放 blob URL。 */
export function openPdfBlob(blob) {
  const url = window.URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener')
  window.setTimeout(() => window.URL.revokeObjectURL(url), 60000)
}

/** 触发浏览器保存 PDF。 */
export function savePdfBlob(blob, filename) {
  downloadBlob(blob, filename || 'print.pdf')
}

export default {
  fetchPrintable,
  fetchTemplates,
  fetchTemplate,
  createTemplate,
  updateTemplate,
  validateTemplate,
  publishTemplate,
  forkDefaultTemplate,
  fetchBindings,
  createBinding,
  updateBinding,
  deleteBinding,
  resolveTemplate,
  renderPreview,
  runPrint,
  reprintRun,
  fetchRuns,
  batchPrint,
  fetchArchivedPdf,
  openPdfBlob,
  savePdfBlob,
}