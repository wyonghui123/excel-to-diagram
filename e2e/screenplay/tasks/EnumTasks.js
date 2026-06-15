/**
 * Screenplay Pattern - Enum Tasks
 *
 * 枚举管理相关的业务原子动作
 */

import { Click, Fill, Navigate, Wait } from '../interactions';

/**
 * 打开枚举类型列表
 */
export class OpenEnumTypeList {
  static in(page) {
    return new OpenEnumTypeList();
  }

  async performAs(actor) {
    await Navigate.to('/enum-type/list').performAs(actor);
    await Wait.for('[data-testid="enum-type-table"]').performAs(actor);
  }
}

/**
 * 打开枚举值/类型表单
 */
export class OpenEnumValueForm {
  static new({ type = 'enum_value' } = {}) {
    return new OpenEnumValueForm({ type });
  }

  constructor(params) {
    this.type = params.type;
  }

  async performAs(actor) {
    const selector = this.type === 'enum_type'
      ? '[data-testid="new-enum-type"]'
      : '[data-testid="new-enum-value"]';
    await Click.on(selector).performAs(actor);
    const formSelector = this.type === 'enum_type'
      ? '[data-testid="enum-type-form"]'
      : '[data-testid="enum-value-form"]';
    await Wait.for(formSelector).performAs(actor);
  }
}

/**
 * 填写枚举字段
 */
export class FillEnumFields {
  static with(fields) {
    return new FillEnumFields(fields);
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
 * 保存枚举
 */
export class SaveEnum {
  async performAs(actor) {
    await Click.on('[data-testid="save"]').performAs(actor);
    await Wait.for('[data-testid="save-success-toast"]').performAs(actor);
  }
}

/**
 * 删除枚举值
 */
export class DeleteEnum {
  static with(code) {
    return new DeleteEnum(code);
  }

  constructor(code) {
    this.code = code;
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    const row = page.locator(`tr:has-text("${this.code}")`);
    await row.locator('[data-testid="delete-btn"]').click();
    await Wait.for('[data-testid="confirm-delete-dialog"]').performAs(actor);
    await Click.on('[data-testid="confirm-delete-btn"]').performAs(actor);
  }
}
