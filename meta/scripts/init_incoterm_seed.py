# -*- coding: utf-8 -*-
"""国际贸易术语（Incoterms）种子数据 —— ICC Incoterms 2020 全部 11 条

依据: meta/schemas/incoterm.yaml
范围: edition=2020 的 11 条术语
  - 任一运输方式 7 条: EXW / FCA / CPT / CIP / DAP / DPU / DDP
  - 海运及内河 4 条: FAS / FOB / CFR / CIF

判据口径（逐条对照 ICC Incoterms 2020 规则原文）:
  risk_transfer_point  风险转移时点
  export_clearance_by  出口清关责任方（仅 EXW 为买方）
  import_clearance_by  进口清关责任方（仅 DDP 为卖方）
  main_carriage_by     主运费责任方
  unloading_by         目的地卸货责任方（仅 DPU 为卖方）
  insurance_cover      卖方强制投保义务（仅 CIF=ICC C / CIP=ICC A）

幂等: by (code, edition) upsert；重跑只刷新业务属性，不重置 status
      （停用≠删除，沿 currency / region / 销售配置种子同一约定）。
"""

import logging

logger = logging.getLogger(__name__)

#: (code, name, name_en, edition, transport_mode, risk_transfer_point,
#:  export_clearance_by, import_clearance_by, main_carriage_by, unloading_by,
#:  insurance_cover, description)
_INCOTERMS = [
    ('EXW', '工厂交货', 'Ex Works', '2020', 'any_mode', 'seller_premises',
     'buyer', 'buyer', 'buyer', 'buyer', 'none',
     '卖方在其场所将货物交由买方处置即完成交货，买方承担装车及之后全部费用与风险'),
    ('FCA', '货交承运人', 'Free Carrier', '2020', 'any_mode', 'carrier',
     'seller', 'buyer', 'buyer', 'buyer', 'none',
     '卖方在指定地点将货物交给买方指定的承运人；卖方办出口清关'),
    ('CPT', '运费付至', 'Carriage Paid To', '2020', 'any_mode', 'carrier',
     'seller', 'buyer', 'seller', 'buyer', 'none',
     '卖方支付运至指定目的地的运费，但风险自货物交给第一承运人时转移'),
    ('CIP', '运费和保险费付至', 'Carriage and Insurance Paid To', '2020',
     'any_mode', 'carrier', 'seller', 'buyer', 'seller', 'buyer', 'icc_a',
     'CPT 基础上卖方须投保一切险（ICC A），最低保额 110% 合同价'),
    ('DAP', '目的地交货', 'Delivered at Place', '2020', 'any_mode',
     'destination_ready', 'seller', 'buyer', 'seller', 'buyer', 'none',
     '货物运抵指定目的地、可供买方卸货时交货；买方办进口清关并卸货'),
    ('DPU', '目的地卸货交货', 'Delivered at Place Unloaded', '2020', 'any_mode',
     'destination_unloaded', 'seller', 'buyer', 'seller', 'seller', 'none',
     '唯一要求卖方在目的地卸货的术语；2020 版取代 2010 版 DAT'),
    ('DDP', '完税后交货', 'Delivered Duty Paid', '2020', 'any_mode',
     'destination_ready', 'seller', 'seller', 'seller', 'buyer', 'none',
     '卖方承担包括进口清关与税费在内的全部责任，交货时仍由买方卸货'),
    ('FAS', '船边交货', 'Free Alongside Ship', '2020', 'sea_and_inland',
     'alongside_ship', 'seller', 'buyer', 'buyer', 'buyer', 'none',
     '卖方将货物置于指定装运港船边即交货；装船及主运费由买方负责'),
    ('FOB', '船上交货', 'Free On Board', '2020', 'sea_and_inland', 'on_board',
     'seller', 'buyer', 'buyer', 'buyer', 'none',
     '货物装上买方指定船舶时交货；装船后风险与主运费由买方承担'),
    ('CFR', '成本加运费', 'Cost and Freight', '2020', 'sea_and_inland',
     'on_board', 'seller', 'buyer', 'seller', 'buyer', 'none',
     '卖方支付运至指定目的港的运费，风险自货物装船时转移'),
    ('CIF', '成本、保险费加运费', 'Cost, Insurance and Freight', '2020',
     'sea_and_inland', 'on_board', 'seller', 'buyer', 'seller', 'buyer', 'icc_c',
     'CFR 基础上卖方须投保最低险（ICC C），最低保额 110% 合同价'),
]


def _upsert_incoterms(ds):
    inserted = updated = 0
    for (code, name, name_en, edition, transport_mode, risk_transfer_point,
         export_by, import_by, main_carriage_by, unloading_by,
         insurance_cover, desc) in _INCOTERMS:
        existing = ds.query(
            "SELECT id FROM incoterms WHERE code = ? AND edition = ?",
            [code, edition])
        if existing:
            ds.execute(
                "UPDATE incoterms SET name = ?, name_en = ?, "
                "transport_mode = ?, risk_transfer_point = ?, "
                "export_clearance_by = ?, import_clearance_by = ?, "
                "main_carriage_by = ?, unloading_by = ?, "
                "insurance_cover = ?, description = ? "
                "WHERE code = ? AND edition = ?",
                [name, name_en, transport_mode, risk_transfer_point,
                 export_by, import_by, main_carriage_by, unloading_by,
                 insurance_cover, desc, code, edition])
            updated += 1
        else:
            ds.execute(
                "INSERT INTO incoterms "
                "(code, name, name_en, edition, transport_mode, "
                " risk_transfer_point, export_clearance_by, import_clearance_by, "
                " main_carriage_by, unloading_by, insurance_cover, status, "
                " description, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, datetime('now'))",
                [code, name, name_en, edition, transport_mode,
                 risk_transfer_point, export_by, import_by, main_carriage_by,
                 unloading_by, insurance_cover, desc])
            inserted += 1
    return inserted, updated


def init_incoterm_seed_data(data_source):
    """幂等写入 Incoterms 2020 的 11 条术语。返回 (inserted, updated)。"""
    result = _upsert_incoterms(data_source)
    data_source.commit()
    logger.info('Incoterms seeded: %s inserted, %s updated', result[0], result[1])
    return result


if __name__ == '__main__':
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path

    _db_path = get_meta_db_path()
    _ds = get_data_source('sqlite', database=str(_db_path))
    _ins, _upd = init_incoterm_seed_data(_ds)
    print(f'[incoterm seed] db={_db_path}')
    print(f'[incoterm seed] incoterms: {_ins} inserted, {_upd} updated')
