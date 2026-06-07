/**
 * debug-dynamic-list.js - 动态列表调试脚本
 *
 * 运行方式:
 *   node debug-dynamic-list.js
 *
 * 或在浏览器控制台中运行检查函数
 */

const DEBUG_MODE = true

const checks = [
  {
    name: '1. 检查 YAML 元数据文件是否存在',
    check: async () => {
      const fs = require('fs')
      const path = require('path')
      const roleYamlPath = path.join(__dirname, 'meta/schemas/role.yaml')
      const userGroupYamlPath = path.join(__dirname, 'meta/schemas/user_group.yaml')

      const results = {
        role: fs.existsSync(roleYamlPath),
        userGroup: fs.existsSync(userGroupYamlPath)
      }

      console.log(`[YAML文件检查] role.yaml: ${results.role ? '[OK] 存在' : '[X] 不存在'}`)
      console.log(`[YAML文件检查] user_group.yaml: ${results.userGroup ? '[OK] 存在' : '[X] 不存在'}`)

      return results.role && results.userGroup
    }
  },
  {
    name: '2. 检查 YAML 格式是否正确',
    check: async () => {
      const fs = require('fs')
      const yaml = require('js-yaml')
      const path = require('path')

      const files = [
        'meta/schemas/role.yaml',
        'meta/schemas/user_group.yaml'
      ]

      const results = []

      for (const file of files) {
        try {
          const content = fs.readFileSync(path.join(__dirname, file), 'utf8')
          const parsed = yaml.load(content)
          console.log(`[YAML解析] ${file}: [OK] 解析成功`)
          results.push({ file, success: true, parsed })
        } catch (e) {
          console.log(`[YAML解析] ${file}: [X] 解析失败 - ${e.message}`)
          results.push({ file, success: false, error: e.message })
        }
      }

      return results.every(r => r.success)
    }
  },
  {
    name: '3. 检查 ui_view_config.list.columns 是否定义',
    check: async () => {
      const fs = require('fs')
      const yaml = require('js-yaml')
      const path = require('path')

      const files = [
        { path: 'meta/schemas/role.yaml', name: 'role' },
        { path: 'meta/schemas/user_group.yaml', name: 'user_group' }
      ]

      const results = []

      for (const { path: filePath, name } of files) {
        try {
          const content = fs.readFileSync(path.join(__dirname, filePath), 'utf8')
          const parsed = yaml.load(content)
          const columns = parsed?.ui_view_config?.list?.columns

          if (columns && Array.isArray(columns) && columns.length > 0) {
            console.log(`[列定义检查] ${name}: [OK] ${columns.length} 列`)
            columns.forEach(col => {
              const field = col.field || col.id
              console.log(`   - ${field}: width=${col.width}, sortable=${col.sortable}`)
            })
            results.push({ name, success: true, count: columns.length })
          } else {
            console.log(`[列定义检查] ${name}: [X] 缺少 columns 定义`)
            results.push({ name, success: false })
          }
        } catch (e) {
          console.log(`[列定义检查] ${name}: [X] 错误 - ${e.message}`)
          results.push({ name, success: false, error: e.message })
        }
      }

      return results.every(r => r.success)
    }
  },
  {
    name: '4. 检查后端 meta API 路由是否注册',
    check: async () => {
      const fs = require('fs')
      const path = require('path')

      const apiFile = path.join(__dirname, 'meta/api/bo_api.py')
      const content = fs.readFileSync(apiFile, 'utf8')

      const patterns = [
        { name: 'get_view_config', pattern: /def get_view_config|@.*route.*view.config/i },
        { name: 'meta_v2_bp', pattern: /meta_v2_bp|meta.*v2.*blueprint/i }
      ]

      const results = []

      for (const { name, pattern } of patterns) {
        const found = pattern.test(content)
        console.log(`[后端API检查] ${name}: ${found ? '[OK] 找到' : '[X] 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  },
  {
    name: '5. 检查前端 metaService 是否正确实现',
    check: async () => {
      const fs = require('fs')
      const path = require('path')

      const serviceFile = path.join(__dirname, 'src/services/metaService.js')
      const content = fs.readFileSync(serviceFile, 'utf8')

      const patterns = [
        { name: 'getViewConfig', pattern: /getViewConfig/i },
        { name: '/api/v2/meta', pattern: /\/api\/v2\/meta/i }
      ]

      const results = []

      for (const { name, pattern } of patterns) {
        const found = pattern.test(content)
        console.log(`[前端服务检查] ${name}: ${found ? '[OK] 找到' : '[X] 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  },
  {
    name: '6. 检查 useMetaList composable 是否正确实现',
    check: async () => {
      const fs = require('fs')
      const path = require('path')

      const composableFile = path.join(__dirname, 'src/composables/useMetaList.js')
      const content = fs.readFileSync(composableFile, 'utf8')

      const patterns = [
        { name: 'useMetaList', pattern: /export.*useMetaList/i },
        { name: 'loadList', pattern: /function loadList|const loadList/i },
        { name: '_transformMetaToComponentFormat', pattern: /_transformMetaToComponentFormat/i },
        { name: 'visibleColumns', pattern: /visibleColumns/i }
      ]

      const results = []

      for (const { name, pattern } of patterns) {
        const found = pattern.test(content)
        console.log(`[Composable检查] ${name}: ${found ? '[OK] 找到' : '[X] 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  },
  {
    name: '7. 检查 RoleManagement.vue 是否使用 useMetaList',
    check: async () => {
      const fs = require('fs')
      const path = require('path')

      const vueFile = path.join(__dirname, 'src/views/SystemManagement/RoleManagement.vue')
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
        console.log(`[RoleManagement检查] ${name}: ${found ? '[OK] 找到' : '[X] 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  },
  {
    name: '8. 检查 UserGroupManagement.vue 是否使用 useMetaList',
    check: async () => {
      const fs = require('fs')
      const path = require('path')

      const vueFile = path.join(__dirname, 'src/views/SystemManagement/UserGroupManagement.vue')
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
        console.log(`[UserGroupManagement检查] ${name}: ${found ? '[OK] 找到' : '[X] 未找到'}`)
        results.push(found)
      }

      return results.every(r => r)
    }
  }
]

async function runDiagnostics() {
  console.log('='.repeat(60))
  console.log('[SEARCH] 动态列表诊断工具')
  console.log('='.repeat(60))
  console.log('')

  let allPassed = true

  for (const { name, check } of checks) {
    console.log(`\n${name}`)
    console.log('-'.repeat(50))

    try {
      const result = await check()
      if (!result) {
        allPassed = false
      }
    } catch (e) {
      console.log(`[X] 检查出错: ${e.message}`)
      allPassed = false
    }
  }

  console.log('\n' + '='.repeat(60))
  if (allPassed) {
    console.log('[OK] 所有检查通过!')
  } else {
    console.log('[WARNING] 部分检查未通过，请查看上面的输出')
  }
  console.log('='.repeat(60))

  return allPassed
}

// 如果直接运行此脚本
if (require.main === module) {
  runDiagnostics().then(passed => {
    process.exit(passed ? 0 : 1)
  })
}

module.exports = { runDiagnostics }
