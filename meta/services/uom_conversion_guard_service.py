# -*- coding: utf-8 -*-
"""计量单位换算守卫 —— 跨对象一致性校验（两层模型）。

依据:
  docs/superpowers/specs/2026-10-24-uom-conversion-model-design.md §6（一期 V1–V8）
  docs/superpowers/specs/2026-10-24-uom-group-tier-upgrade/spec.md §4（二期 V9–V14）

两层换算：
  item_uom_conversion —— 物料级例外（允许跨组，如 KG ↔ PC）；
  uom_conversion      —— 组内标准换算（uom 必须属组，且以组基本单位 base_uom_id 为基准）。

各条落点（V1 / V3 不在此处）：
  V1 factor > 0 且 ≤10 位小数 —— 字段级 `constraints: numeric_range`，
     由 `MetadataDrivenValidator._check_numeric_range` 执行；
  V3 唯一键（item 级 / 组级各自）—— 唯一索引 + `_check_unique_indexes`；
  V2 / V4 / V5 —— `validate_conversion_write`（物料级换算行写前）；
  V7 —— `validate_item_update`（物料改基本单位前）；
  V8 / V14 —— `validate_uom_update`（单位停用前，含类级引用与组基本单位占用）；
  V9 / V10 —— `validate_group_conversion_write`（组内换算行写前）；
  V11 / V12 —— `validate_group_update`（组改基本单位前）；
  V13 —— `validate_uom_group_change`（单位改组前）。

查询失败一律 fail-open + 告警（与 party_relation 镜像行守卫同口径）：
读侧守卫不应因一次瞬时查询异常把整条写入路径打死。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: 物料「已签发」口径：draft = 未签发；active / frozen / inactive 均为已签发过的物料
_UNISSUED_STATUS = 'draft'


class UomConversionGuardError(ValueError):
    """换算守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


class UomConversionGuardService:
    """两类单位换算（物料级 / 组级）的跨对象校验。

    覆写 `_fetch_*` / `_count_*` 即可注入测试数据（不依赖真实库）。
    """

    ITEM_TABLE = 'items'
    UOM_TABLE = 'uoms'
    GROUP_TABLE = 'uom_groups'
    ITEM_CONV_TABLE = 'item_uom_conversions'
    GROUP_CONV_TABLE = 'uom_conversions'

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口：物料级换算 ----------

    def validate_conversion_write(self, data: Dict[str, Any]) -> None:
        """物料级换算行写入前校验 V5 / V4 / V2。"""
        item_id = data.get('item_id')
        uom_id = data.get('uom_id')

        item = self._fetch_item(item_id) if item_id is not None else None
        if item is not None and item.get('status') == _UNISSUED_STATUS:
            raise UomConversionGuardError(
                '未签发（草稿）物料不允许维护单位换算，请先签发物料',
                field_name='物料', rule='item_not_issued')

        uom = self._fetch_uom(uom_id) if uom_id is not None else None
        if uom is not None and uom.get('status') != 'active':
            name = uom.get('name') or uom_id
            raise UomConversionGuardError(
                f'计量单位「{name}」已停用，不能新增换算',
                field_name='换算单位', rule='uom_inactive')

        # V2 依赖物料的基本单位；物料行取不到时（脏数据 / 越权）交给 FK 校验兜底
        if item is not None and uom_id is not None:
            base_uom = item.get('base_uom')
            if base_uom is not None and str(uom_id) == str(base_uom):
                raise UomConversionGuardError(
                    '换算单位不能与物料的基本单位相同',
                    field_name='换算单位', rule='uom_equals_base')

    # ---------- 公开入口：组级标准换算 ----------

    def validate_group_conversion_write(self, data: Dict[str, Any]) -> None:
        """组内换算行写入前校验 V9 / V10 / V4。"""
        group_id = data.get('uom_group_id')
        uom_id = data.get('uom_id')

        group = self._fetch_group(group_id) if group_id is not None else None
        if group is not None and group.get('status') != 'active':
            name = group.get('name') or group_id
            raise UomConversionGuardError(
                f'计量单位组「{name}」已停用，不能维护组内换算',
                field_name='计量单位组', rule='group_inactive')

        # V10（前半）：组没有基本单位时，换算率无基准，拒绝维护
        if group is not None and group.get('base_uom_id') is None:
            raise UomConversionGuardError(
                '该组尚未设置基本单位，无法定义组内换算率；请先在组上选择基本单位',
                field_name='计量单位组', rule='group_base_uom_unset')

        uom = self._fetch_uom(uom_id) if uom_id is not None else None
        if uom is None:
            return  # 单位行取不到时交给 FK 存在性校验兜底

        if uom.get('status') != 'active':
            name = uom.get('name') or uom_id
            raise UomConversionGuardError(
                f'计量单位「{name}」已停用，不能新增换算',
                field_name='换算单位', rule='uom_inactive')

        if group is not None:
            # V9：组内换算的单位必须属于本组
            uom_group_id = uom.get('uom_group_id')
            if uom_group_id is None or str(uom_group_id) != str(group_id):
                raise UomConversionGuardError(
                    '组内换算的单位必须属于该计量单位组',
                    field_name='换算单位', rule='uom_group_mismatch')
            # V10（后半）：换算单位不能就是组基本单位
            if str(uom_id) == str(group.get('base_uom_id')):
                raise UomConversionGuardError(
                    '换算单位不能与组基本单位相同（基本单位的换算率恒为 1，无需定义）',
                    field_name='换算单位', rule='uom_equals_group_base')

    # ---------- 公开入口：物料 / 单位 / 组更新 ----------

    def validate_item_update(self, item_id: Any, new_base_uom: Any) -> None:
        """物料更新前校验 V7：已有换算行时禁止变更基本单位。"""
        if item_id is None or new_base_uom is None:
            return
        item = self._fetch_item(item_id)
        if item is None:
            return
        old_base = item.get('base_uom')
        if old_base is None or str(old_base) == str(new_base_uom):
            return
        count = self._count_by_item(item_id)
        if count:
            raise UomConversionGuardError(
                f'该物料已维护 {count} 条单位换算，变更基本单位会使全部换算失效，请先清理换算记录',
                field_name='基本单位', rule='base_uom_locked')

    def validate_uom_update(self, uom_id: Any, new_status: Any) -> None:
        """单位更新前校验 V8 / V14：被引用的单位禁止停用。"""
        if uom_id is None or new_status != 'inactive':
            return
        uom = self._fetch_uom(uom_id)
        if uom is not None and uom.get('status') == 'inactive':
            return  # 已是停用态，重复提交不拦

        item_count = self._count_by_uom(uom_id)
        if item_count:
            raise UomConversionGuardError(
                f'该单位被 {item_count} 条物料换算引用，请先清理换算记录后再停用',
                field_name='状态', rule='uom_referenced')

        group_conv_count = self._count_group_conv_by_uom(uom_id)
        if group_conv_count:
            raise UomConversionGuardError(
                f'该单位被 {group_conv_count} 条组内换算引用，请先清理换算记录后再停用',
                field_name='状态', rule='uom_referenced')

        base_count = self._count_group_by_base(uom_id)
        if base_count:
            raise UomConversionGuardError(
                f'该单位是 {base_count} 个计量单位组的基本单位，请先更换组基本单位后再停用',
                field_name='状态', rule='uom_is_group_base')

    def validate_uom_group_change(self, uom_id: Any, new_group_id: Any) -> None:
        """单位更新前校验 V13：已有组内换算的单位禁止改组。"""
        if uom_id is None or new_group_id is None:
            return
        uom = self._fetch_uom(uom_id)
        if uom is None:
            return
        old_group_id = uom.get('uom_group_id')
        if old_group_id is not None and str(old_group_id) == str(new_group_id):
            return
        count = self._count_group_conv_by_uom(uom_id)
        if count:
            raise UomConversionGuardError(
                f'该单位已维护 {count} 条组内换算，变更所属组会使换算失效，请先清理换算记录',
                field_name='计量单位组', rule='uom_group_locked')

    def validate_group_update(self, group_id: Any, new_base_uom: Any) -> None:
        """组更新前校验 V11 / V12：基本单位变更的锁定与有效性。"""
        if group_id is None:
            return
        group = self._fetch_group(group_id)
        if group is None:
            return
        old_base = group.get('base_uom_id')
        if old_base is None and new_base_uom is None:
            return  # 未变更（均为空）
        if old_base is not None and new_base_uom is not None \
                and str(old_base) == str(new_base_uom):
            return  # 未变更

        if new_base_uom is not None:
            uom = self._fetch_uom(new_base_uom)
            if uom is not None:
                # V12：基本单位必须属于本组且启用
                uom_group_id = uom.get('uom_group_id')
                if uom_group_id is None or str(uom_group_id) != str(group_id):
                    raise UomConversionGuardError(
                        '基本单位必须属于本计量单位组',
                        field_name='基本单位', rule='base_uom_group_mismatch')
                if uom.get('status') != 'active':
                    name = uom.get('name') or new_base_uom
                    raise UomConversionGuardError(
                        f'计量单位「{name}」已停用，不能设为组基本单位',
                        field_name='基本单位', rule='base_uom_inactive')

        # V11：已有组内换算时，基本单位（含清空）一律锁定
        count = self._count_group_conv_by_group(group_id)
        if count:
            raise UomConversionGuardError(
                f'该组已维护 {count} 条组内换算，变更基本单位会使全部换算失效，请先清理换算记录',
                field_name='基本单位', rule='base_uom_locked')

    # ---------- 查询（可覆写，便于单测注入）----------

    def _one(self, sql: str, params: list) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open（不阻断正常写入）
            logger.warning(f'[uom_conversion_guard] 查询失败: {e}')
            return None
        return rows[0] if rows else None

    def _fetch_item(self, item_id: Any) -> Optional[Dict[str, Any]]:
        return self._one(
            f"SELECT id, base_uom, status FROM {self.ITEM_TABLE} WHERE id = ?",
            [item_id])

    def _fetch_uom(self, uom_id: Any) -> Optional[Dict[str, Any]]:
        return self._one(
            f"SELECT id, name, status, uom_group_id FROM {self.UOM_TABLE} WHERE id = ?",
            [uom_id])

    def _fetch_group(self, group_id: Any) -> Optional[Dict[str, Any]]:
        return self._one(
            f"SELECT id, name, base_uom_id, status FROM {self.GROUP_TABLE} WHERE id = ?",
            [group_id])

    def _count_by_item(self, item_id: Any) -> int:
        return self._count(
            f"SELECT COUNT(*) AS cnt FROM {self.ITEM_CONV_TABLE} WHERE item_id = ?",
            [item_id])

    def _count_by_uom(self, uom_id: Any) -> int:
        return self._count(
            f"SELECT COUNT(*) AS cnt FROM {self.ITEM_CONV_TABLE} WHERE uom_id = ?",
            [uom_id])

    def _count_group_conv_by_uom(self, uom_id: Any) -> int:
        return self._count(
            f"SELECT COUNT(*) AS cnt FROM {self.GROUP_CONV_TABLE} WHERE uom_id = ?",
            [uom_id])

    def _count_group_conv_by_group(self, group_id: Any) -> int:
        return self._count(
            f"SELECT COUNT(*) AS cnt FROM {self.GROUP_CONV_TABLE} WHERE uom_group_id = ?",
            [group_id])

    def _count_group_by_base(self, uom_id: Any) -> int:
        return self._count(
            f"SELECT COUNT(*) AS cnt FROM {self.GROUP_TABLE} WHERE base_uom_id = ?",
            [uom_id])

    def _count(self, sql: str, params: list) -> int:
        row = self._one(sql, params)
        if not row:
            return 0
        try:
            return int(row.get('cnt') or 0)
        except (TypeError, ValueError):
            return 0
