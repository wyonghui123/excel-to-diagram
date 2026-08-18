#!/usr/bin/env python3
"""Calibrate mermaid render cost vs node count (synthetic benchmark, local vite dev).

用法: python test_helpers/calibrate_scale.py [--buckets 30,50,80,120,160,240,320,400,600,800,1200]
"""
import argparse
import json
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright not installed"); sys.exit(1)

BASE = 'http://localhost:3004/benchmark.html'
BUCKETS = [30, 50, 80, 120, 160, 240, 320, 400, 600, 800, 1200, 1600, 2400, 3200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--buckets', default=','.join(map(str, BUCKETS)))
    ap.add_argument('--repeats', type=int, default=1, help='基准重复次数')
    ap.add_argument('--engines', default='dagre,elk')
    ap.add_argument('--fixed-nodes', type=int, default=None,
                    help='固定节点数, 扫边数模式 (配合 --edge-buckets)')
    ap.add_argument('--edge-buckets', default=None,
                    help='边数档位 csv, 如 200,400,600,1000,1500,2000')
    args = ap.parse_args()
    buckets = [int(x) for x in args.buckets.split(',')]
    engines = args.engines.split(',')
    edge_buckets = [int(x) for x in args.edge_buckets.split(',')] if args.edge_buckets else None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(120000)
        t0 = time.time()
        page.goto(BASE, wait_until='domcontentloaded')
        # 等 bench 模块加载 (mermaid 预打包可能较慢)
        for _ in range(60):
            try:
                ok = page.evaluate('() => typeof window.runBench === "function"')
                if ok:
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            print('[FATAL] bench module not ready'); browser.close(); sys.exit(2)
        if args.fixed_nodes and edge_buckets:
            print(f'[ready] {time.time()-t0:.1f}s  EDGE-SWEEP mode: nodes={args.fixed_nodes} '
                  f'edges={edge_buckets} engines={engines}')
        else:
            print(f'[ready] {time.time()-t0:.1f}s  engines={engines}  buckets={buckets}')

        rows = []
        if args.fixed_nodes and edge_buckets:
            runs = [(args.fixed_nodes, e) for e in edge_buckets]
        else:
            runs = [(n, None) for n in buckets]
        for n, edge_target in runs:
            for eng in engines:
                r = page.evaluate(
                    '(args) => window.runBench(args.n, args.eng, args.repeats, args.edges)',
                    {'n': n, 'eng': eng, 'repeats': args.repeats, 'edges': edge_target}
                )
                rows.append(r)
                dims = r.get('dims') or {}
                if r.get('error'):
                    print(f'  nodes={n:<5} edges={edge_target} {eng:6s} ERROR: {r["error"]}')
                else:
                    print(f'  nodes={n:<5} edges={r.get("edges"):<5} {eng:6s} '
                          f'render={r.get("avgMs"):>6}ms (best {r.get("renderMs")}ms) '
                          f'domNodes={r.get("domNodes")} dims={dims.get("w")}x{dims.get("h")}')
                page.wait_for_timeout(800)

        # 汇总表 (markdown)
        print('\n===== 汇总 =====')
        print('| 节点 | 关系 | 引擎 | 平均渲染ms | 最佳ms | DOM节点 | 尺寸WxH |')
        print('|---|---|---|---|---|---|---|')
        for r in rows:
            dims = r.get('dims') or {}
            if r.get('error'):
                print(f'| {r["nodes"]} | {r.get("edges")} | {r.get("engine")} | ERROR: {r["error"]} | - | - | - |')
            else:
                print(f'| {r["nodes"]} | {r.get("edges")} | {r.get("engine")} | {r.get("avgMs")} | '
                      f'{r.get("renderMs")} | {r.get("domNodes")} | {dims.get("w")}x{dims.get("h")} |')

        out_json = 'test_output/calibrate_edges.json' if (args.fixed_nodes and edge_buckets) else 'test_output/calibrate_scale.json'
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f'\nreport: {out_json}')
        browser.close()


if __name__ == '__main__':
    main()
