# -*- coding: utf-8 -*-
"""税务守卫 —— 税码 / 税率 / 税务登记号的跨行不变量校验。

依据: docs/superpowers/specs/2026-10-25-tax-wave0-implementation-spec.md §6

规则落点：
  C1 免税依据      —— `validate_tax_code_write`（exempt / out_of_scope 必须有依据）
  C2 外部税系统    —— `validate_tax_code_write`（rate_source=external 必须有系统标识）
  G1 区间自洽      —— `validate_tax_rate_write`（effective_to 必须晚于 effective_from）
  G2 区间不重叠    —— `validate_tax_rate_write`（同一税码下任意两段不得真重叠）
  G3 税率范围      —— `validate_tax_rate_write`（0 <= rate < 100，字段级 constraints 之外的双保险）
  G4 税码存在      —— `validate_tax_rate_write`（tax_code_id 必须指向真实税码）
  G5 主号唯一      —— `validate_party_tax_registration_write`（同伙伴+国家+税种至多一个主号）
  G6 有效期自洽    —— `validate_party_tax_registration_write`（valid_to 必须晚于 valid_from）

为什么 G2 / G5 必须放在应用层：
  DB 唯一索引只能表达 (tax_code_id, effective_from) 与
  (party_id, country_id, tax_type, registration_number)，表达不了
  「区间交集为空」与「条件唯一（仅 is_primary=1 的那一行唯一）」。
  与 currency_rate 的 R2（无序币对）同因。

查询失败一律 fail-open + WARNING（沿用 currency_rate_guard 口径）：
  读侧守卫不应因一次瞬时查询异常把整条写入路径打死。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TAX_TYPE_VALUES = {
    'vat', 'gst', 'sales_tax', 'excise', 'customs_duty', 'other', 'none',
}
TREATMENT_VALUES = {'standard', 'zero_rated', 'exempt', 'out_of_scope'}
_TREATMENT_REQUIRES_REASON = {'exempt', 'out_of_scope'}

#: 查询失败哨兵 —— 与「查不到」区分：查不到 ⇒ 拒（G4），查询失败 ⇒ 放行（fail-open）。
_UNKNOWN = object()


class TaxGuardError(ValueError):
    """税务守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


class TaxGuardService:
    """税务三对象写入前的跨行校验。

    覆写 `_fetch_tax_code` / `_list_sibling_rates` / `_count_primary` 即可注入测试数据。
    """

    TAX_CODE_TABLE = 'tax_codes'
    RATE_TABLE = 'tax_rates'
    REGISTRATION_TABLE = 'party_tax_registrations'

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def validate_tax_code_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """税码创建 / 更新前校验 C1 / C2。"""
        treatment = _text(data.get('tax_treatment'))
        if treatment in _TREATMENT_REQUIRES_REASON:
            if not _text(data.get('exemption_reason')):
                raise TaxGuardError(
                    '税务处理方式为「免税」或「未纳入范围」时必须填写减免依据',
                    field_name='减免依据', rule='exemption_reason_required')

        if _text(data.get('rate_source')) == 'external':
            if not _text(data.get('external_tax_system')):
                raise TaxGuardError(
                    '税率取数方式为「外部税系统」时必须填写外部税系统标识',
                    field_name='外部税系统', rule='external_system_required')

    def validate_tax_rate_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """税率行创建 / 更新前校验 G1 / G3 / G4 / G2。"""
        tax_code_id = data.get('tax_code_id')
        if tax_code_id in (None, ''):
            return  # 缺父键交给必填校验兜底

        # G1：区间自洽
        start = _date_key(data.get('effective_from'))
        end = _date_key(data.get('effective_to'))
        if start and end and end <= start:
            raise TaxGuardError(
                '生效截止日必须晚于生效起始日（区间为 [起始日, 截止日)）',
                field_name='生效截止日', rule='window_inverted')

        # G3：税率范围（字段级 numeric_range 之外的双保险，防绕过校验层写入）
        rate = _number(data.get('rate_percent'))
        if rate is not None and not (0 <= rate < 100):
            raise TaxGuardError(
                '税率必须在 0 到 100 之间（不含 100；13% 填 13，不填 0.13）',
                field_name='税率(%)', rule='rate_out_of_range')

        # G4：税码必须存在（查询失败返回哨兵 ⇒ 放行，不把瞬时故障当成不存在）
        if self._fetch_tax_code(tax_code_id) is None:
            raise TaxGuardError(
                '所属税码不存在，请先创建税码',
                field_name='税码', rule='tax_code_missing')

        if not start:
            return  # 缺起始日交给必填校验兜底

        # G2：同一税码下区间不重叠（半开区间；None = +∞）
        for row in self._list_sibling_rates(tax_code_id, exclude_id):
            other_start = _date_key(row.get('effective_from'))
            other_end = _date_key(row.get('effective_to'))
            if _overlaps(start, end, other_start, other_end):
                raise TaxGuardError(
                    f'该税码在此生效期内已有税率记录（{other_start} 起'
                    f'{"至 " + other_end if other_end else "至今"}），'
                    '同一税码的税率区间不得重叠',
                    field_name='生效起始日', rule='window_overlap')

    def validate_party_tax_registration_write(self, data: Dict[str, Any],
                                              exclude_id: Any = None) -> None:
        """税务登记号创建 / 更新前校验 G6 / G5。"""
        # G6：有效期自洽
        start = _date_key(data.get('valid_from'))
        end = _date_key(data.get('valid_to'))
        if start and end and end <= start:
            raise TaxGuardError(
                '生效截止日必须晚于生效起始日',
                field_name='生效截止日', rule='validity_inverted')

        # G5：同 (伙伴, 国家, 税种) 至多一个主号
        if not _truthy(data.get('is_primary')):
            return
        party_id = data.get('party_id')
        country_id = data.get('country_id')
        tax_type = _text(data.get('tax_type'))
        if party_id in (None, '') or country_id in (None, '') or not tax_type:
            return  # 缺键交给必填校验兜底

        if self._count_primary(party_id, country_id, tax_type, exclude_id) > 0:
            raise TaxGuardError(
                '该业务伙伴在该国家该税种下已有一个主登记号，请先取消原主号',
                field_name='主登记号', rule='primary_duplicated')

    # ---------- 查询（可覆写，便于单测注入）----------

    def _one(self, sql: str, params: list) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open（不阻断正常写入）
            logger.warning(f'[tax_guard] 查询失败: {e}')
            return None
        return rows[0] if rows else None

    def _all(self, sql: str, params: list) -> List[Dict[str, Any]]:
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:
            logger.warning(f'[tax_guard] 查询失败: {e}')
            return []
        return list(rows or [])

    def _fetch_tax_code(self, tax_code_id: Any) -> Any:
        """返回税码行 / None（确认不存在）/ `_UNKNOWN`（查询失败，fail-open）。"""
        try:
            rows = self.ds.query(
                f"SELECT id, code, status FROM {self.TAX_CODE_TABLE} WHERE id = ?",
                [tax_code_id])
        except Exception as e:
            logger.warning(f'[tax_guard] 查询失败: {e}')
            return _UNKNOWN
        return rows[0] if rows else None

    def _list_sibling_rates(self, tax_code_id: Any, exclude_id: Any) -> List[Dict[str, Any]]:
        sql = (
            f"SELECT id, effective_from, effective_to FROM {self.RATE_TABLE} "
            "WHERE tax_code_id = ?"
        )
        params = [tax_code_id]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        return self._all(sql, params)

    def _count_primary(self, party_id: Any, country_id: Any, tax_type: str,
                       exclude_id: Any) -> int:
        sql = (
            f"SELECT COUNT(*) AS cnt FROM {self.REGISTRATION_TABLE} "
            "WHERE party_id = ? AND country_id = ? AND tax_type = ? "
            "AND is_primary = 1"
        )
        params = [party_id, country_id, tax_type]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        row = self._one(sql, params)
        if not row:
            return 0
        try:
            return int(row.get('cnt') or 0)
        except (TypeError, ValueError):
            return 0


# ---------- 内部工具 ----------

def _overlaps(a_start: str, a_end: Optional[str],
              b_start: Optional[str], b_end: Optional[str]) -> bool:
    """两个半开区间 [start, end) 是否真重叠；end=None 表示 +∞。

    相邻（a_end == b_start 或反之）不算重叠。
    """
    if b_start is None:
        return False  # 兄弟行缺起始日，属脏数据，不参与判定
    if b_end is not None and a_start >= b_end:
        return False
    if a_end is not None and b_start >= a_end:
        return False
    return True


def _date_key(value: Any) -> Optional[str]:
    """把 date / datetime / 字符串统一成 'YYYY-MM-DD'，与库内 date 字段存储口径一致。"""
    if value is None:
        return None
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    text = str(value).strip()
    return text[:10] if text else None


def _text(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _number(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'y')
