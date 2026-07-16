from typing import List, Optional

from meta.core.models import MetaObject, registry
from meta.core.query_builder import QueryBuilder


def resolve_object_id_by_depth(depth: int) -> Optional[str]:
    for object_id in registry.list_objects():
        meta_obj = registry.get(object_id)
        if meta_obj and meta_obj.get_hierarchy_depth() == depth:
            return object_id
    return None


def get_name_field(meta_obj: MetaObject) -> Optional[str]:
    for f in meta_obj.fields:
        if f.semantics.display_name:
            return f.id
    for f in meta_obj.fields:
        if f.id == "name":
            return f.id
    return None


def get_child_object_id(object_id: str) -> Optional[str]:
    for oid in registry.list_objects():
        meta_obj = registry.get(oid)
        if meta_obj and meta_obj.parent_object == object_id:
            return oid
    return None


def get_parent_field(child_obj: MetaObject, parent_object_id: str) -> Optional[str]:
    expected_field = "{0}_id".format(parent_object_id)
    for f in child_obj.fields:
        if f.id == expected_field:
            return f.id
    for f in child_obj.fields:
        if f.id.endswith("_id") and parent_object_id.replace("_", "") in f.id.replace("_", ""):
            return f.id
    return None


def get_ancestor_parent_field(meta_obj: MetaObject, ancestor_id: str) -> Optional[str]:
    expected_field = "{0}_id".format(ancestor_id)
    for f in meta_obj.fields:
        if f.id == expected_field:
            return f.id
    hierarchy = meta_obj.get_hierarchy_ancestors()
    if ancestor_id in hierarchy:
        ancestor_obj = registry.get(ancestor_id)
        if ancestor_obj:
            for f in meta_obj.fields:
                if f.id.endswith("_id"):
                    field_prefix = f.id[:-3]
                    if field_prefix in hierarchy:
                        return f.id
    return None


def apply_hierarchy_filter(ds, builder: QueryBuilder, meta_obj: MetaObject,
                           hierarchy_path: str) -> None:
    segments = [s.strip() for s in hierarchy_path.strip().split("/") if s.strip()]
    if not segments:
        return

    depth = len(segments) - 1
    target_depth = meta_obj.get_hierarchy_depth()

    if depth == target_depth:
        last_segment = segments[-1]
        name_field = get_name_field(meta_obj)
        if name_field:
            builder.where_ilike(name_field, last_segment)
    elif depth < target_depth:
        ancestor_object_id = resolve_object_id_by_depth(depth)
        if ancestor_object_id:
            ancestor_obj = registry.get(ancestor_object_id)
            if ancestor_obj:
                ancestor_name_field = get_name_field(ancestor_obj)
                if ancestor_name_field:
                    ancestor_builder = QueryBuilder(ds, ancestor_obj)
                    ancestor_builder.where_ilike(ancestor_name_field, segments[-1])
                    ancestor_rows = ancestor_builder.execute()
                    ancestor_ids = [r.get("id") for r in ancestor_rows if r.get("id") is not None]
                    if ancestor_ids:
                        parent_field = get_ancestor_parent_field(meta_obj, ancestor_object_id)
                        if parent_field:
                            builder.where_in(parent_field, ancestor_ids)


def apply_path_name_filters(ds, builder: QueryBuilder, segments: List[str]) -> None:
    depth = len(segments) - 1
    target_object_id = resolve_object_id_by_depth(depth)
    if not target_object_id:
        return

    meta_obj = registry.get(target_object_id)
    if not meta_obj:
        return

    name_field = get_name_field(meta_obj)
    if name_field and segments:
        builder.where_ilike(name_field, segments[-1])

    if len(segments) > 1:
        hierarchy = registry.get_hierarchy(target_object_id)
        for i, ancestor_id in enumerate(hierarchy[:-1]):
            if i >= len(segments) - 1:
                break
            ancestor_obj = registry.get(ancestor_id)
            if not ancestor_obj:
                continue
            ancestor_name_field = get_name_field(ancestor_obj)
            if not ancestor_name_field:
                continue

            ancestor_builder = QueryBuilder(ds, ancestor_obj)
            ancestor_builder.where_ilike(ancestor_name_field, segments[i])
            ancestor_rows = ancestor_builder.execute()
            ancestor_ids = [r.get("id") for r in ancestor_rows if r.get("id") is not None]

            if not ancestor_ids:
                continue

            next_in_chain = hierarchy[i + 1] if i + 1 < len(hierarchy) else None
            if next_in_chain == target_object_id:
                parent_field = get_ancestor_parent_field(meta_obj, ancestor_id)
                if parent_field:
                    builder.where_in(parent_field, ancestor_ids)
            else:
                intermediate_obj = registry.get(next_in_chain)
                if intermediate_obj:
                    parent_field = get_ancestor_parent_field(intermediate_obj, ancestor_id)
                    if parent_field:
                        intermediate_builder = QueryBuilder(ds, intermediate_obj)
                        intermediate_builder.where_in(parent_field, ancestor_ids)
                        intermediate_rows = intermediate_builder.execute()
                        intermediate_ids = [r.get("id") for r in intermediate_rows if r.get("id") is not None]
                        if intermediate_ids:
                            chain_idx = hierarchy.index(next_in_chain)
                            next_chain = hierarchy[chain_idx + 1] if chain_idx + 1 < len(hierarchy) else None
                            if next_chain == target_object_id:
                                pf = get_ancestor_parent_field(meta_obj, next_chain)
                                if pf:
                                    builder.where_in(pf, intermediate_ids)
