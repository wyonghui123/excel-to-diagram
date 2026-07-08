from flask import Blueprint, request, jsonify
from meta.services.auth_middleware import login_required, is_admin

audit_mgmt_bp = Blueprint('audit_mgmt', __name__, url_prefix='/api/v1')

_audit_service = None


def init_audit_mgmt_services(audit_service=None):
    global _audit_service
    _audit_service = audit_service


@audit_mgmt_bp.route('/audit/failed', methods=['GET'])
@login_required
def get_failed_audit_logs():
    if not is_admin():
        return jsonify({'success': False, 'message': '您没有执行此操作的权限，需要管理员权限'}), 403

    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    result = _audit_service.get_failed_audit_logs(page=page, page_size=page_size)

    return jsonify({
        'success': True,
        'data': result.get('data', []),
        'total': result.get('total', 0),
        'page': result.get('page', page),
        'page_size': result.get('page_size', page_size),
    })


@audit_mgmt_bp.route('/audit/failed/<int:record_id>/retry', methods=['POST'])
@login_required
def retry_failed_audit_log(record_id):
    if not is_admin():
        return jsonify({'success': False, 'message': '您没有执行此操作的权限，需要管理员权限'}), 403

    result = _audit_service.retry_failed_record(record_id)

    if result.get('success'):
        return jsonify({
            'success': True,
            'message': result.get('message', '重试成功'),
        })
    else:
        return jsonify({
            'success': False,
            'message': result.get('message', '重试失败'),
        }), 400


@audit_mgmt_bp.route('/audit/stats', methods=['GET'])
@login_required
def get_audit_writer_stats():
    if not is_admin():
        return jsonify({'success': False, 'message': '您没有执行此操作的权限，需要管理员权限'}), 403

    from meta.services.async_audit_writer import async_audit_writer
    stats = async_audit_writer.get_stats()

    return jsonify({
        'success': True,
        'data': stats,
    })
