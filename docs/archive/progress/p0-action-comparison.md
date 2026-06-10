# P0 候选 Action 详细代码对比

> **日期**: 2026-06-05
> **目的**: 决策辅助 — 看完此表后可精准选择哪些 Action 实施

---

## 📊 P0 7 个 Action 现状对比

### 1️⃣ notification.publish — 业务价值 🔴 极高

**现有端点**：`POST /api/v1/notification/subscriptions` (notification_api.py:190-235)

**业务逻辑**（已读到 190-235 行）：
```python
@notification_bp.route('/subscriptions', methods=['POST'])
def create_subscription():
    user_id = g.get('user_id')
    data = request.get_json() or {}
    # 验证 object_type / event_types / channel / webhook_url
    # ds.insert('change_subscriptions', subscription)
    # logger.info(...)
```

**复杂度**：🟡 中（10 个字段 + 校验）
**业务含义**：用户订阅对象变化通知
**Action 设计**：`notification.create_subscription`
**优势**：跨 BO（object_type 可任意）—— 完美适合 V3 BO Action（V2 路径化不优雅）
**风险**：🟢 低（直接写表，不涉多 BO）
**预计工时**：1h

---

### 2️⃣ audit.retry — 运维价值 🟠 高

**现有端点**：`POST /api/v1/audit/failed/<record_id>/retry` (audit_management_api.py:34-51)

**业务逻辑**（已读全文 1-65 行）：
```python
@audit_mgmt_bp.route('/audit/failed/<int:record_id>/retry', methods=['POST'])
@login_required
def retry_failed_audit_log(record_id):
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403
    result = _audit_service.retry_failed_record(record_id)
    return jsonify({'success': result.get('success'), 'message': ...})
```

**复杂度**：🟢 极简（15 行）
**业务含义**：管理员重试失败的审计日志写入
**Action 设计**：`audit.retry`
**优势**：纯运维 / 已有 service 方法 `_audit_service.retry_failed_record()`
**风险**：🟢 低（admin 限定）
**预计工时**：30min

---

### 3️⃣ audit.export — 运维价值 🟠 高

**现有端点**：`GET /audit/logs/export` (audit_api.py:255-)

**业务逻辑**（已读 255-303 行）：
```python
@audit_bp.route('/logs/export', methods=['GET'])
@login_required
def export_audit_logs():
    action = request.args.get('action', '')
    object_type = request.args.get('object_type', '')
    # ... 5 个查询参数
    # 构建 conditions + where_clause
    # SELECT ... FROM audit_logs WHERE ... LIMIT 10000
    # rows = cursor.fetchall()
    # 生成 CSV 输出
```

**复杂度**：🟠 中（5 参数 + SQL 拼接 + CSV 生成）
**业务含义**：导出审计日志为 CSV
**Action 设计**：`audit.export`
**优势**：**返回文件流**（特殊 — V3 BO Action 当前仅返回 JSON；**需扩展**支持文件流）
**风险**：🟡 中（**v3 不支持文件流返回**，需要先扩展 `bo_action_api.py`）
**预计工时**：1.5h（含支持文件流）

---

### 4️⃣ user.reset_password — 业务价值 🟠 高

**现有端点**：`POST /api/v1/users/<user_id>/reset-password` (user_api.py:446-491)

**业务逻辑**（已读全文 446-491 行）：
```python
@user_bp.route('/<int:user_id>/reset-password', methods=['POST'])
@login_required
def reset_password(user_id):
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403
    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password', '')
    # 长度校验
    # 查用户存在
    # _hash_password_pbdkdf2(new_password)
    # _set_user_context() + transaction: UPDATE users SET password_hash, must_change_password=1
    # INSERT INTO audit_logs (object_type='user', action='RESET_PASSWORD')
    return jsonify({'success': True, 'message': '密码重置成功'})
```

**复杂度**：🟠 中（45 行 + 审计 + 事务）
**业务含义**：管理员重置用户密码（**强制 must_change_password=1**）
**Action 设计**：`user.reset_password`（与 `user.change_password` 对称）
**优势**：**完美对称** —— `user.change_password` 已是 BO Action，`user.reset_password` 同样适合
**风险**：🟢 低（admin 限定 + 已有同模式参考）
**预计工时**：30min

---

### 5️⃣ task.trigger — 运维价值 🟠 高

**现有端点**：`POST /api/v2/tasks/<task_code>/trigger` (task_api.py:43-55)

**业务逻辑**（已读 23-130 行）：
```python
@task_api_bp.route('/api/v2/tasks/<task_code>/trigger', methods=['POST'])
def trigger_task(task_code):
    scheduler = _get_scheduler()
    scheduler.trigger_task(task_code)
    return jsonify({'success': True, 'message': f'Task {task_code} triggered'})
```

**复杂度**：🟢 极简（12 行）
**业务含义**：手动触发定时任务
**Action 设计**：`task.trigger`
**优势**：**当前端点没有鉴权**（缺 `@login_required`）—— 改造为 BO Action **顺便加鉴权**
**风险**：🟢 低（无 DB 写 + 状态安全）
**预计工时**：30min

---

### 6️⃣ batch_delete (通用) — 业务价值 🟠 高

**现有端点**：`POST /api/v1/manage/<object_type>/batch-delete` (manage_api.py:984-998)

**业务逻辑**（已读 984-998 行）：
```python
@manage_bp.route('/<object_type>/batch-delete', methods=['POST'])
@_auth_required
def batch_delete(object_type):
    _set_audit_user()
    body = request.get_json(silent=True) or {}
    ids = body.get('ids', [])
    force = body.get('force', False)
    result = _get_manage_service().batch_delete(object_type, ids, force)
    return jsonify({
        'success': result.failed_count == 0,
        'success_count': result.success_count,
        'failed_count': result.failed_count,
        'results': [...],
        'errors': result.errors,
    })
```

**复杂度**：🟡 中（**通用** — 任意 object_type）
**业务含义**：批量删除
**Action 设计**：`batch_delete`（**已有** `batch_save` 镜像）
**优势**：**对称** —— 已实现 `batch_save`，加 `batch_delete` 完美
**风险**：🟡 中（删除是不可逆的；**必须小心**——但现有端点也做删除，所以无新风险）
**预计工时**：1h

---

### 7️⃣ state.transition — 业务价值 🔴 极高

**现有端点**：`POST /api/v1/manage/<object_type>/<id>/actions/<action_id>` (manage_api.py:1095-1119)

**业务逻辑**（已读 1095-1119 行）：
```python
@manage_bp.route('/<object_type>/<id>/actions/<action_id>', methods=['POST'])
@_auth_required
def execute_action(object_type, id, action_id):
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify(...), 404
    action = meta_obj.get_action(action_id)
    if not action:
        return jsonify(...), 404
    _set_audit_user()
    body = request.get_json(silent=True) or {}
    params = dict(body)
    params['id'] = int(id) if str(id).isdigit() else id
    result = _get_manage_service().executor.execute(meta_obj, action_id, params)
    return jsonify({...})
```

**复杂度**：🟠 中（15 行 + 多步）
**业务含义**：执行对象级自定义 Action（V2 BO API）
**Action 设计**：`{object_type}.{action_id}` 已经在 V2 体系
**优势**：❌ **已存在 V2 体系**——再下沉为 V3 **不增值**（V2 是单 BO 行为，V3 是跨 BO 业务）
**风险**：🟡 中（**重复工作**）
**预计工时**：1.5h（且价值有限）
**建议**：⚠️ **不做** — V2 已有，迁移价值低

---

## 📊 关键决策表

| # | Action | 价值 | 复杂度 | 现有端点 | V3 适配 | 工时 | 推荐 |
|---|--------|:---:|:---:|------|:---:|:---:|:---:|
| 1 | notification.publish | 🔴 | 🟡 | ✅ | ✅ 完美 | 1h | ✅ |
| 2 | audit.retry | 🟠 | 🟢 | ✅ | ✅ | 30min | ✅ |
| 3 | audit.export | 🟠 | 🟠 | ✅ | ⚠️ 需扩展文件流 | 1.5h | ⚠️ 慎重 |
| 4 | user.reset_password | 🟠 | 🟡 | ✅ | ✅ **对称完美** | 30min | ✅✅ |
| 5 | task.trigger | 🟠 | 🟢 | ✅ | ✅ | 30min | ✅ |
| 6 | batch_delete | 🟠 | 🟡 | ✅ | ✅ **对称完美** | 1h | ✅✅ |
| 7 | state.transition | 🔴 | 🟠 | ✅ | ❌ V2 已有 | 1.5h | ❌ |

---

## 🏆 强烈推荐（4 个最值得做）

| # | Action | 理由 | 工时 |
|---|--------|------|:---:|
| **4** | `user.reset_password` | 与 `user.change_password` **完美对称**，低风险 | 30min |
| **6** | `batch_delete` | 与 `batch_save` **完美对称**，业务高频 | 1h |
| **1** | `notification.publish` | 跨 BO 业务，V3 优势明显 | 1h |
| **2** | `audit.retry` | 极简，运维必需 | 30min |

**4 个总工时**: 3h

**审计 + 状态转换** (2/3/7)：要么需要扩展框架（文件流），要么已存在 V2 体系——本期**不做**。

---

## 📋 推荐组合

### 方案 A：3 个最稳妥（2h）

`user.reset_password` + `audit.retry` + `task.trigger`
- 全部极简、admin 限定、风险低
- 总工时：1.5h

### 方案 B：4 个高价值（3h）⭐推荐

`user.reset_password` + `batch_delete` + `notification.publish` + `audit.retry`
- 含 2 个"对称完美" Action（与已有配对）
- 含 1 个跨 BO 业务
- 含 1 个极简运维
- 总工时：3h

### 方案 C：全 7 个（6-7h）

含 audit.export (需扩展) + state.transition (迁移价值低)
- 风险较高、价值不均
- 总工时：6-7h

---

## ⚠️ 实施注意

- **bo_action_api.py 当前仅支持 JSON 返回**——`audit.export` 返回 CSV/Excel 需扩展（增加 `file_response` 支持）
- **V2 vs V3 选型**：单 BO 行为继续走 V2（路径化），跨 BO 业务走 V3（统一端点）
- **保留老端点**：本次实施**不删除**任何 endpoint，仅作为**新的调用方式**新增
- **回滚容易**：删除 server.py 注册行 + 删除 service 文件即可

---

## 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-05 | P0 7 个 Action 详细代码对比 + 决策表 |
