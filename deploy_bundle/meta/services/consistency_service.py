from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

from meta.core.datasource import DataSource
from meta.core.models import MetaObject, registry
from meta.services.cascade_service import HierarchyConfigLoader


def _build_hierarchy_chain():
    loader = HierarchyConfigLoader
    levels = loader.get_levels('biz_hierarchy')
    chain = ["product", "version"]
    for level in levels:
        obj = level.get('object', '')
        if obj and obj not in chain:
            chain.append(obj)
    chain.append("relationship")
    return chain


def _build_parent_fk_map():
    loader = HierarchyConfigLoader
    fk_map = {
        "version": "product_id",
        "relationship": "version_id",
    }
    for level in loader.get_levels('biz_hierarchy'):
        obj = level.get('object', '')
        fk = level.get('foreign_key_field', '')
        if obj and fk:
            fk_map[obj] = fk
    return fk_map


def _build_version_scoped_objects():
    loader = HierarchyConfigLoader
    objects = ["version"]
    for level in loader.get_levels('biz_hierarchy'):
        obj = level.get('object', '')
        if obj:
            objects.append(obj)
    objects.append("relationship")
    return objects


HIERARCHY_CHAIN = _build_hierarchy_chain()
PARENT_FOREIGN_KEY_MAP = _build_parent_fk_map()
VERSION_SCOPED_OBJECTS = _build_version_scoped_objects()


@dataclass
class ConsistencyCheckResult:
    valid: bool = True
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)

    def add_error(self, code: str, message: str, field_name: str = "", detail: Dict[str, Any] = None):
        self.valid = False
        self.errors.append({
            "code": code,
            "message": message,
            "field": field_name,
            "detail": detail or {},
        })

    def add_warning(self, code: str, message: str, field_name: str = "", detail: Dict[str, Any] = None):
        self.warnings.append({
            "code": code,
            "message": message,
            "field": field_name,
            "detail": detail or {},
        })

    def merge(self, other: "ConsistencyCheckResult"):
        if not other.valid:
            self.valid = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


class ConsistencyService:

    def __init__(self, datasource: DataSource):
        self.ds = datasource

    def _get_parent_object_type(self, object_type: str) -> Optional[str]:
        meta_obj = registry.get(object_type)
        if meta_obj and meta_obj.parent_object:
            return meta_obj.parent_object
        hierarchy_index = HIERARCHY_CHAIN.index(object_type) if object_type in HIERARCHY_CHAIN else -1
        if hierarchy_index > 0:
            return HIERARCHY_CHAIN[hierarchy_index - 1]
        return None

    def _get_parent_fk_field(self, object_type: str) -> Optional[str]:
        return PARENT_FOREIGN_KEY_MAP.get(object_type)

    def _resolve_version_id(self, object_type: str, data: Dict[str, Any]) -> Any:
        if "version_id" in data and data["version_id"] is not None:
            return data["version_id"]
        if object_type == "version":
            return data.get("id")
        if object_type == "product":
            return None
        parent_type = self._get_parent_object_type(object_type)
        parent_fk = self._get_parent_fk_field(object_type)
        if parent_fk and parent_fk in data and data[parent_fk] is not None:
            parent_record = self.ds.find_by_id(
                registry.get(parent_type).table_name,
                data[parent_fk],
            )
            if parent_record:
                return self._resolve_version_id(parent_type, parent_record)
        return None

    def check_hierarchy_constraint(self, object_type: str, data: Dict[str, Any]) -> ConsistencyCheckResult:
        result = ConsistencyCheckResult()
        meta_obj = registry.get(object_type)
        if not meta_obj:
            result.add_error("UNKNOWN_OBJECT_TYPE", "未知的对象类型: {}".format(object_type))
            return result

        parent_type = self._get_parent_object_type(object_type)
        if parent_type is None:
            return result

        parent_fk = self._get_parent_fk_field(object_type)
        if not parent_fk:
            return result

        parent_id_value = data.get(parent_fk)
        if parent_id_value is None:
            result.add_error(
                "PARENT_ID_MISSING",
                "缺少父对象引用字段: {}".format(parent_fk),
                field_name=parent_fk,
            )
            return result

        parent_meta = registry.get(parent_type)
        if not parent_meta:
            result.add_error(
                "PARENT_TYPE_NOT_FOUND",
                "父对象类型未注册: {}".format(parent_type),
                field_name=parent_fk,
            )
            return result

        parent_record = self.ds.find_by_id(parent_meta.table_name, parent_id_value)
        if not parent_record:
            result.add_error(
                "PARENT_NOT_FOUND",
                "父对象不存在: {} id={}".format(parent_type, parent_id_value),
                field_name=parent_fk,
                detail={"parent_type": parent_type, "parent_id": parent_id_value},
            )
            return result

        if object_type in VERSION_SCOPED_OBJECTS and parent_type in VERSION_SCOPED_OBJECTS:
            data_version_id = self._resolve_version_id(object_type, data)
            parent_version_id = self._resolve_version_id(parent_type, parent_record)
            if data_version_id is not None and parent_version_id is not None:
                if data_version_id != parent_version_id:
                    result.add_error(
                        "VERSION_MISMATCH",
                        "父对象与当前对象不属于同一版本: data_version={}, parent_version={}".format(
                            data_version_id, parent_version_id
                        ),
                        field_name=parent_fk,
                        detail={
                            "data_version_id": data_version_id,
                            "parent_version_id": parent_version_id,
                        },
                    )

        return result

    def check_reference_integrity(
        self,
        object_type: str,
        data: Dict[str, Any],
        exclude_id: Any = None,
    ) -> ConsistencyCheckResult:
        result = ConsistencyCheckResult()
        meta_obj = registry.get(object_type)
        if not meta_obj:
            result.add_error("UNKNOWN_OBJECT_TYPE", "未知的对象类型: {}".format(object_type))
            return result

        for rel in meta_obj.relations:
            if rel.relation_type.value != "reference":
                continue
            fk_field = rel.source_field
            if not fk_field:
                continue
            ref_id_value = data.get(fk_field)
            if ref_id_value is None:
                continue
            target_meta = registry.get(rel.target_object)
            if not target_meta:
                result.add_error(
                    "REFERENCE_TARGET_NOT_REGISTERED",
                    "引用目标对象类型未注册: {}".format(rel.target_object),
                    field_name=fk_field,
                )
                continue
            target_record = self.ds.find_by_id(target_meta.table_name, ref_id_value)
            if not target_record:
                result.add_error(
                    "REFERENCE_NOT_FOUND",
                    "引用目标不存在: {} id={}".format(rel.target_object, ref_id_value),
                    field_name=fk_field,
                    detail={"target_type": rel.target_object, "target_id": ref_id_value},
                )

        if object_type == "relationship":
            source_bo_id = data.get("source_bo_id")
            target_bo_id = data.get("target_bo_id")
            if source_bo_id is not None and target_bo_id is not None:
                if source_bo_id == target_bo_id:
                    result.add_error(
                        "SELF_REFERENCE",
                        "源业务对象和目标业务对象不能相同",
                        field_name="source_bo_id",
                        detail={"source_bo_id": source_bo_id, "target_bo_id": target_bo_id},
                    )

            bo_meta = registry.get("business_object")
            if bo_meta:
                if source_bo_id is not None:
                    source_bo = self.ds.find_by_id(bo_meta.table_name, source_bo_id)
                    if not source_bo:
                        result.add_error(
                            "SOURCE_BO_NOT_FOUND",
                            "源业务对象不存在: id={}".format(source_bo_id),
                            field_name="source_bo_id",
                            detail={"source_bo_id": source_bo_id},
                        )
                if target_bo_id is not None:
                    target_bo = self.ds.find_by_id(bo_meta.table_name, target_bo_id)
                    if not target_bo:
                        result.add_error(
                            "TARGET_BO_NOT_FOUND",
                            "目标业务对象不存在: id={}".format(target_bo_id),
                            field_name="target_bo_id",
                            detail={"target_bo_id": target_bo_id},
                        )

            if source_bo_id is not None and target_bo_id is not None:
                self._check_circular_reference(data, exclude_id, result)

        return result

    def _check_circular_reference(
        self,
        data: Dict[str, Any],
        exclude_id: Any,
        result: ConsistencyCheckResult,
    ):
        source_bo_id = data.get("source_bo_id")
        target_bo_id = data.get("target_bo_id")
        rel_meta = registry.get("relationship")
        if not rel_meta:
            return

        visited: Set[Any] = set()
        visited.add(source_bo_id)
        current_bo_id = target_bo_id

        while current_bo_id is not None:
            if current_bo_id in visited:
                result.add_error(
                    "CIRCULAR_REFERENCE",
                    "存在循环引用: 从业务对象 {} 可以回到 {}".format(source_bo_id, current_bo_id),
                    field_name="target_bo_id",
                    detail={"source_bo_id": source_bo_id, "target_bo_id": target_bo_id},
                )
                return
            visited.add(current_bo_id)
            next_bo_id = None
            filters = {"source_bo_id": current_bo_id}
            outgoing_rels = self.ds.find(rel_meta.table_name, filters)
            if outgoing_rels:
                next_bo_id = outgoing_rels[0].get("target_bo_id")
            current_bo_id = next_bo_id

    def check_uniqueness(
        self,
        object_type: str,
        data: Dict[str, Any],
        exclude_id: Any = None,
    ) -> ConsistencyCheckResult:
        result = ConsistencyCheckResult()
        meta_obj = registry.get(object_type)
        if not meta_obj:
            result.add_error("UNKNOWN_OBJECT_TYPE", "未知的对象类型: {}".format(object_type))
            return result

        business_key_field = meta_obj.get_business_key_field()
        if business_key_field:
            bk_value = data.get(business_key_field.db_column)
            if bk_value is not None:
                version_id = self._resolve_version_id(object_type, data)
                filters = {business_key_field.db_column: bk_value}
                if version_id is not None:
                    filters["version_id"] = version_id
                existing = self.ds.find(meta_obj.table_name, filters)
                if existing:
                    if exclude_id is not None:
                        existing = [r for r in existing if r.get("id") != exclude_id]
                    if existing:
                        scope_desc = "版本(version_id={})内".format(version_id) if version_id else "全局"
                        result.add_error(
                            "BUSINESS_KEY_DUPLICATE",
                            "业务键{}重复: {}={}".format(scope_desc, business_key_field.db_column, bk_value),
                            field_name=business_key_field.db_column,
                            detail={
                                "field": business_key_field.db_column,
                                "value": bk_value,
                                "version_id": version_id,
                                "existing_ids": [r.get("id") for r in existing],
                            },
                        )

        code_field = None
        for f in meta_obj.fields:
            if f.db_column == "code":
                code_field = f
                break
        if code_field:
            code_value = data.get("code")
            if code_value is not None:
                version_id = self._resolve_version_id(object_type, data)
                filters = {"code": code_value}
                if version_id is not None:
                    filters["version_id"] = version_id
                existing = self.ds.find(meta_obj.table_name, filters)
                if existing:
                    if exclude_id is not None:
                        existing = [r for r in existing if r.get("id") != exclude_id]
                    if existing:
                        scope_desc = "版本(version_id={})内".format(version_id) if version_id else "全局"
                        result.add_error(
                            "CODE_DUPLICATE",
                            "编码{}重复: code={}".format(scope_desc, code_value),
                            field_name="code",
                            detail={
                                "value": code_value,
                                "version_id": version_id,
                                "existing_ids": [r.get("id") for r in existing],
                            },
                        )

        return result

    def validate_full(
        self,
        object_type: str,
        data: Dict[str, Any],
        operation: str = "create",
        exclude_id: Any = None,
    ) -> ConsistencyCheckResult:
        result = ConsistencyCheckResult()

        hierarchy_result = self.check_hierarchy_constraint(object_type, data)
        result.merge(hierarchy_result)

        reference_result = self.check_reference_integrity(object_type, data, exclude_id)
        result.merge(reference_result)

        uniqueness_result = self.check_uniqueness(object_type, data, exclude_id)
        result.merge(uniqueness_result)

        return result
