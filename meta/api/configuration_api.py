# -*- coding: utf-8 -*-
"""配置域 API（Configuration Price / Match / Solve / Materialize）
================================================================

把 P4 的四条能力暴露为 HTTP 端点：

    POST /api/v1/config/price        配置实例出价（PriceRequest → PriceResult）
    POST /api/v1/config/match        `one_time_standard` 复用入口
    POST /api/v1/config/solve        求解并串接复用（solve → match）
    POST /api/v1/config/materialize  把已求解/已冻结的实例固化为 draft 变式物料

[分层] api 层**只做参数校验与响应包装**，业务在
`configuration_price_service` / `configuration_match_service` /
`item_structure_config_service` / `variant_item_materialize_service`。故本模块测试属"契约测试"：断言状态码、
字段名与类型，不重复测业务正确性。

[solve → match] `solve` 服务自身行为与状态保持不变（P3 基线零回归），
复用由本层在求解成功后调用 `match` 串接；模型策略非
`one_time_standard` 时 `match` 原样返回、不产生写操作。

[错误码映射] 域内错误只有 `ItemStructureConfigError` 一族，按语义分档：

    404  实例 / 结构不存在（rule: configuration_not_found / item_structure_not_found）
    400  CONFIG_INVALID_VALUE（请求参数与实例内容矛盾，改请求可修复）
    409  CONFIG_VERSION_MISMATCH（实例状态或模型版本不允许本次操作）
    422  CONFIG_CONFLICT / CONFIG_INCOMPLETE / CONFIG_PRICE_MISSING / CONFIG_TIMEOUT
         （参数没错，需改配置或补主数据后重试）

权限：不新增对象，`price` / `match` / `solve` 同挂 `configuration` 的 read
（双段式码 `configuration:configuration_read` 由 v117 落库）。
"""
import logging
from typing import Any, Dict, Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.api.decorators import require_permission
from meta.services.auth_middleware import login_required
from meta.services.configuration_match_service import ConfigurationMatchService
from meta.services.configuration_price_service import ConfigurationPriceService
from meta.services.item_structure_config_service import (
    ItemStructureConfigError,
    ItemStructureConfigService,
)
from meta.services.variant_item_materialize_service import (
    MaterializeError,
    VariantItemMaterializeService,
)

logger = logging.getLogger(__name__)

configuration_bp = Blueprint(
    'configuration', __name__, url_prefix='/api/v1/config')

_NOT_FOUND_RULES = frozenset({
    'configuration_not_found', 'item_structure_not_found',
})

_CLIENT_CODES = frozenset({'CONFIG_INVALID_VALUE'})

#: 物化错误码 → HTTP 状态（spec §2 D2 / D4）
_MATERIALIZE_STATUS = {
    'CONFIG_NOT_FOUND': 404,
    'MODEL_NOT_FOUND': 404,
    'CONFIG_NOT_SOLVED': 409,
    'MATERIALIZE_DISABLED': 409,
    'MODEL_NOT_TRADABLE': 409,
    'CONFIG_HASH_MISSING': 422,
    'ITEM_CODE_TOO_LONG': 422,
    'CODE_CONFLICT': 422,
}

_price_service: Optional[ConfigurationPriceService] = None
_match_service: Optional[ConfigurationMatchService] = None
_config_service: Optional[ItemStructureConfigService] = None
_materialize_service: Optional[VariantItemMaterializeService] = None


def init_services(data_source=None) -> ConfigurationPriceService:
    """初始化四个服务。测试传入内存数据源；生产懒取 meta 库。

    [WARNING] 数据库路径必须走 `get_meta_db_path()`，禁止相对路径。
    """
    global _price_service, _match_service, _config_service, _materialize_service
    if data_source is not None:
        _price_service = ConfigurationPriceService(data_source)
        _match_service = ConfigurationMatchService(data_source)
        _config_service = ItemStructureConfigService(data_source)
        _materialize_service = VariantItemMaterializeService(data_source)
    elif (_price_service is None or _match_service is None
          or _config_service is None or _materialize_service is None):
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        data_source = get_data_source('sqlite', database=get_meta_db_path())
        _price_service = ConfigurationPriceService(data_source)
        _match_service = ConfigurationMatchService(data_source)
        _config_service = ItemStructureConfigService(data_source)
        _materialize_service = VariantItemMaterializeService(data_source)
    return _price_service


def _get_price_service() -> ConfigurationPriceService:
    init_services()
    return _price_service


def _get_match_service() -> ConfigurationMatchService:
    init_services()
    return _match_service


def _get_config_service() -> ItemStructureConfigService:
    init_services()
    return _config_service


def _get_materialize_service() -> VariantItemMaterializeService:
    init_services()
    return _materialize_service


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


def _as_bool(v: Any, label: str) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ('true', 'false'):
        return v.strip().lower() == 'true'
    raise _ParamError(f"{label} 必须为布尔值")


def _req_int(body: Dict[str, Any], key: str) -> int:
    if _is_blank(body.get(key)):
        raise _ParamError(f"缺少必填参数：{key}")
    return _as_int(body[key], key)


def _opt_int(body: Dict[str, Any], key: str,
             default: Optional[int] = None) -> Optional[int]:
    v = body.get(key)
    return default if _is_blank(v) else _as_int(v, key)


def _opt_str(body: Dict[str, Any], key: str) -> Optional[str]:
    v = body.get(key)
    return None if _is_blank(v) else str(v).strip()


def _opt_dict(body: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    v = body.get(key)
    if _is_blank(v):
        return None
    if not isinstance(v, dict):
        raise _ParamError(f"{key} 必须为对象")
    return v


def _opt_bool(body: Dict[str, Any], key: str, default: bool) -> bool:
    v = body.get(key)
    return default if _is_blank(v) else _as_bool(v, key)


def _fail(exc: Exception):
    """域内异常 → 契约错误响应。未识别异常继续上抛（全局 500 处理）。"""
    if isinstance(exc, _ParamError):
        return error_response(str(exc), code="INVALID_PARAM", status=400)
    if isinstance(exc, ItemStructureConfigError):
        if exc.rule in _NOT_FOUND_RULES:
            status = 404
        elif exc.code in _CLIENT_CODES:
            status = 400
        elif exc.code == 'CONFIG_VERSION_MISMATCH':
            status = 409
        else:
            status = 422
        details: Dict[str, Any] = {'rule': exc.rule}
        if exc.field_name:
            details['field'] = exc.field_name
        if exc.configuration_id is not None:
            details['configuration_id'] = exc.configuration_id
        if exc.conflicts:
            details['conflicts'] = exc.conflicts
        if exc.warnings:
            details['warnings'] = exc.warnings
        return error_response(str(exc), code=exc.code, status=status,
                              details=details)
    if isinstance(exc, MaterializeError):
        status = _MATERIALIZE_STATUS.get(exc.code, 422)
        details: Dict[str, Any] = {'code': exc.code}
        if exc.configuration_id is not None:
            details['configuration_id'] = exc.configuration_id
        return error_response(str(exc), code=exc.code, status=status,
                              details=details)
    raise exc


# ----------------------------------------------------------------------
# 出价
# ----------------------------------------------------------------------
@configuration_bp.route('/price', methods=['POST'])
@login_required
def price():
    """对配置实例出价，返回 `PriceResult`。

    请求体：
        configuration_id  必填  配置实例 id
        price_source      选填  none | component_price | base_plus_option
                                 | attribute_matrix | calculated；缺省 none
        pricing_context   选填  定价域上下文（过程编码 / 价目表 / 币种 /
                                 日期 / 槽位键 / 定价归属）
        resolved          选填  调用方展开结果；只用于比对，不一致即拒绝
    """
    try:
        body = _json_body()
        configuration_id = _req_int(body, 'configuration_id')
        price_source = _opt_str(body, 'price_source')
        pricing_context = _opt_dict(body, 'pricing_context')

        resolved = body.get('resolved')
        if not _is_blank(resolved) and not isinstance(resolved, (dict, list)):
            raise _ParamError('resolved 需为组件列表或含 components 的对象')

        data = _get_price_service().price(
            configuration_id,
            price_source=price_source,
            pricing_context=pricing_context,
            resolved=resolved,
        )
    except Exception as exc:
        return _fail(exc)
    return ok(data)


# ----------------------------------------------------------------------
# 复用
# ----------------------------------------------------------------------
@configuration_bp.route('/match', methods=['POST'])
@login_required
def match():
    """`one_time_standard` 命中与复用。

    请求体：
        configuration_id  必填  刚求解出的实例 id

    未命中或策略不匹配时原样返回（`reused=false`），不产生写操作。
    """
    try:
        body = _json_body()
        configuration_id = _req_int(body, 'configuration_id')
        data = _get_match_service().match(configuration_id)
    except Exception as exc:
        return _fail(exc)
    return ok(data)


# ----------------------------------------------------------------------
# 求解 + 复用
# ----------------------------------------------------------------------
@configuration_bp.route('/solve', methods=['POST'])
@login_required
def solve():
    """求解配置实例，成功后在**接口层**串接复用匹配。

    请求体：
        structure_id      必填  结构版本 id
        selections        选填  用户选择（结构行 → 选中量）
        quantities        选填  数量覆盖（结构行 → 数量）
        attribute_values  选填  特征值（特征编码 → 值）
        qty               选填  父项数量，默认 1
        as_of             选填  有效期日期（YYYY-MM-DD）
        max_depth         选填  展开深度上限，默认 20
        model_version     选填  结构版本；给出则须与实例一致
        context           选填  上下文，原样留存到实例头
        record_invalid    选填  失败时是否落 invalid 实例，默认 false
        match             选填  求解成功后是否复用匹配，默认 true

    返回 `{configuration: <solve 产物>, match: <match 产物 | null>}`。
    """
    try:
        body = _json_body()
        structure_id = _req_int(body, 'structure_id')

        selections = body.get('selections')
        if not _is_blank(selections) and not isinstance(selections, (dict, list)):
            raise _ParamError('selections 需为对象或数组')

        quantities = _opt_dict(body, 'quantities')
        attribute_values = _opt_dict(body, 'attribute_values')
        context = _opt_dict(body, 'context')

        qty = 1.0
        if not _is_blank(body.get('qty')):
            qty = _as_number(body['qty'], 'qty')

        max_depth = _opt_int(body, 'max_depth', 20)
        if max_depth is None or max_depth < 1:
            raise _ParamError('max_depth 必须为正整数')

        record_invalid = _opt_bool(body, 'record_invalid', False)
        reuse = _opt_bool(body, 'match', True)

        configuration = _get_config_service().solve(
            structure_id,
            selections=selections,
            quantities=quantities,
            attribute_values=attribute_values,
            qty=qty,
            as_of=_opt_str(body, 'as_of'),
            max_depth=max_depth,
            model_version=_opt_str(body, 'model_version'),
            context=context,
            record_invalid=record_invalid,
        )

        matched = None
        if reuse:
            matched = _get_match_service().match(
                configuration.get('configuration_id'))
    except Exception as exc:
        return _fail(exc)
    return ok({'configuration': configuration, 'match': matched})


# ----------------------------------------------------------------------
# 变式物料化
# ----------------------------------------------------------------------
@configuration_bp.route('/materialize', methods=['POST'])
@login_required
@require_permission('configuration:configuration_materialize')
def materialize():
    """把已求解 / 已冻结的配置实例固化为变式物料。

    请求体：
        configuration_id  必填  配置实例 id

    返回 `{item_id, item_code, created}`；`created=False` 表示命中幂等键
    `(model_item_id, config_hash)`，复用了已有变式物料。
    产物状态依模型策略：manual → draft（须签发），auto → active。
    """
    try:
        body = _json_body()
        configuration_id = _req_int(body, 'configuration_id')
        data = _get_materialize_service().materialize(configuration_id)
    except Exception as exc:
        return _fail(exc)
    return ok(data)
