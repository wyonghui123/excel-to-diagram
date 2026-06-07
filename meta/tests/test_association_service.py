import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
AssociationService 测试

测试元模型驱动的关联操作功能：
- assign: 创建关联
- unassign: 删除关联
- list_members: 查询成员
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.yaml_loader import parse_associations, parse_association, AssociationDefinition, AssociationActionDef


def test_parse_associations_empty():
    """测试空 associations 解析"""
    print("\n=== 测试 parse_associations 空配置 ===")
    
    data = {}
    associations = parse_associations(data)
    assert associations == {}
    print("[OK] 空配置返回空字典")


def test_parse_associations_basic():
    """测试基本 associations 解析"""
    print("\n=== 测试 parse_associations 基本配置 ===")
    
    data = {
        "associations": {
            "users": {
                "type": "many_to_many",
                "through": "user_roles",
                "source_key": "role_id",
                "target_entity": "user",
                "target_key": "user_id"
            }
        }
    }
    associations = parse_associations(data)
    
    assert "users" in associations
    users_assoc = associations["users"]
    assert users_assoc.type == "many_to_many"
    assert users_assoc.through == "user_roles"
    assert users_assoc.source_key == "role_id"
    assert users_assoc.target_entity == "user"
    assert users_assoc.target_key == "user_id"
    print(f"[OK] users 关联解析成功: {users_assoc.type}")


def test_parse_associations_with_actions():
    """测试带 actions 的 associations"""
    print("\n=== 测试 parse_associations 带 actions ===")
    
    data = {
        "associations": {
            "users": {
                "type": "many_to_many",
                "through": "user_roles",
                "source_key": "role_id",
                "target_entity": "user",
                "target_key": "user_id",
                "actions": {
                    "assign": {
                        "name": "assign_user",
                        "label": "分配用户"
                    },
                    "unassign": {
                        "name": "unassign_user",
                        "label": "取消分配"
                    },
                    "list": {
                        "name": "list_users",
                        "label": "成员列表",
                        "readonly": True
                    }
                }
            }
        }
    }
    associations = parse_associations(data)
    
    assert "users" in associations
    users_assoc = associations["users"]
    
    assert "assign" in users_assoc.actions
    assert users_assoc.actions["assign"].name == "assign_user"
    assert users_assoc.actions["assign"].label == "分配用户"
    
    assert "unassign" in users_assoc.actions
    assert users_assoc.actions["unassign"].name == "unassign_user"
    
    assert "list" in users_assoc.actions
    assert users_assoc.actions["list"].readonly == True
    
    print(f"[OK] actions 解析成功: {list(users_assoc.actions.keys())}")


def test_parse_association_one_to_many():
    """测试一对多关联"""
    print("\n=== 测试 parse_association 一对多 ===")
    
    data = {
        "name": "children",
        "type": "one_to_many",
        "source_key": "parent_id",
        "target_entity": "child",
        "target_key": "id"
    }
    assoc = parse_association(data)
    
    assert assoc.name == "children"
    assert assoc.type == "one_to_many"
    assert assoc.through is None
    assert assoc.source_key == "parent_id"
    assert assoc.target_entity == "child"
    print(f"[OK] 一对多关联解析成功")


def test_parse_association_many_to_one():
    """测试多对一关联"""
    print("\n=== 测试 parse_association 多对一 ===")
    
    data = {
        "name": "parent",
        "type": "many_to_one",
        "source_key": "id",
        "target_entity": "parent",
        "target_key": "parent_id"
    }
    assoc = parse_association(data)
    
    assert assoc.name == "parent"
    assert assoc.type == "many_to_one"
    print(f"[OK] 多对一关联解析成功")


def test_parse_associations_multiple():
    """测试多个关联"""
    print("\n=== 测试 parse_associations 多个关联 ===")
    
    data = {
        "associations": {
            "users": {
                "type": "many_to_many",
                "through": "user_roles",
                "source_key": "role_id",
                "target_entity": "user",
                "target_key": "user_id"
            },
            "permissions": {
                "type": "many_to_many",
                "through": "role_permissions",
                "source_key": "role_id",
                "target_entity": "permission",
                "target_key": "permission_id"
            }
        }
    }
    associations = parse_associations(data)
    
    assert len(associations) == 2
    assert "users" in associations
    assert "permissions" in associations
    
    print(f"[OK] 解析了 {len(associations)} 个关联: {list(associations.keys())}")


def test_parse_association_empty_actions():
    """测试空 actions"""
    print("\n=== 测试 parse_association 空 actions ===")
    
    data = {
        "name": "items",
        "type": "many_to_many",
        "through": "order_items",
        "source_key": "order_id",
        "target_entity": "item",
        "target_key": "item_id",
        "actions": {}
    }
    assoc = parse_association(data)
    
    assert assoc.actions == {}
    print("[OK] 空 actions 解析正确")


def test_parse_association_with_handler():
    """测试带 handler 的 action"""
    print("\n=== 测试 parse_association 带 handler ===")
    
    data = {
        "name": "users",
        "type": "many_to_many",
        "through": "user_roles",
        "source_key": "role_id",
        "target_entity": "user",
        "target_key": "user_id",
        "actions": {
            "assign": {
                "name": "assign_user",
                "label": "分配用户",
                "handler": "role_service.assign_user",
                "params": ["user_id", "role_id"]
            }
        }
    }
    assoc = parse_association(data)
    
    assign_action = assoc.actions["assign"]
    assert assign_action.handler == "role_service.assign_user"
    assert assign_action.params == ["user_id", "role_id"]
    print(f"[OK] handler: {assign_action.handler}, params: {assign_action.params}")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("AssociationService YAML 解析测试")
    print("=" * 60)
    
    test_parse_associations_empty()
    test_parse_associations_basic()
    test_parse_associations_with_actions()
    test_parse_association_one_to_many()
    test_parse_association_many_to_one()
    test_parse_association_default_type()
    test_parse_associations_multiple()
    test_parse_association_empty_actions()
    test_parse_association_with_handler()
    
    print("\n" + "=" * 60)
    print("[OK] 所有 AssociationService YAML 解析测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
