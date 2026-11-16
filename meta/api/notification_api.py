# -*- coding: utf-8 -*-
"""
变更通知 API

提供 WebSocket 端点支持实时推送变更事件。
提供订阅管理 API。
"""

from flask import Blueprint, request, jsonify
from meta.api._response_contract import error_response, ok, ok_message
from meta.core.query_spec import parse_query_spec
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging
import json
import time
from datetime import datetime

from meta.services.websocket_manager import websocket_manager
from meta.services.token_service import TokenService
from meta.services.auth_middleware import login_required, get_current_user, is_admin
from meta.core.change_event_types import normalize as normalize_event_type

logger = logging.getLogger(__name__)

notification_bp = Blueprint('notification', __name__, url_prefix='/api/v1/notifications')

#: 与 change_subscriptions DDL 的 chk_channel 保持一致
SUBSCRIPTION_CHANNELS = ('in_app', 'email', 'webhook', 'sms')

socketio = None
ds = None

#: 手动重试去抖窗口（秒）：同一用户对同一事件的重复点击只产生一次新尝试
RETRY_DEBOUNCE_SECONDS = 5
_retry_debounce = {}


def _can_retry_all(user):
    """是否具备跨订阅重试权限（管理员或 notification:retry:all）。"""
    if is_admin(user):
        return True
    permissions = (user or {}).get('permissions') or []
    if isinstance(permissions, str):
        permissions = [permissions]
    return 'notification:retry:all' in permissions


def _same_user(left, right):
    """比较用户 id（token 里可能是字符串，DB 里是整数）。"""
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return left == right


def _current_user_id():
    """当前登录用户 id（鉴权中间件只写 g.current_user，不写 g.user_id）。"""
    user = get_current_user() or {}
    return user.get('user_id')


def _visible_object_types(user_id):
    """事件读取隔离（P1-b）：非管理员仅可见自己收件箱中出现过的 object_type。

    返回 None 表示不限制（管理员）；返回空集合表示无任何可见事件。
    """
    if is_admin(get_current_user()):
        return None
    rows = ds.execute(
        'SELECT DISTINCT object_type FROM notification_inbox WHERE user_id = ?',
        (user_id,)
    ).fetchall() or []
    return {row[0] for row in rows if row and row[0]}


def _inbox_service():
    from meta.services.notification_inbox_service import NotificationInboxService
    return NotificationInboxService(ds)


def init_notification_api(datasource):
    """初始化通知 API"""
    global ds
    ds = datasource


def init_socketio(app):
    """初始化 SocketIO"""
    global socketio
    
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode='threading',
        ping_timeout=60,
        ping_interval=25
    )
    
    websocket_manager.init_socketio(socketio)
    
    @socketio.on('connect')
    def handle_connect():
        """处理客户端连接"""
        from flask_socketio import request as socket_request

        token = socket_request.cookies.get('auth_token', '')
        if not token:
            token = socket_request.args.get('token', '')
        if not token:
            auth_header = socket_request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]

        if not token:
            logger.warning("Connection rejected: no token provided")
            return False
        
        try:
            user_info = TokenService.verify_token(token)
            if not user_info:
                logger.warning("Connection rejected: invalid token")
                return False
            
            user_id = user_info.get('user_id') or user_info.get('sub')
            username = user_info.get('username', '')
            
            websocket_manager.register_client(
                sid=socket_request.sid,
                user_id=user_id,
                username=username
            )
            
            emit('connected', {
                'status': 'connected',
                'sid': socket_request.sid,
                'user_id': user_id
            })
            
            logger.info(f"Client connected: sid={socket_request.sid}, user_id={user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """处理客户端断开"""
        from flask_socketio import request as socket_request
        
        websocket_manager.unregister_client(socket_request.sid)
        logger.info(f"Client disconnected: sid={socket_request.sid}")
    
    @socketio.on('subscribe')
    def handle_subscribe(data):
        """处理订阅请求"""
        from flask_socketio import request as socket_request
        
        object_type = data.get('object_type')
        event_types = data.get('event_types', ['created', 'updated', 'deleted', 'state_changed'])
        if isinstance(event_types, list):
            event_types = [t for t in (normalize_event_type(x) for x in event_types) if t]
        
        if not object_type:
            emit('error', {'message': 'object_type is required'})
            return
        
        success = websocket_manager.subscribe(
            sid=socket_request.sid,
            object_type=object_type,
            event_types=event_types
        )
        
        if success:
            emit('subscribed', {
                'object_type': object_type,
                'event_types': event_types
            })
        else:
            emit('error', {'message': 'Subscription failed'})
    
    @socketio.on('unsubscribe')
    def handle_unsubscribe(data):
        """处理取消订阅"""
        from flask_socketio import request as socket_request
        
        object_type = data.get('object_type')
        
        success = websocket_manager.unsubscribe(
            sid=socket_request.sid,
            object_type=object_type
        )
        
        if success:
            emit('unsubscribed', {'object_type': object_type})
        else:
            emit('error', {'message': 'Unsubscribe failed'})
    
    @socketio.on('ping')
    def handle_ping():
        """处理心跳"""
        emit('pong', {'timestamp': __import__('datetime').datetime.now().isoformat()})
    
    return socketio


@notification_bp.route('/stats', methods=['GET'])
@login_required
def get_stats():
    """获取 WebSocket 连接统计（仅管理员）"""
    if not is_admin(get_current_user()):
        return error_response('您没有执行此操作的权限', status=403)
    return ok(websocket_manager.get_stats())


@notification_bp.route('/subscriptions', methods=['GET'])
@login_required
def get_subscriptions():
    """获取当前用户的订阅列表"""
    user_id = _current_user_id()

    if not ds:
        stats = websocket_manager.get_stats()
        user_clients = [
            c for c in stats.get('clients', [])
            if c.get('user_id') == user_id
        ]
        return jsonify({
            'success': True,
            'data': user_clients
        })
    
    subscriptions = ds.find(
        'change_subscriptions',
        filters={'user_id': user_id},
        order_by='created_at DESC'
    )
    
    return jsonify({
        'success': True,
        'data': subscriptions or []
    })


@notification_bp.route('/subscriptions', methods=['POST'])
@login_required
def create_subscription():
    """创建订阅"""
    user_id = _current_user_id()

    if not ds:
        return error_response('Service not initialized', status=500)
    
    data = request.get_json() or {}
    
    object_type = data.get('object_type')
    event_types = data.get('event_types', ['created', 'updated', 'deleted', 'state_changed'])
    if isinstance(event_types, list):
        event_types = [t for t in (normalize_event_type(x) for x in event_types) if t]
    channel = data.get('channel', 'in_app')
    webhook_url = data.get('webhook_url', '')
    webhook_secret = data.get('webhook_secret', '')
    filter_condition = data.get('filter_condition', {})

    # FR-2：订阅可引用集成连接（connection_id），投递目标以连接的 endpoint/secret 为准
    connection_id = data.get('connection_id')
    if connection_id in (None, ''):
        connection_id = None
    else:
        try:
            connection_id = int(connection_id)
        except (TypeError, ValueError):
            return error_response('connection_id 必须为整数', status=400)
        if not ds.find_by_id('integration_connection', connection_id):
            return error_response('connection_id 对应的连接不存在', status=400)
    
    if not object_type:
        return error_response('object_type is required')

    if channel not in SUBSCRIPTION_CHANNELS:
        return error_response(
            f"channel 必须是 {'/'.join(SUBSCRIPTION_CHANNELS)} 之一",
            status=400
        )

    if channel == 'webhook' and not webhook_url and connection_id is None:
        return error_response('webhook channel 需要 webhook_url 或 connection_id')
    
    subscription = {
        'user_id': user_id,
        'object_type': object_type,
        'event_types': json.dumps(event_types) if isinstance(event_types, list) else event_types,
        'channel': channel,
        'webhook_url': webhook_url,
        'webhook_secret': webhook_secret,
        'filter_condition': json.dumps(filter_condition) if filter_condition else '{}',
        'enabled': 1,
        'created_at': datetime.now().isoformat()
    }
    if connection_id is not None:
        subscription['connection_id'] = connection_id
    
    try:
        sub_id = ds.insert('change_subscriptions', subscription)
        subscription['id'] = sub_id
        
        logger.info(
            "Subscription created: id=%s, user_id=%s, object_type=%s, channel=%s",
            sub_id, user_id, object_type, channel
        )
        
        return ok(subscription), 201
        
    except Exception as e:
        logger.error("Failed to create subscription: %s", e)
        return error_response(str(e), status=500)


@notification_bp.route('/subscriptions/<int:sub_id>', methods=['GET'])
@login_required
def get_subscription(sub_id):
    """获取单个订阅详情"""
    user_id = _current_user_id()

    if not ds:
        return error_response('Service not initialized', status=500)
    
    subscription = ds.find_by_id('change_subscriptions', sub_id)
    
    if not subscription:
        return error_response('订阅不存在', status=404)
    
    if subscription.get('user_id') != user_id:
        return error_response('您没有执行此操作的权限', status=403)
    
    return ok(subscription)


@notification_bp.route('/subscriptions/<int:sub_id>', methods=['PUT'])
@login_required
def update_subscription(sub_id):
    """更新订阅"""
    user_id = _current_user_id()

    if not ds:
        return error_response('Service not initialized', status=500)
    
    subscription = ds.find_by_id('change_subscriptions', sub_id)
    
    if not subscription:
        return error_response('订阅不存在', status=404)
    
    if subscription.get('user_id') != user_id:
        return error_response('您没有执行此操作的权限', status=403)
    
    data = request.get_json() or {}
    
    update_data = {}
    
    # FR-2：允许绑定/解绑集成连接（connection_id=null 表示解绑）
    if 'connection_id' in data:
        raw_conn = data.get('connection_id')
        if raw_conn in (None, ''):
            update_data['connection_id'] = None
        else:
            try:
                conn_id = int(raw_conn)
            except (TypeError, ValueError):
                return error_response('connection_id 必须为整数', status=400)
            if not ds.find_by_id('integration_connection', conn_id):
                return error_response('connection_id 对应的连接不存在', status=400)
            update_data['connection_id'] = conn_id
    
    if 'event_types' in data:
        event_types = data['event_types']
        if isinstance(event_types, list):
            event_types = [t for t in (normalize_event_type(x) for x in event_types) if t]
        update_data['event_types'] = json.dumps(event_types) if isinstance(event_types, list) else event_types
    
    if 'channel' in data:
        update_data['channel'] = data['channel']
    
    if 'webhook_url' in data:
        update_data['webhook_url'] = data['webhook_url']
    
    if 'webhook_secret' in data:
        update_data['webhook_secret'] = data['webhook_secret']
    
    if 'filter_condition' in data:
        filter_condition = data['filter_condition']
        update_data['filter_condition'] = json.dumps(filter_condition) if filter_condition else '{}'
    
    if 'enabled' in data:
        update_data['enabled'] = 1 if data['enabled'] else 0
    
    if not update_data:
        return error_response('No fields to update')
    
    try:
        ds.update('change_subscriptions', sub_id, update_data)
        
        logger.info("Subscription updated: id=%s", sub_id)
        
        updated = ds.find_by_id('change_subscriptions', sub_id)
        
        return ok(updated)
        
    except Exception as e:
        logger.error("Failed to update subscription: %s", e)
        return error_response(str(e), status=500)


@notification_bp.route('/subscriptions/<int:sub_id>', methods=['DELETE'])
@login_required
def delete_subscription(sub_id):
    """删除订阅"""
    user_id = _current_user_id()

    if not ds:
        return error_response('Service not initialized', status=500)
    
    subscription = ds.find_by_id('change_subscriptions', sub_id)
    
    if not subscription:
        return error_response('订阅不存在', status=404)
    
    if subscription.get('user_id') != user_id:
        return error_response('您没有执行此操作的权限', status=403)
    
    try:
        ds.delete('change_subscriptions', sub_id)
        
        logger.info("Subscription deleted: id=%s", sub_id)
        
        return ok_message('Subscription deleted')
        
    except Exception as e:
        logger.error("Failed to delete subscription: %s", e)
        return error_response(str(e), status=500)


@notification_bp.route('/events', methods=['GET'])
@login_required
def get_events():
    """获取变更事件列表（按用户可见范围隔离）"""
    if not ds:
        return error_response('Service not initialized', status=500)

    visible = _visible_object_types(_current_user_id())

    object_type = request.args.get('object_type')
    status = request.args.get('status')
    spec = parse_query_spec(request.args)
    page, page_size = spec.page, spec.page_size

    filters = {}
    if object_type:
        if visible is not None and object_type not in visible:
            return error_response('您没有执行此操作的权限', status=403)
        filters['object_type'] = object_type
    elif visible is not None:
        if not visible:
            return jsonify({
                'success': True,
                'data': [],
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': 0
                }
            })
        filters['object_type__in'] = sorted(visible)
    if status:
        filters['status'] = status
    
    events = ds.find(
        'change_events',
        filters=filters,
        order_by='created_at DESC',
        limit=page_size,
        offset=(page - 1) * page_size
    )
    
    total = ds.count('change_events', filters=filters)
    
    return jsonify({
        'success': True,
        'data': events or [],
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total': total
        }
    })


@notification_bp.route('/events/<int:event_id>', methods=['GET'])
@login_required
def get_event(event_id):
    """获取单个事件详情"""
    if not ds:
        return error_response('Service not initialized', status=500)

    visible = _visible_object_types(_current_user_id())

    event = ds.find_by_id('change_events', event_id)

    if not event:
        return error_response('Event not found', status=404)

    if visible is not None and event.get('object_type') not in visible:
        return error_response('您没有执行此操作的权限', status=403)

    return ok(event)


@notification_bp.route('/events/<int:event_id>/retry', methods=['POST'])
@login_required
def retry_event(event_id):
    """手动重试事件投递（P1-c）。

    规则（spec FR-5）：
      - 归属校验：必须是该事件某订阅的收件人，或具备 notification:retry:all
      - 仅重置 failed/skipped 投递为 pending；delivered 不动（部分失败只重试失败部分）
      - next_retry_at = now；attempts 单调递增，不清零
      - 5 秒内重复点击视为同一次重试（幂等）
    """
    if not ds:
        return error_response('Service not initialized', status=500)

    user = get_current_user() or {}
    user_id = user.get('user_id')

    event = ds.find_by_id('change_events', event_id)
    if not event:
        return error_response('Event not found', status=404)

    deliveries = ds.find('notification_deliveries', filters={'event_id': event_id}) or []
    owns_event = any(_same_user(d.get('user_id'), user_id) for d in deliveries)
    if not (owns_event or _can_retry_all(user)):
        return error_response('您没有执行此操作的权限', status=403)

    # 同一用户短时间内重复点击：只产生一次有效新尝试
    debounce_key = (event_id, user_id)
    now_monotonic = time.monotonic()
    last = _retry_debounce.get(debounce_key)
    if last is not None and now_monotonic - last < RETRY_DEBOUNCE_SECONDS:
        return ok({
            'event_id': event_id,
            'reset': 0,
            'attempted': 0,
            'delivered': 0,
            'failed': 0,
            'skipped': 0,
            'debounced': True,
        })
    _retry_debounce[debounce_key] = now_monotonic

    try:
        from meta.services.change_event_dispatcher import ChangeEventDispatcher
        dispatcher = ChangeEventDispatcher(ds)
        reset_count = dispatcher.prepare_retry(event_id)
        stats = dispatcher.redeliver_pending(event_id, event, force=True)
        return ok({
            'event_id': event_id,
            'reset': reset_count,
            'debounced': False,
            **stats,
        })
    except Exception as e:
        logger.error("Failed to retry event: %s", e)
        return error_response(str(e), status=500)


# ------------------------------------------------------------------ 收件箱（P1-b）
@notification_bp.route('/inbox', methods=['GET'])
@login_required
def get_inbox():
    """当前用户收件箱（按事件聚合，分页）"""
    if not ds:
        return error_response('Service not initialized', status=500)

    spec = parse_query_spec(request.args)
    unread_only = str(request.args.get('unread_only', '')).lower() in ('1', 'true', 'yes')
    service = _inbox_service()

    items, total = service.list(
        _current_user_id(),
        unread_only=unread_only,
        object_type=request.args.get('object_type'),
        event_type=request.args.get('event_type'),
        keyword=request.args.get('q'),
        page=spec.page,
        page_size=spec.page_size,
    )

    return jsonify({
        'success': True,
        'data': items,
        'unread_count': service.unread_count(_current_user_id()),
        'pagination': {
            'page': spec.page,
            'page_size': spec.page_size,
            'total': total,
        },
    })


@notification_bp.route('/inbox/unread-count', methods=['GET'])
@login_required
def get_inbox_unread_count():
    """未读数（排除已忽略）"""
    if not ds:
        return error_response('Service not initialized', status=500)
    return ok({'unread_count': _inbox_service().unread_count(_current_user_id())})


@notification_bp.route('/inbox/read-all', methods=['POST'])
@login_required
def read_all_inbox():
    """全部标记已读"""
    if not ds:
        return error_response('Service not initialized', status=500)

    data = request.get_json(silent=True) or {}
    service = _inbox_service()
    user_id = _current_user_id()
    affected = service.mark_all_read(
        user_id,
        object_type=data.get('object_type'),
        event_type=data.get('event_type'),
    )
    return ok({
        'affected': affected,
        'unread_count': service.unread_count(user_id),
    })


@notification_bp.route('/inbox/<int:inbox_id>/read', methods=['POST'])
@login_required
def read_inbox_item(inbox_id):
    """单条标记已读（仅本人）"""
    if not ds:
        return error_response('Service not initialized', status=500)

    row = _inbox_service().mark_read(_current_user_id(), inbox_id)
    if row is None:
        return error_response('消息不存在或无权访问', status=404)
    return ok(row)


@notification_bp.route('/inbox/<int:inbox_id>/dismiss', methods=['POST'])
@login_required
def dismiss_inbox_item(inbox_id):
    """单条忽略（保留在「全部」，不计入未读）"""
    if not ds:
        return error_response('Service not initialized', status=500)

    row = _inbox_service().dismiss(_current_user_id(), inbox_id)
    if row is None:
        return error_response('消息不存在或无权访问', status=404)
    return ok(row)
