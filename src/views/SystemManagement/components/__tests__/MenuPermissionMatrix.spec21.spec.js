/**
 * MenuPermissionMatrix.spec21.spec.js - Spec 21 菜单权限树相关测试
 *
 * 覆盖（PM 反馈 2026-09-12）：
 *   - 第一次：列头副标签灰度色调
 *   - 第二次：实例/对象色深浅区分
 *   - 第三次：来源 tag 无边框
 *   - 第四次：菜单权限树限高分页（pageSize/maxHeight/el-pagination）
 *   - 第五次（最新）：来源 tag 不应被窄 drawer 压扁 → 换行到第二行
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import fs from 'fs'
import path from 'path'

const COMPONENT_PATH = path.resolve(__dirname, '../MenuPermissionMatrix.vue')

describe('Spec 21 MenuPermissionMatrix — 模板渲染', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('pageSize/maxHeight prop 已声明（PM 反馈第四次：限高分页）', () => {
    const tmpl = fs.readFileSync(COMPONENT_PATH, 'utf-8')
    expect(tmpl).toMatch(/pageSize\?:\s*number/)
    expect(tmpl).toMatch(/maxHeight\?:\s*number/)
    // 模板里有用到 el-pagination
    expect(tmpl).toMatch(/el-pagination/)
  })

  it('MenuPermissionMatrix 模板用 :page-size + :max-height 绑定 props（消费者用 props.pageSize / props.maxHeight）', () => {
    const tmpl = fs.readFileSync(COMPONENT_PATH, 'utf-8')
    // props 透传给子模板的 el-pagination / menu-list :style
    expect(tmpl).toMatch(/page-size="props\.pageSize"/)
    expect(tmpl).toMatch(/menuListStyle[^]*maxHeight/i)
  })
})

describe('Spec 21 MenuPermissionMatrix — 来源 tag 单行展示（PM 反馈第七次）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('.menu-card-header 不再 flex-wrap（PM 反馈第七次：单行展示，来源 tag 用 ellipsis 截断）', () => {
    const css = fs.readFileSync(COMPONENT_PATH, 'utf-8')
    // 截取 .menu-card-header {...} 块，去掉注释后断言没有 flex-wrap
    const blockMatch = css.match(/\.menu-card-header\s*\{([\s\S]*?)\n\}/)
    expect(blockMatch).toBeTruthy()
    let block = blockMatch[1].replace(/\/\*[\s\S]*?\*\//g, '')
    expect(block).not.toMatch(/flex-wrap:\s*wrap/)
  })

  it('.menu-source 不再 flex-basis: 100%（回到单行）', () => {
    const css = fs.readFileSync(COMPONENT_PATH, 'utf-8')
    // 截取 .menu-source {...} 块，断言没有 flex-basis: 100%
    const blockMatch = css.match(/\.menu-source\s*\{([\s\S]*?)\n\}/)
    expect(blockMatch).toBeTruthy()
    let block = blockMatch[1].replace(/\/\*[\s\S]*?\*\//g, '')
    expect(block).not.toMatch(/flex-basis:\s*100%/)
  })

  it('.menu-source-label 单行 + ellipsis（PM 反馈第七次：tooltip 兜底）', () => {
    const css = fs.readFileSync(COMPONENT_PATH, 'utf-8')
    const blockMatch = css.match(/\.menu-source-label\s*\{([\s\S]*?)\n\}/)
    expect(blockMatch).toBeTruthy()
    const block = blockMatch[1].replace(/\/\*[\s\S]*?\*\//g, '')
    expect(block).toMatch(/white-space:\s*nowrap/)
    expect(block).toMatch(/overflow:\s*hidden/)
    expect(block).toMatch(/text-overflow:\s*ellipsis/)
  })

  it('.menu-name 单行 + ellipsis（PM 反馈第七次：菜单名太长也截断）', () => {
    const css = fs.readFileSync(COMPONENT_PATH, 'utf-8')
    const blockMatch = css.match(/\.menu-name\s*\{([\s\S]*?)\n\}/)
    expect(blockMatch).toBeTruthy()
    const block = blockMatch[1].replace(/\/\*[\s\S]*?\*\//g, '')
    expect(block).toMatch(/white-space:\s*nowrap/)
    expect(block).toMatch(/overflow:\s*hidden/)
    expect(block).toMatch(/text-overflow:\s*ellipsis/)
  })

  it('.menu-source 嵌套在 .menu-title-area 内（PM 反馈第七次：与菜单名同行展示）', () => {
    const tmpl = fs.readFileSync(COMPONENT_PATH, 'utf-8')
    // .menu-source 应在 .menu-title-area 的开标签之后、闭标签之前
    const titleAreaStart = tmpl.indexOf('class="menu-title-area"')
    const titleAreaEnd = tmpl.indexOf('</div>', titleAreaStart)
    const sourceIdx = tmpl.indexOf('class="menu-source"')
    expect(titleAreaStart).toBeGreaterThan(-1)
    expect(sourceIdx).toBeGreaterThan(titleAreaStart)
    expect(sourceIdx).toBeLessThan(titleAreaEnd)
  })
})
