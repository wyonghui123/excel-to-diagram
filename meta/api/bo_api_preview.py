# -*- coding: utf-8 -*-
"""
bo_api_preview - 架构预览聚合 API (FR-012 拆分)

[FR-012] 从 bo_api.py 拆分的第一个子模块，专门负责：
- /architecture/preview 聚合 API

[FR-004 + FR-009] ID 列表过滤下推到 SQL

设计：register_preview_routes(bo_bp, get_bo_fn)
- 不直接导入 bo_api（避免循环依赖）
- 由 bo_api 在蓝图创建后调用注册
"""
import logging
from flask import request, jsonify

logger = logging.getLogger(__name__)


def get_architecture_preview_impl(bo):
    """架构预览聚合 API - 一次返回完整树结构数据

    [FR-004 + FR-009] ID 列表过滤下推到 SQL，避免 Python 端二次遍历

    Args:
        bo: bo_framework 实例（通过参数注入，避免循环导入）

    Returns:
        Flask Response (jsonify)
    """
    try:
        version_id = request.args.get('version_id', type=int)
        domain_ids = request.args.get('domain_ids', '')
        sub_domain_ids = request.args.get('sub_domain_ids', '')
        service_module_ids = request.args.get('service_module_ids', '')
        business_object_ids = request.args.get('business_object_ids', '')

        # 构建版本过滤条件
        version_filter = {'version_id': version_id} if version_id else {}

        # 解析过滤 ID 列表（提前到 SQL 过滤之前）
        domain_id_list = [int(x) for x in domain_ids.split(',') if x.strip()]
        sub_domain_id_list = [int(x) for x in sub_domain_ids.split(',') if x.strip()]
        module_id_list = [int(x) for x in service_module_ids.split(',') if x.strip()]
        bo_id_list = [int(x) for x in business_object_ids.split(',') if x.strip()]

        # [FR-009] 下推 ID 列表到 SQL：避免 Python 端 5000+ 二次过滤
        # 关键：当 ID 列表非空时，添加 id__in 过滤并降低 page_size
        if domain_id_list:
            domain_filter = {**version_filter, 'id__in': domain_id_list}
            domain_page_size = min(5000, len(domain_id_list) * 2)  # 2x 容错
        else:
            domain_filter = version_filter.copy()
            domain_page_size = 5000
        if sub_domain_id_list:
            sub_domain_filter = {**version_filter, 'id__in': sub_domain_id_list}
            sub_domain_page_size = min(5000, len(sub_domain_id_list) * 2)
        else:
            sub_domain_filter = version_filter.copy()
            sub_domain_page_size = 5000
        if module_id_list:
            module_filter = {**version_filter, 'id__in': module_id_list}
            module_page_size = min(5000, len(module_id_list) * 2)
        else:
            module_filter = version_filter.copy()
            module_page_size = 5000
        if bo_id_list:
            bo_filter = {**version_filter, 'id__in': bo_id_list}
            bo_page_size = min(5000, len(bo_id_list) * 2)
        else:
            bo_filter = version_filter.copy()
            bo_page_size = 5000

        # [FR-009] 关系表下推：source_bo_id__in + target_bo_id__in
        rel_filter = version_filter.copy()
        if bo_id_list:
            rel_filter['source_bo_id__in'] = bo_id_list
            rel_filter['target_bo_id__in'] = bo_id_list
            rel_page_size = min(10000, len(bo_id_list) * len(bo_id_list) * 2)
        else:
            rel_page_size = 10000

        # 查询各层级数据
        domain_result = bo.query('domain', domain_filter, page_size=domain_page_size)
        sub_domain_result = bo.query('sub_domain', sub_domain_filter, page_size=sub_domain_page_size)
        module_result = bo.query('service_module', module_filter, page_size=module_page_size)
        bo_result = bo.query('business_object', bo_filter, page_size=bo_page_size)
        rel_result = bo.query('relationship', rel_filter, page_size=rel_page_size)

        # 提取数据
        domains = domain_result.data if domain_result.success else []
        sub_domains = sub_domain_result.data if sub_domain_result.success else []
        modules = module_result.data if module_result.success else []
        business_objects = bo_result.data if bo_result.success else []
        relationships = rel_result.data if rel_result.success else []

        # [FR-009] Python 端二次过滤已不需要（已在 SQL 层下推）
        # 保留以下作为防御性 fallback
        if domain_id_list:
            domains = [d for d in domains if d.get('id') in set(domain_id_list)]
        if sub_domain_id_list:
            sub_domains = [d for d in sub_domains if d.get('id') in set(sub_domain_id_list)]
        if module_id_list:
            modules = [m for m in modules if m.get('id') in set(module_id_list)]
        if bo_id_list:
            business_objects = [b for b in business_objects if b.get('id') in set(bo_id_list)]

        # ── [v32 2026-06-11] 补全 hierarchy 范围 ──
        module_id_set = set(module_id_list) if module_id_list else None
        sub_domain_id_set = set(sub_domain_id_list) if sub_domain_id_list else None
        domain_id_set = set(domain_id_list) if domain_id_list else None
        referenced_sm_ids = set()
        referenced_sub_domain_ids = set()
        referenced_domain_ids = set()
        for b in business_objects:
            sm_id = b.get('service_module_id')
            sd_id = b.get('sub_domain_id')
            d_id = b.get('domain_id')
            if sm_id and (module_id_set is None or sm_id not in module_id_set):
                referenced_sm_ids.add(sm_id)
            if sd_id and (sub_domain_id_set is None or sd_id not in sub_domain_id_set):
                referenced_sub_domain_ids.add(sd_id)
            if d_id and (domain_id_set is None or d_id not in domain_id_set):
                referenced_domain_ids.add(d_id)
        if referenced_sm_ids or referenced_sub_domain_ids or referenced_domain_ids:
            extra_modules = [m for m in module_result.data if m.get('id') in referenced_sm_ids]
            extra_sub_domains = [sd for sd in sub_domain_result.data if sd.get('id') in referenced_sub_domain_ids]
            extra_domains = [d for d in domain_result.data if d.get('id') in referenced_domain_ids]
            seen = {m.get('id') for m in modules}
            for m in extra_modules:
                if m.get('id') not in seen:
                    modules.append(m)
                    seen.add(m.get('id'))
            seen = {sd.get('id') for sd in sub_domains}
            for sd in extra_sub_domains:
                if sd.get('id') not in seen:
                    sub_domains.append(sd)
                    seen.add(sd.get('id'))
            seen = {d.get('id') for d in domains}
            for d in extra_domains:
                if d.get('id') not in seen:
                    domains.append(d)
                    seen.add(d.get('id'))

        # 计算 center_scope
        center_scope = []
        if bo_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('id') in bo_id_list]
        elif module_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('service_module_id') in module_id_list]
        elif sub_domain_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('sub_domain_id') in sub_domain_id_list]
        elif domain_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('domain_id') in domain_id_list]

        # ── Relation Classification ──
        bo_id_map = {}
        for b in business_objects:
            bo_id_map[b.get('id')] = {
                'domain_id': b.get('domain_id'),
                'sub_domain_id': b.get('sub_domain_id'),
                'service_module_id': b.get('service_module_id'),
            }

        center_scope_set = set(center_scope)
        bo_code_map = {b.get('code'): b.get('id') for b in business_objects if b.get('code')}

        for rel in relationships:
            src_code = rel.get('source_code') or rel.get('sourceCode')
            tgt_code = rel.get('target_code') or rel.get('targetCode')

            if src_code and tgt_code and src_code == tgt_code:
                rel['scope_type'] = 'external'
                rel['category_type'] = 'cross-domain'
                continue

            src_bo_id = bo_code_map.get(src_code)
            tgt_bo_id = bo_code_map.get(tgt_code)
            src_info = bo_id_map.get(src_bo_id, {}) if src_bo_id else {}
            tgt_info = bo_id_map.get(tgt_bo_id, {}) if tgt_bo_id else {}

            src_in_scope = src_code in center_scope_set if center_scope_set else True
            tgt_in_scope = tgt_code in center_scope_set if center_scope_set else True

            if src_in_scope and tgt_in_scope:
                scope_type = 'internal'
            elif src_in_scope or tgt_in_scope:
                scope_type = 'cross-boundary'
            else:
                scope_type = 'external'

            src_domain_id = src_info.get('domain_id')
            tgt_domain_id = tgt_info.get('domain_id')
            src_sub_domain_id = src_info.get('sub_domain_id')
            tgt_sub_domain_id = tgt_info.get('sub_domain_id')
            src_module_id = src_info.get('service_module_id')
            tgt_module_id = tgt_info.get('service_module_id')

            if src_domain_id and tgt_domain_id and src_domain_id != tgt_domain_id:
                category_type = 'cross-domain'
            elif src_sub_domain_id and tgt_sub_domain_id and src_sub_domain_id != tgt_sub_domain_id:
                category_type = 'same-domain-cross-subdomain'
            elif src_module_id and tgt_module_id and src_module_id != tgt_module_id:
                category_type = 'same-subdomain-cross-module'
            else:
                category_type = 'same-module'

            if scope_type != 'internal' and category_type == 'same-module':
                if src_sub_domain_id and tgt_sub_domain_id and src_sub_domain_id != tgt_sub_domain_id:
                    category_type = 'same-domain-cross-subdomain'
                elif src_domain_id and tgt_domain_id and src_domain_id != tgt_domain_id:
                    category_type = 'cross-domain'

            rel['scope_type'] = scope_type
            rel['category_type'] = category_type

        return jsonify({
            'success': True,
            'data': {
                'domains': domains,
                'sub_domains': sub_domains,
                'service_modules': modules,
                'business_objects': business_objects,
                'relationships': relationships,
                'center_scope': center_scope
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api_preview] architecture preview error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


def register_preview_routes(bo_bp, get_bo_fn, login_required_decorator):
    """注册架构预览相关路由到指定蓝图

    Args:
        bo_bp: Flask Blueprint 实例
        get_bo_fn: 获取 bo_framework 的函数（避免循环导入）
        login_required_decorator: 登录验证装饰器
    """
    @bo_bp.route('/architecture/preview', methods=['GET'])
    @login_required_decorator
    def get_architecture_preview():
        return get_architecture_preview_impl(get_bo_fn())
