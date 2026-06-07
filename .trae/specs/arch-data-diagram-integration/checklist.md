# Checklist

## 数据转换验证

- [x] convertToCenterScope函数正确转换领域ID为业务对象编码列表
- [x] convertToCenterScope函数正确转换子领域ID为业务对象编码列表
- [x] convertToCenterScope函数正确转换服务模块ID为业务对象编码列表
- [x] convertToCenterScope函数正确转换业务对象ID为编码列表
- [x] buildPreviewDataFromArchData函数正确构建domainProducts
- [x] domainProducts中领域和子领域只使用name属性
- [x] domainProducts中服务模块和业务对象使用code属性
- [x] businessObjects包含完整的层级信息
- [x] relationships正确关联业务对象编码

## 导航控制验证

- [x] Excel导入入口时步骤导航正常工作
- [x] 架构管理跳转入口时步骤0-2显示为已完成状态
- [x] 架构管理跳转入口时步骤0-2点击无效
- [x] 架构管理跳转入口时步骤3为当前步骤
- [x] 架构管理跳转入口时步骤3的"上一步"返回架构管理
- [x] 架构管理跳转入口时步骤4/5的"上一步"正常回退
- [x] 返回架构管理时选择状态正确恢复

## 架构管理页面验证

- [x] "展示图表"按钮正确显示
- [x] 未选择范围时按钮禁用
- [x] 点击按钮后正确跳转到AA图步骤3
- [x] 点击按钮后数据正确初始化

## AA图原有流程验证

- [x] Excel导入入口功能不受影响
- [x] 步骤0-5正常显示和点击
- [x] "上一步"按钮正常回退
- [x] 数据结构和数据流逻辑不变

## UI显示验证

- [x] 禁用步骤显示灰色勾选标记
- [x] 当前步骤高亮显示
- [x] 按钮样式符合设计规范
