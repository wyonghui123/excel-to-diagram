# -*- coding: utf-8 -*-
"""税务种子数据 —— 税务分类 3 条 + 中国增值税税码 6 条（含首段税率）

依据: docs/superpowers/specs/2026-10-25-tax-wave0-implementation-spec.md §8

范围:
  税务分类（按用途轴拆开，决定对象上的默认税码）:
    VAT_STD_CUST / customer、VAT_STD_SUPP / supplier、VAT_ITEM_STD / item
  税码（中国增值税现行档位）:
    13% / 9% / 6% / 3% / 1% / 0%（免税）
  每条税码带一段开放区间税率（effective_from = 2020-01-01，effective_to = NULL）。

幂等: by 业务键 upsert（分类 = code + applicable_to；税码 = code；税率 = tax_code_id + effective_from）。
      重跑只刷新业务属性，不重置 status（停用≠删除，沿 currency / region / incoterm 同一约定）。
      region 中查不到 CN（level='country'）时记 ERROR 并跳过税码，不写死 id。
"""

import logging

logger = logging.getLogger(__name__)

#: (code, name, applicable_to, description)
_CLASSIFICATIONS = [
    ('VAT_STD_CUST', '客户标准税率分类', 'customer',
     '客户档案默认税务分类：决定销售方向默认取用的税码'),
    ('VAT_STD_SUPP', '供应商标准税率分类', 'supplier',
     '供应商档案默认税务分类：决定采购方向默认取用的税码'),
    ('VAT_ITEM_STD', '物料标准税率分类', 'item',
     '物料默认税务分类：按物料适用税档决定行上默认税码'),
]

#: (code, name, tax_type, direction, treatment, rate_percent,
#:  exemption_reason, description)
_TAX_CODES = [
    ('CN_VAT_13', '增值税 13%', 'vat', 'both', 'standard', 13, '',
     '中国增值税标准档，适用于销售货物、提供加工修理修配劳务及有形动产租赁'),
    ('CN_VAT_9', '增值税 9%', 'vat', 'both', 'standard', 9, '',
     '中国增值税低档，适用于交通运输、邮政、基础电信、建筑、不动产租赁与销售等'),
    ('CN_VAT_6', '增值税 6%', 'vat', 'both', 'standard', 6, '',
     '中国增值税服务档，适用于现代服务、金融服务、生活服务及无形资产销售'),
    ('CN_VAT_3', '增值税 3%', 'vat', 'both', 'standard', 3, '',
     '小规模纳税人征收率 3%'),
    ('CN_VAT_1', '增值税 1%', 'vat', 'both', 'standard', 1, '',
     '小规模纳税人阶段性减按 1% 征收率'),
    ('CN_VAT_0', '增值税 0%（免税）', 'vat', 'both', 'exempt', 0,
     '法定免税项目',
     '法定免税项目：出口货物、农业生产者自产农产品等（依税收法规列举）'),
]

_RATE_EFFECTIVE_FROM = '2020-01-01'


def _find_cn_region_id(ds):
    rows = ds.query(
        "SELECT id FROM regions WHERE code = ? AND level = ?",
        ['CN', 'country'])
    if not rows:
        return None
    row = rows[0]
    return row['id'] if isinstance(row, dict) else row[0]


def _upsert_classifications(ds):
    inserted = updated = 0
    for code, name, applicable_to, desc in _CLASSIFICATIONS:
        existing = ds.query(
            "SELECT id FROM tax_classifications WHERE code = ? AND applicable_to = ?",
            [code, applicable_to])
        if existing:
            ds.execute(
                "UPDATE tax_classifications SET name = ?, description = ? "
                "WHERE code = ? AND applicable_to = ?",
                [name, desc, code, applicable_to])
            updated += 1
        else:
            ds.execute(
                "INSERT INTO tax_classifications "
                "(code, name, applicable_to, description, status, created_at) "
                "VALUES (?, ?, ?, ?, 'active', datetime('now'))",
                [code, name, applicable_to, desc])
            inserted += 1
    return inserted, updated


def _upsert_tax_codes(ds, country_id):
    inserted = updated = rates_inserted = rates_updated = 0
    for (code, name, tax_type, direction, treatment, rate_percent,
         exemption_reason, desc) in _TAX_CODES:
        existing = ds.query("SELECT id FROM tax_codes WHERE code = ?", [code])
        if existing:
            tax_code_id = existing[0]['id'] if isinstance(existing[0], dict) else existing[0]
            ds.execute(
                "UPDATE tax_codes SET name = ?, country_id = ?, tax_type = ?, "
                "direction = ?, tax_treatment = ?, rate_source = 'internal', "
                "rounding = 'round', exemption_reason = ?, description = ? "
                "WHERE code = ?",
                [name, country_id, tax_type, direction, treatment,
                 exemption_reason, desc, code])
            updated += 1
        else:
            ds.execute(
                "INSERT INTO tax_codes "
                "(code, name, country_id, tax_type, direction, tax_treatment, "
                " rate_source, rounding, exemption_reason, description, "
                " status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'internal', 'round', ?, ?, 'active', datetime('now'))",
                [code, name, country_id, tax_type, direction, treatment,
                 exemption_reason, desc])
            tax_code_id = ds.query("SELECT id FROM tax_codes WHERE code = ?", [code])[0]['id']
            inserted += 1

        # 首段开放区间税率
        rate_existing = ds.query(
            "SELECT id FROM tax_rates WHERE tax_code_id = ? AND effective_from = ?",
            [tax_code_id, _RATE_EFFECTIVE_FROM])
        if rate_existing:
            ds.execute(
                "UPDATE tax_rates SET rate_percent = ?, effective_to = NULL, "
                "is_provisional = 0, legal_basis = ? WHERE id = ?",
                [rate_percent, exemption_reason, rate_existing[0]['id']])
            rates_updated += 1
        else:
            ds.execute(
                "INSERT INTO tax_rates "
                "(tax_code_id, effective_from, effective_to, rate_percent, "
                " is_provisional, legal_basis, description, created_at) "
                "VALUES (?, ?, NULL, ?, 0, ?, '', datetime('now'))",
                [tax_code_id, _RATE_EFFECTIVE_FROM, rate_percent, exemption_reason])
            rates_inserted += 1
    return inserted, updated, rates_inserted, rates_updated


def init_tax_seed_data(data_source):
    """幂等写入税务分类、税码与首段税率。

    返回 dict：classifications / tax_codes / tax_rates 各自的 inserted / updated。
    """
    cls_ins, cls_upd = _upsert_classifications(data_source)
    country_id = _find_cn_region_id(data_source)
    if country_id is None:
        logger.error('[tax seed] region 中未找到 CN（level=country），跳过税码种子')
        data_source.commit()
        return {
            'classifications': (cls_ins, cls_upd),
            'tax_codes': None,
            'tax_rates': None,
        }
    code_ins, code_upd, rate_ins, rate_upd = _upsert_tax_codes(data_source, country_id)
    data_source.commit()
    logger.info(
        '[tax seed] classifications %s/%s, tax_codes %s/%s, tax_rates %s/%s',
        cls_ins, cls_upd, code_ins, code_upd, rate_ins, rate_upd)
    return {
        'classifications': (cls_ins, cls_upd),
        'tax_codes': (code_ins, code_upd),
        'tax_rates': (rate_ins, rate_upd),
    }


if __name__ == '__main__':
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path

    logging.basicConfig(level=logging.INFO)
    _db_path = get_meta_db_path()
    _ds = get_data_source('sqlite', database=str(_db_path))
    _result = init_tax_seed_data(_ds)
    print(f'[tax seed] db={_db_path}')
    for _key, _val in _result.items():
        print(f'[tax seed] {_key}: {_val}')
