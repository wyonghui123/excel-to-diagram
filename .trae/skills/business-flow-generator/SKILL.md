---
name: business-flow-generator
description: Generate Playwright E2E spec + Screenplay Task from reviewed business-flow.yaml. In TRAE IDE, generated files are auto-opened and tests are run in terminal panel.
triggers:
  - PM/BA approved YAML
  - "/bt-continue"
  - "生成代码"
  - review_status 从 draft → reviewed/approved
---

# business-flow-generator

> **版本**: 1.0
> **状态**: Active
> **注册 ID**: SK-023
> **依赖**: business-flow-planner, Screenplay Framework

## 1. 必读上下文

- `.trae/specs/<feat>/business-flow.yaml` (**must be review_status: approved or reviewed**)
- `.trae/skills/business-flow-planner/SKILL.md`
- `e2e/screenplay/` (Screenplay 5 要素)
- `e2e/helpers/auto-fixtures.js` (数据隔离)
- `.trae/specs/_business_rules/_index.json` (业务规则索引)

## 2. Pipeline

### Stage 1: 校验
- 检查 `review_status != "draft"` (Generator 不接受 draft)
- 检查 `tasks/questions` 字段必填
- 检查 `tasks[].class` 在 Screenplay 已注册

### Stage 2: 生成 Screenplay Task
- 遍历 `tasks` 字段,生成 `e2e/screenplay/tasks/<TaskName>.js`
- 业务原子动作,**不是 UI 操作**

### Stage 3: 生成 Playwright Spec
- 遍历 `questions` 字段,生成 `e2e/business-flow/<feat>.spec.js`
- 业务断言 70% + DOM 断言 30%
- 使用 `e2e/helpers/auto-fixtures.js` 的 fixtures

### Stage 4: IDE 集成(关键)
- 调用 MCP:
  - `file_open(spec.js)` - 在 IDE 中打开生成的 spec
  - `terminal_run('npx playwright test e2e/business-flow/<feat>.spec.js')` - 跑测试
  - `status_bar_set('🤖 业务流 0/8 通过', progress=0)`
  - `show_notification('✅ 生成完成')`

## 3. 输出

- `e2e/screenplay/tasks/<TaskName>.js`
- `e2e/business-flow/<feat>.spec.js`
- IDE 中自动打开 + 跑测试

## 4. 模板示例

```javascript
// e2e/business-flow/business-object-lifecycle.spec.js
import { test, expect } from '../../helpers/auto-fixtures';
import { AdminActor } from '../../screenplay/actor';
import { 
  OpenBusinessObjectList, 
  OpenBusinessObjectForm, 
  FillBusinessObjectFields,
  VerifyKeyTemplateAutoFill,
  SaveBusinessObject,
} from '../../screenplay/tasks/BusinessObjectTasks';
import { BusinessRuleAssertor } from '../../screenplay/questions/BusinessRuleAssertor';

test.describe('业务对象生命周期', () => {
  test('happy path - 新建业务对象', async ({ page, isolation, apiClient }) => {
    const admin = AdminActor(page, { isolation, apiClient });
    
    // 业务动作(非 UI 操作)
    await admin.attemptsTo(
      OpenBusinessObjectList.in(page),
      OpenBusinessObjectForm.new(),
      FillBusinessObjectFields.with({ name: '客户订单' }),
      VerifyKeyTemplateAutoFill.with({ pattern: '{sm_code}{SEQ:2}', serviceModuleCode: 'SM01' }),
      SaveBusinessObject,
    );
    
    // 业务断言(非 DOM 断言)
    await admin.ask(BusinessRuleAssertor.assertRule('BR-business_object-KEY', {
      code: '...',
      serviceModuleCode: 'SM01',
    }));
  });
});
```

## 5. 关联

- 触发: PM/BA approved YAML
- 输入: `.trae/specs/<feat>/business-flow.yaml`
- 输出: `e2e/business-flow/<feat>.spec.js`
- 下游: Playwright 跑测试,失败 → business-flow-healer
