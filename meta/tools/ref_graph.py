# -*- coding: utf-8 -*-
"""
引用图工具 - 扫描 yaml 中的关联声明,产出引用图 JSON

[v0.1 2026-09-22 PoC B 实证]
- 仅扫描 yaml 内的 through / source_key / target_key 字段
- 不扫描代码 SQL(yaml-only scope)
- 输出 .ref_graph.json,可作为 v089 类问题的"提前告警"输入

用法:
    python -m meta.tools.ref_graph                    # 默认扫描 meta/schemas/*.yaml
    python -m meta.tools.ref_graph --check-drops      # 检查"未引用任何 yaml 的 join table"(可疑孤儿)
    python -m meta.tools.ref_graph --check-orphans    # 检查"yaml 通过 through 引用不存在的 join table"
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Set
import yaml


REF_GRAPH_FILE = "meta/schemas/.ref_graph.json"


def scan_yaml_through(yaml_path: Path, all_table_names: Set[str]) -> Dict[str, Any]:
    """
    扫描单个 yaml 的 associations 列表,抽取 through/source_key/target_key 字段。
    返回该 yaml 的引用边列表。
    """
    edges = []
    warnings = []

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return {"file": yaml_path.name, "error": str(e), "edges": [], "warnings": []}

    if not isinstance(data, dict):
        return {"file": yaml_path.name, "error": "top-level not dict", "edges": [], "warnings": []}

    obj_id = data.get("id") or yaml_path.stem
    obj_table = data.get("table_name") or yaml_path.stem + "s"

    # 关联定义通常在 associations 下,可能是 list 或 dict(以 name 为 key)
    associations = data.get("associations", [])
    if isinstance(associations, dict):
        # dict 形态: {name: assoc_def}
        assoc_list = []
        for k, v in associations.items():
            if isinstance(v, dict):
                v["name"] = v.get("name") or k
                assoc_list.append(v)
            elif isinstance(v, list):
                # 嵌套 list 形态(罕见)
                assoc_list.extend(v)
        associations = assoc_list
    elif not isinstance(associations, list):
        associations = []

    for idx, assoc in enumerate(associations):
        if not isinstance(assoc, dict):
            continue

        assoc_name = assoc.get("name") or f"assoc_{idx}"
        through_raw = assoc.get("through")
        if not through_raw:
            continue  # 非 join table 关联,跳过

        # through 可能是字符串或列表
        # 字符串形态: "org_members" 或 "service_module->sub_domain->domain"
        # 列表形态(罕见): 通过 path 列表
        through_paths = through_raw if isinstance(through_raw, list) else [through_raw]

        for path_str in through_paths:
            if not isinstance(path_str, str):
                continue
            # 链式 path 拆分: service_module->sub_domain->domain
            # 每一步都是 yaml id,生成对应的"step 边"
            steps = [s.strip() for s in path_str.split("->")]
            for step in steps:
                # 检测 v089 类问题:引用的表在 yaml 中是否存在
                if step and step not in all_table_names and step + "s" not in all_table_names:
                    warnings.append({
                        "type": "through_ref_missing",
                        "yaml": yaml_path.name,
                        "assoc": assoc_name,
                        "missing_ref": step,
                        "path": path_str,
                    })

            # 主边:用最后一步作为"目标实体"(链式 path 的终点)
            target_entity = steps[-1] if steps else None
            source_key = assoc.get("source_key")
            target_key = assoc.get("target_key")
            assoc_type = assoc.get("type", "many_to_many")

            edges.append({
                "from_yaml": obj_id,
                "from_table": obj_table,
                "assoc": assoc_name,
                "through": path_str,
                "to_entity": target_entity,
                "type": assoc_type,
                "source_key": source_key,
                "target_key": target_key,
            })

    return {"file": yaml_path.name, "obj_id": obj_id, "edges": edges, "warnings": warnings}


def build_ref_graph(yaml_dir: str = "meta/schemas") -> Dict[str, Any]:
    """构建引用图主函数"""
    schema_dir = Path(yaml_dir)
    if not schema_dir.exists():
        print(f"[ERROR] yaml dir not found: {schema_dir}")
        sys.exit(1)

    # 第一遍: 收集所有 yaml id 和 table_name,作为"已知实体集"
    all_table_names: Set[str] = set()
    yaml_files = sorted(schema_dir.glob("*.yaml"))

    for yp in yaml_files:
        try:
            with open(yp, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f)
            if isinstance(d, dict):
                obj_id = d.get("id") or yp.stem
                obj_table = d.get("table_name")
                if obj_id:
                    all_table_names.add(obj_id)
                if obj_table:
                    all_table_names.add(obj_table)
        except Exception:
            pass  # 第二遍再细处理

    # 第二遍: 扫描所有 yaml 的 through 字段
    all_edges = []
    all_warnings = []
    yaml_summary = []

    for yp in yaml_files:
        if yp.name.startswith("_"):
            continue  # 跳过 _template / _audit 之类
        result = scan_yaml_through(yp, all_table_names)
        all_edges.extend(result["edges"])
        all_warnings.extend(result["warnings"])
        yaml_summary.append({
            "file": result["file"],
            "obj_id": result.get("obj_id"),
            "edge_count": len(result["edges"]),
            "warning_count": len(result["warnings"]),
        })

    # 第三遍: 检查 join table 孤儿(被引用为 through 但没有自己的 yaml)
    referenced_join_tables: Set[str] = set()
    for edge in all_edges:
        through = edge["through"]
        steps = [s.strip() for s in through.split("->")]
        for step in steps:
            # join table 名通常是复数: org_members, role_permissions
            if step.endswith("s"):
                referenced_join_tables.add(step)

    orphan_join_tables = []
    for jt in referenced_join_tables:
        # join table 没有自己的 yaml(id 或 table_name 匹配)
        if jt not in all_table_names:
            orphan_join_tables.append(jt)

    return {
        "yaml_dir": str(schema_dir),
        "total_yaml_files": len(yaml_files),
        "scanned_yaml_files": len(yaml_summary),
        "total_edges": len(all_edges),
        "total_warnings": len(all_warnings),
        "yaml_summary": yaml_summary,
        "edges": all_edges,
        "warnings": all_warnings,
        "orphan_join_tables": orphan_join_tables,  # 可疑:被引用但无 yaml
        "all_known_entities": sorted(all_table_names),
    }


def print_summary(graph: Dict[str, Any]):
    """打印引用图摘要"""
    print(f"=== yaml 引用图扫描 ===")
    print(f"扫描目录: {graph['yaml_dir']}")
    print(f"yaml 文件: {graph['scanned_yaml_files']}/{graph['total_yaml_files']}")
    print(f"引用边: {graph['total_edges']}")
    print(f"警告: {graph['total_warnings']}")
    print(f"孤儿 join table: {len(graph['orphan_join_tables'])}")
    print()

    if graph["warnings"]:
        print("=== 警告列表(through 引用不存在的实体)===")
        for w in graph["warnings"][:20]:
            print(f"  [{w['yaml']}] {w['assoc']}: missing ref '{w['missing_ref']}'")
        if len(graph["warnings"]) > 20:
            print(f"  ... and {len(graph['warnings']) - 20} more")
        print()

    if graph["orphan_join_tables"]:
        print("=== 可疑 join table(被引用但无 yaml)===")
        for jt in graph["orphan_join_tables"]:
            print(f"  - {jt}")
        print()


def save_ref_graph(graph: Dict[str, Any], path: str = REF_GRAPH_FILE):
    """保存引用图到 .ref_graph.json"""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    print(f"[WRITE] {out_path} size={os.path.getsize(out_path)} bytes")


def main():
    parser = argparse.ArgumentParser(description="yaml 引用图扫描工具")
    parser.add_argument("--yaml-dir", default="meta/schemas", help="yaml 目录")
    parser.add_argument("--out", default=REF_GRAPH_FILE, help="输出 JSON 路径")
    parser.add_argument("--check-drops", action="store_true", help="检查 join table 孤儿")
    parser.add_argument("--check-orphans", action="store_true", help="检查 through 引用缺失")
    args = parser.parse_args()

    graph = build_ref_graph(args.yaml_dir)
    print_summary(graph)
    save_ref_graph(graph, args.out)

    # 退出码:有警告则非零(便于 CI 阻断)
    if graph["warnings"] or graph["orphan_join_tables"]:
        sys.exit(1)


if __name__ == "__main__":
    main()