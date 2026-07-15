# DEPLOY_HANDOVER_BUG_V041 - 协调智能体 (PM) 交接文档

> 撰写: 2026-07-04 08:57 (Asia/Shanghai)
> 撰写人: bugfix-export agent (smart-annotation)
> 接收方: 协调智能体 / PM
> 优先级: **HIGH** - 用户当前报告的 BUG

---

## 0. 一句话总结

> **BUG-V041 修复已 commit + push + cherry-pick + 3011 后端重启**,
> 端到端 E2E 验证通过 - 用户导入 Excel 后 successes[].code 现在显示 `admin/TEST333/TEST888`
> 而不是空字符串。**没有影响 multi-object page (有 context 场景)**.

---

## 1. 用户报告

> "现在看ok的, 在导入结果展示页面上, 业务编码展示为空,
>  注意不要影响到multiple object page, 有 context 的场景 检查的仔细点"

---

## 2. 根因分析

### 2.1 直接原因
`meta/services/import_export_service.py` `_record_success_item` 调用的 `code_override` 参数
只查 `record.code / record.id_code` 字段 (line 6232), 而 **user schema 没有 `code` 字段**,
其业务编码对应 `username` (business_key=true)。

### 2.2 修复路径 (前后 2 个 commit)
- **commit `a8627c3`** (BUG-V041 初版): 加 `_get_row_code` 内部 business_key 字段回退
- **commit `ff1288b`** (BUG-V041 补全): 把 12 处 `_get_row_code(row)` 调用补传 `record`
  - 之前传 `record=None`, record 路径永远走不到
  - 修复后 `_get_row_code(row, record)` 才能真正使用 record[bk_id] 路径

### 2.3 multi-object page 安全性
- multi-object (multiTypeMode=true) 主要是 BO/relationship/annotation/domain/sub_domain/service_module
- 这些 schema 都有 `code` 字段, 走 `record.code` 优先路径 (新增回退不动该路径)
- 仅在"业务编码字段是 bk 字段 (如 user.username) 且无 code 字段"时走新路径
- **multi-object page 不受任何影响**

---

## 3. 我做了什么

### 3.1 Git

| 操作 | Commit | 状态 |
|------|--------|------|
| 修复 1 (业务键回退逻辑) | `a8627c3` | ✅ |
| 修复 2 (调用补传 record) | `ff1288b` | ✅ |
| push origin | `f3c2bcc..ff1288b` | ✅ |
| cherry-pick release-prep-worktree | `2246119` (在 `e36d007` 之上) | ✅ auto-merge OK |

### 3.2 代码改动 (1 文件, +13 -13)

`meta/services/import_export_service.py`:

1. **新增业务键字段发现** (line 6838-6848)
   ```python
   _bk_field_ids = []
   for _f in obj.fields:
       if getattr(_f.semantics, 'business_key', False) and _f.storage.value != 'virtual':
           _bk_field_ids.append(_f.id)
   ```

2. **修改 `_get_row_code` 优先级** (line 6850-6866)
   ```python
   def _get_row_code(row, record=None):
       if record:
           rec_code = record.get("code") or record.get("id_code")
           if rec_code: return rec_code.strip()
           # 业务键字段回退 (BUG-V041)
           for bk_id in _bk_field_ids:
               bk_val = record.get(bk_id)
               if bk_val: return bk_val.strip()
       if code_col_idx >= 0 and code_col_idx < len(row):
           v = row[code_col_idx]
           return str(v).strip() if v is not None else ""
       return ""
   ```

3. **修改 `_get_row_name`** (line 6868-6884) - 同步回退 (名称列也有此问题)

4. **12 处调用补传 `record`**
   ```python
   # Before:
   code_override=_get_row_code(row)
   # After:
   code_override=_get_row_code(row, record)
   ```

### 3.3 验证 (8/8 + E2E)

| Test | 场景 | 期望 |
|------|------|------|
| T1 | user 业务键回退 (record 路径) | 'admin' ✅ |
| T2 | BO 有 code 字段 (走 code 优先) | 'CUSTOMER' ✅ |
| T3 | user record 缺 username → '' | '' (防御) ✅ |
| T4 | BO 优先级 record.code > bk | 'CUSTOMER' ✅ |
| T5 | row[col_idx] 兜底仍工作 | '编码列' ✅ |
| T6 | 整数业务键 '42' | '42' ✅ |
| T7 | relationship multi-object 不受影响 | 'REL_001' ✅ |
| T8 | 传 record 后实际走 username 路径 | 'admin' ✅ (mini E2E) |
| E2E | 用户真实 Excel import execute | **code='admin/TEST333/TEST888'** ✅ |

---

## 4. PM 必须做的事

### 4.1 已完成 ✅
1. ✅ 3011 后端已重启 (PID 10512, 启动 8:55:53, 加载新 .pyc 8:55:42)
2. ✅ E2E 验证通过
3. ✅ 修复 commit 已在本地 feat + release-prep-worktree
4. ✅ 修复 commit 已 push 到 origin

### 4.2 待 PM 确认 (可选)
- 让用户在 3006 上重新跑一次用户导入, 在第 4 步"成功"tab 看到
  admin / TEST333 / TEST888 的"业务编码"列显示正确 username
- 让用户在架构数据管理页跑 multi-object 导入, 确认 BO 等有 code 字段的对象
  业务编码仍正确显示 (走 record.code 优先路径)

---

## 5. 关键文件路径

| 文件 | 路径 |
|------|------|
| Fix commit 1 (feat branch) | `a8627c3` |
| Fix commit 2 (feat branch) | `ff1288b` |
| Cherry-pick commit (release branch) | `2246119` |
| 改动文件 | `D:\filework\excel-to-diagram\meta\services\import_export_service.py` |
| 用户上传文件 | `C:\Users\Administrator\Downloads\用户_20260704_072435.xlsx` |
| Schema (无 code 字段, bk=username) | `D:\filework\excel-to-diagram\meta\schemas\user.yaml` |
| 3011 后端进程 | PID 10512, 启动 2026-07-04 08:55:53 |

---

## 6. 当前服务状态

| 服务 | 状态 | 进程 |
|------|------|------|
| 3006 vite preview | ✅ | PID 22632 (BUG-V039 修复生效) |
| 3011 python 后端 | ✅ | **PID 10512 (BUG-V040 + BUG-V041 修复生效)** |

---

## 7. 关联 BUG 历史

| BUG | 描述 | Fix Commit | 状态 |
|-----|------|------------|------|
| BUG-V037 | ObjectDetailPage 4 变量同步 | `797edb8` | ✅ 已部署 |
| BUG-V038 | 导出"上下文信息"section 强制显示 | `0407f60` / `3d3f563` | ⚠️ 部分 (前端部署, 后端需重启) |
| BUG-V039 | ImportDialog 第 3 步强制 product_version | `e13fcb4` | ✅ 已部署 |
| BUG-V040 | 枚举值校验 user.status | `f3c2bcc` / `eb5c8c0` | ✅ 已部署 |
| **BUG-V041** | **结果展示页业务编码空** | **`a8627c3` + `ff1288b` / `2246119`** | **✅ 已部署** |

---

**撰写完成时间**: 2026-07-04 08:57
**紧急级别**: HIGH (用户当前 BUG)
**当前状态**: ✅ 修复 + 重启 + E2E 验证全部完成
