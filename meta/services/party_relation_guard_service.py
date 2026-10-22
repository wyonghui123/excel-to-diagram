# -*- coding: utf-8 -*-
"""party_relation 镜像行守卫 —— 同一对单位在同角色同法人域下的无序去重。

依据: docs/superpowers/specs/2026-10-20-party-relation-role-dictionary-and-mirror-guard.md
      §4.4（落点）/ §4.5（判定口径）

背景（spec §1.2）: F2 D5 的唯一键是**有向**四元组 (party1_id, party2_id, role, le_org_id)
  部分唯一索引（condition: `le_org_id IS NOT NULL`）。方向相反的镜像行
  (A,B) 与 (B,A) 是两组不同的元组 ⇒ 索引不冲突、合法入库 ⇒「谁是客户谁是供应商」
  不可判定、后续单据挂边二义。本服务在写入路径补无序去重 ——
  **不改表结构、不改索引**。

口径（spec §4.5）:
  · 同 role + 同 le_org_id + 存在反向行 ⇒ 拒；
  · `le_org_id` 为空的行不参与（与部分唯一索引 condition 口径一致）；
  · update 场景排除自身（`exclude_id`），避免误伤。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: 角色码 → 中文标签（消息用语；新角色未登记时回退为原始码）
_ROLE_LABELS = {
    'customer': '客户',
    'vendor': '供应商',
}


class MirrorRowError(ValueError):
    """检测到镜像行（同角色同法人域下存在反向关系）—— 拒绝写入。"""


class SelfRelationError(ValueError):
    """检测到自反关系（我方侧与对手侧是同一个单位）—— 拒绝写入。

    [2026-10-20] 独立成类而非复用 MirrorRowError：调用方按类型分流文案，
    且「两侧同单位」与「存在反向行」是两件事，不应混为一谈。
    """


class PartyRelationGuardService:
    """party_relation 镜像行守卫。

    覆写 :meth:`_find_mirror` / :meth:`_party_names` 可注入测试数据（避免依赖真实库）。
    """

    TABLE = 'party_relations'
    PARTY_TABLE = 'parties'

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def assert_no_mirror(self,
                         data: Dict[str, Any],
                         exclude_id: Optional[int] = None) -> None:
        """校验入参 `data` 是否存在镜像行；存在则抛 :class:`MirrorRowError`。

        Args:
            data: 写入载荷（含 party1_id / party2_id / role / le_org_id）
            exclude_id: update 场景的自身行 id（排除自身，避免误伤）

        Raises:
            MirrorRowError: 同一对单位在同角色同法人域下已存在反向行
        """
        party1_id = data.get('party1_id')
        party2_id = data.get('party2_id')
        role = data.get('role')
        le_org_id = data.get('le_org_id')

        # [2026-10-20] 自反关系（两侧同一单位）恒非法：与 role / le_org_id 无关。
        #   镜像查询对 A==B 是盲的（SQL 查反向行，A==B 时查到的就是自己那组），
        #   故必须在镜像判定之前拦截，否则会被放行。
        if (party1_id is not None and party2_id is not None
                and str(party1_id) == str(party2_id)):
            raise SelfRelationError(self._build_self_message(party1_id))

        # 三要素齐备才判定；le_org_id 为空 ⇒ 不参与（与部唯一索引 condition 口径一致）
        if party1_id is None or party2_id is None or role is None:
            return
        if le_org_id is None:
            return

        mirror = self._find_mirror(
            party1_id=party1_id,
            party2_id=party2_id,
            role=role,
            le_org_id=le_org_id,
            exclude_id=exclude_id,
        )
        if mirror is not None:
            raise MirrorRowError(self._build_message(party1_id, party2_id, role))

    # ---------- 查询 / 文案（可覆写，便于单测注入）----------

    def _find_mirror(self, *, party1_id: Any, party2_id: Any, role: Any,
                     le_org_id: Any, exclude_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """查询反向行（`party1_id` = 本 `party2_id` 且 `party2_id` = 本 `party1_id`）。

        返回命中的反向行（dict）或 None。
        """
        sql = (
            f"SELECT id, party1_id, party2_id, role, le_org_id "
            f"FROM {self.TABLE} "
            "WHERE party1_id = ? AND party2_id = ? AND role = ? AND le_org_id = ?"
        )
        params = [party2_id, party1_id, role, le_org_id]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        sql += " LIMIT 1"
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open（不阻断正常写入）
            logger.warning(f'[party_relation_guard] 镜像行查询失败: {e}')
            return None
        return rows[0] if rows else None

    def _party_names(self, party_ids) -> Dict[Any, str]:
        """按 id 批量取 party 显示名（best-effort；失败回退为空表 → 用 id 呈现）。"""
        ids = [i for i in party_ids if i is not None]
        if not ids:
            return {}
        placeholders = ','.join('?' for _ in ids)
        sql = f"SELECT id, name FROM {self.PARTY_TABLE} WHERE id IN ({placeholders})"
        try:
            rows = self.ds.query(sql, ids)
        except Exception as e:  # 名称解析失败不影响拦截语义
            logger.warning(f'[party_relation_guard] party 显示名解析失败: {e}')
            return {}
        return {r.get('id'): r.get('name') for r in rows}

    # ---------- 派生 ----------

    def derive_internal_mark(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """按对手侧往来单位的来源派生内外标记（internal_mark）。

        口径：对手侧 ``parties.source = 'org'`` ⇒ ``internal``，否则 ``external``。
        标记非判定（I3-A），只是关系实例自身的分类标签；判定仍归 org / 法人关系。

        仅当载荷含 ``party2_id`` 时改写：create 必含；update 仅在改对手侧时重新派生，
        未改对手侧的更新保留库中原值（不无谓覆盖）。客户端自带的值一律丢弃。

        Raises:
            Exception: 来源查询失败（schema 异常须显式暴露，不得静默写 external）
        """
        data = dict(data)
        party2_id = data.get('party2_id')
        if party2_id is None:
            # 未涉及对手侧：不猜值，也不接受客户端自带值（DB 保留原值）
            data.pop('internal_mark', None)
            return data

        sources = self._party_sources([party2_id])
        if party2_id not in sources:
            # 对手侧不存在属输入错误，交由后续 FK 存在性校验给出标准错误；
            # 此处不猜值，避免把无效输入静默标成 external。
            logger.warning(
                f'[party_relation_guard] 内外标记派生跳过: party2_id={party2_id} 不存在'
            )
            data.pop('internal_mark', None)
            return data

        data['internal_mark'] = (
            'internal' if sources[party2_id] == 'org' else 'external'
        )
        return data

    def _party_sources(self, party_ids) -> Dict[Any, Any]:
        """按 id 批量取 party 来源（source='org' 为内部组织表示，其余为对外）。"""
        ids = [i for i in party_ids if i is not None]
        if not ids:
            return {}
        placeholders = ','.join('?' for _ in ids)
        sql = f"SELECT id, source FROM {self.PARTY_TABLE} WHERE id IN ({placeholders})"
        rows = self.ds.query(sql, ids)
        return {r.get('id'): r.get('source') for r in rows}

    def _build_message(self, party1_id: Any, party2_id: Any, role: Any) -> str:
        """构造面向用户的拒写消息（显式指出反向行，而非泛化「唯一性冲突」）。"""
        names = self._party_names([party1_id, party2_id])

        def _label(pid):
            return names.get(pid) or str(pid)

        role_label = _ROLE_LABELS.get(str(role), str(role))
        return (
            f"往来自「{_label(party2_id)}」到「{_label(party1_id)}」的反向关系已存在"
            f"（角色：{role_label}），同一法人范围内同一对单位只应存在一条关系"
        )

    def _build_self_message(self, party_id: Any) -> str:
        """构造自反关系的拒写消息（我方侧与对手侧不能是同一个单位）。"""
        name = self._party_names([party_id]).get(party_id) or str(party_id)
        return f"我方侧与对手侧不能是同一个往来单位（{name}）"


def derive_internal_mark_hook(data_source, data: Dict[str, Any]) -> Dict[str, Any]:
    """写前派生钩子：供 ``ComputedFieldHandler.register_hook`` 注册。

    薄封装以便测试覆写 :class:`PartyRelationGuardService` 的查询方法。
    """
    return PartyRelationGuardService(data_source).derive_internal_mark(data)
