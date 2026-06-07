# -*- coding: utf-8 -*-
"""
{API名称} API

功能描述：
"""

from flask import Blueprint, request, jsonify
from meta.core.datasource import get_data_source
import os

{api_name}_bp = Blueprint('{api_name}', __name__, url_prefix='/api/v1/{api_name}')

_data_source = None
_service = None


def init_services(data_source=None):
    """
    初始化服务 - 使用绝对路径获取数据库
    
    [WARNING] 重要：必须使用以下方式获取数据库路径，禁止使用相对路径！
    
    正确：
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    
    错误：
        _data_source = get_data_source("sqlite", database="meta/architecture.db")
        _data_source = get_data_source("sqlite", database="architecture.db")
    """
    global _data_source, _service
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    # _service = YourService(_data_source)


def _get_service():
    if _service is None:
        init_services()
    return _service


@{api_name}_bp.route('/example', methods=['GET'])
def example():
    """示例接口"""
    return jsonify({
        "success": True,
        "message": "API模板示例"
    })


# ============================================================
# 复制模板时请删除以下注释内容
# ============================================================
# 
# 创建新 API 的步骤：
# 
# 1. 复制此文件并重命名
# 2. 替换以下占位符：
#    - {API名称} → 你的API名称（如：产品管理）
#    - {api_name} → 你的API名称小写（如：product）
# 3. 删除这行注释
# 4. 在 server.py 中注册蓝图：
#    from meta.api.{api_name}_api import {api_name}_bp
#    app.register_blueprint({api_name}_bp)
# 
# [WARNING] 重要：数据库路径必须使用以下方式：
# 
#    db_path = os.path.join(
#        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
#        'architecture.db'
#    )
# 
# 禁止使用：
#    - "meta/architecture.db"
#    - "architecture.db"
#    - 任何相对路径
# 
# ============================================================
