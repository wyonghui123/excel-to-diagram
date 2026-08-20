# -*- coding: utf-8 -*-
"""
PermissionDerivationPipeline — Layer 2 → Layer 1 推导管道

[8 步推导流程]
  Step 1: 加载 permission_rules_v2 配置源
  Step 2: 加载角色菜单 (可选, 用于菜单→BO actions 推导)
  Step 3: 加载手工 Intent (manual source, 最高优先级)
  Step 4: 统一展开 (核心: LEVEL_BUNDLES + 条件结构化)
  Step 5: 维度→菜单推导 (可选)
  Step 6: 菜单→BO actions 推导 + 反向建议 (可选)
  Step 7: 冲突解决 + 合并 → 写入 role_effective_intents
  Step 8: 标记 stale 清除

[输出]
  role_effective_intents 表: (role_id, bo_id, action_name, data_scope, derivation_mode, source)

[Cartesian 语义保留 (AC-008)]
  derivation_mode='dynamic' 时, include_conditions 中的 ID 列表保持原样,
  不做静态展开。运行时由 EffectiveIntentChecker 通过 CHILDREN_OF 子查询展开。
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional

from meta.core.level_bundles import expand_level


class PermissionDerivationPipeline:
    """Layer 2 → Layer 1 推导管道"""

    def __init__(
        self,
        db_path: str,
        dao,
    ):
        """
        Args:
            db_path: 数据库路径
            dao: EffectiveIntentDAO 实例
        """
        self._db_path = db_path
        self._dao = dao
        # [P4 补充] 惰性初始化 DimensionScopeEngine (复用其维度展开逻辑)
        self._dim_engine = None

    def derive(self, role_id: int) -> Dict[str, Any]:
        """执行 8 步推导

        Args:
            role_id: 角色 ID

        Returns:
            {
                'intent_count': int,
                'actions': List[str],
                'rules_processed': int,
                'derived_menus': List[str],  # [P1-A6] FR-011 维度→菜单推导
                'reverse_suggestions': List[str],  # [P1-A6] FR-011 菜单→BO 反向建议
            }
        """
        # Step 1: 加载 permission_rules_v2
        rules = self._load_permission_rules(role_id)

        if not rules:
            # 无规则: 清空该角色所有 Intent (避免脏数据)
            self._dao.delete_for_role(role_id)
            return {
                'intent_count': 0,
                'actions': [],
                'rules_processed': 0,
                'derived_menus': [],
                'reverse_suggestions': [],
            }

        # Step 2-3: 加载菜单和手工 Intent (FR-013 manual intent 优先级)
        # [P1-A2 2026-07-26] 实现 _load_manual_intents, 从 role_intents 表加载
        #   source='manual' 的 (bo_id, action_name, granted) 记录
        #   - granted=true  → 强制包含该 (bo_id, action_name) intent
        #   - granted=false → 强制排除该 (bo_id, action_name) intent
        # [P1-A6 2026-07-26] FR-011 实现 _load_role_menus, 从 role_menu_permissions
        #   表加载角色已授权的 menu_code 列表
        # [P1-A7 2026-07-26] FR-012 加载 object_owd (对象基线, 最低优先级兜底)
        menus = self._load_role_menus(role_id)
        manual_intents = self._load_manual_intents(role_id)
        owd = self._load_object_owd()

        # Step 4: 统一展开 (规则 → intents)
        # 每个 rule 展开为多个 (bo_id, action_name, data_scope) 三元组
        expanded = self._unified_expand(rules)

        # [P1-A7 2026-07-26] FR-012 应用 OWD 兜底 (最低优先级)
        # OWD (Object Wide Defaults) 是最低优先级的兜底 intent:
        #   - 当角色对某 BO 无任何配置时, 使用 OWD 作为基线
        #   - source='owd', 优先级低于 manual / derived / menu
        #   - public_read → 添加 read intent (空 include = 全允许)
        #   - public_read_write → 添加 read+create+update intent
        #   - private → 不添加 intent (默认拒绝, 仅 owner 可见)
        if owd:
            self._apply_owd_baseline(expanded, owd)

        # [P4 补充] Step 4.5: 维度展开 (复用 DimensionScopeEngine)
        # 把 role_dimension_scopes + v2 规则中的维度配置展开为所有 BO 的条件
        # 这一步会为 HIERARCHY_CHAIN 中的每个 BO 生成额外的 intents
        dim_expanded = self._expand_dimensions_to_intents(role_id)
        expanded.extend(dim_expanded)

        # [P1-A6 2026-07-26] Step 5: 维度→菜单推导 (FR-011)
        # 基于已生成的 intents (BO 维度范围), 推导该角色应该看到的菜单列表
        # 例: role 有 sub_domain:read intent → 推荐"子领域管理"菜单
        derived_menus = self._derive_menus_from_dimensions(expanded)

        # [P1-A6 2026-07-26] Step 6: 菜单→BO actions 推导 + 反向建议 (FR-011)
        # 1. menu_intents: 从角色已授权菜单的 bo_bindings 推导 BO actions intents
        #    (即使用户未配置 dim scope, 通过菜单授权也能获得 BO read 权限)
        # 2. reverse_suggestions: 基于 BO intents, 反向建议应该授权的菜单
        #    (用户已有 BO intent 但未授权对应菜单 → 建议)
        menu_intents = self._derive_intents_from_menus(menus)
        if menu_intents:
            # menu 推导的 intents 用 source='menu' 标记, 优先级低于 manual
            # 不覆盖已有的 derived/manual intents
            existing_keys = {(i['bo_id'], i['action_name']) for i in expanded}
            for mi in menu_intents:
                key = (mi['bo_id'], mi['action_name'])
                if key not in existing_keys:
                    expanded.append(mi)
                    existing_keys.add(key)

        reverse_suggestions = self._suggest_menus_for_intents(expanded, menus)

        # [P1-B4 修复 2026-07-26] 移动 _merge_manual_intents 到所有展开之后
        # 问题: 原顺序在 _expand_dimensions_to_intents 之前执行 manual merge,
        #       但 dim_expanded 会用 source='derived_dim_expand' 覆盖 manual intent
        #       (upsert 是 last-wins, dim_expanded 在 manual 之后 extend → 覆盖 manual)
        # 修复: 将 _merge_manual_intents 移到所有展开之后, 确保 manual intent 优先级最高
        #       (FR-013: manual intent 优先级 > derived > menu > owd)
        if manual_intents:
            self._merge_manual_intents(expanded, manual_intents)

        # Step 7: 合并 → 写入 role_effective_intents
        # 先删除旧的, 再批量插入 (简化逻辑, 后续可优化为增量)
        self._dao.delete_for_role(role_id)
        for intent in expanded:
            self._dao.upsert(
                role_id=role_id,
                bo_id=intent['bo_id'],
                action_name=intent['action_name'],
                data_scope=intent['data_scope'],
                derivation_mode=intent['derivation_mode'],
                source=intent['source'],
            )

        # Step 8: 清除 stale 标记
        self._dao.clear_stale(role_id)

        # 计算摘要
        actions = sorted({i['action_name'] for i in expanded})
        return {
            'intent_count': len(expanded),
            'actions': actions,
            'rules_processed': len(rules),
            'derived_menus': derived_menus,
            'reverse_suggestions': reverse_suggestions,
        }

    # ============================================================
    # Step 1: 加载配置源
    # ============================================================
    def _load_permission_rules(self, role_id: int) -> List[Dict[str, Any]]:
        """从 permission_rules_v2 表加载规则"""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                '''
                SELECT * FROM permission_rules_v2
                WHERE role_id = ?
                ORDER BY id
                ''',
                [role_id],
            ).fetchall()
            return [dict(r) for r in rows]

    # ============================================================
    # Step 4: 统一展开 (核心)
    # ============================================================
    def _unified_expand(
        self,
        rules: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """规则展开: 每条规则 → 多个 (bo_id, action, data_scope) 三元组

        [展开规则]
          - permission_level → 通过 LEVEL_BUNDLES 展开为 action 列表
          - include_conditions → data_scope.include
          - exclude_conditions → data_scope.exclude
          - derivation_mode → 直接透传 (static/dynamic)
          - source → 直接透传

        [多规则合并]
          同一 (bo_id, action_name) 的多条规则:
          - 后写覆盖前写 (简化策略, 后续可优化为 union 合并)
          - 但 source='manual' 优先级最高, 不被覆盖

        Args:
            rules: permission_rules_v2 表的规则列表

        Returns:
            [{bo_id, action_name, data_scope, derivation_mode, source}, ...]
        """
        # 用 dict 合并: key = (bo_id, action_name)
        # source='manual' 优先级最高, 不被 derived/template 覆盖
        merged: Dict[tuple, Dict[str, Any]] = {}
        # 处理顺序: derived/template 先, manual 最后 (确保 manual 覆盖)
        sorted_rules = sorted(
            rules,
            key=lambda r: 0 if r.get('source') == 'manual' else 1,
        )

        for rule in sorted_rules:
            bo_id = rule['resource_type']
            level = rule.get('permission_level', 'read')
            actions = expand_level(level)
            include = self._parse_conditions(rule.get('include_conditions'))
            exclude = self._parse_conditions(rule.get('exclude_conditions'))
            derivation_mode = rule.get('derivation_mode', 'static')
            source = rule.get('source', 'derived')

            data_scope = {'include': include, 'exclude': exclude}

            for action_name in actions:
                key = (bo_id, action_name)
                existing = merged.get(key)
                if existing is not None:
                    # manual 优先级最高, 覆盖一切
                    if source == 'manual':
                        merged[key] = {
                            'bo_id': bo_id,
                            'action_name': action_name,
                            'data_scope': data_scope,
                            'derivation_mode': derivation_mode,
                            'source': source,
                        }
                    # 否则保留现有的 (可能是先到的 manual 或同等优先级)
                else:
                    merged[key] = {
                        'bo_id': bo_id,
                        'action_name': action_name,
                        'data_scope': data_scope,
                        'derivation_mode': derivation_mode,
                        'source': source,
                    }

        return list(merged.values())

    # ============================================================
    # [P1-A2 2026-07-26] Step 3: 加载手工 Intent (FR-013)
    # ============================================================
    def _load_manual_intents(self, role_id: int) -> List[Dict[str, Any]]:
        """[P1-A2 2026-07-26] 从 role_intents 表加载手工 Intent

        [FR-013 manual intent 优先级生效]
          role_intents 表 (FR-017 BO 统一模型) 存储 (role_id, bo_id, action_name, granted, source)
          其中 source='manual' 的记录是手工配置, 优先级最高, 覆盖 derived 推导结果

          - granted=true  → 强制包含该 (bo_id, action_name) intent (即使 derived 没推导出来)
          - granted=false → 强制排除该 (bo_id, action_name) intent (即使 derived 推导出来了)

        Args:
            role_id: 角色 ID

        Returns:
            [{bo_id, action_name, granted}, ...]
        """
        result: List[Dict[str, Any]] = []
        try:
            with sqlite3.connect(self._db_path) as conn:
                # 检查 role_intents 表是否存在
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='role_intents'"
                )
                if cursor.fetchone() is None:
                    return result  # 表不存在, 返回空

                rows = conn.execute(
                    '''
                    SELECT bo_id, action_name, granted
                    FROM role_intents
                    WHERE role_id = ? AND source = 'manual'
                    ''',
                    [role_id],
                ).fetchall()
            for row in rows:
                bo_id = row[0] if not isinstance(row, tuple) else row[0]
                action_name = row[1] if not isinstance(row, tuple) else row[1]
                granted = row[2] if not isinstance(row, tuple) else row[2]
                result.append({
                    'bo_id': bo_id,
                    'action_name': action_name,
                    'granted': bool(granted),
                })
        except sqlite3.Error:
            pass  # 表不存在或查询失败, 返回空
        return result

    def _merge_manual_intents(
        self,
        expanded: List[Dict[str, Any]],
        manual_intents: List[Dict[str, Any]],
    ) -> None:
        """[P1-A2 2026-07-26] 合并 manual_intents 到 expanded (原地修改)

        [FR-013 manual intent 优先级]
          - manual granted=true  → 强制加入 (若无), data_scope = {include:[], exclude:[]}
                                 (空 include = 全允许, 与未配置行为一致)
          - manual granted=false → 强制排除 (覆盖现有 intent, data_scope 含永假条件)
                                 (确保 read/write 路径都拒绝, 而非 "无 intent = 允许所有")
          - source='manual' 标记

        [P1-B4 修复 2026-07-26] granted=false 行为修正
          旧实现: granted=false 时从 expanded 中移除 intent → IntentScopeAdapter
                  找不到 intent → 返回 'no_intent_allows_all' → read 路径允许所有
                  (与 "强制排除" 语义相反)
          新实现: granted=false 时覆盖/添加 intent, data_scope 含永假条件
                  (include=[{field:'id', op:'=', value:-1}])
                  → IntentScopeAdapter 生成 SQL: id = -1 (永不匹配) → 拒绝所有
                  → EffectiveIntentChecker 同样拒绝 (include 不匹配)
                  → 修复后 manual granted=false 真正实现 "强制排除"

        [合并策略]
          1. 处理 granted=false: 覆盖现有 intent 为永假条件 (或添加新的永假 intent)
          2. 处理 granted=true: 若 expanded 中没有, 添加一个空的 data_scope intent
             若已有, 不重复添加 (但更新 source='manual' 标记)

        Args:
            expanded: derived 展开后的 intent 列表 (会被原地修改)
            manual_intents: 手工配置的 intent 列表
        """
        # 构建现有 (bo_id, action_name) → intent 索引
        existing_map: Dict[tuple, Dict[str, Any]] = {}
        for i, intent in enumerate(expanded):
            key = (intent['bo_id'], intent['action_name'])
            existing_map[key] = intent

        # 永假条件: id = -1 (SQLite 中整数 id 通常从 1 开始, -1 永不匹配)
        DENY_ALL_SCOPE = {
            'include': [{'field': 'id', 'op': '=', 'value': -1}],
            'exclude': [],
        }

        # Step 1: 处理 granted=false (强制排除 = 覆盖为永假条件)
        for manual in manual_intents:
            if manual['granted']:
                continue
            key = (manual['bo_id'], manual['action_name'])
            if key in existing_map:
                # 覆盖现有 intent 为永假条件
                existing_map[key]['data_scope'] = DENY_ALL_SCOPE
                existing_map[key]['source'] = 'manual_deny'
                existing_map[key]['derivation_mode'] = 'static'
            else:
                # 添加新的永假 intent (强制拒绝)
                new_intent = {
                    'bo_id': manual['bo_id'],
                    'action_name': manual['action_name'],
                    'data_scope': DENY_ALL_SCOPE,
                    'derivation_mode': 'static',
                    'source': 'manual_deny',
                }
                expanded.append(new_intent)
                existing_map[key] = new_intent

        # Step 2: 处理 granted=true (强制加入)
        for manual in manual_intents:
            if not manual['granted']:
                continue
            key = (manual['bo_id'], manual['action_name'])
            if key in existing_map:
                # 已存在, 标记 source='manual' (优先级提示)
                existing_map[key]['source'] = 'manual_override'
            else:
                # 不存在, 添加 manual intent
                # data_scope = 空 include (允许所有) + 空 exclude (无否决)
                new_intent = {
                    'bo_id': manual['bo_id'],
                    'action_name': manual['action_name'],
                    'data_scope': {'include': [], 'exclude': []},
                    'derivation_mode': 'static',
                    'source': 'manual',
                }
                expanded.append(new_intent)
                existing_map[key] = new_intent

    def _parse_conditions(self, raw: Optional[str]) -> List[Dict[str, Any]]:
        """解析 conditions JSON 字符串

        Args:
            raw: JSON 字符串 (如 '[{"field":"x","op":"=","value":1}]')
                 或 None/空 → 返回 []

        Returns:
            [{field, op, value}, ...]
        """
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    # ============================================================
    # [P4 补充] Step 4.5: 维度展开 (复用 DimensionScopeEngine)
    # ============================================================
    def _get_dim_engine(self):
        """惰性初始化 DimensionScopeEngine"""
        if self._dim_engine is None:
            try:
                from meta.services.dimension_scope_engine import DimensionScopeEngine
                from meta.core.datasource import get_data_source
                ds = get_data_source('sqlite', database=self._db_path)
                self._dim_engine = DimensionScopeEngine(ds)
            except ImportError:
                self._dim_engine = None
        return self._dim_engine

    def _expand_dimensions_to_intents(self, role_id: int) -> List[Dict[str, Any]]:
        """[P4 补充] 维度展开: 调用 DimensionScopeEngine 生成所有 BO 的条件

        [背景]
          旧系统 DimensionScopeEngine.derive_data_conditions(role_id) 会:
          1. 加载 role_dimension_scopes 配置 (含 include/exclude/wildcard)
          2. 向上展开 (sub_domain → domain → version → product)
          3. 向下展开 (product → version → domain → sub_domain)
          4. 为每个 BO 生成 SQL WHERE 条件
          5. [P5 修复 2026-07-26] 处理 scope_mode='exclude' (id NOT IN (...))

          新系统 derivation_pipeline 之前只处理 permission_rules_v2,
          没有维度展开, 导致 effective_intents 覆盖不全。

        [策略]
          复用 DimensionScopeEngine.derive_data_conditions 获取 {bo_id: SQL},
          然后用 op='RAW' 包装成结构化条件, 存到 intent 中。
          [P5 修复 2026-07-26] 同时调用 _load_exclude_values 提取 exclude,
          并附加到 data_scope.exclude (用于 IntentScopeAdapter 在 read 时生成 NOT (...) 条件)
          [P6 修复 2026-07-26] 用动态子查询 SQL 覆盖 derive_data_conditions
          的静态 ID 列表 (例: domain=[2200] 时, sub_domain 应生成
          "domain_id IN (2200)" 而非 "id IN (297,...,448) AND domain_id=2200"),
          避免新增对象后静态 ID 列表过期

        Args:
            role_id: 角色 ID

        Returns:
            [{bo_id, action_name, data_scope, derivation_mode, source}, ...]
        """
        engine = self._get_dim_engine()
        if engine is None:
            return []

        try:
            # 调用旧系统获取所有 BO 的 SQL 条件 (含 exclude 已合并)
            bo_conditions = engine.derive_data_conditions(role_id)
        except Exception:
            return []

        if not bo_conditions:
            return []

        # [P5 修复 2026-07-26] 检测 wildcard 维度
        # wildcard 维度存储空 include (动态条件), 避免新增对象后静态 ID 列表过期
        # 例: product wildcard → 所有 BO 的 intent 存空 include (所有可见)
        #     而非 id IN (1,2,3,...) 静态列表
        try:
            wildcard_dims = engine.get_wildcard_dims(role_id)
        except Exception:
            wildcard_dims = set()

        # 计算 wildcard 影响的 BO 集合
        # wildcard 维度本身 + HIERARCHY_CHAIN 中其下方的所有维度 + EXTENDED_CHAIN 的 BO
        wildcard_affected_bos = self._get_wildcard_affected_bos(wildcard_dims)

        # [P6 修复 2026-07-26] 用动态子查询 SQL 覆盖 derive_data_conditions 的静态 ID 列表
        # 修复场景: dim scope 配置 domain=[2200], derive_data_conditions 会展开为
        #   sub_domain: "domain_id=2200 AND id IN (297, 299, ..., 448)"
        # 静态 ID 列表不包含测试新创建的 SD 455 → 拒绝访问
        # 修复后: 用动态子查询 "domain_id IN (2200)" 覆盖, 自动包含 SD 455
        if not wildcard_affected_bos:
            try:
                dim_configs = self._load_dim_scope_configs(role_id)
                if dim_configs:
                    dynamic_sql_map = self._generate_dynamic_dim_scope_sql(dim_configs)
                    for bo_id, dyn_sql in dynamic_sql_map.items():
                        if bo_id in bo_conditions:
                            bo_conditions[bo_id] = dyn_sql
            except Exception:
                pass

        # [P5 修复 2026-07-26] 提取 exclude 配置 (用于附加到 data_scope.exclude)
        # 这样 IntentScopeAdapter 在 read 时会生成 NOT (id IN (...)) 条件
        try:
            excluded = engine._load_exclude_values(role_id)
        except Exception:
            excluded = {}

        # [P5 修复 2026-07-26] 为每个 BO 生成所有 action 的 intent
        # 之前只生成 read/list/export (expand_level('read')), 导致
        #   - IntentScopeAdapter 找不到 create/update/delete intent
        #   - 写操作回退到 legacy, 但 legacy 也有 bug (_dim_has_any_values 不兼容 set)
        #   - 即使 legacy 修复, effective_intents 路径仍然不工作
        # 修复: 查询 role_permissions 获取该 role 实际持有的 (bo_id, action) 集合,
        #       为每个 (bo_id, action) 生成 intent, 使用相同的 dim scope 条件
        role_actions = self._load_role_actions_for_dim(role_id)

        result = []
        for bo_id, sql_condition in bo_conditions.items():
            if not sql_condition or sql_condition.strip() == '':
                continue

            # [P5 修复 2026-07-26] wildcard 影响的 BO 存储空 include (动态条件)
            # 避免静态 ID 列表在新增对象后过期 (F1 测试场景)
            is_wildcard_affected = bo_id in wildcard_affected_bos

            # 用 op='RAW' 包装 SQL 条件
            # 空 SQL (表示所有可见) → include=[]
            # 非空 SQL → include=[{field:'*', op:'RAW', value:sql}]
            # wildcard 影响的 BO → include=[] (动态条件, 所有可见)
            if is_wildcard_affected:
                include = []  # wildcard: 空 = all (动态, 不受新增对象影响)
            elif sql_condition.strip() == '1=1' or sql_condition.strip() == 'TRUE':
                include = []  # 空 = all
            else:
                include = [{
                    'field': '*',
                    'op': 'RAW',
                    'value': sql_condition,
                }]

            # [P5 修复 2026-07-26] 附加 exclude (仅当 bo_id == dimension_code 时)
            # 例: sub_domain exclude [339] → data_scope.exclude = [{field:'id', op:'IN', value:[339]}]
            # 注意: derive_data_conditions 已将 NOT IN 合并到 SQL, 这里仅作冗余记录
            #       以便 IntentScopeAdapter 在 read 时正确生成 NOT 条件
            exclude_list = []
            if bo_id in excluded and excluded[bo_id]:
                excl_ids = sorted(excluded[bo_id])
                exclude_list.append({
                    'field': 'id',
                    'op': 'IN',
                    'value': excl_ids,
                })

            data_scope = {
                'include': include,
                'exclude': exclude_list,
            }

            # [P5 修复 2026-07-26] 决定为该 BO 生成哪些 action 的 intent
            # 优先用 role_permissions 中实际持有的 action (覆盖 create/update/delete/import)
            # 回退到 read level (read/list/export) 保证向后兼容
            # [P1-B3 修复 2026-07-26] actions_for_bo 取 role_actions ∪ expand_level('read')
            #   修复 bug: 之前只取 role_actions, 当 role_permissions 只有 [read, export] 时,
            #   不生成 list intent, 导致 _unified_expand 写入的旧 list intent (来自
            #   permission_rules_v2 migrated_dim_scope) 不被覆盖, dim_scope 变更后
            #   list intent 仍保持旧值, IntentScopeAdapter 用旧 SQL 过滤, 行为错误
            if bo_id in role_actions and role_actions[bo_id]:
                # Union role_actions + expand_level('read') 确保 list/export 总会被
                # 重新生成, 覆盖 _unified_expand 的旧 intent
                read_level_actions = expand_level('read')
                actions_for_bo = list(set(role_actions[bo_id]) | set(read_level_actions))
            else:
                # role 无该 BO 的功能权限 → 只生成 read-level (用于数据范围过滤)
                actions_for_bo = expand_level('read')

            for action_name in actions_for_bo:
                result.append({
                    'bo_id': bo_id,
                    'action_name': action_name,
                    'data_scope': data_scope,
                    'derivation_mode': 'dynamic',  # 维度展开 = dynamic
                    'source': 'derived_dim_expand',
                })

        return result

    def _load_role_actions_for_dim(self, role_id: int) -> Dict[str, List[str]]:
        """[P5 补充 2026-07-26] 加载 role 实际持有的 (bo_id, action) 集合

        从 role_permissions + permissions 表查询, 解析 permission.code
        格式: '{resource_type}:{action}' (如 'sub_domain:create')

        Returns:
            {bo_id: [action_name, ...]}  e.g. {'sub_domain': ['create', 'read', 'update', ...]}

        [用途]
            derivation_pipeline 之前只生成 read/list/export intent, 漏掉
            create/update/delete/import, 导致 IntentScopeAdapter 在写操作时
            返回 'no_intent_allows_all' → 回退到 legacy → legacy 也有 bug → 拒绝
            修复后: 为 role 实际持有的每个 (bo_id, action) 生成 intent

        [P1-A5 修复 2026-07-26] 支持自定义 action (如 approve/reject/assign)
          - 之前过滤掉非标准 action, 导致自定义权限不会生成 intent
          - 修复后: 接受所有符合 '{bo_id}:{action}' 格式的权限
          - 排除明显是 BO 全名而非 action 的权限 (如 'ai_async_task_create')
        """
        result: Dict[str, List[str]] = {}
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    '''
                    SELECT p.code
                    FROM role_permissions rp
                    JOIN permissions p ON rp.permission_id = p.id
                    WHERE rp.role_id = ? AND rp.granted = 1
                    ''',
                    [role_id],
                ).fetchall()
            for row in rows:
                code = row[0] if not isinstance(row, tuple) else row[0]
                if not code or ':' not in code:
                    continue
                # 解析 'sub_domain:create' → bo_id='sub_domain', action='create'
                parts = code.split(':', 1)
                if len(parts) != 2:
                    continue
                bo_id, action = parts[0], parts[1]
                # [P1-A5 修复] 接受所有符合格式的 action (含自定义 action)
                # 只排除明显异常的:
                #   - 空 action
                #   - action 长度超过 50 (异常长, 可能是误配)
                if not action or len(action) > 50:
                    continue
                # 标准化: 转小写 (与 expand_level 输出一致)
                action_lower = action.lower()
                if bo_id not in result:
                    result[bo_id] = []
                if action_lower not in result[bo_id]:
                    result[bo_id].append(action_lower)
        except Exception:
            pass
        return result

    def _get_wildcard_affected_bos(self, wildcard_dims: set) -> set:
        """[P5 修复 2026-07-26] 计算 wildcard 影响的 BO 集合

        wildcard 维度本身 + HIERARCHY_CHAIN 中其下方的所有维度
        + EXTENDED_CHAIN 的 BO (service_module, business_object, relationship)

        例: wildcard_dims={'product'} →
            {'product', 'version', 'domain', 'sub_domain',
             'service_module', 'business_object', 'relationship'}

        例: wildcard_dims={'domain'} →
            {'domain', 'sub_domain',
             'service_module', 'business_object', 'relationship'}

        Args:
            wildcard_dims: wildcard 维度集合 (如 {'product'})

        Returns:
            受 wildcard 影响的 BO 集合
        """
        if not wildcard_dims:
            return set()

        try:
            from meta.services.dimension_scope_engine import (
                HIERARCHY_CHAIN, VERSION_AWARE_BOS
            )
        except ImportError:
            return set()

        affected = set()
        for dim in wildcard_dims:
            # wildcard 维度本身
            affected.add(dim)
            # HIERARCHY_CHAIN 中下方的维度
            try:
                idx = HIERARCHY_CHAIN.index(dim)
                for child_dim in HIERARCHY_CHAIN[idx + 1:]:
                    affected.add(child_dim)
            except ValueError:
                pass  # 非 HIERARCHY_CHAIN 维度 (如 service_module), 仅影响自身

        # EXTENDED_CHAIN 的 BO (service_module, business_object, relationship)
        # 这些 BO 沿 HIERARCHY_CHAIN 派生, 任何 HIERARCHY wildcard 都影响它们
        if affected & set(HIERARCHY_CHAIN):
            affected.update(VERSION_AWARE_BOS.keys())

        return affected

    def _load_dim_scope_configs(self, role_id: int) -> Dict[str, List[int]]:
        """[P6 修复 2026-07-26] 加载 role_dimension_scopes 的原始配置

        返回用户配置的 dim_vals (非展开值), 用于生成动态子查询 SQL
        例: domain=[2200] → {'domain': [2200]}

        [排除场景]
          - scope_mode != 'include' (exclude/all 由其他路径处理)
          - dimension_values 含 '*' (wildcard, 由 _get_wildcard_affected_bos 处理)
          - 维度不在 HIERARCHY_CHAIN (非层级维度, 无需动态子查询)

        Returns:
            {dim_code: [dim_val, ...]}
        """
        result: Dict[str, List[int]] = {}
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT dimension_code, dimension_values, scope_mode "
                    "FROM role_dimension_scopes WHERE role_id = ?",
                    [role_id],
                ).fetchall()
            for row in rows:
                dim_code = row[0] if not isinstance(row, tuple) else row[0]
                raw_vals = row[1] if not isinstance(row, tuple) else row[1]
                scope_mode = row[2] if not isinstance(row, tuple) else row[2]
                if scope_mode != 'include':
                    continue
                if not raw_vals:
                    continue
                # 解析 dim_values (JSON 字符串)
                try:
                    parsed = json.loads(raw_vals) if isinstance(raw_vals, str) else raw_vals
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(parsed, list):
                    continue
                # 排除 wildcard '*'
                vals = []
                for v in parsed:
                    if isinstance(v, str) and v.strip() == '*':
                        continue
                    try:
                        vals.append(int(v))
                    except (ValueError, TypeError):
                        continue
                if vals:
                    result[dim_code] = vals
        except Exception:
            pass
        return result

    def _generate_dynamic_dim_scope_sql(
        self, dim_configs: Dict[str, List[int]]
    ) -> Dict[str, str]:
        """[P6 修复 2026-07-26] 根据 dim scope 原始配置生成动态子查询 SQL

        替代 derive_data_conditions 的静态 ID 列表,
        使用动态子查询以便新创建的对象自动包含

        例: dim_configs = {'domain': [2200]}
        生成:
        {
            'sub_domain': 'domain_id IN (SELECT id FROM domains WHERE id IN (2200))',
            'service_module': 'sub_domain_id IN (SELECT id FROM sub_domains WHERE domain_id IN (SELECT id FROM domains WHERE id IN (2200)))',
            'business_object': 'service_module_id IN (SELECT id FROM service_modules WHERE sub_domain_id IN (SELECT id FROM sub_domains WHERE domain_id IN (SELECT id FROM domains WHERE id IN (2200))))',
            'relationship': '(source_bo_id IN (SELECT id FROM business_objects WHERE service_module_id IN (SELECT id FROM service_modules WHERE sub_domain_id IN (SELECT id FROM sub_domains WHERE domain_id IN (SELECT id FROM domains WHERE id IN (2200)))))) OR (target_bo_id IN (SELECT id FROM business_objects WHERE service_module_id IN (SELECT id FROM service_modules WHERE sub_domain_id IN (SELECT id FROM sub_domains WHERE domain_id IN (SELECT id FROM domains WHERE id IN (2200))))))',
        }

        [设计选择]
          - 使用 "IN (SELECT id FROM <parent_table> WHERE id IN (vals))" 而非
            "<parent_field> IN (vals)" 是为了保持 SQL 结构一致, 便于后续递归
          - 不包含 wildcard (由 wildcard_affected_bos 处理)
          - 不包含 dim_code 自己 (用户配置静态 OK)
          - [P1-A5 2026-07-26] 包含 relationship: 通过 source_bo_id/target_bo_id 双向关联
        """
        if not dim_configs:
            return {}

        # HIERARCHY_CHAIN: product → version → domain → sub_domain
        # 每个 BO 的 (parent_field_on_this_table, table_name)
        # service_module 和 business_object 也在 chain 中 (EXTENDED_CHAIN)
        HIERARCHY_FK = [
            ('product', None, 'products'),
            ('version', 'product_id', 'versions'),
            ('domain', 'version_id', 'domains'),
            ('sub_domain', 'domain_id', 'sub_domains'),
            ('service_module', 'sub_domain_id', 'service_modules'),
            ('business_object', 'service_module_id', 'business_objects'),
        ]

        result: Dict[str, str] = {}
        for dim_code, dim_vals in dim_configs.items():
            if not dim_vals:
                continue

            # 找到 dim_code 在 HIERARCHY_FK 中的位置
            start_idx = None
            for i, (code, _, _) in enumerate(HIERARCHY_FK):
                if code == dim_code:
                    start_idx = i
                    break
            if start_idx is None:
                continue

            # 构造 vals SQL
            vals_sql = ','.join(str(int(v)) for v in dim_vals)

            # 当前 BO 的表名 (即 dim_code 的表)
            current_table = HIERARCHY_FK[start_idx][2]

            # inner_query 初始: 查 dim_code 表中 id 在 vals 的记录
            inner_query = f"SELECT id FROM {current_table} WHERE id IN ({vals_sql})"

            # 从 dim_code 向下生成动态子查询
            for i in range(start_idx + 1, len(HIERARCHY_FK)):
                child_code, child_fk_field, child_table = HIERARCHY_FK[i]

                # child_code 的 SQL (用于 bo_conditions)
                # 例: child=sub_domain, fk=domain_id, current=domains
                #   sql = "domain_id IN (SELECT id FROM domains WHERE id IN (2200))"
                sql = f"{child_fk_field} IN ({inner_query})"
                result[child_code] = sql

                # 更新 inner_query 用于下一层
                inner_query = (
                    f"SELECT id FROM {child_table} "
                    f"WHERE {child_fk_field} IN ({inner_query})"
                )
                current_table = child_table

            # [P1-A5 修复 2026-07-26] 添加 relationship 的动态 SQL
            # relationship 通过 source_bo_id 和 target_bo_id 双向关联 business_objects
            # 数据范围: source_bo 在 dim scope 内 OR target_bo 在 dim scope 内
            # 例: domain=[2200] → relationship.source_bo_id IN (...) OR target_bo_id IN (...)
            if start_idx < len(HIERARCHY_FK) - 1:
                # 只有当 dim_code 不是 business_object (最底层) 时才需要 relationship
                # 此时 inner_query 是 business_objects 的 id 子查询
                bo_inner_query = inner_query  # 已经是 SELECT id FROM business_objects WHERE ...
                rel_sql = (
                    f"(source_bo_id IN ({bo_inner_query})) "
                    f"OR (target_bo_id IN ({bo_inner_query}))"
                )
                result['relationship'] = rel_sql

        return result

    # ============================================================
    # [P0 修复 2026-07-26] FR-011 菜单反向推导 4 个方法
    # ============================================================
    def _load_role_menus(self, role_id: int) -> List[str]:
        """[P0 修复 2026-07-26] FR-011 加载角色已授权的 menu_code 列表

        从 role_menu_permissions 表加载 (role_id, menu_code) 关联.

        Args:
            role_id: 角色 ID

        Returns:
            [menu_code, ...]  e.g. ['domain_management', 'sub_domain_management', ...]

        [设计说明]
          - role_menu_permissions 表由 role_menu_api.py 维护
          - 表结构: (role_id, menu_code) 简单关联, 无 action 粒度
          - 菜单本身定义了 bo_bindings, 指明关联的 BO 和 role
          - 通过菜单授权, 用户间接获得 BO 的 read 权限
        """
        result: List[str] = []
        try:
            with sqlite3.connect(self._db_path) as conn:
                # 检查 role_menu_permissions 表是否存在
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='role_menu_permissions'"
                )
                if cursor.fetchone() is None:
                    return result  # 表不存在, 返回空

                rows = conn.execute(
                    'SELECT menu_code FROM role_menu_permissions WHERE role_id = ?',
                    [role_id],
                ).fetchall()
            for row in rows:
                menu_code = row[0] if not isinstance(row, tuple) else row[0]
                if menu_code:
                    result.append(menu_code)
        except sqlite3.Error:
            pass  # 表不存在或查询失败, 返回空
        return result

    def _derive_menus_from_dimensions(
        self,
        expanded: List[Dict[str, Any]],
    ) -> List[str]:
        """[P0 修复 2026-07-26] FR-011 维度→菜单推导

        基于已生成的 BO intents, 推导该角色应该看到的菜单列表.
        例: role 有 sub_domain:read intent → 推荐"子领域管理"菜单

        [推导规则]
          1. 从 expanded 中提取所有 bo_id (去重)
          2. 查询 menus 表, 找到 bo_bindings 中含这些 bo_id 的菜单
          3. 返回 menu_code 列表 (按 sort_order 排序)

        Args:
            expanded: 已推导的 intent 列表

        Returns:
            [menu_code, ...]  推导出的菜单列表
        """
        if not expanded:
            return []

        # 提取所有 bo_id
        bo_ids = sorted({i['bo_id'] for i in expanded if i.get('bo_id')})
        if not bo_ids:
            return []

        # 查询含这些 bo_id 的菜单
        try:
            with sqlite3.connect(self._db_path) as conn:
                # 检查 menus 表是否存在
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='menus'"
                )
                if cursor.fetchone() is None:
                    return []

                rows = conn.execute(
                    'SELECT menu_code, bo_bindings, sort_order FROM menus '
                    'WHERE is_active = 1 ORDER BY sort_order'
                ).fetchall()
        except sqlite3.Error:
            return []

        derived: List[str] = []
        for row in rows:
            menu_code = row[0]
            bo_bindings_raw = row[1]
            if not menu_code or not bo_bindings_raw:
                continue
            # 解析 bo_bindings JSON
            try:
                bindings = json.loads(bo_bindings_raw) if isinstance(bo_bindings_raw, str) else bo_bindings_raw
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(bindings, list):
                continue
            # 检查菜单是否绑定到 expanded 中的任意 bo_id
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                bound_bo_id = binding.get('bo_id')
                if bound_bo_id and bound_bo_id in bo_ids:
                    if menu_code not in derived:
                        derived.append(menu_code)
                    break  # 一个菜单只需匹配一个 bo_id
        return derived

    def _derive_intents_from_menus(
        self,
        menus: List[str],
    ) -> List[Dict[str, Any]]:
        """[P0 修复 2026-07-26] FR-011 菜单→BO actions 推导

        从角色已授权菜单的 bo_bindings 推导 BO actions intents.
        即使用户未配置 dim scope, 通过菜单授权也能获得 BO read 权限.

        [推导规则]
          1. 加载 menus 表中 bo_bindings 字段
          2. 对每个菜单的每个 binding, 提取 bo_id + include_actions
          3. 生成 (bo_id, action_name) intent, source='menu'
          4. data_scope = 空 include (全允许) + 空 exclude (无否决)
             原因: 菜单授权是功能性权限, 不限制数据范围

        Args:
            menus: 角色已授权的 menu_code 列表

        Returns:
            [{bo_id, action_name, data_scope, derivation_mode, source}, ...]
        """
        if not menus:
            return []

        # 加载菜单的 bo_bindings
        menu_bindings: List[Dict[str, Any]] = []
        try:
            with sqlite3.connect(self._db_path) as conn:
                # 检查 menus 表
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='menus'"
                )
                if cursor.fetchone() is None:
                    return []

                placeholders = ','.join('?' * len(menus))
                rows = conn.execute(
                    f'SELECT menu_code, bo_bindings FROM menus WHERE menu_code IN ({placeholders})',
                    menus,
                ).fetchall()
            for row in rows:
                menu_code = row[0]
                bo_bindings_raw = row[1]
                if not bo_bindings_raw:
                    continue
                try:
                    bindings = json.loads(bo_bindings_raw) if isinstance(bo_bindings_raw, str) else bo_bindings_raw
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(bindings, list):
                    continue
                for binding in bindings:
                    if not isinstance(binding, dict):
                        continue
                    binding_with_menu = dict(binding)
                    binding_with_menu['_from_menu'] = menu_code
                    menu_bindings.append(binding_with_menu)
        except sqlite3.Error:
            return []

        # 为每个 binding 生成 intents
        # 默认 action 集合: ['read', 'list', 'export'] (read level)
        # 如果 binding 指定 include_actions, 用指定的
        DEFAULT_MENU_ACTIONS = ['read', 'list', 'export']
        result: List[Dict[str, Any]] = []
        seen_keys: set = set()
        for binding in menu_bindings:
            bo_id = binding.get('bo_id')
            if not bo_id:
                continue
            include_actions = binding.get('include_actions')
            if include_actions and isinstance(include_actions, list):
                actions = [a.lower() for a in include_actions if isinstance(a, str)]
            else:
                actions = DEFAULT_MENU_ACTIONS
            for action_name in actions:
                key = (bo_id, action_name)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                result.append({
                    'bo_id': bo_id,
                    'action_name': action_name,
                    # data_scope = 空 include (允许所有), 空 exclude (无否决)
                    # 菜单授权是功能性权限, 数据范围由 dim_scope 控制
                    'data_scope': {'include': [], 'exclude': []},
                    'derivation_mode': 'static',
                    'source': 'menu',
                })
        return result

    def _suggest_menus_for_intents(
        self,
        expanded: List[Dict[str, Any]],
        current_menus: List[str],
    ) -> List[str]:
        """[P0 修复 2026-07-26] FR-011 反向建议应该授权的菜单

        基于已有 BO intents, 反向建议应该授权的菜单.
        用户已有 BO intent 但未授权对应菜单 → 建议授权.

        [推导规则]
          1. 提取 expanded 中的所有 bo_id
          2. 查询 menus 表, 找到绑定这些 bo_id 的菜单
          3. 过滤掉 current_menus 中已有的
          4. 返回建议的 menu_code 列表

        Args:
            expanded: 已推导的 intent 列表
            current_menus: 当前已授权的菜单列表

        Returns:
            [menu_code, ...]  建议追加授权的菜单
        """
        if not expanded:
            return []

        bo_ids = sorted({i['bo_id'] for i in expanded if i.get('bo_id')})
        if not bo_ids:
            return []

        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='menus'"
                )
                if cursor.fetchone() is None:
                    return []
                rows = conn.execute(
                    'SELECT menu_code, bo_bindings FROM menus WHERE is_active = 1'
                ).fetchall()
        except sqlite3.Error:
            return []

        suggestions: List[str] = []
        current_set = set(current_menus or [])
        for row in rows:
            menu_code = row[0]
            bo_bindings_raw = row[1]
            if not menu_code or menu_code in current_set:
                continue
            if not bo_bindings_raw:
                continue
            try:
                bindings = json.loads(bo_bindings_raw) if isinstance(bo_bindings_raw, str) else bo_bindings_raw
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(bindings, list):
                continue
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                bound_bo_id = binding.get('bo_id')
                if bound_bo_id and bound_bo_id in bo_ids:
                    if menu_code not in suggestions:
                        suggestions.append(menu_code)
                    break
        return suggestions

    # ============================================================
    # [P1-A7 2026-07-26] FR-012 对象基线 OWD
    # ============================================================
    def _load_object_owd(self) -> Dict[str, Dict[str, Any]]:
        """[P1-A7 2026-07-26] FR-012 加载 object_owd 表 (对象基线)

        OWD (Object Wide Defaults) 借鉴 Salesforce 概念, 为每个 BO 定义默认可见性:
          - private:           仅 owner 可见 (默认, 拒绝其他用户)
          - public_read:       所有用户可读 (兜底 read intent)
          - public_read_write: 所有用户可读写 (兜底 read+create+update intent)

        在 derive() 中, OWD 作为最低优先级的兜底 intent (source='owd'):
          - 优先级: manual > derived > menu > owd
          - 当角色对某 BO 无任何配置时, 使用 OWD 作为基线

        Returns:
            {bo_id: {'visibility': str, 'permission_level': str}, ...}
            例: {'product': {'visibility': 'private', 'permission_level': 'none'},
                 'enum_type': {'visibility': 'public_read', 'permission_level': 'read'}}
        """
        result: Dict[str, Dict[str, Any]] = {}
        try:
            with sqlite3.connect(self._db_path) as conn:
                # 检查 object_owd 表是否存在
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='object_owd'"
                )
                if cursor.fetchone() is None:
                    return result  # 表不存在, 返回空

                rows = conn.execute(
                    'SELECT bo_id, default_visibility, default_permission_level '
                    'FROM object_owd'
                ).fetchall()
            for row in rows:
                bo_id = row[0] if not isinstance(row, tuple) else row[0]
                visibility = row[1] if not isinstance(row, tuple) else row[1]
                level = row[2] if not isinstance(row, tuple) else row[2]
                if bo_id:
                    result[bo_id] = {
                        'visibility': visibility or 'private',
                        'permission_level': level or 'none',
                    }
        except sqlite3.Error:
            pass  # 表不存在或查询失败, 返回空
        return result

    def _apply_owd_baseline(
        self,
        expanded: List[Dict[str, Any]],
        owd: Dict[str, Dict[str, Any]],
    ) -> None:
        """[P1-A7 2026-07-26] FR-012 应用 OWD 兜底 (原地修改 expanded)

        [应用规则]
          - 对每个 OWD 配置的 BO, 检查 expanded 中是否已有 intent
          - 若已有 (来自 manual/derived/menu), 跳过 (OWD 是最低优先级)
          - 若无, 根据 OWD visibility 添加兜底 intent:
            * private:           不添加 (默认拒绝, 仅 owner 可见, 由 owner 检查处理)
            * public_read:       添加 read+list+export intent (空 include = 全允许)
            * public_read_write: 添加 read+list+export+create+update intent

        [设计说明]
          - OWD intent 的 data_scope = 空 include (允许所有), 空 exclude (无否决)
            原因: OWD 是组织级默认, 不限制具体数据范围
          - source='owd' 标记, IntentScopeAdapter 可识别并应用
          - derivation_mode='static' (OWD 是静态配置)

        Args:
            expanded: derived + manual 合并后的 intent 列表 (会被原地修改)
            owd: object_owd 配置字典
        """
        if not owd:
            return

        # 构建现有 (bo_id, action_name) → intent 索引
        existing_keys: set = set()
        for intent in expanded:
            existing_keys.add((intent['bo_id'], intent['action_name']))

        for bo_id, config in owd.items():
            visibility = config.get('visibility', 'private')
            level = config.get('permission_level', 'none')

            # 根据 visibility 决定要添加的 actions
            if visibility == 'public_read':
                # public_read: 添加 read level (read+list+export)
                actions_to_add = ['read', 'list', 'export']
            elif visibility == 'public_read_write':
                # public_read_write: 添加 write level (read+list+export+create+update)
                actions_to_add = ['read', 'list', 'export', 'create', 'update']
                # 如果 permission_level=admin, 还添加 delete
                if level == 'admin':
                    actions_to_add.append('delete')
            else:
                # private 或其他: 不添加兜底 intent
                # private 对象仅 owner 可见, 由 EffectiveIntentChecker._is_owner 处理
                continue

            # 添加缺失的 OWD intent
            for action_name in actions_to_add:
                key = (bo_id, action_name)
                if key in existing_keys:
                    continue  # 已有 (来自更高优先级 source), 跳过
                expanded.append({
                    'bo_id': bo_id,
                    'action_name': action_name,
                    # 空 include = 全允许, 空 exclude = 无否决
                    # OWD 是组织级默认, 不限制具体数据范围
                    'data_scope': {'include': [], 'exclude': []},
                    'derivation_mode': 'static',
                    'source': 'owd',
                })
                existing_keys.add(key)
