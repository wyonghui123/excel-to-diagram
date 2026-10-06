# -*- coding: utf-8 -*-
"""ISO 4217 币种种子数据（currency）— foundation 参数据面延伸

依据: docs/superpowers/specs/2026-10-06-currency-object-design.md（TBD-3）
标准: ISO 4217 alpha-3；维护机构 = SIX Interbank Clearing（currency-iso.org）
精度: ISO "Minor unit" 列 ⇒ 映射为 decimal_places（SAP TCURX 例外机制 / Oracle Precision 合并）
范围: 30 条常用流通币种（方案 A）
      覆盖 中港台 + 东南亚 + 主要贸易伙伴 + 全部精度异常值（JPY/KRW=0 · KWD/BHD=3）
      **刻意排除**: ISO List one 含基金与超国家代码（XOF / XAF / XPF / XDR / XCG 等）
                    —— 属"基金/记账本位"而非流通币种，灌入会污染业务币种表
      **XCG 处置**: ISO Amendment 176（2025-03-31 起 XCG 取代 ANG，1:1，numeric 532 不变）
                    按现行 List one 只保留在位币，不预置已退市的 ANG
幂等: by code upsert（先 SELECT → UPDATE / INSERT）
      重跑只刷新 name / name_en / decimal_places / symbol，不重置 status
      （停用≠删除，重跑不复活 —— 沿 region 种子同一约定）
"""
import logging

logger = logging.getLogger(__name__)

# (code, 中文名, 英文名, decimal_places, symbol)
_CURRENCIES = [
    # ---- 精度 = 0（ISO Minor unit 例外；SAP 需 TCURX 特例行）----
    ('JPY', '日元', 'Japanese Yen', 0, '¥'),
    ('KRW', '韩元', 'South Korean Won', 0, '₩'),
    ('CLP', '智利比索', 'Chilean Peso', 0, '$'),
    ('ISK', '冰岛克朗', 'Icelandic Krona', 0, 'kr'),
    # ---- 精度 = 3（中东非流通辅币）----
    ('KWD', '科威特第纳尔', 'Kuwaiti Dinar', 3, 'د.ك'),
    ('BHD', '巴林第纳尔', 'Bahraini Dinar', 3, '.د.ب'),
    ('OMR', '阿曼里亚尔', 'Omani Rial', 3, 'ر.ع.'),
    # ---- 精度 = 2（ISO 主流）----
    ('CNY', '人民币', 'Chinese Yuan', 2, '¥'),
    ('USD', '美元', 'US Dollar', 2, '$'),
    ('EUR', '欧元', 'Euro', 2, '€'),
    ('GBP', '英镑', 'Pound Sterling', 2, '£'),
    ('HKD', '港元', 'Hong Kong Dollar', 2, '$'),
    ('TWD', '新台币', 'New Taiwan Dollar', 2, 'NT$'),
    ('MOP', '澳门元', 'Macanese Pataca', 2, 'MOP$'),
    ('SGD', '新加坡元', 'Singapore Dollar', 2, '$'),
    ('MYR', '马来西亚林吉特', 'Malaysian Ringgit', 2, 'RM'),
    ('THB', '泰铢', 'Thai Baht', 2, '฿'),
    ('VND', '越南盾', 'Vietnamese Dong', 2, '₫'),
    ('IDR', '印尼盾', 'Indonesian Rupiah', 2, 'Rp'),
    ('PHP', '菲律宾比索', 'Philippine Peso', 2, '₱'),
    ('AUD', '澳元', 'Australian Dollar', 2, '$'),
    ('NZD', '新西兰元', 'New Zealand Dollar', 2, '$'),
    ('CAD', '加元', 'Canadian Dollar', 2, '$'),
    ('CHF', '瑞士法郎', 'Swiss Franc', 2, 'CHF'),
    ('SEK', '瑞典克朗', 'Swedish Krona', 2, 'kr'),
    ('NOK', '挪威克朗', 'Norwegian Krone', 2, 'kr'),
    ('DKK', '丹麦克朗', 'Danish Krone', 2, 'kr'),
    ('PLN', '波兰兹罗提', 'Polish Zloty', 2, 'zł'),
    ('CZK', '捷克克朗', 'Czech Koruna', 2, 'Kč'),
    ('INR', '印度卢比', 'Indian Rupee', 2, '₹'),
    ('RUB', '俄罗斯卢布', 'Russian Ruble', 2, '₽'),
    ('BRL', '巴西雷亚尔', 'Brazilian Real', 2, 'R$'),
    ('MXN', '墨西哥比索', 'Mexican Peso', 2, '$'),
    ('ZAR', '南非兰特', 'South African Rand', 2, 'R'),
    ('TRY', '土耳其里拉', 'Turkish Lira', 2, '₺'),
    ('AED', '阿联酋迪拉姆', 'UAE Dirham', 2, 'د.إ'),
    ('SAR', '沙特里亚尔', 'Saudi Riyal', 2, '﷼'),
    ('ILS', '以色列新谢克尔', 'Israeli New Shekel', 2, '₪'),
    ('EGP', '埃及镑', 'Egyptian Pound', 2, 'E£'),
]

# 描述：仅标注需要留意的币种（口径差异 / 退市 / 例外精度）
_DESCRIPTIONS = {
    'JPY': 'ISO 4217 例外精度 0（日元无小数位）；SAP S/4 需 TCURX 特例行登记',
    'KRW': 'ISO 4217 例外精度 0',
    'CLP': 'ISO 4217 例外精度 0',
    'ISK': 'ISO 4217 例外精度 0',
    'KWD': 'ISO 4217 例外精度 3（中东非流通辅币）',
    'BHD': 'ISO 4217 例外精度 3',
    'OMR': 'ISO 4217 例外精度 3',
    'CNY': 'ISO 4217 numeric 156；注意 CNY≠CNH（离岸 CNH 不在 ISO 4217 清单内）',
    'SAR': 'ISO 4217 沙里亚尔；符号 U+FDFC 为孤立 Unicode 字符（部分字体显示为豆腐块）',
}

_REFRESHED = ('name', 'name_en', 'decimal_places', 'symbol', 'description')


def _iter_rows():
    """产出 (code, name, name_en, decimal_places, symbol, description)"""
    for code, name, name_en, places, symbol in _CURRENCIES:
        yield code, name, name_en, places, symbol, _DESCRIPTIONS.get(code)


def init_currency_seed_data(data_source):
    """幂等写入 ISO 4217 常用币种种子。返回 (inserted, updated) 计数。

    不重置 status：已停用的币种重跑保持 inactive（停用≠删除）。
    """
    inserted = 0
    updated = 0
    for code, name, name_en, places, symbol, desc in _iter_rows():
        existing = data_source.query(
            "SELECT id FROM currencies WHERE code = ?", (code,))
        if existing:
            data_source.execute(
                "UPDATE currencies SET name = ?, name_en = ?, "
                "decimal_places = ?, symbol = ?, description = ? "
                "WHERE code = ?",
                [name, name_en, places, symbol, desc, code])
            updated += 1
        else:
            data_source.execute(
                "INSERT INTO currencies "
                "(code, name, name_en, decimal_places, symbol, status, "
                " description, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, datetime('now'))",
                [code, name, name_en, places, symbol, desc])
            inserted += 1

    data_source.commit()
    logger.info("Currency seeded: %d inserted, %d updated", inserted, updated)
    return inserted, updated
