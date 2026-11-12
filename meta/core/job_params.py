# -*- coding: utf-8 -*-
"""作业参数清洗与校验（spec §7.2 运行期校验）。

依据:
  docs/specs/spec-background-job-infrastructure-2026-11-10.md §7.2

职责:
  · 只做纯函数校验：参数形状 / 键白名单 / 禁止键 / 16KB 上限；
  · 不写库、不执行作业（dispatcher 在下发前调用，executor 不得二次信任）。

约定:
  · `params_schema` 为 NULL/空 → 视为空对象 schema，所有键被丢弃（并记 warning）；
  · 声明了 `properties` 的 schema → 仅保留白名单键；
  · `required` 缺失、`const` / `enum` / `type` 不符 → 拒绝执行（返回 error）。
"""

import json
import logging

logger = logging.getLogger(__name__)

#: 参数快照上限（spec §7.2）。
MAX_PARAMS_BYTES = 16 * 1024

#: 出现即拒绝的键名片段（防反射 / 防注入执行器配置）。
FORBIDDEN_KEY_PARTS = ('handler', 'module', 'class')

_TYPE_MAP = {
    'string': lambda v: isinstance(v, str),
    'object': lambda v: isinstance(v, dict),
    'array': lambda v: isinstance(v, list),
    'boolean': lambda v: isinstance(v, bool),
    'integer': lambda v: isinstance(v, int) and not isinstance(v, bool),
    'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


def parse_json_object(raw):
    """把 TEXT 列（或已解析的 dict）转成 dict；非法返回空 dict。"""
    if raw is None or raw == '':
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def job_default_params(job) -> dict:
    return parse_json_object((job or {}).get('default_params'))


def job_params_schema(job) -> dict:
    return parse_json_object((job or {}).get('params_schema'))


def merge_job_params(job, override=None) -> dict:
    """`default_params` ← `params_override`（触发器 / 手动入参覆盖）。"""
    merged = dict(job_default_params(job))
    if isinstance(override, dict):
        merged.update(override)
    return merged


def sanitize_params(params, schema) -> 'tuple[dict, str | None]':
    """返回 `(clean_params, error)`；`error` 非 None 表示拒绝执行。"""
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return {}, 'params 必须是 object'
    try:
        size = len(json.dumps(params, ensure_ascii=False,
                              sort_keys=True).encode('utf-8'))
    except (TypeError, ValueError):
        return {}, 'params 无法序列化为 JSON'
    if size > MAX_PARAMS_BYTES:
        return {}, 'params 超过 %d 字节' % MAX_PARAMS_BYTES

    bad_key = _find_forbidden_key(params)
    if bad_key:
        return {}, '参数键被禁止: %s' % bad_key

    schema = schema if isinstance(schema, dict) else {}
    properties = schema.get('properties')
    properties = properties if isinstance(properties, dict) else {}

    clean = {}
    for key, value in params.items():
        spec = properties.get(key)
        if not isinstance(spec, dict):
            logger.warning('[job-params] 丢弃未声明参数键: %s', key)
            continue
        error = _check_value(key, value, spec)
        if error:
            return {}, error
        clean[key] = value

    for key in schema.get('required') or []:
        if key not in clean:
            return {}, '缺少必填参数: %s' % key
    return clean, None


def _find_forbidden_key(obj, path=''):
    if isinstance(obj, dict):
        for key, value in obj.items():
            name = str(key).lower()
            if name.startswith('__') or any(
                    part in name for part in FORBIDDEN_KEY_PARTS):
                return path + str(key)
            found = _find_forbidden_key(value, path + str(key) + '.')
            if found:
                return found
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found = _find_forbidden_key(value, '%s[%d].' % (path, index))
            if found:
                return found
    return None


def _check_value(key, value, spec) -> 'str | None':
    expected = spec.get('type')
    checker = _TYPE_MAP.get(expected) if isinstance(expected, str) else None
    if checker is not None and not checker(value):
        return '参数 %s 类型应为 %s' % (key, expected)
    if 'const' in spec and value != spec['const']:
        return '参数 %s 必须等于 %r' % (key, spec['const'])
    enum = spec.get('enum')
    if isinstance(enum, list) and value not in enum:
        return '参数 %s 不在允许取值内' % key
    return None