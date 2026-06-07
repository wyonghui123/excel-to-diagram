from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import re

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

from meta.core.models import MetaObject, registry, ImportExportConfig, QueryOperator, FieldStorage
from meta.core.datasource import DataSource
from meta.services.manage_service import ManageService, BatchOperationResult, CreateRequest, UpdateRequest, DeleteRequest
from meta.services.query_service import QueryService, SearchRequest, QueryCondition
from meta.services.hierarchy_filter_service import HierarchyFilterService
from meta.services.cascade_service import get_type_order
from meta.services.excel_design_system import ExcelDesignSystem


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


@dataclass
class ExportResult:
    """导出结果"""
    success: bool
    file_path: str = ""
    sheets: List[Dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class ImportPreview:
    """导入预览"""
    sheets: List[Dict[str, Any]] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)
    import_order: List[str] = field(default_factory=list)


@dataclass
class ImportResult:
    """导入结果"""
    success: bool
    results: Dict[str, Dict[str, int]] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    error_report_path: str = ""


class ImportExportService:

    def __init__(self, data_source: DataSource, manage_service: Optional[ManageService] = None,
                 query_service: Optional[QueryService] = None):
        self.data_source = data_source
        self.manage_service = manage_service or ManageService(data_source)
        self.query_service = query_service or QueryService(data_source)
        self.hierarchy_filter = HierarchyFilterService(self.query_service, data_source)

    def import_from_excel(self, object_type: str, file_path: str,
                          mapping: Optional[Dict[str, str]] = None) -> BatchOperationResult:
        meta_obj = registry.get(object_type)
        if meta_obj is None:
            return BatchOperationResult(
                failed_count=1,
                errors=["Meta object not found: {0}".format(object_type)]
            )

        if not os.path.exists(file_path):
            return BatchOperationResult(
                failed_count=1,
                errors=["File not found: {0}".format(file_path)]
            )

        try:
            wb = load_workbook(file_path, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
        except Exception as e:
            return BatchOperationResult(
                failed_count=1,
                errors=["Failed to read Excel file: {0}".format(str(e))]
            )

        if len(rows) < 2:
            return BatchOperationResult(
                failed_count=1,
                errors=["Excel file is empty or has no data rows"]
            )

        headers = [str(h).strip() if h is not None else "" for h in rows[0]]

        if mapping:
            field_map = mapping
        else:
            field_map = self._auto_map_fields(meta_obj, headers)

        data_list = []
        for row in rows[1:]:
            record = {}
            for col_idx, header in enumerate(headers):
                if header and header in field_map:
                    field_id = field_map[header]
                    value = row[col_idx] if col_idx < len(row) else None
                    meta_field = meta_obj.get_field(field_id)
                    if meta_field and value is not None:
                        value = self._convert_value(value, meta_field)
                    record[field_id] = value
            if record:
                data_list.append(record)

        if not data_list:
            return BatchOperationResult(
                failed_count=1,
                errors=["No valid data rows found after mapping"]
            )

        return self.manage_service.batch_create(object_type, data_list)

    def export_to_excel(self, object_type: str, filters: Optional[Dict[str, Any]] = None,
                        fields: Optional[List[str]] = None) -> str:
        meta_obj = registry.get(object_type)
        if meta_obj is None:
            raise ValueError("Meta object not found: {0}".format(object_type))

        conditions = []
        if filters:
            for key, value in filters.items():
                conditions.append(QueryCondition(field=key, operator="eq", value=value))

        search_request = SearchRequest(
            object_type=object_type,
            conditions=conditions,
            page=1,
            page_size=100000,
        )

        search_result = self.query_service.search(search_request)
        data = search_result.data

        if not data:
            data = []

        if fields:
            export_fields = []
            for f_id in fields:
                mf = meta_obj.get_field(f_id)
                if mf:
                    export_fields.append(mf)
        else:
            export_fields = meta_obj.fields

        wb = Workbook()
        ws = wb.active
        ws.title = meta_obj.name

        header_row = []
        for mf in export_fields:
            header_row.append(mf.name or mf.id)
        ws.append(header_row)

        for record in data:
            row_data = []
            for mf in export_fields:
                value = record.get(mf.id) or record.get(mf.db_column)
                row_data.append(_safe_cell_value(value))
            ws.append(row_data)

        output_dir = os.path.join(os.getcwd(), "exports")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = "{0}_{1}.xlsx".format(object_type, timestamp)
        file_path = os.path.join(output_dir, file_name)

        wb.save(file_path)
        wb.close()

        return file_path

    def _auto_map_fields(self, meta_object: MetaObject, headers: List[str]) -> Dict[str, str]:
        field_map = {}
        field_by_id = {f.id: f for f in meta_object.fields}
        field_by_name = {}
        field_by_alias = {}

        for f in meta_object.fields:
            field_by_name[f.name] = f
            if f.semantics and f.semantics.aliases:
                for alias in f.semantics.aliases:
                    field_by_alias[alias] = f

        for header in headers:
            if not header:
                continue

            if header in field_by_id:
                field_map[header] = header
                continue

            if header in field_by_name:
                field_map[header] = field_by_name[header].id
                continue

            if header in field_by_alias:
                field_map[header] = field_by_alias[header].id
                continue

            header_lower = header.lower().replace(" ", "_").replace("-", "_")
            for f in meta_object.fields:
                fid_lower = f.id.lower().replace(" ", "_").replace("-", "_")
                if header_lower == fid_lower:
                    field_map[header] = f.id
                    break
                fname_lower = (f.name or "").lower().replace(" ", "_").replace("-", "_")
                if header_lower == fname_lower:
                    field_map[header] = f.id
                    break

        return field_map

    def _get_enum_value_map_from_value_help(self, meta_field) -> Optional[Dict[str, str]]:
        vh = getattr(meta_field, 'value_help', None)
        if not vh:
            ui_vh = getattr(meta_field, 'ui', None)
            if ui_vh:
                vh = getattr(ui_vh, 'value_help', None)
        if not vh:
            return None

        source = getattr(vh, 'source', None)
        if not source or getattr(source, 'type', None) != 'enum':
            return None

        enum_type_id = getattr(source, 'enum_type_id', None)
        if not enum_type_id:
            return None

        try:
            sql = "SELECT code, name FROM enum_values WHERE enum_type_id = ? AND is_active = 1 ORDER BY sort_order"
            cursor = self.data_source.execute(sql, [enum_type_id])
            rows = cursor.fetchall()
            if rows:
                return {row[0]: row[1] for row in rows}
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[ValueHelp] 获取枚举映射失败: {enum_type_id} - {e}")
        return None

    def _get_enum_type_id_from_value_help(self, meta_field) -> Optional[str]:
        vh = getattr(meta_field, 'value_help', None)
        if not vh:
            ui_vh = getattr(meta_field, 'ui', None)
            if ui_vh:
                vh = getattr(ui_vh, 'value_help', None)
        if not vh:
            return None

        source = getattr(vh, 'source', None)
        if not source or getattr(source, 'type', None) != 'enum':
            return None

        return getattr(source, 'enum_type_id', None)

    def _get_bo_display_map_from_value_help(self, meta_field, record_ids: List[Any]) -> Optional[Dict[Any, str]]:
        vh = getattr(meta_field, 'value_help', None)
        if not vh:
            ui_vh = getattr(meta_field, 'ui', None)
            if ui_vh:
                vh = getattr(ui_vh, 'value_help', None)
        if not vh:
            return None

        source = getattr(vh, 'source', None)
        if not source or getattr(source, 'type', None) != 'bo':
            return None

        target_bo = getattr(source, 'target_bo', None)
        display_field = getattr(source, 'display_field', 'name') or 'name'
        value_field = getattr(source, 'value_field', 'id') or 'id'

        if not target_bo or not record_ids:
            return None

        try:
            from meta.core.yaml_loader import get_meta_object
            from meta.core.bo_engine import BOEngine

            meta_obj = get_meta_object(target_bo)
            if not meta_obj:
                return None

            engine = BOEngine(meta_obj)
            result_map = {}
            for rid in record_ids:
                if rid is None:
                    continue
                try:
                    record = engine.get_record(rid)
                    if record:
                        result_map[rid] = str(record.get(display_field, ''))
                except Exception:
                    pass
            return result_map if result_map else None
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[ValueHelp] 获取BO显示名映射失败: {target_bo} - {e}")
        return None

    def _convert_value(self, value: Any, meta_field) -> Any:
        if value is None:
            return None

        from meta.core.models import FieldType

        try:
            enum_map = None
            if meta_field.enum_values:
                enum_map = {ev.get('value'): ev.get('label', ev.get('value')) for ev in meta_field.enum_values}
            elif not meta_field.enum_values:
                enum_map = self._get_enum_value_map_from_value_help(meta_field)

            if enum_map:
                valid_keys = set(enum_map.keys())
                label_to_key = {v: k for k, v in enum_map.items()}

                if isinstance(value, str):
                    if ' - ' in value:
                        key_part = value.split(' - ')[0].strip()
                        if key_part in valid_keys:
                            return key_part

                    if value in valid_keys:
                        return value

                    if value in label_to_key:
                        return label_to_key[value]

            if isinstance(value, str):
                vh_bo = getattr(meta_field, 'value_help', None)
                if not vh_bo:
                    ui_vh = getattr(meta_field, 'ui', None)
                    if ui_vh:
                        vh_bo = getattr(ui_vh, 'value_help', None)
                if vh_bo:
                    vh_source = getattr(vh_bo, 'source', None)
                    if vh_source and getattr(vh_source, 'type', None) == 'bo':
                        import re
                        m = re.search(r'\((\d+)\)\s*$', value)
                        if m:
                            return int(m.group(1))

            if meta_field.field_type == FieldType.INTEGER:
                return int(value)
            elif meta_field.field_type == FieldType.FLOAT:
                return float(value)
            elif meta_field.field_type == FieldType.BOOLEAN:
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return bool(value)
            elif meta_field.field_type == FieldType.DATETIME:
                if isinstance(value, datetime):
                    return value.isoformat()
                return str(value)
            return value
        except (ValueError, TypeError):
            return value

    def export_template(self, selected_types: List[str], options: Optional[Dict[str, Any]] = None) -> ExportResult:
        """
        生成导入模板（只包含表头，不包含数据）
        
        Args:
            selected_types: 选定的对象类型列表
            options: 导出选项
        
        Returns:
            ExportResult: 导出结果
        """
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        from openpyxl.comments import Comment
        from meta.core.models import registry

        options = options or {}
        include_operation_mode = options.get("include_operation_mode", True)

        type_order = get_type_order()
        type_order = self._ensure_association_types_in_order(type_order)
        
        # 检查selected_types是否在registry中注册
        from meta.core.models import registry
        valid_types = [t for t in selected_types if registry.get(t)]
        
        # 如果selected_types不在type_order中，直接使用valid_types
        ordered_types = [t for t in type_order if t in valid_types]
        if not ordered_types:
            # 如果没有在type_order中，直接使用valid_types
            ordered_types = valid_types
        
        if not ordered_types:
            return ExportResult(success=False, errors=["No valid object types selected"])

        # 检查是否有任何对象支持 CUD 操作
        has_cud = any(_has_cud_actions(registry.get(ot)) for ot in ordered_types if registry.get(ot))
        
        # 检查是否所有对象都是只读的
        all_readonly = all(not _has_cud_actions(registry.get(ot)) for ot in ordered_types if registry.get(ot))
        
        wb = Workbook()
        ws_meta = wb.active
        ws_meta.title = "说明"
        
        ds = ExcelDesignSystem
        
        ws_meta.cell(row=1, column=1, value="导入模板说明").font = Font(bold=True, size=14, color=ds.PRIMARY_COLOR)
        ws_meta.row_dimensions[1].height = 24
        ws_meta.cell(row=2, column=1, value="生成时间").font = ds.LABEL_FONT
        ws_meta.cell(row=2, column=2, value=datetime.now().strftime("%Y-%m-%d %H:%M:%S")).font = ds.VALUE_FONT
        ws_meta.cell(row=3, column=1, value="包含对象").font = ds.LABEL_FONT
        included_names = [registry.get(ot).name for ot in ordered_types if registry.get(ot)]
        ws_meta.cell(row=3, column=2, value=", ".join(included_names)).font = ds.VALUE_FONT
        
        # 只有在有 CUD 操作时才显示操作说明部分
        if has_cud:
            ws_meta.cell(row=5, column=1, value="操作说明").font = ds.SECTION_FONT
            ws_meta.cell(row=5, column=1).fill = ds.SECTION_FILL
            ws_meta.cell(row=6, column=1, value="操作模式").font = ds.LABEL_FONT
            ws_meta.cell(row=6, column=2, value="create - 新增/update - 更新/delete - 删除，留空默认为update").font = ds.VALUE_FONT
            ws_meta.cell(row=7, column=1, value="单元格颜色").font = ds.LABEL_FONT
            ws_meta.cell(row=7, column=2, value="不同颜色背景表示不同的字段控制：").font = ds.VALUE_FONT
            
            ws_meta.cell(row=8, column=1, value="  灰色").font = ds.LABEL_FONT
            ws_meta.cell(row=8, column=1).fill = ds.READONLY_FILL
            ws_meta.cell(row=8, column=2, value="只读字段，不可编辑").font = ds.VALUE_FONT
            
            ws_meta.cell(row=9, column=1, value="  浅绿色").font = ds.LABEL_FONT
            ws_meta.cell(row=9, column=1).fill = ds.BUSINESS_KEY_FILL
            ws_meta.cell(row=9, column=2, value="业务关键字，新增必填，编辑时只读").font = ds.VALUE_FONT
            
            ws_meta.cell(row=10, column=1, value="  浅黄色").font = ds.LABEL_FONT
            ws_meta.cell(row=10, column=1).fill = ds.REQUIRED_FILL
            ws_meta.cell(row=10, column=2, value="新增时必填字段").font = ds.VALUE_FONT
            
            ws_meta.cell(row=11, column=1, value="业务关键字").font = ds.LABEL_FONT
            ws_meta.cell(row=11, column=2, value="编码字段为业务关键字，用于唯一标识记录。新增时必填，编辑时只读。").font = ds.VALUE_FONT
            ws_meta.cell(row=12, column=1, value="父对象编码").font = ds.LABEL_FONT
            ws_meta.cell(row=12, column=2, value="用于关联父对象。新增时必填，编辑时可切换到其他父对象。").font = ds.VALUE_FONT
            ws_meta.cell(row=13, column=1, value="删除操作").font = ds.LABEL_FONT
            ws_meta.cell(row=13, column=2, value="设置操作模式为'delete'，系统将根据业务键查找并删除记录").font = ds.VALUE_FONT
            ws_meta.cell(row=14, column=1, value="新增操作").font = ds.LABEL_FONT
            ws_meta.cell(row=14, column=2, value="在新增行中填写数据，操作模式设为'create'。业务关键字和父对象编码必填。").font = ds.VALUE_FONT
            ws_meta.cell(row=15, column=1, value="冲突处理策略").font = ds.LABEL_FONT
            ws_meta.cell(row=15, column=2, value="在导入界面选择：有则更新（存在则更新，不存在则新增）或跳过冲突（存在则跳过）。").font = ds.VALUE_FONT
            ws_meta.cell(row=16, column=1, value="注意事项").font = ds.LABEL_FONT
            ws_meta.cell(row=16, column=2, value="请勿修改灰色背景单元格的值，否则导入时会忽略这些字段").font = ds.VALUE_FONT
            
            for row in range(1, 17):
                for col in range(1, 3):
                    ws_meta.cell(row=row, column=col).border = ds.THIN_BORDER
        elif all_readonly:
            # 所有对象都是只读的，显示只读说明
            ws_meta.cell(row=5, column=1, value="说明").font = ds.SECTION_FONT
            ws_meta.cell(row=5, column=1).fill = ds.SECTION_FILL
            ws_meta.cell(row=6, column=1, value="导出说明").font = ds.LABEL_FONT
            ws_meta.cell(row=6, column=2, value="当前导出的对象为只读数据，不支持导入修改。").font = ds.VALUE_FONT
            ws_meta.cell(row=7, column=1, value="使用说明").font = ds.LABEL_FONT
            ws_meta.cell(row=7, column=2, value="此模板仅用于查看和导出数据，如需修改请通过系统界面操作。").font = ds.VALUE_FONT
            
            for row in range(1, 8):
                for col in range(1, 3):
                    ws_meta.cell(row=row, column=col).border = ds.THIN_BORDER
        else:
            # 混合模式（部分对象支持 CUD）
            ws_meta.cell(row=5, column=1, value="说明").font = ds.SECTION_FONT
            ws_meta.cell(row=5, column=1).fill = ds.SECTION_FILL
            ws_meta.cell(row=6, column=1, value="注意").font = ds.LABEL_FONT
            ws_meta.cell(row=6, column=2, value="部分对象不支持导入修改，仅支持导出。").font = ds.VALUE_FONT
            
            for row in range(1, 7):
                for col in range(1, 3):
                    ws_meta.cell(row=row, column=col).border = ds.THIN_BORDER
        
        ws_meta.column_dimensions['A'].width = 18
        ws_meta.column_dimensions['B'].width = 60
        
        header_fill = ds.HEADER_FILL
        header_font = ds.HEADER_FONT
        
        sheets_info = []
        
        for ot in ordered_types:
            obj = registry.get(ot)
            if obj is None:
                continue
            
            if not obj.import_export.export_enabled:
                continue
            
            ws = wb.create_sheet(title=obj.name)
            
            headers, editable_columns, readonly_columns, parent_key_columns, create_required_columns, header_comments, header_to_field, enum_value_maps, bo_display_fields = self._get_export_headers_with_editable(obj, options)
            
            bo_display_maps = {}
            
            obj_has_cud = _has_cud_actions(obj)
            
            if obj_has_cud:
                headers.insert(0, "操作模式")
                header_comments.insert(0, "create - 新增/update - 更新/delete - 删除，留空默认为update")
            
            for col_idx, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_idx, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = ds.TEXT_CENTER
                cell.border = ds.THIN_BORDER
                if col_idx - 1 < len(header_comments) and header_comments[col_idx - 1]:
                    cell.comment = Comment(_sanitize_xml_string(header_comments[col_idx - 1]), "系统")
            
            if obj_has_cud:
                op_mode_validation = DataValidation(
                    type="list",
                    formula1='"create - 新增,update - 更新,delete - 删除"',
                    allow_blank=True
                )
                op_mode_validation.error = "请从下拉列表中选择操作模式"
                op_mode_validation.errorTitle = "无效输入"
                ws.add_data_validation(op_mode_validation)
            
            col_offset = 1 if include_operation_mode else 0
            enum_validations = {}
            for col_idx, header in enumerate(headers[col_offset:], 1 + col_offset):
                actual_col_idx = col_idx - 1 - col_offset
                field_id = header_to_field.get(header, header)
                
                if field_id in enum_value_maps:
                    enum_map = enum_value_maps[field_id]
                    display_values = [f"{k} - {v}" for k, v in enum_map.items()]
                    if display_values:
                        col_letter = get_column_letter(col_idx)
                        dv = DataValidation(
                            type="list",
                            formula1='"' + ','.join(display_values) + '"',
                            allow_blank=True
                        )
                        dv.error = f"请从下拉列表中选择有效的{header}"
                        dv.errorTitle = "无效输入"
                        dv.prompt = f"请选择{header} (Key - Label)"
                        dv.promptTitle = header
                        ws.add_data_validation(dv)
                        enum_validations[actual_col_idx] = (dv, display_values, list(enum_map.keys()))
            
            empty_rows_count = options.get("empty_rows_for_new", 5)
            for row_idx in range(2, 2 + empty_rows_count):
                if obj_has_cud:
                    op_cell = ws.cell(row=row_idx, column=1, value="create - 新增")
                    op_cell.fill = ds.BUSINESS_KEY_FILL
                    op_cell.border = ds.THIN_BORDER
                    op_cell.alignment = ds.TEXT_CENTER
                    op_mode_validation.add(op_cell)
                    col_offset = 1
                else:
                    col_offset = 0
                
                for col_idx, header in enumerate(headers[col_offset:], 1 + col_offset):
                    cell = ws.cell(row=row_idx, column=col_idx, value="")
                    cell.border = ds.THIN_BORDER
                    
                    actual_col_idx = col_idx - 1 - col_offset
                    if actual_col_idx in enum_validations:
                        dv, display_values, keys = enum_validations[actual_col_idx]
                        dv.add(cell)
                    
                    if actual_col_idx in parent_key_columns:
                        cell.fill = ds.BUSINESS_KEY_FILL
                    elif actual_col_idx in create_required_columns:
                        cell.fill = ds.REQUIRED_FILL
                    elif actual_col_idx in readonly_columns:
                        cell.fill = ds.READONLY_FILL
            
            for col_idx, header in enumerate(headers, 1):
                column_letter = get_column_letter(col_idx)
                max_length = len(str(header))
                adjusted_width = min(max(max_length + 2, 10), 50)
                ws.column_dimensions[column_letter].width = adjusted_width
            
            sheets_info.append({
                "name": obj.name,
                "row_count": 0
            })
        
        file_name = f"import_template_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        export_dir = os.path.join(os.getcwd(), "exports")
        os.makedirs(export_dir, exist_ok=True)
        file_path = os.path.join(export_dir, file_name)
        
        wb.save(file_path)
        
        return ExportResult(
            success=True,
            file_path=file_path,
            sheets=sheets_info,
            total_rows=0
        )

    def export_selected_types(self, selected_types: List[str], filters: Optional[Dict[str, Any]] = None,
                              options: Optional[Dict[str, Any]] = None, sort_by: str = None, 
                              sort_order: str = 'asc',
                              progress_callback: Optional[callable] = None,
                              page: int = None, page_size: int = None) -> ExportResult:
        """
        导出选定的对象类型
        
        Args:
            selected_types: 选定的对象类型列表
            filters: 筛选条件
            options: 导出选项
            sort_by: 排序字段
            sort_order: 排序方向 (asc/desc)
            progress_callback: 进度回调函数，接收 dict:
                {progress, current_type, current_type_name, total_types, current_index, message}
            page: 页码（分页导出时使用）
            page_size: 每页数量（分页导出时使用）
        
        Returns:
            ExportResult: 导出结果
        """
        from openpyxl.styles import PatternFill, Font, Alignment, Protection, Border, Side
        from openpyxl.worksheet.protection import SheetProtection
        from openpyxl.comments import Comment
        from meta.core.models import registry

        options = options or {}
        include_readonly = options.get("include_readonly", True)
        include_operation_mode = options.get("include_operation_mode", True)
        protect_sheet = options.get("protect_sheet", False)
        include_annotations = options.get("include_child_objects",
                                           options.get("include_annotations", True))

        type_order = get_type_order()
        type_order = self._ensure_association_types_in_order(type_order)
        
        # 检查selected_types是否在registry中注册
        from meta.core.models import registry
        valid_types = [t for t in selected_types if registry.get(t)]
        
        # 如果selected_types不在type_order中，直接使用valid_types
        ordered_types = [t for t in type_order if t in valid_types]
        if not ordered_types:
            # 如果没有在type_order中，直接使用valid_types
            ordered_types = valid_types
        
        if not ordered_types:
            return ExportResult(success=False, errors=["No valid object types selected"])

        wb = Workbook()
        ws_meta = wb.active
        ws_meta.title = "说明"
        
        ds = ExcelDesignSystem
        
        ws_meta.cell(row=1, column=1, value="导出信息").font = Font(bold=True, size=11, color=ds.PRIMARY_COLOR)
        ws_meta.row_dimensions[1].height = 20
        
        product_code, version_code = self._get_product_version_codes(filters)
        product_name, version_name = self._get_product_version_info(filters)
        
        try:
            from flask import request as flask_request
            export_user = flask_request.headers.get('X-User-Name', '') if flask_request else ''
        except Exception:
            export_user = ''
        
        ws_meta.cell(row=2, column=1, value="导出时间").font = ds.LABEL_FONT
        ws_meta.cell(row=2, column=2, value=datetime.now().strftime("%Y-%m-%d %H:%M:%S")).font = ds.VALUE_FONT
        ws_meta.cell(row=3, column=1, value="导出用户").font = ds.LABEL_FONT
        ws_meta.cell(row=3, column=2, value=export_user).font = ds.VALUE_FONT
        ws_meta.cell(row=4, column=1, value="导出范围").font = ds.LABEL_FONT
        ws_meta.cell(row=4, column=2, value="选定对象导出").font = ds.VALUE_FONT
        ws_meta.cell(row=5, column=1, value="包含对象").font = ds.LABEL_FONT
        included_names = [registry.get(ot).name for ot in ordered_types if registry.get(ot)]
        ws_meta.cell(row=5, column=2, value=", ".join(included_names)).font = ds.VALUE_FONT
        
        ws_meta.cell(row=7, column=1, value="上下文信息").font = ds.SECTION_FONT
        ws_meta.cell(row=7, column=1).fill = ds.SECTION_FILL
        ws_meta.cell(row=8, column=1, value="产品编码").font = ds.LABEL_FONT
        ws_meta.cell(row=8, column=2, value=product_code).font = ds.VALUE_FONT
        ws_meta.cell(row=9, column=1, value="产品名称").font = ds.LABEL_FONT
        ws_meta.cell(row=9, column=2, value=product_name).font = ds.VALUE_FONT
        ws_meta.cell(row=10, column=1, value="版本编码").font = ds.LABEL_FONT
        ws_meta.cell(row=10, column=2, value=version_code).font = ds.VALUE_FONT
        ws_meta.cell(row=11, column=1, value="版本名称").font = ds.LABEL_FONT
        ws_meta.cell(row=11, column=2, value=version_name).font = ds.VALUE_FONT
        ws_meta.cell(row=12, column=1, value="版本ID").font = ds.LABEL_FONT
        ws_meta.cell(row=12, column=2, value=str(filters.get('version_id', '')) if filters else '').font = ds.VALUE_FONT
        
        section_font = Font(bold=True, size=11, color=ds.PRIMARY_COLOR)
        
        # 检查是否有任何对象支持 CUD 操作
        has_cud = any(_has_cud_actions(registry.get(ot)) for ot in ordered_types if registry.get(ot))
        
        # 检查是否所有对象都是只读的
        all_readonly = all(not _has_cud_actions(registry.get(ot)) for ot in ordered_types if registry.get(ot))
        
        if has_cud:
            ws_meta.cell(row=14, column=1, value="操作说明").font = section_font
            ws_meta.cell(row=14, column=1).fill = ds.SECTION_FILL
            ws_meta.cell(row=15, column=1, value="操作模式").font = ds.LABEL_FONT
            ws_meta.cell(row=15, column=2, value="create - 新增/update - 更新/delete - 删除，留空默认为update").font = ds.VALUE_FONT
            ws_meta.cell(row=16, column=1, value="单元格颜色").font = ds.LABEL_FONT
            ws_meta.cell(row=16, column=2, value="不同颜色背景表示不同的字段控制：").font = ds.VALUE_FONT
            
            # 颜色示例行
            ws_meta.cell(row=17, column=1, value="  灰色").font = ds.LABEL_FONT
            ws_meta.cell(row=17, column=1).fill = ds.READONLY_FILL
            ws_meta.cell(row=17, column=2, value="只读字段，不可编辑").font = ds.VALUE_FONT
            
            ws_meta.cell(row=18, column=1, value="  浅绿色").font = ds.LABEL_FONT
            ws_meta.cell(row=18, column=1).fill = ds.BUSINESS_KEY_FILL
            ws_meta.cell(row=18, column=2, value="父对象编码，新增必填，编辑时可切换").font = ds.VALUE_FONT
            
            ws_meta.cell(row=19, column=1, value="  浅黄色").font = ds.LABEL_FONT
            ws_meta.cell(row=19, column=1).fill = ds.REQUIRED_FILL
            ws_meta.cell(row=19, column=2, value="业务关键字，新增必填，编辑时只读").font = ds.VALUE_FONT
            
            ws_meta.cell(row=20, column=1, value="业务关键字").font = ds.LABEL_FONT
            ws_meta.cell(row=20, column=2, value="编码字段为业务关键字，用于唯一标识记录。新增时必填，编辑时只读。").font = ds.VALUE_FONT
            ws_meta.cell(row=21, column=1, value="父对象编码").font = ds.LABEL_FONT
            ws_meta.cell(row=21, column=2, value="用于关联父对象。新增时必填，编辑时可切换到其他父对象。").font = ds.VALUE_FONT
            ws_meta.cell(row=22, column=1, value="删除操作").font = ds.LABEL_FONT
            ws_meta.cell(row=22, column=2, value="设置操作模式为'delete'，系统将根据业务键查找并删除记录").font = ds.VALUE_FONT
            ws_meta.cell(row=23, column=1, value="新增操作").font = ds.LABEL_FONT
            ws_meta.cell(row=23, column=2, value="在新增行中填写数据，操作模式设为'create'。业务关键字和父对象编码必填。").font = ds.VALUE_FONT
            ws_meta.cell(row=24, column=1, value="冲突处理策略").font = ds.LABEL_FONT
            ws_meta.cell(row=24, column=2, value="在导入界面选择：有则更新（存在则更新，不存在则新增）或跳过冲突（存在则跳过）。").font = ds.VALUE_FONT
            ws_meta.cell(row=25, column=1, value="子对象Sheet").font = ds.LABEL_FONT
            ws_meta.cell(row=25, column=2, value="子对象Sheet（如备注信息）支持创建/更新/删除操作，通过操作模式列控制。灰色背景字段为只读字段。").font = ds.VALUE_FONT
            ws_meta.cell(row=26, column=1, value="注意事项").font = ds.LABEL_FONT
            ws_meta.cell(row=26, column=2, value="请勿修改灰色背景单元格的值，否则导入时会忽略这些字段").font = ds.VALUE_FONT

            for row in range(1, 27):
                for col in range(1, 3):
                    ws_meta.cell(row=row, column=col).border = ds.THIN_BORDER
        elif all_readonly:
            ws_meta.cell(row=14, column=1, value="说明").font = section_font
            ws_meta.cell(row=14, column=1).fill = ds.SECTION_FILL
            ws_meta.cell(row=15, column=1, value="导出说明").font = ds.LABEL_FONT
            ws_meta.cell(row=15, column=2, value="当前导出的对象为只读数据，不支持导入修改。").font = ds.VALUE_FONT
            ws_meta.cell(row=16, column=1, value="使用说明").font = ds.LABEL_FONT
            ws_meta.cell(row=16, column=2, value="此模板仅用于查看和导出数据，如需修改请通过系统界面操作。").font = ds.VALUE_FONT
            
            for row in range(1, 17):
                for col in range(1, 3):
                    ws_meta.cell(row=row, column=col).border = ds.THIN_BORDER
        else:
            ws_meta.cell(row=14, column=1, value="注意").font = section_font
            ws_meta.cell(row=14, column=1).fill = ds.SECTION_FILL
            ws_meta.cell(row=15, column=1, value="注意").font = ds.LABEL_FONT
            ws_meta.cell(row=15, column=2, value="部分对象不支持导入修改，仅支持导出。").font = ds.VALUE_FONT
            
            for row in range(1, 16):
                for col in range(1, 3):
                    ws_meta.cell(row=row, column=col).border = ds.THIN_BORDER
        
        ws_meta.column_dimensions['A'].width = 18
        ws_meta.column_dimensions['B'].width = 60
        
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        
        sheets_info = []
        total_rows = 0
        
        total_types = len(ordered_types)
        if progress_callback:
            progress_callback({
                'progress': 0,
                'current_type': '',
                'current_type_name': '',
                'total_types': total_types,
                'current_index': 0,
                'message': '开始导出，共 {0} 种对象类型'.format(total_types)
            })
        
        for i, ot in enumerate(ordered_types):
            obj = registry.get(ot)
            if obj is None:
                continue
            
            if not obj.import_export.export_enabled:
                continue
            
            type_name = obj.name or ot
            current_index = i + 1
            if progress_callback:
                progress_callback({
                    'progress': int((i / total_types) * 100),
                    'current_type': ot,
                    'current_type_name': type_name,
                    'total_types': total_types,
                    'current_index': current_index,
                    'message': '正在导出: {0} ({1}/{2})'.format(type_name, current_index, total_types)
                })
            
            sheet_data = self._query_with_hierarchy(ot, filters, options, sort_by=sort_by, sort_order=sort_order, page=page, page_size=page_size)
            
            ws = wb.create_sheet(title=obj.name)
            
            headers, editable_columns, readonly_columns, parent_key_columns, create_required_columns, header_comments, header_to_field, enum_value_maps, bo_display_fields = self._get_export_headers_with_editable(obj, options)
            
            bo_display_maps = {}
            if bo_display_fields and sheet_data:
                for field_id, vh_info in bo_display_fields.items():
                    record_ids = list(set(
                        r.get(field_id) for r in sheet_data
                        if r.get(field_id) is not None
                    ))
                    if record_ids:
                        from meta import get_meta_object
                        from meta.core.bo_engine import BOEngine
                        try:
                            target_meta = get_meta_object(vh_info['target_bo'])
                            if target_meta:
                                engine = BOEngine(target_meta)
                                display_map = {}
                                for rid in record_ids:
                                    try:
                                        rec = engine.get_record(rid)
                                        if rec:
                                            display_map[rid] = str(rec.get(vh_info['display_field'], ''))
                                    except Exception:
                                        pass
                                if display_map:
                                    bo_display_maps[field_id] = display_map
                        except Exception:
                            pass
            
            # 根据 include_operation_mode 选项决定是否包含操作模式列
            if include_operation_mode:
                headers.insert(0, "操作模式")
                header_comments.insert(0, "新增/更新/删除/跳过，留空默认为更新")
            
            for col_idx, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_idx, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = ds.THIN_BORDER
                if col_idx - 1 < len(header_comments) and header_comments[col_idx - 1]:
                    cell.comment = Comment(_sanitize_xml_string(header_comments[col_idx - 1]), "系统")
            
            if include_operation_mode:
                op_mode_validation = DataValidation(
                    type="list",
                    formula1='"create - 新增,update - 更新,delete - 删除"',
                    allow_blank=True
                )
                op_mode_validation.error = "请从下拉列表中选择操作模式"
                op_mode_validation.errorTitle = "无效输入"
                ws.add_data_validation(op_mode_validation)
            
            col_offset = 1 if include_operation_mode else 0

            sheet_row_count = len(sheet_data)
            progress_interval = max(100, sheet_row_count // 10) if sheet_row_count > 0 else 100

            for row_idx, record in enumerate(sheet_data, 2):
                if sheet_row_count > 500 and (row_idx - 2) % progress_interval == 0:
                    progress = (row_idx - 2) * 100 // sheet_row_count
                    print(f"[Export] 正在导出 {obj.name}，进度 {progress}% ({row_idx - 2}/{sheet_row_count})")

                if include_operation_mode:
                    op_cell = ws.cell(row=row_idx, column=1, value="update - 更新")
                    op_cell.fill = ds.READONLY_FILL
                    op_cell.border = ds.THIN_BORDER
                    if protect_sheet:
                        op_cell.protection = Protection(locked=False)
                    op_mode_validation.add(op_cell)

                for col_idx, header in enumerate(headers[col_offset:], 1 + col_offset):
                    field_id = header_to_field.get(header, header)
                    value = record.get(field_id) or record.get(header)

                    if field_id in enum_value_maps and value is not None:
                        label = enum_value_maps[field_id].get(value, value)
                        value = f"{value} - {label}" if label != value else value
                    
                    if field_id in bo_display_maps and value is not None:
                        display_name = bo_display_maps[field_id].get(value)
                        if display_name:
                            value = f"{display_name} ({value})"

                    cell = ws.cell(row=row_idx, column=col_idx, value=_safe_cell_value(value))
                    cell.border = ds.THIN_BORDER

                    actual_col_idx = col_idx - 1 - col_offset
                    if actual_col_idx in parent_key_columns:
                        cell.fill = ds.BUSINESS_KEY_FILL
                        if protect_sheet:
                            cell.protection = Protection(locked=False)
                    elif actual_col_idx in create_required_columns:
                        cell.fill = ds.REQUIRED_FILL
                        if protect_sheet:
                            cell.protection = Protection(locked=False)
                    elif actual_col_idx in readonly_columns:
                        cell.fill = ds.READONLY_FILL
                        if protect_sheet:
                            cell.protection = Protection(locked=True)
                    elif actual_col_idx in editable_columns:
                        if protect_sheet:
                            cell.protection = Protection(locked=False)

            print(f"[Export] {obj.name} 数据写入完成，共 {sheet_row_count} 行")
            
            export_enum_validations = {}
            for col_idx, header in enumerate(headers[col_offset:] if include_operation_mode else headers, 1 + col_offset if include_operation_mode else 1):
                actual_col_idx = col_idx - 1 - col_offset if include_operation_mode else col_idx - 1
                field_id = header_to_field.get(header, header)
                
                if field_id in enum_value_maps:
                    enum_map = enum_value_maps[field_id]
                    display_values = [f"{k} - {v}" for k, v in enum_map.items()]
                    if display_values:
                        dv = DataValidation(
                            type="list",
                            formula1='"' + ','.join(display_values) + '"',
                            allow_blank=True
                        )
                        dv.error = f"请从下拉列表中选择有效的{header}"
                        dv.errorTitle = "无效输入"
                        dv.prompt = f"请选择{header} (Key - Label)"
                        dv.promptTitle = header
                        ws.add_data_validation(dv)
                        export_enum_validations[col_idx] = dv
            
            for row_idx in range(2, len(sheet_data) + 2):
                for col_idx in export_enum_validations:
                    cell = ws.cell(row=row_idx, column=col_idx)
                    export_enum_validations[col_idx].add(cell)
            
            for col_idx, header in enumerate(headers, 1):
                column_letter = get_column_letter(col_idx)
                max_length = len(str(header))
                for row in range(2, len(sheet_data) + 2):
                    cell = ws.cell(row=row, column=col_idx)
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                adjusted_width = min(max(max_length + 2, 10), 50)
                ws.column_dimensions[column_letter].width = adjusted_width
            
            if protect_sheet:
                ws.protection = SheetProtection(
                    sheet=True,
                    autoFilter=False,
                    deleteColumns=False,
                    deleteRows=False,
                    formatCells=True,
                    formatColumns=True,
                    formatRows=True,
                    insertColumns=False,
                    insertRows=True,
                    sort=True,
                    objects=False,
                    scenarios=False,
                    pivotTables=False
                )
            
            sheets_info.append({
                "name": obj.name,
                "object_type": ot,
                "row_count": len(sheet_data) if sheet_data else 0
            })
            total_rows += len(sheet_data) if sheet_data else 0
        
        if progress_callback:
            progress_callback({
                'progress': 100,
                'current_type': '',
                'current_type_name': '',
                'total_types': total_types,
                'current_index': total_types,
                'message': '导出完成'
            })
        
        if include_annotations:
            child_parent_map = self._collect_child_object_types(ordered_types)
            if child_parent_map:
                total_child_types = len(child_parent_map)
                for idx, (child_type_name, parent_list) in enumerate(child_parent_map.items()):
                    if progress_callback:
                        try:
                            child_reg_meta = registry.get(child_type_name)
                            child_display = child_reg_meta.name if child_reg_meta else child_type_name
                        except Exception:
                            child_display = child_type_name
                        progress_callback({
                            'progress': 95 + int((idx / total_child_types) * 5),
                            'current_type': child_type_name,
                            'current_type_name': child_display,
                            'total_types': total_child_types,
                            'current_index': idx + 1,
                            'message': '正在导出子对象: {0}'.format(child_display)
                        })

                    try:
                        child_data = self._query_child_object(child_type_name, parent_list, filters)
                        child_meta = registry.get(child_type_name)
                        if child_meta:
                            self._write_child_sheet(wb, child_type_name, child_meta, child_data or [], sheets_info, options)
                            total_rows += len(child_data) if child_data else 0
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(
                            f"[Export] 子对象 {child_type_name} 导出失败: {e}"
                        )
        
        output_dir = os.path.join(os.getcwd(), "exports")
        os.makedirs(output_dir, exist_ok=True)
        
        product_name, version_name = self._get_product_version_info(filters)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if product_name and version_name:
            safe_product = "".join(c if c.isalnum() or c in '_-' else '_' for c in product_name)
            safe_version = "".join(c if c.isalnum() or c in '_-' else '_' for c in version_name)
            file_name = "{0}_{1}_{2}.xlsx".format(safe_product, safe_version, timestamp)
        elif version_name:
            safe_version = "".join(c if c.isalnum() or c in '_-' else '_' for c in version_name)
            file_name = "{0}_{1}.xlsx".format(safe_version, timestamp)
        else:
            file_name = "{0}.xlsx".format(timestamp)
        file_path = os.path.join(output_dir, file_name)
        
        wb.save(file_path)
        wb.close()
        
        return ExportResult(
            success=True,
            file_path=file_path,
            sheets=sheets_info,
            total_rows=total_rows
        )

    def export_cascade(self, object_type: str, filters: Optional[Dict[str, Any]] = None,
                       options: Optional[Dict[str, Any]] = None, sort_by: str = None, 
                       sort_order: str = 'asc',
                       page: int = None, page_size: int = None) -> ExportResult:
        """
        级联导出：导出指定对象及其所有子级对象
        
        参考SAP SuccessFactors导入模板方案：
        1. 单元格级别保护：只读字段使用灰色背景+锁定
        2. 操作模式列：使用下拉列表数据验证
        3. 工作表保护：允许编辑可编辑单元格
        
        Args:
            object_type: 起始对象类型
            filters: 筛选条件
            options: 导出选项
                - include_hierarchy_path: 是否包含层级路径列
                - include_hierarchy_ids: 是否包含层级ID列
                - include_metadata_sheet: 是否包含元数据Sheet
                - include_readonly: 是否标记只读字段
                - include_operation_mode: 是否包含操作模式列
                - protect_sheet: 是否保护工作表
            sort_by: 排序字段
            sort_order: 排序方向 (asc/desc)
            page: 页码（分页导出时使用）
            page_size: 每页数量（分页导出时使用）
        
        Returns:
            ExportResult: 导出结果
        """
        from openpyxl.styles import PatternFill, Font, Alignment, Protection, Border, Side
        from openpyxl.worksheet.protection import SheetProtection
        from openpyxl.comments import Comment

        options = options or {}
        include_readonly = options.get("include_readonly", True)
        include_operation_mode = options.get("include_operation_mode", True)
        protect_sheet = options.get("protect_sheet", False)

        ds = ExcelDesignSystem

        meta_obj = registry.get(object_type)
        if meta_obj is None:
            return ExportResult(success=False, errors=["Meta object not found: {0}".format(object_type)])
        
        if meta_obj.import_export and not meta_obj.import_export.cascade_export:
            return self.export_selected_types([object_type], filters, options, page=page, page_size=page_size)

        object_types = self._get_cascade_object_types(object_type)
        ordered_types = self._sort_by_hierarchy(object_types)
        
        wb = Workbook()
        ws_meta = wb.active
        ws_meta.title = "说明"
        
        meta_fill = PatternFill(start_color="F8F9FA", end_color="F8F9FA", fill_type="solid")
        section_font = Font(bold=True, size=11, color="1565C0")
        
        ws_meta.cell(row=1, column=1, value="导出信息").font = Font(bold=True, size=14, color="1565C0")
        ws_meta.row_dimensions[1].height = 25
        ws_meta.cell(row=2, column=1, value="导出时间").font = ds.LABEL_FONT
        ws_meta.cell(row=2, column=2, value=datetime.now().strftime("%Y-%m-%d %H:%M:%S")).font = ds.VALUE_FONT
        ws_meta.cell(row=3, column=1, value="导出范围").font = ds.LABEL_FONT
        ws_meta.cell(row=3, column=2, value="级联导出").font = ds.VALUE_FONT
        ws_meta.cell(row=4, column=1, value="起始对象").font = ds.LABEL_FONT
        ws_meta.cell(row=4, column=2, value=meta_obj.name).font = ds.VALUE_FONT
        ws_meta.cell(row=5, column=1, value="包含对象").font = ds.LABEL_FONT
        exclude_object_types = {'version', 'product'}
        included_objects = [registry.get(ot).name for ot in ordered_types 
                           if registry.get(ot) and ot not in exclude_object_types]
        ws_meta.cell(row=5, column=2, value=", ".join(included_objects)).font = ds.VALUE_FONT
        
        ws_meta.cell(row=7, column=1, value="操作说明").font = section_font
        ws_meta.cell(row=7, column=1).fill = ds.SECTION_FILL
        ws_meta.cell(row=8, column=1, value="操作模式").font = ds.LABEL_FONT
        ws_meta.cell(row=8, column=2, value="create - 新增/update - 更新/delete - 删除，留空默认为update").font = ds.VALUE_FONT
        ws_meta.cell(row=9, column=1, value="单元格颜色").font = ds.LABEL_FONT
        ws_meta.cell(row=9, column=2, value="不同颜色背景表示不同的字段控制：").font = ds.VALUE_FONT
        
        # 颜色示例行
        ws_meta.cell(row=10, column=1, value="  灰色").font = ds.LABEL_FONT
        ws_meta.cell(row=10, column=1).fill = ds.READONLY_FILL
        ws_meta.cell(row=10, column=2, value="只读字段，不可编辑").font = ds.VALUE_FONT
        
        ws_meta.cell(row=11, column=1, value="  浅绿色").font = ds.LABEL_FONT
        ws_meta.cell(row=11, column=1).fill = ds.BUSINESS_KEY_FILL
        ws_meta.cell(row=11, column=2, value="父对象编码，新增必填，编辑时可切换").font = ds.VALUE_FONT
        
        ws_meta.cell(row=12, column=1, value="  浅黄色").font = ds.LABEL_FONT
        ws_meta.cell(row=12, column=1).fill = ds.REQUIRED_FILL
        ws_meta.cell(row=12, column=2, value="业务关键字，新增必填，编辑时只读").font = ds.VALUE_FONT
        
        ws_meta.cell(row=13, column=1, value="业务关键字").font = ds.LABEL_FONT
        ws_meta.cell(row=13, column=2, value="编码字段为业务关键字，用于唯一标识记录。新增时必填，编辑时只读。").font = ds.VALUE_FONT
        ws_meta.cell(row=14, column=1, value="父对象编码").font = ds.LABEL_FONT
        ws_meta.cell(row=14, column=2, value="用于关联父对象。新增时必填，编辑时可切换到其他父对象。").font = ds.VALUE_FONT
        ws_meta.cell(row=15, column=1, value="删除操作").font = ds.LABEL_FONT
        ws_meta.cell(row=15, column=2, value="设置操作模式为'delete'，系统将根据业务键查找并删除记录").font = ds.VALUE_FONT
        ws_meta.cell(row=16, column=1, value="新增操作").font = ds.LABEL_FONT
        ws_meta.cell(row=16, column=2, value="在新增行中填写数据，操作模式设为'create'。业务关键字和父对象编码必填。").font = ds.VALUE_FONT
        ws_meta.cell(row=17, column=1, value="冲突处理策略").font = ds.LABEL_FONT
        ws_meta.cell(row=17, column=2, value="在导入界面选择：有则更新（存在则更新，不存在则新增）或跳过冲突（存在则跳过）。").font = ds.VALUE_FONT
        ws_meta.cell(row=18, column=1, value="注意事项").font = ds.LABEL_FONT
        ws_meta.cell(row=18, column=2, value="请勿修改灰色背景单元格的值，否则导入时会忽略这些字段。级联导出不含子对象Sheet").font = ds.VALUE_FONT

        for row in range(1, 19):
            for col in range(1, 3):
                ws_meta.cell(row=row, column=col).border = ds.THIN_BORDER
        
        ws_meta.column_dimensions['A'].width = 18
        ws_meta.column_dimensions['B'].width = 60
        
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        light_blue_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
        
        sheets_info = []
        total_rows = 0
        
        for ot in ordered_types:
            if ot in exclude_object_types:
                continue
            
            obj = registry.get(ot)
            if obj is None:
                continue
            
            if not obj.import_export.export_enabled:
                continue
            
            sheet_data = self._query_with_hierarchy(ot, filters, options, sort_by=sort_by, sort_order=sort_order, page=page, page_size=page_size)
            
            ws = wb.create_sheet(title=obj.name)
            
            headers, editable_columns, readonly_columns, parent_key_columns, create_required_columns, header_comments, header_to_field, enum_value_maps, bo_display_fields = self._get_export_headers_with_editable(obj, options)
            
            bo_display_maps = {}
            if bo_display_fields and sheet_data:
                for field_id, vh_info in bo_display_fields.items():
                    record_ids = list(set(
                        r.get(field_id) for r in sheet_data
                        if r.get(field_id) is not None
                    ))
                    if record_ids:
                        from meta import get_meta_object
                        from meta.core.bo_engine import BOEngine
                        try:
                            target_meta = get_meta_object(vh_info['target_bo'])
                            if target_meta:
                                engine = BOEngine(target_meta)
                                display_map = {}
                                for rid in record_ids:
                                    try:
                                        rec = engine.get_record(rid)
                                        if rec:
                                            display_map[rid] = str(rec.get(vh_info['display_field'], ''))
                                    except Exception:
                                        pass
                                if display_map:
                                    bo_display_maps[field_id] = display_map
                        except Exception:
                            pass
            
            if include_operation_mode:
                headers.insert(0, "操作模式")
                header_comments.insert(0, "新增/更新/删除/跳过，留空默认为更新")
            
            for col_idx, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_idx, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = ds.THIN_BORDER
                if col_idx - 1 < len(header_comments) and header_comments[col_idx - 1]:
                    cell.comment = Comment(_sanitize_xml_string(header_comments[col_idx - 1]), "系统")
            
            if include_operation_mode:
                operation_dv = DataValidation(
                    type="list",
                    formula1='"create - 新增,update - 更新,delete - 删除"',
                    allow_blank=True,
                    showDropDown=False
                )
                operation_dv.error = "请从下拉列表中选择：create - 新增/update - 更新/delete - 删除"
                operation_dv.errorTitle = "无效输入"
                operation_dv.prompt = "选择操作模式"
                operation_dv.promptTitle = "操作模式"
                ws.add_data_validation(operation_dv)
            
            row_idx = 2
            for record in (sheet_data or []):
                col_idx = 1
                
                if include_operation_mode:
                    cell = ws.cell(row=row_idx, column=col_idx, value="update - 更新")
                    cell.fill = light_blue_fill
                    cell.border = ds.THIN_BORDER
                    cell.alignment = Alignment(horizontal="center")
                    if protect_sheet:
                        cell.protection = Protection(locked=False)
                    operation_dv.add(cell)
                    col_idx += 1
                
                for header in headers[1:] if include_operation_mode else headers:
                    field_id = header_to_field.get(header, header)
                    value = record.get(field_id) or record.get(header)
                    
                    if field_id in enum_value_maps and value is not None:
                        label = enum_value_maps[field_id].get(value, value)
                        value = f"{value} - {label}" if label != value else value
                    
                    if field_id in bo_display_maps and value is not None:
                        display_name = bo_display_maps[field_id].get(value)
                        if display_name:
                            value = f"{display_name} ({value})"
                    
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                    cell.border = ds.THIN_BORDER
                    
                    original_col_idx = col_idx - 2 if include_operation_mode else col_idx - 1
                    
                    if original_col_idx in parent_key_columns:
                        cell.fill = ds.BUSINESS_KEY_FILL
                        if protect_sheet:
                            cell.protection = Protection(locked=False)
                    elif original_col_idx in create_required_columns:
                        cell.fill = ds.REQUIRED_FILL
                        if protect_sheet:
                            cell.protection = Protection(locked=False)
                    elif original_col_idx in readonly_columns:
                        cell.fill = ds.READONLY_FILL
                        if protect_sheet:
                            cell.protection = Protection(locked=True)
                    else:
                        if protect_sheet:
                            cell.protection = Protection(locked=False)
                    
                    col_idx += 1
                row_idx += 1
            
            export_enum_validations = {}
            for col_idx, header in enumerate(headers[1:] if include_operation_mode else headers, 2 if include_operation_mode else 1):
                field_id = header_to_field.get(header, header)
                
                if field_id in enum_value_maps:
                    enum_map = enum_value_maps[field_id]
                    display_values = [f"{k} - {v}" for k, v in enum_map.items()]
                    if display_values:
                        dv = DataValidation(
                            type="list",
                            formula1='"' + ','.join(display_values) + '"',
                            allow_blank=True
                        )
                        dv.error = f"请从下拉列表中选择有效的{header}"
                        dv.errorTitle = "无效输入"
                        dv.prompt = f"请选择{header} (Key - Label)"
                        dv.promptTitle = header
                        ws.add_data_validation(dv)
                        export_enum_validations[col_idx] = dv
            
            for row in range(2, row_idx):
                for col_idx in export_enum_validations:
                    cell = ws.cell(row=row, column=col_idx)
                    export_enum_validations[col_idx].add(cell)
            
            empty_rows_count = options.get("empty_rows_for_new", 5)
            for empty_row in range(empty_rows_count):
                col_idx = 1
                
                if include_operation_mode:
                    cell = ws.cell(row=row_idx, column=col_idx, value="create - 新增")
                    cell.fill = ds.BUSINESS_KEY_FILL
                    cell.border = ds.THIN_BORDER
                    cell.alignment = Alignment(horizontal="center")
                    if protect_sheet:
                        cell.protection = Protection(locked=False)
                    operation_dv.add(cell)
                    col_idx += 1
                
                for header in headers[1:] if include_operation_mode else headers:
                    cell = ws.cell(row=row_idx, column=col_idx, value="")
                    cell.border = ds.THIN_BORDER
                    
                    original_col_idx = col_idx - 2 if include_operation_mode else col_idx - 1
                    
                    if original_col_idx in parent_key_columns:
                        cell.fill = ds.BUSINESS_KEY_FILL
                        cell.comment = Comment(_sanitize_xml_string("新增时必填：请填写父对象的业务键编码"), "System")
                        if protect_sheet:
                            cell.protection = Protection(locked=False)
                    elif original_col_idx in create_required_columns:
                        cell.fill = ds.REQUIRED_FILL
                        if protect_sheet:
                            cell.protection = Protection(locked=False)
                    elif original_col_idx in readonly_columns:
                        cell.fill = ds.READONLY_FILL
                        if protect_sheet:
                            cell.protection = Protection(locked=True)
                    else:
                        if protect_sheet:
                            cell.protection = Protection(locked=False)
                    
                    col_idx += 1
                row_idx += 1
            
            for col_idx in range(1, len(headers) + 1):
                max_length = 0
                column_letter = get_column_letter(col_idx)
                for row in range(1, min(row_idx, 100)):
                    cell = ws.cell(row=row, column=col_idx)
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                adjusted_width = min(max(max_length + 2, 10), 50)
                ws.column_dimensions[column_letter].width = adjusted_width
            
            if protect_sheet:
                ws.protection = SheetProtection(
                    sheet=True,
                    autoFilter=False,
                    deleteColumns=False,
                    deleteRows=False,
                    formatCells=True,
                    formatColumns=True,
                    formatRows=True,
                    insertColumns=False,
                    insertRows=True,
                    sort=True,
                    objects=False,
                    scenarios=False,
                    pivotTables=False
                )
            
            sheets_info.append({
                "name": obj.name,
                "object_type": ot,
                "row_count": len(sheet_data) if sheet_data else 0
            })
            total_rows += len(sheet_data) if sheet_data else 0
        
        output_dir = os.path.join(os.getcwd(), "exports")
        os.makedirs(output_dir, exist_ok=True)
        
        product_name, version_name = self._get_product_version_info(filters)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if product_name and version_name:
            safe_product = "".join(c if c.isalnum() or c in '_-' else '_' for c in product_name)
            safe_version = "".join(c if c.isalnum() or c in '_-' else '_' for c in version_name)
            file_name = "{0}_{1}_{2}.xlsx".format(safe_product, safe_version, timestamp)
        elif version_name:
            safe_version = "".join(c if c.isalnum() or c in '_-' else '_' for c in version_name)
            file_name = "{0}_{1}.xlsx".format(safe_version, timestamp)
        else:
            file_name = "{0}.xlsx".format(timestamp)
        file_path = os.path.join(output_dir, file_name)
        
        wb.save(file_path)
        wb.close()
        
        return ExportResult(
            success=True,
            file_path=file_path,
            sheets=sheets_info,
            total_rows=total_rows
        )

    def _get_export_headers_with_editable(self, meta_obj: MetaObject, options: Optional[Dict[str, Any]]) -> tuple:
        """获取导出表头及可编辑列索引

        默认导出规则（参考 SAP Fiori "所见即所导" 原则）：
        1. 列表中可见的字段（ui.visible: true）默认可导出
        2. 显式设置 export_visible: true 的字段额外导出（不在列表中但需要导出）
        3. 显式设置 export_visible: false 的字段排除（在列表中但不导出）
        4. 默认排除系统字段：id, created_at, updated_at, created_by, updated_by
        5. 默认排除层级外键字段：version_id, product_id 等

        返回：
        - headers: 表头列表
        - editable_columns: 可编辑列索引（普通可编辑字段）
        - readonly_columns: 只读列索引（ID、系统字段等）
        - parent_key_columns: 父对象业务键列索引（新增时需要填写）
        - create_required_columns: 新增必填列索引（business_key、parent_key等）
        """
        options = options or {}
        include_hierarchy_ids = options.get("include_hierarchy_ids", True)
        include_hierarchy_path = options.get("include_hierarchy_path", True)
        include_hierarchy_names = options.get("include_hierarchy_names", True)

        hierarchy_fields = self._get_hierarchy_field_names(meta_obj)

        default_exclude_fields = self._build_default_exclude_fields(meta_obj)

        headers = []
        header_comments = []
        header_to_field = {}
        editable_columns = []
        readonly_columns = []
        parent_key_columns = []
        create_required_columns = []
        enum_value_maps = {}
        bo_display_fields = {}
        col_idx = 0

        def should_export_field(f):
            return self._should_export_field(meta_obj, f)

        # 调试日志
        all_fields = list(meta_obj.fields)
        excluded_by_default = [f for f in all_fields if f.id in default_exclude_fields]
        excluded_by_storage = [f for f in all_fields if f.storage.value == "virtual" and not hasattr(f, 'ui')]
        passed_fields = [f for f in all_fields if should_export_field(f)]
        
        hierarchy_fields = self._get_hierarchy_field_names(meta_obj)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Export] 对象类型: {meta_obj.id}, 总字段数: {len(all_fields)}")
        logger.info(f"[Export] hierarchy_fields: {hierarchy_fields}")
        logger.info(f"[Export] 因默认排除而过滤的字段: {[f.id for f in excluded_by_default]}")
        logger.info(f"[Export] 因virtual且无ui而过滤的字段: {[f.id for f in excluded_by_storage]}")
        logger.info(f"[Export] 通过 should_export_field 的字段: {[f.id for f in passed_fields]}")
        logger.info(f"[Export] 最终导出的字段 (排除hierarchy): {[f.name or f.id for f in passed_fields if (f.name or f.id) not in hierarchy_fields]}")
        
        export_fields = sorted(
            passed_fields,
            key=lambda f: (
                0 if getattr(f.semantics, 'business_key', False) else 1,
                0 if f.storage.value != "virtual" else 1,
                f.semantics.import_order if f.semantics.import_order else 999
            )
        )

        for f in export_fields:
            field_name = f.name or f.id
            if field_name not in hierarchy_fields:
                header_name = field_name
                headers.append(header_name)
                header_to_field[header_name] = f.id
                
                if f.enum_values:
                    enum_map = {ev.get('value'): ev.get('label', ev.get('value')) for ev in f.enum_values}
                    enum_value_maps[f.id] = enum_map
                else:
                    vh_enum_map = self._get_enum_value_map_from_value_help(f)
                    if vh_enum_map:
                        enum_value_maps[f.id] = vh_enum_map

                vh = getattr(f, 'value_help', None)
                if not vh:
                    ui_vh = getattr(f, 'ui', None)
                    if ui_vh:
                        vh = getattr(ui_vh, 'value_help', None)
                if vh:
                    vh_source = getattr(vh, 'source', None)
                    if vh_source and getattr(vh_source, 'type', None) == 'bo':
                        bo_display_fields[f.id] = {
                            'target_bo': getattr(vh_source, 'target_bo', ''),
                            'display_field': getattr(vh_source, 'display_field', 'name') or 'name',
                            'value_field': getattr(vh_source, 'value_field', 'id') or 'id',
                            'code_field': getattr(vh_source, 'code_field', 'code') or 'code',
                        }
                
                comment_parts = []
                if f.description:
                    comment_parts.append(f.description)
                
                # 只在有控制信息时添加标识
                has_control_info = False
                if f.semantics.business_key:
                    comment_parts.append("【业务关键字】新增必填，编辑时只读")
                    has_control_info = True
                    create_required_columns.append(col_idx)
                elif f.required or getattr(f.semantics, 'mandatory', False):
                    comment_parts.append("【必填】")
                    has_control_info = True
                elif getattr(f.semantics, 'parent_key', False) and hasattr(f, 'ui') and hasattr(f.ui, 'relation') and f.ui.relation:
                    comment_parts.append("【父对象外键】新增必填")
                    has_control_info = True
                    create_required_columns.append(col_idx)
                
                if not self._is_field_editable(f):
                    comment_parts.append("【只读】")
                    has_control_info = True
                
                header_comments.append("；".join(comment_parts) if has_control_info else "")
                
                if self._is_field_editable(f):
                    editable_columns.append(col_idx)
                else:
                    readonly_columns.append(col_idx)
                col_idx += 1

        if include_hierarchy_path:
            headers.append("层级路径")
            header_to_field["层级路径"] = "层级路径"
            header_comments.append("对象的完整层级路径，如：领域/子领域/服务模块")
            readonly_columns.append(col_idx)
            col_idx += 1

        is_first_parent = True
        current_obj = meta_obj
        while current_obj and current_obj.parent_object:
            parent_obj = registry.get(current_obj.parent_object)
            if parent_obj:
                # 找到对应 parent_object 的 parent_key 字段
                # 例如：parent_object 是 domain，则找 domain_id 字段
                parent_key_field_id = "{0}_id".format(current_obj.parent_object)
                parent_key_field = current_obj.get_field(parent_key_field_id)
                
                # 检查这个 parent_key 字段是否是 context_field
                is_context_field = parent_key_field and getattr(parent_key_field.semantics, 'context_field', False)
                
                if is_context_field:
                    # 遇到 context_field，停止向上追溯
                    # 这是上下文边界，之外的数据通过导入界面选择
                    break
                
                if include_hierarchy_ids:
                    header_name = "{0}编码".format(parent_obj.name)
                    headers.append(header_name)
                    header_to_field[header_name] = header_name
                    
                    if is_first_parent and parent_key_field:
                        if getattr(parent_key_field.semantics, 'readonly_always', False):
                            comment_msg = "父对象编码，只读"
                            readonly_columns.append(col_idx)
                        else:
                            comment_msg = "【父对象编码】新增必填；编辑时可切换到其他父对象"
                            parent_key_columns.append(col_idx)
                    else:
                        comment_msg = "父对象编码，只读"
                        readonly_columns.append(col_idx)
                    header_comments.append(comment_msg)
                    col_idx += 1
                if include_hierarchy_names:
                    header_name = "{0}名称".format(parent_obj.name)
                    headers.append(header_name)
                    header_to_field[header_name] = header_name
                    header_comments.append("父对象名称，只读")
                    readonly_columns.append(col_idx)
                    col_idx += 1
                is_first_parent = False
                current_obj = parent_obj
            else:
                break

        return headers, editable_columns, readonly_columns, parent_key_columns, create_required_columns, header_comments, header_to_field, enum_value_maps, bo_display_fields

    def _get_cascade_object_types(self, object_type: str) -> List[str]:
        """获取级联导出的对象类型列表
        
        级联导出包含：
        1. 当前对象的所有父对象（向上追溯）
        2. 当前对象的所有子对象（向下追溯）
        3. 如果包含业务对象，则自动包含关系对象
        
        这样可以导出完整的层级数据。
        """
        result = set()
        result.add(object_type)
        
        parent_types = self._get_parent_object_types(object_type)
        result.update(parent_types)
        
        child_types = self._get_child_object_types(object_type)
        result.update(child_types)
        
        result.update(self._get_association_bound_types(result))
        
        return list(result)
    
    def _get_parent_object_types(self, object_type: str) -> set:
        """向上获取所有父对象类型"""
        result = set()
        current_type = object_type
        
        while current_type:
            obj = registry.get(current_type)
            if obj and obj.parent_object:
                parent_obj = registry.get(obj.parent_object)
                if parent_obj:
                    result.add(obj.parent_object)
                    current_type = obj.parent_object
                else:
                    break
            else:
                break
        
        return result
    
    def _get_child_object_types(self, object_type: str) -> set:
        """向下获取所有子对象类型"""
        result = set()
        
        for obj_id in registry.list_objects():
            obj = registry.get(obj_id)
            if obj and obj.parent_object == object_type:
                result.add(obj_id)
                result.update(self._get_child_object_types(obj_id))
        
        return result

    def _sort_by_hierarchy(self, object_types: List[str]) -> List[str]:
        """按层级排序（父对象在前，子对象在后）

        排序规则：
        1. parent_object 关系：子对象依赖父对象（如 sub_domain → domain）
        2. child_sections 关系：子对象依赖其所有父对象
           （如 annotation → [domain, sub_domain, service_module, business_object, relationship]）
        """
        graph = {ot: [] for ot in object_types}
        
        for ot in object_types:
            obj = registry.get(ot)
            if obj and obj.parent_object and obj.parent_object in object_types:
                graph[ot] = [obj.parent_object]
        
        child_parent_map = self._collect_child_object_types(object_types)
        for child_type, parent_list in child_parent_map.items():
            if child_type in graph:
                for pt in parent_list:
                    if pt in object_types and pt not in graph[child_type]:
                        graph[child_type].append(pt)
        
        result = []
        visited = set()
        
        def visit(node):
            if node in visited:
                return
            visited.add(node)
            for parent in graph.get(node, []):
                visit(parent)
            result.append(node)
        
        for ot in object_types:
            visit(ot)
        
        return result

    def _query_with_hierarchy(self, object_type: str, filters: Optional[Dict[str, Any]],
                              options: Optional[Dict[str, Any]], sort_by: str = None, 
                              sort_order: str = 'asc',
                              page: int = None, page_size: int = None) -> List[Dict[str, Any]]:
        """查询数据并添加层级信息
        
        使用与列表查询相同的 resolve_conditions 方法，确保导出和列表数据一致性
        
        Args:
            object_type: 对象类型
            filters: 筛选条件
            options: 导出选项
            sort_by: 排序字段
            sort_order: 排序方向 (asc/desc)
            page: 页码（分页导出时使用，优先级高于 MAX_EXPORT_LIMIT）
            page_size: 每页数量（分页导出时使用）
        """
        conditions = []
        if filters:
            args_dict = {}
            for key, value in filters.items():
                if isinstance(value, list):
                    args_dict[key] = [str(v) for v in value]
                else:
                    args_dict[key] = [str(value)]
            
            conditions = self.hierarchy_filter.resolve_conditions(object_type, args_dict)
        
        if self._is_association_type(object_type) and filters:
            return self._query_association_with_hierarchy_filters(object_type, filters)
        
        MAX_EXPORT_LIMIT = self._get_export_limit(object_type)

        if page is not None and page_size is not None:
            actual_page = page
            actual_page_size = page_size
            print(f"[Export] 使用分页参数: page={actual_page}, page_size={actual_page_size}")
        else:
            actual_page = 1
            actual_page_size = MAX_EXPORT_LIMIT
            print(f"[Export] 开始查询 {object_type}，限制最大 {actual_page_size} 条")

        search_request = SearchRequest(
            object_type=object_type,
            conditions=conditions,
            page=actual_page,
            page_size=actual_page_size,
            sort_by=sort_by or '',
            sort_order=sort_order or 'asc',
        )

        search_result = self.query_service.search(search_request)
        data = search_result.data or []

        print(f"[Export] 查询完成，获取 {len(data)} 条数据")

        data = self._inject_hierarchy_info(data, object_type, filters, options)

        print(f"[Export] 层级信息注入完成")

        return data
    
    def _query_association_with_hierarchy_filters(self, object_type: str,
                                                     filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """配置驱动的 association 层级过滤查询

        从 hierarchies.yaml 的 association_filter_config 读取配置，
        按优先级（从细粒度到粗粒度）匹配过滤器，使用通用 SQL 查询 + 回退机制。

        支持任意 association 类型和任意层级结构，无需硬编码。
        """
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader

        filter_config = HierarchyConfigLoader.get_association_filter_config(object_type)
        if not filter_config:
            return []

        meta_obj = registry.get(object_type)
        table_name = meta_obj.table_name if meta_obj else object_type + 's'
        version_id = filters.get('version_id')
        relation_codes = filters.get('relation_codes', [])
        if not isinstance(relation_codes, list):
            relation_codes = [relation_codes] if relation_codes else []

        filter_levels = filter_config.get('hierarchy_filter_levels', [])

        for level_config in filter_levels:
            level_object = level_config.get('object')
            filter_key = level_object + '_id'
            level_ids = filters.get(filter_key, [])

            if not level_ids:
                continue
            if not isinstance(level_ids, list):
                level_ids = [level_ids]

            return self._query_association_by_level(
                object_type, table_name, version_id, level_ids,
                level_config, filter_config, relation_codes
            )

        if version_id:
            return self._query_association_by_version(object_type, table_name, version_id, relation_codes)

        return []

    def _query_association_by_level(self, object_type: str, table_name: str,
                                      version_id: int, level_ids: List[int],
                                      level_config: Dict[str, Any],
                                      filter_config: Dict[str, Any],
                                      relation_codes: List[str]) -> List[Dict[str, Any]]:
        """通用层级关联查询：直接查 association 表的 source/target 列，无结果则回退到子级"""
        from meta.core.enrichment_engine import enrich_records

        if not level_ids:
            return []

        source_col = level_config.get('source_column')
        target_col = level_config.get('target_column')
        if not source_col or not target_col:
            return []

        placeholders = ','.join(['?'] * len(level_ids))
        sql = f"""
            SELECT r.* FROM {table_name} r
            WHERE r.version_id = ?
            AND (r.{source_col} IN ({placeholders}) OR r.{target_col} IN ({placeholders}))
        """
        params = [version_id, *level_ids, *level_ids]

        if relation_codes:
            code_placeholders = ','.join(['?'] * len(relation_codes))
            sql += f" AND r.relation_code IN ({code_placeholders})"
            params.extend(relation_codes)

        cursor = self.data_source.execute(sql, tuple(params))
        columns = [desc[0] for desc in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not data:
            fallback = level_config.get('fallback')
            if fallback:
                child_object = fallback.get('child_object')
                child_fk_field = fallback.get('child_fk_field')
                if child_object and child_fk_field:
                    child_level = self._get_table_name_for_object(child_object)
                    child_placeholders = ','.join(['?'] * len(level_ids))
                    child_sql = f"SELECT id FROM {child_level} WHERE {child_fk_field} IN ({child_placeholders})"
                    cursor2 = self.data_source.execute(child_sql, tuple(level_ids))
                    child_ids = [row[0] for row in cursor2.fetchall()]
                    if child_ids:
                        child_level_config = self._find_filter_level_config(
                            object_type, child_object
                        )
                        if child_level_config:
                            return self._query_association_by_level(
                                object_type, table_name, version_id, child_ids,
                                child_level_config, filter_config, relation_codes
                            )

        data = enrich_records(object_type, data)

        return data

    def _get_table_name_for_object(self, object_type: str) -> str:
        """获取对象类型对应的表名"""
        meta_obj = registry.get(object_type)
        if meta_obj and meta_obj.table_name:
            return meta_obj.table_name
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader
        level = HierarchyConfigLoader.get_level_by_object(object_type)
        return level.get('table_name', object_type + 's')

    def _find_filter_level_config(self, object_type: str, target_object: str) -> Optional[Dict[str, Any]]:
        """在 association_filter_config 中查找指定 object 的层级配置"""
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader
        filter_levels = HierarchyConfigLoader.get_association_filter_levels(object_type)
        for level in filter_levels:
            if level.get('object') == target_object:
                return level
        return None

    def _query_association_by_version(self, object_type: str, table_name: str,
                                        version_id: int,
                                        relation_codes: List[str]) -> List[Dict[str, Any]]:
        """按 version_id 查询 association 数据（无层级过滤时使用）"""
        from meta.core.enrichment_engine import enrich_records

        sql = f"SELECT * FROM {table_name} WHERE version_id = ?"
        params = [version_id]

        if relation_codes:
            code_placeholders = ','.join(['?'] * len(relation_codes))
            sql += f" AND relation_code IN ({code_placeholders})"
            params.extend(relation_codes)

        cursor = self.data_source.execute(sql, tuple(params))
        columns = [desc[0] for desc in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]

        data = enrich_records(object_type, data)

        return data

    def _is_association_type(self, object_type: str) -> bool:
        """检查对象类型是否是 association 类型"""
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader
        level = HierarchyConfigLoader.get_level_by_object(object_type)
        return level.get('kind') == 'association'

    def _ensure_association_types_in_order(self, type_order: List[str]) -> List[str]:
        """确保 association 类型出现在 type_order 末尾

        从 hierarchies.yaml 的 levels 中查找 kind=association 的类型，
        自动追加到 type_order 末尾（如果尚未存在）。
        """
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader
        levels = HierarchyConfigLoader.get_levels()
        for level in levels:
            if level.get('kind') == 'association':
                obj = level.get('object')
                if obj and obj not in type_order:
                    type_order = type_order + [obj]
        return type_order

    def _get_export_limit(self, object_type: str) -> int:
        """获取导出数量限制

        优先从 meta_obj.import_export.max_export_limit 读取，
        默认 10000。
        """
        meta_obj = registry.get(object_type)
        if meta_obj and meta_obj.import_export:
            limit = getattr(meta_obj.import_export, 'max_export_limit', None)
            if limit:
                return limit
        return 10000

    def _build_type_labels(self) -> Dict[str, str]:
        """从 hierarchies.yaml 的 levels 配置构建类型标签映射"""
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader
        labels = {}
        levels = HierarchyConfigLoader.get_levels()
        for level in levels:
            obj = level.get('object')
            display_name = level.get('display_name', '')
            if obj and display_name:
                labels[obj] = display_name
        return labels

    def _build_full_data_sheets(self) -> set:
        """从 hierarchies.yaml 的 levels 配置构建需要完整数据的 sheet 集合

        entity 类型（kind=entity）的层级对象需要完整数据（可能被其他 sheet 引用）。
        """
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader
        sheets = set()
        levels = HierarchyConfigLoader.get_levels()
        for level in levels:
            if level.get('kind', 'entity') == 'entity':
                obj = level.get('object')
                table = level.get('table_name', '')
                if obj:
                    sheets.add(obj)
                    if table:
                        sheets.add(table)
        return sheets

    def _get_association_bound_types(self, existing_types: set) -> set:
        """获取与已有类型绑定的 association 类型

        从 hierarchies.yaml 的 levels 中查找 kind=association 的类型，
        如果其 source_entity 在 existing_types 中，则该 association 也应被包含。
        """
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader
        result = set()
        levels = HierarchyConfigLoader.get_levels()
        for level in levels:
            if level.get('kind') == 'association':
                source_entity = level.get('source_entity', '')
                if source_entity in existing_types:
                    result.add(level.get('object'))
        return result
    
    def _inject_hierarchy_info(self, data: List[Dict[str, Any]], object_type: str, 
                               filters: Optional[Dict[str, Any]], 
                               options: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        import logging
        logger = logging.getLogger(__name__)
        
        meta_obj = registry.get(object_type)
        
        for record in data:
            if options and options.get("include_hierarchy_path", True):
                record["层级路径"] = self._build_hierarchy_path(record, meta_obj)

            self._add_hierarchy_fields(record, meta_obj, options)

            if object_type == 'relationship':
                self._enrich_relationship_record(record)
        
        return data

    def _build_hierarchy_path(self, record: Dict[str, Any], meta_obj: MetaObject) -> str:
        """构建层级路径"""
        parts = []
        current_obj = meta_obj
        current_record = record
        
        while current_obj:
            name = current_record.get("name") or current_record.get(current_obj.id + "_name") or ""
            if name:
                parts.insert(0, name)
            
            if current_obj.parent_object:
                parent_obj = registry.get(current_obj.parent_object)
                parent_id = current_record.get(current_obj.parent_object + "_id")
                if parent_obj and parent_id:
                    parent_record = self._get_parent_record(current_obj.parent_object, parent_id)
                    current_obj = parent_obj
                    current_record = parent_record
                else:
                    break
            else:
                break
        
        return "/".join(parts)

    def _get_product_version_info(self, filters: Optional[Dict[str, Any]]) -> tuple:
        """获取产品线和版本名称"""
        product_name = ""
        version_name = ""
        
        if not filters:
            return product_name, version_name
        
        version_id = filters.get("version_id")
        if version_id:
            try:
                version_obj = registry.get("version")
                if version_obj:
                    search_request = SearchRequest(
                        object_type="version",
                        conditions=[QueryCondition(field="id", operator="eq", value=version_id)],
                        page=1,
                        page_size=1,
                    )
                    result = self.query_service.search(search_request)
                    if result.data:
                        version_data = result.data[0]
                        version_name = version_data.get("name", "")
                        product_id = version_data.get("product_id")
                        if product_id:
                            product_search = SearchRequest(
                                object_type="product",
                                conditions=[QueryCondition(field="id", operator="eq", value=product_id)],
                                page=1,
                                page_size=1,
                            )
                            product_result = self.query_service.search(product_search)
                            if product_result.data:
                                product_name = product_result.data[0].get("name", "")
            except Exception:
                pass
        
        return product_name, version_name

    def _get_product_version_codes(self, filters: Optional[Dict[str, Any]]) -> tuple:
        """根据 filters 中的 version_id 获取 product_code 和 version_code
        
        Args:
            filters: 包含 version_id 的过滤条件
            
        Returns:
            tuple: (product_code, version_code)
        """
        if not filters:
            return ('', '')
        
        version_id = filters.get('version_id')
        if not version_id:
            return ('', '')
        
        try:
            query = """
                SELECT p.code as product_code, v.code as version_code
                FROM versions v
                LEFT JOIN products p ON v.product_id = p.id
                WHERE v.id = ?
                LIMIT 1
            """
            cursor = self.data_source.execute(query, (version_id,))
            row = cursor.fetchone()
            if row:
                return (row[0] or '', row[1] or '')
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to get product/version codes: {e}")
        
        return ('', '')

    def _collect_child_object_types(self, selected_types: List[str]) -> Dict[str, List[str]]:
        """从 child_sections 配置收集子对象类型及其父对象映射

        扫描每个选中类型的 ui_view_config.child_sections 配置，
        收集所有 child_object 类型并记录父对象映射。

        Returns:
            Dict[str, List[str]]: {child_object_type: [parent_type_1, parent_type_2, ...]}
        """
        from meta.core.models import registry
        
        child_parent_map = {}
        for obj_type in selected_types:
            meta_obj = registry.get(obj_type)
            if not meta_obj:
                continue
            child_sections = getattr(meta_obj.ui_view_config, 'child_sections', [])
            for section in child_sections:
                child_type = section.get('child_object')
                if child_type:
                    if child_type not in child_parent_map:
                        child_parent_map[child_type] = []
                    if obj_type not in child_parent_map[child_type]:
                        child_parent_map[child_type].append(obj_type)
        return child_parent_map

    def _query_child_object(self, child_type: str, parent_types: List[str],
                            filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """通用子对象查询

        自动判断关联类型：
        - 多态关联（annotation）：通过 associations 的 polymorphic_type_field 查询
        - 直接 FK 关联（enum_value、version 等）：通过子对象 parent_object 字段反查父对象数据

        Args:
            child_type: 子对象类型 ID（如 'annotation', 'enum_value', 'version'）
            parent_types: 父对象类型 ID 列表
            filters: 导出过滤条件

        Returns:
            List[Dict]: 增强后的子对象数据列表
        """
        from meta.core.models import registry

        child_meta = registry.get(child_type)
        if not child_meta:
            return []

        if child_type == 'annotation':
            return self._query_annotations_impl(parent_types, filters)

        parent_object = getattr(child_meta, 'parent_object', None)
        if parent_object and parent_object in parent_types:
            return self._query_direct_fk_child(child_type, child_meta, parent_object, filters)

        return []

    def _classify_field(self, field) -> str:
        """对单个字段进行导出分类（与主导出保持一致）

        返回值：
        - 'parent_key'：父对象外键（多态 FK / 直接 FK），新增必填、编辑时只读
        - 'create_required'：新增必填字段（业务关键字、必填字段等）
        - 'readonly'：始终只读字段
        - 'editable'：普通可编辑字段
        """
        if not field:
            return 'readonly'

        if getattr(field.semantics, 'parent_key', False):
            if not getattr(field.semantics, 'readonly_always', False):
                return 'parent_key'

        if getattr(field.semantics, 'business_key', False):
            return 'create_required'

        if (field.required or getattr(field.semantics, 'mandatory', False)) and \
                not self._is_field_editable(field, mode='create'):
            return 'readonly'

        if not self._is_field_editable(field, mode='edit'):
            return 'readonly'

        return 'editable'

    def _write_child_sheet(self, wb, child_type: str, child_meta, data: List[Dict],
                           sheets_info: List[Dict], options: Optional[Dict[str, Any]] = None) -> None:
        """通用子对象 Sheet 写入

        使用 child_meta 的 export_visible 语义动态构建表头和数据行。

        对于需要 round-trip（导出后修改再导入）的场景，子对象 Sheet 采用
        export_visible UNION import_visible 的联合规则，确保导出的 Excel 包含
        导入所需的关键字段（如 annotation 的 target_type）。

        当子对象支持 CUD 操作时，自动添加"操作模式"列、数据验证、
        单元格级别的只读/可编辑高亮、列注释，以及空行用于新增记录。
        此行为是通用的：任何定义了 crud 类型 action 的子对象
        （无论多态关联如 annotation，还是直接 FK 关联如 enum_value）
        都会自动获得 CUD 支持。

        字段控制逻辑（与主导出保持一致）：
        - 父对象外键（parent_key）：现有行用 BUSINESS_KEY_FILL（浅绿），
          新增行同样用 BUSINESS_KEY_FILL（表示必填但可切换）
        - 业务关键字（business_key）：现有行用 REQUIRED_FILL（浅黄），
          新增行同样用 REQUIRED_FILL（新增必填、编辑时只读）
        - 普通必填（required / mandatory）：现有行不加底色，新增行用 REQUIRED_FILL
        - 始终只读（immutable、readonly_always、virtual、ui.editable=false）：
          所有行用 READONLY_FILL（灰色）
        - 可编辑字段：不加底色

        Args:
            wb: openpyxl Workbook 对象
            child_type: 子对象类型 ID
            child_meta: 子对象的 MetaObject
            data: 子对象数据列表
            sheets_info: Sheet 信息列表（会被修改）
            options: 导出选项（支持 include_operation_mode, empty_rows_for_new）
        """
        from openpyxl.styles import PatternFill, Font, Alignment
        from openpyxl.comments import Comment
        from openpyxl.utils import get_column_letter

        options = options or {}
        sheet_name = child_meta.name or child_type

        has_cud = _has_cud_actions(child_meta)
        include_operation_mode = options.get("include_operation_mode", True) and has_cud

        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        ds = ExcelDesignSystem

        default_exclude_fields = self._build_default_exclude_fields(child_meta)

        cud_required_fields = {'id'} if has_cud else set()

        candidates = []
        seen_names = set()
        for f in child_meta.fields:
            if f.id in default_exclude_fields and f.id not in cud_required_fields:
                continue
            if f.storage.value == "virtual" and not hasattr(f, 'ui'):
                continue

            export_vis = getattr(f.semantics, 'export_visible', None)
            import_vis = getattr(f.semantics, 'import_visible', None)

            is_cud_required = f.id in cud_required_fields

            if not is_cud_required and export_vis is False and import_vis is False:
                continue

            is_export = export_vis is True or is_cud_required
            is_import = import_vis is True

            if is_export or is_import or (hasattr(f, 'ui') and hasattr(f.ui, 'visible') and f.ui.visible is True):
                candidates.append((f, is_export, is_import))

        candidates.sort(key=lambda x: (
            0 if (x[1] and x[2]) else 1,
            0 if (x[2] and not (x[0].storage.value == 'virtual' or getattr(x[0].semantics, 'virtual', False))) else 1,
            0 if x[1] else 1
        ))

        export_fields = []
        for f, is_export, is_import in candidates:
            if f.name and f.name in seen_names:
                continue
            if f.name:
                seen_names.add(f.name)
            export_fields.append(f)

        export_fields.sort(key=lambda f: (
            0 if getattr(f.semantics, 'business_key', False) else 1,
            0 if f.storage.value != "virtual" else 1,
            f.semantics.import_order if f.semantics.import_order else 999
        ))

        if has_cud:
            id_in_export = any(f.id == 'id' for f in export_fields)
            if not id_in_export:
                for f in child_meta.fields:
                    if f.id == 'id':
                        export_fields.insert(0, f)
                        break

        ws = wb.create_sheet(title=sheet_name)
        col_offset = 0

        if include_operation_mode:
            col_offset = 1
            cell = ws.cell(row=1, column=1, value="操作模式")
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = ds.THIN_BORDER
            ws.column_dimensions['A'].width = 18
            cell.comment = Comment("新增/更新/删除/跳过，留空默认为更新", "系统")

            operation_dv = DataValidation(
                type="list",
                formula1='"create - 新增,update - 更新,delete - 删除"',
                allow_blank=True
            )
            operation_dv.error = "请从下拉列表中选择：create - 新增/update - 更新/delete - 删除"
            operation_dv.errorTitle = "无效输入"
            operation_dv.prompt = "选择操作模式"
            operation_dv.promptTitle = "操作模式"
            ws.add_data_validation(operation_dv)

        field_ids = [f.id for f in export_fields]
        field_classifications = {
            f.id: self._classify_field(f) for f in export_fields
        }
        enum_validations = {}
        value_help_map = {}

        for col_idx, f in enumerate(export_fields):
            actual_col = col_idx + 1 + col_offset
            header_name = f.name
            cell = ws.cell(row=1, column=actual_col, value=header_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = ds.THIN_BORDER

            classification = field_classifications[f.id]
            is_editable_create = self._is_field_editable(f, mode='create')
            is_editable_edit = self._is_field_editable(f, mode='edit')

            comment_parts = []
            if f.description:
                comment_parts.append(f.description)
            if classification == 'parent_key':
                if getattr(f.semantics, 'parent_key', False) and getattr(f.semantics, 'readonly_always', False):
                    comment_parts.append("【父对象外键】始终只读（上下文带入）")
                else:
                    comment_parts.append("【父对象外键 / 必填】新增必填，编辑时只读（可切换到其他父对象）")
            elif classification == 'create_required':
                if getattr(f.semantics, 'business_key', False):
                    comment_parts.append("【业务关键字】新增必填，编辑时只读")
                else:
                    comment_parts.append("【必填】")
            if not is_editable_create and not (classification == 'parent_key' or classification == 'create_required'):
                comment_parts.append("【只读】")
            if comment_parts:
                cell.comment = Comment("；".join(comment_parts), "系统")

            enum_dv_values = self._build_enum_dv_values(f)
            if enum_dv_values:
                dv = DataValidation(
                    type="list",
                    formula1=enum_dv_values,
                    allow_blank=True
                )
                dv.error = "请从下拉列表中选择有效值"
                dv.errorTitle = "无效输入"
                if classification == 'parent_key' or classification == 'create_required':
                    dv.error = "新增时该字段必填，且必须从下拉列表中选择"
                ws.add_data_validation(dv)
                enum_validations[actual_col] = dv
                value_help_map[f.id] = enum_dv_values

        for row_idx, record in enumerate(data, 2):
            if include_operation_mode:
                cell = ws.cell(row=row_idx, column=1, value="update - 更新")
                cell.fill = ds.READONLY_FILL
                cell.border = ds.THIN_BORDER
                cell.alignment = Alignment(horizontal="center")
                operation_dv.add(cell)

            for col_idx, field_id in enumerate(field_ids):
                actual_col = col_idx + 1 + col_offset
                value = record.get(field_id, "")
                cell = ws.cell(row=row_idx, column=actual_col, value=_safe_cell_value(value))
                cell.border = ds.THIN_BORDER

                classification = field_classifications[field_id]
                if classification == 'parent_key':
                    cell.fill = ds.BUSINESS_KEY_FILL
                elif classification == 'create_required':
                    cell.fill = ds.REQUIRED_FILL
                elif classification == 'readonly':
                    cell.fill = ds.READONLY_FILL
                if actual_col in enum_validations:
                    enum_validations[actual_col].add(cell)

        empty_rows_count = 0
        if include_operation_mode:
            empty_rows_count = options.get("empty_rows_for_new", 3)
            for empty_row in range(empty_rows_count):
                row_idx = len(data) + 2 + empty_row

                cell = ws.cell(row=row_idx, column=1, value="create - 新增")
                cell.fill = ds.BUSINESS_KEY_FILL
                cell.border = ds.THIN_BORDER
                cell.alignment = Alignment(horizontal="center")
                operation_dv.add(cell)

                for col_idx, field_id in enumerate(field_ids):
                    actual_col = col_idx + 1 + col_offset
                    cell = ws.cell(row=row_idx, column=actual_col, value="")
                    cell.border = ds.THIN_BORDER

                    classification = field_classifications[field_id]
                    if classification == 'parent_key':
                        cell.fill = ds.BUSINESS_KEY_FILL
                        cell.comment = Comment("新增时必填：请填写父对象的业务键编码", "System")
                    elif classification == 'create_required':
                        cell.fill = ds.REQUIRED_FILL
                    elif classification == 'readonly':
                        cell.fill = ds.READONLY_FILL
                    if actual_col in enum_validations:
                        enum_validations[actual_col].add(cell)

        total_rows_in_sheet = 2 + len(data) + empty_rows_count
        for col_idx, f in enumerate(export_fields):
            actual_col = col_idx + 1 + col_offset
            col_letter = get_column_letter(actual_col)
            max_length = len(f.name or f.id)
            for row in range(2, total_rows_in_sheet):
                try:
                    cell_val = ws.cell(row=row, column=actual_col).value
                    if cell_val is not None:
                        max_length = max(max_length, len(str(cell_val)))
                except Exception:
                    pass
            adjusted_width = min(max(max_length + 2, 8), 50)
            ws.column_dimensions[col_letter].width = adjusted_width

        sheets_info.append({
            "name": sheet_name,
            "object_type": child_type,
            "row_count": len(data) + (empty_rows_count if include_operation_mode else 0)
        })

    def _build_enum_dv_values(self, field) -> Optional[str]:
        """构造字段的 DataValidation 下拉值（统一优先：value_help > enum_values > ui.options）

        返回 openpyxl DataValidation 的 formula1 字符串（如 '"a,b,c"'），
        若字段没有可枚举的值则返回 None。
        """
        candidates = []

        vh = getattr(field, 'value_help', None)
        if not vh:
            ui_vh = getattr(field, 'ui', None)
            if ui_vh:
                vh = getattr(ui_vh, 'value_help', None)
        if vh:
            source = getattr(vh, 'source', None)
            if source and getattr(source, 'type', None) == 'enum':
                enum_type_id = getattr(source, 'enum_type_id', None)
                if enum_type_id:
                    enum_map = self._get_enum_value_map_from_value_help(field)
                    if enum_map:
                        candidates.extend(f"{k} - {v}" for k, v in enum_map.items())

        if not candidates and getattr(field, 'enum_values', None):
            candidates.extend(
                f"{ev.get('value')} - {ev.get('label', ev.get('value'))}"
                for ev in field.enum_values
            )

        if not candidates:
            ui = getattr(field, 'ui', None)
            if ui and getattr(ui, 'options', None):
                candidates.extend(
                    f"{opt.get('value')} - {opt.get('label', opt.get('value'))}"
                    if isinstance(opt, dict) else str(opt)
                    for opt in ui.options
                )

        if not candidates:
            return None

        safe_values = []
        for v in candidates:
            v = str(v).replace('"', "'")
            safe_values.append(v)

        return '"' + ','.join(safe_values) + '"'

    def _query_direct_fk_child(self, child_type: str, child_meta, parent_type: str,
                                filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """查询直接 FK 关联的子对象数据

        根据子对象的 parent_object 字段，反查父对象数据并获取其子对象。

        Args:
            child_type: 子对象类型 ID
            child_meta: 子对象的 MetaObject
            parent_type: 父对象类型 ID
            filters: 导出过滤条件

        Returns:
            List[Dict]: 子对象数据列表
        """
        parent_meta = registry.get(parent_type)
        if not parent_meta:
            return []

        parent_table = parent_meta.table_name or parent_type + 's'
        child_table = child_meta.table_name or child_type + 's'

        version_id = (filters or {}).get('version_id')
        parent_fk_field = child_meta.parent_object + '_id'

        try:
            if version_id:
                sql = (f"SELECT c.* FROM {child_table} c "
                       f"INNER JOIN {parent_table} p ON c.{parent_fk_field} = p.id "
                       f"WHERE p.version_id = ?")
                params = [version_id]
            else:
                sql = (f"SELECT c.* FROM {child_table} c "
                       f"INNER JOIN {parent_table} p ON c.{parent_fk_field} = p.id")
                params = []

            cursor = self.data_source.execute(sql, tuple(params))
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"[Export] 查询子对象 {child_type} 失败: {e}"
            )
            return []

    def _query_annotations_impl(self, parent_types: List[str],
                                 filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """查询备注信息（内部实现，供 _query_child_object 调用）"""
        from meta.core.models import registry

        category_labels = {
            "important": "重要",
            "warning": "警告",
            "info": "信息",
            "tip": "提示"
        }

        type_labels = self._build_type_labels()

        try:
            conditions = [QueryCondition(field="target_type", operator=QueryOperator.IN, values=parent_types)]

            search_request = SearchRequest(
                object_type="annotation",
                conditions=conditions,
                page=1,
                page_size=100000,
            )
            result = self.query_service.search(search_request)
            annotations = result.data or []

            enriched_annotations = []
            for ann in annotations:
                target_type = ann.get("target_type", "")
                target_id = ann.get("target_id")

                target_code = ""
                target_name = ""

                if target_type and target_id:
                    try:
                        target_obj = registry.get(target_type)
                        if target_obj:
                            target_search = SearchRequest(
                                object_type=target_type,
                                conditions=[QueryCondition(field="id", operator=QueryOperator.EQ, value=target_id)],
                                page=1,
                                page_size=1,
                            )
                            target_result = self.query_service.search(target_search)
                            if target_result.data:
                                target_data = target_result.data[0]

                                bk_fields = [f for f in target_obj.fields
                                            if getattr(f.semantics, 'business_key', False)
                                            and not getattr(f.semantics, 'virtual', False)]
                                name_field = next((f for f in target_obj.fields if f.id == "name" or "name" in f.id.lower()), None)

                                if target_type == "relationship":
                                    target_code = target_data.get("relation_code", "")
                                    target_name = target_data.get("relation_desc", "") or " -> ".join(filter(None, [target_data.get("source_code", ""), target_data.get("target_code", "")]))
                                elif bk_fields:
                                    target_code = target_data.get(bk_fields[0].id, "")
                                    target_name = target_data.get(name_field.id, "") if name_field else ""
                                else:
                                    target_code = target_data.get("code", "")
                                    target_name = target_data.get("name", "")
                    except Exception:
                        pass

                created_at_raw = ann.get("created_at", "")
                created_at_formatted = ""
                if created_at_raw:
                    try:
                        from datetime import datetime
                        if isinstance(created_at_raw, datetime):
                            created_at_formatted = created_at_raw.strftime("%Y-%m-%d %H:%M")
                        elif isinstance(created_at_raw, str):
                            try:
                                dt = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                                created_at_formatted = dt.strftime("%Y-%m-%d %H:%M")
                            except ValueError:
                                created_at_formatted = created_at_raw
                        else:
                            created_at_formatted = str(created_at_raw)
                    except Exception:
                        created_at_formatted = str(created_at_raw)

                enriched_annotations.append({
                    "id": ann.get("id"),
                    "target_type": target_type,
                    "target_type_label": type_labels.get(target_type, target_type),
                    "target_code": target_code,
                    "target_name": target_name,
                    "category": ann.get("category", ""),
                    "category_label": category_labels.get(ann.get("category", ""), ann.get("category", "")),
                    "content": ann.get("content", ""),
                    "created_at": created_at_formatted,
                    "created_by": ann.get("created_by", "")
                })

            return enriched_annotations
        except Exception:
            return []

    def _query_annotations(self, object_types: List[str], filters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """查询备注信息（已废弃，请使用 _query_child_object）

        保留此方法用于向后兼容。
        """
        return self._query_annotations_impl(object_types, filters)

    def _get_parent_record(self, object_type: str, record_id: int) -> Dict[str, Any]:
        """获取父记录"""
        try:
            search_request = SearchRequest(
                object_type=object_type,
                conditions=[QueryCondition(field="id", operator="eq", value=record_id)],
                page=1,
                page_size=1,
            )
            result = self.query_service.search(search_request)
            return result.data[0] if result.data else {}
        except Exception:
            return {}

    def _add_hierarchy_fields(self, record: Dict[str, Any], meta_obj: MetaObject, options: Dict[str, Any]):
        """添加层级字段（编码和名称）- 向上追溯所有父对象
        
        注意：遇到 context_field 时停止追溯，这是上下文边界
        """
        include_hierarchy_ids = options.get("include_hierarchy_ids", True)
        include_hierarchy_names = options.get("include_hierarchy_names", True)

        current_obj = meta_obj
        current_record = record

        while current_obj and current_obj.parent_object:
            parent_id = current_record.get(current_obj.parent_object + "_id")
            parent_obj = registry.get(current_obj.parent_object)
            
            # 找到对应 parent_object 的 parent_key 字段
            parent_key_field_id = "{0}_id".format(current_obj.parent_object)
            parent_key_field = current_obj.get_field(parent_key_field_id)
            
            # 检查这个 parent_key 字段是否是 context_field
            is_context_field = parent_key_field and getattr(parent_key_field.semantics, 'context_field', False)
            
            # 遇到 context_field 时停止追溯
            if is_context_field:
                break
            
            if parent_obj and parent_id:
                parent_record = self._get_parent_record(current_obj.parent_object, parent_id)
                if include_hierarchy_ids:
                    bk_fields = [f for f in parent_obj.fields 
                                if getattr(f.semantics, 'business_key', False) 
                                and not getattr(f.semantics, 'virtual', False)]
                    code = parent_record.get(bk_fields[0].id, "") if bk_fields else parent_record.get("code", "")
                    record["{0}编码".format(parent_obj.name)] = code
                if include_hierarchy_names:
                    name = parent_record.get("name", "")
                    record["{0}名称".format(parent_obj.name)] = name
                current_obj = parent_obj
                current_record = parent_record
            else:
                break

    def _add_hierarchy_ids(self, record: Dict[str, Any], meta_obj: MetaObject):
        """添加层级ID列（保留兼容性）"""
        pass

    def _add_hierarchy_names(self, record: Dict[str, Any], meta_obj: MetaObject):
        """添加层级名称列（保留兼容性）"""
        pass

    def _enrich_relationship_record(self, record: Dict[str, Any]):
        """填充关系记录的 virtual 字段 - 兼容入口"""
        self._enrich_association_record('relationship', record)

    def _enrich_association_record(self, object_type: str, record: Dict[str, Any]):
        """填充 association 记录的 virtual 字段（配置驱动）

        从 hierarchies.yaml 的 association_filter_config 读取 source/target 列名和实体类型，
        动态填充层级名称字段。
        """
        import logging
        logger = logging.getLogger(__name__)

        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader
        filter_config = HierarchyConfigLoader.get_association_filter_config(object_type)
        if not filter_config:
            return

        source_prefix = filter_config.get('source_prefix', 'source')
        target_prefix = filter_config.get('target_prefix', 'target')
        entity_id_field = filter_config.get('entity_id_field', 'bo_id')
        source_entity = HierarchyConfigLoader.get_level_by_object(object_type).get('source_entity', '')

        source_id = record.get(source_prefix + '_' + entity_id_field)
        target_id = record.get(target_prefix + '_' + entity_id_field)
        relation_code = record.get('relation_code')

        if relation_code:
            enum_info = self._get_enum_value_info('relation_type', relation_code)
            if enum_info:
                record['relation_type_name'] = enum_info.get('name', relation_code)
                record['relation_type_name_en'] = enum_info.get('name_en', '')
                if enum_info.get('dimensions'):
                    record['relation_type_dimensions'] = enum_info['dimensions']
            else:
                record['relation_type_name'] = relation_code

        if source_id and source_entity:
            source_entity_data = self._get_entity_with_hierarchy(source_entity, source_id)
            if source_entity_data:
                record[source_prefix + '_bo_name'] = source_entity_data.get('name', '')
                record[source_prefix + '_code'] = record.get(source_prefix + '_code') or source_entity_data.get('code', '')
                for key, value in source_entity_data.items():
                    if key.endswith('_name') and key != 'name':
                        record[source_prefix + '_' + key] = value

        if target_id and source_entity:
            target_entity_data = self._get_entity_with_hierarchy(source_entity, target_id)
            if target_entity_data:
                record[target_prefix + '_bo_name'] = target_entity_data.get('name', '')
                record[target_prefix + '_code'] = record.get(target_prefix + '_code') or target_entity_data.get('code', '')
                for key, value in target_entity_data.items():
                    if key.endswith('_name') and key != 'name':
                        record[target_prefix + '_' + key] = value

    def _get_bo_by_id(self, bo_id: int) -> Dict[str, Any]:
        """根据 ID 获取业务对象（包含层级信息）- 配置驱动动态 JOIN"""
        return self._get_entity_with_hierarchy('business_object', bo_id)

    def _get_entity_with_hierarchy(self, object_type: str, entity_id: int) -> Dict[str, Any]:
        """根据 ID 获取实体对象（包含层级名称信息）

        从 hierarchies.yaml 的层级链动态构建 LEFT JOIN SQL，
        而非硬编码 bo → sm → sd → d 四表 JOIN。
        """
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader

        meta_obj = registry.get(object_type)
        if not meta_obj:
            return {}

        table_name = meta_obj.table_name
        levels = HierarchyConfigLoader.get_levels()

        object_to_level = {l.get('object'): l for l in levels}
        current = object_type
        join_parts = []
        select_parts = ["t0.id", "t0.code", "t0.name"]
        result_keys = ['id', 'code', 'name']
        table_idx = 0

        while current:
            level = object_to_level.get(current, {})
            parent_object = level.get('parent_object')
            if not parent_object or parent_object == 'version':
                break

            parent_level = object_to_level.get(parent_object, {})
            parent_table = parent_level.get('table_name')
            fk_field = level.get('foreign_key_field')

            if not parent_table or not fk_field:
                break

            table_idx += 1
            parent_alias = "t{0}".format(table_idx)
            child_alias = "t{0}".format(table_idx - 1)
            join_parts.append(
                "LEFT JOIN {0} {1} ON {2}.{3} = {1}.id".format(
                    parent_table, parent_alias, child_alias, fk_field
                )
            )
            name_key = parent_object + '_name'
            select_parts.append("{0}.name as {1}".format(parent_alias, name_key))
            result_keys.append(name_key)

            current = parent_object

        sql = "SELECT {0} FROM {1} t0 {2} WHERE t0.id = ? LIMIT 1".format(
            ', '.join(select_parts), table_name, ' '.join(join_parts)
        )

        try:
            cursor = self.data_source.execute(sql, (entity_id,))
            row = cursor.fetchone()
            if row:
                result = {}
                for i, key in enumerate(result_keys):
                    result[key] = row[i] if row[i] is not None else ''
                return result
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("[Enrichment] Failed to get %s by id %s: %s", object_type, entity_id, e)
        return {}

    def _get_export_headers(self, meta_obj: MetaObject, options: Optional[Dict[str, Any]]) -> List[str]:
        """获取导出表头"""
        options = options or {}
        include_hierarchy_ids = options.get("include_hierarchy_ids", True)
        include_hierarchy_path = options.get("include_hierarchy_path", True)
        include_hierarchy_names = options.get("include_hierarchy_names", True)
        include_readonly = options.get("include_readonly", True)

        hierarchy_fields = self._get_hierarchy_field_names(meta_obj)

        headers = []

        export_fields = sorted(
            [f for f in meta_obj.fields if f.semantics.export_visible and f.storage.value != "virtual"],
            key=lambda f: f.semantics.import_order
        )

        for f in export_fields:
            field_name = f.name or f.id
            if field_name not in hierarchy_fields:
                if include_readonly and not self._is_field_editable(f):
                    headers.append("{0}(只读)".format(field_name))
                else:
                    headers.append(field_name)

        if include_hierarchy_path:
            headers.append("层级路径")

        current_obj = meta_obj
        while current_obj and current_obj.parent_object:
            parent_obj = registry.get(current_obj.parent_object)
            if parent_obj:
                if include_hierarchy_ids:
                    headers.append("{0}编码".format(parent_obj.name))
                if include_hierarchy_names:
                    headers.append("{0}名称".format(parent_obj.name))
            current_obj = parent_obj

        return headers

    def _is_field_editable(self, field, mode: str = 'edit') -> bool:
        """判断字段是否可编辑（用于导入导出）

        参考 SAP CDS View 字段控制逻辑：
        1. 系统字段：始终只读
        2. readonly_always 字段：始终只读（新建+编辑）
        3. 计算字段（computation.formula 或 semantics.computed）：始终只读
        4. virtual 字段（无 computation）：如果是搜索帮助则可编辑，否则只读
        5. immutable 字段：编辑时只读
        6. parent_key 字段：可编辑（SAP One Model 允许移动层级）
        7. ui.editable=false：始终只读
        """
        readonly_field_ids = {'id', 'created_at', 'updated_at', 'created_by', 'updated_by'}

        if field.id in readonly_field_ids:
            return False

        # readonly_always 始终只读
        if getattr(field.semantics, 'readonly_always', False):
            return False

        # 计算字段（computation.formula）始终只读
        if hasattr(field, 'computation') and getattr(field.computation, 'formula', None):
            return False

        # 计算字段（semantics.computed）始终只读
        if getattr(field.semantics, 'computed', False):
            return False

        is_parent_key = getattr(field.semantics, 'parent_key', False)

        if is_parent_key and mode == 'create':
            is_polymorphic = (
                getattr(field.semantics, 'virtual', False)
                or field.storage.value == 'virtual'
            )
            if hasattr(field, 'ui') and hasattr(field.ui, 'editable') and field.ui.editable is False:
                return False
            if is_polymorphic:
                return True
            return True

        if mode == 'edit' and is_parent_key:
            pass

        # virtual 字段：如果是计算字段则只读，如果是外键/搜索帮助则可编辑
        if field.storage.value == 'virtual' or getattr(field.semantics, 'virtual', False):
            # 有 ui.relation 的 virtual 字段是外键/搜索帮助，可编辑
            if hasattr(field, 'ui') and hasattr(field.ui, 'relation') and field.ui.relation:
                pass  # 可编辑
            else:
                return False  # 计算字段，只读

        if mode == 'edit':
            if getattr(field.semantics, 'immutable', False):
                return False
            # parent_key 字段可编辑（SAP One Model 允许移动层级）

        if hasattr(field, 'ui') and hasattr(field.ui, 'editable') and field.ui.editable is False:
            return False

        if hasattr(field.semantics, 'import_editable') and field.semantics.import_editable is False:
            return False

        return True
    
    def _filter_import_record(self, record: Dict[str, Any], meta_obj, operation_mode: str = 'update') -> Dict[str, Any]:
        """过滤导入记录，只保留可导入的字段
        
        导入规则（参考 _is_field_editable）：
        1. 系统字段（id, created_at 等）：新增时忽略，编辑时保留
        2. readonly_always 字段：始终忽略
        3. virtual 字段：始终忽略（除非有 ui.relation 作为搜索帮助字段，且操作是新增）
        4. immutable 字段：编辑模式下忽略（业务键不可修改）
        5. ui.editable=false：始终忽略
        """
        filtered = {}
        system_fields = {'id', 'created_at', 'updated_at', 'created_by', 'updated_by'}
        
        is_create = operation_mode in ["新增", "插入", "create", "insert", "Create", "Insert"]
        is_update = operation_mode in ["更新", "update", "Update"]
        # 删除和更新都需要保留业务键来定位记录
        is_need_bk = operation_mode in ["更新", "update", "Update", "删除", "delete", "Delete"]
        
        for field_id, value in record.items():
            if field_id in system_fields:
                if is_create:
                    continue  # 新增时忽略 id 等系统字段
                else:
                    filtered[field_id] = value  # 编辑时保留 id 等系统字段
                    continue
            
            field = meta_obj.get_field(field_id)
            if not field:
                continue
            
            # 业务键字段始终保留（用于定位记录）
            is_bk = getattr(field.semantics, 'business_key', False)
            
            # readonly_always 字段忽略（业务键除外）
            if getattr(field.semantics, 'readonly_always', False) and not is_bk:
                continue
            
            # ui.editable=false 字段忽略（业务键除外）
            if hasattr(field, 'ui') and hasattr(field.ui, 'editable') and field.ui.editable is False and not is_bk:
                continue
            
            # import_editable=false 字段忽略（业务键除外）
            if hasattr(field.semantics, 'import_editable') and field.semantics.import_editable is False and not is_bk:
                continue
            
            # virtual 字段的处理
            is_virtual = field.storage.value == 'virtual' or getattr(field.semantics, 'virtual', False)
            has_relation = hasattr(field, 'ui') and hasattr(field.ui, 'relation') and field.ui.relation
            is_parent_key = getattr(field.semantics, 'parent_key', False)

            if is_virtual:
                if (has_relation or is_parent_key) and is_create:
                    filtered[field_id] = value
                elif is_parent_key and is_need_bk:
                    filtered[field_id] = value
                else:
                    continue
            
            # immutable 字段在编辑/更新/删除时忽略（业务键不可修改）
            # 但 business_key 字段必须保留，用于查找记录
            # [SYMBOL] 关键修复：parent_key 字段也必须保留，用于建立父子关系
            if is_update and getattr(field.semantics, 'immutable', False):
                is_bk = getattr(field.semantics, 'business_key', False)
                if not is_bk and not is_parent_key:
                    continue
            
            # 删除模式下，非 business_key 的 immutable 字段也忽略
            if operation_mode in ["删除", "delete", "Delete"] and getattr(field.semantics, 'immutable', False):
                is_bk = getattr(field.semantics, 'business_key', False)
                if not is_bk:
                    continue
            
            filtered[field_id] = value
        
        return filtered
    
    def _is_business_key(self, field) -> bool:
        """判断字段是否为业务键"""
        return hasattr(field.semantics, 'business_key') and field.semantics.business_key is True

    def _build_default_exclude_fields(self, meta_obj: MetaObject) -> set:
        """从 hierarchy 配置自动推导默认排除字段

        替代硬编码的 default_exclude_fields 集合。
        系统字段 + 层级 FK/名称字段 + association 虚拟字段均从配置推导。
        """
        from meta.services.config_driven_hierarchy_filter import HierarchyConfigLoader

        exclude = {
            'id', 'created_at', 'updated_at', 'created_by', 'updated_by',
            'version_id', 'product_id', 'version_name', 'product_name',
            'product_line', 'product_line_id', 'version_code',
            '版本编码', '版本名称', '产品线编码', '产品线名称',
            'ID'
        }

        levels = HierarchyConfigLoader.get_levels()
        for level in levels:
            obj = level.get('object')
            kind = level.get('kind', 'entity')
            display_name = level.get('display_name', '')

            if kind == 'entity':
                exclude.add(obj + '_id')
                exclude.add(obj + '_name')
                exclude.add(display_name)
                exclude.add(display_name + '编码')
                exclude.add(display_name + '名称')

        level_config = HierarchyConfigLoader.get_level_by_object(meta_obj.id)
        if level_config.get('kind') == 'association':
            filter_config = HierarchyConfigLoader.get_association_filter_config(meta_obj.id)
            if filter_config:
                for fl in filter_config.get('hierarchy_filter_levels', []):
                    src_col = fl.get('source_column', '')
                    tgt_col = fl.get('target_column', '')
                    if not fl.get('direct_filter'):
                        exclude.add(src_col)
                        exclude.add(tgt_col)

            for f in meta_obj.fields:
                if f.storage.value == 'virtual' and not getattr(f.semantics, 'export_visible', False):
                    exclude.add(f.id)
                    if f.name:
                        exclude.add(f.name)

        return exclude

    def _object_has_field(self, object_type: str, field_id: str) -> bool:
        """检查对象类型是否有指定字段"""
        obj = registry.get(object_type)
        if not obj:
            return False
        return any(f.id == field_id for f in obj.fields)

    def _should_export_field(self, meta_obj: MetaObject, field) -> bool:
        """判断字段是否应导出（统一规则）

        导出规则：
        1. 在默认排除列表中 → 不导出
        2. 敏感字段（sensitivity: restricted/confidential） → 不导出
        3. virtual 且无 ui → 不导出
        4. ui.hidden_in_list: true → 不导出（与列表显示保持一致）
        5. ui.hidden_in_form: true → 不导出（表单中隐藏，导出也应隐藏）
        6. 显式 export_visible: false → 不导出
        7. 显式 export_visible: true → 导出
        8. ui.visible: true → 导出
        9. 以上都不满足 → 导出（默认导出）
        """
        default_exclude_fields = self._build_default_exclude_fields(meta_obj)

        if field.id in default_exclude_fields:
            return False

        sensitivity = getattr(field.semantics, 'sensitivity', None)
        if sensitivity in ('restricted', 'confidential'):
            return False

        if field.storage.value == "virtual" and not hasattr(field, 'ui'):
            return False

        if hasattr(field, 'ui'):
            # 检查 ui.hidden_in_list - 与列表显示保持一致
            if hasattr(field.ui, 'hidden_in_list') and field.ui.hidden_in_list:
                return False
            # 检查 ui.hidden_in_form - 表单中隐藏，导出也应隐藏
            if hasattr(field.ui, 'hidden_in_form') and field.ui.hidden_in_form:
                return False
            # 检查 ui.visible - 显式设置为不可见
            if hasattr(field.ui, 'visible') and field.ui.visible is False:
                return False

        if hasattr(field.semantics, 'export_visible'):
            if field.semantics.export_visible is False:
                return False
            if field.semantics.export_visible is True:
                return True

        if hasattr(field, 'ui') and hasattr(field.ui, 'visible'):
            return field.ui.visible is True

        return True

    def _get_hierarchy_field_names(self, meta_obj: MetaObject) -> set:
        """获取与层级关联的字段名集合（排除这些字段避免重复）
        
        只排除父对象的业务键字段，因为它们已通过层级编码/名称列显示。
        当前对象自己的业务键字段（如编码）应该保留。
        """
        hierarchy_fields = set()

        current_obj = meta_obj
        while current_obj and current_obj.parent_object:
            parent_obj = registry.get(current_obj.parent_object)
            if parent_obj:
                hierarchy_fields.add("{0}_id".format(parent_obj.id))
                hierarchy_fields.add("{0}_name".format(parent_obj.id))
                hierarchy_fields.add("{0}ID".format(parent_obj.name))
                hierarchy_fields.add("{0}名".format(parent_obj.name))
                hierarchy_fields.add("{0}编码".format(parent_obj.name))
                hierarchy_fields.add("{0}名称".format(parent_obj.name))
                hierarchy_fields.add("{0}_id".format(parent_obj.name.lower()))
                hierarchy_fields.add("{0}_name".format(parent_obj.name.lower()))
                hierarchy_fields.add(parent_obj.name)
            current_obj = parent_obj

        return hierarchy_fields

    def _get_parent_key_headers(self, meta_obj: MetaObject, headers: List[str]) -> Dict[str, Dict[str, str]]:
        """获取父对象业务键表头映射
        
        返回格式：{ "父对象编码": { "parent_type": "parent_object_id", "id_field": "parent_id" } }
        例如：{ "服务模块编码": { "parent_type": "service_module", "id_field": "service_module_id" } }
        """
        result = {}
        
        if not meta_obj.parent_object:
            return result
        
        parent_obj = registry.get(meta_obj.parent_object)
        if not parent_obj:
            return result
        
        parent_code_header = "{0}编码".format(parent_obj.name)
        if parent_code_header in headers:
            result[parent_code_header] = {
                "parent_type": meta_obj.parent_object,
                "id_field": "{0}_id".format(meta_obj.parent_object)
            }
        
        return result

    def _header_to_field_id(self, meta_obj: MetaObject, header: str) -> str:
        """将表头转换为字段ID"""
        for f in meta_obj.fields:
            if f.name == header or f.id == header:
                return f.id
        return header

    def import_cascade(self, file_path: str, mode: str = "execute",
                       conflict_strategy: str = "upsert",
                       context: Optional[Dict[str, Any]] = None,
                       progress_callback: Optional[callable] = None) -> Any:
        """
        级联导入：从Excel文件导入多个对象类型的数据

        Args:
            file_path: Excel文件路径
            mode: 导入模式 (preview | execute)
            conflict_strategy: 冲突处理策略 (upsert | skip | replace)
            context: 导入上下文，包含version_id和product_id等
            progress_callback: 进度回调函数，接收 dict: {progress, current_type, current_type_name, total_types, current_index, message}

        Returns:
            ImportPreview 或 ImportResult
        """
        import logging
        logger = logging.getLogger(__name__)

        context = context or {}

        if not os.path.exists(file_path):
            return ImportPreview() if mode == "preview" else ImportResult(
                success=False, errors=[{"message": "File not found: {0}".format(file_path)}]
            )
        
        try:
            wb = load_workbook(file_path, read_only=True, data_only=True)
        except Exception as e:
            return ImportPreview() if mode == "preview" else ImportResult(
                success=False, errors=[{"message": "Failed to read Excel: {0}".format(str(e))}]
            )
        
        sheets = []
        # [SYMBOL] 收集所有需要完整数据的Sheet（可能被其他Sheet引用）
        full_data_sheets = self._build_full_data_sheets()

        for sheet_name in wb.sheetnames:
            if sheet_name == "元数据":
                continue

            object_type = self._sheet_name_to_object_type(sheet_name)
            if not object_type:
                continue

            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))

            if len(rows) < 2:
                continue

            headers = [str(h).strip() if h is not None else "" for h in rows[0]]

            # [SYMBOL] 预览时：
            # - 业务对象等可能被引用的Sheet：收集所有数据（用于引用完整性检查）
            # - 其他Sheet：只取前10行
            if object_type in full_data_sheets:
                data_rows = [list(row) for row in rows[1:]]  # 收集所有行
                logger.info(f"[Import] 收集完整数据: {sheet_name} ({len(data_rows)} 行)")
            else:
                data_rows = [list(row) for row in rows[1:10]]  # 预览只取前10行

            sheets.append({
                "name": sheet_name,
                "object_type": object_type,
                "row_count": len(rows) - 1,
                "columns": headers,
                "preview_rows": data_rows
            })
        
        wb.close()

        import_order = self._sort_by_hierarchy([s["object_type"] for s in sheets])

        logger.info(f"[Import] sheets: {[s['object_type'] for s in sheets]}")
        logger.info(f"[Import] import_order: {import_order}")

        if mode == "preview":
            validation = self._validate_sheets(sheets, context)
            return ImportPreview(
                sheets=sheets,
                validation=validation,
                import_order=import_order
            )
        
        results = {}
        all_errors = []

        enabled_types = [ot for ot in import_order if registry.get(ot) and registry.get(ot).import_export.import_enabled]
        total_types = len(enabled_types)
        completed_count = 0

        if progress_callback:
            progress_callback({
                'progress': 0,
                'current_type': '',
                'current_type_name': '',
                'total_types': total_types,
                'current_index': 0,
                'message': '开始导入，共 {0} 种对象类型'.format(total_types)
            })

        for i, ot in enumerate(import_order):
            sheet_info = next((s for s in sheets if s["object_type"] == ot), None)
            if not sheet_info:
                continue

            obj = registry.get(ot)
            if not obj or not obj.import_export.import_enabled:
                continue

            type_name = obj.name or ot
            current_index = i + 1
            
            type_progress_base = int((i / total_types) * 100) if total_types > 0 else 0
            type_progress_weight = int(100 / total_types) if total_types > 0 else 100

            if progress_callback:
                progress_callback({
                    'progress': type_progress_base,
                    'current_type': ot,
                    'current_type_name': type_name,
                    'total_types': total_types,
                    'current_index': current_index,
                    'message': '开始导入: {0} ({1}/{2})'.format(type_name, current_index, total_types)
                })

            obj_conflict_strategy = conflict_strategy
            if obj and obj.import_export and obj.import_export.conflict_strategy:
                obj_conflict_strategy = obj.import_export.conflict_strategy

            sheet_result = self._import_sheet(file_path, sheet_info, obj_conflict_strategy, context,
                                              progress_callback, type_progress_base, type_progress_weight)
            results[ot] = sheet_result
            completed_count += 1

            if sheet_result.get("errors"):
                all_errors.extend([
                    {"object_type": ot, **e} for e in sheet_result["errors"]
                ])

            if progress_callback:
                progress_callback({
                    'progress': min(99, int(((i + 1) / total_types) * 100)) if total_types > 0 else 100,
                    'current_type': ot,
                    'current_type_name': type_name,
                    'total_types': total_types,
                    'current_index': current_index,
                    'message': '已完成: {0} ({1}/{2})'.format(type_name, completed_count, total_types)
                })

        if progress_callback:
            progress_callback({
                'progress': 100,
                'current_type': '',
                'current_type_name': '',
                'total_types': total_types,
                'current_index': total_types,
                'message': '导入完成'
            })
        
        return ImportResult(
            success=len(all_errors) == 0,
            results=results,
            errors=all_errors
        )

    def _sheet_name_to_object_type(self, sheet_name: str) -> Optional[str]:
        """将Sheet名称转换为对象类型"""
        for obj_id in registry.list_objects():
            obj = registry.get(obj_id)
            if obj and obj.name == sheet_name:
                return obj_id
        return None

    def _validate_sheets(self, sheets: List[Dict[str, Any]], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """校验导入数据

        校验规则：
        1. business_key 字段必填（新增时）
        2. business_key 值不能重复（在当前版本内）
        3. 父对象 business_key（如 code）必须存在（数据库或当前Excel中）
        """
        import logging
        logger = logging.getLogger(__name__)

        context = context or {}
        version_id = context.get('version_id')
        logger.info(f"[Validate] 开始校验，版本ID: {version_id}")

        valid_count = 0
        invalid_count = 0
        errors = []

        # [SYMBOL] 第一步：收集所有即将导入的业务键，建立索引
        # 格式: {object_type: {bk_field_id: set of values}}
        importing_bk_values: Dict[str, Dict[str, set]] = {}

        for sheet in sheets:
            obj = registry.get(sheet["object_type"])
            if not obj:
                continue

            # 获取业务键字段
            bk_fields = []
            for f in obj.fields:
                if getattr(f.semantics, 'business_key', False):
                    is_virtual = f.storage.value == 'virtual' or getattr(f.semantics, 'virtual', False)
                    import_visible = getattr(f.semantics, 'import_visible', True)
                    if not is_virtual and import_visible:
                        bk_fields.append(f)

            if not bk_fields:
                continue

            # 收集该对象类型的所有业务键值
            if obj.id not in importing_bk_values:
                importing_bk_values[obj.id] = {}

            for row in sheet.get("preview_rows", []):
                record = dict(zip(sheet["columns"], row))

                if len(bk_fields) == 1:
                    # 单业务键
                    # [SYMBOL] 尝试多种方式获取值：中文列名、英文列名、字段ID
                    bk_value = None
                    bk_field = bk_fields[0]

                    # 首先尝试字段的 name 属性
                    if bk_field.name and bk_field.name in record:
                        bk_value = record[bk_field.name]
                    # 然后尝试字段的 ID
                    elif bk_field.id and bk_field.id in record:
                        bk_value = record[bk_field.id]
                    # 最后遍历 record 的 key 查找中文列名
                    else:
                        for key in record.keys():
                            if key in ['编码', '名称', 'code', bk_field.name, bk_field.id]:
                                bk_value = record[key]
                                break

                    if bk_value and str(bk_value).strip():
                        bk_value_str = str(bk_value).strip()
                        if bk_field.id not in importing_bk_values[obj.id]:
                            importing_bk_values[obj.id][bk_field.id] = set()
                        importing_bk_values[obj.id][bk_field.id].add(bk_value_str)
                        # [SYMBOL] 添加调试日志
                        logger.info(f"[Validate] 索引收集: {obj.id}.{bk_field.id} = {bk_value_str} (key={bk_field.name}/{bk_field.id})")
                else:
                    # 组合业务键
                    bk_values = []
                    all_empty = True
                    for bk_field in bk_fields:
                        bk_value = record.get(bk_field.name) or record.get(bk_field.id)
                        if bk_value and str(bk_value).strip():
                            all_empty = False
                            bk_values.append(str(bk_value).strip())
                        else:
                            bk_values.append("")

                    if not all_empty:
                        composite_key = "||".join(bk_values)
                        if 'composite' not in importing_bk_values[obj.id]:
                            importing_bk_values[obj.id]['composite'] = {}
                        if obj.id not in importing_bk_values[obj.id]['composite']:
                            importing_bk_values[obj.id]['composite'][obj.id] = set()
                        importing_bk_values[obj.id]['composite'][obj.id].add(composite_key)

        logger.info(f"[Validate] 收集到的待导入业务键: {importing_bk_values.keys()}")

        for sheet in sheets:
            obj = registry.get(sheet["object_type"])
            if not obj:
                continue
            
            # 获取可用于导入的业务关键字字段（支持组合键）
            # 条件：business_key=true, NOT virtual, import_visible != false
            bk_fields = []
            for f in obj.fields:
                if getattr(f.semantics, 'business_key', False):
                    is_virtual = f.storage.value == 'virtual' or getattr(f.semantics, 'virtual', False)
                    import_visible = getattr(f.semantics, 'import_visible', True)
                    if not is_virtual and import_visible:
                        bk_fields.append(f)
            
            existing_composite_keys = set()
            
            # 检查是否有操作模式列
            op_mode_idx = None
            columns = sheet.get("columns", [])
            if "操作模式" in columns:
                op_mode_idx = columns.index("操作模式")
            
            for idx, row in enumerate(sheet.get("preview_rows", [])):
                row_num = idx + 2
                record = dict(zip(sheet["columns"], row))
                
                # 确定当前行的操作模式
                operation_mode = "update"  # 默认是更新模式
                if op_mode_idx is not None and op_mode_idx < len(row):
                    op_value = row[op_mode_idx]
                    if op_value:
                        op_str = str(op_value).strip()
                        # 解析 "Key - Label" 格式
                        if ' - ' in op_str:
                            key_part = op_str.split(' - ')[0].strip().lower()
                        else:
                            key_part = op_str.lower()
                        
                        if key_part in ["新增", "插入", "create", "insert"]:
                            operation_mode = "create"
                        elif key_part in ["删除", "delete"]:
                            operation_mode = "delete"
                        elif key_part in ["跳过", "skip"]:
                            operation_mode = "skip"
                        elif key_part in ["更新", "update"]:
                            operation_mode = "update"
                
                # 只有新增和更新模式才验证必填字段
                should_validate_required = operation_mode in ["create", "update"]
                
                # 构建列名到字段的映射
                column_to_field = {}
                for field in obj.fields:
                    column_to_field[field.name] = field
                    column_to_field[field.id] = field
                
                # 层级字段的列名映射（如"领域编码" -> domain_id 字段）
                parent_object = obj.parent_object
                current_for_hierarchy = obj
                while parent_object:
                    parent_obj = registry.get(parent_object)
                    if parent_obj:
                        parent_key_field_id = "{0}_id".format(parent_object)
                        parent_key_field = current_for_hierarchy.get_field(parent_key_field_id)
                        if parent_key_field:
                            # 层级字段的列名是 "{父对象名称}编码" 和 "{父对象名称}名称"
                            code_header = "{0}编码".format(parent_obj.name)
                            column_to_field[code_header] = parent_key_field
                            name_header = "{0}名称".format(parent_obj.name)
                            column_to_field[name_header] = parent_key_field
                    parent_obj_instance = registry.get(parent_object)
                    if parent_obj_instance:
                        parent_object = parent_obj_instance.parent_object
                        current_for_hierarchy = parent_obj_instance
                    else:
                        break
                
                for field in obj.fields:
                    # 跳过系统字段和上下文字段（这些由系统自动填充）
                    if field.id == 'id' and field.required and getattr(field.semantics, 'meaning', '').find('自增主键') >= 0:
                        continue  # ID 字段是自增主键，导入时自动生成，不验证
                    
                    if getattr(field.semantics, 'readonly_always', False):
                        continue  # readonly_always 字段不验证（从上下文带入）
                    
                    if getattr(field.semantics, 'context_field', False):
                        continue  # 上下文字段不验证（从上下文带入）
                    
                    # 跳过可以通过 resolve_from_field 解析的字段
                    # 借鉴 SAP @ObjectModel.foreignKey.association 注解
                    resolve_from = getattr(field.semantics, 'resolve_from_field', None)
                    resolve_to = getattr(field.semantics, 'resolve_to_object', None)
                    if not resolve_from or not resolve_to:
                        vh = getattr(field, 'value_help', None)
                        if not vh:
                            ui_obj = getattr(field, 'ui', None)
                            if ui_obj:
                                vh = getattr(ui_obj, 'value_help', None)
                        if vh:
                            vh_source = getattr(vh, 'source', None)
                            if vh_source and getattr(vh_source, 'type', None) == 'bo':
                                resolve_to = getattr(vh_source, 'target_bo', None)
                                code_field = getattr(vh_source, 'code_field', None) or 'code'
                                if code_field and code_field != field.id:
                                    resolve_from = code_field
                    if resolve_from and resolve_to:
                        # 检查源字段是否有值
                        # record 的 key 可能是中文字段名或字段 ID
                        source_field = obj.get_field(resolve_from)
                        source_value = None
                        if source_field:
                            source_value = record.get(source_field.name) or record.get(resolve_from)
                        else:
                            source_value = record.get(resolve_from)
                        if source_value:
                            continue  # 可以通过源字段解析，跳过必填验证
                    
                    # 检查是否必填：mandatory / business_key / parent_key
                    # 注意：更新模式下 parent_key 字段不验证必填（保留原值）
                    is_parent_key_field = getattr(field.semantics, 'parent_key', False)
                    is_business_key_field = getattr(field.semantics, 'business_key', False)
                    is_required = (
                        getattr(field.semantics, 'mandatory', False)
                        or (is_parent_key_field and operation_mode == "create")
                        or (is_business_key_field and operation_mode == "create")
                    )
                    
                    if should_validate_required and is_required:
                        # 尝试多种方式获取值：直接用列名或通过 column_to_field 映射
                        value = None
                        # 先尝试 field.name 和 field.id
                        value = record.get(field.name) or record.get(field.id)
                        # 如果没找到，遍历 record 的 key 看是否映射到当前 field
                        if value is None or value == "":
                            for col_name in record.keys():
                                mapped_field = column_to_field.get(col_name)
                                if mapped_field == field:
                                    value = record[col_name]
                                    break
                        
                        if value is None or value == "":
                            field_label = field.name or field.id
                            meaning = getattr(field.semantics, 'meaning', field_label)
                            errors.append({
                                "sheet": sheet["name"],
                                "row": row_num,
                                "field": field_label,
                                "error": f"{meaning} 不能为空"
                            })
                            invalid_count += 1
                    
                    enum_type_ref = getattr(field.semantics, 'enum_type_ref', None) or (
                        hasattr(field, 'ui') and getattr(field.ui, 'enum_type', None)
                    )
                    if not enum_type_ref:
                        enum_type_ref = self._get_enum_type_id_from_value_help(field)
                    if enum_type_ref and should_validate_required:
                        field_value = record.get(field.name) or record.get(field.id)
                        if field_value and str(field_value).strip():
                            field_value_str = str(field_value).strip()
                            if not self._validate_enum_value(enum_type_ref, field_value_str):
                                field_label = field.name or field.id
                                errors.append({
                                    "sheet": sheet["name"],
                                    "row": row_num,
                                    "field": field_label,
                                    "error": f"【枚举值无效】'{field_value_str}' 不是有效的 {field_label}，请检查枚举值配置"
                                })
                                invalid_count += 1
                
                if bk_fields:
                    # 构建组合业务键值
                    bk_values = []
                    all_bk_empty = True
                    for bk_field in bk_fields:
                        bk_value = record.get(bk_field.name) or record.get(bk_field.id)
                        if bk_value is not None and str(bk_value).strip() != "":
                            all_bk_empty = False
                            bk_values.append(str(bk_value).strip())
                        else:
                            bk_values.append("")
                    
                    composite_key = "||".join(bk_values)
                    
                    if all_bk_empty:
                        if operation_mode == "create":
                            bk_field_names = "、".join([f.name for f in bk_fields])
                            errors.append({
                                "sheet": sheet["name"],
                                "row": row_num,
                                "field": bk_field_names,
                                "error": "【业务关键字】新增必填"
                            })
                            invalid_count += 1
                    else:
                        if composite_key in existing_composite_keys:
                            bk_field_names = "、".join([f.name for f in bk_fields])
                            errors.append({
                                "sheet": sheet["name"],
                                "row": row_num,
                                "field": bk_field_names,
                                "error": "【业务关键字】组合值重复：{0}".format(composite_key.replace("||", " + "))
                            })
                            invalid_count += 1
                        else:
                            existing_composite_keys.add(composite_key)
                            # 检查组合键是否已存在于数据库（考虑版本）
                            if len(bk_fields) == 1:
                                existing_record = self._find_by_key(sheet["object_type"], bk_fields[0].id, bk_values[0], version_id)
                            else:
                                existing_record = self._find_by_composite_key(sheet["object_type"], bk_fields, bk_values, version_id)
                            if existing_record:
                                if operation_mode == "create":
                                    bk_field_names = "、".join([f.name for f in bk_fields])
                                    version_hint = f" (版本ID: {version_id})" if version_id else " (所有版本)"
                                    errors.append({
                                        "sheet": sheet["name"],
                                        "row": row_num,
                                        "field": bk_field_names,
                                        "error": f"【业务关键字】数据库中已存在相同记录{version_hint}"
                                    })
                                    invalid_count += 1
                                    logger.warning(f"[Validate] 业务键冲突: {composite_key} (版本ID: {version_id})")

                # [SYMBOL] 引用完整性检查 - 检查所有外键引用
                # 包括通过 resolve_from_field 引用其他对象的字段
                for field in obj.fields:
                    # 检查是否有 resolve_from_field 和 resolve_to_object 语义
                    resolve_to = getattr(field.semantics, 'resolve_to_object', None)
                    resolve_from = getattr(field.semantics, 'resolve_from_field', None)

                    # 如果字段本身有 resolve_to_object，说明它是通过 ID 引用
                    # 如果字段有 resolve_from_field，说明它是引用源字段（如 source_code 引用 business_object）
                    if resolve_to:
                        # 获取源字段的值
                        source_field = None
                        if resolve_from:
                            # 通过 resolve_from_field 获取源字段
                            source_field = obj.get_field(resolve_from)
                            if not source_field:
                                source_field = obj.get_field_by_name(resolve_from)
                        else:
                            # 直接使用当前字段
                            source_field = field

                        if source_field:
                            # 从 record 中获取值
                            source_value = record.get(source_field.name) or record.get(source_field.id)

                            if source_value and str(source_value).strip():
                                # 检查被引用的对象是否存在
                                source_value_str = str(source_value).strip()

                                # 获取引用对象的业务键字段
                                ref_obj = registry.get(resolve_to)
                                if ref_obj:
                                    # [SYMBOL] 收集用于导入的 business_key 字段（与索引收集的逻辑一致）
                                    ref_bk_fields = []
                                    for rf in ref_obj.fields:
                                        if getattr(rf.semantics, 'business_key', False):
                                            # [SYMBOL] 过滤 virtual 和 import_visible 字段（与索引收集逻辑一致）
                                            is_virtual = getattr(rf, 'storage', None) and rf.storage.value == 'virtual' or getattr(rf.semantics, 'virtual', False)
                                            import_visible = getattr(rf.semantics, 'import_visible', True)
                                            if not is_virtual and import_visible:
                                                ref_bk_fields.append(rf)

                                    if ref_bk_fields:
                                        # [SYMBOL] 在数据库中查找被引用的对象
                                        ref_record = None
                                    if len(ref_bk_fields) == 1:
                                        ref_record = self._find_by_key(resolve_to, ref_bk_fields[0].id, source_value_str, version_id)
                                    else:
                                        ref_record = self._find_by_composite_key(resolve_to, ref_bk_fields, [source_value_str], version_id)

                                    # [SYMBOL] 如果数据库中没有，检查是否在即将导入的数据中
                                    in_importing = False
                                    if not ref_record:
                                        logger.info(f"[Validate] 数据库中未找到 {source_value_str}，检查即将导入的索引...")
                                        logger.info(f"[Validate] importing_bk_values keys: {list(importing_bk_values.keys())}")

                                        if resolve_to in importing_bk_values:
                                            ref_obj_data = importing_bk_values[resolve_to]
                                            logger.info(f"[Validate] 找到引用对象的索引, ref_obj_data keys: {list(ref_obj_data.keys())}")

                                            if len(ref_bk_fields) == 1:
                                                bk_field_id = ref_bk_fields[0].id
                                                logger.info(f"[Validate] 查询字段: {bk_field_id}")

                                                if bk_field_id in ref_obj_data:
                                                    values = ref_obj_data[bk_field_id]
                                                    logger.info(f"[Validate] 索引中的值数量: {len(values)}")
                                                    if source_value_str in values:
                                                        in_importing = True
                                                        logger.info(f"[Validate] [OK] 在即将导入的数据中找到 {source_value_str}")
                                                    else:
                                                        logger.info(f"[Validate] [X] 索引中不包含 {source_value_str}")
                                                        logger.info(f"[Validate] 索引中的部分值: {list(values)[:5]}")
                                                else:
                                                    logger.info(f"[Validate] 引用 {source_value_str} 在即将导入的数据中找到")

                                        if not ref_record and not in_importing:
                                            field_label = source_field.name or source_field.id
                                            version_info = f"(版本ID: {version_id})" if version_id else ""
                                            error_msg = f"【引用完整性】引用的 {ref_obj.name} '{source_value_str}' 不存在 {version_info}"
                                            hint = f"请先导入 {ref_obj.name} 数据，或检查业务键 '{source_value_str}' 是否正确"
                                            errors.append({
                                                "sheet": sheet["name"],
                                                "row": row_num,
                                                "field": field_label,
                                                "error": error_msg,
                                                "hint": hint
                                            })
                                            invalid_count += 1
                                            logger.warning(f"[Validate] 引用完整性错误: {obj.name}.{field_label} -> {resolve_to}.{source_value_str} (版本ID: {version_id})")
                
                valid_count += 1
        
        return {
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "errors": errors[:20]
        }

    def _validate_enum_value(self, enum_type_id: str, code: str) -> bool:
        """验证枚举值是否有效
        
        Args:
            enum_type_id: 枚举类型ID（如 'relation_type'）
            code: 枚举值编码
            
        Returns:
            bool: 枚举值是否存在且启用
        """
        try:
            sql = """
                SELECT COUNT(*) FROM enum_values 
                WHERE enum_type_id = ? AND code = ? AND is_active = 1
            """
            cursor = self.data_source.execute(sql, [enum_type_id, code])
            result = cursor.fetchone()
            return result[0] > 0 if result else False
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[Validate] 枚举值验证失败: {enum_type_id}.{code} - {e}")
            return True

    def _get_enum_value_info(self, enum_type_id: str, code: str) -> Optional[Dict[str, Any]]:
        """获取枚举值详细信息（包括名称和维度）
        
        Args:
            enum_type_id: 枚举类型ID
            code: 枚举值编码
            
        Returns:
            Dict: 枚举值信息，包含 name, dimensions 等
        """
        try:
            sql = """
                SELECT code, name, name_en, dimensions 
                FROM enum_values 
                WHERE enum_type_id = ? AND code = ? AND is_active = 1
            """
            cursor = self.data_source.execute(sql, [enum_type_id, code])
            row = cursor.fetchone()
            if row:
                import json
                result = {
                    'code': row[0],
                    'name': row[1],
                    'name_en': row[2] or ''
                }
                if row[3]:
                    try:
                        result['dimensions'] = json.loads(row[3])
                    except:
                        result['dimensions'] = {}
                return result
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[Validate] 获取枚举值信息失败: {enum_type_id}.{code} - {e}")
        return None

    def _preload_references(self, rows: List[tuple], headers: List[str], 
                           parent_key_headers: Dict, obj, version_id: Optional[int] = None) -> Dict[str, Any]:
        """批量预加载外键引用，避免 N+1 查询问题

        优化策略：
        1. 收集所有需要查询的 (object_type, code) 组合
        2. 批量查询数据库
        3. 建立内存索引 {(object_type, code): record}

        Args:
            rows: Excel 数据行
            headers: 列名列表
            parent_key_headers: 父对象键信息
            obj: 元对象
            version_id: 版本ID

        Returns:
            Dict: {(object_type, code): record} 内存索引
        """
        import logging
        logger = logging.getLogger(__name__)

        lookup_index: Dict[tuple, Dict] = {}
        if not rows or not headers:
            return lookup_index

        object_codes: Dict[str, set] = {}

        for row in rows:
            for parent_header, parent_info in parent_key_headers.items():
                parent_code_idx = headers.index(parent_header) if parent_header in headers else -1
                if parent_code_idx >= 0 and parent_code_idx < len(row):
                    parent_code = row[parent_code_idx]
                    if parent_code:
                        parent_type = parent_info["parent_type"]
                        if parent_type not in object_codes:
                            object_codes[parent_type] = set()
                        object_codes[parent_type].add(parent_code)

            for field in obj.fields:
                resolve_from = getattr(field.semantics, 'resolve_from_field', None)
                resolve_to_object = getattr(field.semantics, 'resolve_to_object', None)
                resolve_to_field = getattr(field.semantics, 'resolve_to_field', None)

                if not resolve_from and not resolve_to_object and not resolve_to_field:
                    vh = getattr(field, 'value_help', None)
                    if not vh:
                        ui_obj = getattr(field, 'ui', None)
                        if ui_obj:
                            vh = getattr(ui_obj, 'value_help', None)
                    if vh:
                        vh_source = getattr(vh, 'source', None)
                        if vh_source and getattr(vh_source, 'type', None) == 'bo':
                            resolve_to_object = getattr(vh_source, 'target_bo', None)
                            code_field = getattr(vh_source, 'code_field', None) or 'code'
                            if code_field and code_field != field.id:
                                resolve_from = code_field

                if resolve_from and (resolve_to_object or resolve_to_field):
                    resolve_from_idx = headers.index(resolve_from) if resolve_from in headers else -1
                    if resolve_from_idx >= 0 and resolve_from_idx < len(row):
                        source_value = row[resolve_from_idx]
                        if source_value:
                            if resolve_to_object:
                                target_type = resolve_to_object
                            elif resolve_to_field:
                                target_type_idx = headers.index(resolve_to_field) if resolve_to_field in headers else -1
                                if target_type_idx >= 0 and target_type_idx < len(row):
                                    target_type = row[target_type_idx]
                                else:
                                    continue
                            else:
                                continue

                            if target_type:
                                if target_type not in object_codes:
                                    object_codes[target_type] = set()
                                object_codes[target_type].add(source_value)

        logger.info(f"[Preload] 需要预加载的对象类型: {list(object_codes.keys())}")
        logger.info(f"[Preload] 各类型编码数量: {[(k, len(v)) for k, v in object_codes.items()]}")

        for object_type, codes in object_codes.items():
            if not codes:
                continue
            try:
                conditions = [
                    QueryCondition(field="code", operator="in", value=list(codes))
                ]
                if version_id is not None:
                    conditions.append(
                        QueryCondition(field="version_id", operator="eq", value=version_id)
                    )

                search_request = SearchRequest(
                    object_type=object_type,
                    conditions=conditions,
                    page=1,
                    page_size=len(codes) * 2,
                )
                result = self.query_service.search(search_request)

                for record in result.data:
                    code_value = record.get("code")
                    if code_value:
                        lookup_index[(object_type, code_value)] = record

                logger.info(f"[Preload] 预加载 {object_type}: 查询到 {len(result.data)} 条记录")

            except Exception as e:
                logger.warning(f"[Preload] 预加载 {object_type} 失败: {e}")

        logger.info(f"[Preload] 预加载完成，总索引条目: {len(lookup_index)}")
        return lookup_index

    def _find_from_index(self, lookup_index: Dict[tuple, Dict], 
                         object_type: str, code: str) -> Optional[Dict]:
        """从内存索引中查找记录

        Args:
            lookup_index: 预加载的内存索引
            object_type: 对象类型
            code: 编码值

        Returns:
            Optional[Dict]: 找到的记录，或 None
        """
        return lookup_index.get((object_type, code))

    def _import_sheet(self, file_path: str, sheet_info: Dict[str, Any],
                      conflict_strategy: str, context: Optional[Dict[str, Any]] = None,
                      progress_callback: Optional[callable] = None,
                      type_progress_base: int = 0,
                      type_progress_weight: int = 100) -> Dict[str, Any]:
        """导入单个Sheet的数据

        Args:
            file_path: Excel文件路径
            sheet_info: Sheet信息
            conflict_strategy: 冲突处理策略
            context: 导入上下文，包含version_id和product_id等
            progress_callback: 进度回调函数
            type_progress_base: 该类型的基础进度（0-100中的起始值）
            type_progress_weight: 该类型的进度权重（占100的比例）
        """
        import logging
        logger = logging.getLogger(__name__)

        context = context or {}

        frontend_version_id = context.get('version_id')
        logger.info(f"[Import] 前端传入的版本ID: {frontend_version_id}, context keys: {list(context.keys())}")

        meta = self._read_meta_sheet(file_path)
        excel_product_code = meta.get('product_code')
        excel_version_code = meta.get('version_code')

        logger.info(f"[Import] Excel元数据表信息: product_code={excel_product_code}, version_code={excel_version_code}")

        if frontend_version_id:
            logger.info(f"[Import] 使用前端传入的version_id={frontend_version_id}，忽略Excel元数据表中的版本")
            if excel_product_code or excel_version_code:
                logger.warning(f"[Import] [WARNING] 前端传入的版本ID({frontend_version_id})与Excel元数据表版本({excel_version_code})可能不一致，将使用前端版本")
        elif excel_product_code and excel_version_code:
            resolved_version_id = self._resolve_version_id(excel_product_code, excel_version_code)
            if resolved_version_id:
                logger.info(f"[Import] 从Excel元数据表解析出version_id={resolved_version_id}")
                context['version_id'] = resolved_version_id
                context['product_code'] = excel_product_code
                context['version_code'] = excel_version_code
            else:
                logger.warning(f"[Import] 无法从Excel元数据表(product={excel_product_code}, version={excel_version_code})解析出version_id")
        else:
            logger.info(f"[Import] 前端未传入version_id，Excel元数据表也无可用版本信息，将不指定版本导入")
        
        object_type = sheet_info["object_type"]
        obj = registry.get(object_type)
        if not obj:
            return {"success": 0, "failed": 0, "errors": [{"message": "Object not found"}]}
        
        try:
            wb = load_workbook(file_path, read_only=True, data_only=True)
            ws = wb[sheet_info["name"]]
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
        except Exception as e:
            return {"success": 0, "failed": 0, "errors": [{"message": str(e)}]}
        
        if len(rows) < 2:
            return {"success": 0, "failed": 0, "errors": []}

        headers = [str(h).strip() if h is not None else "" for h in rows[0]]
        field_map = self._auto_map_fields(obj, headers)

        parent_key_headers = self._get_parent_key_headers(obj, headers)

        # [SYMBOL] 调试日志：打印 parent_key_headers
        if parent_key_headers:
            logger.info(f"[Import] parent_key_headers for {object_type}: {parent_key_headers}")

        has_operation_mode = "操作模式" in headers
        operation_mode_idx = headers.index("操作模式") if has_operation_mode else -1

        logger.info(f"[Import] {object_type}导入 - headers: {headers[:10]}, has_operation_mode={has_operation_mode}")

        # [SYMBOL] 性能优化：批量预加载外键引用
        lookup_version_id = context.get('version_id')
        lookup_index = self._preload_references(rows[1:], headers, parent_key_headers, obj, lookup_version_id)

        success_count = 0
        failed_count = 0
        skipped_count = 0
        deleted_count = 0
        errors = []
        
        total_rows = len(rows) - 1
        type_name = obj.name or object_type
        
        progress_stages = [0.2, 0.4, 0.6, 0.8, 1.0]
        progress_stage_index = 0
        
        for idx, row in enumerate(rows[1:]):
            row_num = idx + 2
            
            if progress_callback and total_rows > 0:
                current_progress = (idx + 1) / total_rows
                while progress_stage_index < len(progress_stages) and current_progress >= progress_stages[progress_stage_index]:
                    stage_percent = int(type_progress_base + progress_stages[progress_stage_index] * type_progress_weight)
                    progress_callback({
                        'progress': min(99, stage_percent),
                        'current_type': object_type,
                        'current_type_name': type_name,
                        'total_types': 0,
                        'current_index': 0,
                        'message': '正在导入 {0}: {1}/{2} 行 ({3}%)'.format(
                            type_name, idx + 1, total_rows, int(progress_stages[progress_stage_index] * 100))
                    })
                    progress_stage_index += 1
            
            record = {}
            
            operation_mode = "create"
            if has_operation_mode and operation_mode_idx >= 0 and operation_mode_idx < len(row):
                mode_value = row[operation_mode_idx]
                if mode_value and str(mode_value).strip():
                    mode_str = str(mode_value).strip()
                    # 解析 "Key - Label" 格式（与 valuehelp 一致）
                    if ' - ' in mode_str:
                        key_part = mode_str.split(' - ')[0].strip().lower()
                    else:
                        key_part = mode_str.lower()
                    
                    if key_part in ["新增", "插入", "create", "insert"]:
                        operation_mode = "create"
                    elif key_part in ["删除", "delete"]:
                        operation_mode = "delete"
                    elif key_part in ["跳过", "skip"]:
                        operation_mode = "skip"
                    elif key_part in ["更新", "update"]:
                        operation_mode = "update"
                    else:
                        operation_mode = key_part
                else:
                    operation_mode = "create"
            
            for col_idx, header in enumerate(headers):
                if header == "操作模式":
                    continue
                if header and header in field_map:
                    field_id = field_map[header]
                    value = row[col_idx] if col_idx < len(row) else None
                    meta_field = obj.get_field(field_id)
                    if meta_field and value is not None:
                        value = self._convert_value(value, meta_field)
                    record[field_id] = value
            
            for parent_header, parent_info in parent_key_headers.items():
                parent_code_idx = headers.index(parent_header) if parent_header in headers else -1
                logger.debug(f"[Import] 检查父对象列: header={parent_header}, idx={parent_code_idx}")
                if parent_code_idx >= 0 and parent_code_idx < len(row):
                    parent_code = row[parent_code_idx]
                    logger.debug(f"[Import] 父对象编码: {parent_header}={parent_code}")
                    if parent_code:
                        parent_id_field = parent_info["id_field"]
                        if parent_id_field not in record or record.get(parent_id_field) is None:
                            parent_obj = registry.get(parent_info["parent_type"])
                            if parent_obj:
                                # [SYMBOL] 性能优化：使用预加载的内存索引替代数据库查询
                                parent_record = self._find_from_index(lookup_index, parent_info["parent_type"], parent_code)
                                if parent_record:
                                    record[parent_id_field] = parent_record.get("id")
                                    logger.info(f"[Import] 解析父对象成功: {parent_id_field}={parent_record.get('id')}")
                                else:
                                    logger.warning(f"[Import] 未找到父对象: {parent_info['parent_type']}.code={parent_code}")
            
            # 外键解析：根据 resolve_from_field 和 resolve_to_object/resolve_to_field 自动解析外键ID
            # 借鉴 SAP @ObjectModel.foreignKey.association 注解
            # 支持两种模式：
            #   1. 静态模式: resolve_to_object = "business_object" （硬编码目标对象类型）
            #   2. 动态模式: resolve_to_field = "target_type"  （从同记录另一字段取目标类型，用于多态外键）
            for field in obj.fields:
                resolve_from = getattr(field.semantics, 'resolve_from_field', None)
                resolve_to_object = getattr(field.semantics, 'resolve_to_object', None)
                resolve_to_field = getattr(field.semantics, 'resolve_to_field', None)

                if not resolve_from and not resolve_to_object and not resolve_to_field:
                    vh = getattr(field, 'value_help', None)
                    if not vh:
                        ui_obj = getattr(field, 'ui', None)
                        if ui_obj:
                            vh = getattr(ui_obj, 'value_help', None)
                    if vh:
                        vh_source = getattr(vh, 'source', None)
                        if vh_source and getattr(vh_source, 'type', None) == 'bo':
                            resolve_to_object = getattr(vh_source, 'target_bo', None)
                            code_field = getattr(vh_source, 'code_field', None) or 'code'
                            if code_field and code_field != field.id:
                                resolve_from = code_field

                if resolve_from and (resolve_to_object or resolve_to_field):
                    if field.id not in record or record.get(field.id) is None:
                        source_value = record.get(resolve_from)
                        if source_value:
                            if resolve_to_field:
                                dynamic_type = record.get(resolve_to_field)
                                if dynamic_type:
                                    # [SYMBOL] 性能优化：使用预加载的内存索引
                                    target_record = self._find_from_index(lookup_index, dynamic_type, source_value)
                                    if target_record:
                                        record[field.id] = target_record.get('id')
                                        logger.info(f"[Import] 动态外键解析成功: {field.id}={record[field.id]} ({dynamic_type}.code={source_value})")
                                    else:
                                        logger.warning(f"[Import] 未找到动态外键对象: {dynamic_type}.code={source_value}")
                                else:
                                    logger.warning(f"[Import] 动态外键类型字段为空: resolve_to_field={resolve_to_field}")
                            elif resolve_to_object:
                                # [SYMBOL] 性能优化：使用预加载的内存索引
                                target_record = self._find_from_index(lookup_index, resolve_to_object, source_value)
                                if target_record:
                                    record[field.id] = target_record.get('id')
                                else:
                                    logger.warning(f"[Import] 未找到外键对象: {resolve_to_object}.code={source_value}")
            
            record = self._filter_import_record(record, obj, operation_mode)

            if context:
                valid_fields = set()
                for f in obj.fields:
                    valid_fields.add(f.id)

                logger.info(f"[Import] context before adding to record: version_id={context.get('version_id')}")
                logger.info(f"[Import] valid_fields includes 'version_id': {'version_id' in valid_fields}")

                for ctx_key, ctx_value in context.items():
                    if ctx_key in valid_fields and ctx_key not in record:
                        logger.info(f"[Import] 添加context字段到record: {ctx_key}={ctx_value}")
                        record[ctx_key] = ctx_value

            logger.info(f"[Import] 最终record中的version_id: {record.get('version_id')}")
            logger.info(f"[Import] operation_mode={operation_mode}, conflict_strategy={conflict_strategy}")

            # [SYMBOL] 关键修复：如果record中没有version_id但context中有，强制添加
            if record.get('version_id') is None and context.get('version_id') is not None:
                logger.info(f"[Import] [SYMBOL] 强制添加version_id={context.get('version_id')}到record")
                record['version_id'] = context.get('version_id')

            try:
                if operation_mode == "delete":
                    logger.info(f"[Import] 执行删除操作")
                    self._delete_record(object_type, record, obj.import_export)
                    deleted_count += 1
                    success_count += 1
                elif operation_mode == "skip":
                    logger.info(f"[Import] 跳过记录")
                    skipped_count += 1
                    continue
                elif operation_mode == "create":
                    logger.info(f"[Import] 执行新增操作")
                    if 'version_id' not in record and context.get('version_id'):
                        record['version_id'] = context.get('version_id')
                    logger.info(f"[Import] 新增数据中version_id={record.get('version_id')}")
                    if conflict_strategy == "upsert":
                        logger.info(f"[Import] conflict_strategy=upsert，使用 upsert 处理可能已存在的记录")
                        if self._upsert_record(object_type, record, obj.import_export):
                            success_count += 1
                        else:
                            failed_count += 1
                            errors.append({"row": row_num, "error": "Upsert failed"})
                    else:
                        self.manage_service.create(CreateRequest(object_type=object_type, data=record))
                        success_count += 1
                elif operation_mode == "update":
                    # [SYMBOL] 关键修复：如果 conflict_strategy=upsert，执行 upsert 而不是更新
                    if conflict_strategy == "upsert":
                        logger.info(f"[Import] 执行upsert操作 (operation_mode=update 但 conflict_strategy=upsert)")
                        if 'version_id' not in record and context.get('version_id'):
                            record['version_id'] = context.get('version_id')
                        if self._upsert_record(object_type, record, obj.import_export):
                            success_count += 1
                        else:
                            failed_count += 1
                    else:
                        logger.info(f"[Import] 执行更新操作")
                        self._update_record(object_type, record, obj.import_export)
                        success_count += 1
                else:
                    logger.info(f"[Import] 执行upsert操作 (conflict_strategy={conflict_strategy})")
                    # [SYMBOL] 确保version_id存在
                    if 'version_id' not in record and context.get('version_id'):
                        record['version_id'] = context.get('version_id')
                    logger.info(f"[Import] upsert数据中version_id={record.get('version_id')}")
                    if conflict_strategy == "upsert":
                        if self._upsert_record(object_type, record, obj.import_export):
                            success_count += 1
                        else:
                            failed_count += 1
                    elif conflict_strategy == "skip":
                        if self._record_exists(object_type, record, obj.import_export):
                            logger.info(f"[Import] 记录已存在，跳过")
                            skipped_count += 1
                            continue
                        result = self.manage_service.create(CreateRequest(object_type=object_type, data=record))
                        if result.success:
                            success_count += 1
                        else:
                            failed_count += 1
                    else:
                        result = self.manage_service.create(CreateRequest(object_type=object_type, data=record))
                        if result.success:
                            success_count += 1
                        else:
                            failed_count += 1

            except Exception as e:
                logger.error(f"[Import] ERROR: Operation failed - {type(e).__name__}: {str(e)}")
                failed_count += 1
                errors.append({
                    "row": row_num,
                    "operation": operation_mode,
                    "message": f"{type(e).__name__}: {str(e)}"
                })

        logger.info(f"[Import] 导入完成: success={success_count}, failed={failed_count}, skipped={skipped_count}, deleted={deleted_count}")
        logger.info(f"[Import] errors: {errors[:5]}")
        
        return {
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "deleted": deleted_count,
            "errors": errors[:20]
        }

    def _get_business_key_fields(self, object_type: str) -> List:
        """获取对象的业务键字段列表（支持组合键）"""
        obj = registry.get(object_type)
        if not obj:
            return []
        
        bk_fields = []
        for field in obj.fields:
            if getattr(field.semantics, 'business_key', False):
                is_virtual = field.storage.value == 'virtual' or getattr(field.semantics, 'virtual', False)
                if not is_virtual:
                    bk_fields.append(field)
        return bk_fields

    def _find_existing_record(self, object_type: str, record: Dict[str, Any],
                               version_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """根据业务键或conflict_key查找现有记录（支持组合键）

        Args:
            object_type: 对象类型
            record: 记录数据
            version_id: 版本ID，如果指定则只在该版本内查找
        """
        obj = registry.get(object_type)
        conflict_key = ""
        if obj and obj.import_export and obj.import_export.conflict_key:
            conflict_key = obj.import_export.conflict_key

        if conflict_key:
            key_value = record.get(conflict_key)
            if key_value is not None:
                return self._find_by_key(object_type, conflict_key, key_value, version_id)
            return None

        bk_fields = self._get_business_key_fields(object_type)

        if not bk_fields:
            record_id = record.get('id')
            if record_id is not None:
                return self._find_by_id(object_type, record_id)
            return None

        if len(bk_fields) == 1:
            key_value = record.get(bk_fields[0].id)
            if key_value is None:
                return None
            # [SYMBOL] 传入 version_id，只在指定版本内查找
            return self._find_by_key(object_type, bk_fields[0].id, key_value, version_id)
        else:
            key_values = []
            for bk_field in bk_fields:
                key_values.append(record.get(bk_field.id))

            if all(v is None for v in key_values):
                return None

            # [SYMBOL] 传入 version_id，只在指定版本内查找
            return self._find_by_composite_key(object_type, bk_fields, key_values, version_id)

    def _delete_record(self, object_type: str, record: Dict[str, Any], config: ImportExportConfig):
        """删除记录"""
        # 从record中获取version_id
        version_id = record.get('version_id')
        existing = self._find_existing_record(object_type, record, version_id)

        if existing:
            self.manage_service.delete(DeleteRequest(object_type=object_type, id=existing["id"]))
        else:
            bk_fields = self._get_business_key_fields(object_type)
            if bk_fields:
                key_desc = ", ".join(["{0}={1}".format(f.id, record.get(f.id)) for f in bk_fields])
            else:
                key_desc = "无业务键"
            raise ValueError("要删除的记录不存在: {0}".format(key_desc))

    def _update_record(self, object_type: str, record: Dict[str, Any], config: ImportExportConfig):
        """更新记录（仅更新，不存在则报错）"""
        # 从record中获取version_id
        version_id = record.get('version_id')
        existing = self._find_existing_record(object_type, record, version_id)

        if existing:
            self.manage_service.update(UpdateRequest(object_type=object_type, id=existing["id"], data=record))
        else:
            bk_fields = self._get_business_key_fields(object_type)
            if bk_fields:
                key_desc = ", ".join(["{0}={1}".format(f.id, record.get(f.id)) for f in bk_fields])
            else:
                key_desc = "无业务键"
            raise ValueError("要更新的记录不存在: {0}".format(key_desc))

    def _upsert_record(self, object_type: str, record: Dict[str, Any],
                       config: ImportExportConfig) -> bool:
        """Upsert记录：存在则更新，不存在则插入
        
        Returns:
            bool: 操作是否成功
        """
        import logging
        logger = logging.getLogger(__name__)

        record_version_id = record.get('version_id')
        logger.info(f"[Upsert] object_type={object_type}, record_version_id={record_version_id}")
        logger.info(f"[Upsert] record keys: {list(record.keys())}")

        # [SYMBOL] 关键修复：传入 version_id，只在当前版本查找
        existing = self._find_existing_record(object_type, record, record_version_id)

        if existing:
            existing_version_id = existing.get('version_id')
            record_id = existing.get("id")
            logger.info(f"[Upsert] 找到已存在记录: id={record_id}, version_id={existing_version_id}")
            logger.info(f"[Upsert] 将执行更新操作...")

            # [SYMBOL] 关键修复：确保 UPDATE 时 version_id 也被设置
            if record_version_id is not None:
                record['version_id'] = record_version_id
                logger.info(f"[Upsert] 强制设置 record.version_id={record_version_id}")

            result = self.manage_service.update(UpdateRequest(object_type=object_type, id=record_id, data=record))
            return result.success
        else:
            logger.info(f"[Upsert] 未找到已存在记录，将执行插入操作")
            if 'version_id' not in record:
                logger.warning(f"[Upsert] [WARNING] record中没有version_id！")
            else:
                logger.info(f"[Upsert] record.version_id={record_version_id}")
            result = self.manage_service.create(CreateRequest(object_type=object_type, data=record))
            if not result.success:
                logger.warning(f"[Upsert] 创建失败: {result.error} - {result.message}")
            return result.success

    def _record_exists(self, object_type: str, record: Dict[str, Any],
                       config: ImportExportConfig) -> bool:
        """检查记录是否存在"""
        return self._find_existing_record(object_type, record) is not None

    def _find_by_id(self, object_type: str, record_id: Any) -> Optional[Dict[str, Any]]:
        """根据 id 查找记录（用于无业务键的导入对象，如 annotation）"""
        try:
            obj = registry.get(object_type)
            if not obj:
                return None
            table_name = obj.table_name or object_type
            sql = "SELECT * FROM {0} WHERE id = ?".format(table_name)
            cursor = self.data_source.execute(sql, (record_id,))
            result = cursor.fetchone()
            if result:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, result))
            return None
        except Exception:
            return None

    def _find_by_key(self, object_type: str, key_field: str, key_value: Any,
                      version_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """根据关键字段查找记录

        Args:
            object_type: 对象类型
            key_field: 关键字段名
            key_value: 关键字段值
            version_id: 版本ID，如果指定则只在该版本内查找
        """
        try:
            conditions = [QueryCondition(field=key_field, operator="eq", value=key_value)]

            if version_id is not None and self._object_has_field(object_type, "version_id"):
                conditions.append(QueryCondition(field="version_id", operator="eq", value=version_id))

            search_request = SearchRequest(
                object_type=object_type,
                conditions=conditions,
                page=1,
                page_size=1,
            )
            result = self.query_service.search(search_request)
            return result.data[0] if result.data else None
        except Exception:
            return None

    def _find_by_composite_key(self, object_type: str, key_fields: List, key_values: List[str],
                                version_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """根据组合关键字段查找记录

        Args:
            object_type: 对象类型
            key_fields: 关键字段列表
            key_values: 关键字段值列表
            version_id: 版本ID，如果指定则只在该版本内查找
        """
        try:
            conditions = []
            for field, value in zip(key_fields, key_values):
                if value:
                    conditions.append(QueryCondition(field=field.id, operator="eq", value=value))

            if not conditions:
                return None

            if version_id is not None and self._object_has_field(object_type, "version_id"):
                conditions.append(QueryCondition(field="version_id", operator="eq", value=version_id))

            search_request = SearchRequest(
                object_type=object_type,
                conditions=conditions,
                page=1,
                page_size=1,
            )
            result = self.query_service.search(search_request)
            return result.data[0] if result.data else None
        except Exception:
            return None

    def _read_meta_sheet(self, file_path: str) -> Dict[str, str]:
        """从 Excel 文件的元数据 Sheet 读取上下文信息
        
        Args:
            file_path: Excel 文件路径
            
        Returns:
            dict: 包含 product_code, version_code, version_id 等信息的字典
        """
        meta = {}
        try:
            from openpyxl import load_workbook
            wb = load_workbook(file_path, read_only=True)
            
            if '元数据' in wb.sheetnames:
                ws = wb['元数据']
                for row in ws.iter_rows(min_row=1, max_row=10, max_col=2):
                    if row[0].value and row[1].value:
                        meta[str(row[0].value)] = str(row[1].value)
            
            wb.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to read meta sheet: {e}")
        
        return meta

    def _resolve_version_id(self, product_code: str, version_code: str) -> Optional[int]:
        """根据 product_code 和 version_code 解析 version_id
        
        Args:
            product_code: 产品编码
            version_code: 版本编码
            
        Returns:
            int: version_id，如果未找到返回 None
        """
        if not product_code or not version_code:
            return None
        
        try:
            query = """
                SELECT v.id
                FROM versions v
                LEFT JOIN products p ON v.product_id = p.id
                WHERE p.code = ? AND v.code = ?
                LIMIT 1
            """
            cursor = self.data_source.execute(query, (product_code, version_code))
            row = cursor.fetchone()
            if row:
                return row[0]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to resolve version_id: {e}")
        
        return None
