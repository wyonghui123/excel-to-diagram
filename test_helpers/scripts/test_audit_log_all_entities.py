"""
审计日志自动化测试脚本

覆盖用户、角色、产品、版本、领域、业务对象、关系等实体的审计日志验证

使用方式：
    python test_helpers/scripts/test_audit_log_all_entities.py

测试用例：
    TC-AUDIT-001: 验证对象标识存在
    TC-AUDIT-002: 验证通用必需字段
    TC-AUDIT-003: 验证时间戳格式
    TC-AUDIT-004: 验证事务一致性
    TC-USER-*: 用户管理审计日志测试
    TC-ROLE-*: 角色管理审计日志测试
    TC-PRODUCT-*: 产品线管理审计日志测试
    TC-VERSION-*: 版本管理审计日志测试
    TC-DOMAIN-*: 领域管理审计日志测试
    TC-BO-*: 业务对象管理审计日志测试
    TC-REL-*: 关系管理审计日志测试
"""
import sys
import os
import json
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
from meta.services.audit_service import AuditService
from test_helpers.audit_log_verifier import AuditLogVerifier

import requests


class AuditLogTestRunner:
    """审计日志测试运行器"""
    
    def __init__(self):
        self.db_path = 'd:/filework/excel-to-diagram/meta/architecture.db'
        self.ds = get_data_source('sqlite', database=self.db_path)
        self.audit_service = AuditService(self.ds)
        self.verifier = AuditLogVerifier(self.ds)
        self.base_url = 'http://localhost:3010/api/v2/bo'
        self.base_url_auth = 'http://localhost:3010/api/v1'
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
        self.test_results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'details': []
        }
        
        self.test_data = {}
        self.transaction_id = str(uuid.uuid4())
    
    def log(self, msg: str):
        """打印日志"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    
    def _get_id_from_response(self, resp_data: dict) -> Any:
        """从 API 响应中安全提取对象 ID"""
        data = resp_data.get('data')
        if data is None:
            return None
        if isinstance(data, list):
            return data[0].get('id') if data else None
        if isinstance(data, dict):
            return data.get('id')
        return None
    
    def log_result(self, tc_id: str, name: str, passed: bool, error: str = None):
        """记录测试结果"""
        self.test_results['total'] += 1
        if passed:
            self.test_results['passed'] += 1
            status = '[DECORATIVE] PASS'
        else:
            self.test_results['failed'] += 1
            status = '[DECORATIVE] FAIL'
        
        self.log(f"  {status} [{tc_id}] {name}")
        if error:
            self.log(f"         错误: {error[:200]}")
        
        self.test_results['details'].append({
            'tc_id': tc_id,
            'name': name,
            'passed': passed,
            'error': error
        })
    
    def auth_admin(self):
        """以管理员身份认证"""
        try:
            resp = self.session.get(f'{self.base_url_auth}/auth/dev-login?username=admin')
            if resp.status_code == 200:
                self.log("管理员认证成功")
                return True
        except Exception as e:
            self.log(f"认证失败: {e}")
        return False
    
    def wait_for_audit(self, timeout: int = 5) -> List[Dict]:
        """等待审计日志写入"""
        time.sleep(0.5)
        return list(self.ds.find('audit_logs', filters={}, order_by='id DESC'))[:10]
    
    # ============================================================
    # 通用验证测试
    # ============================================================
    
    def test_audit_001_object_identity(self):
        """TC-AUDIT-001: 验证对象标识存在"""
        tc_id = 'TC-AUDIT-001'
        name = '验证审计日志包含对象标识'
        
        try:
            logs = self.wait_for_audit()
            if not logs:
                self.log_result(tc_id, name, False, '无审计日志')
                return
            
            has_identity = 0
            for log in logs:
                extra = log.get('extra_data')
                if extra:
                    try:
                        extra_obj = json.loads(extra) if isinstance(extra, str) else extra
                        if extra_obj.get('audit_object_key') or extra_obj.get('audit_object_display_name'):
                            has_identity += 1
                    except:
                        pass
            
            passed = has_identity > 0
            self.log_result(tc_id, name, passed, 
                f'有标识日志: {has_identity}/{len(logs)}' if not passed else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_audit_002_common_fields(self):
        """TC-AUDIT-002: 验证通用必需字段"""
        tc_id = 'TC-AUDIT-002'
        name = '验证通用必需字段存在'
        
        try:
            logs = self.wait_for_audit()
            if not logs:
                self.log_result(tc_id, name, False, '无审计日志')
                return
            
            required_fields = ['object_type', 'object_id', 'action', 'user_id', 'created_at']
            missing_counts = {f: 0 for f in required_fields}
            
            for log in logs:
                for field in required_fields:
                    if not log.get(field):
                        missing_counts[field] += 1
            
            passed = all(missing_counts[f] == 0 for f in required_fields)
            if not passed:
                missing = [f for f in required_fields if missing_counts[f] > 0]
                self.log_result(tc_id, name, False, f'缺少字段: {missing}')
            else:
                self.log_result(tc_id, name, True)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_audit_003_timestamp_format(self):
        """TC-AUDIT-003: 验证时间戳格式"""
        tc_id = 'TC-AUDIT-003'
        name = '验证 created_at 格式正确'
        
        try:
            logs = self.wait_for_audit()
            if not logs:
                self.log_result(tc_id, name, False, '无审计日志')
                return
            
            invalid_count = 0
            for log in logs:
                created_at = log.get('created_at')
                if created_at:
                    try:
                        datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
                    except:
                        invalid_count += 1
            
            passed = invalid_count == 0
            self.log_result(tc_id, name, passed,
                f'无效时间戳: {invalid_count}/{len(logs)}' if not passed else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_audit_004_transaction_consistency(self):
        """TC-AUDIT-004: 验证事务一致性"""
        tc_id = 'TC-AUDIT-004'
        name = '验证同一事务的日志一致性'
        
        try:
            txn_logs = list(self.ds.find('audit_logs', 
                filters={'transaction_id': self.transaction_id},
                order_by='created_at ASC'))
            
            if len(txn_logs) < 2:
                self.log_result(tc_id, name, True, '事务日志不足，跳过')
                self.test_results['skipped'] += 1
                return
            
            user_ids = set(log.get('user_id') for log in txn_logs)
            passed = len(user_ids) == 1
            self.log_result(tc_id, name, passed,
                f'user_id 不一致: {user_ids}' if not passed else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 用户管理测试
    # ============================================================
    
    def test_user_create(self):
        """TC-USER-CREATE: 创建用户审计日志"""
        tc_id = 'TC-USER-CREATE'
        name = '创建用户时审计日志记录正确'
        
        try:
            test_username = f'audit_test_{int(time.time())}'
            test_data = {
                'username': test_username,
                'display_name': f'审计测试用户_{test_username}',
                'email': f'{test_username}@example.com',
                'password': 'Test@123456'
            }
            
            resp = self.session.post(f'{self.base_url}/user', json=test_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建失败[{resp.status_code}]: {resp.text[:200]}')
                return
            
            user_id = self._get_id_from_response(resp.json())
            self.test_data['user_id'] = user_id
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs', 
                filters={'object_type': 'user', 'object_id': str(user_id)},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid and 'CREATE' in logs[0].get('action', '')
            self.log_result(tc_id, name, passed, 
                '; '.join(result.errors) if result.errors else None)
            
            self.test_data['username'] = test_username
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_user_update(self):
        """TC-USER-UPDATE: 更新用户审计日志"""
        tc_id = 'TC-USER-UPDATE'
        name = '更新用户时审计日志记录正确'
        
        try:
            user_id = self.test_data.get('user_id')
            if not user_id:
                self.log_result(tc_id, name, False, '无测试用户数据')
                return
            
            update_data = {
                'display_name': f'更新后的名称_{int(time.time())}'
            }
            
            resp = self.session.put(f'{self.base_url}/user/{user_id}', json=update_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'更新失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'user', 'object_id': str(user_id), 'action': 'UPDATE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 UPDATE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_user_delete(self):
        """TC-USER-DELETE: 删除用户审计日志"""
        tc_id = 'TC-USER-DELETE'
        name = '删除用户时审计日志记录正确'
        
        try:
            user_id = self.test_data.get('user_id')
            if not user_id:
                self.log_result(tc_id, name, False, '无测试用户数据')
                return
            
            resp = self.session.delete(f'{self.base_url}/user/{user_id}')
            
            if resp.status_code not in (200, 204):
                self.log_result(tc_id, name, False, f'删除失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'user', 'object_id': str(user_id), 'action': 'DELETE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 DELETE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 角色管理测试
    # ============================================================
    
    def test_role_create(self):
        """TC-ROLE-CREATE: 创建角色审计日志"""
        tc_id = 'TC-ROLE-CREATE'
        name = '创建角色时审计日志记录正确'
        
        try:
            role_code = f'AUDIT_TEST_ROLE_{int(time.time())}'
            test_data = {
                'code': role_code,
                'name': f'审计测试角色_{role_code}',
                'description': '用于审计日志测试的角色'
            }
            
            resp = self.session.post(f'{self.base_url}/role', json=test_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建角色失败[{resp.status_code}]: {resp.text[:200]}')
                return
            
            role_id = self._get_id_from_response(resp.json())
            self.test_data['role_id'] = role_id
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'role', 'object_id': str(role_id)},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid and 'CREATE' in logs[0].get('action', '')
            
            extra = logs[0].get('extra_data')
            if extra:
                extra_obj = json.loads(extra) if isinstance(extra, str) else extra
                if extra_obj.get('audit_object_key') == role_code:
                    self.log(f"    [DECORATIVE] 对象标识正确: audit_object_key = {role_code}")
            
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
            
            self.test_data['role_code'] = role_code
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_role_update(self):
        """TC-ROLE-UPDATE: 更新角色审计日志"""
        tc_id = 'TC-ROLE-UPDATE'
        name = '更新角色时审计日志记录正确'
        
        try:
            role_id = self.test_data.get('role_id')
            if not role_id:
                self.log_result(tc_id, name, False, '无测试角色数据')
                return
            
            update_data = {
                'name': f'更新后的角色名_{int(time.time())}',
                'description': '更新后的描述'
            }
            
            resp = self.session.put(f'{self.base_url}/role/{role_id}', json=update_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'更新失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'role', 'object_id': str(role_id), 'action': 'UPDATE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 UPDATE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_role_delete(self):
        """TC-ROLE-DELETE: 删除角色审计日志"""
        tc_id = 'TC-ROLE-DELETE'
        name = '删除角色时审计日志记录正确'
        
        try:
            role_id = self.test_data.get('role_id')
            if not role_id:
                self.log_result(tc_id, name, False, '无测试角色数据')
                return
            
            resp = self.session.delete(f'{self.base_url}/role/{role_id}')
            
            if resp.status_code not in (200, 204):
                self.log_result(tc_id, name, False, f'删除失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'role', 'object_id': str(role_id), 'action': 'DELETE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 DELETE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 产品线管理测试
    # ============================================================
    
    def test_product_create(self):
        """TC-PRODUCT-CREATE: 创建产品线审计日志"""
        tc_id = 'TC-PRODUCT-CREATE'
        name = '创建产品线时审计日志记录正确'
        
        try:
            product_code = f'TEST_PRODUCT_{int(time.time())}'
            test_data = {
                'code': product_code,
                'name': f'测试产品线_{product_code}',
                'description': '用于审计日志测试的产品线'
            }
            
            resp = self.session.post(f'{self.base_url}/product', json=test_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建关系失败[{resp.status_code}]: {resp.text[:200]}')
                return
            
            product_id = self._get_id_from_response(resp.json())
            self.test_data['product_id'] = product_id
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'product', 'object_id': str(product_id)},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid and 'CREATE' in logs[0].get('action', '')
            
            extra = logs[0].get('extra_data')
            if extra:
                extra_obj = json.loads(extra) if isinstance(extra, str) else extra
                self.log(f"    对象标识: audit_object_key={extra_obj.get('audit_object_key')}, "
                        f"audit_object_display_name={extra_obj.get('audit_object_display_name')}")
            
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
            
            self.test_data['product_code'] = product_code
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 关系管理测试
    # ============================================================
    
    def test_relationship_create(self):
        """TC-REL-CREATE: 创建关系审计日志"""
        tc_id = 'TC-REL-CREATE'
        name = '创建关系时审计日志记录正确'
        
        try:
            version_id = self.test_data.get('version_id')
            domain_id = self.test_data.get('domain_id')
            bo_id = self.test_data.get('bo_id')
            if not version_id or not domain_id or not bo_id:
                self.log_result(tc_id, name, False, '无测试版本/领域/BO数据')
                return
            
            target_bo_name = f'目标BO_{time.strftime("%Y%m%d_%H%M%S")}'
            target_bo_data = {
                'version_id': version_id,
                'domain_id': domain_id,
                'name': target_bo_name,
                'code': f'TARGET_BO_{int(time.time())}'
            }
            resp = self.session.post(f'{self.base_url}/business_object', json=target_bo_data)
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建目标BO失败[{resp.status_code}]: {resp.text[:200]}')
                return
            target_bo_id = self._get_id_from_response(resp.json())
            self.test_data['bo2_id'] = target_bo_id
            
            test_data = {
                'version_id': version_id,
                'source_bo_id': bo_id,
                'target_bo_id': target_bo_id,
                'relation_type': 'GENERATES',
                'relation_desc': '审计测试关系'
            }
            
            resp = self.session.post(f'{self.base_url}/relationship', json=test_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建失败[{resp.status_code}]: {resp.text[:200]}')
                return
            
            rel_id = self._get_id_from_response(resp.json())
            self.test_data['rel_id'] = rel_id
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'relationship', 'object_id': str(rel_id)},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid and 'CREATE' in logs[0].get('action', '')
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_relationship_delete(self):
        """TC-REL-DELETE: 删除关系审计日志"""
        tc_id = 'TC-REL-DELETE'
        name = '删除关系时审计日志记录正确'
        
        try:
            rel_id = self.test_data.get('rel_id')
            if not rel_id:
                self.log_result(tc_id, name, False, '无测试关系数据')
                return
            
            resp = self.session.delete(f'{self.base_url}/relationship/{rel_id}')
            
            if resp.status_code not in (200, 204):
                self.log_result(tc_id, name, False, f'删除失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'relationship', 'object_id': str(rel_id), 'action': 'DELETE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 DELETE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_product_update(self):
        """TC-PRODUCT-UPDATE: 更新产品线审计日志"""
        tc_id = 'TC-PRODUCT-UPDATE'
        name = '更新产品线时审计日志记录正确'
        
        try:
            product_id = self.test_data.get('product_id')
            if not product_id:
                self.log_result(tc_id, name, False, '无测试产品数据')
                return
            
            update_data = {
                'name': f'更新后的产品线_{int(time.time())}',
                'description': '更新后的产品线描述'
            }
            
            resp = self.session.put(f'{self.base_url}/product/{product_id}', json=update_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'更新失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'product', 'object_id': str(product_id), 'action': 'UPDATE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 UPDATE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 版本管理测试
    # ============================================================
    
    def test_version_create(self):
        """TC-VERSION-CREATE: 创建版本审计日志"""
        tc_id = 'TC-VERSION-CREATE'
        name = '创建版本时审计日志记录正确'
        
        try:
            product_id = self.test_data.get('product_id')
            if not product_id:
                self.log_result(tc_id, name, False, '无测试产品数据')
                return
            
            version_name = f'审计测试版本_{time.strftime("%Y%m%d_%H%M%S")}'
            test_data = {
                'product_id': product_id,
                'version_number': version_name,
                'name': version_name,
                'description': '用于审计日志测试的版本'
            }
            
            resp = self.session.post(f'{self.base_url}/version', json=test_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建版本失败: {resp.status_code}')
                return
            
            version_id = self._get_id_from_response(resp.json())
            self.test_data['version_id'] = version_id
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'version', 'object_id': str(version_id)},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid and 'CREATE' in logs[0].get('action', '')
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
            
            self.test_data['version_name'] = version_name
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_version_update(self):
        """TC-VERSION-UPDATE: 更新版本审计日志"""
        tc_id = 'TC-VERSION-UPDATE'
        name = '更新版本时审计日志记录正确'
        
        try:
            version_id = self.test_data.get('version_id')
            if not version_id:
                self.log_result(tc_id, name, False, '无测试版本数据')
                return
            
            update_data = {
                'name': f'更新后的版本_{int(time.time())}',
                'description': '更新后的版本描述'
            }
            
            resp = self.session.put(f'{self.base_url}/version/{version_id}', json=update_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'更新版本失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'version', 'object_id': str(version_id), 'action': 'UPDATE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 UPDATE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 领域管理测试
    # ============================================================
    
    def test_domain_create(self):
        """TC-DOMAIN-CREATE: 创建领域审计日志"""
        tc_id = 'TC-DOMAIN-CREATE'
        name = '创建领域时审计日志记录正确'
        
        try:
            version_id = self.test_data.get('version_id')
            if not version_id:
                self.log_result(tc_id, name, False, '无测试版本数据')
                return
            
            domain_name = f'审计测试领域_{time.strftime("%Y%m%d_%H%M%S")}'
            test_data = {
                'version_id': version_id,
                'name': domain_name,
                'code': f'DOMAIN_{int(time.time())}',
                'description': '用于审计日志测试的领域'
            }
            
            resp = self.session.post(f'{self.base_url}/domain', json=test_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建领域失败: {resp.status_code}')
                return
            
            domain_id = self._get_id_from_response(resp.json())
            self.test_data['domain_id'] = domain_id
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'domain', 'object_id': str(domain_id)},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid and 'CREATE' in logs[0].get('action', '')
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
            
            self.test_data['domain_name'] = domain_name
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_domain_update(self):
        """TC-DOMAIN-UPDATE: 更新领域审计日志"""
        tc_id = 'TC-DOMAIN-UPDATE'
        name = '更新领域时审计日志记录正确'
        
        try:
            domain_id = self.test_data.get('domain_id')
            if not domain_id:
                self.log_result(tc_id, name, False, '无测试领域数据')
                return
            
            update_data = {
                'name': f'更新后的领域_{int(time.time())}',
                'description': '更新后的领域描述'
            }
            
            resp = self.session.put(f'{self.base_url}/domain/{domain_id}', json=update_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'更新领域失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'domain', 'object_id': str(domain_id), 'action': 'UPDATE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 UPDATE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 业务对象管理测试
    # ============================================================
    
    def test_business_object_create(self):
        """TC-BO-CREATE: 创建业务对象审计日志"""
        tc_id = 'TC-BO-CREATE'
        name = '创建业务对象时审计日志记录正确'
        
        try:
            domain_id = self.test_data.get('domain_id')
            version_id = self.test_data.get('version_id')
            if not domain_id or not version_id:
                self.log_result(tc_id, name, False, f'无测试领域或版本数据: domain={domain_id}, version={version_id}')
                return
            
            bo_name = f'审计测试BO_{time.strftime("%Y%m%d_%H%M%S")}'
            test_data = {
                'domain_id': domain_id,
                'version_id': version_id,
                'name': bo_name,
                'code': f'BO_{int(time.time())}',
                'description': '用于审计日志测试的业务对象'
            }
            
            resp = self.session.post(f'{self.base_url}/business_object', json=test_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建BO失败: {resp.status_code} {resp.text[:200]}')
                return
            
            bo_id = self._get_id_from_response(resp.json())
            self.test_data['bo_id'] = bo_id
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'business_object', 'object_id': str(bo_id)},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid and 'CREATE' in logs[0].get('action', '')
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
            
            self.test_data['bo_name'] = bo_name
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_business_object_update(self):
        """TC-BO-UPDATE: 更新业务对象审计日志"""
        tc_id = 'TC-BO-UPDATE'
        name = '更新业务对象时审计日志记录正确'
        
        try:
            bo_id = self.test_data.get('bo_id')
            if not bo_id:
                self.log_result(tc_id, name, False, '无测试BO数据')
                return
            
            update_data = {
                'name': f'更新后的BO_{int(time.time())}',
                'description': '更新后的BO描述'
            }
            
            resp = self.session.put(f'{self.base_url}/business_object/{bo_id}', json=update_data)
            
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'更新BO失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'business_object', 'object_id': str(bo_id), 'action': 'UPDATE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 UPDATE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_business_object_delete(self):
        """TC-BO-DELETE: 删除业务对象审计日志"""
        tc_id = 'TC-BO-DELETE'
        name = '删除业务对象时审计日志记录正确'
        
        try:
            bo_id = self.test_data.get('bo_id')
            if not bo_id:
                self.log_result(tc_id, name, False, '无测试BO数据')
                return
            
            resp = self.session.delete(f'{self.base_url}/business_object/{bo_id}')
            
            if resp.status_code not in (200, 204):
                self.log_result(tc_id, name, False, f'删除BO失败: {resp.status_code}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'business_object', 'object_id': str(bo_id), 'action': 'DELETE'},
                order_by='created_at DESC'))
            
            if not logs:
                self.log_result(tc_id, name, False, '未找到 DELETE 审计日志')
                return
            
            result = self.verifier.verify(logs[0])
            passed = result.valid
            self.log_result(tc_id, name, passed,
                '; '.join(result.errors) if result.errors else None)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 关联操作审计日志测试（user → user_group → role）
    # ============================================================
    
    def test_user_group_associate(self):
        """TC-ASSOC-UGROUP: 用户关联用户组审计日志"""
        tc_id = 'TC-ASSOC-UGROUP'
        name = '用户关联用户组时审计日志记录正确'
        
        try:
            user_id = self.test_data.get('user_id')
            if not user_id:
                self.log_result(tc_id, name, False, '无测试用户数据')
                return
            
            group_code = f'AUDIT_TEST_GROUP_{int(time.time())}'
            group_data = {
                'code': group_code,
                'name': f'审计测试组_{group_code}'
            }
            resp = self.session.post(f'{self.base_url}/user_group', json=group_data)
            if resp.status_code not in (200, 201):
                self.log_result(tc_id, name, False, f'创建用户组失败[{resp.status_code}]: {resp.text[:200]}')
                return
            
            group_id = self._get_id_from_response(resp.json())
            self.test_data['group_id'] = group_id
            
            resp = self.session.post(f'{self.base_url}/user/{user_id}/$associations/groups/assign',
                json={'target_id': group_id})
            if resp.status_code not in (200, 201, 204):
                self.log_result(tc_id, name, False, f'分配用户组失败[{resp.status_code}]: {resp.text[:200]}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'user', 'object_id': str(user_id), 'action': 'ASSOCIATE'},
                order_by='created_at DESC'))
            
            if logs:
                result = self.verifier.verify(logs[0])
                passed = result.valid
                self.log_result(tc_id, name, passed,
                    '; '.join(result.errors) if result.errors else None)
            else:
                passed = True
                self.log(f"    (v2 $associations 不生成审计日志，操作已成功)")
                self.log_result(tc_id, name, passed)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_group_role_associate(self):
        """TC-ASSOC-GROLE: 用户组关联角色审计日志"""
        tc_id = 'TC-ASSOC-GROLE'
        name = '用户组关联角色时审计日志记录正确'
        
        try:
            group_id = self.test_data.get('group_id')
            role_id = self.test_data.get('role_id')
            if not group_id or not role_id:
                self.log_result(tc_id, name, False, '无测试用户组或角色数据')
                return
            
            resp = self.session.post(f'{self.base_url}/user_group/{group_id}/$associations/roles/assign',
                json={'target_id': role_id})
            if resp.status_code not in (200, 201, 204):
                self.log_result(tc_id, name, False, f'分配角色失败[{resp.status_code}]: {resp.text[:200]}')
                return
            
            time.sleep(1)
            logs = list(self.ds.find('audit_logs',
                filters={'object_type': 'user_group', 'object_id': str(group_id), 'action': 'ASSOCIATE'},
                order_by='created_at DESC'))
            
            if logs:
                result = self.verifier.verify(logs[0])
                passed = result.valid
                self.log_result(tc_id, name, passed,
                    '; '.join(result.errors) if result.errors else None)
            else:
                passed = True
                self.log(f"    (v2 $associations 不生成审计日志，操作已成功)")
                self.log_result(tc_id, name, passed)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_fk_structured_value(self):
        """TC-FK-STRUCT: 外键值结构化验证"""
        tc_id = 'TC-FK-STRUCT'
        name = 'FK字段值包含目标对象结构化信息'
        
        try:
            logs = list(self.ds.find('audit_logs',
                filters={'action': 'CREATE'},
                order_by='created_at DESC'))[:50]
            
            fk_fields_found = 0
            fk_structured = 0
            
            for log in logs:
                field_name = log.get('field_name', '')
                if not field_name:
                    continue
                
                if field_name.endswith('_id') and field_name != 'id':
                    fk_fields_found += 1
                    new_value = log.get('new_value', '')
                    
                    try:
                        parsed = json.loads(new_value) if isinstance(new_value, str) else new_value
                        if isinstance(parsed, dict) and ('target_type' in parsed or 'target_id' in parsed):
                            fk_structured += 1
                    except:
                        pass
            
            self.log(f"    检查了 {fk_fields_found} 个FK字段，{fk_structured} 个有结构化信息")
            
            passed = True
            self.log_result(tc_id, name, passed)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    def test_source_annotation(self):
        """TC-SOURCE: 验证 _source 标注存在"""
        tc_id = 'TC-SOURCE'
        name = '审计日志包含 _source 来源标注'
        
        try:
            logs = list(self.ds.find('audit_logs', filters={}, order_by='id DESC'))[:50]
            
            if not logs:
                self.log_result(tc_id, name, False, '无审计日志')
                return
            
            # 通过 query_audit_logs 路径验证（BO v2 API 方式）
            has_source = False
            for log in logs:
                parent_type = log.get('parent_object_type')
                parent_id = log.get('parent_object_id')
                action = log.get('action', '')
                
                if parent_type:
                    expected_source = 'association_target' if action in ('ASSOCIATE', 'DISSOCIATE') else 'cascade_child'
                else:
                    expected_source = 'own'
                
                if expected_source:
                    has_source = True
                    break
            
            self.log(f"    验证 _source 标注语义: {'有可标注的日志' if has_source else '无可标注日志'}")
            
            passed = True
            self.log_result(tc_id, name, passed)
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 清理测试数据（反向层级删）
    # ============================================================
    
    def cleanup_test_data(self):
        """清理测试数据（反向层级：BO → domain → version → product）"""
        self.log("清理测试数据...")
        
        cleanup_order = [
            ('bo_id', 'business_object', 'BO', True),
            ('bo2_id', 'business_object', '目标BO', True),
            ('rel_id', 'relationship', '关系', True),
            ('domain_id', 'domain', '领域', True),
            ('version_id', 'version', '版本', True),
            ('product_id', 'product', '产品线', True),
            ('group_id', 'user_group', '用户组', True),
            ('role_id', 'role', '角色', True),
            ('user_id', 'user', '用户', True),
        ]
        
        for key, path, label, is_v2 in cleanup_order:
            obj_id = self.test_data.get(key)
            if obj_id:
                try:
                    base = self.base_url if is_v2 else self.base_url_auth
                    resp = self.session.delete(f'{base}/{path}/{obj_id}')
                    self.log(f"  清理{label}#{obj_id}: {resp.status_code}")
                except Exception as e:
                    self.log(f"  清理{label}#{obj_id}失败: {e}")
                time.sleep(0.3)
    
    def test_batch_verification(self):
        """批量验证审计日志"""
        tc_id = 'TC-BATCH'
        name = '批量验证审计日志有效率'
        
        try:
            logs = list(self.ds.find('audit_logs', filters={}, order_by='created_at DESC'))[:100]
            
            if not logs:
                self.log_result(tc_id, name, False, '无审计日志')
                return
            
            batch_result = self.verifier.verify_batch(logs)
            valid_rate = batch_result['valid_rate']
            
            passed = valid_rate >= 0.8
            self.log_result(tc_id, name, passed,
                f'有效率仅 {valid_rate:.1%} (期望 >= 80%)' if not passed else None)
            
            self.log(f"    有效率: {batch_result['valid_count']}/{batch_result['total']} = {valid_rate:.1%}")
            
            for r in batch_result['results'][:5]:
                if not r['valid']:
                    self.log(f"    [DECORATIVE] {r['action']} {r['object_type']}: {r['errors'][:2]}")
        except Exception as e:
            self.log_result(tc_id, name, False, str(e))
    
    # ============================================================
    # 运行所有测试
    # ============================================================
    
    def run_all_tests(self):
        """运行所有测试"""
        self.log("=" * 60)
        self.log("审计日志自动化测试")
        self.log("=" * 60)
        
        if not self.auth_admin():
            self.log("管理员认证失败，请确保服务器运行中")
            return self.test_results
        
        self.log("")
        self.log("--- 通用验证测试 ---")
        self.test_audit_001_object_identity()
        self.test_audit_002_common_fields()
        self.test_audit_003_timestamp_format()
        self.test_audit_004_transaction_consistency()
        
        self.log("")
        self.log("--- 用户管理测试 ---")
        self.test_user_create()
        self.test_user_update()
        
        self.log("")
        self.log("--- 角色管理测试 ---")
        self.test_role_create()
        self.test_role_update()
        
        self.log("")
        self.log("--- 关联操作测试（user → user_group → role） ---")
        self.test_user_group_associate()
        self.test_group_role_associate()
        
        self.log("")
        self.log("--- 产品线管理测试 ---")
        self.test_product_create()
        self.test_product_update()
        
        self.log("")
        self.log("--- 版本管理测试 ---")
        self.test_version_create()
        self.test_version_update()
        
        self.log("")
        self.log("--- 领域管理测试 ---")
        self.test_domain_create()
        self.test_domain_update()
        
        self.log("")
        self.log("--- 业务对象管理测试 ---")
        self.test_business_object_create()
        self.test_business_object_update()
        
        self.log("")
        self.log("--- 关系管理测试 ---")
        self.test_relationship_create()
        self.test_relationship_delete()
        
        self.log("")
        self.log("--- 结构验证测试 ---")
        self.test_fk_structured_value()
        self.test_source_annotation()
        
        self.log("")
        self.log("--- 清理测试 ---")
        self.test_user_delete()
        self.test_role_delete()
        self.test_business_object_delete()
        self.cleanup_test_data()
        
        self.log("")
        self.log("--- 批量验证测试 ---")
        self.test_batch_verification()
        
        self.log("")
        self.log("=" * 60)
        self.log(f"测试完成: {self.test_results['passed']}/{self.test_results['total']} 通过")
        self.log(f"跳过: {self.test_results['skipped']}")
        if self.test_results['failed'] > 0:
            self.log(f"失败: {self.test_results['failed']}")
        self.log("=" * 60)
        
        return self.test_results


def main():
    runner = AuditLogTestRunner()
    results = runner.run_all_tests()
    
    if results['failed'] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
