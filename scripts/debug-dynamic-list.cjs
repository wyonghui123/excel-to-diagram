/**
 * debug-dynamic-list.cjs - 动态列表调试脚本
 *
 * 运行方式:
 *   node debug-dynamic-list.cjs
 */

const fs = require('fs')
const path = require('path')

const checks = [
  {
    name: '1. 检查 YAML 元数据文件是否存在',
    check: () => {
      const roleYamlPath = path.join(__dirname, '../meta/schemas/role.yaml')
      const userGroupYamlPath = path.join(__dirname, '../meta/schemas/user_group.yaml')

      const results = {
        role: fs.existsSync(roleYamlPath),
        userGroup: fs.existsSync(userGroupYamlPath)
      }

      console.log(`[YAML文件检查] role.yaml: ${results.role ? '✅ 存在' : '❌ 不存在'}`)
      console.log(`[YAML文件检查] user_group.yaml: ${results.userGroup ? '✅ 存在' : '❌ 不存在'}`)

      return results.role && results.userGroup
    }
  },
  {
    name: '2. 检查 YAML 格式是否正确',
    check: () => {
      let yaml
      try {
        yaml = require('js-yaml')
      } catch (e) {
        console.log('[YAML解析] ❌ js-yaml 模块未安装')
        return false
      }

      const files = [
        'meta/schemas/role.yaml',
        'meta/schemas/user_group.yaml'
      ]

      const results = []

      for (const file of files) {
        try {
          const content = fs.readFileSync(path.join(__dirname, '..', file), 'utf8')
          const parsed = yaml.load(content)
          console.log(`[YAML解析] ${file}: ✅ 解析成功`)
          results.push({ file, success: true, parsed })
        } catch (e) {
          console.log(`[YAML解析] ${file}: ❌ 解析失败 - ${e.message}`)
          results.push({ file, success: false, error: e.message })
        }
      }

      return results.every(r => r.success)
    }
  },
  {
    name: '3. 检查 ui_view_config.list.columns 是否定义',
    check: () => {
      let yaml
      try {
        yaml = require('js-yaml')
      } catch (e) {
        console.log('[列定义检查] ❌ js-yaml 模块未安装')
        return false
      }

      const files = [
        { path: 'meta/schemas/role.yaml', name: 'role' },
        { path: 'meta/schemas/user_group.yaml', name: 'user_group' }
      ]

      const results = []

      for (const { path: filePath, name } of files) {
        try {
          const content = fs.readFileSync(path.join(__dirname, '..', filePath), 'utf8')
          const parsed = yaml.load(content)
          const columns = parsed?.ui_view_config?.list?.columns

          if (columns && Array.isArray(columns) && columns.length > 0) {
            console.log(`[列定义检查] ${name}: ✅ ${columns.length} 列`)
            columns.forEach(col => {
              const field = col.field || col.id
              console.log(`   - ${field}: width=${col.width}, sortable=${col.sortable}`)
            })
            results.push({ name, success: true, count: columns.length })
          } else {
            console.log(`[列定义检查] ${name}: ❌ 缺少 columns 定义或为空`)
            console.log(`   ui_view_config: ${JSON.stringify(parsed?.ui_view_config)}`)
            results.push({ name, success: false })
          }
        } catch (e) {
          console.log(`[列定义检查] ${name}: ❌ 错误 - ${e.message}`)
          results.push({ name, success: false, error: e.message })
        }
      }

      return results.every(r => r.success)
    }
  },
  {
    name: '4. 检查后端 meta API 路由是否注册',
    check: () => {
      const apiFile = path.join(__dirname, '../meta/api/bo_api.py')
      const content = fs.readFileSync(apiFile, 'utf8')

      const patterns = [
        { name: 'get_view_config', pattern: /def get_view_config/i },
        { name: 'meta_v2_bp', pattern: /meta_v2_bp/i }
      ]

      const results = []

      for (const { name, pattern } of patterns) {
        const found = pattern.test(content)
        console.log(`[后端API检查] ${name}: ${found ? '✅ 找到' : '❌ 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  },
  {
    name: '5. 检查前端 metaService 是否正确实现',
    check: () => {
      const serviceFile = path.join(__dirname, '../src/services/metaService.js')
      const content = fs.readFileSync(serviceFile, 'utf8')

      const patterns = [
        { name: 'getViewConfig', pattern: /getViewConfig/i },
        { name: '/api/v2/meta', pattern: /\/api\/v2\/meta/i }
      ]

      const results = []

      for (const { name, pattern } of patterns) {
        const found = pattern.test(content)
        console.log(`[前端服务检查] ${name}: ${found ? '✅ 找到' : '❌ 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  },
  {
    name: '6. 检查 useMetaList composable 是否正确实现',
    check: () => {
      const composableFile = path.join(__dirname, '../src/composables/useMetaList.js')
      const content = fs.readFileSync(composableFile, 'utf8')

      const patterns = [
        { name: 'useMetaList', pattern: /export.*useMetaList|function useMetaList/i },
        { name: 'loadList', pattern: /function loadList|const loadList/i },
        { name: '_transformMetaToComponentFormat', pattern: /_transformMetaToComponentFormat/i },
        { name: 'visibleColumns', pattern: /visibleColumns/i }
      ]

      const results = []

      for (const { name, pattern } of patterns) {
        const found = pattern.test(content)
        console.log(`[Composable检查] ${name}: ${found ? '✅ 找到' : '❌ 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  },
  {
    name: '7. 检查 RoleManagement.vue 是否使用 useMetaList',
    check: () => {
      const vueFile = path.join(__dirname, '../src/views/SystemManagement/RoleManagement.vue')
      const content = fs.readFileSync(vueFile, 'utf8')

      const patterns = [
        { name: 'useMetaList import', pattern: /import.*useMetaList.*from.*useMetaList/i },
        { name: 'useMetaList 调用', pattern: /useMetaList\s*\(\s*['"]role['"]/i },
        { name: 'visibleColumns 使用', pattern: /visibleColumns/i },
        { name: 'data 使用', pattern: /\{\s*data\s*\}/i }
      ]

      const results = []

      for (const { name, pattern } of patterns) {
        const found = pattern.test(content)
        console.log(`[RoleManagement检查] ${name}: ${found ? '✅ 找到' : '❌ 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  },
  {
    name: '8. 检查 UserGroupManagement.vue 是否使用 useMetaList',
    check: () => {
      const vueFile = path.join(__dirname, '../src/views/SystemManagement/UserGroupManagement.vue')
      const content = fs.readFileSync(vueFile, 'utf8')

      const patterns = [
        { name: 'useMetaList import', pattern: /import.*useMetaList.*from.*useMetaList/i },
        { name: 'useMetaList 调用', pattern: /useMetaList\s*\(\s*['"]user_group['"]/i },
        { name: 'visibleColumns 使用', pattern: /visibleColumns/i },
        { name: 'data 使用', pattern: /\{\s*data\s*\}/i }
      ]

      const results = []

      for (const { name, pattern } of patterns) {
        const found = pattern.test(content)
        console.log(`[UserGroupManagement检查] ${name}: ${found ? '✅ 找到' : '❌ 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  }
]

async function runDiagnostics() {
  console.log('='.repeat(60))
  console.log('🔍 动态列表诊断工具')
  console.log('='.repeat(60))
  console.log('')

  let allPassed = true

  for (const { name, check } of checks) {
    console.log(`\n${name}`)
    console.log('-'.repeat(50))

    try {
      const result = check()
      if (!result) {
        allPassed = false
      }
    } catch (e) {
      console.log(`❌ 检查出错: ${e.message}`)
      console.log(e.stack)
      allPassed = false
    }
  }

  console.log('\n' + '='.repeat(60))
  if (allPassed) {
    console.log('✅ 所有检查通过!')
  } else {
    console.log('⚠️ 部分检查未通过，请查看上面的输出')
    console.log('\n可能的原因:')
    console.log('1. YAML 文件格式错误或缺少 ui_view_config.list.columns')
    console.log('2. 后端 meta API 路由未正确注册')
    console.log('3. 前端 metaService 或 useMetaList 未正确实现')
    console.log('4. 组件未正确使用 useMetaList composable')
  }
  console.log('='.repeat(60))

  return allPassed
}

runDiagnostics().then(passed => {
  process.exit(passed ? 0 : 1)
})
