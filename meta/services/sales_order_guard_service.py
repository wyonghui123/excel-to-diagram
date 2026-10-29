# -*- coding: utf-8 -*-
"""销售订单守卫 —— 波次 0 不变量 W0-R1 ~ W0-R10 与结构展开 W2-R1 ~ W2-R6。

依据: meta/schemas/sales_order.yaml / sales_order_line.yaml 头注释
      docs/superpowers/specs/2026-10-24-sales-order-wave0-detailed-plan.md §1.4

落点划分:
  W0-R1  order_no 生成后不可改                        —— 抬头更新
  W0-R2  qty > 0；方向由抬头 document_category 决定    —— 行写入
  W0-R3  退货单金额为负（符号由金额服务施加，本服务只保证方向来源唯一）
  W0-R4  order_type 须 scope_bo='sales_order' + level='header'；
         行 line_type 须 level='line'
  W0-R5  行 line_type 与抬头 order_type 同 scope_bo
  W0-R6  item_id 为空时 description 必填；uom_id 恒必填
  W0-R7  抬头合计 = 行合计                            —— 金额服务回写（不在本服务）
  W0-R8  非 draft 禁删行；非 draft 禁改 order_no / order_type_id / currency_id
  W0-R9  确认后冻结 exchange_rate（行侧由「行只能在 draft 维护」覆盖）
  W0-R10 sales_org_id 须具备 org_functions.function_type='sales'

结构展开（P1）:
  W2-R1  configuration_id / parent_line_id / component_no 由展开服务写入，
         手工写入路径不得新建或修改（表单回传原值放行）
  W2-R2  子行（parent_line_id 非空）的 item_id 不可改，否则与 component_no 失配
  W2-R3  component_no 须符合配置实例的组件键格式 Ldddd(.Ldddd)*
  W2-R4  pricing_mode 只能是 standalone / bundle_price / component_price /
         base_plus_option
  W2-R5  服务行（line_type.code='SVC'）不指定发货点，与不可发货行同口径
  W2-R6  有展开子行的父行不可直接删除，须先删子行

服务行（W2-A）:
  W2-SVC-1  非服务物料行不得填写服务属性
  W2-SVC-2  服务物料须处于可售状态（判定来源 = sales_order_line.item_id 的
            value_help.value_filter.status，未声明时回落 active）
  W2-SVC-3  服务结束日不得早于开始日
  W2-SVC-4  服务时长 > 0，且必须与时长单位成对
  W2-SVC-5  计费方式 / 资源类型 / 时长单位必须在枚举内

退货引用（E6 / R-RET，依据 docs/superpowers/specs/
2026-10-26-sales-order-master-data-gap-spec.md §10）:
  R-RET-1  仅退货单（document_category=return）+ 退货行（line_category=return）
           可填引用；无源退货留空放行
  R-RET-2  引用行必须存在
  R-RET-3  引用行不得属于当前订单（含自身）
  R-RET-4  被引用行及其所属订单都不得是退货
  R-RET-5  被引用行所属订单须为 confirmed / closed
  R-RET-6  退货单客户须等于原单客户
  R-RET-7  行的 item_id 须等于被引用行（双方都有值时）
  R-RET-8  累计退货量（不含当前行、排除已取消行 / 单）+ 本次 ≤ 原行 qty
  R-RET-9  被引用行禁止删除

地址快照（W2-D）:
  R-ADR-1  订单离开草稿后两列只读（唯一例外：确认动作同一请求内由系统回填）
  R-ADR-2  已非空的快照不得被清空
  R-ADR-3  快照值只取自 address.formatted_address，不拼接、不格式化

销售区域（M3）:
  R-TER-8  订单确认后 territory_id 冻结；未确认可改
  §6.1     新建时按客户主区域带出（当日有效 → 主区域优先 → priority 升序
           → effective_from 最新）；客户无分配则留空，不阻断下单（fail-open）

产品组（B）:
  R-DIV-1  division_code 须存在于 division 且为启用态（创建或值变更时校验）

最小订单量 / 订单倍数（E9 / R-QTY，依据 docs/superpowers/specs/
2026-10-26-sales-order-master-data-gap-spec.md §11）:
  R-QTY-1  限制值以 item.sales_uom 为锚（空则 base_uom），用
           UomQuantityService.convert(item_id, limit, 锚单位, 行单位) 换算到行单位
  R-QTY-2  小于最小订单量拒绝                       —— qty_below_min_order（字段 qty）
  R-QTY-3  非订单倍数整数倍拒绝                     —— qty_not_order_multiple（字段 qty）
  R-QTY-4  创建必校验；更新仅在 qty / item_id / uom_id 任一变化时校验
  R-QTY-5  退货单 / 退货行 / 服务物料 / 两限制都为空 → 豁免
  R-QTY-6  物料读不到、锚单位为空、convert 返回 None → fail-open

抬头折扣 / 附加费（R-DSC-H，依据 docs/superpowers/specs/
2026-10-26-sales-order-billing-and-header-discount-spec.md §4.8）:
  R-DSC-H1  折扣率 / 附加费率须在 0..100             —— HEADER_DISCOUNT_RANGE
  R-DSC-H2  分摊后整单净额不得为负；抬头快照符号须为
            折扣 ≤ 0 / 附加费 ≥ 0                    —— HEADER_DISCOUNT_NEGATIVE_AMOUNT
  R-DSC-H3  非 draft 冻结两个百分比                  —— HEADER_DISCOUNT_LOCKED
  R-DSC-H4  确认时抬头快照与行分摊额须等于按当前行基额
            回算的 D / S（含 Σ 行调整额守恒）         —— HEADER_DISCOUNT_NOT_APPLIED
  R-DSC-H5  置了比例但整单行基额为 0（确认时校验）   —— HEADER_DISCOUNT_ZERO_BASE
  R-DSC-H6  行已手工改价（price_source='manual'）不排斥，
            抬头折扣仍按折后净额比例摊（不设错误码）

行的写入门槛取「父单必须是 draft」一条：
  R8 只明文限制删除，但 submitted / confirmed 已是下游读取的快照态，
  允许追加或改行会让 R7 的汇总回写改动已确认金额，故创建 / 更新 / 删除
  统一要求 draft。这一条同时覆盖 R9 的行侧冻结（tax_rate_percent / unit_price
  在 draft 之外不再变化）。

查询失败一律 fail-open + WARNING（沿用 currency_rate / payment_term 守卫口径）：
读侧守卫不应因一次瞬时查询异常把整条写入路径打死。取不到行时不做判定，
缺失引用由数据库外键约束兜底。

计划行（R-SCH-0 ~ R-SCH-10，依据 docs/superpowers/specs/
2026-10-26-sales-order-schedule-line-spec.md）:
  R-SCH-0  order_id 必须等于 line_id 所属订单
  R-SCH-1  promised_date 必填
  R-SCH-2  billing 不承诺数量（promised_qty 必须为空）
  R-SCH-3  delivery 承诺量必填且 > 0；同一行 delivery 合计 ≤ 行 qty
  R-SCH-4  service 必须填写 service_visit_no（行内唯一由部分唯一索引兜底）
  R-SCH-5  订单非 draft 禁止新增 / 删除，只允许改期 / 改量 / 改发货点
  R-SCH-6  milestone_code 长度 ≤ 64，不做存在性校验
  R-SCH-7  delivery 必须有发货点（默认继承订单行，行为空时要求本行显式填写）
  R-SCH-8  物理删除：仅 draft 且未被派生边引用时允许
  R-SCH-9  状态流转须符合 §2.3 图，终态不可回退 / 复活
  R-SCH-10 kind 门控：本波只有 SCHEDULE_KINDS_ENABLED（delivery / billing）可写
  R-SCH-11 billing 收款比例必填且在 0..100                 —— BILLING_PERCENT_*
  R-SCH-12 billing 不得填写 plant_location_id / service_visit_no
  R-SCH-13 同一订单行 billing 比例合计 ≤ 100
  R-SCH-14 billing 收款日（promised_date）必填
  R-SCH-15 非草稿订单冻结 billing_percent
  R-SCH-16 行类型 delivery_relevant=false 的订单行禁止建 delivery 计划行
           —— SCHEDULE_NOT_DELIVERY_RELEVANT

履约状态（§4.6 Close 前置，依据 docs/superpowers/specs/
2026-10-28-sales-order-fulfillment-status-writeback-spec.md）:
  ORDER_NOT_FULFILLED  订单关闭前 fulfillment_status 须为 fulfilled
                       （读值失败 fail-open）

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与其他守卫同一限制）。展开服务同样绕过拦截器链，
其不变量由 SalesOrderExpandService 自行保证。
"""

import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional

from meta.services.uom_quantity_service import UomQuantityService

logger = logging.getLogger(__name__)

ORDER_OBJECT = 'sales_order'
LINE_OBJECT = 'sales_order_line'
SALES_SCOPE = 'sales_order'
DRAFT = 'draft'
#: 订单关闭态（§4.6 Close 前置判定用）
CLOSED = 'closed'
#: 履约完成态（见 docs/superpowers/specs/2026-10-28-sales-order-fulfillment-status-writeback-spec.md §4.3）
FULFILLMENT_FULFILLED = 'fulfilled'
#: 允许关闭的履约状态（FR-006：无待履约事实即可关闭；not_applicable 为纯服务 / 文本单）
CLOSE_ALLOWED_FULFILLMENT = (FULFILLMENT_FULFILLED, 'voided', 'not_applicable')

# W0-R8：非 draft 后不可变的抬头字段
_FROZEN_AFTER_DRAFT = ('order_no', 'order_type_id', 'currency_id')
#: 确认后冻结的汇率快照字段（W0-R9）
_EXCHANGE_SNAPSHOT_FIELDS = ('exchange_rate', 'exchange_rate_type', 'exchange_rate_date')
# W0-R9：确认后冻结的汇率
_CONFIRMED_STATES = ('confirmed', 'closed')

# W2-R1：只由展开服务写入的行字段
_EXPAND_FIELDS = ('configuration_id', 'parent_line_id', 'component_no')
# B7：只由确认动作系统回填的行地址文本快照字段
_LINE_ADDRESS_SNAPSHOT_FIELDS = ('ship_to_address_text', 'bill_to_address_text')
# W2-R4：定价模式枚举
PRICING_MODES = ('standalone', 'bundle_price', 'component_price', 'base_plus_option')
# W2-R3：配置实例组件键（L0010 / L0010.L0020）
_COMPONENT_NO_RE = re.compile(r'^L\d{4}(\.L\d{4})*$')
SERVICE_LINE_CODE = 'SVC'
SERVICE_ITEM = 'service'
# W2-A：服务行字段与受控枚举
_SERVICE_LINE_FIELDS = ('service_start_date', 'service_end_date', 'billing_method',
                        'required_resource_type', 'service_duration', 'duration_type')
_BILLING_METHODS = ('fixed_price', 'time_and_material', 'milestone')
_RESOURCE_TYPES = ('technician', 'engineer', 'consultant')
_DURATION_TYPES = ('hour', 'day', 'week')

#: W2-SVC-2 兜底可售状态：schema 未声明 / registry 未加载时沿用历史口径
_DEFAULT_SELLABLE_STATUS = 'active'


def _sellable_statuses() -> tuple:
    """服务物料可售状态的唯一来源 = `sales_order_line.item_id` 的 value_help 过滤。

    manage_api 侧由 value_help 本身校验；bo_api 侧拦截器链不读 value_help，
    故此处从同一 schema 声明取值，避免在 Python 里重复写一份状态列表。
    读不到（registry 未加载 / 未声明 status 过滤）→ 回落 `active`。
    """
    try:
        from meta.core.models import registry
        obj = registry.get(LINE_OBJECT)
        for field in getattr(obj, 'fields', None) or []:
            if getattr(field, 'id', '') != 'item_id':
                continue
            value_help = getattr(field, 'value_help', None)
            source = getattr(value_help, 'source', None)
            value_filter = getattr(source, 'value_filter', None) or {}
            status = value_filter.get('status')
            if status:
                return (str(status),)
    except Exception as e:  # schema 不可读 → fail-open，不因读侧异常阻断下单
        logger.warning(f'[sales_order_guard] 读取 item_id value_help 失败: {e}')
    return (_DEFAULT_SELLABLE_STATUS,)

# ---------------- 退货引用链（E6 / R-RET） ----------------
RETURN_CATEGORY = 'return'
RETURN_REFERENCE_FIELD = 'reference_line_id'
#: R-RET-8：累计退货量比较容差（数量允许小数）
_QTY_TOLERANCE = 1e-9
#: R-QTY-3：订单倍数整数倍判定容差（qty / 折算倍数 的小数偏差）
_QTY_MULTIPLE_TOLERANCE = Decimal('1e-6')
#: 从原行复制的空值字段；不复制 qty / unit_price / plant_location_id
_RETURN_REF_COPY_FIELDS = ('item_id', 'customer_item_code', 'description',
                           'uom_id', 'tax_code_id')
# W2-D：地址文本快照（文本列 ← 地址引用列）
_ADDRESS_SNAPSHOT_PAIRS = (('ship_to_address_text', 'ship_to_address_id'),
                           ('bill_to_address_text', 'bill_to_address_id'))
_ADDRESS_SNAPSHOT_FIELDS = tuple(pair[0] for pair in _ADDRESS_SNAPSHOT_PAIRS)
# W1-C：联系人快照（文本列 ← 引用列）；电话快照走 person_profiles.mobile
_CONTACT_SNAPSHOT_PAIRS = (('contact_name_text', 'contact_party_id'),
                           ('contact_phone_text', 'contact_party_id'))
_CONTACT_SNAPSHOT_FIELDS = tuple(pair[0] for pair in _CONTACT_SNAPSHOT_PAIRS)
# W1-C：改客户即清空时涉及的列（引用 + 两张快照）
_CONTACT_CLEAR_FIELDS = ('contact_party_id',) + _CONTACT_SNAPSHOT_FIELDS
CONFIRMED = 'confirmed'

# ---------------- 抬头折扣 / 附加费（R-DSC-H） ----------------
HEADER_DISCOUNT_PERCENT = 'header_discount_percent'
HEADER_SURCHARGE_PERCENT = 'header_surcharge_percent'
HEADER_DISCOUNT_AMOUNT = 'header_discount_amount'
HEADER_SURCHARGE_AMOUNT = 'header_surcharge_amount'
_HEADER_RATE_MIN = 0.0
_HEADER_RATE_MAX = 100.0
# 币种精度 2 位时，回算 D/S 与落库快照允许 1 分的四舍五入差异
_AMOUNT_TOLERANCE = 0.01
_DEFAULT_DECIMALS = 2
_ZERO_DEC = Decimal('0')
_ONE_HUNDRED = Decimal('100')

# ---------------- 计划行（R-SCH） ----------------
SCHEDULE_OBJECT = 'sales_order_schedule'
SCHEDULE_TABLE = 'sales_order_schedules'
# R-SCH-10：三 kind 一次声明，本波启用 delivery / billing
SCHEDULE_KINDS = ('delivery', 'billing', 'service')
SCHEDULE_KINDS_ENABLED = ('delivery', 'billing')
SCHEDULE_STATUSES = ('planned', 'confirmed', 'completed', 'cancelled')
# §2.3：completed / cancelled 为终态，不可回退、不可复活
SCHEDULE_TERMINAL = ('completed', 'cancelled')
SCHEDULE_TRANSITIONS = {
    'planned': ('confirmed', 'cancelled'),
    'confirmed': ('completed', 'cancelled'),
}
SCHEDULE_MILESTONE_MAX = 64
# R-SCH-5：订单离开草稿后仍可改的列。status 不在冻结范围（状态流转由 R-SCH-9 管）。
SCHEDULE_EDITABLE_AFTER_DRAFT = ('promised_date', 'promised_qty',
                                 'plant_location_id', 'status')
# R-SCH-5 对 billing 收窄：无发货点 / 无承诺量，只余收款日与状态。
# billing_percent 不在其中，由 R-SCH-15 单独判定（避免报错码串味）。
SCHEDULE_BILLING_EDITABLE_AFTER_DRAFT = ('promised_date', 'status')
# R-SCH-11 / R-SCH-13 / R-SCH-15：比例比较与合计上限的浮点容差
BILLING_PERCENT_TOLERANCE = 1e-6


class SalesOrderGuardError(ValueError):
    """销售订单守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _num(value: Any) -> Optional[float]:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value: Any) -> Decimal:
    if value is None or value == '':
        return _ZERO_DEC
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _ZERO_DEC


def _round_amount(value: Decimal, decimals: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


class SalesOrderGuardService:
    """销售订单头 / 行的写前校验。

    覆写 `_load_type` / `_load_order` / `_load_line` / `_org_has_function`
    即可注入测试数据（不依赖真实库）。
    """

    def __init__(self, data_source):
        self.ds = data_source

    # ---------------- 抬头 ----------------

    def validate_order_write(self, data: Dict[str, Any],
                             old_data: Optional[Dict[str, Any]] = None,
                             is_create: bool = False) -> None:
        """抬头创建 / 更新前校验（R1 / R4 / R8 / R9 / R10）。

        `data` 是「写入后的有效行」（更新场景 = 旧行 ∪ 本次参数）。
        `old_data` 是写入前的行，用于判定不可变字段与状态门槛。
        """
        old = old_data or {}

        # R1：业务键不可变
        if old and 'order_no' in data \
                and str(data.get('order_no')) != str(old.get('order_no')):
            raise SalesOrderGuardError(
                '订单编号生成后不可修改', field_name='order_no',
                rule='order_no_immutable')

        old_status = old.get('status')

        # §4.6 Close 前置：履约未完成的订单不得关闭（FR-013 的消费方）
        # 只拦「本次由非 closed 转为 closed」；已是 closed 的更新不重复判定。
        if not is_create and str(data.get('status') or '') == CLOSED \
                and str(old_status or '') != CLOSED:
            current = self._load_fulfillment_status(data.get('id'))
            if current is not None and current not in CLOSE_ALLOWED_FULFILLMENT:
                raise SalesOrderGuardError(
                    f'订单尚未履约完成（当前 {current}），不能关闭',
                    field_name='fulfillment_status',
                    rule='ORDER_NOT_FULFILLED')

        # R8：非草稿后禁止改 order_no / order_type_id / currency_id
        if old_status and old_status != DRAFT:
            for field in _FROZEN_AFTER_DRAFT:
                if field not in data:
                    continue
                if str(data.get(field)) != str(old.get(field)):
                    raise SalesOrderGuardError(
                        f'订单已离开草稿态（{old_status}），不允许修改 {field}',
                        field_name=field, rule='field_frozen_after_draft')

        # R9：确认后汇率快照冻结（汇率 / 汇率类型 / 汇率日期）
        if old_status in _CONFIRMED_STATES:
            new_rate = _num(data.get('exchange_rate'))
            old_rate = _num(old.get('exchange_rate'))
            if 'exchange_rate' in data and new_rate is not None \
                    and old_rate is not None and new_rate != old_rate:
                raise SalesOrderGuardError(
                    '订单已确认，汇率快照已冻结，不可修改', field_name='exchange_rate',
                    rule='exchange_rate_frozen')
            for field in _EXCHANGE_SNAPSHOT_FIELDS:
                if field == 'exchange_rate' or field not in data:
                    continue
                if str(data.get(field) or '') != str(old.get(field) or ''):
                    raise SalesOrderGuardError(
                        '订单已确认，汇率快照已冻结，不可修改',
                        field_name=field, rule='exchange_rate_frozen')

        # W0-R13：存在折算（exchange_rate != 1）时汇率日期必填；本币 rate = 1 允许留空
        effective_rate = _num(data.get('exchange_rate')) if 'exchange_rate' in data \
            else _num(old.get('exchange_rate'))
        effective_date = data.get('exchange_rate_date', old.get('exchange_rate_date'))
        if effective_rate is not None and effective_rate != 1 \
                and _is_blank(effective_date):
            raise SalesOrderGuardError(
                '存在汇率折算（exchange_rate != 1）时，汇率日期必填',
                field_name='exchange_rate_date',
                rule='exchange_rate_date_required')

        # R-TER-8：确认后销售区域冻结（此后客户分配变化不影响本单）
        if old_status in _CONFIRMED_STATES and 'territory_id' in data \
                and str(data.get('territory_id')) != str(old.get('territory_id')):
            raise SalesOrderGuardError(
                '订单已确认，销售区域已冻结，不可修改',
                field_name='territory_id', rule='order_territory_locked')

        # W2-D R-ADR-1 / R-ADR-2：地址快照离开草稿后冻结，仅确认动作允许系统回填
        if old_status and old_status != DRAFT:
            confirming = (str(data.get('status') or '') == CONFIRMED
                          and str(old_status) != CONFIRMED)
            for field in _ADDRESS_SNAPSHOT_FIELDS:
                if field not in data:
                    continue
                new_value, old_value = data.get(field), old.get(field)
                if str(new_value) == str(old_value):
                    continue
                if confirming and not _is_blank(new_value):
                    continue
                if confirming:
                    raise SalesOrderGuardError(
                        '已确认的地址快照不得清空',
                        field_name=field, rule='address_snapshot_locked')
                raise SalesOrderGuardError(
                    f'订单已离开草稿态（{old_status}），地址快照只读',
                    field_name=field, rule='address_snapshot_locked')

        # W1-C R-CNT-1 / R-CNT-2：联系人快照离开草稿后冻结，仅确认动作允许系统回填
        if old_status and old_status != DRAFT:
            confirming = (str(data.get('status') or '') == CONFIRMED
                          and str(old_status) != CONFIRMED)
            for field in _CONTACT_SNAPSHOT_FIELDS:
                if field not in data:
                    continue
                new_value, old_value = data.get(field), old.get(field)
                if str(new_value) == str(old_value):
                    continue
                if confirming and not _is_blank(new_value):
                    continue
                if confirming:
                    raise SalesOrderGuardError(
                        '已确认的联系人快照不得清空',
                        field_name=field, rule='contact_snapshot_locked')
                raise SalesOrderGuardError(
                    f'订单已离开草稿态（{old_status}），联系人快照只读',
                    field_name=field, rule='contact_snapshot_locked')

        # R4：单据类型必须 header 层且属销售订单作用域
        type_id = data.get('order_type_id')
        if not _is_blank(type_id):
            type_row = self._load_type(type_id)
            if type_row and (type_row.get('scope_bo') != SALES_SCOPE
                             or type_row.get('level') != 'header'):
                raise SalesOrderGuardError(
                    f'订单类型 {type_id} 不是销售订单抬头类型'
                    f'（须 scope_bo=sales_order / level=header）',
                    field_name='order_type_id', rule='order_type_scope')

        # R10：销售组织必须具备 sales 职能
        sales_org_id = data.get('sales_org_id')
        if not _is_blank(sales_org_id) \
                and not self._org_has_function(sales_org_id, 'sales'):
            raise SalesOrderGuardError(
                f'组织 {sales_org_id} 不具备销售职能（sales），不能作为销售组织',
                field_name='sales_org_id', rule='sales_org_not_sales')

        # R-DIV-1：产品组须存在于 division 且为启用态（严格绑定）
        # 平台 _validate_value_helps 只读顶层已废弃的 validation 且固定按 id 查找，
        # 对 code 型 value_help 不生效，故在此补齐写侧校验。
        division_code = data.get('division_code')
        if not _is_blank(division_code) \
                and (is_create or str(division_code) != str(old.get('division_code'))):
            found, division = self._load_division(division_code)
            if found and division is None:
                raise SalesOrderGuardError(
                    f'产品组 {division_code} 不存在',
                    field_name='division_code', rule='division_not_found')
            if found and division.get('status') != 'active':
                raise SalesOrderGuardError(
                    f'产品组 {division_code} 已停用，不能用于新订单',
                    field_name='division_code', rule='division_inactive')

        # R-DSC-H1 ~ H6：抬头折扣 / 附加费（spec §4.8）
        self.validate_header_discount(data, old_data=old)

    # ---------------- 抬头折扣 / 附加费（R-DSC-H1 ~ H6, §4.8） ----------------

    def validate_header_discount(self, data: Dict[str, Any],
                                 old_data: Optional[Dict[str, Any]] = None,
                                 is_create: bool = False) -> None:
        """抬头折扣 / 附加费的写前校验。

        `data` 是「写入后的有效行」。H1 / H3 与 H2 的符号检查在每次抬头写入
        都执行；H2 的整单净额、H4 的「确认前未重算」、H5 的零基额都取决于
        行金额与分摊结果，故只在比例非零时读行（读侧异常 fail-open）。
        R-DSC-H6 是「允许项」：手工改价的行不排斥抬头折扣，无需校验。
        """
        old = old_data or {}
        disc_pct = _num(data.get(HEADER_DISCOUNT_PERCENT))
        sur_pct = _num(data.get(HEADER_SURCHARGE_PERCENT))

        # R-DSC-H1：折扣率 / 附加费率须在 0..100
        for field, value in ((HEADER_DISCOUNT_PERCENT, disc_pct),
                             (HEADER_SURCHARGE_PERCENT, sur_pct)):
            if value is not None \
                    and (value < _HEADER_RATE_MIN or value > _HEADER_RATE_MAX):
                raise SalesOrderGuardError(
                    f'{field} 须在 0..100 之间（当前 {value}）',
                    field_name=field, rule='HEADER_DISCOUNT_RANGE')

        # R-DSC-H2 前置：抬头快照符号（折扣 ≤ 0 / 附加费 ≥ 0）
        disc_adj = _num(data.get(HEADER_DISCOUNT_AMOUNT))
        sur_adj = _num(data.get(HEADER_SURCHARGE_AMOUNT))
        if (disc_adj is not None and disc_adj > 0) \
                or (sur_adj is not None and sur_adj < 0):
            raise SalesOrderGuardError(
                '抬头折扣金额须 ≤ 0 且附加费金额须 ≥ 0',
                field_name=HEADER_DISCOUNT_AMOUNT,
                rule='HEADER_DISCOUNT_NEGATIVE_AMOUNT')

        old_status = old.get('status')

        # R-DSC-H3：非 draft 冻结两个百分比
        if old_status and old_status != DRAFT:
            for field in (HEADER_DISCOUNT_PERCENT, HEADER_SURCHARGE_PERCENT):
                if field not in data:
                    continue
                new_value = _num(data.get(field)) or 0.0
                old_value = _num(old.get(field)) or 0.0
                if new_value != old_value:
                    raise SalesOrderGuardError(
                        f'订单已离开草稿态（{old_status}），{field} 已冻结',
                        field_name=field, rule='HEADER_DISCOUNT_LOCKED')

        if not disc_pct and not sur_pct:
            return

        order_id = data.get('id')
        if _is_blank(order_id):
            order_id = old.get('id')
        if _is_blank(order_id):
            return
        base_info = self._header_discount_base(order_id)
        if base_info is None:  # 读侧异常 → fail-open
            return
        base, abs_base = base_info

        currency_id = data.get('currency_id')
        if _is_blank(currency_id):
            currency_id = old.get('currency_id')
        decimals = self._currency_decimals(currency_id)
        discount = _round_amount(
            base * _to_decimal(disc_pct) / _ONE_HUNDRED, decimals)
        surcharge = _round_amount(
            base * _to_decimal(sur_pct) / _ONE_HUNDRED, decimals)

        # R-DSC-H2：分摊后整单净额不得为负（Σ net_final = base − D + S）
        if float(base - discount + surcharge) < -_AMOUNT_TOLERANCE:
            raise SalesOrderGuardError(
                '抬头折扣 / 附加费分摊后整单净额为负',
                field_name=HEADER_DISCOUNT_PERCENT,
                rule='HEADER_DISCOUNT_NEGATIVE_AMOUNT')

        confirming = (str(data.get('status') or '') == CONFIRMED
                      and str(old_status or '') != CONFIRMED)
        if not confirming:
            return

        # R-DSC-H5：置了比例但整单行基额为 0
        if abs_base == 0:
            raise SalesOrderGuardError(
                '整单行基额为 0，抬头折扣 / 附加费无法按行分摊',
                field_name=HEADER_DISCOUNT_PERCENT,
                rule='HEADER_DISCOUNT_ZERO_BASE')

        # R-DSC-H4：抬头快照须等于按当前行基额回算的 D / S（未重算即确认）
        header_disc = disc_adj
        if header_disc is None:
            header_disc = _num(old.get(HEADER_DISCOUNT_AMOUNT)) or 0.0
        header_sur = sur_adj
        if header_sur is None:
            header_sur = _num(old.get(HEADER_SURCHARGE_AMOUNT)) or 0.0
        expected_disc = -float(discount)
        expected_sur = float(surcharge)
        if (abs(header_disc - expected_disc) > _AMOUNT_TOLERANCE
                or abs(header_sur - expected_sur) > _AMOUNT_TOLERANCE):
            raise SalesOrderGuardError(
                '抬头折扣 / 附加费未按当前基额重算，不能确认订单',
                field_name=HEADER_DISCOUNT_AMOUNT,
                rule='HEADER_DISCOUNT_NOT_APPLIED')

        # 守恒：Σ 行调整额须等于抬头快照（§4.1 / §4.10）
        sums = self._header_discount_sums(order_id)
        if sums is None:  # 读侧异常 → fail-open
            return
        sum_disc, sum_sur = sums
        if (abs(float(sum_disc) - header_disc) > _AMOUNT_TOLERANCE
                or abs(float(sum_sur) - header_sur) > _AMOUNT_TOLERANCE):
            raise SalesOrderGuardError(
                '行分摊额合计与抬头折扣 / 附加费快照不一致，不能确认订单',
                field_name=HEADER_DISCOUNT_AMOUNT,
                rule='HEADER_DISCOUNT_NOT_APPLIED')

    # ---------------- 销售区域带出（M3, §6.1） ----------------

    def territory_default(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """新建订单时按客户主区域带出 `territory_id`；无分配 / 读侧异常返回空。

        判定顺序（§6.1）：当日有效（effective_from ≤ 今天 ≤ effective_to）
        → 主区域优先 → priority 升序（空视为最大）→ effective_from 最新
        → id 最新。手工已填时不覆盖；客户无分配则留空（fail-open）。
        """
        if not _is_blank(data.get('territory_id')):
            return {}
        customer_id = data.get('customer_account_id')
        if _is_blank(customer_id):
            return {}
        try:
            rows = self.ds.query(
                'SELECT territory_id FROM territory_account_assignments '
                'WHERE customer_account_id = ? '
                '  AND (effective_from IS NULL OR effective_from <= ?) '
                '  AND (effective_to IS NULL OR effective_to >= ?) '
                'ORDER BY CASE WHEN is_primary = 1 THEN 0 ELSE 1 END, '
                '         CASE WHEN priority IS NULL THEN 2147483647 ELSE priority END, '
                '         effective_from DESC, id DESC LIMIT 1',
                [customer_id, self._today(), self._today()])
        except Exception as e:  # 查询失败 → fail-open（不阻断下单）
            logger.warning(
                f'[sales_order_guard] 读取客户区域分配 {customer_id} 失败: {e}')
            return {}
        if not rows:
            return {}
        territory_id = rows[0].get('territory_id')
        return {} if _is_blank(territory_id) else {'territory_id': territory_id}

    @staticmethod
    def _today() -> str:
        """带出判定基准日；独立方法便于单测固定日期。"""
        from datetime import date
        return date.today().isoformat()

    def validate_order_delete(self, order_id: Any) -> None:
        """非草稿订单不可删除（§1.3 事实单据口径）。"""
        if _is_blank(order_id):
            return
        order = self._load_order(order_id) or {}
        status = order.get('status')
        if status and status != DRAFT:
            raise SalesOrderGuardError(
                f'订单处于 {status} 状态，只有草稿可删除',
                field_name='status', rule='order_delete_not_draft')

    def snapshot_address_text(self, data: Dict[str, Any],
                              old_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """R-ADR-3：订单转为 confirmed 时按地址库回填两列文本快照。

        只在该次请求内返回待写入值，由拦截器并入写入参数（同一次事务）。
        地址为空 / 查询失败 / 地址库无全文时跳过该列，不阻断确认。
        """
        old = old_data or {}
        if str(data.get('status') or '') != CONFIRMED:
            return {}
        if str(old.get('status') or '') == CONFIRMED:
            return {}
        snapshot = {}
        for text_field, id_field in _ADDRESS_SNAPSHOT_PAIRS:
            address_id = data.get(id_field)
            if _is_blank(address_id):
                continue
            address = self._load_address(address_id)
            if not address:
                continue
            text = address.get('formatted_address')
            if not _is_blank(text):
                snapshot[text_field] = text
        return snapshot

    def freeze_line_address_text(self, order_id: Any,
                                 snapshot: Dict[str, Any]) -> int:
        """B7：确认动作同一请求内按抬头快照逐行写入地址文本。

        直连 SQL 更新（绕开 bo_api 的「父单须草稿」限制），取消行不写。
        查询/写入失败 → 记 warning 返回 0，不阻断确认（与抬头快照 fail-open 一致）。
        """
        if _is_blank(order_id) or not snapshot:
            return 0
        fields = [f for f in _LINE_ADDRESS_SNAPSHOT_FIELDS
                  if not _is_blank(snapshot.get(f))]
        if not fields:
            return 0
        assignments = ', '.join(f'{f} = ?' for f in fields)
        values = [snapshot[f] for f in fields]
        try:
            cursor = self.ds.execute(
                f"UPDATE sales_order_lines SET {assignments}, "
                "updated_at = datetime('now') "
                "WHERE order_id = ? AND status <> 'cancelled'",
                values + [order_id])
        except Exception as e:  # 快照回填失败不阻断确认
            logger.warning(
                f'[sales_order_guard] 回填行地址快照 {order_id} 失败: {e}')
            return 0
        return getattr(cursor, 'rowcount', 0) or 0

    def snapshot_contact_text(self, data: Dict[str, Any],
                              old_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """W1-C R-CNT-3：订单转为 confirmed 时回填联系人姓名 / 电话快照。

        只在该次请求内返回待写入值，由拦截器并入写入参数（同一次事务）。
        未指定联系人 / 无 person_profile / 手机号为空 / 查询失败 → 跳过对应列，
        不阻断确认（fail-open）。
        """
        old = old_data or {}
        if str(data.get('status') or '') != CONFIRMED:
            return {}
        if str(old.get('status') or '') == CONFIRMED:
            return {}
        contact_id = data.get('contact_party_id')
        if _is_blank(contact_id):
            return {}
        contact = self._load_contact(contact_id)
        if not contact:
            return {}
        snapshot = {}
        name = contact.get('name')
        if not _is_blank(name):
            snapshot['contact_name_text'] = name
        mobile = contact.get('mobile')
        if not _is_blank(mobile):
            snapshot['contact_phone_text'] = mobile
        return snapshot

    def contact_clear_on_customer_change(self, data: Dict[str, Any],
                                         old_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """W1-C R-CNT-4：草稿期改客户 ⇒ 清空联系人引用与两张快照列。

        联系人属于旧客户；草稿期换客户后必须重选，否则会把旧客户的人带到新单上。
        已离开草稿的订单**不清空**（冻结优先，NFR-004）：已成立订单的联系人是
        该单的既有事实，不随客户变更而改写。

        返回待清空的列（值统一 None），由拦截器并入写入参数（同一次事务）。
        """
        old = old_data or {}
        if not old:
            return {}
        if str(old.get('status') or '') != DRAFT:
            return {}
        if 'customer_account_id' not in data:
            return {}
        if str(old.get('customer_account_id')) == str(data.get('customer_account_id')):
            return {}
        return {field: None for field in _CONTACT_CLEAR_FIELDS}

    # ---------------- 行 ----------------
    def validate_line_write(self, data: Dict[str, Any],
                            old_data: Optional[Dict[str, Any]] = None,
                            is_create: bool = False) -> None:
        """行创建 / 更新前校验（R2 / R4 / R5 / R6 + 父单 draft 门槛）。"""
        order_id = data.get('order_id')
        order = self._require_parent_draft(order_id, 'line_write')

        # R4：行类型必须 line 层且属销售订单作用域
        line_type_id = data.get('line_type_id')
        line_type = self._load_type(line_type_id) if not _is_blank(line_type_id) else None
        if line_type and (line_type.get('scope_bo') != SALES_SCOPE
                          or line_type.get('level') != 'line'):
            raise SalesOrderGuardError(
                f'行类型 {line_type_id} 不是销售订单行类型'
                f'（须 scope_bo=sales_order / level=line）',
                field_name='line_type_id', rule='line_type_scope')

        # R5：行类型与抬头单据类型同 scope_bo；抬头类型同时供 R-RET-1 判定
        order_type = (self._load_type(order.get('order_type_id'))
                      if not _is_blank(order.get('order_type_id')) else None)
        if line_type and order_type:
            order_scope = order_type.get('scope_bo')
            if order_scope and order_scope != line_type.get('scope_bo'):
                raise SalesOrderGuardError(
                    f'行类型作用域（{line_type.get("scope_bo")}）与'
                    f'订单类型作用域（{order_scope}）不一致',
                    field_name='line_type_id', rule='line_type_scope_mismatch')

        # R2：数量恒为正（方向由抬头单据类别决定）
        qty = _num(data.get('qty'))
        if qty is None or qty <= 0:
            raise SalesOrderGuardError(
                '订单行数量必须大于 0', field_name='qty', rule='qty_not_positive')

        # R6：单位恒必填；无物料时描述必填
        if _is_blank(data.get('uom_id')):
            raise SalesOrderGuardError(
                '订单行必须填写计量单位', field_name='uom_id', rule='uom_required')
        # V-SU-3 / R-SU-5：行单位须可换算到物料基本单位（仅创建或单位/物料变化时）
        self._validate_line_uom(data, old_data, is_create)
        # E9 / R-QTY-1~6：最小订单量 / 订单倍数（只校验不舍入）
        self._validate_item_qty_rules(data, old_data, is_create, line_type, order_type)
        if _is_blank(data.get('item_id')) and _is_blank(data.get('description')):
            raise SalesOrderGuardError(
                '未选物料的行必须填写行描述', field_name='description',
                rule='description_required')

        # W2-R1：展开字段只读（表单回传原值放行）
        self._validate_expand_fields(data, old_data, is_create)
        # B7：行地址文本快照只由确认动作回填，手工路径不可设置
        self._validate_line_address_snapshot(data, old_data, is_create)

        # W2-R2：子行的物料不可改
        old = old_data or {}
        if (not _is_blank(old.get('parent_line_id')) and 'item_id' in data
                and str(data.get('item_id')) != str(old.get('item_id'))):
            raise SalesOrderGuardError(
                '展开子行的物料不可修改，请先移除子行后重新展开',
                field_name='item_id', rule='component_item_immutable')

        # W2-R3：组件号格式
        component_no = data.get('component_no')
        if not _is_blank(component_no) \
                and not _COMPONENT_NO_RE.match(str(component_no)):
            raise SalesOrderGuardError(
                f'组件号 {component_no} 不符合配置实例的组件键格式'
                '（如 L0010 或 L0010.L0020）',
                field_name='component_no', rule='component_no_format')

        # W2-R4：定价模式枚举
        pricing_mode = data.get('pricing_mode')
        if not _is_blank(pricing_mode) and str(pricing_mode) not in PRICING_MODES:
            raise SalesOrderGuardError(
                f'定价模式 {pricing_mode} 不属于 '
                f'{"/".join(PRICING_MODES)}',
                field_name='pricing_mode', rule='pricing_mode_invalid')

        # W2-R5：服务行不指定发货点
        if line_type and line_type.get('code') == SERVICE_LINE_CODE \
                and not _is_blank(data.get('plant_location_id')):
            raise SalesOrderGuardError(
                '服务行不产生库存移动，不能指定发货点',
                field_name='plant_location_id', rule='service_line_no_location')

        # W2-A：服务行属性（W2-SVC-1~5）
        self._validate_service_line(data)

        # E6 / R-RET-1~8：退货行引用原行（引用为空直接放行）
        self._validate_return_reference(
            data, old_data, is_create, line_type, order_type, order)

    # ---------------- 行单位可换算（V-SU-3 / R-SU-5） ----------------

    def _validate_line_uom(self, data: Dict[str, Any],
                           old_data: Optional[Dict[str, Any]],
                           is_create: bool) -> None:
        """行单位必须能换算到物料基本单位；判定不足（None）放行。

        R-SU-5：更新时 `item_id` / `uom_id` 都未变化则跳过，避免存量行被
        非单位字段的更新「顺手」打回；创建时必校验。
        """
        item_id = data.get('item_id')
        uom_id = data.get('uom_id')
        if _is_blank(item_id) or _is_blank(uom_id):
            return
        if not is_create:
            old = old_data or {}
            if old \
                    and str(item_id) == str(old.get('item_id')) \
                    and str(uom_id) == str(old.get('uom_id')):
                return

        item = self._load_item(item_id)
        if not item:
            return  # R-SU-3：物料读不到不判定（由外键 / 必填兜底）

        compatible = UomQuantityService(self.ds).is_compatible(
            item_id, uom_id, item.get('base_uom'))
        if compatible is False:
            raise SalesOrderGuardError(
                '订单行计量单位与物料基本单位不可换算',
                field_name='uom_id', rule='item_uom_incompatible')

    # ---------------- 最小订单量 / 订单倍数（E9 / R-QTY） ----------------

    def _validate_item_qty_rules(self, data: Dict[str, Any],
                                 old_data: Optional[Dict[str, Any]],
                                 is_create: bool, line_type: Optional[Dict[str, Any]],
                                 order_type: Optional[Dict[str, Any]]) -> None:
        """R-QTY-1~6：物料最小订单量 / 订单倍数（只校验不舍入）。"""
        if (order_type or {}).get('document_category') == RETURN_CATEGORY \
                or (line_type or {}).get('line_category') == RETURN_CATEGORY:
            return
        item_id = data.get('item_id')
        uom_id = data.get('uom_id')
        if _is_blank(item_id) or _is_blank(uom_id):
            return
        qty = _to_decimal(data.get('qty'))
        if qty is None:
            return
        if not is_create:
            old = old_data or {}
            if old:
                qty_changed = 'qty' in data and _to_decimal(data.get('qty')) != _to_decimal(old.get('qty'))
                item_changed = str(item_id) != str(old.get('item_id'))
                uom_changed = str(uom_id) != str(old.get('uom_id'))
                if not (qty_changed or item_changed or uom_changed):
                    return
        item = self._load_item(item_id)
        if not item or item.get('item_type') == SERVICE_ITEM:
            return
        min_qty = _to_decimal(item.get('min_order_qty'))
        multiple = _to_decimal(item.get('order_multiple'))
        if min_qty is None and multiple is None:
            return
        anchor = item.get('sales_uom') if not _is_blank(item.get('sales_uom')) else item.get('base_uom')
        if _is_blank(anchor):
            return
        service = UomQuantityService(self.ds)
        if min_qty is not None and min_qty > 0:
            converted_min = service.convert(item_id, min_qty, anchor, uom_id)
            if converted_min is not None and qty < converted_min - Decimal('1e-9'):
                raise SalesOrderGuardError(
                    f'订单行数量 {qty} 低于物料最小订单量 {min_qty}'
                    f'（按锚单位 {anchor} 折算为 {converted_min} {uom_id}）',
                    field_name='qty', rule='qty_below_min_order')
        if multiple is not None and multiple > 0:
            converted_multiple = service.convert(item_id, multiple, anchor, uom_id)
            if converted_multiple is not None and converted_multiple > 0:
                ratio = qty / converted_multiple
                if abs(ratio - ratio.to_integral_value(rounding=ROUND_HALF_UP)) > _QTY_MULTIPLE_TOLERANCE:
                    raise SalesOrderGuardError(
                        f'订单行数量 {qty} 不是物料订单倍数 {multiple} 的整数倍'
                        f'（按锚单位 {anchor} 折算为 {converted_multiple} {uom_id}）',
                        field_name='qty', rule='qty_not_order_multiple')

    # ---------------- 服务行（W2-A） ----------------

    def _validate_service_line(self, data: Dict[str, Any]) -> None:
        """服务属性校验；物料读不到时 fail-open。"""
        filled = [f for f in _SERVICE_LINE_FIELDS if not _is_blank(data.get(f))]
        item_id = data.get('item_id')
        if _is_blank(item_id):
            if filled:
                raise SalesOrderGuardError(
                    '未选物料的行不能填写服务属性',
                    field_name=filled[0], rule='service_field_non_service_item')
            return

        item = self._load_item(item_id)
        if not item:
            return  # fail-open：物料缺失交给外键 / 必填校验兜底

        if item.get('item_type') != SERVICE_ITEM:
            if filled:
                raise SalesOrderGuardError(
                    '只有服务物料行可以填写服务属性',
                    field_name=filled[0], rule='service_field_non_service_item')
            return

        # 服务物料必须处于 schema 声明的可售状态（默认 active）
        if str(item.get('status') or _DEFAULT_SELLABLE_STATUS) not in _sellable_statuses():
            raise SalesOrderGuardError(
                f'服务物料 {item_id} 未签发或已停用，不能下单',
                field_name='item_id', rule='service_item_not_sellable')

        start = data.get('service_start_date')
        end = data.get('service_end_date')
        if not _is_blank(start) and not _is_blank(end) and str(end) < str(start):
            raise SalesOrderGuardError(
                '服务结束日不得早于开始日',
                field_name='service_end_date', rule='service_date_range')

        if not _is_blank(data.get('service_duration')):
            duration = _num(data.get('service_duration'))
            if duration is None or duration <= 0:
                raise SalesOrderGuardError(
                    '服务时长必须大于 0',
                    field_name='service_duration', rule='service_duration_invalid')
            if _is_blank(data.get('duration_type')):
                raise SalesOrderGuardError(
                    '填写服务时长时必须选择时长单位',
                    field_name='duration_type', rule='duration_type_required')

        for field, allowed in (('billing_method', _BILLING_METHODS),
                               ('required_resource_type', _RESOURCE_TYPES),
                               ('duration_type', _DURATION_TYPES)):
            value = data.get(field)
            if not _is_blank(value) and str(value) not in allowed:
                raise SalesOrderGuardError(
                    f'{field} 取值 {value} 不在 {"/".join(allowed)} 内',
                    field_name=field, rule='service_enum_invalid')

    def service_line_defaults(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """按物料属性补行级默认值（只补空字段；读不到物料返回空）。

        默认单位（R-SU-1）：`uom_id` 为空时取 `item.sales_uom`，再退
        `item.base_uom`；显式给值不覆盖（R-SU-2）。
        服务字段（W2-A）只在 `item_type == service` 时补，映射不变。

        由拦截器在创建前并入写入参数，故默认值与真实写入同一次事务。
        """
        item_id = data.get('item_id')
        if _is_blank(item_id):
            return {}
        item = self._load_item(item_id)
        if not item:
            return {}

        defaults: Dict[str, Any] = {}
        if _is_blank(data.get('uom_id')):
            uom = item.get('sales_uom') or item.get('base_uom')
            if not _is_blank(uom):
                defaults['uom_id'] = uom

        if item.get('item_type') == SERVICE_ITEM:
            mapping = {
                'billing_method': item.get('billing_method_default'),
                'required_resource_type': item.get('required_resource_type'),
                'service_duration': item.get('standard_duration'),
                'duration_type': item.get('duration_type'),
            }
            defaults.update({k: v for k, v in mapping.items()
                             if _is_blank(data.get(k)) and not _is_blank(v)})
        return defaults

    def return_line_defaults(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """退货引用默认值：按原行补空字段（E6 / R-RET）。

        只复制 `item_id` / `customer_item_code` / `description` / `uom_id` /
        `tax_code_id`；不复制 `qty`（避免整行全退）、`unit_price`（定价仍由
        定价引擎取当前价）与 `plant_location_id`（退货收货点可能不同）。
        引用为空 / 原行读不到时返回空，不阻断写入。
        """
        reference_line_id = data.get(RETURN_REFERENCE_FIELD)
        if _is_blank(reference_line_id):
            return {}
        found, ref = self._load_reference_line(reference_line_id)
        if not found or not ref:
            return {}

        defaults: Dict[str, Any] = {}
        for field in _RETURN_REF_COPY_FIELDS:
            if _is_blank(data.get(field)) and not _is_blank(ref.get(field)):
                defaults[field] = ref.get(field)
        return defaults

    def validate_line_delete(self, line_id: Any) -> None:
        """非草稿订单下禁止删除行（R8）；有展开子行的父行须先删子行（W2-R6）。"""
        if _is_blank(line_id):
            return
        line = self._load_line(line_id) or {}
        self._require_parent_draft(line.get('order_id'), 'line_delete')
        if self._has_children(line_id):
            raise SalesOrderGuardError(
                '该行存在展开子行，请先删除子行再删除父行',
                field_name='parent_line_id', rule='line_has_children')
        if self._has_return_refs(line_id):
            raise SalesOrderGuardError(
                '该订单行已被退货行引用，请先删除退货行再删除原行',
                field_name=RETURN_REFERENCE_FIELD, rule='line_has_return_refs')

    # ---------------- 展开字段（W2-R1） ----------------

    @staticmethod
    def _validate_expand_fields(data: Dict[str, Any],
                                old_data: Optional[Dict[str, Any]],
                                is_create: bool) -> None:
        old = old_data or {}
        for field in _EXPAND_FIELDS:
            new_value = data.get(field)
            if _is_blank(new_value):
                continue
            old_value = old.get(field)
            if is_create or _is_blank(old_value) \
                    or str(new_value) != str(old_value):
                raise SalesOrderGuardError(
                    f'{field} 由结构展开服务写入，不能在手工维护路径设置',
                    field_name=field, rule='expand_field_readonly')

    @staticmethod
    def _validate_line_address_snapshot(data: Dict[str, Any],
                                        old_data: Optional[Dict[str, Any]],
                                        is_create: bool) -> None:
        """B7：行地址文本快照只读（确认动作的系统回填走直连 SQL，不经本守卫）。"""
        old = old_data or {}
        for field in _LINE_ADDRESS_SNAPSHOT_FIELDS:
            new_value = data.get(field)
            if _is_blank(new_value):
                continue
            old_value = old.get(field)
            if is_create or _is_blank(old_value) \
                    or str(new_value) != str(old_value):
                raise SalesOrderGuardError(
                    '行地址文本为确认时冻结的地址快照，不能手工修改',
                    field_name=field, rule='line_address_snapshot_readonly')

    # ---------------- 查询（可覆写，便于单测注入） ----------------

    def _require_parent_draft(self, order_id: Any, rule: str) -> Dict[str, Any]:
        if _is_blank(order_id):
            # 缺父键交给必填 / 外键校验兜底
            return {}
        order = self._load_order(order_id) or {}
        status = order.get('status')
        if status and status != DRAFT:
            raise SalesOrderGuardError(
                f'订单处于 {status} 状态，只有草稿可维护订单行',
                field_name='status', rule=f'{rule}_parent_not_draft')
        return order

    def _load_type(self, type_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                'SELECT id, code, scope_bo, level, document_category, '
                'line_category FROM type_definitions WHERE id = ?', [type_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取类型 {type_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                'SELECT id, order_no, order_type_id, order_date, status, '
                'sales_org_id, org_id, currency_id, exchange_rate, '
                'customer_account_id FROM sales_orders WHERE id = ?', [order_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取订单 {order_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _load_fulfillment_status(self, order_id: Any) -> Optional[str]:
        """读订单当前的派生履约状态（§4.6 Close 前置）。

        读不到 / 查询失败返回 None，由调用方按 fail-open 放行。
        """
        if _is_blank(order_id):
            return None
        try:
            rows = self.ds.query(
                'SELECT fulfillment_status FROM sales_orders WHERE id = ?',
                [order_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 读取订单 {order_id} 履约状态失败: {e}')
            return None
        if not rows:
            return None
        return rows[0].get('fulfillment_status')

    def _header_discount_lines(self, order_id: Any):
        """读订单行的净额与两调整列；查询失败返回 None（fail-open）。"""
        try:
            return self.ds.query(
                'SELECT id, net_amount, header_discount_amount, '
                'header_surcharge_amount FROM sales_order_lines '
                'WHERE order_id = ?', [order_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 读取订单 {order_id} 的行金额失败: {e}')
            return None

    def _header_discount_base(self, order_id: Any):
        """返回 `(Σ 行基额, Σ |行基额|)`；查询失败返回 None。

        行基额 = net_amount − header_discount_amount − header_surcharge_amount，
        与 `SalesOrderHeaderDiscountService._base_of` 同一口径。
        """
        rows = self._header_discount_lines(order_id)
        if rows is None:
            return None
        base = _ZERO_DEC
        abs_base = _ZERO_DEC
        for row in rows:
            base_i = (_to_decimal(row.get('net_amount'))
                      - _to_decimal(row.get('header_discount_amount'))
                      - _to_decimal(row.get('header_surcharge_amount')))
            base += base_i
            abs_base += abs(base_i)
        return base, abs_base

    def _header_discount_sums(self, order_id: Any):
        """返回 `(Σ 行折扣调整额, Σ 行附加费调整额)`；查询失败返回 None。"""
        rows = self._header_discount_lines(order_id)
        if rows is None:
            return None
        discount = _ZERO_DEC
        surcharge = _ZERO_DEC
        for row in rows:
            discount += _to_decimal(row.get('header_discount_amount'))
            surcharge += _to_decimal(row.get('header_surcharge_amount'))
        return discount, surcharge

    def _currency_decimals(self, currency_id: Any) -> int:
        """币种小数位；缺币种 / 查询失败按 2 位（与金额服务同口径）。"""
        if _is_blank(currency_id):
            return _DEFAULT_DECIMALS
        try:
            rows = self.ds.query(
                'SELECT decimal_places FROM currencies WHERE id = ?',
                [currency_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 读取币种精度 {currency_id} 失败: {e}')
            return _DEFAULT_DECIMALS
        raw = rows[0].get('decimal_places') if rows else None
        try:
            decimals = int(raw)
        except (TypeError, ValueError):
            return _DEFAULT_DECIMALS
        return decimals if 0 <= decimals <= 8 else _DEFAULT_DECIMALS

    def _load_division(self, code: Any):
        """按 code 读产品组。

        返回 `(found, row)`：`found=False` 表示查询失败（fail-open，不拦截）；
        `found=True, row=None` 表示确无该产品组。
        """
        try:
            rows = self.ds.query(
                'SELECT code, status FROM divisions WHERE code = ?', [code])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取产品组 {code} 失败: {e}')
            return False, None
        return True, (rows[0] if rows else None)

    def _load_address(self, address_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                'SELECT id, formatted_address FROM addresses WHERE id = ?',
                [address_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取地址 {address_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _load_contact(self, party_id: Any) -> Optional[Dict[str, Any]]:
        """W1-C：按 party_id 取联系人姓名与手机号。

        parties 表无联系方式列 ⇒ 手机号取 person_profiles.mobile（party_id 1:1 锚）。
        LEFT JOIN：联系人无 person_profile 档案时仍返回姓名，仅手机号为空。
        查询失败 → fail-open（不阻断确认）。
        """
        try:
            rows = self.ds.query(
                'SELECT p.name AS name, pp.mobile AS mobile '
                'FROM parties p '
                'LEFT JOIN person_profiles pp ON pp.party_id = p.id '
                'WHERE p.id = ?',
                [party_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取联系人 {party_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                'SELECT id, order_id, line_no, line_type_id, item_id, '
                '       qty, uom_id, tax_code_id, customer_item_code, '
                '       description, reference_line_id, '
                '       parent_line_id, component_no, configuration_id, '
                '       pricing_mode FROM sales_order_lines WHERE id = ?',
                [line_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取订单行 {line_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _load_reference_line(self, line_id: Any):
        """读取退货引用行及其订单上下文。

        返回 `(found, row)`：`found=False` 表示查询失败（fail-open，不判定）；
        `found=True, row=None` 表示引用行确实不存在（R-RET-2 拒绝）。
        独立于 `_load_line`，避免把「不存在」与「查询失败」混为一谈。
        """
        try:
            rows = self.ds.query(
                'SELECT l.id, l.order_id, l.qty, l.item_id, l.line_type_id, '
                '       l.customer_item_code, l.description, l.uom_id, '
                '       l.tax_code_id, '
                '       o.order_type_id AS ref_order_type_id, '
                '       o.status AS ref_order_status, '
                '       o.customer_account_id AS ref_customer_account_id '
                'FROM sales_order_lines l '
                'JOIN sales_orders o ON o.id = l.order_id '
                'WHERE l.id = ?', [line_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 读取退货引用行 {line_id} 失败: {e}')
            return False, None
        return True, (rows[0] if rows else None)

    def _load_item(self, item_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                'SELECT id, item_type, status, base_uom, sales_uom, '
                '       min_order_qty, order_multiple, '
                '       billing_method_default, '
                '       required_resource_type, standard_duration, duration_type '
                'FROM items WHERE id = ?', [item_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取物料 {item_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _has_children(self, line_id: Any) -> bool:
        try:
            rows = self.ds.query(
                'SELECT 1 FROM sales_order_lines WHERE parent_line_id = ? LIMIT 1',
                [line_id])
        except Exception as e:  # 查询失败 → fail-open（不因读侧异常阻断删除）
            logger.warning(f'[sales_order_guard] 读取子行 {line_id} 失败: {e}')
            return False
        return bool(rows)

    # ---------------- 退货引用（E6 / R-RET） ----------------

    def _validate_return_reference(self, data: Dict[str, Any],
                                   old_data: Optional[Dict[str, Any]],
                                   is_create: bool,
                                   line_type: Optional[Dict[str, Any]],
                                   order_type: Optional[Dict[str, Any]],
                                   order: Dict[str, Any]) -> None:
        """R-RET-1~8：退货行引用原行的合法性。引用为空直接放行。"""
        old = old_data or {}
        reference_line_id = data.get(RETURN_REFERENCE_FIELD)
        if RETURN_REFERENCE_FIELD not in data and not is_create:
            reference_line_id = old.get(RETURN_REFERENCE_FIELD)
        if _is_blank(reference_line_id):
            return

        # R-RET-1：引用只属于「退货订单 + 退货行」
        if (order_type or {}).get('document_category') != RETURN_CATEGORY \
                or (line_type or {}).get('line_category') != RETURN_CATEGORY:
            raise SalesOrderGuardError(
                '只有退货订单的退货行可以填写原订单行',
                field_name=RETURN_REFERENCE_FIELD, rule='return_ref_not_allowed')

        # R-RET-2：引用行必须存在（读失败不判定）
        found, ref = self._load_reference_line(reference_line_id)
        if not found:
            return
        if not ref:
            raise SalesOrderGuardError(
                f'原订单行 {reference_line_id} 不存在',
                field_name=RETURN_REFERENCE_FIELD, rule='return_ref_not_found')

        # R-RET-3：不得引用本单（含自身）
        order_id = data.get('order_id')
        if _is_blank(order_id):
            order_id = order.get('id')
        if str(ref.get('order_id')) == str(order_id):
            raise SalesOrderGuardError(
                '退货行不能引用当前订单内的行，请选择其他订单的原行',
                field_name=RETURN_REFERENCE_FIELD, rule='return_ref_same_order')

        # R-RET-4：原行及其订单都不得是退货
        ref_line_type = (self._load_type(ref.get('line_type_id'))
                         if not _is_blank(ref.get('line_type_id')) else None)
        ref_order_type = (self._load_type(ref.get('ref_order_type_id'))
                          if not _is_blank(ref.get('ref_order_type_id')) else None)
        if (ref_line_type or {}).get('line_category') == RETURN_CATEGORY \
                or (ref_order_type or {}).get('document_category') == RETURN_CATEGORY:
            raise SalesOrderGuardError(
                '原订单行属于退货单 / 退货行，不能再被退货引用',
                field_name=RETURN_REFERENCE_FIELD, rule='return_ref_not_return')

        # R-RET-5：原单须已确认 / 关闭，避免对未生效订单预开退货
        ref_status = ref.get('ref_order_status')
        if not _is_blank(ref_status) and ref_status not in _CONFIRMED_STATES:
            raise SalesOrderGuardError(
                f'原订单处于 {ref_status} 状态，只有 confirmed / closed 可开退货',
                field_name=RETURN_REFERENCE_FIELD,
                rule='return_ref_order_not_confirmed')

        # R-RET-6：退货单客户须与原单客户一致
        customer_id = order.get('customer_account_id')
        ref_customer_id = ref.get('ref_customer_account_id')
        if not _is_blank(customer_id) and not _is_blank(ref_customer_id) \
                and str(customer_id) != str(ref_customer_id):
            raise SalesOrderGuardError(
                '退货单客户与原订单客户不一致',
                field_name=RETURN_REFERENCE_FIELD,
                rule='return_ref_customer_mismatch')

        # R-RET-7：双方都有物料时须一致
        item_id = data.get('item_id')
        if item_id is None and not is_create:
            item_id = old.get('item_id')
        if not _is_blank(item_id) and not _is_blank(ref.get('item_id')) \
                and str(item_id) != str(ref.get('item_id')):
            raise SalesOrderGuardError(
                '退货行物料与原订单行不一致',
                field_name=RETURN_REFERENCE_FIELD,
                rule='return_ref_item_mismatch')

        # R-RET-8：累计退货量不得超过原行数量（当前行按 id 排除）
        qty = _num(data.get('qty'))
        if qty is None and not is_create:
            qty = _num(old.get('qty'))
        original_qty = _num(ref.get('qty'))
        if qty is None or original_qty is None:
            return
        current_id = data.get('id')
        if _is_blank(current_id) and not is_create:
            current_id = old.get('id')
        returned = self._sum_returned_qty(
            reference_line_id, exclude_line_id=current_id)
        if returned is None:
            return
        if returned + qty > original_qty + _QTY_TOLERANCE:
            raise SalesOrderGuardError(
                f'累计退货量 {returned + qty:g} 超过原行数量 {original_qty:g}',
                field_name='qty', rule='return_qty_exceeded')

    def _has_return_refs(self, line_id: Any) -> bool:
        """原行是否被退货行引用（R-RET-9）；查询失败 fail-open。"""
        try:
            rows = self.ds.query(
                'SELECT 1 FROM sales_order_lines '
                'WHERE reference_line_id = ? LIMIT 1', [line_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 读取退货引用 {line_id} 失败: {e}')
            return False
        return bool(rows)

    def _sum_returned_qty(self, reference_line_id: Any,
                          exclude_line_id: Any = None):
        """原行已发生的退货数量合计；排除当前行与已取消行 / 单。

        返回 None 表示查询失败（fail-open，R-RET-8 不判定）。
        """
        sql = ('SELECT COALESCE(SUM(rl.qty), 0) AS qty '
               'FROM sales_order_lines rl '
               'JOIN sales_orders ro ON ro.id = rl.order_id '
               'WHERE rl.reference_line_id = ? '
               "  AND rl.status <> 'cancelled' "
               "  AND ro.status <> 'cancelled'")
        params = [reference_line_id]
        if not _is_blank(exclude_line_id):
            sql += ' AND rl.id <> ?'
            params.append(exclude_line_id)
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 汇总退货数量 {reference_line_id} 失败: {e}')
            return None
        if not rows:
            return 0.0
        return _num(rows[0].get('qty')) or 0.0

    def _org_has_function(self, org_id: Any, function_type: str) -> bool:
        try:
            rows = self.ds.query(
                'SELECT 1 FROM org_functions WHERE org_id = ? AND function_type = ? '
                'LIMIT 1', [org_id, function_type])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[sales_order_guard] 读取组织职能 {org_id} 失败: {e}')
            return True
        return bool(rows)

    # ---------------- 计划行（R-SCH-0 ~ R-SCH-10） ----------------

    def validate_schedule_write(self, data: Dict[str, Any],
                                old_data: Optional[Dict[str, Any]] = None,
                                is_create: bool = True) -> None:
        """计划行创建 / 更新前校验。

        `data` 是「写入后的有效行」（更新场景 = 旧行 ∪ 本次参数）。
        读侧异常一律 fail-open：取不到订单 / 订单行时不做判定，
        缺失引用交给外键与必填校验兜底。
        """
        old = old_data or {}
        kind = data.get('schedule_kind')

        # R-SCH-10：kind 门控（三值已声明，本波只启用 delivery）
        if not _is_blank(kind) and str(kind) not in SCHEDULE_KINDS_ENABLED:
            raise SalesOrderGuardError(
                f'计划类型 {kind} 尚未启用（当前可用：'
                f'{"/".join(SCHEDULE_KINDS_ENABLED)}）',
                field_name='schedule_kind', rule='SCHEDULE_KIND_NOT_ENABLED')

        # R-SCH-1 / R-SCH-14：承诺日期必填（billing 的承诺日期即收款日）
        if _is_blank(data.get('promised_date')):
            if str(kind) == 'billing':
                raise SalesOrderGuardError(
                    'billing 计划行必须填写收款日期',
                    field_name='promised_date', rule='BILLING_DATE_REQUIRED')
            raise SalesOrderGuardError(
                '计划行必须填写承诺日期',
                field_name='promised_date', rule='SCHEDULE_DATE_REQUIRED')

        # R-SCH-6：里程碑码长度上限（本波只是自由字符串，不做存在性校验）
        milestone = data.get('milestone_code')
        if not _is_blank(milestone) and len(str(milestone)) > SCHEDULE_MILESTONE_MAX:
            raise SalesOrderGuardError(
                f'里程碑码长度不得超过 {SCHEDULE_MILESTONE_MAX} 个字符',
                field_name='milestone_code', rule='MILESTONE_CODE_TOO_LONG')

        line_id = data.get('line_id')
        order_id = data.get('order_id')
        line = self._load_line_schedule_context(line_id) \
            if not _is_blank(line_id) else None

        # R-SCH-0：计划行所属订单必须与订单行一致
        if line and not _is_blank(order_id) \
                and str(order_id) != str(line.get('order_id')):
            raise SalesOrderGuardError(
                f'计划行所属订单（{order_id}）与订单行所属订单'
                f'（{line.get("order_id")}）不一致',
                field_name='order_id', rule='SCHEDULE_ORDER_MISMATCH')

        # R-SCH-5：订单离开草稿后禁止新增，只允许改期 / 改量 / 改发货点
        #        （billing 收窄为改收款日 / 改状态，比例由 R-SCH-15 判定）
        parent_order_id = order_id if not _is_blank(order_id) \
            else (line or {}).get('order_id')
        order = self._load_order(parent_order_id) \
            if not _is_blank(parent_order_id) else {}
        parent_status = (order or {}).get('status')
        if parent_status and parent_status != DRAFT:
            if is_create:
                raise SalesOrderGuardError(
                    f'订单处于 {parent_status} 状态，不允许新增计划行',
                    field_name='status', rule='SCHEDULE_LOCKED')
            if str(kind) == 'billing':
                editable = SCHEDULE_BILLING_EDITABLE_AFTER_DRAFT
                # billing_percent 不参与本规则的冻结比对（R-SCH-15 专管）
                frozen = [f for f in data
                          if f not in editable and f != 'billing_percent']
            else:
                editable = SCHEDULE_EDITABLE_AFTER_DRAFT
                frozen = [f for f in data if f not in editable]
            changed = [f for f in frozen
                       if str(data.get(f)) != str(old.get(f))]
            if changed:
                raise SalesOrderGuardError(
                    f'订单处于 {parent_status} 状态，计划行只允许修改 '
                    f'{"/".join(editable)}',
                    field_name=changed[0], rule='SCHEDULE_LOCKED')

        if str(kind) == 'billing':
            # R-SCH-2：billing 不承诺数量
            if not _is_blank(data.get('promised_qty')):
                raise SalesOrderGuardError(
                    'billing 计划行不承诺数量，promised_qty 必须留空',
                    field_name='promised_qty', rule='BILLING_QTY_NOT_ALLOWED')

            # R-SCH-12：billing 不涉及发货点 / 服务次数
            for field in ('plant_location_id', 'service_visit_no'):
                if not _is_blank(data.get(field)):
                    raise SalesOrderGuardError(
                        f'billing 计划行不得填写 {field}',
                        field_name=field, rule='BILLING_FIELD_NOT_ALLOWED')

            old_pct = _num(old.get('billing_percent'))
            new_pct = _num(data.get('billing_percent'))
            # R-SCH-15：非草稿订单冻结收款比例（旧值非空且本次变更）
            if not is_create and parent_status and parent_status != DRAFT \
                    and old_pct is not None and 'billing_percent' in data:
                if new_pct is None \
                        or abs(new_pct - old_pct) > BILLING_PERCENT_TOLERANCE:
                    raise SalesOrderGuardError(
                        f'订单处于 {parent_status} 状态，billing_percent 已冻结',
                        field_name='billing_percent',
                        rule='BILLING_PERCENT_LOCKED')

            # R-SCH-11：收款比例必填且 0 < p ≤ 100
            if _is_blank(data.get('billing_percent')):
                raise SalesOrderGuardError(
                    'billing 计划行必须填写收款比例',
                    field_name='billing_percent', rule='BILLING_PERCENT_REQUIRED')
            if new_pct is None or new_pct <= 0 or new_pct > 100:
                raise SalesOrderGuardError(
                    f'收款比例须大于 0 且不超过 100（当前 {new_pct}）',
                    field_name='billing_percent', rule='BILLING_PERCENT_RANGE')

            # R-SCH-13：同一订单行的 billing 比例合计 ≤ 100（作废行不占）
            if not _is_blank(line_id):
                planned = self._sum_billing_percent(
                    line_id, exclude_id=data.get('id'))
                total = planned + new_pct
                if total > 100 + BILLING_PERCENT_TOLERANCE:
                    raise SalesOrderGuardError(
                        f'本行 billing 收款比例合计（{total:g}）超过 100',
                        field_name='billing_percent',
                        rule='BILLING_PERCENT_SUM_EXCEEDED')

        elif str(kind) == 'delivery':
            # R-SCH-16：交货不相关的订单行（行类型 delivery_relevant=false）
            # 不允许建 delivery 计划行。取不到行时 fail-open（列缺失由迁移兜底）。
            relevant = (line or {}).get('delivery_relevant')
            if relevant is not None and not int(relevant):
                raise SalesOrderGuardError(
                    '该订单行的行类型为「不交货相关」，不允许创建交货计划行',
                    field_name='schedule_kind',
                    rule='SCHEDULE_NOT_DELIVERY_RELEVANT')
            qty = _num(data.get('promised_qty'))
            # R-SCH-3：承诺量必填且 > 0
            if qty is None or qty <= 0:
                raise SalesOrderGuardError(
                    'delivery 计划行必须填写大于 0 的承诺数量',
                    field_name='promised_qty', rule='DELIVERY_QTY_INVALID')
            # R-SCH-3：同一行 delivery 合计 ≤ 行 qty（作废行不占量）
            line_qty = _num((line or {}).get('qty'))
            if not _is_blank(line_id) and line_qty is not None:
                consumed = self._sum_delivery_qty(line_id, exclude_id=data.get('id'))
                if consumed + qty > line_qty + 1e-9:
                    raise SalesOrderGuardError(
                        f'本行 delivery 承诺量合计（{consumed + qty:g}）'
                        f'超过订单行数量（{line_qty:g}）',
                        field_name='promised_qty', rule='DELIVERY_QTY_EXCEEDED')
            # R-SCH-7：发货点必填（默认继承订单行）
            if _is_blank(data.get('plant_location_id')) \
                    and _is_blank((line or {}).get('plant_location_id')):
                raise SalesOrderGuardError(
                    'delivery 计划行必须指定发货点（订单行未指定时请本行显式填写）',
                    field_name='plant_location_id', rule='SCHEDULE_PLANT_REQUIRED')

        elif str(kind) == 'service':
            # R-SCH-4：服务次数必填（行内唯一由部分唯一索引兜底）
            if _is_blank(data.get('service_visit_no')):
                raise SalesOrderGuardError(
                    'service 计划行必须填写服务次数',
                    field_name='service_visit_no',
                    rule='SERVICE_VISIT_NO_REQUIRED')

        # R-SCH-9：状态流转须符合 §2.3 图，终态不可回退 / 复活
        new_status = data.get('status')
        if not _is_blank(new_status) and str(new_status) not in SCHEDULE_STATUSES:
            raise SalesOrderGuardError(
                f'计划行状态 {new_status} 不属于 {"/".join(SCHEDULE_STATUSES)}',
                field_name='status', rule='SCHEDULE_STATUS_INVALID')
        if not is_create and not _is_blank(new_status):
            old_status = old.get('status')
            if old_status and str(new_status) != str(old_status):
                if str(old_status) in SCHEDULE_TERMINAL:
                    raise SalesOrderGuardError(
                        f'计划行已处于终态 {old_status}，不可再变更状态',
                        field_name='status', rule='SCHEDULE_STATUS_INVALID')
                allowed = SCHEDULE_TRANSITIONS.get(str(old_status), ())
                if str(new_status) not in allowed:
                    raise SalesOrderGuardError(
                        f'计划行状态不允许从 {old_status} 变为 {new_status}'
                        f'（允许：{"/".join(allowed) or "无"}）',
                        field_name='status', rule='SCHEDULE_STATUS_INVALID')

    def validate_schedule_delete(self, schedule_id: Any) -> None:
        """R-SCH-8：仅 draft 且未被任何派生边引用时允许物理删除。

        作废请改 `status=cancelled`，不要物理删。
        """
        if _is_blank(schedule_id):
            return
        schedule = self._load_schedule(schedule_id) or {}
        order_id = schedule.get('order_id')
        order = self._load_order(order_id) if not _is_blank(order_id) else {}
        status = (order or {}).get('status')
        if status and status != DRAFT:
            raise SalesOrderGuardError(
                f'订单处于 {status} 状态，计划行不可删除（请改 status=cancelled 作废）',
                field_name='status', rule='SCHEDULE_DELETE_FORBIDDEN')
        if self._has_schedule_derivation_refs(schedule_id):
            raise SalesOrderGuardError(
                '该计划行已被派生单据引用，不可物理删除（请作废）',
                field_name='id', rule='SCHEDULE_DELETE_FORBIDDEN')

    def _load_schedule(self, schedule_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                f'SELECT id, order_id, line_id, schedule_no, schedule_kind, '
                f'       promised_date, promised_qty, plant_location_id, '
                f'       milestone_code, service_visit_no, status '
                f'FROM {SCHEDULE_TABLE} WHERE id = ?', [schedule_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 读取计划行 {schedule_id} 失败: {e}')
            return None
        return rows[0] if rows else None

    def _load_line_schedule_context(self, line_id: Any) -> Optional[Dict[str, Any]]:
        """计划行判定所需的订单行上下文（订单归属 / 数量 / 发货点 / 交货相关性）。

        独立于 `_load_line`（后者被 12+ 处既有规则复用，不改其列集）。
        `delivery_relevant` 取自行类型级配置（等价 SAP TVAP-LFREL）。
        """
        try:
            rows = self.ds.query(
                'SELECT l.id, l.order_id, l.qty, l.uom_id, l.plant_location_id, '
                '       COALESCE(t.delivery_relevant, 1) AS delivery_relevant '
                'FROM sales_order_lines l '
                'LEFT JOIN type_definitions t ON t.id = l.line_type_id '
                'WHERE l.id = ?', [line_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 读取计划行上下文（订单行 {line_id}）失败: {e}')
            return None
        return rows[0] if rows else None

    def _sum_delivery_qty(self, line_id: Any, exclude_id: Any = None) -> float:
        """同一行已承诺的 delivery 数量合计（作废行不占量）。"""
        sql = (f'SELECT COALESCE(SUM(promised_qty), 0) AS qty '
               f'FROM {SCHEDULE_TABLE} '
               f"WHERE line_id = ? AND schedule_kind = 'delivery' "
               f"  AND status <> 'cancelled'")
        params = [line_id]
        if not _is_blank(exclude_id):
            sql += ' AND id <> ?'
            params.append(exclude_id)
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 汇总计划行数量（订单行 {line_id}）失败: {e}')
            return 0.0
        if not rows:
            return 0.0
        return _num(rows[0].get('qty')) or 0.0

    def _sum_billing_percent(self, line_id: Any,
                             exclude_id: Any = None) -> float:
        """同一行已排的 billing 收款比例合计（作废行不占比例）。"""
        sql = (f'SELECT COALESCE(SUM(billing_percent), 0) AS pct '
               f'FROM {SCHEDULE_TABLE} '
               f"WHERE line_id = ? AND schedule_kind = 'billing' "
               f"  AND status <> 'cancelled'")
        params = [line_id]
        if not _is_blank(exclude_id):
            sql += ' AND id <> ?'
            params.append(exclude_id)
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 汇总计划行比例（订单行 {line_id}）失败: {e}')
            return 0.0
        if not rows:
            return 0.0
        return _num(rows[0].get('pct')) or 0.0

    def _has_schedule_derivation_refs(self, schedule_id: Any) -> bool:
        """计划行是否已被派生边引用（doc_flow_edges.source_bo + source_id）。"""
        try:
            rows = self.ds.query(
                'SELECT 1 FROM doc_flow_edges '
                'WHERE source_bo = ? AND source_id = ? LIMIT 1',
                [SCHEDULE_OBJECT, str(schedule_id)])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(
                f'[sales_order_guard] 读取计划行派生边 {schedule_id} 失败: {e}')
            return False
        return bool(rows)
