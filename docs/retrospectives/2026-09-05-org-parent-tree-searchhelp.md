# 复盘: 父组织树状 SearchHelp 排查与修复 (2026-09-05)

> **任务**: org.parent_id 从扁平下拉改造为树状 SearchHelp 弹窗 (spec16)
> **结果**: 修复 2 个真实 bug, 浏览器级全链路验证通过; 验证阶段约 12 次往返, 其中 8 次消耗在与"树逻辑本身无关"的卡点上
> **改动文件**: meta/schemas/org.yaml, meta/schemas/schema_loader.py, src/components/common/{SearchHelpDialog,ValueHelpField}.vue, meta/core/models_value_help.py, meta/core/yaml_loader.py, meta/core/ui_config/value_help_formatter.py
> **目的**: 提炼可复用的排查动作, 让未来同类问题一次命中

---

## 一、最终修复的两个 bug

| # | bug | 层 | 症状 | 修复 |
|---|-----|-----|------|------|
| 1 | value-help 链路 total 语义 = **当页行数**而非总数 (实测 page1 total=500, page2 total=459, 真实 959) | 前端循环分页 | 首页后 `all.length >= total` 误判提前 break → 只拉 500/959 行, 树静默缺 459 节点 | SearchHelpDialog.loadGenericTreeData 只以 `rows.length < PAGE_SIZE` 判结束, 删除 total 判据 |
| 2 | `/api/v1/meta/<type>/ui-config` (SchemaLoader.load_schema) 字段序列化**丢 value_help** | 后端序列化 hop | 表单拿不到 dialog/tree 配置 → ValueHelpField 静默回退 dropdown, 树弹窗**根本不出现** | schema_loader 增加 `_serialize_value_help` (复用 value_help_to_dict, 延迟 import 防环) |

**关键认知**: 两个 bug 都不在"新写的树逻辑"里, 而在链路上**从未被验证过的既有环节** (分页判据 / 序列化 hop)。

## 二、卡点时间线 (验证阶段, 按消耗排序)

### 1. DOM 猜测式定位 — 4 轮试错
- 按钮定位命中隐藏元素 (其他 tab 面板的重复按钮) → 需 `:visible` 过滤
- `router.push` 直跳目标路由后工具栏按钮不渲染 (tab 内组件状态未初始化) → 必须模拟真实 tab 点击
- 假设表单是 `el-form-item` → dump 为空 (MOMP 实为 op-field 自定义结构)
- "上级组织"文本同时命中**左侧范围树列头**和表单 label → 点错 input, 需在 `.el-drawer` 域内查 label

### 2. 环境坏点 — 3 轮
- `service_manager.ps1` PS5.1 语法解析失败 (疑似 PS7 语法), pwsh 不存在
- `python service_manager.py restart --port 3010` 实际起在 **3011** (显式端口未透传/语义不同, 未深究)
- 手动 kill + `AGENT_PORT=3010 python waitress_server.py` 才恢复; vite proxy 固定指 3010, 3011 起了也白起

### 3. 假阳性验证 — 2 轮
- 编辑了错误记录: `has_text='TEST888'` 子串匹配同时命中 TEST888_GROUP(id=8279) → "回显为空"是**正确行为** (8279 本来无父级), 白查一轮
- 防环假阳性: nodeCount 937→936 以为剪枝生效 → 实际 el-tree 未展开节点**不渲染 DOM**, 1045/1046 的 label 根本不在页面里。真正证明要靠: 树内搜索目标 (0 命中=剪除) + 展开父级看 children

### 4. 端点试错 — 2 轮
- 按 `/api/v2` 前缀试 ui-config 404 (meta_bp 实际挂 `/api/v1`) → 翻 blueprint url_prefix 确认

### 5. 自伤性误报 — 1 轮
- 自己 curl 漏带 `hierarchy` 参数 → 误判后端 extra.parent_id 注入失效 (后端契约: 不带 hierarchy 参数就不注入)

## 三、效率损失归因 (根因)

### 1. 验证层级错位 ★ 最大教训
上一会话的 verify_parent_tree.cjs 验证了 **yaml 解析 + value-help 数据端点**, 但表单实际消费的是 **ui-config 端点**。`yaml → MetaField → ui-config JSON` 这个序列化 hop 从未被验证 → 树逻辑全部写完后, 功能在第 0 秒就是坏的, 拖到浏览器阶段才暴露。

> **原则: 验证"消费链路", 不是"改动清单"。**

元数据驱动功能的检查清单: `yaml → loader/engine → 每个序列化出口 → 前端 service → 组件 props → 渲染`。改动完成后**先用 curl 打最终消费端点核对 payload 全部关键字段**, 再投入 UI 自动化。本次若先做这步, bug2 在 1 分钟内就能发现, 省 8+ 轮。

### 2. DOM 猜测 vs 源码先行
4 轮 DOM 试错的根因是**没先读页面组件源码**。后来读 ObjectPageShell/ObjectPageField 一次看清: op-field 结构、编辑入口在详情抽屉 (列表无行内编辑按钮)、数据来自 `metaService.getUIConfig`。

> **原则: 自动化脚本前先读视图组件源码, 提取结构与入口路径; 同名词元素用容器域限定选择器。**

### 3. 数据画像滞后
959 行里只有 23 行有 parent_id、仅 1 条三代链 (15 New Group → 1045 采购领域小组 → 1046 采购领域小组宽放)。这些决定测试样本, 却在中后段才查明 → 936 roots 的"疑似 bug"困惑 + 错误样本选择。

> **原则: 树/层级类任务开工先做数据画像 (总数 / 父指针分布 / 最深链), 直接选定验证样本。**

### 4. 工具链坏点 (每次踩都重新付费)
| 坏点 | 现象 | 状态 (2026-09-05 已修) |
|------|------|---------|
| scripts/service_manager.ps1 | PS5.1 解析 19 个语法错误。**根因不是 PS7 语法** (初判有误): 文件是无 BOM UTF-8 + LF 换行, PS5.1 按 GBK 解码, 中文注释尾字节吞掉 LF → 1001 行变 976 行、结构崩坏 | [已修] 转为 UTF-8 BOM + CRLF, ParseFile 0 errors |
| scripts/service_manager.py `--port` | restart --port 3010 起在 3011: 只覆盖 SERVICES[].port, env 里硬编码的 AGENT_PORT=3011 未同步 | [已修] --port 时同步覆盖 AGENT_PORT/BACKend_PORT, 实测起在 3010 |
| test.py | PROJECT_ROOT 硬编码 worktree 路径 (不存在) → NotADirectoryError | [已修] 改为 Path(__file__).resolve().parent, 实测 pytest 正常执行 (32 passed; 1 个失败为 spec16 role→permission_set 存量断言过时, 另行处理) |
| 裸 pytest | 被全局拦截器拦 (要求走 test.py), test.py 修好后此链路已通 | [已通] python test.py --file <path> 可用 |

### 5. 验证脚本自身低级 bug (节奏打断)
lambda 多参数、截图无扩展名、按钮文案集合漏"确认选择"。累计打断节奏。
> **模式: 验证脚本先 dump 后断言** (把按钮/文案/结构列表先打出来再决定匹配方式), 用统一 log 助手 (log + print 双输出, 崩了也有现场)。

## 四、正面实践 (保持)

- **curl 打真实端点做语义核对**: total 语义 (page1=500/page2=459) 就是这样一次钉死的, 快于任何 UI 手段
- **读源码定位数据流**: ObjectPageShell → getUIConfig → SchemaLoader, 一次命中 bug2 根因
- **network tracking 拿实证**: formData={id:8279, parent_id:null} 直接终止"回显 bug"空猜
- **git stash 对照**: 证明 ValueHelpField 单测失败是存量问题 (useVersionContext 依赖 router), 避免误伤本次改动
- **修根因不修症状**: 分页判据、序列化 hop 都改在链路正确位置

## 五、未来排查/修复标准动作 (提炼)

1. **消费端冒烟先行**: 改动完成 → curl 最终消费端点 → 核对全部关键字段 → 再进 UI 验证
2. **源码先行**: 写自动化前读视图组件, 提取结构/入口/选择器 (MOMP 表单=op-field, 编辑入口=详情抽屉)
3. **数据画像先行**: 层级类任务先查父指针分布, 选定三代链样本
4. **链路断点优先假设**: "配置改了但没生效" → 逐 hop 查序列化/透传, 最后才怀疑新组件逻辑
5. **树验证两板斧**: 树内搜索目标 (0 命中=剪除) + 展开父级看 children; 禁止只数 nodeCount (el-tree 懒渲染)
6. **环境坏点即时登记**: 每踩一个工具坑记入 project_memory 并开修复项, 不重复付费

## 六、遗留事项

- [x] ~~修 scripts/service_manager.ps1 PS5.1 兼容~~ (2026-09-05 已修: UTF-8 BOM + CRLF)
- [x] ~~修 scripts/service_manager.py --port 透传 AGENT_PORT~~ (2026-09-05 已修, 实测起在 3010)
- [x] ~~修 test.py PROJECT_ROOT 硬编码~~ (2026-09-05 已修: Path(__file__).parent)
- [ ] ValueHelpField 存量单测: useVersionContext 在无 router 环境报 route.query (独立修复)
- [ ] test_yaml_loader 存量断言: test_registry_list_objects 断言 'role' 在注册表中, 但 spec16 已 role→permission_set (独立修复)
- [ ] OrgManagement.vue (/org-management) 数据源仍是 user_group; spec16 切换时需把树状配置同步到 user_group.yaml 或切 objectType
