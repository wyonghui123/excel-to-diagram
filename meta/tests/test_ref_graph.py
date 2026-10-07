"""
引用图工具测试 - meta/tools/ref_graph.py

[2026-10-07 新增] 守护 build_ref_graph 第一遍扫描的 "_" 前缀判据。
"""

import shutil
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


REAL_SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def _copy_real_schemas(tmp_path):
    """把真实 schemas 复制到 tmp，避免污染仓库。"""
    dst = tmp_path / "schemas"
    dst.mkdir()
    for src in REAL_SCHEMAS.glob("*.yaml"):
        shutil.copy2(src, dst / src.name)
    return dst


class TestKnownEntitiesExcludeUnderscoreFiles:
    """[2026-10-07] all_known_entities 不得包含 `_` 前缀文件的 id / table_name。

    build_ref_graph 分两遍扫 yaml，两遍都必须按同一判据排除内部文件：
      · 第一遍收集 id / table_name 作为"已知实体集"（写入 all_known_entities）
      · 第二遍扫描 through 引用（原本就有 `_` 前缀跳过）

    第一遍原先漏判，导致 _template.yaml 的 id: new_object / table_name: new_objects
    被当成真实实体写进 .ref_graph.json —— 与 load_yaml_directory 的同源缺陷。
    产物是入库文件，只要有人重跑工具就会把污染写回去，故在此守护。
    """

    @staticmethod
    def _build(schemas_dir):
        from meta.tools.ref_graph import build_ref_graph
        return build_ref_graph(str(schemas_dir))

    def test_real_schemas_have_no_new_object(self):
        """真实 schemas 扫描后，已知实体集里不得有 new_object / new_objects。"""
        with tempfile.TemporaryDirectory() as td:
            graph = self._build(_copy_real_schemas(Path(td)))
            entities = graph["all_known_entities"]
            assert "new_object" not in entities
            assert "new_objects" not in entities

    def test_real_schemas_keep_genuine_objects(self):
        """真实对象仍须在已知实体集内，防止判据过宽误伤。"""
        with tempfile.TemporaryDirectory() as td:
            graph = self._build(_copy_real_schemas(Path(td)))
            entities = graph["all_known_entities"]
            for name in ("address", "key_schema", "factor_catalog", "item"):
                assert name in entities, f"{name} 是真实对象，不应被 `_` 前缀判据误伤"

    def test_underscore_prefixed_file_is_excluded(self):
        """`_` 前缀文件即使带合法 id 也不进已知实体集。"""
        with tempfile.TemporaryDirectory() as td:
            schemas = _copy_real_schemas(Path(td))
            (schemas / "_tpl.yaml").write_text(
                "id: totally_real_id\ntable_name: totally_real_table\n", encoding="utf-8"
            )
            entities = self._build(schemas)["all_known_entities"]
            assert "totally_real_id" not in entities
            assert "totally_real_table" not in entities

    def test_removed_entities_are_exactly_the_underscore_prefixed_ones(self):
        """本次判据变更只移除 `_` 前缀文件的 id / table_name，不误伤其他实体。

        无顶层 id 的配置字典（shared_properties / aspects 等）靠第一遍的
        `d.get("id") or yp.stem` 兜底以 stem 进实体集 —— 那是既有行为，与 `_` 前缀
        判据无关（stem 不带下划线），此处显式记录该边界，防止后人误以为一并清理过。
        """
        with tempfile.TemporaryDirectory() as td:
            entities = self._build(_copy_real_schemas(Path(td)))["all_known_entities"]
            # 移除的 5 个：3 个 _ 前缀配置 + _template 的 id/table_name
            for gone in ("_action_groups", "_audit_materialization", "_standard_actions",
                         "new_object", "new_objects"):
                assert gone not in entities, f"{gone} 应随 `_` 前缀判据一并排除"
            # stem 兜底的既有行为保持不变（本批未动）
            for kept in ("shared_properties", "aspects",
                         "audit_log_expectations", "resource_types"):
                assert kept in entities, f"{kept} 靠 stem 兜底，属既有行为，本批不应改动"


class TestCommittedRefGraphArtifact:
    """[2026-10-07] 入库的 .ref_graph.json 不得残留 new_object。

    产物入库意味着污染会随仓库扩散；即使工具修好了，已入库的脏产物也要清。
    """

    def test_committed_artifact_is_clean(self):
        artifact = REAL_SCHEMAS / ".ref_graph.json"
        assert artifact.exists(), ".ref_graph.json 应作为入库产物存在"
        content = artifact.read_text(encoding="utf-8")
        assert "new_object" not in content, (
            ".ref_graph.json 残留 new_object —— 需修 ref_graph.py 第一遍判据并重跑工具"
        )