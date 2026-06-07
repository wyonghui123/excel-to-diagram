"""
schema - M13 v3 引擎：Schema 治理

基于实际代码（46 blueprint + M9 ENTITY_SCHEMAS + meta_object 表）：
- Layer 1 SSOT: M9 ENTITY_SCHEMAS（已存在）
- Layer 2 Exporters: OpenAPI / JSON Schema / TypeScript / GraphQL SDL
- Layer 3 Audit + CI: 字段变更审计 + 破坏性变更检测
- Layer 4 Dashboard: /schema/dashboard 页面

公开 API：
- export_openapi() -> dict
- export_json_schema(entity_name: str) -> dict
- export_typescript() -> str
- calc_compatibility_score(before, after) -> int  (D2 实施)
- run_schema_diff(before, after) -> str  (D2 实施)

回滚方案：删除 schema/ 目录即可（M9 ENTITY_SCHEMAS 不变）
"""
import logging
from .exporters import (
    export_openapi,
    export_entity_openapi,
    export_json_schema,
    export_json_schema_all,
    export_typescript,
)

logger = logging.getLogger(__name__)

__all__ = [
    'export_openapi',
    'export_entity_openapi',
    'export_json_schema',
    'export_json_schema_all',
    'export_typescript',
]

__version__ = '1.1.0'
