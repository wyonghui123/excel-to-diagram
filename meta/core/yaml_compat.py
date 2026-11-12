# -*- coding: utf-8 -*-
"""YAML 解析统一入口：优先 libyaml (CSafeLoader)，缺失时回退纯 Python SafeLoader。

[schema 全量解析实测] 213 个文件 / 2.4MB
  SafeLoader   29.4s
  CSafeLoader   3.8s   (约 7.7x)

create_app() 启动阶段会多次全量解析 schema（register_from_directory 等），
是测试 session 固定开销与服务冷启动的主要来源，故统一走本模块。
"""
import yaml

Loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)


def safe_load(stream):
    """等价 yaml.safe_load，但使用 C 实现（可用时）。"""
    return yaml.load(stream, Loader=Loader)
