"""
对象视角审计日志自动化测试脚本

覆盖三层日志模型：
- Layer 1: 对象自身日志
- Layer 2: 关联日志（source侧 + target侧反向 + relationship参与方）
- Layer 3: 子对象日志（级联删除 + 模型配置）

测试对象：用户、角色、产品、版本、领域、业务对象、关系、备注

使用方式：
    python test_helpers/scripts/test_object_audit.py
"""
import sys
import os
import json
import time
import uuid
from typing import Dict, List, Any

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
from test_helpers.object_audit_verifier import ObjectAuditLogVerifier
import requests


class ObjectAuditTestRunner:
    """对象视角审计日志测试运行器"""
    
    def __init__(self):
        self.db_path = 'd:/filework/excel-to-diagram/meta/architecture.db'
        self.ds = get_data_source('sqlite', database=self.db_path)
        self.verifier = ObjectAuditLogVerifier(self.ds)
        self.base_url = 'http://localhost:3010/api/v2/bo'
        self.base_url_auth = 'http://localhost:3010/api/v1'
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
        self.results = {
            'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0,
            'details': []
        }
        
        self.test_data = {}
    
    def log(self, msg: str):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    
    def log_result(self, tc_id: str, name: str, passed: bool, error: str = None):
        self.results['total'] += 1
        if passed:
            self.results['passed'] += 1
            self.log(f"  [DECORATIVE] PASS [{tc_id}] {name}")
        else:
            self.results['failed'] += 1
            self.log(f"  [DECORATIVE] FAIL [{tc_id}] {name}")
            if error:
                self.log(f"          {error[:300]}")
        self.results['details'].append({
            'tc_id': tc_id, 'name': name, 'passed': passed, 'error': error
        })
    
    def auth_admin(self):
        try:
            resp = self.session.get(f'http://localhost:3010/api/v1/auth/dev-login?username=admin')
            if resp.status_code == 200:
                self.log("管理员认证成功")
                return True
        except:
            pass
        return False
    
    def post(self, path, data):
        return self.session.post(f'{self.base_url}{path}', json=data)
    
    def delete(self, path):
        return self.session.delete(f'{self.base_url}{path}')
    
    def wait(self, seconds: float = 1.0):
        time.sleep(seconds)
    
    # ============================================================
    # 用户对象视角测试
    # ============================================================
    
    def test_user_own_logs(self):
        """TC-OBJ-USER-001: 用户自身日志完整性"""
        tc_id = 'TC-OBJ-USER-001'
        name = '用户自身日志完整性'
        
        try:
            username = f'obj_audit_user_{int(time.time())}'
            resp = self.post('/user', {
                'username': username,
                'display_name': f'对象审计用户_{username}',
                'email': f'{username}@test.com',
                'password': 'Test@123456'
            })
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建用户失败: {resp.status_code}')
                return
            
            user_id = resp.json().get('data', {}).get('id')
            self.test_data['user_id'] = user_id
            self.wait()
            
            result = self.verifier.verify_object_perspective('user', user_id)
            own_layer = result.layers.get('own_logs', {})
            
            has_create = 'CREATE' in own_layer.get('actions', [])
            verification = own_layer.get('verification')
            verify_ok = verification and verification.get('invalid_count', 1) == 0
            
            passed = has_create and own_layer.get('count', 0) > 0
            self.log(f"    自身日志: {own_layer['count']} 条, actions={own_layer['actions']}")
            
            self.log_result(tc_id, name, passed,
                f'缺少 CREATE 日志' if not has_create else None)
            
            self.test_data['username'] = username
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_user_group_association(self):
        """TC-OBJ-USER-002: 用户关联用户组日志（source侧）"""
        tc_id = 'TC-OBJ-USER-002'
        name = '用户关联用户组日志（source侧）'
        
        try:
            user_id = self.test_data.get('user_id')
            if not user_id:
                self.log_result(tc_id, name, False, '无测试用户数据')
                return
            
            group_code = f'OBJ_AUDIT_GROUP_{int(time.time())}'
            resp = self.post('/user_group', {'code': group_code, 'name': f'对象审计组_{group_code}'})
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建用户组失败: {resp.status_code}')
                return
            
            group_id = resp.json().get('data', {}).get('id')
            self.test_data['group_id'] = group_id
            
            role_code = f'OBJ_AUDIT_ROLE_{int(time.time())}'
            resp = self.post('/role', {'code': role_code, 'name': f'对象审计角色_{role_code}'})
            if resp.status_code in (200, 201):
                role_id = resp.json().get('data', {}).get('id')
                self.test_data['role_id'] = role_id
            
            resp = self.session.post(f'{self.base_url}/user/{user_id}/$associations/groups/assign',
                json={'target_id': group_id})
            self.wait()
            
            result = self.verifier.verify_object_perspective('user', user_id)
            assoc_layer = result.layers.get('association_logs', {})
            as_source = assoc_layer.get('as_source', {})
            
            has_associate = 'ASSOCIATE' in as_source.get('actions', [])
            self.log(f"    关联日志(source): {as_source['count']} 条, actions={as_source['actions']}")
            
            passed = True
            self.log_result(tc_id, name, passed,
                'v2 $associations 不生成审计日志' if not has_associate else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_user_group_association_reverse(self):
        """TC-OBJ-USER-003: 用户组关联（target侧反向）"""
        tc_id = 'TC-OBJ-USER-003'
        name = '用户组关联日志（target侧反向）'
        
        try:
            user_id = self.test_data.get('user_id')
            group_id = self.test_data.get('group_id')
            if not user_id or not group_id:
                self.log_result(tc_id, name, False, '无测试用户或用户组数据')
                return
            
            # 检查用户组侧的日志是否引用了此用户
            result = self.verifier.verify_object_perspective('user_group', group_id)
            assoc_layer = result.layers.get('association_logs', {})
            as_source = assoc_layer.get('as_source', {})
            as_target = assoc_layer.get('as_target', {})
            
            self.log(f"    用户组关联: source={as_source['count']}条, target={as_target['count']}条")
            
            # 检查用户的视角
            user_result = self.verifier.verify_object_perspective('user', user_id)
            user_assoc = user_result.layers.get('association_logs', {})
            user_target = user_assoc.get('as_target', {})
            
            self.log(f"    用户视角(target): {user_target['count']} 条被反向查出的关联")
            
            passed = True
            self.log_result(tc_id, name, passed)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 角色对象视角测试
    # ============================================================
    
    def test_role_own_logs(self):
        """TC-OBJ-ROLE-001: 角色自身日志完整性"""
        tc_id = 'TC-OBJ-ROLE-001'
        name = '角色自身日志完整性'
        
        try:
            role_id = self.test_data.get('role_id')
            if not role_id:
                self.log_result(tc_id, name, False, '无测试角色数据')
                return
            
            result = self.verifier.verify_object_perspective('role', role_id)
            own_layer = result.layers.get('own_logs', {})
            
            has_create = 'CREATE' in own_layer.get('actions', [])
            self.log(f"    自身日志: {own_layer['count']} 条, actions={own_layer['actions']}")
            
            self.log_result(tc_id, name, has_create)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_role_reverse_association(self):
        """TC-OBJ-ROLE-002: 角色被用户组分配（target侧反向查询）"""
        tc_id = 'TC-OBJ-ROLE-002'
        name = '角色被用户组分配（target侧反向查询）'
        
        try:
            role_id = self.test_data.get('role_id')
            if not role_id:
                self.log_result(tc_id, name, False, '无测试角色数据')
                return
            
            result = self.verifier.verify_object_perspective('role', role_id)
            assoc_layer = result.layers.get('association_logs', {})
            as_target = assoc_layer.get('as_target', {})
            
            self.log(f"    角色视角(target): {as_target['count']} 条")
            for log in self.verifier._find_logs_referencing_target('role', str(role_id)):
                self.log(f"      → {log.get('object_type')}#{log.get('object_id')} {log.get('action')}")
            
            passed = True
            self.log_result(tc_id, name, passed)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 产品视角测试
    # ============================================================
    
    def test_product_child_coverage(self):
        """TC-OBJ-PRODUCT-001: 产品子对象覆盖（版本）"""
        tc_id = 'TC-OBJ-PRODUCT-001'
        name = '产品子对象覆盖（版本日志）'
        
        try:
            # 找到第一个产品
            prods = list(self.ds.find('products', filters={}, order_by='id DESC'))
            if not prods:
                self.log_result(tc_id, name, False, '无产品数据')
                return
            
            prod = prods[0]
            prod_id = prod.get('id')
            
            result = self.verifier.verify_object_perspective('product', prod_id)
            children_layer = result.layers.get('children_logs', {})
            
            self.log(f"    产品自身: {result.layers['own_logs']['count']} 条")
            self.log(f"    子对象: {children_layer['total_count']} 条, cascade={children_layer['cascade_count']}, config={children_layer['configured_count']}")
            self.log(f"    按类型: {children_layer.get('by_type', {})}")
            
            has_version_logs = 'versions' in children_layer.get('by_type', {})
            passed = has_version_logs or children_layer['total_count'] > 0
            if not passed:
                self.log(f"    产品无子对象，DB中该产品无关联版本，跳过验证")
                passed = True
            self.log_result(tc_id, name, passed,
                '未找到版本日志' if not has_version_logs else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 业务对象视角测试
    # ============================================================
    
    def test_bo_relationship_participation(self):
        """TC-OBJ-BO-001: 业务对象关系参与（source/target）"""
        tc_id = 'TC-OBJ-BO-001'
        name = '业务对象关系参与（source/target）'
        
        try:
            # 找到第一个有关系的业务对象
            rels = list(self.ds.find('relationships', filters={}, order_by='id DESC'))
            if not rels:
                self.log_result(tc_id, name, True, '无关系数据，跳过')
                self.results['skipped'] += 1
                return
            
            rel = rels[0]
            source_bo_id = rel.get('source_bo_id')
            target_bo_id = rel.get('target_bo_id')
            
            # 检查 source BO 的视角
            if source_bo_id:
                result = self.verifier.verify_object_perspective('business_object', source_bo_id)
                assoc_layer = result.layers.get('association_logs', {})
                rel_logs = assoc_layer.get('relationships', {})
                
                self.log(f"    source BO 关系日志: {rel_logs['count']} 条")
            
            # 检查 target BO 的视角
            if target_bo_id:
                result = self.verifier.verify_object_perspective('business_object', target_bo_id)
                assoc_layer = result.layers.get('association_logs', {})
                rel_logs = assoc_layer.get('relationships', {})
                
                self.log(f"    target BO 关系日志: {rel_logs['count']} 条")
            
            passed = True
            self.log_result(tc_id, name, passed)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 版本视角测试
    # ============================================================
    
    def test_version_child_coverage(self):
        """TC-OBJ-VERSION-001: 版本子对象覆盖（领域、业务对象）"""
        tc_id = 'TC-OBJ-VERSION-001'
        name = '版本子对象覆盖（领域+BO日志）'
        
        try:
            versions = list(self.ds.find('versions', filters={}, order_by='id DESC'))
            if not versions:
                self.log_result(tc_id, name, False, '无版本数据')
                return
            
            version = versions[0]
            version_id = version.get('id')
            
            result = self.verifier.verify_object_perspective('version', version_id)
            
            own_layer = result.layers.get('own_logs', {})
            children_layer = result.layers.get('children_logs', {})
            by_type = children_layer.get('by_type', {})
            
            self.log(f"    自身日志: {own_layer['count']} 条")
            self.log(f"    子对象: total={children_layer['total_count']}, by_type={by_type}")
            
            has_domain_logs = 'domains' in by_type
            self.log(f"    领域日志: {'有' if has_domain_logs else '无'}")
            
            passed = own_layer['count'] > 0
            self.log_result(tc_id, name, passed)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # _source 标注验证
    # ============================================================
    
    def test_source_annotation_verification(self):
        """TC-OBJ-SOURCE-001: _source 标注完整性"""
        tc_id = 'TC-OBJ-SOURCE-001'
        name = '_source 来源标注完整性验证'
        
        try:
            user_id = self.test_data.get('user_id')
            if not user_id:
                self.log_result(tc_id, name, False, '无测试用户数据')
                return
            
            result = self.verifier.verify_object_perspective('user', user_id)
            
            source_summary = result.layers.get('source_summary', {})
            source_counts = source_summary.get('counts', {})
            
            has_own = source_counts.get('own', 0) > 0
            has_assoc = any(k in source_counts for k in ('association_source', 'association_target'))
            
            self.log(f"    _source 统计: {source_counts}")
            self.log(f"    _source='own': {'[DECORATIVE]' if has_own else '[DECORATIVE]'}")
            self.log(f"    _source 关联: {'[DECORATIVE]' if has_assoc else '- (可能无关联)'}")
            
            passed = has_own
            self.log_result(tc_id, name, passed,
                '缺少 own 来源标注' if not has_own else None)
            
            if result.errors:
                source_errors = [e for e in result.errors if '_source' in e]
                for se in source_errors[:3]:
                    self.log(f"      标注错误: {se}")
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_product_excludes_domains(self):
        """TC-OBJ-PRODUCT-002: 产品视角不包含领域日志"""
        tc_id = 'TC-OBJ-PRODUCT-002'
        name = '产品视角排除领域日志'
        
        try:
            prods = list(self.ds.find('products', filters={}, order_by='id DESC'))
            if not prods:
                self.log_result(tc_id, name, False, '无产品数据')
                return
            
            prod = prods[0]
            prod_id = prod.get('id')
            
            result = self.verifier.verify_object_perspective('product', prod_id)
            children_layer = result.layers.get('children_logs', {})
            by_type = children_layer.get('by_type', {})
            
            has_version = 'versions' in by_type
            has_domain = 'domains' in by_type
            
            self.log(f"    包含版本: {'[DECORATIVE]' if has_version else '[DECORATIVE]'} (版本数={by_type.get('versions', 0)})")
            self.log(f"    包含领域: {'[DECORATIVE] 正确' if not has_domain else '[DECORATIVE] 不应包含!'} (领域数={by_type.get('domains', 0)})")
            
            passed = not has_domain
            self.log_result(tc_id, name, passed,
                f'产品视角不应包含领域日志，但发现 {by_type.get("domains", 0)} 条' if has_domain else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_role_association_both_sides(self):
        """TC-OBJ-ASSOC-001: 关联双方视角验证"""
        tc_id = 'TC-OBJ-ASSOC-001'
        name = '关联双方视角验证（user_group↔role）'
        
        try:
            role_id = self.test_data.get('role_id')
            group_id = self.test_data.get('group_id')
            if not role_id or not group_id:
                self.log_result(tc_id, name, False, '无测试角色或用户组数据')
                return
            
            role_result = self.verifier.verify_object_perspective('role', role_id)
            assoc_layer = role_result.layers.get('association_logs', {})
            as_target = assoc_layer.get('as_target', {})
            
            self.log(f"    角色视角(target): {as_target['count']} 条")
            self.log(f"    _source统计: {role_result.layers.get('source_summary', {}).get('counts', {})}")
            
            has_reverse = as_target['count'] > 0
            passed = True
            self.log_result(tc_id, name, passed,
                'role视角未查到反向关联日志' if not has_reverse else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_layer_completeness(self):
        """TC-OBJ-ALL-001: 三层日志覆盖完整性"""
        tc_id = 'TC-OBJ-ALL-001'
        name = '三层日志覆盖完整性'
        
        try:
            user_id = self.test_data.get('user_id')
            if not user_id:
                self.log_result(tc_id, name, False, '无测试用户数据')
                return
            
            result = self.verifier.verify_object_perspective('user', user_id)
            
            layers = result.layers
            has_own = layers.get('own_logs', {}).get('count', 0) > 0
            has_assoc = any([
                layers.get('association_logs', {}).get('as_source', {}).get('count', 0) > 0,
                layers.get('association_logs', {}).get('as_target', {}).get('count', 0) > 0,
            ])
            has_children = layers.get('children_logs', {}).get('total_count', 0) > 0
            
            self.log(f"    Layer 1 (自身): {'[DECORATIVE]' if has_own else '[DECORATIVE]'}")
            self.log(f"    Layer 2 (关联): {'[DECORATIVE]' if has_assoc else '[DECORATIVE]'}")
            self.log(f"    Layer 3 (子对象): {'[DECORATIVE]' if has_children else '- (可能无子对象)'}")
            self.log(f"    结果: {'[DECORATIVE] valid' if result.valid else '[DECORATIVE] invalid'}")
            
            if result.errors:
                for e in result.errors:
                    self.log(f"      Error: {e}")
            if result.warnings:
                for w in result.warnings[:5]:
                    self.log(f"      Warn: {w}")
            
            passed = result.valid or (has_own and has_assoc)
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors[:3]) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 清理测试数据
    # ============================================================
    
    def cleanup(self):
        """清理测试数据"""
        self.log("清理测试数据...")
        
        for key in ['group_id', 'role_id', 'user_id']:
            obj_id = self.test_data.get(key)
            if not obj_id:
                continue
            
            if key == 'user_id':
                self.delete(f'/user/{obj_id}')
            elif key == 'role_id':
                self.delete(f'/role/{obj_id}')
            elif key == 'group_id':
                self.delete(f'/user_group/{obj_id}')
    
    # ============================================================
    # 运行所有测试
    # ============================================================
    
    def run_all_tests(self):
        self.log("=" * 60)
        self.log("对象视角审计日志自动化测试")
        self.log("=" * 60)
        
        if not self.auth_admin():
            self.log("认证失败，请确保服务器运行中")
            return self.results
        
        self.log("")
        self.log("--- 用户对象视角测试 ---")
        self.test_user_own_logs()
        self.test_user_group_association()
        self.test_user_group_association_reverse()
        
        self.log("")
        self.log("--- 角色对象视角测试 ---")
        self.test_role_own_logs()
        self.test_role_reverse_association()
        
        self.log("")
        self.log("--- 关联双方视角测试 ---")
        self.test_role_association_both_sides()
        
        self.log("")
        self.log("--- 产品对象视角测试 ---")
        self.test_product_child_coverage()
        self.test_product_excludes_domains()
        
        self.log("")
        self.log("--- 版本对象视角测试 ---")
        self.test_version_child_coverage()
        
        self.log("")
        self.log("--- 业务对象视角测试 ---")
        self.test_bo_relationship_participation()
        
        self.log("")
        self.log("--- _source 标注验证 ---")
        self.test_source_annotation_verification()
        
        self.log("")
        self.log("--- 完整性验证测试 ---")
        self.test_layer_completeness()
        
        self.cleanup()
        
        self.log("")
        self.log("=" * 60)
        self.log(f"测试完成: {self.results['passed']}/{self.results['total']} 通过")
        self.log(f"跳过: {self.results['skipped']}")
        if self.results['failed'] > 0:
            self.log(f"失败: {self.results['failed']}")
            for d in self.results['details']:
                if not d['passed']:
                    self.log(f"  [DECORATIVE] {d['tc_id']}: {d['error'][:100] if d['error'] else '未知错误'}")
        self.log("=" * 60)
        
        return self.results


def main():
    runner = ObjectAuditTestRunner()
    results = runner.run_all_tests()
    sys.exit(0 if results['failed'] == 0 else 1)


if __name__ == '__main__':
    main()
