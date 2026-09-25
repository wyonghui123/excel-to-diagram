# -*- coding: utf-8 -*-
"""warehouse 应用的 API（PoC 2）

挂载方式: 由 app_registry._register_blueprints() 挂到 /api/v1/apps/warehouse
（见 docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.4 / §6.7）

数据源取用遵循 §6.5 的统一出口:

    resolve_data_source(get_platform_data_source())

- `APP_DB_ROUTING=1` → 请求已被绑定到**本应用库**, 读到自己库的数据
- `APP_DB_ROUTING=0`（默认）→ 未绑定, 回落平台库（应用表所在库, 改造前行为）

本模块刻意不依赖平台重模块, 保证应用可独立演进。
"""
from flask import Blueprint, jsonify

# blueprint 名需全局唯一, 故加应用前缀
warehouse_bp = Blueprint("warehouse_inventory", __name__)


@warehouse_bp.route("/stock-summary", methods=["GET"])
def stock_summary():
    """库存汇总 —— 证明应用自定义 API 在路由下读的是自己的库。"""
    from meta.core.datasource import get_platform_data_source, resolve_data_source

    data_source = resolve_data_source(get_platform_data_source())
    rows = data_source.execute(
        "SELECT COUNT(*) AS item_count, COALESCE(SUM(quantity), 0) AS total_quantity "
        "FROM stock_items"
    ).fetchall()
    item_count, total_quantity = rows[0] if rows else (0, 0)

    return jsonify({
        "app": "warehouse",
        "item_count": item_count,
        "total_quantity": total_quantity,
    })


@warehouse_bp.route("/health", methods=["GET"])
def health():
    """应用健康检查。"""
    return jsonify({"app": "warehouse", "status": "ok"})