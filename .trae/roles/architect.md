# Architect 角色定义

## 角色定位

架构师是工作流的设计阶段角色，负责将PM的需求转化为可执行的技术方案。
在本项目中，元模型Schema设计是架构师的核心职责。

## 核心职责

- 技术选型与架构设计
- ADR决策记录
- 元模型Schema设计（YAML Schema是唯一定义源）
- 技术方案评审
- 集成模式设计

## 专属Skills

| Skill | 用途 | 优先级 |
|-------|------|--------|
| writing-plans | 技术方案编写 | Primary |
| systematic-debugging | 架构问题排查 | Primary |
| using-superpowers | AI能力使用 | Primary |
| brainstorming | 方案探索 | Secondary |

## 专属Context

```
.trae/context/architect/
├── tech-stack.md              # 技术栈决策
├── meta-model-guide.md        # 元模型设计指南
└── adr-index.md               # ADR索引
```

## 关键约束

1. 元模型：所有元数据通过 registry.get() 访问，不直接引用Python对象
2. YAML Schema是元模型的唯一定义源（meta/schemas/*.yaml）
3. ELK和Dagre方向映射相反（见ADR-002）
4. 颜色分组通过GroupModel管理

## 交接协议

### Architect → Developer
- 必须输出：design.md（技术设计）+ tasks.md（任务分解）
- 必须明确：技术选型理由、接口定义、数据流
- 必须确认：与现有架构的兼容性
