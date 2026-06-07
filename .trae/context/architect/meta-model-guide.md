# 元模型设计指南

## 核心原则

1. **YAML Schema是唯一定义源**（meta/schemas/*.yaml）
2. 所有元数据通过 registry.get() 访问
3. 当前定义24个元模型对象
4. 支持字段、关系、动作、校验、UI配置等完整元数据

## Schema变更流程

详见 `.trae/rules/meta-model-schema-sync.md`

1. 修改YAML Schema文件
2. 运行同步脚本
3. 验证前后端一致性
4. 更新相关文档

## 关键约束

- 历史 Python 对象定义已归档至 archive/objects-backup/
- 新增元模型对象必须先定义YAML Schema
- 字段语义（semantics）必须完整定义
- UI配置（ui）必须包含widget、visible、editable
