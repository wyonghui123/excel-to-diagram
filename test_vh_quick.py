#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查 metaConfig.value 的完整结构"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={'width': 1920, 'height': 1080}).new_page()
    
    # 登录
    page.goto('http://localhost:3004/login', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(2000)
    page.fill('input[type="text"]', 'admin')
    page.fill('input[type="password"]', 'admin123')
    page.click('button[type="submit"]')
    page.wait_for_timeout(5000)
    
    # 导航
    page.goto('http://localhost:3004/user-permission?tab=user-groups', wait_until='networkidle', timeout=60000)
    page.wait_for_timeout(8000)
    
    # 检查 metaConfig.value 是否有 fields
    result = page.evaluate("""() => {
        const allEls = document.querySelectorAll('*');
        for (const el of allEls) {
            const comp = el.__vue_parent_component;
            if (!comp) continue;
            
            const ss = comp.setupState;
            if (!ss) continue;
            
            // 检查 metaConfig
            if (ss.metaConfig) {
                const mc = ss.metaConfig;
                const val = mc.__v_isRef ? mc.value : mc;
                if (val) {
                    return {
                        hasFields: 'fields' in val,
                        fieldsCount: val.fields ? val.fields.length : 0,
                        topLevelKeys: Object.keys(val),
                        listHasFields: val.list ? ('fields' in val.list) : false,
                        listFieldsCount: val.list?.fields?.length || 0,
                    };
                }
            }
        }
        return 'metaConfig not found';
    }""")
    print(f"\n=== metaConfig 结构 ===")
    print(f"  {result}")
    
    browser.close()
