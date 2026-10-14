# -*- coding: utf-8 -*-
import json
import logging

logger = logging.getLogger(__name__)

#遗留任务叶子菜单（P1 入口收敛：task.v1 直接接管 task-management，
# 这些叶子指向旧 scheduled_task / task_queue / task_execution / ai_async_task）
LEGACY_LEAF_MENU_CODES = (
    'task-definitions', 'task-queues', 'task-executions', 'ai-async-tasks',
)


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
            'menu_name': '任务管理',
            'menu_path': '/system/task-management',
            # P1入口收敛：task.v1 直接接管本页，页面由 TaskCenter.vue 自定义实现
            # （监控 tab + 详情抽屉），故 page_type 须为 custom_page —— 若沿用
            # multi_object_hub，dynamicRoutes 会按 GenericTabContainer 渲染，
            # 与实际页面实现不符。
            'page_type': 'custom_page',
            # 遗留实体（scheduled_task / task_queue / task_execution / ai_async_task）
            # 已随入口收敛下线：task.v1 的读路径走 /api/v1/tasks，不经 BO 泛型列表，
            # 故不绑任何 object_types / bo_bindings。
            # required_permissions 固定为 ['*']（管理员门槛）：menu_permission_api 的
            # _prune_empty_groups 把「custom_page + 无 children + required_permissions 为空」
            # 当空分组容器裁掉；本页是自实现页面叶子（有 menu_path、无子菜单），
            # 若门槛为空会被误剪而不可见。设 ['*'] 即声明「这是独立页面」，同时
            # 与路由 meta.requiresAdmin 同口径（仅管理员，业务用户不可见）。
            'primary_object_type': '',
            'object_types': [],
            'bo_bindings': [],
            'required_permissions': ['*'],
            'parent_menu': 'system',
            'icon': 'Timer',
            'color': 'blue',
            'description': '任务收件箱与监控（task.v1）',
            'sort_order': 0,
            'show_in_sidebar': True,
            'auto_generated': False,
            'page_config': {},
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

    # P1 入口收敛：清除遗留叶子菜单（menus + menu_permissions 两张表）。
    # 只删种子不删历史行不够 —— 已升级过的库仍留着旧行，
    # 配合前端静态路由会让 URL 直访落回遗留 GenericObjectList。
    for stale_code in LEGACY_LEAF_MENU_CODES:
        for table in ('menus', 'menu_permissions'):
            try:
                cur = data_source.execute(
                    f"DELETE FROM {table} WHERE menu_code = ?", (stale_code,))
                if cur.rowcount and cur.rowcount > 0:
                    logger.info("Removed stale %s entry: %s", table, stale_code)
            except Exception as e:
                logger.error("Failed to remove stale %s entry %s: %s", table, stale_code, e)

    data_source.commit()
    logger.info("Task menu_permissions synced")
    return count
