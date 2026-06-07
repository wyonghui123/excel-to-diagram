/**
 * check-view-config.cjs - 检查 view-config API 返回的原始数据
 */

const http = require('http')

const BASE_URL = 'http://localhost:5000'

function makeRequest(path) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE_URL)
    console.log(`\n🌐 请求: GET ${url.href}`)

    http.get(url.href, (res) => {
      let data = ''

      res.on('data', (chunk) => {
        data += chunk
      })

      res.on('end', () => {
        console.log(`📥 状态码: ${res.statusCode}`)
        try {
          const json = JSON.parse(data)
          resolve({ status: res.statusCode, data: json })
        } catch (e) {
          console.log(`❌ JSON 解析失败: ${e.message}`)
          resolve({ status: res.statusCode, data: data })
        }
      })
    }).on('error', (e) => {
      console.log(`❌ 请求失败: ${e.message}`)
      reject(e)
    })
  })
}

async function checkViewConfig(entityType) {
  console.log('\n' + '='.repeat(60))
  console.log(`🔍 检查 ${entityType} 的 view-config`)
  console.log('='.repeat(60))

  const result = await makeRequest(`/api/v2/meta/${entityType}/view-config`)

  if (result.status === 401) {
    console.log('⚠️  需要认证，使用模拟数据测试...')
    return
  }

  if (result.data.success) {
    const config = result.data.data
    console.log('✅ view-config 加载成功')

    console.log('\n📋 list 配置:')
    if (config.list) {
      console.log(`   title: ${config.list.title}`)
      console.log(`   columns 数量: ${config.list.columns?.length || 0}`)
      console.log(`   actions 数量: ${config.list.actions?.length || 0}`)
      console.log(`   searchFields 数量: ${config.list.searchFields?.length || 0}`)
      console.log(`   filters 数量: ${config.list.filters?.length || 0}`)

      if (config.list.columns) {
        console.log('\n   📌 列定义:')
        config.list.columns.forEach((col, i) => {
          console.log(`      ${i + 1}. key=${col.key}, title=${col.title}, width=${col.width}`)
        })
      }

      if (config.list.actions) {
        console.log('\n   📌 操作定义:')
        config.list.actions.forEach((act, i) => {
          console.log(`      ${i + 1}. key=${act.key}, label=${act.label}`)
        })
      }
    } else {
      console.log('   ❌ 缺少 list 配置')
    }

    console.log('\n📋 form 配置:')
    if (config.form) {
      console.log(`   title: ${config.form.title}`)
      console.log(`   groups 数量: ${config.form.groups?.length || 0}`)
    } else {
      console.log('   ⚠️  缺少 form 配置')
    }

    console.log('\n📋 detail 配置:')
    if (config.detail) {
      console.log(`   title: ${config.detail.title}`)
      console.log(`   tabs 数量: ${config.detail.tabs?.length || 0}`)
    } else {
      console.log('   ⚠️  缺少 detail 配置')
    }

    return config
  } else {
    console.log('❌ view-config 加载失败:', result.data.message)
    return null
  }
}

async function main() {
  console.log('='.repeat(60))
  console.log('🔍 View-Config API 诊断工具')
  console.log('='.repeat(60))

  // 检查后端是否运行
  console.log('\n1. 检查后端服务...')
  try {
    await makeRequest('/api/health')
    console.log('✅ 后端服务正常运行')
  } catch (e) {
    console.log('❌ 后端服务未运行')
    process.exit(1)
  }

  // 检查各个实体的 view-config
  await checkViewConfig('role')
  await checkViewConfig('user_group')
  await checkViewConfig('user')

  console.log('\n' + '='.repeat(60))
  console.log('诊断完成')
  console.log('='.repeat(60))
}

main().catch(console.error)
