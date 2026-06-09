---
title: 审计日志最佳实践
version: 1.0.0
date: 2026-06-07
status: 活跃
audience: 架构师、开发者、运维
---

# 审计日志最佳实践方案

## 1. 参考头部企业实践

### SAP S/4HANA
- **审计日志不可随意删除**，保留周期长（6个月到7年）
- 有专门的程序来读取归档的审计日志（SARA, RSAU_ARCHIVE_READ）
- 支持细粒度的字段级审计
- 区分运行日志和审计日志

### Salesforce
- **软删除机制**：删除的记录进入回收站（Recycle Bin），保留15-30天
- 支持硬删除和软删除的区分
- 有专门的审计轨迹（Field Audit Trail）
- 可以恢复误删的记录
- 保留完整的数据变更历史

### 通用最佳实践
1. **只记录变更**：只记录实际发生变化的字段，避免记录无意义的变更
2. **保留完整上下文**：记录操作人、操作时间、IP地址、客户端信息等
3. **支持数据恢复**：通过审计日志可以恢复误删或错误修改的数据
4. **软删除优先**：优先使用软删除，保留删除前的数据快照
5. **异步写入**：审计日志写入不应该阻塞业务流程

## 2. 当前实现状态

### ✅ 已实现功能

| 功能 | 状态 | 说明 |
|-----|------|------|
| CREATE审计 | ✅ 正常 | 记录所有初始字段值 |
| UPDATE审计 | ✅ 正常 | 只记录有变更的字段 |
| DELETE审计 | ✅ 正常 | 记录删除前的完整数据 |
| 异步写入 | ✅ 正常 | 不阻塞业务流程 |
| 前端显示 | ✅ 正常 | 支持分页和过滤 |
| 通用装饰器 | ✅ 正常 | @audit_log 装饰器 |

### ⚠️ 需要完善的功能

| 功能 | 状态 | 说明 |
|-----|------|------|
| 软删除 | ❌ 未实现 | 当前直接硬删除 |
| 数据恢复 | ❌ 未实现 | 无法恢复误删数据 |
| 归档机制 | ❌ 未实现 | 需要长期保留策略 |
| 字段历史 | ⚠️ 部分实现 | user/role/group已实现，其他对象未实现 |

## 3. 审计日志表结构

```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT NOT NULL,          -- 对象类型：user, role, group等
    object_id TEXT NOT NULL,            -- 对象ID
    action TEXT NOT NULL,               -- 操作类型：CREATE, UPDATE, DELETE
    field_name TEXT,                    -- 字段名
    old_value TEXT,                     -- 旧值
    new_value TEXT,                     -- 新值
    user_id TEXT,                       -- 操作人ID
    user_name TEXT,                     -- 操作人姓名
    ip_address TEXT,                    -- IP地址
    user_agent TEXT,                    -- 用户代理
    created_at TEXT NOT NULL,           -- 操作时间
    -- 扩展字段
    trace_id TEXT,                      -- 追踪ID
    transaction_id TEXT,                 -- 事务ID
    status TEXT,                        -- 状态：written, failed
    error_message TEXT,                 -- 错误信息
    agent_id TEXT,                      -- Agent ID
    agent_session_id TEXT,              -- Agent会话ID
    tool_call_id TEXT,                  -- 工具调用ID
    agent_reasoning TEXT,               -- Agent推理内容
    extra_data TEXT,                    -- 额外数据（JSON）
    
    -- 索引
    INDEX idx_object (object_type, object_id),
    INDEX idx_user (user_id),
    INDEX idx_action (action),
    INDEX idx_created (created_at),
    INDEX idx_status (status)
);
```

## 4. 通用审计日志装饰器

```python
@audit_log(object_type='user')
def update_user(self, user_id, data):
    # 业务逻辑
    ...
```

装饰器会自动：
1. 检测操作类型（CREATE/UPDATE/DELETE）
2. 获取变更前后的数据
3. 异步写入审计日志
4. 只记录有变更的字段

## 5. 删除数据查看方案

### 方案一：软删除 + 审计日志（推荐）

```sql
-- 给需要审计的对象添加软删除字段
ALTER TABLE users ADD COLUMN deleted_at TEXT;
ALTER TABLE users ADD COLUMN deleted_by TEXT;
```

```python
def delete_user(user_id):
    # 不直接删除，而是标记为已删除
    _data_source.execute("""
        UPDATE users 
        SET deleted_at = ?, deleted_by = ?
        WHERE id = ?
    """, [datetime.now().isoformat(), get_current_user().get('user_id'), user_id])
    
    # 记录审计日志
    _get_audit_interceptor().log_delete(...)
```

### 方案二：通过审计日志恢复

查看已删除数据的审计日志：

```sql
SELECT * FROM audit_logs 
WHERE object_type = 'user' 
  AND action = 'DELETE'
  AND object_id = ?
ORDER BY created_at DESC;
```

### 方案三：定期归档 + 查询接口

```python
@audit_bp.route('/archive', methods=['GET'])
def get_deleted_records():
    """查询已归档的删除记录"""
    object_type = request.args.get('object_type')
    
    cursor = _data_source.execute("""
        SELECT * FROM audit_logs 
        WHERE object_type = ? 
          AND action = 'DELETE'
        ORDER BY created_at DESC
    """, [object_type])
    
    return jsonify({'success': True, 'data': cursor.fetchall()})
```

## 6. 前端展示优化

### 变更日志列表

```vue
<template>
  <div class="audit-log">
    <div class="audit-filters">
      <el-select v-model="filterAction" placeholder="操作类型">
        <el-option label="全部" value="" />
        <el-option label="创建" value="CREATE" />
        <el-option label="更新" value="UPDATE" />
        <el-option label="删除" value="DELETE" />
      </el-select>
      <el-date-picker v-model="dateRange" type="daterange" />
    </div>
    
    <div class="audit-list">
      <div v-for="log in logs" :key="log.id" class="audit-item">
        <div class="audit-header">
          <el-tag :type="getActionType(log.action)">{{ log.action }}</el-tag>
          <span class="audit-time">{{ log.created_at }}</span>
          <span class="audit-user">{{ log.user_name }}</span>
        </div>
        
        <div class="audit-detail">
          <template v-if="log.action === 'UPDATE'">
            <span class="field-name">{{ log.field_name }}:</span>
            <span class="old-value">{{ log.old_value }}</span>
            <span class="arrow">→</span>
            <span class="new-value">{{ log.new_value }}</span>
          </template>
          <template v-else-if="log.action === 'CREATE'">
            <span class="field-name">{{ log.field_name }}:</span>
            <span class="new-value">{{ log.new_value }}</span>
          </template>
          <template v-else-if="log.action === 'DELETE'">
            <span class="field-name">{{ log.field_name }}:</span>
            <span class="old-value">{{ log.old_value }}</span>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
```

## 7. 下一步行动计划

### 短期（1-2周）
1. ✅ 统一审计日志记录逻辑（所有对象使用同一套装饰器）
2. ✅ 修复 UPDATE 时只记录变更字段
3. ✅ 完善前端展示，支持时间范围过滤
4. ⬜ 添加软删除支持

### 中期（1个月）
1. ⬜ 实现数据恢复功能
2. ⬜ 添加审计日志归档机制
3. ⬜ 支持审计日志导出（CSV/Excel）
4. ⬜ 添加审计日志统计报表

### 长期（3个月）
1. ⬜ 实现审计日志实时监控
2. ⬜ 添加异常操作告警
3. ⬜ 支持审计日志合规报告生成
4. ⬜ 集成第三方SIEM系统

## 8. 合规性建议

| 场景 | 保留周期 | 说明 |
|-----|---------|------|
| 金融行业 | 7年 | 满足监管要求 |
| 医疗行业 | 6年 | HIPAA合规 |
| 电商行业 | 3年 | 消费者权益保护 |
| 一般企业 | 1年 | 基础合规 |

## 9. 性能优化

1. **异步写入**：审计日志写入不阻塞主业务流程
2. **批量写入**：积累一定数量后批量提交
3. **读写分离**：大量查询走只读副本
4. **定期清理**：归档旧数据，保持查询性能

## 10. 安全考虑

1. **审计日志本身也需要审计**：谁查看了审计日志
2. **防篡改**：使用哈希链或区块链技术防止日志被修改
3. **访问控制**：只有特定角色可以查看审计日志
4. **加密存储**：敏感信息加密存储
