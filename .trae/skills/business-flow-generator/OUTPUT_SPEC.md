# business-flow-generator - OUTPUT_SPEC

## 输出文件

### 1. Screenplay Task

`e2e/screenplay/tasks/<TaskName>.js`

每个 task class 一文件。命名: PascalCase,以动词开头。

### 2. Playwright Spec

`e2e/business-flow/<feat>.spec.js`

## 校验

- spec.js 必须能跑通 (`npx playwright test <path>`)
- 业务断言 ≥ 70%
- DOM 断言 ≤ 30%
- 使用 `auto-fixtures.js` 的 `isolation` fixture

## 模板

```javascript
import { test, expect } from '../../helpers/auto-fixtures';
import { AdminActor } from '../../screenplay/actor';
import { BusinessRuleAssertor } from '../../screenplay/questions/BusinessRuleAssertor';

test.describe('<业务流描述>', () => {
  test('<场景名>', async ({ page, isolation, apiClient }) => {
    const admin = AdminActor(page, { isolation, apiClient });
    
    // === 业务动作 ===
    await admin.attemptsTo(
      Task1.with(params),
      Task2.with(params),
    );
    
    // === 业务断言 ===
    await BusinessRuleAssertor.assertRule('BR-...', context);
  });
});
```

## 质量门禁

| 指标 | 目标 |
|------|------|
| 业务断言比例 | ≥ 70% |
| 跨页路由 | ≥ 3 |
| 数据隔离 | 100% |
| 跑通测试 | 100% |
