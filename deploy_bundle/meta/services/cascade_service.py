from enum import Enum
from typing import Dict, List, Any, Optional
from pathlib import Path
import yaml

from meta.core.datasource import DataSource
from meta.core.models import MetaObject, registry, RelationType


class CascadeStrategy(Enum):
    RESTRICT = "restrict"
    CASCADE = "cascade"
    SET_NULL = "set_null"
    SET_DEFAULT = "set_default"


class HierarchyConfigLoader:
    _instance = None
    _config = None

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        if cls._config is None:
            config_path = Path(__file__).parent.parent / 'schemas' / 'hierarchies.yaml'
            with open(config_path, 'r', encoding='utf-8') as f:
                cls._config = yaml.safe_load(f)
        return cls._config

    @classmethod
    def get_hierarchy(cls, hierarchy_id: str = 'biz_hierarchy') -> Optional[Dict]:
        config = cls.get_config()
        for h in config.get('hierarchies', []):
            if h.get('id') == hierarchy_id:
                return h
        return None

    @classmethod
    def get_levels(cls, hierarchy_id: str = 'biz_hierarchy') -> List[Dict]:
        hierarchy = cls.get_hierarchy(hierarchy_id)
        return hierarchy.get('levels', []) if hierarchy else []

    @classmethod
    def get_level_by_object(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> Optional[Dict]:
        levels = cls.get_levels(hierarchy_id)
        for level in levels:
            if level.get('object') == object_type:
                return level
        return None

    @classmethod
    def get_delete_behavior(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> Dict:
        level = cls.get_level_by_object(object_type, hierarchy_id)
        if level:
            return level.get('delete_behavior', {'policy': 'RESTRICT'})
        return {'policy': 'RESTRICT'}

    @classmethod
    def get_parent_object(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> Optional[str]:
        level = cls.get_level_by_object(object_type, hierarchy_id)
        if level and level.get('parent_object'):
            return level.get('parent_object')
        return cls.get_parent_object_from_associations(object_type)

    @classmethod
    def get_foreign_key(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> Optional[str]:
        level = cls.get_level_by_object(object_type, hierarchy_id)
        if level and level.get('foreign_key_field'):
            return level.get('foreign_key_field')
        return cls.get_foreign_key_from_associations(object_type)

    @classmethod
    def get_child_types(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> List[str]:
        levels = cls.get_levels(hierarchy_id)
        children = []
        for level in levels:
            if level.get('parent_object') == object_type:
                children.append(level.get('object'))
        if not children:
            children = cls.get_child_types_from_associations(object_type)
        return children

    @classmethod
    def get_cascade_strategy(cls, parent_type: str, child_type: str) -> CascadeStrategy:
        child_level = cls.get_level_by_object(child_type)
        if child_level:
            delete_behavior = child_level.get('delete_behavior', {})
            policy = delete_behavior.get('policy', 'RESTRICT').upper()
            try:
                return CascadeStrategy[policy]
            except KeyError:
                return CascadeStrategy.RESTRICT
        return cls.get_cascade_strategy_from_associations(parent_type, child_type)

    @classmethod
    def get_table_name(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> Optional[str]:
        """从层级配置获取表名（比 registry 更可靠，不依赖 schema 加载顺序）"""
        level = cls.get_level_by_object(object_type, hierarchy_id)
        if level and level.get('table_name'):
            return level.get('table_name')
        return None

    @classmethod
    def get_type_order(cls) -> List[str]:
        levels = cls.get_levels('biz_hierarchy')
        return [level.get('object') for level in levels if level.get('object')]

    @classmethod
    def sort_by_hierarchy(cls, object_types: List[str]) -> List[str]:
        """[FR-008] 按层级拓扑排序（父对象在前，子对象在后）

        替代 get_type_order()，支持任意类型子集排序 + child_sections 依赖。
        统一 import_export_service 中 4 个导出/导入入口的排序逻辑。

        排序规则：
        1. parent_object 关系：子对象依赖父对象（如 sub_domain → domain）
        2. child_sections 关系：子对象依赖其所有父对象
        """
        from meta.core.models import registry

        graph = {ot: [] for ot in object_types}

        for ot in object_types:
            obj = registry.get(ot)
            if obj and obj.parent_object and obj.parent_object in object_types:
                graph[ot] = [obj.parent_object]

        # child_sections 依赖
        for ot in object_types:
            obj = registry.get(ot)
            if obj and hasattr(obj, 'child_sections') and obj.child_sections:
                for section in obj.child_sections:
                    section_type = getattr(section, 'object_type', None)
                    if section_type and section_type in object_types and section_type != ot:
                        if ot not in graph[section_type]:
                            graph[section_type].append(ot)

        result = []
        visited = set()

        def visit(node):
            if node in visited:
                return
            visited.add(node)
            for parent in graph.get(node, []):
                visit(parent)
            result.append(node)

        for ot in object_types:
            visit(ot)

        return result

    @classmethod
    def get_dimensions(cls) -> List[Dict[str, Any]]:
        config = cls.get_config()
        return config.get('dimensions', [])

    @classmethod
    def get_dimension(cls, dimension_id: str) -> Dict[str, Any]:
        for d in cls.get_dimensions():
            if d.get('id') == dimension_id:
                return d
        return {}

    @classmethod
    def get_api_mappings(cls) -> Dict[str, Any]:
        config = cls.get_config()
        return config.get('api_mappings', {})

    @classmethod
    def get_parent_object(cls, object_type: str) -> Optional[str]:
        level = cls.get_level_by_object(object_type)
        return level.get('parent_object') if level else None

    @classmethod
    def build_child_chain(cls, from_type: str, to_type: str) -> List[str]:
        levels = cls.get_levels()
        parent_to_children = {}
        for level in levels:
            parent = level.get('parent_object')
            child = level.get('object')
            if parent and parent != 'version':
                if parent not in parent_to_children:
                    parent_to_children[parent] = []
                parent_to_children[parent].append((level.get('level', 0), child))

        for parent in parent_to_children:
            parent_to_children[parent].sort(key=lambda x: x[0])
            parent_to_children[parent] = [c[1] for c in parent_to_children[parent]]

        chain = [from_type]
        current = from_type

        while current != to_type:
            children = parent_to_children.get(current, [])
            if not children:
                break
            next_child = None
            for child in children:
                chain.append(child)
                if child == to_type:
                    return chain
                next_child = child
                break
            if not next_child:
                break
            current = next_child

        return chain if current == to_type else []

    @classmethod
    def build_hierarchy_chain(cls, from_type: str, to_type: str) -> List[str]:
        levels = cls.get_levels()
        object_to_level = {l.get('object'): l for l in levels}
        chain = [from_type]
        current = from_type

        while current != to_type:
            level = object_to_level.get(current, {})
            parent = level.get('parent_object')
            if not parent or parent == 'version':
                break
            chain.append(parent)
            current = parent

        return chain if current == to_type else []

    @classmethod
    def _get_entity_associations(cls, object_type: str):
        """从 Registry 获取实体的 associations
        
        向后兼容：优先从 hierarchies.yaml 获取，不存在时从 Registry 推导
        """
        from meta.core.models import registry
        
        entity = registry.get(object_type)
        if entity and hasattr(entity, 'associations') and entity.associations:
            return entity.associations
        return None

    @classmethod
    def get_parent_object_from_associations(cls, object_type: str) -> Optional[str]:
        """从 Association 配置推导 parent_object
        
        规则：
        1. 查找 cardinality='many_to_one' 且 type='composition' 的 Association
        2. 其 target_entity 即为 parent_object
        """
        associations = cls._get_entity_associations(object_type)
        if not associations:
            return None
        
        for assoc_name, assoc in associations.items():
            if (hasattr(assoc, 'cardinality') and assoc.cardinality == 'many_to_one' and
                hasattr(assoc, 'type') and assoc.type == 'composition'):
                if hasattr(assoc, 'target_entity') and assoc.target_entity:
                    return assoc.target_entity
        
        return None

    @classmethod
    def get_foreign_key_from_associations(cls, object_type: str) -> Optional[str]:
        """从 Association 配置推导 foreign_key_field
        
        规则：
        1. 查找 cardinality='many_to_one' 且 type='composition' 的 Association
        2. 优先使用显式配置的 foreign_key_field
        3. 否则自动推导：target_entity + "_id"
        """
        associations = cls._get_entity_associations(object_type)
        if not associations:
            return None
        
        for assoc_name, assoc in associations.items():
            if (hasattr(assoc, 'cardinality') and assoc.cardinality == 'many_to_one' and
                hasattr(assoc, 'type') and assoc.type == 'composition'):
                if hasattr(assoc, 'foreign_key_field') and assoc.foreign_key_field:
                    return assoc.foreign_key_field
                if hasattr(assoc, 'target_entity') and assoc.target_entity:
                    return f"{assoc.target_entity}_id"
        
        return None

    @classmethod
    def get_child_types_from_associations(cls, object_type: str) -> List[str]:
        """从 Association 配置推导所有子对象类型
        
        规则：
        查找 cardinality='one_to_many' 且 type='composition' 的 Association
        """
        associations = cls._get_entity_associations(object_type)
        if not associations:
            return []
        
        children = []
        for assoc_name, assoc in associations.items():
            if (hasattr(assoc, 'cardinality') and assoc.cardinality == 'one_to_many' and
                hasattr(assoc, 'type') and assoc.type == 'composition'):
                if hasattr(assoc, 'target_entity') and assoc.target_entity:
                    children.append(assoc.target_entity)
        
        return children

    @classmethod
    def get_cascade_strategy_from_associations(cls, parent_type: str, child_type: str) -> CascadeStrategy:
        """从 Association 配置推导级联策略
        
        规则：
        1. 查找 child_type 对应的 Association
        2. type='composition' 且 cascade_delete=True 时返回 CASCADE
        """
        associations = cls._get_entity_associations(child_type)
        if not associations:
            return CascadeStrategy.RESTRICT
        
        for assoc_name, assoc in associations.items():
            if (hasattr(assoc, 'target_entity') and assoc.target_entity == parent_type and
                hasattr(assoc, 'type') and assoc.type == 'composition'):
                if hasattr(assoc, 'cascade_delete') and assoc.cascade_delete:
                    return CascadeStrategy.CASCADE
                return CascadeStrategy.RESTRICT
        
        return CascadeStrategy.RESTRICT

    @classmethod
    def get_hierarchy_scopes(cls, hierarchy_id: str = 'biz_hierarchy') -> List[Dict]:
        config = cls.get_config()
        return config.get('hierarchy_scopes', [])

    @classmethod
    def compute_scope(cls, relation: Dict[str, Any], hierarchy_id: str = 'biz_hierarchy') -> tuple:
        scopes = cls.get_hierarchy_scopes(hierarchy_id)
        for scope in scopes:
            rule = scope.get('rule', '')
            if cls._evaluate_scope_rule(rule, relation):
                return (scope.get('name', ''), scope.get('id', ''), scope.get('color', ''))
        return ('', '', '')

    @classmethod
    def _evaluate_scope_rule(cls, rule: str, relation: Dict[str, Any]) -> bool:
        source_domain = relation.get('source_domain_id')
        target_domain = relation.get('target_domain_id')
        source_sd = relation.get('source_sub_domain_id')
        target_sd = relation.get('target_sub_domain_id')
        source_sm = relation.get('source_service_module_id')
        target_sm = relation.get('target_service_module_id')

        if 'source.domain_id != target.domain_id' in rule:
            return source_domain and target_domain and source_domain != target_domain
        elif 'source.sub_domain_id != target.sub_domain_id' in rule:
            return (source_domain and target_domain and source_domain == target_domain
                    and source_sd and target_sd and source_sd != target_sd)
        elif 'source.service_module_id != target.service_module_id' in rule:
            return (source_sd and target_sd and source_sd == target_sd
                    and source_sm and target_sm and source_sm != target_sm)
        elif 'source.service_module_id == target.service_module_id' in rule:
            return source_sm and target_sm and source_sm == target_sm
        return False

    @classmethod
    def clear_cache(cls):
        cls._config = None

    @classmethod
    def reload(cls):
        cls.clear_cache()
        return cls.get_config()


class CascadeService:

    def __init__(self, datasource: DataSource):
        self.ds = datasource
        self.config_loader = HierarchyConfigLoader

    def _get_composition_cascade_strategy(self, parent_type: str, child_type: str) -> Optional[CascadeStrategy]:
        parent_meta = registry.get(parent_type)
        if not parent_meta:
            return None
        for relation in parent_meta.relations:
            if relation.relation_type == RelationType.COMPOSITION and relation.target_object == child_type:
                if relation.cascade_delete:
                    return CascadeStrategy.CASCADE
                else:
                    return CascadeStrategy.RESTRICT
        return None

    def get_cascade_strategy(self, parent_type: str, child_type: str) -> CascadeStrategy:
        composition_strategy = self._get_composition_cascade_strategy(parent_type, child_type)
        if composition_strategy is not None:
            return composition_strategy
        return self.config_loader.get_cascade_strategy(parent_type, child_type)

    def _get_foreign_key(self, parent_type: str, child_type: str) -> str:
        fk = self.config_loader.get_foreign_key(child_type)
        return fk if fk else f"{parent_type}_id"

    def _get_child_types(self, object_type: str) -> List[str]:
        return self.config_loader.get_child_types(object_type)

    def _get_composition_child_types(self, object_type: str) -> List[str]:
        parent_meta = registry.get(object_type)
        if not parent_meta:
            return []
        return [r.target_object for r in parent_meta.relations if r.relation_type == RelationType.COMPOSITION]

    def _get_all_child_types(self, object_type: str) -> List[str]:
        hierarchy_children = self._get_child_types(object_type)
        composition_children = self._get_composition_child_types(object_type)
        seen = set()
        result = []
        for ct in hierarchy_children + composition_children:
            if ct not in seen:
                seen.add(ct)
                result.append(ct)
        return result

    def _get_composition_fk(self, parent_type: str, child_type: str) -> Optional[str]:
        parent_meta = registry.get(parent_type)
        if not parent_meta:
            return None
        for relation in parent_meta.relations:
            if relation.relation_type == RelationType.COMPOSITION and relation.target_object == child_type:
                return relation.source_field or f"{parent_type}_id"
        return None

    def _find_child_records(self, child_type: str, fk_field: str, parent_id: Any) -> List[Dict[str, Any]]:
        child_meta = registry.get(child_type)
        if not child_meta:
            return []
        table = child_meta.table_name
        results = self.ds.find(table, {fk_field: parent_id})
        return results if results else []

    def _find_relationships_by_bo(self, business_object_id: Any) -> List[Dict[str, Any]]:
        rel_meta = registry.get("relationship")
        if not rel_meta:
            return []
        table = rel_meta.table_name
        sql = f"SELECT DISTINCT * FROM {table} WHERE source_bo_id = ? OR target_bo_id = ?"
        cursor = self.ds.execute(sql, (business_object_id, business_object_id))
        rows = cursor.fetchall()
        if rows:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        return []

    def _collect_affected(self, object_type: str, object_id: Any, visited: set = None) -> Dict[str, Dict]:
        if visited is None:
            visited = set()
        key = (object_type, object_id)
        if key in visited:
            return {}
        visited.add(key)

        affected = {}
        child_types = self._get_child_types(object_type)

        for child_type in child_types:
            if child_type == "relationship" and object_type == "business_object":
                child_records = self._find_relationships_by_bo(object_id)
            else:
                fk = self._get_foreign_key(object_type, child_type)
                child_records = self._find_child_records(child_type, fk, object_id)

            if not child_records:
                continue

            strategy = self.get_cascade_strategy(object_type, child_type)
            child_ids = [r["id"] for r in child_records]

            affected[child_type] = {
                "count": len(child_ids),
                "ids": child_ids,
                "strategy": strategy.value,
            }

            if strategy == CascadeStrategy.CASCADE:
                for cid in child_ids:
                    nested = self._collect_affected(child_type, cid, visited)
                    for nested_type, nested_info in nested.items():
                        if nested_type in affected:
                            existing = affected[nested_type]
                            merged_ids = list(set(existing["ids"] + nested_info["ids"]))
                            affected[nested_type] = {
                                "count": len(merged_ids),
                                "ids": merged_ids,
                                "strategy": nested_info["strategy"],
                            }
                        else:
                            affected[nested_type] = nested_info

        parent_meta = registry.get(object_type)
        if parent_meta:
            for relation in parent_meta.relations:
                if relation.relation_type == RelationType.COMPOSITION:
                    comp_child_type = relation.target_object
                    fk_field = relation.source_field or f"{object_type}_id"
                    child_records = self._find_child_records(comp_child_type, fk_field, object_id)
                    if not child_records:
                        continue
                    strategy = self.get_cascade_strategy(object_type, comp_child_type)
                    child_ids = [r["id"] for r in child_records]
                    if comp_child_type in affected:
                        existing = affected[comp_child_type]
                        merged_ids = list(set(existing["ids"] + child_ids))
                        affected[comp_child_type] = {
                            "count": len(merged_ids),
                            "ids": merged_ids,
                            "strategy": strategy.value,
                        }
                    else:
                        affected[comp_child_type] = {
                            "count": len(child_ids),
                            "ids": child_ids,
                            "strategy": strategy.value,
                        }
                    if strategy == CascadeStrategy.CASCADE:
                        for cid in child_ids:
                            nested = self._collect_affected(comp_child_type, cid, visited)
                            for nested_type, nested_info in nested.items():
                                if nested_type in affected:
                                    existing = affected[nested_type]
                                    merged_ids = list(set(existing["ids"] + nested_info["ids"]))
                                    affected[nested_type] = {
                                        "count": len(merged_ids),
                                        "ids": merged_ids,
                                        "strategy": nested_info["strategy"],
                                    }
                                else:
                                    affected[nested_type] = nested_info

        return affected

    def _build_actions(self, object_type: str, object_id: Any, affected: Dict[str, Dict]) -> List[Dict]:
        actions = []

        child_types = self._get_all_child_types(object_type)
        for child_type in child_types:
            if child_type not in affected:
                continue
            info = affected[child_type]
            strategy = CascadeStrategy(info["strategy"])

            if strategy == CascadeStrategy.RESTRICT:
                actions.append({
                    "type": "restrict",
                    "target": child_type,
                    "ids": info["ids"],
                })
            elif strategy == CascadeStrategy.CASCADE:
                actions.append({
                    "type": "delete",
                    "target": child_type,
                    "ids": info["ids"],
                })
            elif strategy == CascadeStrategy.SET_NULL:
                actions.append({
                    "type": "set_null",
                    "target": child_type,
                    "ids": info["ids"],
                })
            elif strategy == CascadeStrategy.SET_DEFAULT:
                actions.append({
                    "type": "set_default",
                    "target": child_type,
                    "ids": info["ids"],
                })

        return actions

    def before_delete(self, object_type: str, object_id: Any) -> Dict:
        affected = self._collect_affected(object_type, object_id)
        actions = self._build_actions(object_type, object_id, affected)

        has_restrict = any(a["type"] == "restrict" for a in actions)
        can_delete = not has_restrict

        return {
            "can_delete": can_delete,
            "strategy": self._get_overall_strategy(object_type),
            "affected": affected,
            "actions": actions,
        }

    def _get_overall_strategy(self, object_type: str) -> str:
        child_types = self._get_all_child_types(object_type)
        if not child_types:
            return "none"
        strategies = [self.get_cascade_strategy(object_type, ct) for ct in child_types]
        if any(s == CascadeStrategy.RESTRICT for s in strategies):
            return CascadeStrategy.RESTRICT.value
        if all(s == CascadeStrategy.CASCADE for s in strategies):
            return CascadeStrategy.CASCADE.value
        return "mixed"

    def execute_cascade(self, actions: List[Dict]) -> Dict[str, int]:
        deleted_counts: Dict[str, int] = {}
        children_audit_info: List[Dict] = []

        delete_actions = [a for a in actions if a["type"] == "delete"]
        set_null_actions = [a for a in actions if a["type"] == "set_null"]
        set_default_actions = [a for a in actions if a["type"] == "set_default"]

        parent_type = None
        parent_id_val = None
        for action in delete_actions:
            if parent_type is None:
                parent_type = action.get("target")
                ids = action.get("ids", [])
                if ids:
                    parent_id_val = ids[0]

        with self.ds.transaction():
            for action in set_null_actions:
                target = action["target"]
                meta = registry.get(target)
                if not meta:
                    continue
                table = meta.table_name
                parent_type_ct = self.config_loader.get_parent_object(target)
                fk = self._get_foreign_key(parent_type_ct, target) if parent_type_ct else f"{parent_type_ct}_id"
                ids = action["ids"]
                if ids:
                    placeholders = ','.join(['?'] * len(ids))
                    sql = f"UPDATE {table} SET {fk} = NULL WHERE id IN ({placeholders})"
                    self.ds.execute(sql, tuple(ids))

            for action in set_default_actions:
                target = action["target"]
                meta = registry.get(target)
                if not meta:
                    continue
                table = meta.table_name
                parent_type_ct = self.config_loader.get_parent_object(target)
                fk = self._get_foreign_key(parent_type_ct, target) if parent_type_ct else f"{parent_type_ct}_id"
                fk_field = None
                for f in meta.fields:
                    if f.db_column == fk:
                        fk_field = f
                        break
                default_val = fk_field.default if fk_field else None
                ids = action["ids"]
                if ids:
                    placeholders = ','.join(['?'] * len(ids))
                    sql = f"UPDATE {table} SET {fk} = ? WHERE id IN ({placeholders})"
                    self.ds.execute(sql, (default_val, *tuple(ids)))

            for action in reversed(delete_actions):
                target = action["target"]
                meta = registry.get(target)
                if not meta:
                    continue
                table = meta.table_name

                child_types = self._get_all_child_types(target)
                for child_type in child_types:
                    child_meta = registry.get(child_type)
                    if not child_meta:
                        continue
                    child_table = child_meta.table_name
                    
                    child_ids_to_delete = []
                    child_old_data_list = []
                    parent_ids = action["ids"]
                    
                    if target == "business_object" and child_type == "relationship":
                        rel_meta = registry.get("relationship")
                        if rel_meta and parent_ids:
                            placeholders_batch = ','.join(['?'] * len(parent_ids))
                            sql_batch = (
                                f"SELECT DISTINCT * FROM {rel_meta.table_name}"
                                f" WHERE source_bo_id IN ({placeholders_batch})"
                                f" OR target_bo_id IN ({placeholders_batch})"
                            )
                            cursor = self.ds.execute(sql_batch, tuple(parent_ids) + tuple(parent_ids))
                            rel_columns = [desc[0] for desc in cursor.description]
                            child_rels = [dict(zip(rel_columns, row)) for row in cursor.fetchall()]
                            for cr in child_rels:
                                child_ids_to_delete.append(cr["id"])
                                child_old_data_list.append(cr)
                    else:
                        comp_fk = self._get_composition_fk(target, child_type)
                        fk = comp_fk if comp_fk else self._get_foreign_key(target, child_type)
                        child_meta = registry.get(child_type)
                        if child_meta and parent_ids and fk:
                            placeholders_batch = ','.join(['?'] * len(parent_ids))
                            sql_batch = (
                                f"SELECT * FROM {child_meta.table_name}"
                                f" WHERE {fk} IN ({placeholders_batch})"
                            )
                            cursor = self.ds.execute(sql_batch, tuple(parent_ids))
                            child_columns = [desc[0] for desc in cursor.description]
                            child_records = [dict(zip(child_columns, row)) for row in cursor.fetchall()]
                            for cr in child_records:
                                child_ids_to_delete.append(cr["id"])
                                child_old_data_list.append(cr)
                    
                    if child_ids_to_delete:
                        child_ids_to_delete = list(set(child_ids_to_delete))
                        child_old_data_list_dedup = []
                        seen_ids = set()
                        for cd in child_old_data_list:
                            if cd["id"] not in seen_ids:
                                seen_ids.add(cd["id"])
                                child_old_data_list_dedup.append(cd)
                        
                        for cd in child_old_data_list_dedup:
                            children_audit_info.append({
                                'object_type': child_type,
                                'object_id': cd["id"],
                                'old_data': cd,
                                'parent_object_type': target,
                                'parent_object_id': rid,
                            })
                        
                        placeholders = ','.join(['?'] * len(child_ids_to_delete))
                        sql = f"DELETE FROM {child_table} WHERE id IN ({placeholders})"
                        self.ds.execute(sql, tuple(child_ids_to_delete))
                        deleted_counts[child_type] = deleted_counts.get(child_type, 0) + len(child_ids_to_delete)

                ids = action["ids"]
                if ids:
                    placeholders = ','.join(['?'] * len(ids))
                    sql = f"DELETE FROM {table} WHERE id IN ({placeholders})"
                    self.ds.execute(sql, tuple(ids))
                    deleted_counts[target] = deleted_counts.get(target, 0) + len(ids)

        deleted_counts['_children_audit_info'] = children_audit_info
        deleted_counts['_parent_object_type'] = parent_type
        deleted_counts['_parent_object_id'] = parent_id_val
        return deleted_counts


def get_type_order() -> List[str]:
    return HierarchyConfigLoader.get_type_order()
