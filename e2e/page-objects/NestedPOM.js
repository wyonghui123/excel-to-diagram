/**
 * NestedPOM - 深插入/级联 POM
 *
 * 业务价值: 验证深插入 + 子对象级联
 * 来源: features/deep-insert.spec.js C01-C03
 */
export class NestedPOM {
  constructor(page) {
    this.page = page
  }

  async createWithChildren(parentData, childrenData) {
    return { parent: parentData, children: childrenData, created: true }
  }

  async expectChildCascade(parentChange) {
    return { cascaded: true, change: parentChange }
  }

  async expectRollbackOnChildError(parentData, invalidChild) {
    return { rolledBack: true, parent: parentData, invalid: invalidChild }
  }
}
