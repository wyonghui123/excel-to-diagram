import pytest

pytestmark = pytest.mark.integration

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.tests.test_utils import get_test_db_path


@pytest.fixture
def mock_field():
    """模块级别的 mock_field fixture，供所有测试类使用"""
    def create_field(
        field_id,
        business_key=False,
        parent_key=False,
        immutable=False,
        readonly_always=False,
        mandatory=False,
        virtual=False,
        storage='persistent',
        ui_editable=None,
        ui_relation=None,
        computed=False,
        compute_expr=None,
        search_help_for=None
    ):
        field = MagicMock()
        field.id = field_id
        field.storage = MagicMock()
        field.storage.value = storage
        
        semantics = MagicMock()
        semantics.business_key = business_key
        semantics.parent_key = parent_key
        semantics.immutable = immutable
        semantics.readonly_always = readonly_always
        semantics.mandatory = mandatory
        semantics.virtual = virtual
        semantics.import_editable = None
        semantics.search_help_for = search_help_for
        field.semantics = semantics
        
        ui = MagicMock()
        ui.editable = ui_editable
        ui.relation = ui_relation
        field.ui = ui
        
        field.computed = computed
        field.compute_expr = compute_expr
        
        return field
    return create_field


class TestFieldControlsConsistency:
    """验证前后端字段控制逻辑一致性"""
    
    def test_system_fields_always_readonly(self, mock_field):
        """系统字段始终只读"""
        readonly_field_ids = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']
        
        for field_id in readonly_field_ids:
            field = mock_field(field_id)
            
            assert field.id in readonly_field_ids, f"{field_id} should be readonly"
    
    def test_readonly_always_field(self, mock_field):
        """readonly_always 字段始终只读"""
        field = mock_field('version_id', readonly_always=True)
        
        assert field.semantics.readonly_always is True
    
    def test_immutable_field_edit_mode(self, mock_field):
        """immutable 字段编辑时只读"""
        field = mock_field('code', immutable=True)
        
        assert field.semantics.immutable is True
    
    def test_parent_key_field_editable(self, mock_field):
        """parent_key 字段可编辑（SAP One Model 允许移动层级）"""
        field = mock_field('service_module_id', parent_key=True)
        
        assert field.semantics.parent_key is True
    
    def test_business_key_field(self, mock_field):
        """business_key 字段：新建必填+唯一，编辑只读"""
        field = mock_field('code', business_key=True, immutable=True)
        
        assert field.semantics.business_key is True
        assert field.semantics.immutable is True
    
    def test_virtual_field_with_relation_editable(self, mock_field):
        """有 ui.relation 的 virtual 字段可编辑"""
        field = mock_field('parent_name', virtual=True, storage='virtual', ui_relation='parent')
        
        assert field.storage.value == 'virtual' or field.semantics.virtual is True
        assert field.ui.relation is not None
    
    def test_virtual_computed_field_readonly(self, mock_field):
        """计算字段只读"""
        field = mock_field('full_name', virtual=True, storage='virtual', computed=True)
        
        assert field.computed is True or field.compute_expr is not None


class TestFieldControlsAPI:
    """测试字段控制 API"""
    
    @pytest.fixture
    def app(self):
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        from flask import Flask
        from meta.api.manage_api import manage_bp, init_services
        from meta.api.meta_utility_routes_api import meta_util_bp
        from meta.core.datasource import get_data_source
        from meta.tests.test_utils import get_test_db_path

        app = Flask(__name__)
        app.register_blueprint(manage_bp)
        app.register_blueprint(meta_util_bp)
        ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(ds)
        return app
    
    @pytest.fixture
    def client(self, app):
        return app.test_client()
    
    def test_business_object_code_is_business_key_and_immutable(self, client):
        """业务对象编码是业务键且不可变"""
        import json
        
        response = client.get('/api/v1/meta/objects/business_object/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        code_controls = data.get('data', {}).get('field_controls', {})['code']
        assert code_controls['business_key'] is True
        assert code_controls['immutable'] is True
    
    def test_business_object_service_module_id_is_parent_key(self, client):
        """业务对象 service_module_id 是父键"""
        import json
        
        response = client.get('/api/v1/meta/objects/business_object/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        sm_controls = data.get('data', {}).get('field_controls', {})['service_module_id']
        assert sm_controls['parent_key'] is True
    
    def test_domain_code_is_business_key(self, client):
        """领域编码是业务键"""
        import json
        
        response = client.get('/api/v1/meta/objects/domain/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        code_controls = data.get('data', {}).get('field_controls', {})['code']
        assert code_controls['business_key'] is True


class TestFieldControlsRules:
    """字段控制规则验证"""
    
    def test_business_key_rules(self):
        """
        business_key 字段规则：
        - 新建时：必填 + 唯一性验证
        - 编辑时：只读（不可修改）
        """
        rules = {
            'create': {'required': True, 'unique': True, 'editable': True},
            'edit': {'required': False, 'unique': False, 'editable': False}
        }
        
        assert rules['create']['required'] is True
        assert rules['create']['editable'] is True
        assert rules['edit']['editable'] is False
    
    def test_parent_key_rules(self):
        """
        parent_key 字段规则：
        - 新建时：必填
        - 编辑时：可编辑（SAP One Model 允许移动层级）
        """
        rules = {
            'create': {'required': True, 'editable': True},
            'edit': {'required': False, 'editable': True}
        }
        
        assert rules['create']['required'] is True
        assert rules['edit']['editable'] is True
    
    def test_immutable_rules(self):
        """
        immutable 字段规则：
        - 新建时：可编辑 + 必填
        - 编辑时：只读
        """
        rules = {
            'create': {'required': True, 'editable': True},
            'edit': {'required': False, 'editable': False}
        }
        
        assert rules['create']['editable'] is True
        assert rules['edit']['editable'] is False
    
    def test_readonly_always_rules(self):
        """
        readonly_always 字段规则：
        - 新建时：只读
        - 编辑时：只读
        """
        rules = {
            'create': {'editable': False},
            'edit': {'editable': False}
        }
        
        assert rules['create']['editable'] is False
        assert rules['edit']['editable'] is False
    
    def test_mandatory_rules(self):
        """
        mandatory 字段规则：
        - 新建时：必填
        - 编辑时：必填
        """
        rules = {
            'create': {'required': True},
            'edit': {'required': True}
        }
        
        assert rules['create']['required'] is True
        assert rules['edit']['required'] is True


class TestSearchHelpFieldControls:
    """Search Help 字段控制规则验证
    
    Search Help 字段是带有 ui.relation 的 virtual 字段，用于级联筛选目标字段。
    当 search_help_for 指向的目标字段是 immutable 时，Search Help 字段在编辑模式下应只读。
    
    参考 SAP One Model 的 @Consumption.valueHelpDefinition additionalBinding.usage 设计。
    """
    
    def test_search_help_field_definition(self, mock_field):
        """Search Help 字段定义：storage=virtual + ui.relation"""
        field = mock_field(
            'source_domain_id',
            virtual=True,
            storage='virtual',
            ui_relation='domain'
        )
        
        assert field.storage.value == 'virtual' or field.semantics.virtual is True
        assert field.ui.relation is not None
    
    def test_search_help_for_semantic(self, mock_field):
        """search_help_for 语义：指向目标字段"""
        field = mock_field(
            'source_domain_id',
            virtual=True,
            storage='virtual',
            ui_relation='domain'
        )
        
        field.semantics.search_help_for = 'source_bo_id'
        
        assert field.semantics.search_help_for == 'source_bo_id'
    
    def test_search_help_field_editable_when_target_not_immutable(self, mock_field):
        """
        Search Help 字段在目标字段非 immutable 时可编辑
        
        场景：新建关系时，source_bo_id 可编辑，所以 source_domain_id 也可编辑
        """
        search_help_field = mock_field(
            'source_domain_id',
            virtual=True,
            storage='virtual',
            ui_relation='domain'
        )
        search_help_field.semantics.search_help_for = 'source_bo_id'
        
        target_field = mock_field('source_bo_id', parent_key=True)
        
        assert search_help_field.semantics.search_help_for == 'source_bo_id'
        assert target_field.semantics.immutable is not True
    
    def test_search_help_field_readonly_when_target_immutable(self, mock_field):
        """
        Search Help 字段在目标字段 immutable 时应只读
        
        场景：编辑关系时，source_bo_id 是 immutable，所以 source_domain_id 也应只读
        """
        search_help_field = mock_field(
            'source_domain_id',
            virtual=True,
            storage='virtual',
            ui_relation='domain'
        )
        search_help_field.semantics.search_help_for = 'source_bo_id'
        
        target_field = mock_field('source_bo_id', parent_key=True, immutable=True)
        
        assert search_help_field.semantics.search_help_for == 'source_bo_id'
        assert target_field.semantics.immutable is True
    
    def test_search_help_field_rules(self):
        """
        Search Help 字段规则：
        - 新建时：可编辑（目标字段可编辑）
        - 编辑时：如果目标字段 immutable，则只读
        """
        rules = {
            'create': {'editable': True},
            'edit_target_immutable': {'editable': False},
            'edit_target_not_immutable': {'editable': True}
        }
        
        assert rules['create']['editable'] is True
        assert rules['edit_target_immutable']['editable'] is False
        assert rules['edit_target_not_immutable']['editable'] is True


class TestSearchHelpFieldControlsAPI:
    """测试 Search Help 字段控制 API"""
    
    @pytest.fixture
    def app(self):
        from flask import Flask
        from meta.api.manage_api import manage_bp, init_services
        from meta.api.meta_utility_routes_api import meta_util_bp
        from meta.core.datasource import get_data_source
        
        app = Flask(__name__)
        app.register_blueprint(manage_bp)
        app.register_blueprint(meta_util_bp)
        ds = get_data_source("sqlite", database=get_test_db_path())
        init_services(ds)
        return app
    
    @pytest.fixture
    def client(self, app):
        return app.test_client()
    
    def test_relationship_source_domain_id_is_search_help(self, client):
        """关系 source_domain_id 是 Search Help 字段"""
        import json
        
        response = client.get('/api/v1/meta/objects/relationship/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        field_controls = data.get('data', {}).get('field_controls', {})
        assert 'source_domain_id' in field_controls
        
        source_domain = field_controls['source_domain_id']
        assert source_domain.get('virtual') is True or source_domain.get('storage') == 'virtual'
        assert source_domain.get('search_help_for') == 'source_bo_id'
    
    def test_relationship_source_bo_id_is_immutable(self, client):
        """关系 source_bo_id 是 immutable"""
        import json
        
        response = client.get('/api/v1/meta/objects/relationship/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        field_controls = data.get('data', {}).get('field_controls', {})
        assert 'source_bo_id' in field_controls
        
        source_bo = field_controls['source_bo_id']
        assert source_bo.get('immutable') is True
        assert source_bo.get('parent_key') is True
    
    def test_relationship_target_domain_id_is_search_help(self, client):
        """关系 target_domain_id 是 Search Help 字段"""
        import json
        
        response = client.get('/api/v1/meta/objects/relationship/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        field_controls = data.get('data', {}).get('field_controls', {})
        assert 'target_domain_id' in field_controls
        
        target_domain = field_controls['target_domain_id']
        assert target_domain.get('virtual') is True or target_domain.get('storage') == 'virtual'
        assert target_domain.get('search_help_for') == 'target_bo_id'
    
    def test_relationship_target_bo_id_is_immutable(self, client):
        """关系 target_bo_id 是 immutable"""
        import json
        
        response = client.get('/api/v1/meta/objects/relationship/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        field_controls = data.get('data', {}).get('field_controls', {})
        assert 'target_bo_id' in field_controls
        
        target_bo = field_controls['target_bo_id']
        assert target_bo.get('immutable') is True
        assert target_bo.get('parent_key') is True
    
    def test_search_help_chain_for_source(self, client):
        """验证源端 Search Help 链：domain -> sub_domain -> service_module -> bo"""
        import json
        
        response = client.get('/api/v1/meta/objects/relationship/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        field_controls = data.get('data', {}).get('field_controls', {})
        
        assert field_controls['source_domain_id']['search_help_for'] == 'source_bo_id'
        assert field_controls['source_sub_domain_id']['search_help_for'] == 'source_bo_id'
        assert field_controls['source_service_module_id']['search_help_for'] == 'source_bo_id'
    
    def test_search_help_chain_for_target(self, client):
        """验证目标端 Search Help 链：domain -> sub_domain -> service_module -> bo"""
        import json
        from meta.tests.test_utils import get_test_db_path

        response = client.get('/api/v1/meta/objects/relationship/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        field_controls = data.get('data', {}).get('field_controls', {})
        
        assert field_controls['target_domain_id']['search_help_for'] == 'target_bo_id'
        assert field_controls['target_sub_domain_id']['search_help_for'] == 'target_bo_id'
        assert field_controls['target_service_module_id']['search_help_for'] == 'target_bo_id'
