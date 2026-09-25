# -*- coding: utf-8 -*-
"""[PoC 4] tms 应用的自定义 API。

除健康检查外，暴露运单查询，便于端到端验证"WMS 出库 → TMS 有运单"。
"""
from flask import Blueprint, jsonify

dispatch_bp = Blueprint("tms_dispatch", __name__)


@dispatch_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"app": "tms", "status": "ok"})


@dispatch_bp.route("/waybills", methods=["GET"])
def list_waybills():
    """读本应用库的运单（消费结果的可观测出口）。"""
    from meta.core.datasource import get_platform_data_source, resolve_data_source

    data_source = resolve_data_source(get_platform_data_source())
    rows = data_source.execute(
        "SELECT waybill_no, order_no, quantity, status FROM waybills ORDER BY id"
    ).fetchall()
    return jsonify({
        "app": "tms",
        "count": len(rows),
        "waybills": [
            {"waybill_no": r[0], "order_no": r[1], "quantity": r[2], "status": r[3]}
            for r in rows
        ],
    })