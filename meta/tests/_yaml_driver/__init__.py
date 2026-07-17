"""YAML 元模型驱动测试引擎 (Meta-Model Driven Test Engine)

Version: v1.1
Purpose: 从 meta/schemas/*.yaml 自动推导测试用例

Submodules:
    - loader: 隔离的 MetaRegistry wrapper, 避免污染全局单例
            v1.1 新增: load_aspects() / load_rls_rules() / load_factories()
    - discoverer: 扫描 yaml -> 推导 case spec
            v1.1 新增: discover_aspect_constraints / discover_rls_constraints
                       / discover_factory_constraints / discover_v11_constraints
    - pytest_plugin: pytest_generate_tests hook, 参数化所有用例

典型用法 (test_yaml_driven_constraints.py):
    from meta.tests._yaml_driver import discover_all_constraints, SchemaLoader

    def test_yaml_constraints(meta_object):
        ...
"""