#!/usr/bin/env node
/**
 * check_chunk_cycles.mjs — 构建产物 chunk 循环依赖门禁
 *
 * 背景 (2026-09-03 staging 18081 "Class extends value undefined"):
 *   manualChunks 手工分桶 + 依赖图漂移 (可选依赖安装状态变化) 反复产生 chunk 双向循环,
 *   ES module 循环初始化时顶层 class extends 的基类绑定未就绪 → 页面白屏/报错。
 *   历史上靠"发现一个环补一条规则"打地鼠, 永远滞后。根治 = 构建期自动门禁:
 *   带环产物直接构建失败, 无法到达任何环境。
 *
 * 检测逻辑:
 *   1. 扫描 dist/assets/*.js 头部, 提取静态 import 边: from "./x.js"
 *      (压缩产物中跨 chunk 静态 import 只出现在文件头部; class extends 崩溃正来自静态边)
 *   2. DFS 找环 → 有环 exit 1 (硬失败, 阻断 build)
 *   3. 动态 import("./x.js") 边仅警告 (动态环通常不炸顶层, 不阻断)
 *
 * 用法: node scripts/check_chunk_cycles.mjs [dist_dir]
 *   dist_dir 默认 dist, CI/脚本可传参。exit 0 = 无环; exit 1 = 有环; exit 2 = 产物缺失。
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, basename } from 'node:path';

const distDir = process.argv[2] || 'dist';
const assetsDir = join(distDir, 'assets');

let files;
try {
  files = readdirSync(assetsDir).filter((f) => f.endsWith('.js') && statSync(join(assetsDir, f)).isFile());
} catch {
  console.error(`[chunk-cycles] FAIL: 无法读取 ${assetsDir} (dist 未构建?)`);
  process.exit(2);
}

if (files.length === 0) {
  console.error('[chunk-cycles] FAIL: assets 目录无 js 产物');
  process.exit(2);
}

// ---- 提取静态/动态 import 边 (只看文件头部 16KB, 压缩产物跨 chunk import 集中于此) ----
const staticEdges = new Map();  // chunk -> Set<chunk>
const dynamicEdges = new Map();
for (const f of files) {
  const head = readFileSync(join(assetsDir, f), 'utf8').slice(0, 16384);
  const sTargets = new Set();
  const dTargets = new Set();
  for (const m of head.matchAll(/from\s*["'](\.\/[^"']+\.js)["']/g)) sTargets.add(basename(m[1]));
  for (const m of head.matchAll(/import\s*\(\s*["'](\.\/[^"']+\.js)["']\s*\)/g)) dTargets.add(basename(m[1]));
  if (sTargets.size) staticEdges.set(f, sTargets);
  if (dTargets.size) dynamicEdges.set(f, dTargets);
}

// ---- DFS 找环 (静态边, 严格) ----
function findCycle(edges) {
  const visited = new Set();
  const dfs = (node, stack) => {
    visited.add(node);
    stack.push(node);
    for (const next of edges.get(node) || []) {
      if (stack.includes(next)) return stack.slice(stack.indexOf(next)).concat(next);
      if (!visited.has(next)) {
        const c = dfs(next, stack);
        if (c) return c;
      }
    }
    stack.pop();
    return null;
  };
  for (const n of edges.keys()) {
    const c = dfs(n, []);
    if (c) return c;
  }
  return null;
}

const cycle = findCycle(staticEdges);
if (cycle) {
  console.error('[chunk-cycles] FAIL: 检测到静态 import 循环依赖!');
  console.error(`  环路: ${cycle.join(' -> ')}`);
  console.error('  后果: 上线后顶层 class extends 将抛 "Class extends value undefined"');
  console.error('  处置: 调整 vite.config.js manualChunks, 把环上 chunk 的冲突依赖并桶 (参考 2026-09-03 vendor-pdf 并入 vendor-mermaid 的先例)');
  process.exit(1);
}
console.log(`[chunk-cycles] OK: ${files.length} 个 chunk, 静态 import 图无循环`);

// ---- 动态 import 边: 仅警告 ----
const dynCycle = findCycle(dynamicEdges);
if (dynCycle) {
  console.warn(`[chunk-cycles] WARN: 存在动态 import 环 (一般不炸顶层, 不阻断): ${dynCycle.join(' -> ')}`);
}
process.exit(0);
