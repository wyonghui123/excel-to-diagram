/**
 * Screenplay Pattern - 单元测试
 *
 * 测试 Actor / Ability / Interactions / BusinessRuleAssertor
 */

import { describe, it, expect, vi } from 'vitest';
import { Actor, AdminActor } from '../actor.js';
import { BrowseTheWeb, CallAPI, IsolateData } from '../ability.js';
import { Click, Fill, Navigate, Wait, Select, PressKey } from '../interactions/index.js';
import { BusinessRuleAssertor, BusinessAssertionError } from '../questions/BusinessRuleAssertor.js';
import { CanBeDeleted, KeyTemplateApplied, CascadeOptionsValid, UserAuthorized } from '../questions/BusinessQuestions.js';

// ============================================================================
// Actor 测试
// ============================================================================

describe('Actor', () => {
  it('应该能创建命名 Actor', () => {
    const actor = Actor.named('TestUser');
    expect(actor.name).toBe('TestUser');
    expect(actor.abilities).toEqual({});
  });

  it('应该能赋予能力', () => {
    const actor = Actor.named('TestUser');
    const page = { dummy: true };
    actor.can(BrowseTheWeb.with(page));
    expect(actor.abilities['BrowseTheWeb']).toBeDefined();
    expect(actor.abilityTo('BrowseTheWeb').page).toBe(page);
  });

  it('应该能链式赋予能力', () => {
    const actor = Actor.named('TestUser');
    const ability = BrowseTheWeb.with({});
    const result = actor.can(ability);
    expect(result).toBe(actor);
  });

  it('访问不存在的能力应该报错', () => {
    const actor = Actor.named('TestUser');
    expect(() => actor.abilityTo('NonExistent')).toThrow(/no ability/);
  });

  it('应该能执行多个任务', async () => {
    const actor = Actor.named('TestUser');
    actor.can(BrowseTheWeb.with({}));

    const task1 = { performAs: vi.fn().mockResolvedValue('r1') };
    const task2 = { performAs: vi.fn().mockResolvedValue('r2') };

    const results = await actor.attemptsTo(task1, task2);
    expect(results).toEqual(['r1', 'r2']);
    expect(task1.performAs).toHaveBeenCalledWith(actor);
    expect(task2.performAs).toHaveBeenCalledWith(actor);
  });

  it('应该能询问', async () => {
    const actor = Actor.named('TestUser');
    const question = { answeredBy: vi.fn().mockResolvedValue('answer') };
    const result = await actor.ask(question);
    expect(result).toBe('answer');
    expect(question.answeredBy).toHaveBeenCalledWith(actor);
  });
});

describe('Actor Factories', () => {
  it('AdminActor 应该返回名为 Admin 的 Actor', () => {
    const page = { dummy: true };
    const helpers = { apiClient: {}, isolation: {} };
    const actor = AdminActor(page, helpers);
    expect(actor.name).toBe('Admin');
    expect(actor.abilityTo('BrowseTheWeb').page).toBe(page);
    expect(actor.abilityTo('CallAPI').client).toBe(helpers.apiClient);
  });
});

// ============================================================================
// Ability 测试
// ============================================================================

describe('BrowseTheWeb', () => {
  it('应该能用 with 创建', () => {
    const page = { name: 'page' };
    const ability = BrowseTheWeb.with(page);
    expect(ability.page).toBe(page);
  });
});

describe('CallAPI', () => {
  it('应该调用 client 方法', async () => {
    const client = {
      get: vi.fn().mockResolvedValue({ data: 1 }),
      post: vi.fn().mockResolvedValue({ id: 1 }),
      delete: vi.fn().mockResolvedValue({ ok: true }),
    };
    const api = CallAPI.using(client);
    expect(await api.get('/x')).toEqual({ data: 1 });
    expect(await api.post('/x', {})).toEqual({ id: 1 });
    expect(await api.delete('/x')).toEqual({ ok: true });
  });
});

// ============================================================================
// Interactions 测试
// ============================================================================

describe('Interactions', () => {
  it('Click.on 应该能构造点击选择器', () => {
    const click = Click.on('button.save');
    expect(click.selector).toBe('button.save');
  });

  it('Fill.the().with() 应该能链式构造', () => {
    const fill = Fill.the('name').with('value');
    expect(fill.field).toBe('name');
    expect(fill.value).toBe('value');
  });

  it('Navigate.to 应该能构造 URL', () => {
    const nav = Navigate.to('/path');
    expect(nav.url).toBe('/path');
  });

  it('Wait.for 应该能构造选择器', () => {
    const wait = Wait.for('.element', { timeout: 3000 });
    expect(wait.selector).toBe('.element');
    expect(wait.options.timeout).toBe(3000);
  });

  it('PressKey 应该能提供常用键快捷方式', () => {
    expect(PressKey.escape().key).toBe('Escape');
    expect(PressKey.enter().key).toBe('Enter');
    expect(PressKey.tab().key).toBe('Tab');
  });

  it('Interactions 应该能真实执行(模拟 page)', async () => {
    const page = {
      click: vi.fn(),
      fill: vi.fn(),
      goto: vi.fn(),
      waitForSelector: vi.fn(),
      selectOption: vi.fn(),
      hover: vi.fn(),
      keyboard: { press: vi.fn() },
    };
    const actor = Actor.named('Test').can(BrowseTheWeb.with(page));

    await Click.on('.btn').performAs(actor);
    expect(page.click).toHaveBeenCalledWith('.btn');

    await Fill.the('name').with('value').performAs(actor);
    expect(page.fill).toHaveBeenCalled();

    await Navigate.to('/home').performAs(actor);
    expect(page.goto).toHaveBeenCalledWith('/home');
  });
});

// ============================================================================
// BusinessRuleAssertor 测试
// ============================================================================

describe('BusinessRuleAssertor', () => {
  // 由于 assertRule 依赖 _index.json 文件,这里测试错误情况
  it('找不到规则应该报错', async () => {
    await expect(
      BusinessRuleAssertor.assertRule('BR-NON-EXISTENT', {})
    ).rejects.toThrow();
  });
});

describe('BusinessAssertionError', () => {
  it('应该是 Error 的子类', () => {
    const err = new BusinessAssertionError(
      'BR-test',
      'test message',
      { ruleType: 'deletability' }
    );
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe('BusinessAssertionError');
    expect(err.ruleId).toBe('BR-test');
    expect(err.isBusinessAssertion).toBe(true);
  });
});

// ============================================================================
// Questions 测试
// ============================================================================

describe('BusinessQuestions', () => {
  it('CanBeDeleted 构造', () => {
    const q = CanBeDeleted.of({ id: 'bo_001' });
    expect(q.businessObject).toEqual({ id: 'bo_001' });
  });

  it('KeyTemplateApplied 构造', () => {
    const q = KeyTemplateApplied.for({ code: 'SM0101', serviceModuleCode: 'SM01' });
    expect(q.params.code).toBe('SM0101');
  });
});
