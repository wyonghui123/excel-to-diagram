# -*- coding: utf-8 -*-
"""
元模型隔离加载器 (v1.1)

设计要点:
1. 不使用全局 MetaRegistry 单例 (避免与运行时注册冲突 + xdist 共享)
2. 提供 load_schemas() / load_aspects() / load_rls_rules() / load_factories()
3. 可注入 mock / 替换特定 yaml, 支持单文件测试
4. v1.1 新增 aspects/rls/factories 三类资产的加载
"""
import os
import ast
from pathlib import Path
from typing import Dict, Optional, Any

# Schema 目录默认路径
DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
DEFAULT_RLS_DIR = Path(__file__).resolve().parents[3] / "rls_rules"


def load_schemas(
    schema_dir: Optional[str] = None,
    target_dict: Optional[Dict] = None,
) -> Dict[str, "MetaObject"]:
    """
    加载元模型目录并返回隔离的对象字典。

    Args:
        schema_dir: yaml 目录路径, 默认 <repo>/meta/schemas
        target_dict: 可选外部字典 (避免共享全局状态)

    Returns:
        {object_id: MetaObject} 字典
    """
    from meta.core.yaml_loader import register_from_directory

    target = target_dict if target_dict is not None else {}
    register_from_directory(str(schema_dir or DEFAULT_SCHEMA_DIR), target=target)
    return target


def load_aspects(schema_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    加载 aspects.yaml, 返回 {aspect_id: aspect_config} 字典。

    v1.1 新增。
    """
    import yaml
    aspects_path = Path(schema_dir or DEFAULT_SCHEMA_DIR) / "aspects.yaml"
    if not aspects_path.exists():
        return {}
    with open(aspects_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def load_rls_rules(rls_dir: Optional[str] = None) -> Dict[str, Dict]:
    """
    加载 rls_rules/*.yaml, 返回 {entity_id: rls_config} 字典。

    v1.1 新增。
    """
    import yaml
    rls_path = Path(rls_dir or DEFAULT_RLS_DIR)
    result = {}
    if not rls_path.exists():
        return result
    for yaml_file in sorted(rls_path.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and isinstance(data, dict) and "entity" in data:
                entity_id = data["entity"]
                result[entity_id] = data
        except Exception:
            # 单文件失败不阻断其他文件加载
            continue
    return result


def _safe_literal_eval(node: ast.AST) -> Any:
    """
    递归提取 AST 节点中的字面量值 (静态分析, 不执行)。

    支持: dict/list/set/tuple/str/bytes/num/bool/None/f-string
    对不可静态求值的内容返回 None (不抛错)。
    """
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _extract_dict_keys(node: ast.AST) -> list:
    """
    静态提取 AST 字典节点的 keys (不要求 values 可求值)。
    """
    keys = []
    if not isinstance(node, ast.Dict):
        return keys
    for k in node.keys:
        if k is None:
            continue
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys.append(k.value)
        elif isinstance(k, ast.Name):
            # f-string 等
            keys.append(getattr(k, 'id', '?'))
    return keys


def load_factories() -> Dict[str, Dict[str, Any]]:
    """
    扫描 meta/tests/factories/*.py, 提取每个工厂的 _OBJECT_TYPE 与 _DEFAULTS / _base_defaults()。

    v1.1 改进: 静态 AST 提取, 不执行代码 (避免 cls.unique_str 等动态依赖)
    v1.1.1 (P2): 也扫描 _base.py, 提取 unique_id() 函数存在性
                  -> 用于 FACTORY_UNIQUE_ID_DETERMINISTIC 约束推导

    Returns:
        {object_type: {"class_name": str, "defaults_keys": list, "file": str}}
        + "_meta": {"unique_id_defined": bool, "unique_id_body": str, ...}
    """
    factories_dir = Path(__file__).resolve().parents[1] / "factories"
    result = {}

    if not factories_dir.exists():
        return result

    # [FIX 2026-07-17 P2] 先扫描 _base.py, 提取 unique_id() 元数据
    _base_file = factories_dir / "_base.py"
    meta_info = {
        "unique_id_defined": False,
        "unique_id_body": "",
        "uses_counter": False,
        "uses_lock": False,
    }
    if _base_file.exists():
        try:
            with open(_base_file, encoding="utf-8") as f:
                base_source = f.read()
            base_tree = ast.parse(base_source)
            for node in ast.walk(base_tree):
                if isinstance(node, ast.FunctionDef) and node.name == "unique_id":
                    meta_info["unique_id_defined"] = True
                    # 序列化函数体源码 (用于错误诊断)
                    body_lines = ast.unparse(node).splitlines()
                    meta_info["unique_id_body"] = "\n".join(body_lines)
                    # 检测关键模式
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Global) and any(
                            "counter" in (t if isinstance(t, str) else t.id)
                            for t in sub.names
                        ):
                            meta_info["uses_counter"] = True
                    # 检测 lock
                    body_src = meta_info["unique_id_body"]
                    meta_info["uses_lock"] = "Lock" in body_src or "lock" in body_src.lower()
        except (SyntaxError, OSError):
            pass

    for py_file in sorted(factories_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue  # 跳过 _base.py / _trace_id.py
        if py_file.name == "__init__.py":
            continue

        try:
            with open(py_file, encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source)
        except SyntaxError:
            continue

        # 找顶层类继承 BaseFactory
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = [
                b.id if isinstance(b, ast.Name) else
                (b.attr if isinstance(b, ast.Attribute) else "")
                for b in node.bases
            ]
            if not any("Factory" in n or "BaseFactory" in n for n in base_names):
                continue

            # 提取 _OBJECT_TYPE + 默认字典 keys
            obj_type = None
            defaults_keys = []
            for item in node.body:
                # 类属性: _OBJECT_TYPE / _DEFAULTS
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "_OBJECT_TYPE":
                                obj_type = _safe_literal_eval(item.value)
                            elif target.id == "_DEFAULTS":
                                defaults_keys = _extract_dict_keys(item.value)

                # 方法: _base_defaults() return {...}
                if isinstance(item, ast.FunctionDef) and item.name == "_base_defaults":
                    # 找 return Dict 字面量
                    for sub in ast.walk(item):
                        if isinstance(sub, ast.Return) and sub.value is not None:
                            keys = _extract_dict_keys(sub.value)
                            if keys and not defaults_keys:
                                defaults_keys = keys
                            break

            if obj_type:
                result[obj_type] = {
                    "class_name": node.name,
                    "defaults_keys": defaults_keys,
                    "file": py_file.name,
                }

    # [FIX 2026-07-17 P2] 注入 _meta 键, 供 FACTORY_UNIQUE_ID_DETERMINISTIC 推导
    result["_meta"] = meta_info

    return result


def reload_one(
    yaml_file_path: str,
    target_dict: Dict,
) -> Optional["MetaObject"]:
    """重新加载单个 yaml 文件到目标字典。"""
    from meta.core.yaml_loader import load_yaml_file

    obj = load_yaml_file(yaml_file_path)
    if obj is not None:
        target_dict[obj.id] = obj
    return obj


def invalidate_global_cache():
    """清空 yaml_loader 内部缓存（开发模式用）"""
    try:
        from meta.core.yaml_loader import _invalidate_yaml_cache
        _invalidate_yaml_cache()
    except Exception:
        pass