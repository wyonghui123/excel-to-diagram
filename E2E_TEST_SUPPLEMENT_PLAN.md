# E2E 测试补充计划

**生成时间**: 2026-05-21  
**目的**: 覆盖所有核心业务对象的界面交互测试

---

## 📊 当前覆盖分析

### 核心业务对象（共 17 个）

| 业务对象 | 当前测试文件 | 覆盖状态 | 建议优先级 |
|----------|-------------|----------|----------|
| **产品线 (Product)** | product-version.spec.js | ⚠️ 部分 | P1 |
| **版本 (Version)** | product-version.spec.js | ⚠️ 部分 | P1 |
| **领域 (Domain)** | arch-data-manage.spec.js | ⚠️ 部分 | P2 |
| **子领域 (SubDomain)** | arch-data-manage.spec.js | ⚠️ 部分 | P2 |
| **服务模块 (ServiceModule)** | core-object-verification.spec.js | ✅ 已覆盖 | - |
| **业务对象 (BusinessObject)** | core-object-verification.spec.js | ✅ 已覆盖 | - |
| **关系 (Relationship)** | relationship-management.spec.js | ✅ 已覆盖 | - |
| **用户 (User)** | user-management*.spec.js | ✅ 已覆盖 | - |
| **角色 (Role)** | role-management*.spec.js | ✅ 已覆盖 | - |
| **用户组 (UserGroup)** | user-group-management*.spec.js | ✅ 已覆盖 | - |
| **枚举类型 (EnumType)** | enum-type-management.spec.js | ✅ 已覆盖 | - |
| **数据权限 (DataPermission)** | data-permission*.spec.js | ✅ 已覆盖 | - |
| **菜单权限 (MenuPermission)** | menu-permission.spec.js | ✅ 已覆盖 | - |
| **审计日志 (AuditLog)** | audit-log*.spec.js | ✅ 已覆盖 | - |
| **备注 (Annotation)** | annotation-metadata.spec.js | ✅ 已覆盖 | - |
| **角色权限 (RolePermission)** | permission-management.spec.js | ✅ 已覆盖 | - |
| **关联关系 (Association)** | association-metadata.spec.js | ✅ 已覆盖 | - |

### 层级结构

```
产品线 (Product)
└── 版本 (Version)
    └── 领域 (Domain)
        └── 子领域 (SubDomain)
            └── 服务模块 (ServiceModule)
                └── 业务对象 (BusinessObject)
                    └── 关系 (Relationship)
```

---

## 🎯 测试补充计划

### 第一阶段：核心 CRUD 完整测试（P1）

#### 1. 产品线管理 (Product) - 完整测试
**当前问题**: 只测试了详情页，未测试列表页 CRUD

**需要补充的测试用例**:
- [ ] `product-management.spec.js` (新建)

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-PROD-001 | 产品线列表加载 | 登录 → 导航到产品线管理 → 等待表格加载 | 显示产品线列表 |
| TC-PROD-002 | 创建新产品线 | 点击"新建" → 填写表单 → 点击保存 | 创建成功并刷新列表 |
| TC-PROD-003 | 编辑产品线 | 选择产品线 → 点击编辑 → 修改名称 → 保存 | 修改成功 |
| TC-PROD-004 | 删除产品线 | 选择无版本的产品线 → 点击删除 → 确认 | 删除成功 |
| TC-PROD-005 | 删除有版本的产品线 | 选择有版本的产品线 → 点击删除 | 提示"存在版本的产品不能删除" |
| TC-PROD-006 | 搜索产品线 | 在搜索框输入关键词 | 过滤显示匹配结果 |
| TC-PROD-007 | 导出产品线 | 点击导出按钮 | 下载 Excel 文件 |

#### 2. 版本管理 (Version) - 完整测试
**需要补充的测试用例**:

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-VER-001 | 版本列表加载 | 登录 → 导航到产品线 → 选择产品 → 查看版本 | 显示版本列表 |
| TC-VER-002 | 创建新版本 | 选择产品线 → 点击"新建版本" → 填写表单 → 保存 | 版本创建成功 |
| TC-VER-003 | 编辑版本 | 选择版本 → 点击编辑 → 修改信息 → 保存 | 修改成功 |
| TC-VER-004 | 删除版本 | 选择无领域的版本 → 点击删除 → 确认 | 删除成功 |
| TC-VER-005 | 设为当前版本 | 选择非当前版本 → 点击"设为当前" | 当前版本标记更新 |
| TC-VER-006 | 版本依赖关系 | 尝试删除被引用的版本 | 提示依赖错误 |

### 第二阶段：层级导航测试（P2）

#### 3. 架构数据管理 - 完整层级导航
**当前问题**: 只测试了页面加载，未测试层级导航

**需要补充的测试用例**:

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-ARCH-001 | 产品线选择器 | 访问架构数据 → 打开产品线选择器 | 显示产品线列表 |
| TC-ARCH-002 | 版本选择器 | 选择产品线 → 版本选择器自动加载 | 显示该产品的版本 |
| TC-ARCH-003 | 领域选择器 | 选择版本 → 领域选择器自动加载 | 显示该版本的领域 |
| TC-ARCH-004 | 子领域选择器 | 选择领域 → 子领域选择器自动加载 | 显示该领域的子领域 |
| TC-ARCH-005 | 服务模块选择器 | 选择子领域 → 服务模块选择器加载 | 显示该子领域的服务模块 |
| TC-ARCH-006 | 业务对象列表 | 选择服务模块 → 右侧显示业务对象 | 显示该服务模块的业务对象 |
| TC-ARCH-007 | 面包屑导航 | 进入深层页面 → 点击面包屑 | 跳转到对应层级 |
| TC-ARCH-008 | 层级刷新 | 选择产品线 → 刷新页面 | 保持当前层级状态 |

### 第三阶段：通用功能测试（P2）

#### 4. 表格通用功能测试
**所有列表页的通用功能**

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-TABLE-001 | 分页导航 | 进入列表页 → 点击下一页 | 加载下一页数据 |
| TC-TABLE-002 | 分页跳转 | 输入页码 → 点击跳转 | 跳转到指定页 |
| TC-TABLE-003 | 每页条数 | 选择"每页 50 条" | 显示 50 条记录 |
| TC-TABLE-004 | 列排序 | 点击列头排序按钮 | 按该列排序 |
| TC-TABLE-005 | 多列排序 | 按住 Shift 点击多列 | 按多列排序 |
| TC-TABLE-006 | 搜索过滤 | 输入搜索关键词 | 实时过滤结果 |
| TC-TABLE-007 | 高级搜索 | 打开高级搜索 → 设置条件 → 搜索 | 显示符合条件的结果 |
| TC-TABLE-008 | 清除搜索 | 输入搜索词 → 点击清除 | 显示全部数据 |
| TC-TABLE-009 | 列宽调整 | 拖动列头分隔线 | 列宽调整 |
| TC-TABLE-010 | 列排序拖动 | 拖动列头 | 列顺序调整 |
| TC-TABLE-011 | 列显示隐藏 | 打开列设置 → 隐藏某列 | 该列不显示 |
| TC-TABLE-012 | 刷新按钮 | 点击刷新按钮 | 重新加载数据 |
| TC-TABLE-013 | 全选操作 | 点击全选 → 选择多项 | 批量操作按钮可用 |
| TC-TABLE-014 | 行选择 | 点击行checkbox | 行被选中 |

#### 5. 表单通用功能测试
**所有表单的通用功能**

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-FORM-001 | 必填字段验证 | 提交空表单 | 提示必填字段 |
| TC-FORM-002 | 字段格式验证 | 输入错误格式 | 提示格式错误 |
| TC-FORM-003 | 唯一性验证 | 输入已存在的编码 | 提示"编码已存在" |
| TC-FORM-004 | 下拉选择器 | 点击下拉框 → 选择选项 | 选项被选中 |
| TC-FORM-005 | 级联下拉 | 选择上级 → 下级自动加载 | 下级选项更新 |
| TC-FORM-006 | 日期选择器 | 打开日期选择器 → 选择日期 | 日期被设置 |
| TC-FORM-007 | 富文本编辑器 | 在富文本框输入 | 内容格式化显示 |
| TC-FORM-008 | 文件上传 | 上传文件 | 显示文件名和大小 |
| TC-FORM-009 | 表单重置 | 填写表单 → 点击重置 | 表单清空 |
| TC-FORM-010 | 取消保存 | 填写表单 → 点击取消 → 确认离开 | 不保存并离开 |

### 第四阶段：详情页功能测试（P2）

#### 6. 详情页通用功能
**所有详情页的通用功能**

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-DETAIL-001 | 基本信息显示 | 打开详情页 | 显示所有基本信息 |
| TC-DETAIL-002 | 编辑基本信息 | 点击编辑 → 修改字段 → 保存 | 信息更新 |
| TC-DETAIL-003 | 子对象列表 | 查看有子对象的数据 | 显示子对象列表 |
| TC-DETAIL-004 | 子对象分页 | 子对象列表分页 | 分页功能正常 |
| TC-DETAIL-005 | 子对象搜索 | 在子对象列表搜索 | 过滤子对象 |
| TC-DETAIL-006 | 变更历史 | 查看变更历史 Tab | 显示修改记录 |
| TC-DETAIL-007 | 关联关系展示 | 查看有关联的数据 | 显示关联面板 |
| TC-DETAIL-008 | 复制功能 | 点击复制按钮 | 复制数据并打开表单 |
| TC-DETAIL-009 | 导出详情 | 点击导出 | 下载详情 Excel |

### 第五阶段：高级功能测试（P3）

#### 7. 导入导出测试

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-IMP-001 | 单个导入 | 选择 Excel → 上传 → 解析预览 → 确认 | 导入成功 |
| TC-IMP-002 | 批量导入 | 选择多个对象 → 批量导入 → 解析预览 → 确认 | 批量导入成功 |
| TC-IMP-003 | 导入冲突处理 | 导入已存在的数据 → 选择覆盖策略 | 按策略处理冲突 |
| TC-IMP-004 | 导入模板下载 | 点击下载模板 | 下载空白模板 |
| TC-IMP-005 | 导入错误提示 | 导入格式错误的文件 | 提示具体错误 |
| TC-EXP-001 | 单个导出 | 选择数据 → 点击导出 | 导出选中数据 |
| TC-EXP-002 | 批量导出 | 选择多个 → 导出 | 导出所有选中数据 |
| TC-EXP-003 | 条件导出 | 设置导出条件 → 导出 | 导出符合条件的数据 |

#### 8. 关系管理测试

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-REL-001 | 创建关系 | 打开业务对象 → 添加关系 → 选择目标 | 关系创建成功 |
| TC-REL-002 | 查看关系图 | 打开关系管理 | 显示关系可视化 |
| TC-REL-003 | 删除关系 | 选择关系 → 点击删除 → 确认 | 关系删除成功 |
| TC-REL-004 | 关系双向性 | 创建 A→B 关系 | 自动显示 B←A |
| TC-REL-005 | 关系约束验证 | 创建违反约束的关系 | 提示约束错误 |

#### 9. 权限测试

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-AUTH-001 | 无权限访问 | 以普通用户登录 → 访问无权限页面 | 显示无权限提示 |
| TC-AUTH-002 | 权限继承 | 子对象继承父对象权限 | 按继承规则显示 |
| TC-AUTH-003 | 权限转移 | 管理员转移对象权限 | 权限转移成功 |
| TC-AUTH-004 | 数据权限过滤 | 按数据权限查看列表 | 只显示有权限的数据 |
| TC-AUTH-005 | 菜单权限控制 | 按角色显示菜单 | 只显示有权限的菜单 |

#### 10. 通知和提醒测试

| 测试用例 ID | 测试内容 | 操作步骤 | 预期结果 |
|------------|---------|---------|---------|
| TC-NOTIFY-001 | 创建通知 | 创建对象 → 查看通知 | 收到创建通知 |
| TC-NOTIFY-002 | 更新通知 | 更新对象 → 查看通知 | 收到更新通知 |
| TC-NOTIFY-003 | 删除通知 | 删除对象 → 查看通知 | 收到删除通知 |
| TC-NOTIFY-004 | 未读标记 | 点击标记已读 | 通知状态更新 |

---

## 📈 测试用例统计

| 阶段 | 描述 | 用例数 | 优先级 |
|------|------|--------|--------|
| 第一阶段 | 核心 CRUD 完整测试 | 13 | P1 |
| 第二阶段 | 层级导航测试 | 8 | P2 |
| 第三阶段 | 通用功能测试 | 27 | P2 |
| 第四阶段 | 详情页功能测试 | 9 | P2 |
| 第五阶段 | 高级功能测试 | 19 | P3 |
| **总计** | | **76** | |

---

## 📝 实施建议

### 1. 创建新测试文件的命名规范

```
e2e/
├── product-management.spec.js      # 产品线完整测试
├── version-management.spec.js     # 版本完整测试
├── arch-hierarchy-navigation.spec.js  # 层级导航测试
├── table-common-functions.spec.js    # 表格通用功能
├── form-common-functions.spec.js     # 表单通用功能
├── detail-page-functions.spec.js     # 详情页通用功能
├── import-export.spec.js            # 导入导出测试
├── relation-management.spec.js      # 关系管理测试
├── permission-advanced.spec.js       # 高级权限测试
└── notification.spec.js            # 通知测试
```

### 2. 测试辅助函数

建议创建 `e2e/helpers/` 目录存放通用辅助函数：

```javascript
// e2e/helpers/table-helpers.js
export async function sortByColumn(page, columnName) { ... }
export async function searchTable(page, keyword) { ... }
export async function goToPage(page, pageNum) { ... }

// e2e/helpers/form-helpers.js
export async function fillForm(page, data) { ... }
export async function submitForm(page) { ... }
export async function resetForm(page) { ... }
export async function validateField(page, fieldName, expectedError) { ... }

// e2e/helpers/navigation-helpers.js
export async function selectProductLine(page, name) { ... }
export async function selectVersion(page, name) { ... }
export async function selectDomain(page, name) { ... }
```

### 3. 测试数据管理

在 `e2e/fixtures/` 目录管理测试数据：

```javascript
// e2e/fixtures/test-data.js
export const testData = {
  products: [
    { name: '测试产品A', code: 'TEST_A' },
    { name: '测试产品B', code: 'TEST_B' },
  ],
  versions: [
    { name: 'V1.0', code: 'V1_0' },
  ],
  // ...
}
```

### 4. 批量执行脚本

创建批量执行脚本：

```javascript
// scripts/run-e2e-batch.js
const testFiles = [
  'e2e/product-management.spec.js',
  'e2e/version-management.spec.js',
  'e2e/arch-hierarchy-navigation.spec.js',
  // ...
];

// 执行所有核心测试
// npx playwright test ${testFiles.join(' ')} --reporter=list
```

---

## ✅ 检查清单

- [ ] 创建 `product-management.spec.js`
- [ ] 创建 `version-management.spec.js`
- [ ] 创建 `arch-hierarchy-navigation.spec.js`
- [ ] 创建 `table-common-functions.spec.js`
- [ ] 创建 `form-common-functions.spec.js`
- [ ] 创建 `detail-page-functions.spec.js`
- [ ] 创建 `import-export.spec.js`
- [ ] 创建 `relation-management.spec.js`
- [ ] 创建 `permission-advanced.spec.js`
- [ ] 创建 `notification.spec.js`
- [ ] 创建 `e2e/helpers/` 目录和辅助函数
- [ ] 创建 `e2e/fixtures/` 测试数据
- [ ] 运行所有新增测试
- [ ] 更新 E2E_TEST_REPORT.md
