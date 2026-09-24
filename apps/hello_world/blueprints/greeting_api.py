# -*- coding: utf-8 -*-
"""hello_world 应用的 API（PoC 1）

挂载方式: 由 ApplicationBuilder.with_app() 挂到 /api/v1/apps/hello_world
（见 docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.4 / §6.7）

本模块刻意不依赖平台内部模块, 保证应用可独立演进。
"""
from flask import Blueprint, jsonify

# blueprint 名需全局唯一, 故加应用前缀
greeting_bp = Blueprint("hello_world_greeting", __name__)


@greeting_bp.route("/greetings", methods=["GET"])
def list_greetings():
    """列出问候语（PoC 占位实现）。"""
    return jsonify({"app": "hello_world", "items": []})


@greeting_bp.route("/health", methods=["GET"])
def health():
    """应用健康检查。"""
    return jsonify({"app": "hello_world", "status": "ok"})
