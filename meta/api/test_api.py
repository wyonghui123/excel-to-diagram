"""
测试辅助 API
提供健康检查、就绪状态等测试支持端点，无需认证
"""
import os
from flask import Blueprint, jsonify
from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path

test_bp = Blueprint('test', __name__, url_prefix='/api/v1/test')


@test_bp.route('/ready', methods=['GET'])
def ready():
    db_ok = False
    try:
        db_path = get_meta_db_path()
        ds = get_data_source("sqlite", database=db_path)
        ds.execute("SELECT 1", [])
        db_ok = True
    except Exception:
        pass

    return jsonify({
        'success': True,
        'ready': db_ok,
        'db': db_ok,
        'service': 'excel-to-diagram'
    })