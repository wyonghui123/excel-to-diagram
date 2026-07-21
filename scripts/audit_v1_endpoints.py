# -*- coding: utf-8 -*-
"""
v1 API 端点状态扫描器

扫描所有已注册的 Flask Blueprint 端点，生成 v1 端点废弃状态清单。

输出：
- docs/api_v1_status.md (人类可读 Markdown 表格)
- docs/api_v1_status.json (结构化数据，供工具消费)

扫描维度：
1. Blueprint 的 url_prefix 是否以 /api/v1/ 开头
2. 每个端点的 view_func 是否有 _v1_status 元信息
3. 端点的 HTTP 方法、URL、状态、迁移目标

用法：
    python scripts/audit_v1_endpoints.py
    python scripts/audit_v1_endpoints.py --output docs/api_v1_status.md
    python scripts/audit_v1_endpoints.py --json docs/api_v1_status.json
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# 确保能 import meta 模块
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _import_app():
    """导入 Flask app，延迟导入避免循环依赖"""
    try:
        from meta.server import create_app
        return create_app()
    except ImportError as e:
        print(f'[ERROR] 无法导入 meta.server: {e}', file=sys.stderr)
        print('[HINT] 请在项目根目录运行: python scripts/audit_v1_endpoints.py', file=sys.stderr)
        sys.exit(1)


def _get_endpoint_status(view_func):
    """获取端点的废弃状态（兼容无 _deprecation 模块的情况）"""
    try:
        from meta.api._deprecation import (
            get_endpoint_status,
            get_endpoint_migrated_to,
            get_endpoint_sunset_at,
            DEPRECATION_ACTIVE,
        )
        status = get_endpoint_status(view_func)
        migrated_to = get_endpoint_migrated_to(view_func)
        sunset_at = get_endpoint_sunset_at(view_func)
        return status, migrated_to, sunset_at
    except ImportError:
        # _deprecation.py 不存在时，所有端点都是 ACTIVE
        return 'ACTIVE', None, None


def _normalize_url(url):
    """标准化 URL（移除 Blueprint 名称前缀，保留 url_prefix + rule）"""
    # Flask url_map 中 url 格式: /api/v1/roles/<int:role_id>
    # 不需要额外处理
    return url


# before_request 钩子中拦截的路径配置（与 server.py 保持同步）
V1_SPECIAL_PREFIXES = {
    'annotations', 'audit-logs', 'audit', 'value-help',
    'analytics', 'enums', 'enum-types', 'enum-values', 'auth',
    'import', 'export', 'import-export',
    'role-menus', 'role-dimension-scopes',
    'permission-audit', 'bo',
    'meta-actions',
    'query', 'agent', 'schema', 'system', 'stats', 'manage', 'test',
    'permissions',  # /api/v1/permissions/* (FR-012)
    'roles',        # /api/v1/roles/*/intents (FR-017)
    'bos',          # /api/v1/bos (FR-017)
    'overlaps',     # /api/v1/roles/*/overlaps (FR-005)
    'telemetry',    # M14
    'identity',     # [FIX 2026-07-21] 查询端点，不是 CRUD list
}

V1_CRUD_MIGRATION = {
    'users': 'user',
    'roles': 'role',
    'user-groups': 'user_group',
    'permission-bundles': 'permission_bundle',
    'permission-rules': 'permission_rule',
    'data-permissions': 'data_permission',
    'management-dimensions': 'management_dimension',
    'filter-variants': 'filter_variant',
    'menu-permission': 'menu_permission',
    'associations': 'association',
    'notifications': 'notification',
}


def _check_before_request_status(url):
    """
    模拟 server.py before_request 钩子的拦截逻辑，
    返回 (is_intercepted, v2_path) 元组。

    如果被拦截，端点实际行为是 SUNSET (410)，
    无论装饰器标记了什么状态。
    """
    if not url.startswith('/api/v1/'):
        return False, None

    path_parts = url[len('/api/v1/'):].split('/')
    if not path_parts or not path_parts[0]:
        return False, None

    # 移除 Flask 路由参数中的类型转换（如 <int:role_id> → <role_id>）
    first_segment = path_parts[0]

    # 1) 在 V1_SPECIAL_PREFIXES 中 → 放行
    if first_segment in V1_SPECIAL_PREFIXES:
        return False, None

    # 2) 在 V1_CRUD_MIGRATION 中 → 检查路径深度
    if first_segment in V1_CRUD_MIGRATION:
        non_empty_parts = [p for p in path_parts if p and not p.startswith('<')]
        if len(non_empty_parts) == 1:
            # 顶层 CRUD list → 410
            v2_target = V1_CRUD_MIGRATION[first_segment]
            return True, f'/api/v2/bo/{v2_target}'
        elif len(non_empty_parts) == 2 and non_empty_parts[1].isdigit():
            # 顶层 CRUD by id → 410
            v2_target = V1_CRUD_MIGRATION[first_segment]
            return True, f'/api/v2/bo/{v2_target}/<id>'
        else:
            # 子路径 → 放行
            return False, None

    # 3) 其他 v1 路径 → 410 (按 v2 名称映射)
    # 但只拦截看起来像资源路径的（排除静态/特殊路径）
    # 注意: manage_bp 的 generic /<object_type> 路由也会匹配这些
    v2_target = first_segment
    non_empty_parts = [p for p in path_parts if p and not p.startswith('<')]
    if len(non_empty_parts) <= 2:
        v2_path = f'/api/v2/bo/{v2_target}'
        if len(path_parts) > 1 and path_parts[1]:
            v2_path += '/' + '/'.join(path_parts[1:])
        return True, v2_path

    return False, None


def scan_endpoints(app):
    """扫描所有 v1 端点"""
    endpoints = []

    for rule in app.url_map.iter_rules():
        url = str(rule)
        view_func = rule.endpoint

        # 获取真实的 view 函数（可能经过 Blueprint 包装）
        try:
            func = app.view_functions[view_func]
        except KeyError:
            continue

        # 判断是 v1 还是 v2 端点
        if '/api/v1/' in url:
            api_version = 'v1'
        elif '/api/v2/' in url:
            api_version = 'v2'
        else:
            api_version = 'other'
            continue  # 只关注 v1/v2

        # 获取废弃状态
        status, migrated_to, sunset_at = _get_endpoint_status(func)

        # 检查 before_request 钩子是否拦截（优先级高于装饰器）
        is_intercepted, v2_path = _check_before_request_status(url)
        if is_intercepted:
            # before_request 钩子拦截的端点实际返回 410 (SUNSET)
            # 装饰器标记可能不准确（因为请求不会到达装饰器）
            if status == 'ACTIVE':
                status = 'SUNSET'
                migrated_to = v2_path

        # 获取 HTTP 方法
        methods = sorted(
            m for m in (rule.methods or set())
            if m not in ('HEAD', 'OPTIONS')
        )

        # 解析 Blueprint 名和端点名
        if '.' in view_func:
            blueprint_name, endpoint_name = view_func.split('.', 1)
        else:
            blueprint_name, endpoint_name = '(root)', view_func

        endpoints.append({
            'api_version': api_version,
            'blueprint': blueprint_name,
            'endpoint': endpoint_name,
            'full_endpoint': view_func,
            'url': _normalize_url(url),
            'methods': methods,
            'status': status,
            'migrated_to': migrated_to,
            'sunset_at': sunset_at,
        })

    return endpoints


def generate_markdown_report(endpoints, output_path):
    """生成 Markdown 报告"""
    v1_endpoints = [e for e in endpoints if e['api_version'] == 'v1']
    v2_endpoints = [e for e in endpoints if e['api_version'] == 'v2']

    # 按状态分组统计
    status_counts = defaultdict(int)
    for e in v1_endpoints:
        status_counts[e['status']] += 1

    # 按 Blueprint 分组
    by_blueprint = defaultdict(list)
    for e in v1_endpoints:
        by_blueprint[e['blueprint']].append(e)

    lines = []
    lines.append('# v1 API 端点状态清单')
    lines.append('')
    lines.append(f'> 自动生成于 `audit_v1_endpoints.py`，请勿手工编辑。')
    lines.append(f'> 重新生成: `python scripts/audit_v1_endpoints.py`')
    lines.append('')

    # 概览
    lines.append('## 一、概览')
    lines.append('')
    lines.append(f'- **v1 端点总数**: {len(v1_endpoints)}')
    lines.append(f'- **v2 端点总数**: {len(v2_endpoints)}')
    lines.append('')
    lines.append('### v1 端点状态分布')
    lines.append('')
    lines.append('| 状态 | 数量 | 占比 | 说明 |')
    lines.append('|------|------|------|------|')
    total_v1 = max(len(v1_endpoints), 1)
    status_desc = {
        'ACTIVE': '正常使用，无废弃标记',
        'DEPRECATED': '可用但警告，前端应迁移',
        'SUNSET': '已下线，返回 410',
        'REMOVED': '已删除，返回 404',
    }
    for status in ['ACTIVE', 'DEPRECATED', 'SUNSET', 'REMOVED']:
        count = status_counts.get(status, 0)
        pct = count * 100 / total_v1
        lines.append(f'| {status} | {count} | {pct:.1f}% | {status_desc[status]} |')
    lines.append('')

    # 迁移建议
    needs_migration = [e for e in v1_endpoints if e['status'] in ('DEPRECATED', 'SUNSET')]
    if needs_migration:
        lines.append('## 二、需要前端迁移的端点')
        lines.append('')
        lines.append('| 状态 | URL | 方法 | 迁移到 | 下线日期 | Blueprint |')
        lines.append('|------|-----|------|--------|---------|-----------|')
        for e in needs_migration:
            methods = ', '.join(e['methods'])
            migrated = e['migrated_to'] or '-'
            sunset = e['sunset_at'] or '-'
            lines.append(
                f'| {e["status"]} | `{e["url"]}` | {methods} | `{migrated}` | {sunset} | {e["blueprint"]} |'
            )
        lines.append('')

    # 按 Blueprint 分组的完整清单
    lines.append('## 三、v1 端点完整清单（按 Blueprint 分组）')
    lines.append('')

    for blueprint in sorted(by_blueprint.keys()):
        eps = by_blueprint[blueprint]
        lines.append(f'### `{blueprint}` ({len(eps)} 个端点)')
        lines.append('')
        lines.append('| URL | 方法 | 状态 | 迁移到 |')
        lines.append('|-----|------|------|--------|')
        for e in sorted(eps, key=lambda x: x['url']):
            methods = ', '.join(e['methods'])
            migrated = e['migrated_to'] or '-'
            lines.append(f'| `{e["url"]}` | {methods} | {e["status"]} | `{migrated}` |')
        lines.append('')

    # v2 端点清单（简要）
    lines.append('## 四、v2 端点清单（简要）')
    lines.append('')
    lines.append(f'> v2 端点总数: {len(v2_endpoints)}')
    lines.append('')
    lines.append('| URL | 方法 | Blueprint |')
    lines.append('|-----|------|-----------|')
    for e in sorted(v2_endpoints, key=lambda x: x['url']):
        methods = ', '.join(e['methods'])
        lines.append(f'| `{e["url"]}` | {methods} | {e["blueprint"]} |')
    lines.append('')

    # 迁移建议
    lines.append('## 五、迁移建议')
    lines.append('')
    lines.append('### 优先级 P0（SUNSET 状态）')
    lines.append('')
    sunset_eps = [e for e in v1_endpoints if e['status'] == 'SUNSET']
    if sunset_eps:
        lines.append('前端必须立即停止调用以下端点（已返回 410）:')
        lines.append('')
        for e in sunset_eps:
            methods = ', '.join(e['methods'])
            lines.append(f'- `{methods} {e["url"]}` → `{e["migrated_to"]}`')
    else:
        lines.append('（无）')
    lines.append('')

    lines.append('### 优先级 P1（DEPRECATED 状态）')
    lines.append('')
    deprecated_eps = [e for e in v1_endpoints if e['status'] == 'DEPRECATED']
    if deprecated_eps:
        lines.append('前端应在 sunset_at 之前迁移以下端点:')
        lines.append('')
        for e in deprecated_eps:
            methods = ', '.join(e['methods'])
            sunset = e['sunset_at'] or '未指定'
            lines.append(f'- `{methods} {e["url"]}` → `{e["migrated_to"]}` (下线: {sunset})')
    else:
        lines.append('（无）')
    lines.append('')

    lines.append('### 优先级 P2（ACTIVE 状态）')
    lines.append('')
    active_eps = [e for e in v1_endpoints if e['status'] == 'ACTIVE']
    if active_eps:
        lines.append(f'以下 {len(active_eps)} 个端点仍正常工作，可按需评估是否迁移到 v2:')
        lines.append('')
        lines.append('| Blueprint | 端点数 |')
        lines.append('|-----------|--------|')
        bp_counts = defaultdict(int)
        for e in active_eps:
            bp_counts[e['blueprint']] += 1
        for bp, count in sorted(bp_counts.items(), key=lambda x: -x[1]):
            lines.append(f'| {bp} | {count} |')
    else:
        lines.append('（无）')
    lines.append('')

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'[OK] Markdown 报告已生成: {output_path}')
    print(f'     v1 端点: {len(v1_endpoints)} (ACTIVE={status_counts.get("ACTIVE", 0)}, '
          f'DEPRECATED={status_counts.get("DEPRECATED", 0)}, '
          f'SUNSET={status_counts.get("SUNSET", 0)}, '
          f'REMOVED={status_counts.get("REMOVED", 0)})')
    print(f'     v2 端点: {len(v2_endpoints)}')


def generate_json_report(endpoints, output_path):
    """生成 JSON 报告"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'generated_at': _get_timestamp(),
        'summary': {
            'v1_total': sum(1 for e in endpoints if e['api_version'] == 'v1'),
            'v2_total': sum(1 for e in endpoints if e['api_version'] == 'v2'),
            'v1_by_status': {
                s: sum(1 for e in endpoints if e['api_version'] == 'v1' and e['status'] == s)
                for s in ['ACTIVE', 'DEPRECATED', 'SUNSET', 'REMOVED']
            },
        },
        'endpoints': endpoints,
    }
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f'[OK] JSON 报告已生成: {output_path}')


def _get_timestamp():
    """获取当前时间戳"""
    from datetime import datetime
    return datetime.now().isoformat()


def main():
    parser = argparse.ArgumentParser(
        description='扫描 v1 API 端点状态，生成清单报告'
    )
    parser.add_argument(
        '--output', '-o',
        default='docs/api_v1_status.md',
        help='Markdown 输出路径（默认: docs/api_v1_status.md）'
    )
    parser.add_argument(
        '--json', '-j',
        default='docs/api_v1_status.json',
        help='JSON 输出路径（默认: docs/api_v1_status.json）'
    )
    parser.add_argument(
        '--no-json',
        action='store_true',
        help='不生成 JSON 报告'
    )
    args = parser.parse_args()

    print('[1/3] 导入 Flask app...')
    app = _import_app()

    print('[2/3] 扫描端点...')
    endpoints = scan_endpoints(app)
    print(f'      共扫描 {len(endpoints)} 个端点')

    print('[3/3] 生成报告...')
    md_path = Path(args.output)
    generate_markdown_report(endpoints, md_path)

    if not args.no_json:
        json_path = Path(args.json)
        generate_json_report(endpoints, json_path)

    print()
    print('完成。请查看:')
    print(f'  - Markdown: {md_path}')
    if not args.no_json:
        print(f'  - JSON:     {Path(args.json)}')


if __name__ == '__main__':
    main()
