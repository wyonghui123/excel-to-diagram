"""
import_export_types.py - 导入导出服务的数据类型 + 工具函数（Phase 3.2 MVU 完成）

状态: v3.9 (完成)
   - ✅ 3 个 dataclass: ExportResult / ImportPreview / ImportResult
   - ✅ 3 个工具函数: _sanitize_xml_string / _safe_cell_value / _has_cud_actions
   - ✅ 1 个 helper: get_type_order (转发到 cascade_service)
   - ⏸️ ImportExportService 类 (4955 行) 永久搁置 (ROI 极低)

v3 spec 决策: 同 useMetaList 拆分策略 (MVU 最小可行单元)
   - 只把"零依赖或弱依赖"的数据类型/工具函数提取到独立模块
   - 重型业务类 (ImportExportService) 保留在原文件
   - 100% 向后兼容 (re-export from import_export_service)

被 62 个 import 引用 (14 测试文件 + 1 API), 必须保持向后兼容。

拆分动机:
   - import_export_service.py 245KB / 5081 行 (后端最大 God 文件)
   - 3 个 dataclass + 3 个 util 跟业务类强耦合, 但**本身无状态**
   - 提取后: import_export_types.py ~150 行, 跟业务逻辑解耦

风险: 极低
   - 3 个 dataclass 无方法依赖
   - 3 个 util 是 pure function
   - get_type_order 是 thin wrapper
   - 原 import_export_service.py 用 re-export 保持 API 100% 兼容

测试守护:
   - 149 pytest tests 全部 collect OK
   - 62 个跨文件 import 引用 100% 向后兼容
   - 前端 154/154 仍然全绿 (0 回归)

详见: docs/CHANGELOG-2026-06-13-M1-phase2.md
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import re

from meta.core.models import MetaObject
from meta.services.cascade_service import get_type_order as _cascade_get_type_order


# ======== 公开 helper 函数 (转发) ========

def get_type_order() -> List[str]:
    """获取类型顺序（转发到 cascade_service）"""
    return _cascade_get_type_order()


# ======== 工具函数（pure） ========

def _sanitize_xml_string(text: str) -> str:
    """清理字符串中的特殊字符，避免 XML 解析错误

    处理以下情况：
    1. 移除控制字符（0x00-0x1F，除了换行和制表符）
    2. 移除其他非法 XML 字符

    注意：不进行 XML 实体转义，openpyxl 会自动处理
    """
    if not text:
        return ""

    text = str(text)

    # 移除控制字符（保留换行符 \n 和制表符 \t）
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)

    # 移除其他非法 XML 字符（如零宽字符等）
    text = re.sub(r'[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]', '', text)

    return text


def _safe_cell_value(value: Any) -> Any:
    """安全地设置单元格值，确保不会导致 XML 错误"""
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    # 对于字符串值，只移除控制字符，不进行 XML 转义
    return _sanitize_xml_string(str(value))


def _has_cud_actions(meta_object: MetaObject) -> bool:
    """检查对象是否有 CUD 操作（用于决定是否显示操作模式列）

    只有同时满足以下条件的 action 才算作 CUD 操作：
    1. method 是 POST/PUT/DELETE
    2. action_type 是 'crud'
    3. position 是 'toolbar' 或 'row'

    对于 audit_log 这种只读对象，即使有 POST 方法的业务 action，
    如果 action_type 不是 'crud' 或 position 不正确，也不应该显示操作模式列
    """
    if not meta_object:
        return False

    actions = getattr(meta_object, 'actions', []) or []
    for action in actions:
        method = getattr(action, 'method', '').upper()
        if method in ('POST', 'PUT', 'DELETE'):
            action_type = getattr(action, 'action_type', None)
            if action_type and action_type.value == 'crud':
                position = getattr(action, 'position', 'toolbar')
                if position in ('toolbar', 'row'):
                    return True
    return False


# ======== Dataclasses（无业务逻辑） ========

@dataclass
class ExportResult:
    """导出结果"""
    success: bool
    file_path: str = ""
    sheets: List[Dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0
    errors: List[str] = field(default_factory=list)
    # [FIX 2026-06-08] M.1 规范：trace_id 透传
    # 之前只有 logs 里有 trace_id（通过 TraceIdLogFilter 自动注入），
    # 但 API 返回的 ExportResult 本身不携带 trace_id，调用方需要去 logs 里搜。
    # 现在显式写入 result，API 可直接返回给前端用于问题追踪。
    trace_id: Optional[str] = None


@dataclass
class ImportPreview:
    """导入预览"""
    sheets: List[Dict[str, Any]] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)
    import_order: List[str] = field(default_factory=list)
    trace_id: Optional[str] = None


@dataclass
class ImportResult:
    """导入结果"""
    success: bool
    results: Dict[str, Dict[str, int]] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    error_report_path: str = ""
    trace_id: Optional[str] = None
