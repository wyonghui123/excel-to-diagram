#!/usr/bin/env python
# -*- coding: utf-8 -*-
print("mermaid 11.13.0 测试")
print('subgraph SD_1["财务云 / 销售管理"]   <- / 不允许')
print('subgraph SD_1["财务云(销售)"]   <- ( ) 在 label 允许但要 escape')
print('node BO_1["销售订单(主)"]   <- 同上')
print('node BO_1["BOSS\"系统"]   <- " 不允许直接')
print('node BO_1["财务云\\n系统"]   <- \\n 在 mermaid 用 <br/>')
print('subgraph G_SD_5["销售管理（财务云 / 销售）"]  <- 财务云 disabledPath 含 /')
print()
print('600+ 节点 BO 图: 长度可能超 50KB, mermaid 有大小限制')
