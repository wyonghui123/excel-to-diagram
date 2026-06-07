import yaml
import os
from typing import List


class StandardActionLoader:
    """标准动作加载器 — 独立于 BO Schema 加载链路

    从 _standard_actions.yaml 加载标准动作，不映射数据库表。
    提供 get_suffix_map() 供 MetaAction.get_permission_suffix() 使用，
    提供 get_action_codes() 供 PermissionService._validate_action_code() 使用。
    """

    _actions: List = []
    _suffix_map = {}
    _action_codes = set()
    _loaded = False

    @classmethod
    def _auto_load(cls):
        if cls._loaded:
            return
        schemas_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
        cls.load(schemas_dir)

    @classmethod
    def load(cls, schemas_dir: str):
        filepath = os.path.join(schemas_dir, '_standard_actions.yaml')
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"标准动作声明文件缺失: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        from meta.core.models import MetaAction, ActionType

        cls._actions = []
        for item in data.get('standard_actions', []):
            cls._actions.append(MetaAction(
                id=item['id'],
                name=item['name'],
                action_type=ActionType(item.get('action_type', 'crud')),
                method=item.get('method', 'POST'),
                path='',
                description=item.get('description', ''),
            ))

        cls._suffix_map = {}
        for a in cls._actions:
            suffix = a.id.replace('crud_', '')
            cls._suffix_map[a.id] = suffix
        cls._action_codes = set(cls._suffix_map.values())
        cls._loaded = True

        return cls._actions

    @classmethod
    def get_actions(cls):
        cls._auto_load()
        return cls._actions

    @classmethod
    def get_suffix_map(cls):
        cls._auto_load()
        return cls._suffix_map

    @classmethod
    def get_action_codes(cls):
        cls._auto_load()
        return cls._action_codes
