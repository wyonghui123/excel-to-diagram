# -*- coding: utf-8 -*-
"""
分摊 API（Allocation）
======================

把 `AllocationService` 的能力暴露为 HTTP 端点：

    POST /api/v1/allocation/allocate    分摊执行（IF-004, FR-013 / FR-014）

[为何独立于 pricing 而非挂在其下 · 2026-10-07]
分摊是**平台级通用能力**，不是定价的附属动作。算法层（`plan` /
`plan_floor`）零业务耦合——只吃 `total/weights/floor/scale/rounding`，
数量·工时·重量分摊同样适用（实测确认）。留痕层已拆出独立表
`allocation_results`（见 TBD-18），与 `calc_results` 物理隔离。

路径随之定为 `/api/v1/allocation/*`，与 `/api/v1/<域>` 惯例一致
（如 `cache_bp` → `/api/v1/cache`）。端点交付次日即改路径，**不留别名**
——仓库内外均无调用方，且本仓一贯拒绝向后兼容垫片。

[分层] api 层**只做参数校验与响应包装**，业务全在
`meta/services/allocation_service.py`。故本模块的测试属"契约测试"：
发请求 → 断言响应字段名与类型，不重复测业务正确性。

[错误码映射] 与定价端点同一分界——400「改请求」/ 422「改配置」：

    400 INVALID_PARAM      参数缺失或类型错（含 rounding/weights 非法）
    400 ALLOCATION_ERROR   分摊参数错
    404 ALLOCATION_ERROR   规则或父行不存在
    422 ALLOCATION_ERROR   配置矛盾（floor 无解、基数列缺值/非正）

`AllocationError` 自带 `status_code`，映射直接取用，避免同一张映射表
在两处维护而漂移。
"""
from typing import Optional

from flask import Blueprint, request

from meta.api._response_contract import ok
from meta.api.pricing_api import (
    _as_int,
    _as_number,
    _fail,
    _is_blank,
    _json_body,
    _opt_int,
    _ParamError,
    _req_int,
    _req_str,
)
from meta.services.allocation_service import (
    ROUNDING_MODES,
    AllocationService,
)
from meta.services.auth_middleware import login_required

allocation_bp = Blueprint(
    'allocation', __name__, url_prefix='/api/v1/allocation')

_alloc_service: Optional[AllocationService] = None


def init_alloc_services(data_source=None) -> AllocationService:
    """分摊服务独立持有——同源于 meta 库，但与定价服务无共享状态。

    [WARNING] 数据库路径必须走 `get_meta_db_path()`，禁止相对路径。
    """
    global _alloc_service
    if data_source is not None:
        _alloc_service = AllocationService(data_source)
    elif _alloc_service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        _alloc_service = AllocationService(
            get_data_source('sqlite', database=get_meta_db_path())
        )
    return _alloc_service


def _get_alloc_service() -> AllocationService:
    return init_alloc_services()


# ----------------------------------------------------------------------
# IF-004 分摊执行（FR-013 / FR-014）
# ----------------------------------------------------------------------
@allocation_bp.route('/allocate', methods=['POST'])
@login_required
def allocate():
    """按 `allocation_rule` 配置把父行的量守恒地摊到 N 个已有子行。

    请求体：
        allocation_rule_id  必填  分摊规则 id（allocation_rules.id）
        parent_id           必填  父记录 id
        target_object       必填  子对象类型
        target_field        必填  子行待写入字段
        basis_field         选填  basis ∈ {value,quantity,weight,volume}
                              时的权重来源列；equal/manual 不需要
        group_by            选填  覆盖规则配置的分组维度（组间均分+组内按 basis）
        floor               选填  覆盖规则配置的地板值
        rounding            选填  覆盖规则配置的取整方式（none/round/ceil/floor）
        weights             选填  显式权重，**优先于 basis**（调试/特例用）
        source_field        选填  父行取总额字段；缺省 = target_field
        fk_field            选填  子行指向父行的外键；缺省由层级配置推导
        parent_object       选填  父对象类型；缺省由层级配置推导
        scale               选填  小数位，默认 2
        persist_result      选填  默认 true；false = 只摊不落 allocation_results
        document_type       选填  留痕行的宿主 BO id；缺省由层级配置推导
        charge_source       选填  费用来源单据类型（order/invoice/…）
        source_document_type/id  选填  费用**来源**单据（可≠ 宿主单据）
        target              选填  归集方向 cost/expense；缺省用规则配置
        currency            选填  默认 CNY；**非金额场景可留空**

    [通用性] 本端点不限定金额。`amount` 列语义是「量」——金额场景填
    金额，工时/数量/重量场景填各自的量，配合 `basis_field` 指权重来源列。
    算法层对两者完全一致（`Σ子行 == 总额` 精确守恒）。

    [守恒] 服务层在**写入后**从 DB 回读校验 `Σ子行 == 实际摊派额`，
    不相等即整体回滚——不会出现「摊了一半」的中间态。
    `rounding` 为 ceil/floor 时 `total`（实际摊派额）与 `source_total`
    （父行原值）不同，这是取整的必然结果，不是误差。
    """
    try:
        body = _json_body()
        spec = {
            'allocation_rule_id': _req_int(body, 'allocation_rule_id'),
            'parent_id': _req_int(body, 'parent_id'),
            'target_object': _req_str(body, 'target_object'),
            'target_field': _req_str(body, 'target_field'),
            'persist_result': bool(body.get('persist_result', True)),
        }

        # 枚举在**入口**拦：非法值属"改请求"（400 INVALID_PARAM），
        # 放到服务层会被当成"配置矛盾"（422）而错误码串号。
        rounding = body.get('rounding') or None
        if rounding is not None and rounding not in ROUNDING_MODES:
            raise _ParamError(
                f"rounding 非法：{rounding!r}；可选 {sorted(ROUNDING_MODES)}"
            )

        weights = body.get('weights')
        if weights is not None and not isinstance(weights, list):
            raise _ParamError('weights 必须为数组')

        # scale 不量化时**不能传 None**：服务层 `spec.get('scale', 2)`
        # 对「键存在但值为 None」不回退默认值，会拿到 None 而崩。
        scale = _opt_int(body, 'scale')
        if scale is not None:
            if scale < 0:
                raise _ParamError('scale 必须为非负整数')
            spec['scale'] = scale

        for key in ('basis_field', 'group_by', 'source_field', 'fk_field',
                    'parent_object', 'document_type', 'charge_source',
                    'source_document_type', 'target'):
            v = body.get(key)
            if not _is_blank(v):
                spec[key] = str(v).strip()
        # currency 允许空串→None：非金额分摊（工时/数量）没有币种。
        # 故**不**用上面的 str(v).strip() 路径，否则空串会变成 ''。
        currency = body.get('currency')
        if not _is_blank(currency):
            spec['currency'] = str(currency).strip()

        if rounding is not None:
            spec['rounding'] = rounding
        if weights is not None:
            spec['weights'] = weights

        floor = body.get('floor')
        if not _is_blank(floor):
            spec['floor'] = _as_number(floor, 'floor')

        source_document_id = _opt_int(body, 'source_document_id')
        if source_document_id is not None:
            spec['source_document_id'] = source_document_id

        data = _get_alloc_service().allocate_by_rule(spec)
    except Exception as exc:
        return _fail(exc)
    return ok(data)


# ----------------------------------------------------------------------
# 分摊留痕回放（FR-013 AC「分摊可回放」）
# ----------------------------------------------------------------------
@allocation_bp.route(
    '/result/<document_type>/<int:document_id>', methods=['GET'])
@login_required
def get_result(document_type: str, document_id: int):
    """回放某宿主的 active 分摊留痕：1 头（待摊总额）+ N 行（各行摊得额）。

    查询参数：
        document_line_id  选填  行 id；给定则只回该行级留痕
        status            选填  默认 `active`；传 `all` = 含已作废行（审计用）

    [为何不并入定价回放] 分摊的数学是一次性闭式（`Σ子行 == 总额` 精确成立，
    无迭代无中间态），**没有 calc_detail 明细可挂**。混进定价的 results
    只会让前端拿到「有结果、无步骤」的残缺链路——那正是拆表前的实测症状。
    """
    try:
        raw_line = request.args.get('document_line_id')
        line_id = None if _is_blank(raw_line) else _as_int(
            raw_line, 'document_line_id')
        raw_status = (request.args.get('status') or '').strip()
        status = None if raw_status == 'all' else 'active'
        rows = _get_alloc_service().query_results(
            document_type, document_id, line_id, status)
    except Exception as exc:
        return _fail(exc)
    return ok({
        'document_type': document_type,
        'document_id': document_id,
        'document_line_id': line_id,
        'results': rows,
    })