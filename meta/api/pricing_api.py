# -*- coding: utf-8 -*-
"""
定价引擎 API（Pricing Engine）
==============================

把 `PricingService`（T1-4）的三条能力暴露为 HTTP 端点：

    POST /api/v1/pricing/calculate                     逐行定价（IF-001）
    GET  /api/v1/pricing/result/<document_type>/<id>   结果回放（IF-002）
    POST /api/v1/pricing/write-back                    结果写回单据（IF-003）

[分摊不在本模块 · 2026-10-07] 分摊（IF-004）原挂 `/api/v1/pricing/allocate`，
现已提升为**平台级**能力并迁至 `meta/api/allocation_api.py`
（`POST /api/v1/allocation/allocate`）——算法层零业务耦合，留痕层已拆出
独立表 `allocation_results`，与定价**物理隔离**，路径不该再挂在 pricing 下。
**旧路径不留别名**（仓库内外均无调用方）。详见 Spec TBD-18。

[分层] api 层**只做参数校验与响应包装**，业务全在
`meta/services/pricing_service.py`。故本模块的测试属"契约测试"：
发请求 → 断言响应字段名与类型，不重复测业务正确性。

[路径命名] 路径里的 `document_type` 即 `calc_result.document_type`
（本仓 `bo_sub_category: document` 型 BO 的 id，如 `sales_order_enhanced`），
`document_id` 为其记录 id。与三表列名一字不差，避免"接口叫 A、表叫 B"
的翻译层——回放/写回都是按这两列定位的。

[错误码映射] 内核异常**不兜底**，按语义映射为不同状态码：

    400  PricingError        编排层无法完成（过程/价目表/查找序列不存在）
    422  ResolutionError     候选消解失败（权重和≠1，配置矛盾，需改配置后重试）
    422  CalculationError    计算过程结构性矛盾（未注册 element_type 等）
    400/404/422  AllocationError  分摊参数错 / 规则或父行不存在 / 地板价无解

400 与 422 的分界是"**改请求**还是**改配置**"：前者传错参数即可修复，
后者参数没错、是配置本身矛盾。`AllocationError` 自带 `status_code`，
映射直接取用，避免同一张映射表在两处维护而漂移。
"""
import logging
from typing import Any, Dict, Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.core.calc_procedure_executor import CalculationError
from meta.core.lookup_resolver import (
    RESOLUTION_BEST,
    RESOLUTION_EXCLUSIVE,
    RESOLUTION_PRECEDENCE,
    RESOLUTION_WEIGHTED,
    ResolutionError,
)
from meta.services.allocation_service import AllocationError
from meta.services.auth_middleware import login_required
from meta.services.pricing_service import PricingError, PricingService

logger = logging.getLogger(__name__)

pricing_bp = Blueprint('pricing', __name__, url_prefix='/api/v1/pricing')

# FR-008 四范式。放白名单在**入口**拦非法值：否则内核报"未知消解范式"
# 会走 ResolutionError → 422，把"参数写错"误标成"配置矛盾"。
RESOLUTIONS = frozenset({
    RESOLUTION_PRECEDENCE, RESOLUTION_BEST,
    RESOLUTION_EXCLUSIVE, RESOLUTION_WEIGHTED,
})

# calc_result.level 的枚举，且 yaml 声明了不变量：
#   level ↔ document_line_id 的空值必须一致（header⟺NULL / line⟺非 NULL）
LEVELS = frozenset({"header", "line"})

_service: Optional[PricingService] = None


def init_services(data_source=None) -> PricingService:
    """初始化服务。测试传入内存数据源；生产懒取 meta 库。

    [WARNING] 数据库路径必须走 `get_meta_db_path()`，禁止相对路径。
    """
    global _service
    if data_source is not None:
        _service = PricingService(data_source)
    elif _service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        _service = PricingService(
            get_data_source('sqlite', database=get_meta_db_path())
        )
    return _service


def _get_service() -> PricingService:
    return init_services()


# ----------------------------------------------------------------------
# 参数校验
# ----------------------------------------------------------------------
class _ParamError(Exception):
    """客户端参数错误（400）。与内核异常区分：这是"请求本身不合法"。"""


def _json_body() -> Dict[str, Any]:
    body = request.get_json(force=True, silent=True)
    return body if isinstance(body, dict) else {}


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _as_int(v: Any, label: str) -> int:
    """转 int。**bool 不算数字**——True 会被 int() 静默变成 1，属误传。"""
    if isinstance(v, bool):
        raise _ParamError(f"{label} 必须为整数")
    try:
        return int(v)
    except (TypeError, ValueError):
        raise _ParamError(f"{label} 必须为整数")


def _as_number(v: Any, label: str) -> float:
    if isinstance(v, bool):
        raise _ParamError(f"{label} 必须为数值")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise _ParamError(f"{label} 必须为数值")


def _req_str(body: Dict[str, Any], key: str) -> str:
    v = body.get(key)
    if _is_blank(v):
        raise _ParamError(f"缺少必填参数：{key}")
    return str(v).strip()


def _req_int(body: Dict[str, Any], key: str) -> int:
    if _is_blank(body.get(key)):
        raise _ParamError(f"缺少必填参数：{key}")
    return _as_int(body[key], key)


def _req_number(body: Dict[str, Any], key: str) -> float:
    if _is_blank(body.get(key)):
        raise _ParamError(f"缺少必填参数：{key}")
    return _as_number(body[key], key)


def _opt_int(body: Dict[str, Any], key: str) -> Optional[int]:
    v = body.get(key)
    return None if _is_blank(v) else _as_int(v, key)


def _fail(exc: Exception):
    """内核/参数异常 → 契约错误响应。未识别异常继续上抛（全局 500 处理）。"""
    if isinstance(exc, _ParamError):
        return error_response(str(exc), code="INVALID_PARAM", status=400)
    if isinstance(exc, PricingError):
        return error_response(str(exc), code="PRICING_ERROR", status=400)
    if isinstance(exc, ResolutionError):
        return error_response(str(exc), code="RESOLUTION_ERROR", status=422)
    if isinstance(exc, CalculationError):
        return error_response(str(exc), code="CALCULATION_ERROR", status=422)
    if isinstance(exc, AllocationError):
        # 分摊层自带 status_code：400 参数错 / 404 规则或父行不存在 /
        # 422 配置矛盾（floor 无解、基数列缺值）。此处不另造映射表——
        # 两处维护同一张表必然漂移。
        return error_response(str(exc), code="ALLOCATION_ERROR",
                              status=getattr(exc, "status_code", 400))
    raise exc


# ----------------------------------------------------------------------
# IF-001 逐行定价
# ----------------------------------------------------------------------
@pricing_bp.route('/calculate', methods=['POST'])
@login_required
def calculate():
    """对一行执行定价：查表（FR-004）→ 算过程（FR-005/006/007）→ 落结果与明细。

    请求体：
        process_code      必填  定价过程编码（calc_procedures.code）
        rate_table_id     必填  价目表 id（**仅 approved 参与取价**，C-T0-11）
        base              必填  计算基数
        slot_keys         选填  与查找序列槽位等长的键值数组，如 [{"customer": 1001}]
        sequence_code     选填  查找序列编码；**留空则跳过查表**，只算过程
        document_type     选填  泛化宿主 BO id（落库必需，见下）
        document_id       选填  宿主记录 id
        document_line_id  选填  行 id；缺省 = 头级（level=header）
        level             选填  header | line；**缺省由 document_line_id 推导**
        resolution        选填  候选消解范式（precedence/best/exclusive/weighted）
        measure           选填  `best` 范式的度量（如 min_amount）；**best 必填**
        valid_on          选填  有效期（含下不含上）
        persist           选填  默认 true；false = 只算不落库（预览）

    [契约] `persist=true` 且给了 `document_type` 但缺 `document_id` 时**报 400**，
    而不是静默跳过落库——否则调用方拿到 `result_id: null` 会以为"算过了"。
    """
    try:
        body = _json_body()
        process_code = _req_str(body, 'process_code')
        rate_table_id = _req_int(body, 'rate_table_id')
        base = _req_number(body, 'base')

        slot_keys = body.get('slot_keys')
        if slot_keys is None:
            slot_keys = []
        if not isinstance(slot_keys, list):
            raise _ParamError('slot_keys 必须为数组')
        for i, k in enumerate(slot_keys):
            if not isinstance(k, dict):
                raise _ParamError(f'slot_keys[{i}] 必须为对象（键 → 值）')

        document_type = body.get('document_type') or None
        document_id = _opt_int(body, 'document_id')
        document_line_id = _opt_int(body, 'document_line_id')
        persist = bool(body.get('persist', True))

        if persist and document_type and document_id is None:
            raise _ParamError(
                'persist=true 且给出 document_type 时必须提供 document_id'
                '（否则无法落库）；仅想试算请传 persist=false'
            )
        if document_line_id is not None and document_id is None:
            raise _ParamError('document_line_id 不能脱离 document_id 单独给出')

        # level 缺省由 document_line_id 推导，并强制两者一致 ——
        # calc_result.yaml 的不变量是「level ↔ document_line_id 空值一致」，
        # 放任不一致会写进一条自相矛盾的结果行（level=line 却无行）。
        level = (body.get('level') or '').strip() or (
            'line' if document_line_id is not None else 'header'
        )
        if level not in LEVELS:
            raise _ParamError(
                f"level 只能为 header 或 line，收到：{level!r}"
            )
        if level == 'line' and document_line_id is None:
            raise _ParamError('level=line 必须提供 document_line_id')
        if level == 'header' and document_line_id is not None:
            raise _ParamError('level=header 不能带 document_line_id（头级无行）')

        resolution = body.get('resolution') or RESOLUTION_PRECEDENCE
        if resolution not in RESOLUTIONS:
            raise _ParamError(
                f"resolution 非法：{resolution!r}；可选 {sorted(RESOLUTIONS)}"
            )
        measure = body.get('measure') or None
        if resolution == RESOLUTION_BEST and not measure:
            # 「Best Price 绝不隐式默认」——缺度量属参数没给全，不是配置矛盾
            raise _ParamError('resolution=best 必须显式提供 measure（如 min_amount）')

        data = _get_service().price_line(
            process_code,
            rate_table_id,
            slot_keys,
            base,
            sequence_code=body.get('sequence_code') or None,
            document_type=document_type,
            document_id=document_id,
            document_line_id=document_line_id,
            level=level,
            resolution=resolution,
            measure=measure,
            valid_on=body.get('valid_on') or None,
            persist=persist,
        )
    except Exception as exc:
        return _fail(exc)
    return ok(data)


# ----------------------------------------------------------------------
# IF-002 结果回放
# ----------------------------------------------------------------------
@pricing_bp.route('/result/<document_type>/<int:document_id>', methods=['GET'])
@login_required
def get_result(document_type: str, document_id: int):
    """回放某单据的 active 定价结果：结果行 + 步骤明细 + 逐层小计。

    查询参数：
        document_line_id  选填  行 id；缺省则返回该头级 + 所有行的结果
    """
    try:
        raw = request.args.get('document_line_id')
        line_id = None if _is_blank(raw) else _as_int(raw, 'document_line_id')
        data = _get_service().explain(document_type, document_id, line_id)
    except Exception as exc:
        return _fail(exc)
    return ok(data)


# ----------------------------------------------------------------------
# IF-003 结果写回
# ----------------------------------------------------------------------
@pricing_bp.route('/write-back', methods=['POST'])
@login_required
def write_back():
    """把 active 定价结果写回业务单据字段（按 `result_semantic` 约定映射）。

    请求体：
        document_type     必填
        document_id       必填
        document_line_id  选填  行级写回时传；缺省 = 头级（只写金额，不写单价）

    返回 `{'written': {...}, 'skipped': [...], 'result_ids': [...]}`；
    `skipped` 非空表示部分语义/字段无对应列，**属正常结果不是错误**。
    """
    try:
        body = _json_body()
        document_type = _req_str(body, 'document_type')
        document_id = _req_int(body, 'document_id')
        document_line_id = _opt_int(body, 'document_line_id')
        data = _get_service().write_back(
            document_type, document_id, document_line_id
        )
    except Exception as exc:
        return _fail(exc)
    return ok(data)
