/**
 * Screenplay Pattern - Business Object Tasks
 *
 * 业务对象相关的业务原子动作(非 UI 操作)。
 * 这些是业务意图,而非具体的 button click。
 */

import { Click, Fill, Navigate, Wait } from '../interactions';
import { BusinessRuleAssertor } from '../questions/BusinessRuleAssertor';

/**
 * 打开业务对象列表
 */
export class OpenBusinessObjectList {
  static in(page) {
    return new OpenBusinessObjectList();
  }

  async performAs(actor) {
    await Navigate.to('/business-object/list').performAs(actor);
    await Wait.for('[data-testid="business-object-table"]').performAs(actor);
  }
}

/**
 * 打开业务对象新建表单
 */
export class OpenBusinessObjectForm {
  static new() {
    return new OpenBusinessObjectForm();
  }

  async performAs(actor) {
    await Click.on('[data-testid="new-business-object"]').performAs(actor);
    await Wait.for('[data-testid="business-object-form"]').performAs(actor);
  }
}

/**
 * 填写业务对象字段
 */
export class FillBusinessObjectFields {
  static with(fields) {
    return new FillBusinessObjectFields(fields);
  }

  constructor(fields) {
    this.fields = fields;
  }

  async performAs(actor) {
    for (const [field, value] of Object.entries(this.fields)) {
      await Fill.the(field).with(value).performAs(actor);
    }
  }
}

/**
 * 验证 key_template 自动编码
 */
export class VerifyKeyTemplateAutoFill {
  static with({ pattern, serviceModuleCode }) {
    return new VerifyKeyTemplateAutoFill({ pattern, serviceModuleCode });
  }

  constructor(params) {
    this.pattern = params.pattern;
    this.serviceModuleCode = params.serviceModuleCode;
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    const code = await page.inputValue('[data-testid="code"]');

    if (!code) {
      throw new Error('key_template 自动编码失败: code 字段为空');
    }

    // 验证 code 起始匹配服务模块编码
    if (!code.startsWith(this.serviceModuleCode)) {
      throw new Error(
        `key_template 自动编码失败: 期望起始 ${this.serviceModuleCode}, 实际 ${code}`
      );
    }

    return { code };
  }
}

/**
 * 保存业务对象
 */
export class SaveBusinessObject {
  async performAs(actor) {
    await Click.on('[data-testid="save"]').performAs(actor);
    // 等待保存成功(列表刷新)
    await Wait.for('[data-testid="save-success-toast"]', { timeout: 5000 }).performAs(actor);
  }
}

/**
 * 创建关系
 */
export class CreateRelationship {
  static between({ source, target, type }) {
    return new CreateRelationship({ source, target, type });
  }

  constructor(params) {
    this.source = params.source;
    this.target = params.target;
    this.type = params.type;
  }

  async performAs(actor) {
    const api = actor.abilityTo('CallAPI');
    return await api.post('/relationship', {
      source_id: this.source.id,
      target_id: this.target.id,
      type: this.type,
    });
  }
}

/**
 * 删除业务对象
 */
export class DeleteBusinessObject {
  static with(code) {
    return new DeleteBusinessObject(code);
  }

  constructor(code) {
    this.code = code;
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    // 列表中找这一行,点击删除按钮
    const row = page.locator(`tr:has-text("${this.code}")`);
    await row.locator('[data-testid="delete-btn"]').click();
    // 确认弹窗
    await Wait.for('[data-testid="confirm-delete-dialog"]').performAs(actor);
    await Click.on('[data-testid="confirm-delete-btn"]').performAs(actor);
  }
}

/**
 * 验证业务对象已删除
 */
export class AssertBusinessObjectDeleted {
  static with(code) {
    return new AssertBusinessObjectDeleted(code);
  }

  constructor(code) {
    this.code = code;
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    const row = page.locator(`tr:has-text("${this.code}")`);
    const count = await row.count();
    if (count > 0) {
      throw new Error(`业务对象 ${this.code} 应已被删除,但仍存在`);
    }
  }
}
