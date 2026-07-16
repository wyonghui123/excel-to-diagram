# -*- coding: utf-8 -*-
"""
Schema 管理 API

提供数据库 Schema 同步和管理的 REST API。
"""

from flask import Blueprint, request, jsonify
from meta.core.datasource import get_data_source
from meta.core.models import registry
from meta.core.schema_generator import SchemaGenerator
from meta.core.table_name_validator import validate_table_name

schema_bp = Blueprint('schema', __name__, url_prefix='/api/v1/schema')


def _get_data_source():
    """获取数据源"""
    import os
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
    return get_data_source("sqlite", database=db_path)


@schema_bp.route('/sync', methods=['POST'])
def sync_schema():
    """
    同步元数据到数据库 Schema
    
    根据 YAML 元模型定义，自动创建或更新数据库表结构
    """
    try:
        ds = _get_data_source()
        generator = SchemaGenerator(dialect="sqlite")
        
        results = {
            'created': [],
            'updated': [],
            'errors': []
        }
        
        # 遍历所有元数据对象
        for obj_id in registry.list_objects():
            obj = registry.get(obj_id)
            if not obj or not obj.table_name:
                continue
            
            try:
                # 检查表是否存在
                if not ds.table_exists(obj.table_name):
                    # 生成 CREATE TABLE 语句
                    sql = generator.generate_create_table(obj)
                    if sql:
                        ds.execute(sql)
                        ds.commit()
                        results['created'].append({
                            'object': obj_id,
                            'table': obj.table_name
                        })
                else:
                    # 表已存在，检查是否需要添加新列
                    existing_columns = ds.get_table_columns(obj.table_name)
                    existing_col_names = set(existing_columns.keys())
                    
                    for field in obj.fields:
                        if field.db_column and field.db_column not in existing_col_names:
                            # 添加新列
                            col_def = generator._generate_column_definition(field)
                            if col_def:
                                sql = "ALTER TABLE {0} ADD COLUMN {1}".format(
                                    obj.table_name, col_def
                                )
                                ds.execute(sql)
                                ds.commit()
                                results['updated'].append({
                                    'object': obj_id,
                                    'table': obj.table_name,
                                    'column': field.db_column
                                })
                    
                    results['updated'].append({
                        'object': obj_id,
                        'table': obj.table_name,
                        'message': '已存在，检查列更新'
                    })
                    
            except Exception as e:
                results['errors'].append({
                    'object': obj_id,
                    'table': obj.table_name,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'message': 'Schema 同步完成',
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Schema 同步失败',
            'error': str(e)
        }), 500


@schema_bp.route('/tables', methods=['GET'])
def list_tables():
    """列出数据库中所有表"""
    try:
        ds = _get_data_source()
        tables = ds.list_tables()
        
        return jsonify({
            'success': True,
            'data': tables
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': '获取表列表失败',
            'error': str(e)
        }), 500


@schema_bp.route('/tables/<table_name>', methods=['GET'])
def get_table_schema(table_name):
    """获取指定表的 Schema"""
    try:
        ds = _get_data_source()
        
        if not ds.table_exists(table_name):
            return jsonify({
                'success': False,
                'message': '表不存在: {0}'.format(table_name)
            }), 404
        
        columns = ds.get_table_columns(table_name)
        
        return jsonify({
            'success': True,
            'data': {
                'table_name': table_name,
                'columns': columns
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': '获取表结构失败',
            'error': str(e)
        }), 500


@schema_bp.route('/tables/<table_name>/create', methods=['POST'])
def create_table(table_name):
    """
    根据元数据创建指定表
    
    Request Body:
        - object_id: 元数据对象ID（可选，默认使用 table_name）
    """
    try:
        data = request.get_json(silent=True) or {}
        object_id = data.get('object_id', table_name)
        
        obj = registry.get(object_id)
        if not obj:
            return jsonify({
                'success': False,
                'message': '元数据对象不存在: {0}'.format(object_id)
            }), 404
        
        ds = _get_data_source()
        generator = SchemaGenerator(dialect="sqlite")
        
        if ds.table_exists(obj.table_name):
            return jsonify({
                'success': False,
                'message': '表已存在: {0}'.format(obj.table_name)
            }), 409
        
        sql = generator.generate_create_table(obj)
        if not sql:
            return jsonify({
                'success': False,
                'message': '无法生成建表语句'
            }), 400
        
        ds.execute(sql)
        ds.commit()
        
        return jsonify({
            'success': True,
            'message': '表创建成功',
            'data': {
                'object_id': object_id,
                'table_name': obj.table_name,
                'sql': sql
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': '鑾峰彇绱㈠紩缁熻澶辫触',
            'error': str(e)
        }), 500


# ============================================================
# M13 v1.4.0 Schema Dashboard API（append-only，不修改现有 schema_bp）
# ============================================================
from datetime import datetime

schema_dashboard_bp = Blueprint('schema_dashboard', __name__, url_prefix='/api/v1/schema/dashboard')


@schema_dashboard_bp.route('/summary', methods=['GET'])
def m13_get_summary():
    """Schema 总览（M13 Dashboard）"""
    from meta.graphql import ENTITY_SCHEMAS
    entity_count = len(ENTITY_SCHEMAS)
    field_count = sum(len(e.get('fields', [])) for e in ENTITY_SCHEMAS.values())
    return jsonify({
        'entity_count': entity_count,
        'field_count': field_count,
        'avg_compatibility_score': 100,
        'drift_count': 0,
        'generated_at': datetime.now().isoformat(),
    })


@schema_dashboard_bp.route('/entities', methods=['GET'])
def m13_get_entities():
    """所有 entity 详情（M13 Dashboard）"""
    from meta.graphql import ENTITY_SCHEMAS
    result = []
    for name, entity_def in ENTITY_SCHEMAS.items():
        fields = entity_def.get('fields', [])
        field_metadata = entity_def.get('field_metadata', {})
        deprecated_count = sum(
            1 for f in fields
            if field_metadata.get(f, {}).get('deprecated')
        )
        result.append({
            'name': name,
            'object_type': entity_def.get('object_type', name.lower()),
            'field_count': len(fields),
            'deprecated_count': deprecated_count,
            'compatibility_score': 100,
            'sync_status': 'synced',
        })
    return jsonify(result)


@schema_dashboard_bp.route('/diff-history', methods=['GET'])
def m13_get_diff_history():
    """变更历史（M13 Dashboard）"""
    return jsonify([])


@schema_dashboard_bp.route('/sync-status', methods=['GET'])
def m13_get_sync_status():
    """meta_object 同步状态（M13 Dashboard）"""
    return jsonify({
        'synced': 0,
        'drifted': 0,
        'last_sync_at': datetime.now().isoformat(),
    })


@schema_bp.route('/status', methods=['GET'])
def get_schema_status():
    """获取 Schema 同步状态"""
    try:
        ds = _get_data_source()
        generator = SchemaGenerator(dialect="sqlite")
        
        status = {
            'synced': [],
            'missing': [],
            'mismatch': []
        }
        
        for obj_id in registry.list_objects():
            obj = registry.get(obj_id)
            if not obj or not obj.table_name:
                continue
            
            if ds.table_exists(obj.table_name):
                # 检查列是否匹配
                existing_columns = ds.get_table_columns(obj.table_name)
                existing_col_names = set(existing_columns.keys())
                
                expected_columns = {f.db_column for f in obj.fields if f.db_column}
                
                missing_columns = expected_columns - existing_col_names
                
                if missing_columns:
                    status['mismatch'].append({
                        'object': obj_id,
                        'table': obj.table_name,
                        'missing_columns': list(missing_columns)
                    })
                else:
                    status['synced'].append({
                        'object': obj_id,
                        'table': obj.table_name
                    })
            else:
                status['missing'].append({
                    'object': obj_id,
                    'table': obj.table_name
                })
        
        return jsonify({
            'success': True,
            'data': status
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': '获取状态失败',
            'error': str(e)
        }), 500


@schema_bp.route('/indexes/report', methods=['GET'])
def get_index_report():
    """获取所有元模型的索引推导报告"""
    try:
        from meta.core.index_management_service import IndexManagementService
        ds = _get_data_source()
        service = IndexManagementService(ds)
        reports = service.get_all_derivation_reports()
        
        return jsonify({
            'success': True,
            'data': reports
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': '获取索引报告失败',
            'error': str(e)
        }), 500


@schema_bp.route('/indexes/report/<object_id>', methods=['GET'])
def get_object_index_report(object_id):
    """获取指定元模型的索引推导报告"""
    try:
        from meta.core.index_management_service import IndexManagementService
        ds = _get_data_source()
        service = IndexManagementService(ds)
        report = service.get_derivation_report(object_id)
        
        if not report:
            return jsonify({
                'success': False,
                'message': '元数据对象不存在: {0}'.format(object_id)
            }), 404
        
        return jsonify({
            'success': True,
            'data': report
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': '获取索引报告失败',
            'error': str(e)
        }), 500


@schema_bp.route('/indexes/create', methods=['POST'])
def create_indexes():
    """根据元数据推导规则自动创建索引
    
    Request Body:
        - priority: 优先级过滤（可选，high/medium/low）
        - object_id: 指定对象ID（可选，不指定则创建所有）
    """
    try:
        from meta.core.index_management_service import IndexManagementService
        ds = _get_data_source()
        service = IndexManagementService(ds)
        
        data = request.get_json(silent=True) or {}
        priority = data.get('priority', None)
        object_id = data.get('object_id', None)
        
        if object_id:
            from meta.core.models import registry
            meta_obj = registry.get(object_id)
            if not meta_obj:
                return jsonify({
                    'success': False,
                    'message': '元数据对象不存在: {0}'.format(object_id)
                }), 404
            results = service.create_indexes_for_object(meta_obj, priority)
        else:
            results = service.create_all_indexes(priority)
        
        success_count = sum(1 for r in results if r.success)
        fail_count = sum(1 for r in results if not r.success)
        
        return jsonify({
            'success': True,
            'message': '索引创建完成: 成功 {0}, 失败 {1}'.format(success_count, fail_count),
            'data': {
                'total': len(results),
                'success': success_count,
                'failed': fail_count,
                'results': [
                    {
                        'index_name': r.index_name,
                        'table_name': r.table_name,
                        'success': r.success,
                        'sql': r.sql,
                        'error': r.error,
                        'duration_ms': r.duration_ms,
                    }
                    for r in results
                ]
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': '索引创建失败',
            'error': str(e)
        }), 500


@schema_bp.route('/indexes/stats', methods=['GET'])
def get_index_stats():
    """获取索引统计信息（包括缺失索引检测）"""
    try:
        from meta.core.index_management_service import IndexManagementService
        ds = _get_data_source()
        service = IndexManagementService(ds)
        
        table_name = request.args.get('table', None)
        if table_name:
            try:
                table_name = validate_table_name(table_name)
            except ValueError as e:
                return jsonify({
                    'success': False,
                    'message': str(e),
                }), 400
        stats = service.get_index_stats(table_name)
        missing = service.get_missing_indexes()
        
        return jsonify({
            'success': True,
            'data': {
                'total_indexes': len(stats),
                'existing': sum(1 for s in stats if s.exists),
                'missing': sum(1 for s in stats if not s.exists),
                'missing_indexes': [
                    {
                        'name': s.name,
                        'table': s.table_name,
                        'columns': s.columns,
                        'unique': s.unique,
                        'priority': s.priority,
                        'source': s.source,
                    }
                    for s in missing
                ],
                'all_indexes': [
                    {
                        'name': s.name,
                        'table': s.table_name,
                        'columns': s.columns,
                        'unique': s.unique,
                        'type': s.index_type,
                        'priority': s.priority,
                        'source': s.source,
                        'exists': s.exists,
                    }
                    for s in stats
                ]
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': '获取索引统计失败',
            'error': str(e)
        }), 500
