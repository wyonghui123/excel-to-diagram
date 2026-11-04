# -*- coding: utf-8 -*-
"""包装容器服务（HU / LPN）—— P6a-2。

依据: docs/specs/p6-serial-number-model/spec.md §11
口径:
  · HU 是库存之上的物流层；inventory_balances 不增加 hu_id，余额仍按
    (item, org, location, batch) 记（§11.1 / §11.13.1）。
  · 单父 + 冗余根（parent_hu_id / root_hu_id），禁止 DAG（H2）。
  · open → sealed → shipped，加 void；状态只由本服务流转（H4）。
  · 组织内唯一 (org_id, hu_no)；跨组织靠复制结构，不改 org_id（H1）。
  · 不生成 SSCC，仅校验 18 位纯数字的 GS1 校验位（H6）。
  · 不自动汇总重量体积（H7）；允许混物料混批次（H9）。
  · content_type='hu' 行只表达嵌套且 qty=0；数量汇总只取 material 行（§11.13）。
  · 服务不 commit；由调用方 framework.transaction() 包裹。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HU_TABLE = 'handling_units'
ITEM_TABLE = 'handling_unit_items'
TX_TABLE = 'hu_transactions'
SERIAL_TABLE = 'serial_numbers'
SERIAL_TX_TABLE = 'serial_transactions'
LINK_TABLE = 'document_serial_links'
ORG_TABLE = 'orgs'
LOCATION_TABLE = 'locations'
BATCH_TABLE = 'batches'
RECEIPT_TABLE = 'receipts'
RECEIPT_LINE_TABLE = 'receipt_lines'
SHIPMENT_TABLE = 'shipments'
SHIPMENT_LINE_TABLE = 'shipment_lines'
TRANSFER_TABLE = 'transfer_orders'
TRANSFER_LINE_TABLE = 'transfer_order_lines'

STATUS_OPEN = 'open'
STATUS_SEALED = 'sealed'
STATUS_SHIPPED = 'shipped'
STATUS_VOID = 'void'
HU_STATUSES = (STATUS_OPEN, STATUS_SEALED, STATUS_SHIPPED, STATUS_VOID)
HU_TYPES = ('pallet', 'carton', 'bin', 'container', 'other')

CONTENT_MATERIAL = 'material'
CONTENT_PACKAGING = 'packaging'
CONTENT_HU = 'hu'
CONTENT_TYPES = (CONTENT_MATERIAL, CONTENT_PACKAGING, CONTENT_HU)

TXN_CREATE = 'create'
TXN_PACK = 'pack'
TXN_UNPACK = 'unpack'
TXN_MOVE = 'move'
TXN_CONSOLIDATE = 'consolidate'
TXN_SPLIT = 'split'
TXN_SEAL = 'seal'
TXN_UNSEAL = 'unseal'
TXN_SHIP = 'ship'
TXN_REVERSE = 'reverse'
TXN_REUSE = 'reuse'
TXN_VOID = 'void'
TXN_TYPES = (TXN_CREATE, TXN_PACK, TXN_UNPACK, TXN_MOVE, TXN_CONSOLIDATE,
             TXN_SPLIT, TXN_SEAL, TXN_UNSEAL, TXN_SHIP, TXN_REVERSE,
             TXN_REUSE, TXN_VOID)

DOC_RECEIPT = 'receipt'
DOC_SHIPMENT = 'shipment'
DOC_TRANSFER = 'transfer_order'


def hu_schema_ready(ds: Any) -> bool:
    """P6a-2 前置：三张 HU 表齐全才启用装箱 / 整箱发运钩子。"""
    try:
        rows = ds.query(
            'SELECT name FROM sqlite_master WHERE type = ? AND name IN (?, ?, ?)',
            ['table', HU_TABLE, ITEM_TABLE, TX_TABLE])
        return len({row.get('name') for row in rows}) >= 3
    except Exception:
        return False


class HandlingUnitError(Exception):
    """包装容器业务校验错误。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _sscc_valid(hu_no: str) -> bool:
    """18 位纯数字时校验 GS1 mod-10 校验位；其他格式放行（H6）。"""
    if len(hu_no) != 18 or not hu_no.isdigit():
        return True
    body, check = hu_no[:17], int(hu_no[17])
    total = 0
    for index, char in enumerate(reversed(body)):
        total += int(char) * (3 if index % 2 == 0 else 1)
    return (10 - total % 10) % 10 == check


class HandlingUnitService:
    """容器主档 / 内容投影 / 事件账的唯一写入口。"""

    def __init__(self, data_source=None):
        self._ds = data_source

    @property
    def ds(self):
        if self._ds is None:
            from meta.core.datasource import get_data_source
            from meta.core.db_path import get_meta_db_path
            self._ds = get_data_source('sqlite', database=get_meta_db_path())
        return self._ds

    # ------------------------------------------------------------------
    # 基础读取
    # ------------------------------------------------------------------
    def _require_row(self, table: str, row_id: Any, label: str,
                     rule: str) -> Dict[str, Any]:
        rows = self.ds.query('SELECT * FROM %s WHERE id = ?' % table, [row_id])
        if not rows:
            raise HandlingUnitError('%s不存在：%s' % (label, row_id),
                                    field_name='id', rule=rule)
        return rows[0]

    def _get_hu(self, hu_id: Any) -> Dict[str, Any]:
        return self._require_row(HU_TABLE, hu_id, '包装容器', 'HU_NOT_FOUND')

    def _find_hu(self, hu_no: Any, org_id: Any = None) -> Optional[Dict[str, Any]]:
        sql = 'SELECT * FROM %s WHERE hu_no = ?' % HU_TABLE
        params: List[Any] = [str(hu_no or '').strip()]
        if not _blank(org_id):
            sql += ' AND org_id = ?'
            params.append(org_id)
        rows = self.ds.query(sql + ' ORDER BY id', params)
        return rows[0] if rows else None

    def _resolve_hu(self, ref: Any, org_id: Any = None) -> Dict[str, Any]:
        """按 id 或容器号解析；容器号需配合 org_id。"""
        if isinstance(ref, int):
            return self._get_hu(ref)
        hu = self._find_hu(ref, org_id)
        if hu is None:
            raise HandlingUnitError('包装容器不存在：%s' % ref,
                                    field_name='hu_no', rule='HU_NOT_FOUND')
        return hu

    def _contents(self, hu_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE hu_id = ? ORDER BY id' % ITEM_TABLE, [hu_id])

    def _children(self, hu_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE hu_id = ? AND content_type = ? '
            'AND child_hu_id IS NOT NULL ORDER BY id' % ITEM_TABLE,
            [hu_id, CONTENT_HU])

    def _ancestors(self, hu_id: Any) -> List[int]:
        """自身 + 向上父链（防环时最多走 100 层）。"""
        chain: List[int] = []
        current = hu_id
        for _ in range(100):
            if current is None or int(current) in chain:
                break
            chain.append(int(current))
            rows = self.ds.query(
                'SELECT parent_hu_id FROM %s WHERE id = ?' % HU_TABLE, [current])
            current = rows[0].get('parent_hu_id') if rows else None
        return chain

    def _descendant_ids(self, hu_id: Any) -> List[int]:
        """含自身的子树 id（BFS）。"""
        result = [int(hu_id)]
        queue = [int(hu_id)]
        while queue:
            current = queue.pop(0)
            for row in self._children(current):
                child_id = int(row['child_hu_id'])
                if child_id in result:
                    continue
                result.append(child_id)
                queue.append(child_id)
        return result

    def _location_org(self, location_id: Any) -> Any:
        if _blank(location_id):
            return None
        try:
            rows = self.ds.query(
                'SELECT org_id FROM %s WHERE id = ?' % LOCATION_TABLE,
                [location_id])
        except Exception:
            return None
        return rows[0].get('org_id') if rows else None

    def _assert_org_location(self, org_id: Any, location_id: Any) -> None:
        if _blank(location_id):
            return
        org_of_location = self._location_org(location_id)
        if org_of_location is not None and int(org_of_location) != int(org_id):
            raise HandlingUnitError('库位不属于该库存组织',
                                    field_name='location_id',
                                    rule='HU_ORG_MISMATCH')

    # ------------------------------------------------------------------
    # 事件账
    # ------------------------------------------------------------------
    def _insert_txn(self, hu_id: Any, txn_type: str,
                    txn_at: Optional[str] = None,
                    **payload) -> int:
        """幂等写事件：键 (hu_id, txn_type, doc_type, doc_id, line_id, serial_id)。"""
        doc_type = payload.get('doc_type')
        doc_id = payload.get('doc_id')
        line_id = payload.get('line_id')
        serial_id = payload.get('serial_id')
        if _blank(txn_at):
            txn_at = _now()
        existing = self.ds.query(
            'SELECT id FROM %s WHERE hu_id = ? AND txn_type = ? '
            'AND COALESCE(doc_type, %s) = COALESCE(?, %s) '
            'AND COALESCE(doc_id, -1) = COALESCE(?, -1) '
            'AND COALESCE(line_id, -1) = COALESCE(?, -1) '
            'AND COALESCE(serial_id, -1) = COALESCE(?, -1)'
            % (TX_TABLE, "''", "''"),
            [hu_id, txn_type, doc_type, doc_id, line_id, serial_id])
        if existing:
            return int(existing[0]['id'])
        cursor = self.ds.execute(
            'INSERT INTO %s (hu_id, serial_id, child_hu_id, txn_type, '
            ' from_hu_id, to_hu_id, from_location_id, to_location_id, '
            ' doc_type, doc_id, line_id, txn_at, remark, created_at) '
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)" % TX_TABLE,
            [hu_id, serial_id, payload.get('child_hu_id'), txn_type,
             payload.get('from_hu_id'), payload.get('to_hu_id'),
             payload.get('from_location_id'), payload.get('to_location_id'),
             doc_type, doc_id, line_id, txn_at,
             payload.get('remark'), _now()])
        return int(cursor.lastrowid)

    # ------------------------------------------------------------------
    # 建箱
    # ------------------------------------------------------------------
    def create_hu(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload or {})
        hu_no = str(data.get('hu_no') or '').strip()
        if not hu_no:
            raise HandlingUnitError('容器号不能为空', field_name='hu_no',
                                    rule='HU_NO_REQUIRED')
        if len(hu_no) > 40:
            raise HandlingUnitError('容器号不能超过 40 个字符',
                                    field_name='hu_no', rule='HU_NO_TOO_LONG')
        if not _sscc_valid(hu_no):
            raise HandlingUnitError('SSCC 校验位不正确：%s' % hu_no,
                                    field_name='hu_no',
                                    rule='HU_SSCC_CHECKSUM_INVALID')
        org_id = data.get('org_id')
        if _blank(org_id):
            raise HandlingUnitError('库存组织不能为空', field_name='org_id',
                                    rule='HU_ORG_MISMATCH')
        self._require_row(ORG_TABLE, org_id, '库存组织', 'HU_ORG_MISMATCH')
        hu_type = str(data.get('hu_type') or 'carton').strip().lower()
        if hu_type not in HU_TYPES:
            raise HandlingUnitError('容器类型不合法：%s' % hu_type,
                                    field_name='hu_type', rule='HU_TYPE_INVALID')
        if self._find_hu(hu_no, org_id):
            raise HandlingUnitError('同一组织内容器号已存在：%s' % hu_no,
                                    field_name='hu_no', rule='HU_NO_DUPLICATE')
        location_id = data.get('location_id')
        self._assert_org_location(org_id, location_id)

        parent_id = data.get('parent_hu_id')
        root_id = None
        if not _blank(parent_id):
            parent = self._get_hu(parent_id)
            if parent.get('status') != STATUS_OPEN:
                raise HandlingUnitError('上层容器必须为打开状态',
                                        field_name='parent_hu_id',
                                        rule='HU_PARENT_NOT_OPEN')
            if int(parent['org_id']) != int(org_id):
                raise HandlingUnitError('父子容器必须属于同一组织',
                                        field_name='parent_hu_id',
                                        rule='HU_PARENT_ORG_MISMATCH')
            root_id = parent.get('root_hu_id') or parent['id']

        now = _now()
        with self.ds.transaction():
            cursor = self.ds.execute(
                'INSERT INTO %s (hu_no, hu_type, packaging_item_id, org_id, '
                ' location_id, parent_hu_id, root_hu_id, status, is_reusable, '
                ' cycle_no, gross_weight, tare_weight, net_weight, volume, '
                ' uom_id, source_doc_type, source_doc_id, remark, '
                ' created_at, updated_at) '
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                % HU_TABLE,
                [hu_no, hu_type, data.get('packaging_item_id'), org_id,
                 location_id, parent_id, root_id, STATUS_OPEN,
                 1 if data.get('is_reusable') else 0,
                 int(data.get('cycle_no') or 1),
                 data.get('gross_weight'), data.get('tare_weight'),
                 data.get('net_weight'), data.get('volume'),
                 data.get('uom_id'), data.get('source_doc_type'),
                 data.get('source_doc_id'), data.get('remark'), now, now])
            hu_id = int(cursor.lastrowid)
            self.ds.execute(
                'UPDATE %s SET root_hu_id = ? WHERE id = ?' % HU_TABLE,
                [hu_id if _blank(root_id) else root_id, hu_id])
            self._insert_txn(hu_id, TXN_CREATE, now,
                             from_hu_id=None, to_hu_id=hu_id,
                             doc_type=data.get('source_doc_type'),
                             doc_id=data.get('source_doc_id'),
                             remark=data.get('remark') or '建箱')
        logger.info('[hu] created id=%s no=%s org=%s', hu_id, hu_no, org_id)
        return {'id': hu_id, 'hu_no': hu_no, 'org_id': org_id,
                'status': STATUS_OPEN, 'root_hu_id': hu_id}

    # ------------------------------------------------------------------
    # 装箱 / 拆箱
    # ------------------------------------------------------------------
    def pack(self, hu_id: Any, lines: List[Dict[str, Any]],
             doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        hu = self._get_hu(hu_id)
        if hu.get('status') != STATUS_OPEN:
            raise HandlingUnitError('仅打开状态的容器可装箱，当前 %s'
                                    % hu.get('status'), field_name='status',
                                    rule='HU_STATUS_INVALID')
        doc = dict(doc or {})
        packed = 0
        location = hu.get('location_id')
        with self.ds.transaction():
            for raw in lines or []:
                line = dict(raw or {})
                content_type = str(line.get('content_type') or '').strip()
                if not content_type:
                    content_type = (CONTENT_HU if not _blank(line.get('child_hu_id'))
                                    else CONTENT_MATERIAL)
                self._assert_content_type(content_type, line)
                if content_type == CONTENT_HU:
                    self._pack_child(hu, line, doc)
                else:
                    location = self._pack_material(
                        hu, line, content_type, doc, location)
                packed += 1
            if not _blank(location) and int(location) != int(hu.get('location_id') or 0):
                self.ds.execute(
                    'UPDATE %s SET location_id = ?, updated_at = ? WHERE id = ?'
                    % HU_TABLE, [location, _now(), hu['id']])
        logger.info('[hu] pack id=%s lines=%s', hu['id'], packed)
        return {'hu_id': hu['id'], 'packed': packed,
                'location_id': location}

    def _assert_content_type(self, content_type: str,
                             line: Dict[str, Any]) -> None:
        if content_type not in CONTENT_TYPES:
            raise HandlingUnitError('内容类型不合法：%s' % content_type,
                                    field_name='content_type',
                                    rule='HU_SERIAL_CONTENT_TYPE_INVALID')
        if content_type == CONTENT_PACKAGING:
            if _blank(line.get('item_id')):
                raise HandlingUnitError('包装物行必须填写物料',
                                        field_name='item_id',
                                        rule='HU_SERIAL_CONTENT_TYPE_INVALID')
            if not _blank(line.get('serial_id')) or not _blank(line.get('batch_id')):
                raise HandlingUnitError(
                    '包装物行不能挂序列号或批次',
                    field_name='serial_id',
                    rule='HU_SERIAL_CONTENT_TYPE_INVALID')
        if content_type == CONTENT_HU:
            if _blank(line.get('child_hu_id')):
                raise HandlingUnitError('子容器行必须填写子容器',
                                        field_name='child_hu_id',
                                        rule='HU_SERIAL_CONTENT_TYPE_INVALID')
            if (not _blank(line.get('item_id'))
                    or not _blank(line.get('batch_id'))
                    or not _blank(line.get('serial_id'))):
                raise HandlingUnitError(
                    '子容器行不能挂物料 / 批次 / 序列号',
                    field_name='child_hu_id',
                    rule='HU_SERIAL_CONTENT_TYPE_INVALID')
        if content_type == CONTENT_MATERIAL and _blank(line.get('item_id')) \
                and _blank(line.get('serial_id')):
            raise HandlingUnitError('物料行必须填写物料或序列号',
                                    field_name='item_id',
                                    rule='HU_SERIAL_CONTENT_TYPE_INVALID')

    def _pack_child(self, hu: Dict[str, Any], line: Dict[str, Any],
                    doc: Dict[str, Any]) -> None:
        child_id = int(line['child_hu_id'])
        child = self._get_hu(child_id)
        if child.get('status') != STATUS_SEALED:
            raise HandlingUnitError(
                '子容器必须处于已密封状态，当前 %s' % child.get('status'),
                field_name='child_hu_id', rule='HU_CHILD_STATUS_INVALID')
        if int(child['org_id']) != int(hu['org_id']):
            raise HandlingUnitError('子容器与父容器必须属于同一组织',
                                    field_name='child_hu_id',
                                    rule='HU_PARENT_ORG_MISMATCH')
        if child_id in self._ancestors(hu['id']):
            raise HandlingUnitError('父子关系不能成环',
                                    field_name='child_hu_id',
                                    rule='HU_PARENT_CYCLE')
        existing = self.ds.query(
            'SELECT id FROM %s WHERE hu_id = ? AND child_hu_id = ?' % ITEM_TABLE,
            [hu['id'], child_id])
        if existing:
            return
        self.ds.execute(
            'INSERT INTO %s (hu_id, content_type, child_hu_id, qty, created_at) '
            "VALUES (?, ?, ?, 0, ?)" % ITEM_TABLE,
            [hu['id'], CONTENT_HU, child_id, _now()])
        root = hu.get('root_hu_id') or hu['id']
        self.ds.execute(
            'UPDATE %s SET parent_hu_id = ?, root_hu_id = ?, updated_at = ? '
            'WHERE id = ?' % HU_TABLE, [hu['id'], root, _now(), child_id])
        self._recalc_root(child_id, root)
        self._insert_txn(hu['id'], TXN_PACK, child_hu_id=child_id,
                         from_hu_id=child_id, to_hu_id=hu['id'],
                         **self._doc_keys(doc))

    def _recalc_root(self, hu_id: Any, root_id: Any) -> None:
        for descendant in self._descendant_ids(hu_id):
            self.ds.execute(
                'UPDATE %s SET root_hu_id = ? WHERE id = ?' % HU_TABLE,
                [root_id, descendant])

    def _pack_material(self, hu: Dict[str, Any], line: Dict[str, Any],
                       content_type: str, doc: Dict[str, Any],
                       location: Any) -> Any:
        serial_id = line.get('serial_id')
        serial_batch_id = None
        if _blank(serial_id) and not _blank(line.get('serial_no')):
            rows = self.ds.query(
                'SELECT id FROM %s WHERE item_id = ? AND org_id = ? '
                'AND serial_no = ?' % SERIAL_TABLE,
                [line.get('item_id'), hu['org_id'],
                 str(line.get('serial_no')).strip()])
            if not rows:
                raise HandlingUnitError('序列号不存在：%s' % line.get('serial_no'),
                                        field_name='serial_no',
                                        rule='HU_NOT_FOUND')
            serial_id = rows[0]['id']

        if not _blank(serial_id):
            serial = self._require_row(SERIAL_TABLE, serial_id, '序列号',
                                       'HU_NOT_FOUND')
            if int(serial['org_id']) != int(hu['org_id']):
                raise HandlingUnitError('序列号与容器不属于同一组织',
                                        field_name='serial_id',
                                        rule='HU_ORG_MISMATCH')
            if serial.get('usage_status') != 'in_stores':
                raise HandlingUnitError(
                    '序列号 %s 不在库，当前 %s' % (
                        serial.get('serial_no'), serial.get('usage_status')),
                    field_name='serial_id', rule='HU_SERIAL_NOT_IN_STORES')
            existing = self.ds.query(
                'SELECT hu_id FROM %s WHERE serial_id = ?' % ITEM_TABLE,
                [serial_id])
            if existing:
                if int(existing[0]['hu_id']) == int(hu['id']):
                    return location
                raise HandlingUnitError(
                    '序列号 %s 已属于其他容器' % serial.get('serial_no'),
                    field_name='serial_id', rule='HU_SERIAL_ALREADY_PACKED')
            serial_location = serial.get('current_location_id')
            if _blank(location):
                location = serial_location
            elif not _blank(serial_location) \
                    and int(serial_location) != int(location):
                raise HandlingUnitError(
                    '序列号 %s 的库位与容器不一致' % serial.get('serial_no'),
                    field_name='serial_id',
                    rule='HU_CONTENT_LOCATION_MISMATCH')
            item_id = serial.get('item_id')
            serial_batch_id = serial.get('batch_id')
            qty = 1.0
        else:
            serial_id = None
            item_id = line.get('item_id')
            qty = _as_float(line.get('qty'))
            if qty <= 0:
                qty = 1.0

        batch_id = line.get('batch_id') or serial_batch_id
        self.ds.execute(
            'INSERT INTO %s (hu_id, content_type, item_id, batch_id, serial_id, '
            ' qty, uom_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
            % ITEM_TABLE,
            [hu['id'], content_type, item_id, batch_id, serial_id, qty,
             line.get('uom_id'), _now()])
        self._insert_txn(hu['id'], TXN_PACK, serial_id=serial_id,
                         from_hu_id=None, to_hu_id=hu['id'],
                         **self._doc_keys(doc))
        return location

    def unpack(self, hu_id: Any, lines: Optional[List[Any]] = None,
               doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        hu = self._get_hu(hu_id)
        if hu.get('status') != STATUS_OPEN:
            raise HandlingUnitError('仅打开状态的容器可拆箱；已密封请先开封',
                                    field_name='status', rule='HU_STATUS_INVALID')
        rows = self._contents(hu['id'])
        targets = self._line_ids(lines, rows) if lines else rows
        removed = 0
        with self.ds.transaction():
            for row in targets:
                if row.get('content_type') == CONTENT_HU and row.get('child_hu_id'):
                    child_id = row['child_hu_id']
                    self.ds.execute(
                        'UPDATE %s SET parent_hu_id = NULL, root_hu_id = id, '
                        'updated_at = ? WHERE id = ?' % HU_TABLE,
                        [_now(), child_id])
                    self._recalc_root(child_id, child_id)
                self.ds.execute('DELETE FROM %s WHERE id = ?' % ITEM_TABLE,
                                [row['id']])
                self._insert_txn(hu['id'], TXN_UNPACK,
                                 serial_id=row.get('serial_id'),
                                 child_hu_id=row.get('child_hu_id'),
                                 from_hu_id=hu['id'], to_hu_id=None,
                                 **self._doc_keys(doc or {}))
                removed += 1
        return {'hu_id': hu['id'], 'unpacked': removed}

    def _line_ids(self, lines: List[Any], rows: List[Dict[str, Any]]) \
            -> List[Dict[str, Any]]:
        by_id = {int(row['id']): row for row in rows}
        selected: List[Dict[str, Any]] = []
        for ref in lines or []:
            line_id = ref.get('line_id') if isinstance(ref, dict) else ref
            row = by_id.get(int(line_id)) if not _blank(line_id) else None
            if row is None:
                raise HandlingUnitError('内容行不属于该容器：%s' % line_id,
                                        field_name='line_id',
                                        rule='HU_NOT_FOUND')
            selected.append(row)
        return selected

    # ------------------------------------------------------------------
    # 密封 / 开封 / 复用 / 作废
    # ------------------------------------------------------------------
    def seal(self, hu_id: Any) -> Dict[str, Any]:
        hu = self._get_hu(hu_id)
        if hu.get('status') != STATUS_OPEN:
            raise HandlingUnitError('仅打开状态的容器可密封', field_name='status',
                                    rule='HU_STATUS_INVALID')
        rows = self._contents(hu['id'])
        if not rows:
            raise HandlingUnitError('容器无内容，不能密封', field_name='status',
                                    rule='HU_CONTENT_EMPTY')
        location = hu.get('location_id')
        for row in rows:
            if row.get('content_type') == CONTENT_HU:
                child = self._get_hu(row['child_hu_id'])
                if child.get('status') != STATUS_SEALED:
                    raise HandlingUnitError(
                        '子容器 %s 未密封，不能密封父容器' % child.get('hu_no'),
                        field_name='status', rule='HU_CHILD_STATUS_INVALID')
            serial_id = row.get('serial_id')
            if not _blank(serial_id):
                serial = self._require_row(SERIAL_TABLE, serial_id, '序列号',
                                           'HU_NOT_FOUND')
                serial_location = serial.get('current_location_id')
                if _blank(location):
                    location = serial_location
                elif not _blank(serial_location) \
                        and int(serial_location) != int(location):
                    raise HandlingUnitError(
                        '容器内容库位不一致', field_name='location_id',
                        rule='HU_CONTENT_LOCATION_MISMATCH')
        if _blank(location):
            raise HandlingUnitError('容器无库位，不能密封', field_name='location_id',
                                    rule='HU_CONTENT_LOCATION_MISMATCH')
        now = _now()
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, location_id = ?, sealed_at = ?, '
                'updated_at = ? WHERE id = ?' % HU_TABLE,
                [STATUS_SEALED, location, now, now, hu['id']])
            self._insert_txn(hu['id'], TXN_SEAL, now,
                             from_location_id=hu.get('location_id'),
                             to_location_id=location, remark='密封')
        return {'hu_id': hu['id'], 'status': STATUS_SEALED,
                'location_id': location}

    def unseal(self, hu_id: Any) -> Dict[str, Any]:
        hu = self._get_hu(hu_id)
        if hu.get('status') != STATUS_SEALED:
            raise HandlingUnitError('仅已密封的容器可开封', field_name='status',
                                    rule='HU_STATUS_INVALID')
        now = _now()
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, sealed_at = NULL, updated_at = ? '
                'WHERE id = ?' % HU_TABLE, [STATUS_OPEN, now, hu['id']])
            self._insert_txn(hu['id'], TXN_UNSEAL, now, remark='开封')
        return {'hu_id': hu['id'], 'status': STATUS_OPEN}

    def reuse(self, hu_id: Any) -> Dict[str, Any]:
        hu = self._get_hu(hu_id)
        if not bool(hu.get('is_reusable')):
            raise HandlingUnitError('该容器不是复用型，不能复用',
                                    field_name='is_reusable',
                                    rule='HU_NOT_REUSABLE')
        # 空容器即可复用：密封态直接开新循环；打开态（拆空后）同样允许
        if hu.get('status') not in (STATUS_SEALED, STATUS_OPEN):
            raise HandlingUnitError('仅空容器可复用，当前 %s' % hu.get('status'),
                                    field_name='status', rule='HU_STATUS_INVALID')
        if self._contents(hu['id']):
            raise HandlingUnitError('容器仍有内容，不能复用', field_name='status',
                                    rule='HU_NOT_EMPTY')
        cycle_no = int(hu.get('cycle_no') or 1) + 1
        now = _now()
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, cycle_no = ?, sealed_at = NULL, '
                'shipped_at = NULL, updated_at = ? WHERE id = ?' % HU_TABLE,
                [STATUS_OPEN, cycle_no, now, hu['id']])
            self._insert_txn(hu['id'], TXN_REUSE, now,
                             remark='复用第 %s 次' % cycle_no)
        return {'hu_id': hu['id'], 'status': STATUS_OPEN, 'cycle_no': cycle_no}

    def void_hu(self, hu_id: Any, reason: str = '') -> Dict[str, Any]:
        hu = self._get_hu(hu_id)
        if hu.get('status') in (STATUS_VOID, STATUS_SHIPPED):
            raise HandlingUnitError('容器已发运或已作废，不能再次作废',
                                    field_name='status', rule='HU_STATUS_INVALID')
        rows = self._contents(hu['id'])
        if rows:
            raise HandlingUnitError('容器仍有内容，请先拆箱', field_name='status',
                                    rule='HU_NOT_EMPTY')
        now = _now()
        with self.ds.transaction():
            if not _blank(hu.get('parent_hu_id')):
                self.ds.execute(
                    'DELETE FROM %s WHERE child_hu_id = ?' % ITEM_TABLE,
                    [hu['id']])
            self.ds.execute(
                'UPDATE %s SET status = ?, voided_at = ?, parent_hu_id = NULL, '
                'updated_at = ? WHERE id = ?' % HU_TABLE,
                [STATUS_VOID, now, now, hu['id']])
            self._insert_txn(hu['id'], TXN_VOID, now,
                             remark=reason or '作废')
        return {'hu_id': hu['id'], 'status': STATUS_VOID}

    # ------------------------------------------------------------------
    # 移库 / 合并 / 拆分
    # ------------------------------------------------------------------
    def move(self, hu_id: Any, to_location_id: Any,
             doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        hu = self._get_hu(hu_id)
        if hu.get('status') in (STATUS_SHIPPED, STATUS_VOID):
            raise HandlingUnitError('已发运 / 已作废的容器不能移库',
                                    field_name='status', rule='HU_STATUS_INVALID')
        if _blank(to_location_id):
            raise HandlingUnitError('目标库位不能为空', field_name='location_id',
                                    rule='HU_NOT_FOUND')
        self._require_row(LOCATION_TABLE, to_location_id, '库位', 'HU_NOT_FOUND')
        self._assert_org_location(hu['org_id'], to_location_id)
        moved = self._descendant_ids(hu['id'])
        now = _now()
        with self.ds.transaction():
            for descendant in moved:
                rows = self.ds.query(
                    'SELECT location_id FROM %s WHERE id = ?' % HU_TABLE,
                    [descendant])
                from_location = rows[0].get('location_id') if rows else None
                self.ds.execute(
                    'UPDATE %s SET location_id = ?, updated_at = ? WHERE id = ?'
                    % HU_TABLE, [to_location_id, now, descendant])
                self._insert_txn(descendant, TXN_MOVE, now,
                                 from_location_id=from_location,
                                 to_location_id=to_location_id,
                                 **self._doc_keys(doc or {}))
        return {'hu_id': hu['id'], 'moved': len(moved),
                'location_id': to_location_id}

    def consolidate(self, source_hu_ids: List[Any], target_hu_id: Any,
                    doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        target = self._get_hu(target_hu_id)
        if target.get('status') != STATUS_OPEN:
            raise HandlingUnitError('目标容器必须为打开状态',
                                    field_name='status', rule='HU_STATUS_INVALID')
        sources = [self._get_hu(source_id) for source_id in source_hu_ids or []]
        if not sources:
            raise HandlingUnitError('来源容器不能为空', field_name='source_hu_ids',
                                    rule='HU_NOT_FOUND')
        moved = 0
        now = _now()
        with self.ds.transaction():
            for source in sources:
                if int(source['id']) == int(target['id']):
                    raise HandlingUnitError('来源容器不能是目标容器本身',
                                            field_name='source_hu_ids',
                                            rule='HU_PARENT_SELF')
                if source.get('status') in (STATUS_SHIPPED, STATUS_VOID):
                    raise HandlingUnitError(
                        '已发运 / 已作废的容器不能合并',
                        field_name='status', rule='HU_STATUS_INVALID')
                if int(source['org_id']) != int(target['org_id']):
                    raise HandlingUnitError('来源与目标容器必须属于同一组织',
                                            field_name='source_hu_ids',
                                            rule='HU_ORG_MISMATCH')
                if not _blank(target.get('location_id')) \
                        and not _blank(source.get('location_id')) \
                        and int(target['location_id']) != int(source['location_id']):
                    raise HandlingUnitError('来源与目标容器库位不一致',
                                            field_name='location_id',
                                            rule='HU_CONTENT_LOCATION_MISMATCH')
                if _blank(target.get('location_id')) \
                        and not _blank(source.get('location_id')):
                    self.ds.execute(
                        'UPDATE %s SET location_id = ? WHERE id = ?' % HU_TABLE,
                        [source['location_id'], target['id']])
                    target['location_id'] = source['location_id']
                rows = self._contents(source['id'])
                for row in rows:
                    self.ds.execute(
                        'UPDATE %s SET hu_id = ? WHERE id = ?' % ITEM_TABLE,
                        [target['id'], row['id']])
                    if row.get('content_type') == CONTENT_HU:
                        self.ds.execute(
                            'UPDATE %s SET parent_hu_id = ?, root_hu_id = ?, '
                            'updated_at = ? WHERE id = ?' % HU_TABLE,
                            [target['id'], target.get('root_hu_id') or target['id'],
                             now, row['child_hu_id']])
                        self._recalc_root(
                            row['child_hu_id'],
                            target.get('root_hu_id') or target['id'])
                    self._insert_txn(target['id'], TXN_CONSOLIDATE, now,
                                     serial_id=row.get('serial_id'),
                                     child_hu_id=row.get('child_hu_id'),
                                     from_hu_id=source['id'],
                                     to_hu_id=target['id'],
                                     **self._doc_keys(doc or {}))
                    moved += 1
                self.ds.execute(
                    'UPDATE %s SET status = ?, voided_at = ?, parent_hu_id = NULL, '
                    'updated_at = ? WHERE id = ?' % HU_TABLE,
                    [STATUS_VOID, now, now, source['id']])
                self._insert_txn(source['id'], TXN_VOID, now,
                                 from_hu_id=source['id'],
                                 remark='合并到容器 %s' % target.get('hu_no'))
        return {'target_hu_id': target['id'], 'sources': len(sources),
                'moved': moved}

    def split(self, hu_id: Any, lines: List[Any], target_hu_id: Any,
              doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        source = self._get_hu(hu_id)
        target = self._get_hu(target_hu_id)
        if source.get('status') in (STATUS_SHIPPED, STATUS_VOID):
            raise HandlingUnitError('已发运 / 已作废的容器不能拆分',
                                    field_name='status', rule='HU_STATUS_INVALID')
        if target.get('status') != STATUS_OPEN:
            raise HandlingUnitError('目标容器必须为打开状态',
                                    field_name='status', rule='HU_STATUS_INVALID')
        if int(source['org_id']) != int(target['org_id']):
            raise HandlingUnitError('来源与目标容器必须属于同一组织',
                                    field_name='source_hu_ids',
                                    rule='HU_ORG_MISMATCH')
        if not _blank(source.get('location_id')) \
                and not _blank(target.get('location_id')) \
                and int(source['location_id']) != int(target['location_id']):
            raise HandlingUnitError('来源与目标容器库位不一致',
                                    field_name='location_id',
                                    rule='HU_CONTENT_LOCATION_MISMATCH')
        rows = self._line_ids(lines, self._contents(source['id']))
        now = _now()
        with self.ds.transaction():
            if _blank(target.get('location_id')) \
                    and not _blank(source.get('location_id')):
                self.ds.execute(
                    'UPDATE %s SET location_id = ? WHERE id = ?' % HU_TABLE,
                    [source['location_id'], target['id']])
            for row in rows:
                self.ds.execute(
                    'UPDATE %s SET hu_id = ? WHERE id = ?' % ITEM_TABLE,
                    [target['id'], row['id']])
                if row.get('content_type') == CONTENT_HU:
                    self.ds.execute(
                        'UPDATE %s SET parent_hu_id = ?, root_hu_id = ?, '
                        'updated_at = ? WHERE id = ?' % HU_TABLE,
                        [target['id'], target.get('root_hu_id') or target['id'],
                         now, row['child_hu_id']])
                    self._recalc_root(
                        row['child_hu_id'],
                        target.get('root_hu_id') or target['id'])
                self._insert_txn(target['id'], TXN_SPLIT, now,
                                 serial_id=row.get('serial_id'),
                                 child_hu_id=row.get('child_hu_id'),
                                 from_hu_id=source['id'], to_hu_id=target['id'],
                                 **self._doc_keys(doc or {}))
        return {'source_hu_id': source['id'], 'target_hu_id': target['id'],
                'moved': len(rows)}

    # ------------------------------------------------------------------
    # 发运 / 反冲
    # ------------------------------------------------------------------
    def ship_hu(self, hu_id: Any, shipment_id: Any = None,
                doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        hu = self._get_hu(hu_id)
        if hu.get('status') != STATUS_SEALED:
            raise HandlingUnitError('仅已密封的容器可整箱发运，当前 %s'
                                    % hu.get('status'), field_name='status',
                                    rule='HU_SHIP_STATUS_INVALID')
        if _blank(hu.get('location_id')):
            raise HandlingUnitError('容器无库位，不能发运',
                                    field_name='location_id',
                                    rule='HU_SHIP_STATUS_INVALID')
        doc = dict(doc or {})
        doc_type = doc.get('doc_type') or (DOC_SHIPMENT if not _blank(shipment_id) else None)
        doc_id = doc.get('doc_id') if not _blank(doc.get('doc_id')) else shipment_id
        tree = self._descendant_ids(hu['id'])
        for hu_item in tree:
            node = self._get_hu(hu_item)
            if node.get('status') != STATUS_SEALED:
                raise HandlingUnitError(
                    '容器 %s 未密封，不能整箱发运' % node.get('hu_no'),
                    field_name='status', rule='HU_SHIP_STATUS_INVALID')
        serial_ids = self._leaf_serial_ids(hu['id'])
        now = _now()
        with self.ds.transaction():
            for serial_id in serial_ids:
                serial = self._require_row(SERIAL_TABLE, serial_id, '序列号',
                                           'HU_NOT_FOUND')
                if serial.get('usage_status') != 'in_stores':
                    raise HandlingUnitError(
                        '序列号 %s 不在库，不能发运' % serial.get('serial_no'),
                        field_name='serial_id', rule='HU_SERIAL_NOT_IN_STORES')
                self._ship_serial(serial, hu, now, doc_type, doc_id)
            for hu_item in tree:
                self.ds.execute(
                    'UPDATE %s SET status = ?, location_id = NULL, '
                    'shipped_at = ?, updated_at = ? WHERE id = ?' % HU_TABLE,
                    [STATUS_SHIPPED, now, now, hu_item])
                self._insert_txn(hu_item, TXN_SHIP, now,
                                 from_location_id=hu.get('location_id'),
                                 from_hu_id=hu_item,
                                 doc_type=doc_type, doc_id=doc_id,
                                 line_id=doc.get('line_id'), remark='整箱发运')
        return {'hu_id': hu['id'], 'status': STATUS_SHIPPED,
                'shipped_serials': len(serial_ids),
                'shipped_hus': len(tree)}

    def _ship_serial(self, serial: Dict[str, Any], hu: Dict[str, Any],
                     now: str, doc_type: Any, doc_id: Any) -> None:
        from meta.services.serial_number_service import (
            SerialNumberError, SerialNumberService)
        try:
            SerialNumberService(self.ds).change_status(
                serial['id'], 'shipped', '整箱发运 %s' % hu.get('hu_no'),
                {'doc_type': doc_type, 'doc_id': doc_id})
        except SerialNumberError as error:
            raise HandlingUnitError(str(error), field_name='serial_id',
                                    rule=error.rule or 'HU_SERIAL_NOT_IN_STORES')

    def reverse_hu_transaction(self, hu_txn_id: Any) -> Dict[str, Any]:
        rows = self.ds.query('SELECT * FROM %s WHERE id = ?' % TX_TABLE, [hu_txn_id])
        if not rows:
            raise HandlingUnitError('容器事件不存在：%s' % hu_txn_id,
                                    field_name='id', rule='HU_NOT_FOUND')
        txn = rows[0]
        hu = self._get_hu(txn['hu_id'])
        now = _now()
        reversed_kind = txn.get('txn_type')
        if reversed_kind == TXN_MOVE:
            # move 自带事务，放在外层避免事务嵌套
            if not _blank(txn.get('from_location_id')):
                self.move(hu['id'], txn.get('from_location_id'),
                          {'doc_type': txn.get('doc_type'),
                           'doc_id': txn.get('doc_id'),
                           'line_id': txn.get('line_id')})
        with self.ds.transaction():
            if reversed_kind == TXN_SHIP and hu.get('status') == STATUS_SHIPPED:
                self._restore_shipped_tree(hu, now, txn)
            elif reversed_kind == TXN_PACK:
                self._undo_pack(txn, hu, now)
            self._insert_txn(hu['id'], TXN_REVERSE, now,
                             serial_id=txn.get('serial_id'),
                             child_hu_id=txn.get('child_hu_id'),
                             from_hu_id=txn.get('to_hu_id'),
                             to_hu_id=txn.get('from_hu_id'),
                             doc_type=txn.get('doc_type'),
                             doc_id=txn.get('doc_id'),
                             line_id=txn.get('line_id'),
                             remark='反冲事件 #%s (%s)' % (hu_txn_id, reversed_kind))
        return {'hu_txn_id': hu_txn_id, 'reversed': reversed_kind}

    def _restore_shipped_tree(self, hu: Dict[str, Any], now: str,
                              txn: Dict[str, Any]) -> None:
        for hu_item in self._descendant_ids(hu['id']):
            node = self._get_hu(hu_item)
            if node.get('status') != STATUS_SHIPPED:
                continue
            self.ds.execute(
                'UPDATE %s SET status = ?, shipped_at = NULL, updated_at = ? '
                'WHERE id = ?' % HU_TABLE, [STATUS_SEALED, now, hu_item])
        location = hu.get('location_id') or txn.get('from_location_id')
        for serial_id in self._leaf_serial_ids(hu['id']):
            serial = self._require_row(SERIAL_TABLE, serial_id, '序列号',
                                       'HU_NOT_FOUND')
            if serial.get('usage_status') != 'shipped':
                continue
            self.ds.execute(
                'INSERT INTO %s (serial_id, txn_type, txn_date, org_from_id, '
                ' org_to_id, location_from_id, location_to_id, usage_from, '
                ' usage_to, doc_type, doc_id, line_id, remark, created_at) '
                "VALUES (?, 'adjust', ?, ?, ?, NULL, ?, 'shipped', 'in_stores', "
                " ?, ?, ?, ?, ?)" % SERIAL_TX_TABLE,
                [serial_id, now, serial.get('org_id'), serial.get('org_id'),
                 location, txn.get('doc_type'), txn.get('doc_id'),
                 txn.get('line_id'), '容器反冲还原在库', now])
            self.ds.execute(
                'UPDATE %s SET usage_status = ?, current_location_id = ?, '
                'shipped_at = NULL, updated_at = ? WHERE id = ?' % SERIAL_TABLE,
                ['in_stores', location, now, serial_id])

    def _undo_pack(self, txn: Dict[str, Any], hu: Dict[str, Any],
                   now: str) -> None:
        if txn.get('serial_id'):
            self.ds.execute(
                'DELETE FROM %s WHERE hu_id = ? AND serial_id = ?' % ITEM_TABLE,
                [hu['id'], txn['serial_id']])
        if txn.get('child_hu_id'):
            self.ds.execute(
                'DELETE FROM %s WHERE hu_id = ? AND child_hu_id = ?' % ITEM_TABLE,
                [hu['id'], txn['child_hu_id']])
            self.ds.execute(
                'UPDATE %s SET parent_hu_id = NULL, root_hu_id = id, '
                'updated_at = ? WHERE id = ?' % HU_TABLE,
                [now, txn['child_hu_id']])
            self._recalc_root(txn['child_hu_id'], txn['child_hu_id'])

    def reverse_document(self, doc_type: str, doc_id: Any) -> Dict[str, Any]:
        """按单据反冲：倒序回退该单据产生的容器事件（红冲接线用）。"""
        rows = self.ds.query(
            'SELECT id FROM %s WHERE doc_type = ? AND doc_id = ? '
            'AND txn_type IN (?, ?, ?, ?) ORDER BY id DESC' % TX_TABLE,
            [doc_type, doc_id, TXN_PACK, TXN_SHIP, TXN_MOVE, TXN_CREATE])
        reversed_count = 0
        for row in rows:
            self.reverse_hu_transaction(row['id'])
            reversed_count += 1
        return {'doc_type': doc_type, 'doc_id': doc_id,
                'reversed': reversed_count}

    # ------------------------------------------------------------------
    # 查询口径（§11.13）
    # ------------------------------------------------------------------
    def hu_contents(self, hu_no: Any, org_id: Any = None,
                    mode: str = 'direct') -> Dict[str, Any]:
        hu = self._resolve_hu(hu_no, org_id)
        if mode not in ('direct', 'exploded'):
            raise HandlingUnitError('查询模式不合法：%s' % mode,
                                    field_name='mode', rule='HU_STATUS_INVALID')
        if mode == 'direct':
            items = [self._decorate_item(row, hu) for row in self._contents(hu['id'])]
        else:
            items = self._exploded(hu)
        return {'hu': hu, 'mode': mode, 'items': items,
                'transactions': self._txn_history(hu['id'])}

    def _exploded(self, hu: Dict[str, Any], path: Optional[List[Dict[str, Any]]] = None) \
            -> List[Dict[str, Any]]:
        current_path = list(path or []) + [{'hu_id': hu['id'],
                                            'hu_no': hu.get('hu_no')}]
        leaves: List[Dict[str, Any]] = []
        for row in self._contents(hu['id']):
            if row.get('content_type') == CONTENT_HU:
                child = self._get_hu(row['child_hu_id'])
                leaves.extend(self._exploded(child, current_path))
            elif row.get('content_type') == CONTENT_MATERIAL:
                item = self._decorate_item(row, hu)
                item['path'] = current_path
                leaves.append(item)
        return leaves

    def _decorate_item(self, row: Dict[str, Any], hu: Dict[str, Any]) \
            -> Dict[str, Any]:
        item = dict(row)
        item['hu_no'] = hu.get('hu_no')
        item['hu_status'] = hu.get('status')
        item['location_id'] = hu.get('location_id')
        serial_id = row.get('serial_id')
        if not _blank(serial_id):
            serials = self.ds.query(
                'SELECT serial_no, usage_status, quality_status, item_id, '
                'batch_id, current_location_id FROM %s WHERE id = ?' % SERIAL_TABLE,
                [serial_id])
            if serials:
                item['serial_no'] = serials[0].get('serial_no')
                item['serial_status'] = serials[0].get('usage_status')
                item['serial_quality_status'] = serials[0].get('quality_status')
                if _blank(item.get('item_id')):
                    item['item_id'] = serials[0].get('item_id')
                if _blank(item.get('batch_id')):
                    item['batch_id'] = serials[0].get('batch_id')
        child_id = row.get('child_hu_id')
        if not _blank(child_id):
            child = self._get_hu(child_id)
            item['child_hu_no'] = child.get('hu_no')
            item['child_status'] = child.get('status')
        return item

    def _txn_history(self, hu_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE hu_id = ? ORDER BY txn_at, id' % TX_TABLE,
            [hu_id])

    def hu_stock(self, hu_id: Any, mode: str = 'exploded') -> Dict[str, Any]:
        hu = self._get_hu(hu_id)
        rows = self._exploded(hu) if mode == 'exploded' \
            else [self._decorate_item(row, hu) for row in self._contents(hu['id'])
                  if row.get('content_type') == CONTENT_MATERIAL]
        aggregated: Dict[Any, Dict[str, Any]] = {}
        for row in rows:
            key = (row.get('item_id'), row.get('batch_id'), row.get('serial_id'))
            bucket = aggregated.setdefault(key, {
                'item_id': row.get('item_id'),
                'batch_id': row.get('batch_id'),
                'serial_id': row.get('serial_id'),
                'qty': 0.0,
                'lines': 0,
            })
            bucket['qty'] += _as_float(row.get('qty'))
            bucket['lines'] += 1
        return {'hu_id': hu['id'], 'hu_no': hu.get('hu_no'),
                'location_id': hu.get('location_id'),
                'rows': list(aggregated.values()),
                'total_qty': sum(bucket['qty'] for bucket in aggregated.values())}

    def hu_where_used(self, serial_no: Any, org_id: Any = None) -> Dict[str, Any]:
        serial_no = str(serial_no or '').strip()
        if not serial_no:
            raise HandlingUnitError('序列号不能为空', field_name='serial_no',
                                    rule='HU_NOT_FOUND')
        sql = 'SELECT * FROM %s WHERE serial_no = ?' % SERIAL_TABLE
        params: List[Any] = [serial_no]
        if not _blank(org_id):
            sql += ' AND org_id = ?'
            params.append(org_id)
        serials = self.ds.query(sql, params)
        if not serials:
            raise HandlingUnitError('序列号不存在：%s' % serial_no,
                                    field_name='serial_no', rule='HU_NOT_FOUND')
        matches = []
        for serial in serials:
            item_rows = self.ds.query(
                'SELECT * FROM %s WHERE serial_id = ?' % ITEM_TABLE, [serial['id']])
            current = None
            path: List[Dict[str, Any]] = []
            if item_rows:
                hu = self._get_hu(item_rows[0]['hu_id'])
                current = {'hu_id': hu['id'], 'hu_no': hu.get('hu_no'),
                           'status': hu.get('status'),
                           'root_hu_id': hu.get('root_hu_id')}
                chain = self._ancestors(hu['id'])
                for ancestor_id in reversed(chain):
                    ancestor = self._get_hu(ancestor_id)
                    path.append({'hu_id': ancestor['id'],
                                 'hu_no': ancestor.get('hu_no'),
                                 'status': ancestor.get('status')})
                current['root_hu_no'] = path[0]['hu_no'] if path else hu.get('hu_no')
            matches.append({
                'org_id': serial.get('org_id'),
                'serial': serial,
                'current_hu': current,
                'path': path,
                'history': self.ds.query(
                    'SELECT * FROM %s WHERE serial_id = ? ORDER BY txn_at, id'
                    % TX_TABLE, [serial['id']]),
            })
        return {'serial_no': serial_no, 'matches': matches}

    # ------------------------------------------------------------------
    # 单据接线（§11.5）：门控调用，表缺失时 no-op
    # ------------------------------------------------------------------
    def pack_receipt(self, receipt_id: Any) -> Dict[str, Any]:
        """收货 / 完工过账后按行 hu_no 建箱并装箱；完工只装成品行。"""
        if not hu_schema_ready(self.ds):
            return {'skipped': True, 'packed': 0}
        header = self._require_row(RECEIPT_TABLE, receipt_id, '收货单',
                                   'HU_NOT_FOUND')
        org_id = header.get('inventory_org_id') or header.get('org_id')
        location_id = header.get('deliver_to_location_id')
        lines = self.ds.query(
            'SELECT * FROM %s WHERE receipt_id = ? AND status <> ?'
            % RECEIPT_LINE_TABLE, [receipt_id, 'cancelled'])
        packed = 0
        for line in lines:
            hu_no = str(line.get('hu_no') or '').strip()
            if not hu_no:
                continue
            contents = self._receipt_contents(line, org_id)
            # §11.5：仅当装箱数量 = 行净收数量；不满足则本行不装箱
            if not contents:
                continue
            hu = self._find_hu(hu_no, org_id)
            if hu is not None and hu.get('status') == STATUS_SEALED:
                # 同组织调拨：容器整体 move 到收货库位，不在收货侧重装
                target_location = line.get('putaway_location_id') or location_id
                if hu.get('location_id') != target_location:
                    self.move(hu['id'], target_location,
                              {'doc_type': DOC_RECEIPT, 'doc_id': receipt_id,
                               'line_id': line.get('id')})
                packed += 1
                continue
            if hu is not None and hu.get('status') != STATUS_OPEN:
                continue
            if hu is None:
                # 跨组织调拨：源组织同号容器已发运 → 复制整棵子树到目标组织
                source = self._find_hu(hu_no)
                if source is not None and source.get('status') in (
                        STATUS_SEALED, STATUS_SHIPPED):
                    self._clone_tree(
                        source, org_id,
                        line.get('putaway_location_id') or location_id,
                        {'doc_type': DOC_RECEIPT, 'doc_id': receipt_id,
                         'line_id': line.get('id')})
                    packed += 1
                    continue
                hu = self.create_hu({
                    'hu_no': hu_no,
                    'hu_type': str(line.get('hu_type') or 'carton').strip(),
                    'org_id': org_id,
                    'location_id': line.get('putaway_location_id') or location_id,
                    'source_doc_type': DOC_RECEIPT,
                    'source_doc_id': receipt_id,
                })
            self.pack(hu['id'], contents,
                      {'doc_type': DOC_RECEIPT, 'doc_id': receipt_id,
                       'line_id': line.get('id')})
            packed += 1
        return {'receipt_id': receipt_id, 'packed': packed}

    def _receipt_contents(self, line: Dict[str, Any], org_id: Any) \
            -> List[Dict[str, Any]]:
        serials = self.ds.query(
            'SELECT serial_id FROM %s WHERE doc_type = ? AND line_id = ? '
            'ORDER BY id' % LINK_TABLE, [DOC_RECEIPT, line.get('id')])
        qty = _as_float(line.get('qty_received')) - _as_float(line.get('qty_rejected'))
        expected = int(round(qty))
        if serials:
            if len(serials) != expected:
                return []
            return [{'content_type': CONTENT_MATERIAL,
                     'serial_id': row['serial_id']} for row in serials]
        if expected <= 0:
            return []
        batch_id = self._resolve_batch(org_id, line.get('item_id'), line.get('lot_no'))
        return [{'content_type': CONTENT_MATERIAL,
                 'item_id': line.get('item_id'), 'batch_id': batch_id,
                 'qty': float(expected), 'uom_id': line.get('uom_id')}]

    def _resolve_batch(self, org_id: Any, item_id: Any, lot_no: Any) -> Any:
        if _blank(lot_no):
            return None
        rows = self.ds.query(
            'SELECT id FROM %s WHERE item_id = ? AND org_id = ? AND batch_no = ?'
            % BATCH_TABLE, [item_id, org_id, str(lot_no).strip()])
        return rows[0]['id'] if rows else None

    def ship_shipment(self, shipment_id: Any) -> Dict[str, Any]:
        """发运确认后按行 hu_no 整箱发运（级联成员号）。"""
        if not hu_schema_ready(self.ds):
            return {'skipped': True, 'shipped': 0}
        header = self._require_row(SHIPMENT_TABLE, shipment_id, '交货单',
                                   'HU_NOT_FOUND')
        org_id = self._location_org(header.get('ship_from_location_id'))
        lines = self.ds.query(
            'SELECT * FROM %s WHERE delivery_id = ? AND status <> ?'
            % SHIPMENT_LINE_TABLE, [shipment_id, 'cancelled'])
        shipped = 0
        for line in lines:
            hu_no = str(line.get('hu_no') or '').strip()
            if not hu_no:
                continue
            hu = self._find_hu(hu_no, org_id)
            if hu is None:
                raise HandlingUnitError('包装容器不存在：%s' % hu_no,
                                        field_name='hu_no', rule='HU_NOT_FOUND')
            self.ship_hu(hu['id'], shipment_id,
                         {'doc_type': DOC_SHIPMENT, 'doc_id': shipment_id,
                          'line_id': line.get('id')})
            shipped += 1
        return {'shipment_id': shipment_id, 'shipped': shipped}

    def ship_transfer(self, transfer_order_id: Any) -> Dict[str, Any]:
        """调拨发运：同组织整体移库；跨组织整箱发运（源容器置 shipped）。

        §11.5：同组织 HU 整体 move 到目标库位；跨组织只把源子树置 shipped，
        目标组织侧的结构复制在收货过账时由 `_clone_tree` 完成。
        """
        if not hu_schema_ready(self.ds):
            return {'skipped': True, 'moved': 0, 'shipped': 0}
        header = self._require_row(TRANSFER_TABLE, transfer_order_id, '调拨单',
                                   'HU_NOT_FOUND')
        from_org = header.get('from_org_id')
        to_org = header.get('to_org_id')
        to_location = header.get('to_location_id')
        lines = self.ds.query(
            'SELECT * FROM %s WHERE transfer_order_id = ? AND status <> ?'
            % TRANSFER_LINE_TABLE, [transfer_order_id, 'cancelled'])
        moved = shipped = 0
        for line in lines:
            hu_no = str(line.get('hu_no') or '').strip()
            if not hu_no:
                continue
            hu = self._find_hu(hu_no, from_org)
            if hu is None:
                raise HandlingUnitError('包装容器不存在：%s' % hu_no,
                                        field_name='hu_no', rule='HU_NOT_FOUND')
            doc = {'doc_type': DOC_TRANSFER, 'doc_id': transfer_order_id,
                   'line_id': line.get('id')}
            same_org = _blank(to_org) or int(to_org) == int(from_org)
            if same_org:
                if _blank(to_location):
                    continue
                if hu.get('location_id') != to_location:
                    self.move(hu['id'], to_location, doc)
                moved += 1
            else:
                self.ship_hu(hu['id'], None, doc)
                shipped += 1
        return {'transfer_order_id': transfer_order_id,
                'moved': moved, 'shipped': shipped}

    def _clone_tree(self, source: Dict[str, Any], org_id: Any,
                    location_id: Any, doc: Optional[Dict[str, Any]] = None,
                    parent_id: Any = None) -> int:
        """跨组织调拨收货：把源容器子树复制到目标组织。

        容器号按 (org_id, hu_no) 唯一，跨组织允许同号；物料行保留 item / qty /
        batch_no（按目标组织重建批次关联），**不复制 serial_id**——序列号主档
        按组织隔离，由目标组织收货录号重新建号。已存在同号容器时直接复用（幂等）。
        """
        hu_no = str(source.get('hu_no') or '').strip()
        existing = self._find_hu(hu_no, org_id)
        if existing is not None:
            return int(existing['id'])
        now = _now()
        doc = doc or {}
        cursor = self.ds.execute(
            'INSERT INTO %s (hu_no, hu_type, packaging_item_id, org_id, '
            ' location_id, parent_hu_id, root_hu_id, status, is_reusable, '
            ' cycle_no, gross_weight, tare_weight, net_weight, volume, uom_id, '
            ' source_doc_type, source_doc_id, sealed_at, created_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            % HU_TABLE,
            [hu_no, source.get('hu_type') or 'carton',
             source.get('packaging_item_id'), org_id, location_id,
             parent_id, None, STATUS_SEALED,
             int(source.get('is_reusable') or 0),
             int(source.get('cycle_no') or 1),
             source.get('gross_weight'), source.get('tare_weight'),
             source.get('net_weight'), source.get('volume'),
             source.get('uom_id'), doc.get('doc_type'), doc.get('doc_id'),
             now, now, now])
        target_id = int(cursor.lastrowid)
        root_id = target_id
        if parent_id is not None:
            parent = self._get_hu(parent_id)
            root_id = parent.get('root_hu_id') or target_id
        self.ds.execute('UPDATE %s SET root_hu_id = ? WHERE id = ?' % HU_TABLE,
                        [root_id, target_id])
        self._insert_txn(target_id, TXN_CREATE, now, **doc)

        for row in self._contents(source['id']):
            if row.get('content_type') == CONTENT_HU:
                child = self._get_hu(row['child_hu_id'])
                child_id = self._clone_tree(child, org_id, location_id, doc,
                                            target_id)
                self.ds.execute(
                    'INSERT INTO %s (hu_id, content_type, child_hu_id, qty, '
                    ' created_at) VALUES (?, ?, ?, 0, ?)' % ITEM_TABLE,
                    [target_id, CONTENT_HU, child_id, now])
                continue
            batch_id = None
            if row.get('batch_id'):
                src_batch = self.ds.query(
                    'SELECT batch_no FROM %s WHERE id = ?' % BATCH_TABLE,
                    [row['batch_id']])
                batch_no = src_batch[0].get('batch_no') if src_batch else None
                batch_id = self._resolve_batch(org_id, row.get('item_id'), batch_no)
            self.ds.execute(
                'INSERT INTO %s (hu_id, content_type, item_id, batch_id, qty, '
                ' uom_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)' % ITEM_TABLE,
                [target_id, row.get('content_type') or CONTENT_MATERIAL,
                 row.get('item_id'), batch_id, _as_float(row.get('qty')),
                 row.get('uom_id'), now])
        return target_id

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _leaf_serial_ids(self, hu_id: Any) -> List[int]:
        return [int(row['serial_id']) for row in self._exploded(self._get_hu(hu_id))
                if row.get('serial_id')]

    @staticmethod
    def _doc_keys(doc: Dict[str, Any]) -> Dict[str, Any]:
        doc = dict(doc or {})
        return {'doc_type': doc.get('doc_type'), 'doc_id': doc.get('doc_id'),
                'line_id': doc.get('line_id')}
