# -*- coding: utf-8 -*-
"""冲销档位策略表回归：声明形状 + 关键单据口径。"""

import pytest

from meta.core.reversal_profiles import (
    REVERSAL_PROFILES,
    VALID_COMMITMENTS,
    VALID_MODES,
    get_profile,
)


def test_receipt_keeps_commitment_and_uses_red_reverse():
    profile = get_profile('receipt')
    assert profile['mode'] == 'red_reverse'
    assert profile['commitment'] == 'no_revert'  # 已发生投料不回退
    assert profile['close_guard'] is True
    assert profile['reason_required'] is True
    assert profile['edges'] == ({
        'rule_id': 'receipt_line_to_inventory_txn',
        'source_bo': 'receipt_line',
    },)


def test_shipment_uses_counter_and_releases_remaining():
    for name in ('shipment', 'transfer_shipment'):
        profile = get_profile(name)
        assert profile['mode'] == 'counter'
        assert profile['commitment'] == 'release_remaining'


def test_unknown_document_raises():
    with pytest.raises(KeyError):
        get_profile('no_such_doc')


def test_all_profiles_are_well_formed():
    assert REVERSAL_PROFILES
    for name, profile in REVERSAL_PROFILES.items():
        assert profile['mode'] in VALID_MODES, name
        assert profile['commitment'] in VALID_COMMITMENTS, name
        assert isinstance(profile['edges'], tuple), name
        assert isinstance(profile['reason_required'], bool), name
