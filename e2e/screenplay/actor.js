/**
 * Screenplay Pattern - Actor
 *
 * Actor 是业务流测试的核心抽象,封装:
 *  - 角色 (Admin / BusinessAnalyst / Readonly / DataSteward)
 *  - 能力 (BrowseTheWeb / CallAPI / IsolateData)
 *  - 执行能力 (attemptsTo) - 跑业务动作
 *  - 询问能力 (ask) - 跑业务断言
 *
 * 用法:
 *   const admin = AdminActor(page, helpers);
 *   await admin.attemptsTo(CreateBusinessObject.with({ name: '客户订单' }));
 *   await admin.ask(BusinessRuleAssertor.assertRule('BR-...', { ... }));
 */

export class Actor {
  constructor(name, abilities = {}) {
    this.name = name;
    this.abilities = abilities;
  }

  static named(name) {
    return new Actor(name);
  }

  can(ability) {
    this.abilities[ability.constructor.name] = ability;
    return this;
  }

  abilityTo(abilityName) {
    const ability = this.abilities[abilityName];
    if (!ability) {
      throw new Error(
        `Actor ${this.name} has no ability "${abilityName}". ` +
        `Available: ${Object.keys(this.abilities).join(', ')}`
      );
    }
    return ability;
  }

  async attemptsTo(...tasks) {
    const results = [];
    for (const task of tasks) {
      const result = await task.performAs(this);
      results.push(result);
    }
    return results;
  }

  async ask(question) {
    return await question.answeredBy(this);
  }
}

// -----------------------------------------------------------------------------
// Actor 工厂
// -----------------------------------------------------------------------------

/**
 * Admin Actor - 拥有所有能力
 * @param {import('@playwright/test').Page} page
 * @param {Object} helpers - { apiClient, isolation, db }
 */
export const AdminActor = (page, helpers) => {
  return Actor.named('Admin')
    .can(BrowseTheWeb.with(page))
    .can(CallAPI.using(helpers.apiClient))
    .can(IsolateData.using(helpers.isolation));
};

/**
 * Readonly Actor - 只读用户
 */
export const ReadonlyActor = (page, helpers) => {
  return Actor.named('Readonly')
    .can(BrowseTheWeb.with(page))
    .can(CallAPI.using(helpers.apiClient));
};

/**
 * BusinessAnalyst Actor - 业务分析师(读 + 部分写)
 */
export const BusinessAnalystActor = (page, helpers) => {
  return Actor.named('BusinessAnalyst')
    .can(BrowseTheWeb.with(page))
    .can(CallAPI.using(helpers.apiClient))
    .can(IsolateData.using(helpers.isolation));
};

/**
 * DataSteward Actor - 数据管理员(强权限)
 */
export const DataStewardActor = (page, helpers) => {
  return Actor.named('DataSteward')
    .can(BrowseTheWeb.with(page))
    .can(CallAPI.using(helpers.apiClient))
    .can(IsolateData.using(helpers.isolation));
};

// -----------------------------------------------------------------------------
// Ability 占位 (在 ability.js 中实现)
// -----------------------------------------------------------------------------
// 这里只是占位,实际 ability 在 ./ability.js 中定义并 export
import { BrowseTheWeb, CallAPI, IsolateData } from './ability';
