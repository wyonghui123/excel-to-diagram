# -*- coding: utf-8 -*-
"""
供应来源 API（Sourcing）
========================

把 `SourcingResolver` 的两条能力暴露为 HTTP 端点：

    GET  /api/v1/sourcing/resolve                     供应来源求值（五步口径）
    POST /api/v1/sourcing/rules/<rule_id>/validate    规则配置完整性校验

[分层] api 层**只做参数校验与响应包装**，业务全在
`meta/services/sourcing_service.py`。故本模块的测试属"契约测试"：
发请求 → 断言响应字段名、状态码与错误码，不重复测业务正确性。

[错误码映射] 与定价 / 分摊端点同一分界——400「改请求」/ 404「对象不存在」/
422「改配置」：

    400 SOURCING_INVALID_PARAM     参数缺失、类型错或 usage/date 非法
    404 SOURCING_RULE_NOT_FOUND    校验的规则不存在
    422 SOURCING_*                 配置矛盾（无分配 / 全部来源不合格 /
                                   作用域冲突 / 分摊比例≠100 …）

`SourcingError` 自带 `status_code` 与 `extra`，映射直接取用，
避免同一张映射表在两处维护而漂移。
"""
from typing import Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.api.pricing_api import (
    _ParamError,
    _is_blank,
    _opt_int,
    _req_int,
    _req_str,
)
from meta.services.auth_middleware import login_required
from meta.services.sourcing_service import (
    SOURCING_INVALID_PARAM,
    USAGES,
    SourcingError,
    SourcingResolver,
)

sourcing_bp = Blueprint('sourcing', __name__, url_prefix='/api/v1/sourcing')

_resolver: Optional[SourcingResolver] = None


def init_sourcing_services(data_source=None) -> SourcingResolver:
    """初始化求值服务。测试传入临时数据源；生产懒取 meta 库。

    [WARNING] 数据库路径必须走 `get_meta_db_path()`，禁止相对路径。
    """
    global _resolver
    if data_source is not None:
        _resolver = SourcingResolver(data_source)
    elif _resolver is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        _resolver = SourcingResolver(
            get_data_source('sqlite', database=get_meta_db_path())
        )
    return _resolver


def _get_resolver() -> SourcingResolver:
    return init_sourcing_services()


def _fail(exc: Exception):
    """本模块的参数 / 服务异常 → 契约错误响应。未识别异常继续上抛。"""
    if isinstance(exc, _ParamError):
        return error_response(
            str(exc), code=SOURCING_INVALID_PARAM, status=400)
    if isinstance(exc, SourcingError):
        details = dict(exc.extra or {})
        if exc.hint:
            details['hint'] = exc.hint
        return error_response(
            exc.message,
            code=exc.code,
            status=exc.status_code,
            details=details or None,
        )
    raise exc


# ----------------------------------------------------------------------
# 供应来源求值
# ----------------------------------------------------------------------
@sourcing_bp.route('/resolve', methods=['GET'])
@login_required
def resolve():
    """按「规则作用域 → 供应方式 → 资格过滤 → 排序取源」求某物料由谁供应。

    查询参数：
        item_id           必填  物料 id
        dest_org_id       必填  目的组织 id
        usage             必填  fulfillment | purchasing
        date              选填  YYYY-MM-DD，缺省 = 今天
        dest_location_id  选填  目的位置 id
    """
    try:
        args = request.args
        usage = _req_str(args, 'usage')
        if usage not in USAGES:
            raise _ParamError(
                f'usage 非法：{usage!r}；可选 {sorted(USAGES)}')

        spec = {
            'item_id': _req_int(args, 'item_id'),
            'dest_org_id': _req_int(args, 'dest_org_id'),
            'usage': usage,
        }
        raw_date = args.get('date')
        if not _is_blank(raw_date):
            spec['date'] = str(raw_date).strip()
        dest_location_id = _opt_int(args, 'dest_location_id')
        if dest_location_id is not None:
            spec['dest_location_id'] = dest_location_id

        data = _get_resolver().resolve(spec)
    except Exception as exc:
        return _fail(exc)
    return ok(data)


# ----------------------------------------------------------------------
# 规则配置校验
# ----------------------------------------------------------------------
@sourcing_bp.route('/rules/<int:rule_id>/validate', methods=['POST'])
@login_required
def validate_rule(rule_id: int):
    """校验规则配置：分摊合计、类型—引用、组织职能 / vendor 关系、作用域唯一。

    返回 `{ok, rule_id, line_count, assignment_count, ranks, conflicts, errors}`；
    `errors` 非空表示配置有矛盾（**属正常结果不是 500**），供前端逐条展示。
    """
    try:
        data = _get_resolver().validate_rule(rule_id)
    except Exception as exc:
        return _fail(exc)
    if data is None:
        return error_response(
            '供应来源规则不存在', code='SOURCING_RULE_NOT_FOUND', status=404)
    return ok(data)
