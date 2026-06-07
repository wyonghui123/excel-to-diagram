import http from 'http'

const VITE_PORT = 3004
const FLASK_PORT = 3010
const FLASK_HEALTH_PATH = '/health'  // 后端健康检查路由

function checkPort(port, name, path = '/') {
  return new Promise((resolve) => {
    const req = http.get(`http://localhost:${port}${path}`, { timeout: 3000 }, (res) => {
      // HTTP 2xx/3xx = OK，4xx/5xx = 服务错误
      const ok = res.statusCode >= 200 && res.statusCode < 400
      resolve({ port, name, ok, status: res.statusCode })
    })
    req.on('error', () => {
      resolve({ port, name, ok: false, status: 'ERR_CONNECTION_REFUSED' })
    })
    req.on('timeout', () => {
      req.destroy()
      resolve({ port, name, ok: false, status: 'TIMEOUT' })
    })
  })
}

async function main() {
  console.log('\n[SEARCH] E2E 测试环境预检\n')
  console.log('─'.repeat(40))

  const checks = await Promise.all([
    checkPort(VITE_PORT, 'Vite 前端'),
    checkPort(FLASK_PORT, 'Flask 后端', FLASK_HEALTH_PATH)
  ])

  let allOk = true

  for (const c of checks) {
    const icon = c.ok ? '[OK]' : '[X]'
    const status = c.ok ? `HTTP ${c.status}` : c.status
    console.log(`  ${icon} ${c.name}: http://localhost:${c.port} (${status})`)
    if (!c.ok) allOk = false
  }

  console.log('─'.repeat(40))

  if (allOk) {
    console.log('\n[OK] 环境就绪，可以运行测试！')
    console.log('\n运行命令：')
    console.log('  npx playwright test --project=smoke --reporter=line,html')
    console.log('  npx playwright test --project=features --reporter=line,html')
    process.exit(0)
  } else {
    console.log('\n[X] 环境未就绪！请先启动服务：')
    console.log('  终端 A: npm run dev')
    console.log('  终端 B: python dev.py')
    console.log('  终端 C: 运行测试命令')
    process.exit(1)
  }
}

main()
