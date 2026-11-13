/**
 * 金额回溯 / 金额重算 API 客户端
 *
 * 后端统一契约（四类单据共用）：
 *   GET  /api/v2/bo/<object_type>/<record_id>/amount-trace  只读回溯
 *   POST /api/v2/action/amount.recalc                      显式重算（草稿态）
 *
 * object_type: sales_order | purchase_order | vendor_invoice | customer_invoice
 */
import { apiV2 } from '@/utils/httpClient'

/** 金额回溯（抬头 / 行 / 调整 / 重算门槛，均为只读）。 */
export function getAmountTrace(objectType, recordId) {
  return apiV2.get(`/bo/${objectType}/${recordId}/amount-trace`)
}

/** 显式重算金额并落库（与回溯面板同一口径）。 */
export function recalcAmount(objectType, recordId) {
  return apiV2.post('/action/amount.recalc', {
    object_type: objectType,
    id: recordId
  })
}