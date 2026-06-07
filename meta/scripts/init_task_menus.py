# -*- coding: utf-8 -*-
import json
import logging

logger = logging.getLogger(__name__)


def init_task_menus(data_source):
    menus = [
        {
            'menu_code': 'system',
            'menu_name': '系统管理',
            'menu_path': '/system',
            'page_type': 'custom_page',
            'primary_object_type': '',
            'object_types': [],
            'bo_bindings': [],
            'required_permissions': [],
            'parent_menu': '',
            'icon': 'Setting',
            'color': 'gray',
            'description': '系统管理与监控',
            'sort_order': 900,
            'show_in_sidebar': True,
            'auto_generated': False,
        },
        {
            'menu_code': 'task-management',
            'menu_name': '任务调度',
            'menu_path': '/system/task-management',
            'page_type': 'multi_object_hub',
            'primary_object_type': 'scheduled_task',
            'object_types': ['scheduled_task', 'task_queue', 'task_execution', 'ai_async_task'],
            'bo_bindings': [
                {'bo_id': 'scheduled_task', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'task_queue', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'task_execution', 'role': 'primary', 'include_actions': ['read', 'delete', 'list']},
                {'bo_id': 'ai_async_task', 'role': 'primary', 'include_actions': ['read', 'delete', 'list']},
            ],
            'required_permissions': [
                'scheduled_task:create', 'scheduled_task:read', 'scheduled_task:update', 'scheduled_task:delete',
                'task_queue:create', 'task_queue:read', 'task_queue:update', 'task_queue:delete',
                'task_execution:read', 'task_execution:delete',
                'ai_async_task:read', 'ai_async_task:delete',
            ],
            'parent_menu': 'system',
            'icon': 'Timer',
            'color': 'blue',
            'description': '后台任务调度与执行管理',
            'sort_order': 0,
            'show_in_sidebar': True,
            'auto_generated': False,
            'page_config': {},
        },
        {
            'menu_code': 'task-definitions',
            'menu_name': '任务定义',
            'menu_path': '/system/task-definitions',
            'page_type': 'object_list',
            'primary_object_type': 'scheduled_task',
            'object_types': ['scheduled_task'],
            'bo_bindings': [{'bo_id': 'scheduled_task', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']}],
            'required_permissions': [],
            'parent_menu': 'task-management',
            'icon': 'List',
            'color': '',
            'description': '管理所有定时任务的配置',
            'sort_order': 1,
            'show_in_sidebar': False,
            'auto_generated': False,
        },
        {
            'menu_code': 'task-queues',
            'menu_name': '任务队列',
            'menu_path': '/system/task-queues',
            'page_type': 'object_list',
            'primary_object_type': 'task_queue',
            'object_types': ['task_queue'],
            'bo_bindings': [{'bo_id': 'task_queue', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']}],
            'required_permissions': [],
            'parent_menu': 'task-management',
            'icon': 'Rank',
            'color': '',
            'description': '查看任务队列状态与配置',
            'sort_order': 2,
            'show_in_sidebar': False,
            'auto_generated': False,
        },
        {
            'menu_code': 'task-executions',
            'menu_name': '执行记录',
            'menu_path': '/system/task-executions',
            'page_type': 'object_list',
            'primary_object_type': 'task_execution',
            'object_types': ['task_execution'],
            'bo_bindings': [{'bo_id': 'task_execution', 'role': 'primary', 'include_actions': ['read', 'delete', 'list']}],
            'required_permissions': [],
            'parent_menu': 'task-management',
            'icon': 'Document',
            'color': '',
            'description': '查看任务执行历史记录',
            'sort_order': 3,
            'show_in_sidebar': False,
            'auto_generated': False,
        },
        {
            'menu_code': 'ai-async-tasks',
            'menu_name': 'AI异步任务',
            'menu_path': '/system/ai-async-tasks',
            'page_type': 'object_list',
            'primary_object_type': 'ai_async_task',
            'object_types': ['ai_async_task'],
            'bo_bindings': [{'bo_id': 'ai_async_task', 'role': 'primary', 'include_actions': ['read', 'delete', 'list']}],
            'required_permissions': [],
            'parent_menu': 'task-management',
            'icon': 'Cpu',
            'color': '',
            'description': '查看AI Agent异步任务',
            'sort_order': 4,
            'show_in_sidebar': False,
            'auto_generated': False,
        },
    ]

    PERMISSION_ENTRIES = {'task-management'}

    count = 0
    for menu in menus:
        try:
            existing = data_source.query(
                "SELECT menu_code FROM menus WHERE menu_code = ?",
                (menu['menu_code'],)
            )
            if existing:
                data_source.execute(
                    """UPDATE menus SET
                        menu_name = ?, menu_path = ?, page_type = ?,
                        primary_object_type = ?, object_types = ?,
                        bo_bindings = ?, required_permissions = ?,
                        parent_menu = ?, icon = ?, color = ?,
                        description = ?, sort_order = ?,
                        show_in_sidebar = ?, auto_generated = ?,
                        page_config = ?
                    WHERE menu_code = ?""",
                    [
                        menu['menu_name'],
                        menu['menu_path'],
                        menu['page_type'],
                        menu['primary_object_type'],
                        json.dumps(menu['object_types'], ensure_ascii=False),
                        json.dumps(menu['bo_bindings'], ensure_ascii=False),
                        json.dumps(menu['required_permissions'], ensure_ascii=False),
                        menu['parent_menu'],
                        menu['icon'],
                        menu['color'],
                        menu['description'],
                        menu['sort_order'],
                        1 if menu['show_in_sidebar'] else 0,
                        1 if menu['auto_generated'] else 0,
                        json.dumps(menu.get('page_config', {}), ensure_ascii=False),
                        menu['menu_code'],
                    ]
                )
                logger.info("Updated menu: %s", menu['menu_code'])
            else:
                data_source.execute(
                    """INSERT INTO menus
                    (menu_code, menu_name, menu_path, page_type,
                     primary_object_type, object_types, bo_bindings,
                     required_permissions, parent_menu, icon, color,
                     description, sort_order, is_active, show_in_sidebar, auto_generated,
                     page_config)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                    [
                        menu['menu_code'],
                        menu['menu_name'],
                        menu['menu_path'],
                        menu['page_type'],
                        menu['primary_object_type'],
                        json.dumps(menu['object_types'], ensure_ascii=False),
                        json.dumps(menu['bo_bindings'], ensure_ascii=False),
                        json.dumps(menu['required_permissions'], ensure_ascii=False),
                        menu['parent_menu'],
                        menu['icon'],
                        menu['color'],
                        menu['description'],
                        menu['sort_order'],
                        1 if menu['show_in_sidebar'] else 0,
                        1 if menu['auto_generated'] else 0,
                        json.dumps(menu.get('page_config', {}), ensure_ascii=False),
                    ]
                )
                logger.info("Created menu: %s", menu['menu_code'])
            count += 1
        except Exception as e:
            logger.error("Failed to init menu %s: %s", menu['menu_code'], e)

    data_source.commit()
    logger.info("Task menus initialized: %d menus", count)

    for menu in menus:
        if menu['menu_code'] not in PERMISSION_ENTRIES:
            continue
        try:
            existing_perm = data_source.query(
                "SELECT menu_code FROM menu_permissions WHERE menu_code = ?",
                (menu['menu_code'],)
            )
            if existing_perm:
                data_source.execute(
                    """UPDATE menu_permissions SET
                        menu_name = ?, menu_path = ?,
                        required_permissions = ?, parent_menu = ?,
                        icon = ?, sort_order = ?, is_active = 1,
                        data_permission_hint = ?
                    WHERE menu_code = ?""",
                    [
                        menu['menu_name'],
                        menu['menu_path'],
                        json.dumps(menu['required_permissions'], ensure_ascii=False),
                        menu['parent_menu'],
                        menu['icon'],
                        menu['sort_order'],
                        json.dumps(menu.get('data_permission_hint', {}), ensure_ascii=False) if menu.get('data_permission_hint') else None,
                        menu['menu_code'],
                    ]
                )
            else:
                data_source.execute(
                    """INSERT INTO menu_permissions
                    (menu_code, menu_name, menu_path, required_permissions,
                     required_any_permission, parent_menu, icon, sort_order,
                     is_active, data_permission_hint)
                    VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, ?)""",
                    [
                        menu['menu_code'],
                        menu['menu_name'],
                        menu['menu_path'],
                        json.dumps(menu['required_permissions'], ensure_ascii=False),
                        menu['parent_menu'],
                        menu['icon'],
                        menu['sort_order'],
                        json.dumps(menu.get('data_permission_hint', {}), ensure_ascii=False) if menu.get('data_permission_hint') else None,
                    ]
                )
        except Exception as e:
            logger.error("Failed to sync menu_permissions for %s: %s", menu['menu_code'], e)

    for stale_code in ['task-definitions', 'task-queues', 'task-executions', 'ai-async-tasks']:
        try:
            data_source.execute(
                "DELETE FROM menu_permissions WHERE menu_code = ?",
                (stale_code,)
            )
            logger.info("Removed stale menu_permissions entry: %s", stale_code)
        except Exception as e:
            logger.error("Failed to remove stale menu_permissions %s: %s", stale_code, e)

    data_source.commit()
    logger.info("Task menu_permissions synced")
    return count
