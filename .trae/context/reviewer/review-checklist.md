# 审查清单

## Stage 1: Spec合规性审查

- [ ] 代码是否实现了spec中的所有需求？
- [ ] 是否有超出spec的额外实现？（YAGNI检查）
- [ ] 验收标准是否全部满足？
- [ ] 用户故事是否完整覆盖？
- [ ] PM场景功能是否通过PM用户路径验证？

## Stage 2: UI规范审查（重要！）

### 组件使用规范
- [ ] Tab导航是否使用 `AppTabs` 组件或底部指示线样式？
- [ ] 侧边导航是否使用 `AppSideNav` 组件或左侧指示线样式？
- [ ] 日志展示是否使用 `AuditLog` 组件？
- [ ] 消息通知是否使用 `useMessage()` 而非 `alert()`？

### 样式规范
- [ ] 是否使用设计令牌（CSS变量）而非硬编码颜色？
- [ ] 文本颜色是否正确使用？（primary/secondary/tertiary）
- [ ] 是否避免了全局自定义滚动条样式？
- [ ] 间距是否使用 `--spacing-*` 变量？
- [ ] 字体大小是否使用 `--font-size-*` 变量？

### yonDesign规范
- [ ] 是否查阅了 [UI_COMPONENT_GUIDELINES.md](../../docs/UI_COMPONENT_GUIDELINES.md)？
- [ ] 是否查阅了 [YONYOU_DESIGN.md](../../src/styles/YONYOU_DESIGN.md)？
- [ ] Tab是否使用底部指示线而非填充背景？
- [ ] 侧边导航是否使用左侧指示线而非背景填充？

## Stage 3: 代码质量审查

### Critical（必须修复）
- [ ] 是否有安全漏洞？（XSS、SQL注入、密钥泄露）
- [ ] 是否有数据丢失风险？
- [ ] 是否有破坏现有功能的变更？

### Important（应该修复）
- [ ] 是否遵循编码规范？
- [ ] 是否有性能问题？（N+1查询、大循环、内存泄漏）
- [ ] 错误处理是否完善？
- [ ] 是否有硬编码的配置值？

### Suggestion（可以改进）
- [ ] 代码可读性
- [ ] 设计模式使用
- [ ] 测试覆盖率
- [ ] 文档完整性

## UE验收标准

- [ ] 交互是否符合设计原则？（见 context/pm/design-principles.md）
- [ ] 消息通知是否使用 useMessage()？
- [ ] 危险操作是否有二次确认？
- [ ] 响应式是否正常？
