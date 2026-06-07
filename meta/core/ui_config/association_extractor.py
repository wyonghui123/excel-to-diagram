class AssociationExtractor:

    @staticmethod
    def extract(meta_obj, registry, make_json_safe_fn, infer_navigation_fn):
        associations = getattr(meta_obj, 'associations', None)
        if not associations:
            return []

        assoc_list = []
        if isinstance(associations, dict):
            for name, assoc in associations.items():
                a = make_json_safe_fn(assoc)
                a['name'] = name
                if 'target_entity' in a and 'target_type' not in a:
                    a['target_type'] = a['target_entity']
                target_type_name = a.get('target_type') or a.get('target_entity')
                if target_type_name:
                    target_meta = registry.get(target_type_name)
                    if target_meta:
                        a['target_display_name_field'] = target_meta.display_name_field
                infer_navigation_fn(a)
                assoc_list.append(a)
        elif isinstance(associations, list):
            for assoc in associations:
                a = make_json_safe_fn(assoc)
                if 'target_entity' in a and 'target_type' not in a:
                    a['target_type'] = a['target_entity']
                target_type_name = a.get('target_type') or a.get('target_entity')
                if target_type_name:
                    target_meta = registry.get(target_type_name)
                    if target_meta:
                        a['target_display_name_field'] = target_meta.display_name_field
                infer_navigation_fn(a)
                assoc_list.append(a)
        return assoc_list
