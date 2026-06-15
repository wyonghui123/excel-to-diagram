/**
 * Screenplay Pattern - Interactions
 *
 * 基础 UI 交互(原子操作),不表达业务意图。
 * 业务流应使用 ./tasks/* 组合这些 interactions。
 */

/**
 * Click - 点击元素
 * @example Click.on('[data-testid="save"]')
 */
export class Click {
  constructor(selector) {
    this.selector = selector;
  }

  static on(selector) {
    return new Click(selector);
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    await page.click(this.selector);
  }
}

/**
 * Fill - 填写输入
 * @example Fill.the('name').with('客户订单')
 */
export class Fill {
  constructor(field, value) {
    this.field = field;
    this.value = value;
  }

  static the(field) {
    return new Fill(field, undefined);
  }

  with(value) {
    this.value = value;
    return this;
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    // field 可以是 name 属性、data-testid 或 selector
    const selector = `[name="${this.field}"], [data-testid="${this.field}"], #${this.field}`;
    await page.fill(selector, this.value);
  }
}

/**
 * Select - 选择下拉
 */
export class Select {
  constructor(field, value) {
    this.field = field;
    this.value = value;
  }

  static from(field) {
    return new Select(field, undefined);
  }

  withValue(value) {
    this.value = value;
    return this;
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    const selector = `[name="${this.field}"], [data-testid="${this.field}"]`;
    await page.selectOption(selector, this.value);
  }
}

/**
 * Hover - 悬停
 */
export class Hover {
  constructor(selector) {
    this.selector = selector;
  }

  static on(selector) {
    return new Hover(selector);
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    await page.hover(this.selector);
  }
}

/**
 * Wait - 等待元素
 */
export class Wait {
  constructor(selector, options = {}) {
    this.selector = selector;
    this.options = options;
  }

  static for(selector, options) {
    return new Wait(selector, options);
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    await page.waitForSelector(this.selector, this.options);
  }
}

/**
 * Navigate - 导航到 URL
 */
export class Navigate {
  constructor(url) {
    this.url = url;
  }

  static to(url) {
    return new Navigate(url);
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    await page.goto(this.url);
  }
}

/**
 * PressKey - 按键
 */
export class PressKey {
  constructor(key) {
    this.key = key;
  }

  static escape() {
    return new PressKey('Escape');
  }

  static enter() {
    return new PressKey('Enter');
  }

  static tab() {
    return new PressKey('Tab');
  }

  static key(key) {
    return new PressKey(key);
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page;
    await page.keyboard.press(this.key);
  }
}
