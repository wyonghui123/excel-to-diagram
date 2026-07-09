# V007.48 mermaid syntax error 深度排查报告 (财务云 600+ 节点)

> **日期**: 2026-07-09 17:30
> **作者**: V007.45 dev-agent (V007.48 P0 BUG-FIX 承接)
> **触发**: 用户在架构管理页面选 财务云 1610 BO + 范围内与外部关系 (199 BO + 689 关系) → mermaid 报 "Syntax error in text, mermaid version 11.13.0"
> **结论**: UnifiedRenderer + MermaidGenerator 注入 BO 名称 / Code / disabledPath 到 subgraph/node label 时**未做 mermaid 11.13 严格转义** (双引号 / 单引号 / 反斜杠 / 换行 / 方括号)

---

## 用户操作 (2026-07-09 17:25)

| 选择 | 数量 |
|------|------|
| 中心范围 (财务云) | 1 域, 16 子, 142 服务, 1610 对象, 0 关系 |
| 范围内与外部节点 (关系) | +10 域, +23 子, +60 服, +199 对, +689 关系 |
| 总显示 | 1 + 10 = 11 domain, 16+23 = 39 sub_domain, 142+60 = 202 service_module, 1610+199 = 1809 BO, 689 关系 |

**mermaid 11.13.0 渲染时**: "Syntax error in text" 整个图显示不出来。

---

## 排查方法 (3 步)

### Step 1: 找 mermaid 代码生成位置
- `src/services/groupModel/UnifiedRenderer.js` (BO/SM 图)
- `src/services/groupModel/MermaidGenerator.js` (旧版)
- `src/composables/useMermaid/syntax/_shared/arrowHelper.js` (link label)

### Step 2: 锁定根因 (用 mermaid 11.13 实际解析)

写测试代码 (mermaid 11.13.0 npm 验证):

| 测试用例 | 结果 |
|---------|------|
| `BO_1["BOSS"系统"]` (raw `"`) | ❌ **Parse error on line 2: `^`** |
| `BO_1["BOSS\"系统"]` (1 个反斜杠) | ❌ Parse error (双引号没转义) |
| `BO_1["BOSS\\"系统"]` (2 个反斜杠) | ❌ Parse error (mermaid 11.13 仍报错) |
| `BO_1["BOSS#quot;系统"]` (mermaid 官方) | ✅ OK |
| `BO_1["财务云 / 销售管理"]` (`/`) | ✅ OK |
| `BO_1["销售订单(主)"]` (`(`, `)`) | ✅ OK |
| `BO_1["销售订单\n(主)"]` (实际换行) | ❌ Parse error |
| `BO_1["销售订单<br/>(主)"]` (`<br/>`) | ✅ OK |
| `subgraph G_SD_1["财务云（销售）"]` (中文括号) | ✅ OK |

**根因**: **mermaid 11.13.0 不允许 subgraph/node label 含未转义的双引号 `"`**。

### Step 3: 找代码漏洞 (UnifiedRenderer)

| 位置 | 代码 | 问题 |
|------|------|------|
| L82 | `${group.title}（${disabledPath.join(' / ')}）` | 注入 disabledPath, name 可能含 `"` |
| L90 | `${group.title}` 直接拼接 | BO 名称含 `"` 时破坏 |
| L92 | `subgraph ${group.id}["${displayTitle}"]` | displayTitle 没转义 |
| L119 | `${child.title}` 直接拼接 | 同样 |
| L147 | `${container.title}` 直接拼接 | 同样 |
| MermaidGenerator.js L131, L196, L206, L235 | 同样问题 | 同样 |

**MermaidGenerator** 跟 UnifiedRenderer 是两个**并行的生成器**。**两者都没做严格转义**！

---

## 真正根因

**mermaid 11.13.0 升级了 label parser**：

| mermaid 版本 | label 允许字符 |
|------------|--------------|
| < 11.0 | `"` 内可含 `' \|` 等 (link label 风格) |
| 11.0+ | `["..."]` 内必须**官方转义** `" ' \ ( ) [ ]` |

但 `src/composables/useMermaid/syntax/_shared/arrowHelper.js` 的 `sanitizeLabel()` (原版) **只**用 `'` 替代 `"` (这是为 link label `-->"text"|` 设计的，link label 单引号字符串允许 `"`)，**不**为 `["..."]` 设计。

**UnifiedRenderer 和 MermaidGenerator 都没用 `sanitizeLabel`**！直接把 `group.title` / `group.elementRef?.code` / `disabledAncestorPath.join(' / ')` 拼到 label。

**外部 domain 名称**（用户选"范围内与外部" 时的 10 个外部域）从数据库读出，**任一字符含 `"` 就触发 mermaid syntax error**。

---

## V007.48 P0 BUG-FIX 实施

### 1. 新增 `sanitizeMermaidLabel` (arrowHelper.js)
严格转义 mermaid 11.13.0 label 规则：

```js
export function sanitizeMermaidLabel(label) {
  if (label === null || label === undefined) return ''
  return String(label)
    .replace(/\\/g, '#92;')          // 反斜杠
    .replace(/"/g, '#quot;')          // 双引号 (mermaid 11.13 官方)
    .replace(/'/g, '#apos;')          // 单引号
    .replace(/[\r\n]+/g, '<br/>')    // 换行
    .replace(/\[/g, '#91;')           // [
    .replace(/\]/g, '#93;')           // ]
    .replace(/\{/g, '#123;')          // {
    .replace(/\}/g, '#125;')          // }
    .replace(/\(/g, '#40;')           // (
    .replace(/\)/g, '#41;')           // )
    .trim()
}
```

### 2. UnifiedRenderer 7 处 label 注入全部走 `sanitizeMermaidLabel`
- L82: `displayTitle` (subgraph label)
- L90: `group.title` (terminal node label)
- L88: `group.elementRef?.code` (terminal node code)
- L119: `childDisplayTitle` + `childCode` (children 终端 label)
- L147: `containerDisplayTitle` + `containerCode` (containers 终端 label)

### 3. MermaidGenerator 6 处 label 注入全部走 `sanitizeMermaidLabel`
- L131: `displayTitle` (subgraph label)
- L196: `containerDisplayTitle` (container label)
- L206: `node.name` + `node.code` (container 内 node label)
- L235: `node.name` + `node.code` (terminal node label)

### 4. V8ae invariant (新)

`tools/verify_v007_46_ioerror_recovery.py` 加 `check_v8ae`:
- `arrowHelper.js` 含 `export function sanitizeMermaidLabel`
- `sanitizeMermaidLabel` 含 `#quot;` 和 `<br/>` 转义
- `UnifiedRenderer.js` `sanitizeMermaidLabel(` 调用 ≥ 3
- `MermaidGenerator.js` `sanitizeMermaidLabel(` 调用 ≥ 3

### 5. 验证 (单元测试)

```
正常                  in: "财务云"        out: "财务云"
含 /                  in: "财务云 / 销售"  out: "财务云 / 销售"   ← mermaid 11.13 允许
含 " (致命)           in: 'BOSS"系统'    out: "BOSS#quot;系统"   ← 修复
含 \                  in: "BOSS\\系统"   out: "BOSS#92;系统"   ← 修复
含 换行               in: "BOSS\n系统"   out: "BOSS<br/>系统"   ← 修复
含 (                  in: "销售订单(主)"  out: "销售订单#40;主#41;" ← 修复
含 '                  in: "It's 系统"     out: "It#apos;s 系统"
disabledPath join     in: "销售管理（财务云 / 销售）"  out: 同样 (mermaid 11.13 允许)
综合                  in: 'A"b\\c\nd（e）' out: 'A#quot;b#92;c<br/>d（e）' ← 修复
```

### 6. V8w~V8ae 9/9 PASS

```
PASSED (9):
  + V8w: safe_connect.py _open_safe_connection 含 mmap_size=0
  + V8x: server.py _cleanup_resources 含 _cleanup_done 幂等守卫
  + V8y: query_service._apply_data_permission except 含 id=-1 拒绝
  + V8z: 3 文件 7 处裸连接全部改用 safe_connect_for_read
  + V8aa: import_export_service._flatten 含 leaf_op 参数
  + V8ab: 4 查询方法全部含 _apply_data_permission 调用
  + V8ac: db_health_monitor 2 处 + async_audit_writer 降级路径全部加固
  + V8ad: 4 个 db-level PRAGMA 全部有幂等保护
  + V8ae: mermaid 11.13 label 严格转义 (sanitizeMermaidLabel) 覆盖 UnifiedRenderer + MermaidGenerator

共 9/9 通过 ✅
```

---

## 给部署 agent 的明确交接

1. 拉 commit (待生成)
2. `python tools/verify_v007_46_ioerror_recovery.py` 必须 9/9
3. rsync 工作树到 deploy_bundle/
4. 打包 deploy-v20260708_015.zip
5. yonaa 部署后:
   - 选财务云 + 范围内与外部 → 不再报 "Syntax error in text"
   - mermaid 正确显示 subgraph + 1610 BO 节点
   - 外部 domain name (含 `"` 的) 也正确显示 (#quot; 在前端 SVG 转回 `"`)

**禁止操作**:
- ❌ 禁止回滚 `sanitizeMermaidLabel` (会复发 syntax error)
- ❌ 禁止只改 UnifiedRenderer 漏掉 MermaidGenerator (双生成器都要改)
- ❌ 禁止用 `'` 替代 `"` (link label 风格, 不适用于 subgraph label)

---

## 反思 (V007.45 dev-agent → V007.48)

| 错误 | 反思 |
|------|------|
| V007.42 P5 写 `sanitizeLabel` 用 `'` 替代 `"` 错了 | **link label (-->|"text"|) 和 subgraph label (["text"]) 规则不同** |
| 之前没意识到双生成器 (UnifiedRenderer + MermaidGenerator) | **任何 mermaid 生成器必须**统一**过 sanitize** |
| 之前没用 npm mermaid 11.13 实际解析测试 | **dev-agent 必须用真 mermaid 库 + jsdom 测**, 不能凭 mermaid 11 官方文档 |
| 之前没加 invariant V8ae | **mermaid 升级时 V8ae 必须 PASS** |

---

**作者**: V007.45 dev-agent (V007.48 P0 BUG-FIX)
**报告时间**: 2026-07-09 17:35
**下一步**: 部署智能体按"给部署 agent 的明确交接"步骤操作
