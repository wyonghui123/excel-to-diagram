# -*- coding: utf-8 -*-
"""
变更通知 API

提供 WebSocket 端点支持实时推送变更事件。
提供订阅管理 API。
"""

from flask import Blueprint, request, jsonify, g
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging
import os
import json
from datetime import datetime

from meta.services.websocket_manager import websocket_manager
from meta.services.token_service import TokenService

logger = logging.getLogger(__name__)

notification_bp = Blueprint('notification', __name__, url_prefix='/api/v1/notifications')

socketio = None
ds = None


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
        event_types = data.get('event_types', ['created', 'updated', 'deleted'])
        
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
def get_stats():
    """获取 WebSocket 连接统计"""
    return jsonify({
        'success': True,
        'data': websocket_manager.get_stats()
    })


@notification_bp.route('/subscriptions', methods=['GET'])
def get_subscriptions():
    """获取当前用户的订阅列表"""
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
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
def create_subscription():
    """创建订阅"""
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    if not ds:
        return jsonify({'success': False, 'error': 'Service not initialized'}), 500
    
    data = request.get_json() or {}
    
    object_type = data.get('object_type')
    event_types = data.get('event_types', ['created', 'updated', 'deleted'])
    channel = data.get('channel', 'websocket')
    webhook_url = data.get('webhook_url', '')
    webhook_secret = data.get('webhook_secret', '')
    filter_condition = data.get('filter_condition', {})
    
    if not object_type:
        return jsonify({'success': False, 'error': 'object_type is required'}), 400
    
    if channel == 'webhook' and not webhook_url:
        return jsonify({'success': False, 'error': 'webhook_url is required for webhook channel'}), 400
    
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
    
    try:
        sub_id = ds.insert('change_subscriptions', subscription)
        subscription['id'] = sub_id
        
        logger.info(
            "Subscription created: id=%s, user_id=%s, object_type=%s, channel=%s",
            sub_id, user_id, object_type, channel
        )
        
        return jsonify({
            'success': True,
            'data': subscription
        }), 201
        
    except Exception as e:
        logger.error("Failed to create subscription: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@notification_bp.route('/subscriptions/<int:sub_id>', methods=['GET'])
def get_subscription(sub_id):
    """获取单个订阅详情"""
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    if not ds:
        return jsonify({'success': False, 'error': 'Service not initialized'}), 500
    
    subscription = ds.find_one('change_subscriptions', filters={'id': sub_id})
    
    if not subscription:
        return jsonify({'success': False, 'error': 'Subscription not found'}), 404
    
    if subscription.get('user_id') != user_id:
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    
    return jsonify({
        'success': True,
        'data': subscription
    })


@notification_bp.route('/subscriptions/<int:sub_id>', methods=['PUT'])
def update_subscription(sub_id):
    """更新订阅"""
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    if not ds:
        return jsonify({'success': False, 'error': 'Service not initialized'}), 500
    
    subscription = ds.find_one('change_subscriptions', filters={'id': sub_id})
    
    if not subscription:
        return jsonify({'success': False, 'error': 'Subscription not found'}), 404
    
    if subscription.get('user_id') != user_id:
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    
    data = request.get_json() or {}
    
    update_data = {}
    
    if 'event_types' in data:
        event_types = data['event_types']
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
        return jsonify({'success': False, 'error': 'No fields to update'}), 400
    
    try:
        ds.update('change_subscriptions', sub_id, update_data)
        
        logger.info("Subscription updated: id=%s", sub_id)
        
        updated = ds.find_one('change_subscriptions', filters={'id': sub_id})
        
        return jsonify({
            'success': True,
            'data': updated
        })
        
    except Exception as e:
        logger.error("Failed to update subscription: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@notification_bp.route('/subscriptions/<int:sub_id>', methods=['DELETE'])
def delete_subscription(sub_id):
    """删除订阅"""
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    if not ds:
        return jsonify({'success': False, 'error': 'Service not initialized'}), 500
    
    subscription = ds.find_one('change_subscriptions', filters={'id': sub_id})
    
    if not subscription:
        return jsonify({'success': False, 'error': 'Subscription not found'}), 404
    
    if subscription.get('user_id') != user_id:
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    
    try:
        ds.delete('change_subscriptions', sub_id)
        
        logger.info("Subscription deleted: id=%s", sub_id)
        
        return jsonify({
            'success': True,
            'message': 'Subscription deleted'
        })
        
    except Exception as e:
        logger.error("Failed to delete subscription: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@notification_bp.route('/events', methods=['GET'])
def get_events():
    """获取变更事件列表"""
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    if not ds:
        return jsonify({'success': False, 'error': 'Service not initialized'}), 500
    
    object_type = request.args.get('object_type')
    status = request.args.get('status')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    
    filters = {}
    if object_type:
        filters['object_type'] = object_type
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
def get_event(event_id):
    """获取单个事件详情"""
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    if not ds:
        return jsonify({'success': False, 'error': 'Service not initialized'}), 500
    
    event = ds.find_one('change_events', filters={'id': event_id})
    
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    return jsonify({
        'success': True,
        'data': event
    })


@notification_bp.route('/events/<int:event_id>/retry', methods=['POST'])
def retry_event(event_id):
    """重试事件投递"""
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    if not ds:
        return jsonify({'success': False, 'error': 'Service not initialized'}), 500
    
    event = ds.find_one('change_events', filters={'id': event_id})
    
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    if event.get('status') == 'delivered':
        return jsonify({'success': False, 'error': 'Event already delivered'}), 400
    
    try:
        from meta.services.webhook_service import webhook_service, WebhookConfig, WebhookPayload
        
        subscriptions = ds.find(
            'change_subscriptions',
            filters={
                'object_type': event.get('object_type'),
                'channel': 'webhook',
                'enabled': 1
            }
        )
        
        if not subscriptions:
            return jsonify({'success': False, 'error': 'No webhook subscriptions found'}), 404
        
        results = []
        for sub in subscriptions:
            config = WebhookConfig(
                url=sub.get('webhook_url', ''),
                secret=sub.get('webhook_secret', ''),
                retry_count=3
            )
            
            payload = WebhookPayload(
                event_id=event_id,
                object_type=event.get('object_type'),
                object_id=event.get('object_id'),
                event_type=event.get('event_type'),
                changed_fields=json.loads(event.get('changed_fields', '[]')),
                old_values=json.loads(event.get('old_values', '{}')),
                new_values=json.loads(event.get('new_values', '{}'))
            )
            
            result = webhook_service.deliver_with_retry(config, payload)
            results.append({
                'subscription_id': sub.get('id'),
                'success': result.success,
                'error': result.error
            })
        
        ds.update('change_events', event_id, {
            'status': 'delivered' if all(r['success'] for r in results) else 'failed',
            'delivered_at': datetime.now().isoformat()
        })
        
        return jsonify({
            'success': True,
            'data': {
                'event_id': event_id,
                'results': results
            }
        })
        
    except Exception as e:
        logger.error("Failed to retry event: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500
