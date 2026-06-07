/**
 * test-api-integration.cjs - 测试后端 API 集成
 */

const http = require('http')

const BASE_URL = 'http://localhost:5000' // 后端地址，根据实际情况修改

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
          console.log(`📦 原始数据: ${data.substring(0, 500)}...`)
          resolve({ status: res.statusCode, data: data })
        }
      })
    }).on('error', (e) => {
      console.log(`❌ 请求失败: ${e.message}`)
      reject(e)
    })
  })
}

async function testAPI() {
  console.log('='.repeat(60))
  console.log('🔍 API 集成测试')
  console.log('='.repeat(60))

  // 测试 1: 检查后端是否运行
  console.log('\n1. 检查后端服务...')
  try {
    const health = await makeRequest('/api/health')
    console.log('✅ 后端服务正常运行')
  } catch (e) {
    console.log('❌ 后端服务未运行，请确保后端已启动 (npm run dev:backend 或 python run.py)')
    console.log('\n如果后端在其他端口运行，请修改 BASE_URL 变量')
    process.exit(1)
  }

  // 测试 2: 获取 role 视图配置
  console.log('\n2. 获取 role 视图配置...')
  const roleViewConfig = await makeRequest('/api/v2/meta/role/view-config')
  if (roleViewConfig.data.success) {
    console.log('✅ role 视图配置加载成功')
    const config = roleViewConfig.data.data
    console.log(`   - title: ${config.list?.title}`)
    console.log(`   - columns: ${config.list?.columns?.length || 0} 列`)
    if (config.list?.columns) {
      config.list.columns.forEach((col, i) => {
        console.log(`     ${i + 1}. key=${col.key}, title=${col.title}`)
      })
    }
    console.log(`   - actions: ${config.list?.actions?.length || 0} 个`)
  } else {
    console.log('❌ role 视图配置加载失败:', roleViewConfig.data.message)
  }

  // 测试 3: 获取 user_group 视图配置
  console.log('\n3. 获取 user_group 视图配置...')
  const userGroupViewConfig = await makeRequest('/api/v2/meta/user_group/view-config')
  if (userGroupViewConfig.data.success) {
    console.log('✅ user_group 视图配置加载成功')
    const config = userGroupViewConfig.data.data
    console.log(`   - title: ${config.list?.title}`)
    console.log(`   - columns: ${config.list?.columns?.length || 0} 列`)
    if (config.list?.columns) {
      config.list.columns.forEach((col, i) => {
        console.log(`     ${i + 1}. key=${col.key}, title=${col.title}`)
      })
    }
  } else {
    console.log('❌ user_group 视图配置加载失败:', userGroupViewConfig.data.message)
  }

  // 测试 4: 获取角色列表数据
  console.log('\n4. 获取角色列表数据...')
  const roleList = await makeRequest('/api/v2/bo/role?page=1&page_size=5')
  if (roleList.data.success) {
    console.log('✅ 角色列表加载成功')
    console.log(`   - total: ${roleList.data.data?.total}`)
    console.log(`   - items: ${roleList.data.data?.items?.length} 条`)
    if (roleList.data.data?.items) {
      roleList.data.data.items.forEach((item, i) => {
        console.log(`     ${i + 1}. id=${item.id}, name=${item.name}`)
      })
    }
  } else {
    console.log('❌ 角色列表加载失败:', roleList.data.message)
  }

  // 测试 5: 获取用户组列表数据
  console.log('\n5. 获取用户组列表数据...')
  const userGroupList = await makeRequest('/api/v2/bo/user_group?page=1&page_size=5')
  if (userGroupList.data.success) {
    console.log('✅ 用户组列表加载成功')
    console.log(`   - total: ${userGroupList.data.data?.total}`)
    console.log(`   - items: ${userGroupList.data.data?.items?.length} 条`)
  } else {
    console.log('❌ 用户组列表加载失败:', userGroupList.data.message)
  }

  console.log('\n' + '='.repeat(60))
  console.log('测试完成')
  console.log('='.repeat(60))
}

testAPI().catch(console.error)
