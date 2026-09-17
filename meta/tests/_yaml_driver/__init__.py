"""YAML 元模型驱动测试引擎 (Meta-Model Driven Test Engine)

Version: v1.0
Purpose: 从 meta/schemas/*.yaml 自动推导测试用例

Submodules:
    - loader: 隔离的 MetaRegistry wrapper, 避免污染全局单例
    - discoverer: 扫描 yaml -> 推导 case spec
    - pytest_plugin: pytest_generate_tests hook, 参数化所有用例

典型用法 (test_yaml_driven_constraints.py):
    from meta.tests._yaml_driver import discover_all_constraints, SchemaLoader

    def test_yaml_constraints(meta_object):
        ...
"""