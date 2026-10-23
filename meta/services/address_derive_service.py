"""地址全文（formatted_address）写前派生。

口径（2026-10-23定案）：formatted_address 是本对象7 个结构化字段的**拼接结果**，
不是独立业务输入。原先要求用户手填且必填，导致：
  1. 重复录入——国家/省/市/区/街道/门牌填完还要再打一遍；
  2. 数据不一致——改了「区」忘了同步全文，库里就存了两份矛盾数据。

改由系统派生后，``required`` 约束依然保留（它同时是 display_name_field，
列表 / FK 回显 / 详情标题都靠它，为空会出现空白行），但用户不再需要输入。

拼接口径：区划部分走**层级链**——取四个区划字段中最深的那个 id，沿 regions.parent_id
上溯到根，拼出「国家→省→市→区」完整路径；而非按字段固定顺序无条件全拼。
原因：直辖市（北京/上海/天津/重庆）的省与市是同一个「北京市」，
固定顺序会拼出「北京市北京市」；同理手工填入同一 id 也会重复。
空片段跳过（不产生连续空格）；街道 → 门牌 → 邮编依次接在路径之后。
客户端自带的值一律丢弃，避免绕过派生口径。
"""

from typing import Any, Dict, List


class AddressDeriveService:
    """地址格式化全文派生服务。"""

    ADDRESS_TABLE = 'addresses'
    REGION_TABLE = 'regions'

    #: 区划级联字段（由浅到深），用于取最深的那个 id 作为层级链起点
    REGION_FIELDS = ('country_id', 'province_id', 'city_id', 'district_id')

    #: 需从库中原值补齐的字段（update 载荷只含被改字段，
    #: 未改的省/市/区若不补齐，拼接结果会丢前缀 ⇒ display_name 残缺）
    STRUCTURE_FIELDS = REGION_FIELDS + ('street', 'street_number', 'postal_code')

    #: 层级链最大深度（防御异常parent_id 成环）
    MAX_DEPTH = 8

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 对外入口 ----------

    def derive_formatted_address(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """按结构化字段派生地址全文。

        Args:
            data: 待保存的数据字典（不修改入参，返回新 dict）

        Returns:
            补写 ``formatted_address`` 后的数据字典

        Raises:
            Exception: 区划/原值查询失败（schema 异常须显式暴露，
                不得静默写入残缺全文——那会污染 display_name）
        """
        data = dict(data)

        # update 时载荷只含被改字段，先合并库中原值再拼接
        if 'id' in data:
            data = self._merge_existing(data)

        parts: List[str] = self._region_path(data)
        parts.extend([
            str(data.get('street') or '').strip(),
            str(data.get('street_number') or '').strip(),
        ])

        segments = [p for p in parts if p]
        postal_code = str(data.get('postal_code') or '').strip()
        if postal_code:
            segments.append(postal_code)

        # 全部结构化字段皆空时不写入，让 required 校验给出标准错误，
        # 而不是硬塞一个空串把「地址无内容」伪装成合法记录
        if not segments:
            data.pop('formatted_address', None)
            return data

        data['formatted_address'] = ''.join(segments)
        return data

    # ---------- 内部 ----------

    def _region_path(self, data: Dict[str, Any]) -> List[str]:
        """取区划层级路径（国家 → 省 → 市 → 区），根在前。

        以四个级联字段中最深的 id 为起点，沿 parent_id 上溯。
        """
        deepest = None
        for f in self.REGION_FIELDS:
            rid = data.get(f)
            if rid is not None:
                deepest = rid
        if deepest is None:
            return []

        chain = self._ancestor_chain(deepest)
        return [name for name in chain if name]

    def _ancestor_chain(self, region_id) -> List[str]:
        """从 region_id 沿 parent_id 上溯到根，返回 [根, ..., region_id] 的名称列表。

        一次批量取回链上所有 id 的 name，避免逐级往返。
        """
        # 先沿 parent_id 找完整 id 链（只需 id/parent_id 两列）
        ids: List[Any] = []
        current = region_id
        seen = set()
        while current is not None and len(ids) < self.MAX_DEPTH:
            if current in seen:  # parent_id 成环 ⇒ 截断
                break
            seen.add(current)
            ids.append(current)
            row = self._region_row(current)
            if not row:
                break
            current = row.get('parent_id')

        if not ids:
            return []

        placeholders = ','.join('?' for _ in ids)
        sql = (
            f"SELECT id, name FROM {self.REGION_TABLE} "
            f"WHERE id IN ({placeholders})"
        )
        rows = self.ds.query(sql, ids)
        names = {r.get('id'): (r.get('name') or '') for r in rows}
        # ids 是 [最深, ..., 根]，反转为 [根, ..., 最深]
        return [names.get(i, '') for i in reversed(ids)]

    def _region_row(self, region_id) -> Dict[str, Any]:
        """取单个区划的 id/parent_id。"""
        rows = self.ds.query(
            f"SELECT id, parent_id FROM {self.REGION_TABLE} WHERE id = ?",
            [region_id])
        return rows[0] if rows else {}

    def _merge_existing(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """把载荷未覆盖的结构化字段用库中原值补齐（键名=db_column）。

        载荷显式传入的值优先（含显式置空），故只补缺失键。
        """
        missing = [f for f in self.STRUCTURE_FIELDS if f not in data]
        if not missing:
            return data

        cols = ', '.join(missing)
        sql = f"SELECT {cols} FROM {self.ADDRESS_TABLE} WHERE id = ?"
        rows = self.ds.query(sql, [data['id']])
        if not rows:
            return data
        row = rows[0]
        merged = dict(data)
        for f in missing:
            merged[f] = row.get(f)
        return merged


def derive_formatted_address_hook(data_source, data: Dict[str, Any]) -> Dict[str, Any]:
    """写前派生钩子：供``ComputedFieldHandler.register_hook`` 注册。

    薄封装以便测试覆写 :class:`AddressDeriveService` 的查询方法。
    """
    return AddressDeriveService(data_source).derive_formatted_address(data)