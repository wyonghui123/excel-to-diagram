/**
 * useMetaList.removeNewRow 单元测试
 *
 * 背景 (2026-06-13):
 * - 用户报错: 在产品详情页版本子列表点 + 新增版本, 未填字段, 选中该行点删除 → UI 错误 (500)
 * - 根因: MetaListPage.executeDelete 直接调 boService.delete('version', '__new_xxx') 触发 404/500
 * - 修复: 新增 useMetaList.removeNewRow API + MetaListPage.executeDelete 走本地移除
 *
 * 测试覆盖 (3 个行为契约):
 *   1. useMetaList 必须暴露 removeNewRow 函数
 *   2. removeNewRow 内部实现: _isNew=true / __new_ 前缀 → 本地移除
 *   3. 拒绝删除已保存行 (id 不是临时) - 防误删
 *   4. MetaListPage.executeDelete 优先调用 removeNewRow (对 _isNew 行)
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const useMetaListPath = resolve(__dirname, '../useMetaList.js')
const useMetaListSource = readFileSync(useMetaListPath, 'utf-8')

const metaListPagePath = resolve(__dirname, '../../components/common/MetaListPage/MetaListPage.vue')
const metaListPageSource = readFileSync(metaListPagePath, 'utf-8')

const filterRowActionsPath = resolve(__dirname, '../../services/metaTransformService.js')
const filterRowActionsSource = readFileSync(filterRowActionsPath, 'utf-8')

describe('useMetaList.removeNewRow (2026-06-13 BUG 修复)', () => {
  describe('API 暴露', () => {
    it('useMetaList.js 必须定义 removeNewRow 函数', () => {
      expect(useMetaListSource).toMatch(/function\s+removeNewRow\s*\(/)
    })

    it('useMetaList.js 的 return 中必须暴露 removeNewRow', () => {
      // 简化: 直接看 addNewRow 后面是否紧跟 removeNewRow
      expect(useMetaListSource).toMatch(/addNewRow,?\s*\n\s*removeNewRow,?/)
    })
  })

  describe('removeNewRow 内部实现契约', () => {
    // 提取 removeNewRow 函数体 - 用更宽容的 regex (匹配到下一个空行 \n\n 或 同样缩进的 \n  }  )
    const fnBodyMatch = useMetaListSource.match(/function\s+removeNewRow\s*\(rowId\)\s*\{[\s\S]*?return true\s*\n\s\s\}/)
    const fnBody = fnBodyMatch ? fnBodyMatch[0] : ''

    it('应能找到 removeNewRow 函数体', () => {
      expect(fnBody, '应能找到 removeNewRow 函数体').not.toBe('')
    })

    it('检查 _isNew 标记 (targetRow._isNew === true)', () => {
      expect(fnBody, '应检查 _isNew === true').toMatch(/\._isNew\s*===\s*true/)
    })

    it('检查 __new_ 前缀 (String(id).startsWith("__new_"))', () => {
      expect(fnBody, '应检查 id 以 __new_ 开头').toMatch(/startsWith\(['"]__new_['"]\)/)
    })

    it('拒绝删除已保存行 (返回 false)', () => {
      expect(fnBody, '非新行应返回 false').toMatch(/if\s*\(\s*!isNew\s*\)\s*return\s+false/)
    })

    it('清理 draftValues 中的临时行', () => {
      expect(fnBody, '应从 draftValues 清理临时行').toMatch(/draftValues\.value\.delete/)
    })

    it('从 data 数组中过滤掉临时行', () => {
      expect(fnBody, '应从 data 过滤掉').toMatch(/data\.value\s*=\s*data\.value\.filter/)
    })

    it('返回 boolean (true=已删除)', () => {
      expect(fnBody, '应返回 true').toMatch(/return\s+true/)
    })
  })

  describe('MetaListPage.executeDelete 集成契约', () => {
    // 提取 executeDelete 函数体 (直到 try 块结束 / 函数结束)
    const fnMatch = metaListPageSource.match(/async\s+function\s+executeDelete\s*\(\)\s*\{[\s\S]*?finally\s*\{[\s\S]*?\}\s*\n\s\s\}/)
    const fnBody = fnMatch ? fnMatch[0] : ''

    it('应能找到 executeDelete 函数体', () => {
      expect(fnBody, '应能找到 executeDelete').not.toBe('')
    })

    it('executeDelete 必须先判断 _isNew (行级短路)', () => {
      expect(fnBody, '应判断 _isNew === true').toMatch(/deleteTargetRow\.value\._isNew\s*===\s*true/)
      expect(fnBody, '应判断 id 以 __new_ 开头').toMatch(/startsWith\(['"]__new_['"]\)/)
    })

    it('executeDelete 对新行应调 removeNewRow (而非 boService.delete)', () => {
      // 找到 isNewRow 分支 (if (isNewRow) { ... })
      const isNewBranch = fnBody.match(/if\s*\(\s*isNewRow\s*\)\s*\{[\s\S]*?\n\s\s\}/)
      expect(isNewBranch, '应有 isNewRow 分支').not.toBeNull()
      // 新行分支必须先调 removeNewRow
      expect(isNewBranch[0], '新行分支应调 removeNewRow').toMatch(/removeNewRow\(/)
      // 不调后端: 显式断言 isNewRow 分支必须有 early return
      expect(isNewBranch[0], '新行分支应有 early return').toMatch(/return/)
    })

    it('executeDelete 必须从 useMetaList 解构 removeNewRow', () => {
      // 找到 useMetaList 解构块 (function 内部最外层)
      const destructBlock = metaListPageSource.match(/\{\s*[\s\S]*?\}\s*=\s*useMetaList\(/)
      expect(destructBlock, '应能找到 useMetaList 解构').not.toBeNull()
      expect(destructBlock[0], '解构中应包含 removeNewRow').toMatch(/removeNewRow/)
    })
  })

  describe('filterRowActions 集成契约 (新行动作过滤)', () => {
    it('filterRowActions 必须对新行隐藏 delete/edit/update 动作', () => {
      // 找到 filterRowActions 函数
      const fnMatch = filterRowActionsSource.match(/export\s+function\s+filterRowActions\s*\([\s\S]*?\n\}/)
      expect(fnMatch, '应能找到 filterRowActions 函数').not.toBeNull()
      const fnBody = fnMatch[0]
      // 应有 _isNew / __new_ 判断
      expect(fnBody, '应判断 _isNew').toMatch(/row\._isNew\s*===\s*true/)
      expect(fnBody, '应判断 __new_ 前缀').toMatch(/startsWith\(['"]__new_['"]\)/)
      // 应过滤 delete/edit/update
      const newRowBranch = fnBody.match(/row\s*&&\s*\([\s\S]*?startsWith\([\s\S]*?\)\s*\)\s*\{[\s\S]*?\n\s\s\}/)
      expect(newRowBranch, '应能找到新行分支').not.toBeNull()
      const branchBody = newRowBranch[0]
      expect(branchBody, '新行应隐藏 delete').toMatch(/['"]delete['"]/)
      expect(branchBody, '新行应隐藏 edit').toMatch(/['"]edit['"]/)
      expect(branchBody, '新行应隐藏 update').toMatch(/['"]update['"]/)
    })
  })
})
