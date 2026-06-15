#!/usr/bin/env python3
"""
Debug script: trace the relation scope tree building for procurement domain.
Reproduces the exact JS logic in Python to verify what the tree should contain.
"""
import requests
import json

API_BASE = "http://localhost:3010/api/v1"

def main():
    s = requests.Session()
    r = s.get(f"{API_BASE}/auth/dev-login?username=admin")
    print(f"[login] status={r.status_code}")
    print(f"[login] cookies: {list(s.cookies.keys())}")

    versions_resp = s.get(f"{API_BASE.replace('/v1', '/v2')}/bo/version?page_size=10")
    print(f"[versions] status={versions_resp.status_code}")
    versions_json = versions_resp.json()
    # Hardcode the target version (新测试2_1780899784189, id=1) - has the 29 relations including the cross-boundary
    version_id = 1
    print(f"[versions] using hardcoded version_id={version_id}")

    rels_resp = s.get(f"{API_BASE.replace('/v1', '/v2')}/bo/relationship?version_id={version_id}&page_size=10000")
    print(f"[relationships] status={rels_resp.status_code}")
    rels_resp_data = rels_resp.json()['data']
    rels = rels_resp_data.get('items', rels_resp_data) if isinstance(rels_resp_data, dict) else rels_resp_data
    print(f"[relationships] count={len(rels)}")
    print(f"[relationships] sample[0]: {json.dumps(rels[0], ensure_ascii=False)[:500]}")

    bos_resp = s.get(f"{API_BASE.replace('/v1', '/v2')}/bo/business_object?version_id={version_id}&page_size=10000").json()['data']
    bos = bos_resp.get('items', bos_resp) if isinstance(bos_resp, dict) else bos_resp
    print(f"[business_objects] count={len(bos)}")
    sms_resp = s.get(f"{API_BASE.replace('/v1', '/v2')}/bo/service_module?version_id={version_id}&page_size=5000").json()['data']
    sms = sms_resp.get('items', sms_resp) if isinstance(sms_resp, dict) else sms_resp
    sds_resp = s.get(f"{API_BASE.replace('/v1', '/v2')}/bo/sub_domain?version_id={version_id}&page_size=1000").json()['data']
    sds = sds_resp.get('items', sds_resp) if isinstance(sds_resp, dict) else sds_resp
    # Fetch all domains (paginate)
    domains = []
    page = 1
    while True:
        domains_resp = s.get(f"{API_BASE.replace('/v1', '/v2')}/bo/domain?version_id={version_id}&page_size=100&page={page}").json()['data']
        items = domains_resp.get('items', domains_resp) if isinstance(domains_resp, dict) else domains_resp
        domains.extend(items)
        total = domains_resp.get('total', 0) if isinstance(domains_resp, dict) else 0
        if len(domains) >= total or len(items) == 0:
            break
        page += 1

    sm_by_id = {str(sm.get('id') or sm.get('service_module_id')): sm for sm in sms if (sm.get('id') or sm.get('service_module_id')) is not None}
    sd_by_id = {str(sd.get('id') or sd.get('sub_domain_id')): sd for sd in sds if (sd.get('id') or sd.get('sub_domain_id')) is not None}

    bo_infos = []
    for bo in bos:
        sm_id = bo.get('service_module_id') or bo.get('serviceModuleId')
        sm = sm_by_id.get(str(sm_id)) if sm_id else None
        sd_id = sm.get('sub_domain_id') or sm.get('subDomainId') if sm else None
        sd = sd_by_id.get(str(sd_id)) if sd_id else None
        bo_infos.append({
            'id': bo.get('id'),
            'code': bo.get('code'),
            'name': bo.get('name'),
            'domainId': sd.get('domain_id') or sd.get('domainId') if sd else bo.get('domain_id') or bo.get('domainId'),
            'domain': sd.get('domain_name') or sd.get('domainName') if sd else bo.get('domain_name') or bo.get('domainName'),
            'subDomainId': sd.get('id') or sd.get('sub_domain_id') if sd else bo.get('sub_domain_id') or bo.get('subDomainId'),
            'subDomain': sd.get('name') or sd.get('sub_domain_name') if sd else bo.get('sub_domain_name') or bo.get('subDomainName'),
            'serviceModuleId': sm_id,
            'serviceModule': sm.get('name') or sm.get('service_module_name') if sm else bo.get('service_module_name') or bo.get('serviceModuleName'),
            'serviceModuleName': sm.get('name') or sm.get('service_module_name') if sm else bo.get('service_module_name') or bo.get('serviceModuleName'),
        })

    print(f"[bo_infos] count={len(bo_infos)}")
    print(f"[domains] count={len(domains)}")
    print(f"[domains] all: {[(d.get('id'), d.get('name')) for d in domains]}")

    # Find procurement domain (hardcoded for now: domain id=1 in v1)
    procurement = next((d for d in domains if d.get('id') == 1), None)
    if not procurement:
        for d in domains:
            name = d.get('name') or d.get('domain_name', '')
            if '采购' in name or 'procurement' in name.lower():
                procurement = d
                break
    if not procurement:
        procurement = domains[0] if domains else None
    print(f"\n[domain] using: id={procurement.get('id')}, name={procurement.get('name')}")
    domain_id = procurement['id']

    SCOPE_INTERNAL = 'internal'
    SCOPE_CROSS = 'cross-boundary'
    SCOPE_EXTERNAL = 'external'
    CAT_CROSS_DOMAIN = 'cross-domain'
    CAT_SAME_DOMAIN_CROSS_SUBDOMAIN = 'same-domain-cross-subdomain'
    CAT_SAME_SUBDOMAIN_CROSS_MODULE = 'same-subdomain-cross-module'
    CAT_SAME_MODULE = 'same-module'

    bo_by_id = {str(bo['id']): bo for bo in bo_infos if bo.get('id') is not None}
    bo_by_code = {str(bo.get('code', '')): bo for bo in bo_infos if bo.get('code')}

    def get_bo_info(rel, side):
        prefix = 'source' if side == 'source' else 'target'
        bo_id = rel.get(f'{prefix}_bo_id') or rel.get(f'{prefix}BoId')
        code = rel.get(f'{prefix}_code') or rel.get(f'{prefix}Code')
        if bo_id is not None and str(bo_id) in bo_by_id:
            return bo_by_id[str(bo_id)]
        if code and str(code) in bo_by_code:
            return bo_by_code[str(code)]
        if rel.get(f'{prefix}_domain_id') is not None or rel.get(f'{prefix}_code') or code:
            return {
                'id': rel.get(f'{prefix}_bo_id') or rel.get(f'{prefix}BoId'),
                'code': rel.get(f'{prefix}_code') or rel.get(f'{prefix}Code') or '',
                'name': rel.get(f'{prefix}_bo_name') or rel.get(f'{prefix}BoName') or rel.get(f'{prefix}_code') or '',
                'domainId': rel.get(f'{prefix}_domain_id') or rel.get(f'{prefix}DomainId'),
                'subDomainId': rel.get(f'{prefix}_sub_domain_id') or rel.get(f'{prefix}SubDomainId'),
                'serviceModuleId': rel.get(f'{prefix}_service_module_id') or rel.get(f'{prefix}ServiceModuleId'),
            }
        return None

    def classify_relation(rel, dom_ids):
        # If rel has scopeType AND categoryType (camelCase), use them
        if rel.get('scopeType') and rel.get('categoryType'):
            return {'scopeType': rel['scopeType'], 'categoryType': rel['categoryType']}

        src_bo = get_bo_info(rel, 'source')
        tgt_bo = get_bo_info(rel, 'target')

        if not src_bo or not tgt_bo:
            return None
        if src_bo.get('code') == tgt_bo.get('code'):
            return {'scopeType': SCOPE_EXTERNAL, 'categoryType': CAT_CROSS_DOMAIN, 'filtered': True}

        src_dom = src_bo.get('domainId')
        tgt_dom = tgt_bo.get('domainId')
        src_sub = src_bo.get('subDomainId')
        tgt_sub = tgt_bo.get('subDomainId')
        src_mod = src_bo.get('serviceModuleId')
        tgt_mod = tgt_bo.get('serviceModuleId')
        src_boid = src_bo.get('id')
        tgt_boid = tgt_bo.get('id')

        if dom_ids:
            src_in = src_dom in dom_ids
            tgt_in = tgt_dom in dom_ids
        else:
            src_in = True
            tgt_in = True

        if src_in and tgt_in:
            scope = SCOPE_INTERNAL
        elif src_in or tgt_in:
            scope = SCOPE_CROSS
        else:
            scope = SCOPE_EXTERNAL

        if src_dom != tgt_dom:
            cat = CAT_CROSS_DOMAIN
        elif src_sub != tgt_sub:
            cat = CAT_SAME_DOMAIN_CROSS_SUBDOMAIN
        elif src_mod != tgt_mod:
            cat = CAT_SAME_SUBDOMAIN_CROSS_MODULE
        else:
            cat = CAT_SAME_MODULE

        if scope != SCOPE_INTERNAL and cat == CAT_SAME_MODULE:
            if src_sub != tgt_sub:
                cat = CAT_SAME_DOMAIN_CROSS_SUBDOMAIN
            elif src_dom != tgt_dom:
                cat = CAT_CROSS_DOMAIN

        return {'scopeType': scope, 'categoryType': cat}

    # Dedupe
    seen = set()
    unique_rels = []
    for r in rels:
        rid = r.get('id') or r.get('relationCode') or r.get('relation_code')
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        unique_rels.append(r)

    print(f"\n[unique_rels] count={len(unique_rels)}")

    # Classify and collect
    classified = []
    for r in unique_rels:
        c = classify_relation(r, [domain_id])
        if not c or c.get('filtered'):
            continue
        classified.append((r, c))

    print(f"[classified] count={len(classified)}")

    # Group by scope
    by_scope = {SCOPE_INTERNAL: [], SCOPE_CROSS: [], SCOPE_EXTERNAL: []}
    for r, c in classified:
        by_scope[c['scopeType']].append(r)

    print("\n========== SCOPE BREAKDOWN ==========")
    for scope, rs in by_scope.items():
        ids = [r.get('id') for r in rs]
        print(f"  {scope}: count={len(rs)}, ids={ids}")
    print(f"  Internal ∪ Cross = {len(set([r.get('id') for r in by_scope[SCOPE_INTERNAL]] + [r.get('id') for r in by_scope[SCOPE_CROSS]]))}")

    # Print details of cross-boundary relations
    print("\n========== CROSS-BOUNDARY RELATION DETAILS ==========")
    for r in by_scope[SCOPE_CROSS]:
        src_bo = get_bo_info(r, 'source')
        tgt_bo = get_bo_info(r, 'target')
        print(f"  id={r.get('id')}, code={r.get('relation_code') or r.get('relationCode')}")
        print(f"    src: {src_bo.get('code')} domainId={src_bo.get('domainId')} subDomainId={src_bo.get('subDomainId')}")
        print(f"    tgt: {tgt_bo.get('code')} domainId={tgt_bo.get('domainId')} subDomainId={tgt_bo.get('subDomainId')}")

    # Now build the tree leaves and see what nodeKeysToRelationIds would return
    print("\n========== TREE LEAF RELATION IDS ==========")
    stats = {
        SCOPE_INTERNAL: {cat: {'count': 0, 'relations': [], 'domains': {}, 'modules': {}} for cat in [CAT_CROSS_DOMAIN, CAT_SAME_DOMAIN_CROSS_SUBDOMAIN, CAT_SAME_SUBDOMAIN_CROSS_MODULE, CAT_SAME_MODULE]},
        SCOPE_CROSS: {cat: {'count': 0, 'relations': [], 'domains': {}, 'modules': {}} for cat in [CAT_CROSS_DOMAIN, CAT_SAME_DOMAIN_CROSS_SUBDOMAIN, CAT_SAME_SUBDOMAIN_CROSS_MODULE, CAT_SAME_MODULE]},
        SCOPE_EXTERNAL: {cat: {'count': 0, 'relations': [], 'domains': {}, 'modules': {}} for cat in [CAT_CROSS_DOMAIN, CAT_SAME_DOMAIN_CROSS_SUBDOMAIN, CAT_SAME_SUBDOMAIN_CROSS_MODULE, CAT_SAME_MODULE]},
    }

    # Group into the structure (same as JS)
    for r, c in classified:
        src_bo = get_bo_info(r, 'source')
        tgt_bo = get_bo_info(r, 'target')
        scope = c['scopeType']
        cat = c['categoryType']
        s = stats[scope][cat]
        s['count'] += 1
        s['relations'].append(r)

        if cat == CAT_SAME_MODULE:
            mod_key = '-'.join(sorted([str(src_bo.get('serviceModuleId')), str(tgt_bo.get('serviceModuleId'))]))
            if mod_key not in s['modules']:
                s['modules'][mod_key] = {'name': mod_key, 'count': 0, 'relations': []}
            s['modules'][mod_key]['count'] += 1
            s['modules'][mod_key]['relations'].append(r)
        else:
            dom_key = '-'.join(sorted([str(src_bo.get('domainId')), str(tgt_bo.get('domainId'))]))
            if dom_key not in s['domains']:
                s['domains'][dom_key] = {'name': dom_key, 'subDomains': {}, 'relations': []}
            s['domains'][dom_key]['count'] = s['domains'][dom_key].get('count', 0) + 1
            s['domains'][dom_key]['relations'].append(r)

            sd_key = '-'.join(sorted([str(src_bo.get('subDomainId')), str(tgt_bo.get('subDomainId'))]))
            if sd_key not in s['domains'][dom_key]['subDomains']:
                s['domains'][dom_key]['subDomains'][sd_key] = {'name': sd_key, 'modules': {}, 'relations': []}
            s['domains'][dom_key]['subDomains'][sd_key]['count'] = s['domains'][dom_key]['subDomains'][sd_key].get('count', 0) + 1
            s['domains'][dom_key]['subDomains'][sd_key]['relations'].append(r)

            mod_key = '-'.join(sorted([str(src_bo.get('serviceModuleId')), str(tgt_bo.get('serviceModuleId'))]))
            if mod_key not in s['domains'][dom_key]['subDomains'][sd_key]['modules']:
                s['domains'][dom_key]['subDomains'][sd_key]['modules'][mod_key] = {'name': mod_key, 'count': 0, 'relations': []}
            s['domains'][dom_key]['subDomains'][sd_key]['modules'][mod_key]['count'] += 1
            s['domains'][dom_key]['subDomains'][sd_key]['modules'][mod_key]['relations'].append(r)

    # Simulate el-tree @check when both parents are checked
    # When user checks a parent in el-tree, ALL leaves under it become checked.
    # So nodeKeySet contains all leaf node IDs
    internal_leaf_node_ids = set()
    cross_leaf_node_ids = set()
    internal_leaf_relation_ids = set()
    cross_leaf_relation_ids = set()

    for scope in [SCOPE_INTERNAL, SCOPE_CROSS]:
        for cat in [CAT_CROSS_DOMAIN, CAT_SAME_DOMAIN_CROSS_SUBDOMAIN, CAT_SAME_SUBDOMAIN_CROSS_MODULE, CAT_SAME_MODULE]:
            s = stats[scope][cat]
            if cat == CAT_SAME_MODULE:
                for mod_key, mod_data in s['modules'].items():
                    leaf_id = f"{scope}-{cat}-module-{mod_key}"
                    rel_ids = [r.get('id') for r in mod_data['relations'] if r.get('id') is not None]
                    if scope == SCOPE_INTERNAL:
                        internal_leaf_node_ids.add(leaf_id)
                        internal_leaf_relation_ids.update(rel_ids)
                    else:
                        cross_leaf_node_ids.add(leaf_id)
                        cross_leaf_relation_ids.update(rel_ids)
            else:
                for dom_key, dom_data in s['domains'].items():
                    for sd_key, sd_data in dom_data['subDomains'].items():
                        for mod_key, mod_data in sd_data['modules'].items():
                            leaf_id = f"{scope}-{cat}-module-{mod_key}"
                            rel_ids = [r.get('id') for r in mod_data['relations'] if r.get('id') is not None]
                            if scope == SCOPE_INTERNAL:
                                internal_leaf_node_ids.add(leaf_id)
                                internal_leaf_relation_ids.update(rel_ids)
                            else:
                                cross_leaf_node_ids.add(leaf_id)
                                cross_leaf_relation_ids.update(rel_ids)

    print(f"\nInternal leaf NODE IDs: {len(internal_leaf_node_ids)}")
    print(f"Cross-boundary leaf NODE IDs: {len(cross_leaf_node_ids)}")
    print(f"\nInternal leaf RELATION IDs: {sorted(internal_leaf_relation_ids)}")
    print(f"Cross-boundary leaf RELATION IDs: {sorted(cross_leaf_relation_ids)}")
    print(f"\nUnion (internal + cross): {sorted(internal_leaf_relation_ids | cross_leaf_relation_ids)}")
    print(f"Intersection: {sorted(internal_leaf_relation_ids & cross_leaf_relation_ids)}")
    print(f"Total unique ids in union: {len(internal_leaf_relation_ids | cross_leaf_relation_ids)}")

    # Check el-tree @check behavior simulation:
    # When both parents are checked, checkedKeys should contain all leaf IDs
    print("\n========== SIMULATING EL-TREE @CHECK ==========")
    print("When user checks BOTH 'internal' AND 'cross-boundary' parents:")
    all_leaf_node_ids = internal_leaf_node_ids | cross_leaf_node_ids
    print(f"  checkedKeys (leaf IDs only): {sorted(all_leaf_node_ids)}")
    print(f"  Total: {len(all_leaf_node_ids)}")

    # Now nodeKeysToRelationIds walks tree, finds nodes with id in nodeKeySet
    # and collects their relationIds
    all_ids = internal_leaf_relation_ids | cross_leaf_relation_ids
    print(f"  Expected relationIds from nodeKeysToRelationIds: {sorted(all_ids)}")
    print(f"  Count: {len(all_ids)}")

    # Check if the cross-boundary leaf is visible (passes filterNodeMethod)
    # For cross-boundary rel, src.domainId=320, tgt.domainId=1
    # isRelationScopeMatch(domainIds=[1]) -> 320 in [1] || 1 in [1] = true
    # So the leaf should NOT be filtered out
    print("\n========== FILTER CHECK ==========")
    for r in by_scope[SCOPE_CROSS]:
        src_bo = get_bo_info(r, 'source')
        tgt_bo = get_bo_info(r, 'target')
        src_dom = src_bo.get('domainId')
        tgt_dom = tgt_bo.get('domainId')
        passes = (domain_id == src_dom) or (domain_id == tgt_dom)
        print(f"  id={r.get('id')}: src_dom={src_dom}, tgt_dom={tgt_dom}, filter passes={passes}")

if __name__ == "__main__":
    import sys
    import traceback
    output = open('d:/filework/excel-to-diagram/debug_output.txt', 'w', encoding='utf-8')

    class TeePrint:
        def __init__(self, *files):
            self.files = files
        def write(self, msg):
            for f in self.files:
                f.write(msg)
        def flush(self):
            for f in self.files:
                f.flush()

    original_stdout = sys.stdout
    sys.stdout = TeePrint(original_stdout, output)

    try:
        main()
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        sys.stdout = original_stdout
        output.close()
        raise
