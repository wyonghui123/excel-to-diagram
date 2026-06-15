/**
 * 业务 Questions - 高层 API
 *
 * Question 表达业务疑问,由 Actor 询问后得到答案。
 * 通常包装 BusinessRuleAssertor,提供更业务化的语义。
 */

import { BusinessRuleAssertor, BusinessAssertionError } from './BusinessRuleAssertor';

/**
 * 业务对象可被删除?
 */
export class CanBeDeleted {
  static of(businessObject) {
    return new CanBeDeleted(businessObject);
  }

  constructor(businessObject) {
    this.businessObject = businessObject;
    this.ruleId = null; // 由调用方注入
  }

  withRuleId(ruleId) {
    this.ruleId = ruleId;
    return this;
  }

  async answeredBy(actor) {
    const api = actor.abilityTo('CallAPI');
    const ruleId = this.ruleId || `BR-${this.businessObject.type || 'business_object'}-DEL-condition`;
    return await BusinessRuleAssertor.assertRule(ruleId, {
      businessObject: this.businessObject,
      apiClient: api.client,
    });
  }
}

/**
 * 业务对象 key 已自动填充?
 */
export class KeyTemplateApplied {
  static for({ code, serviceModuleCode, pattern }) {
    return new KeyTemplateApplied({ code, serviceModuleCode, pattern });
  }

  constructor(params) {
    this.params = params;
  }

  withRuleId(ruleId) {
    this.ruleId = ruleId;
    return this;
  }

  async answeredBy(actor) {
    const ruleId = this.ruleId || `BR-${this.params.objectType || 'business_object'}-KEY`;
    return await BusinessRuleAssertor.assertRule(ruleId, this.params);
  }
}

/**
 * 级联下拉选项符合?
 */
export class CascadeOptionsValid {
  static of({ field, options, expectedCount, parentValue }) {
    return new CascadeOptionsValid({ field, options, expectedCount, parentValue });
  }

  constructor(params) {
    this.params = params;
  }

  withRuleId(ruleId) {
    this.ruleId = ruleId;
    return this;
  }

  async answeredBy(actor) {
    const ruleId = this.ruleId || `BR-business_object-CS-${this.params.field}`;
    return await BusinessRuleAssertor.assertRule(ruleId, this.params);
  }
}

/**
 * 用户已授权?
 */
export class UserAuthorized {
  static for({ userId, resourceId, status }) {
    return new UserAuthorized({ userId, resourceId, status });
  }

  constructor(params) {
    this.params = params;
  }

  withRuleId(ruleId) {
    this.ruleId = ruleId;
    return this;
  }

  async answeredBy(actor) {
    const ruleId = this.ruleId || `BR-business_object-AUTH`;
    return await BusinessRuleAssertor.assertRule(ruleId, {
      authorized: this.params.authorized !== false,
      ...this.params,
    });
  }
}

export { BusinessAssertionError };
