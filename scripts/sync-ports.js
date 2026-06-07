#!/usr/bin/env node
/**
 * 端口配置同步脚本
 * 
 * 功能：
 * 1. 从 .env 文件读取端口配置
 * 2. 同步到所有相关配置文件
 * 3. 验证配置一致性
 * 
 * 使用方法：
 *   node scripts/sync-ports.js
 * 
 * 环境变量优先级：
 *   1. .env 文件
 *   2. .env.local 文件（本地覆盖）
 *   3. 系统环境变量
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');

// 默认端口配置
const DEFAULT_PORTS = {
  VITE_DEV_PORT: '3004',
  MOCK_API_PORT: '3001',
  FLASK_PORT: '5000',
  E2E_PORT: '3004'
};

// 读取 .env 文件
function loadEnv() {
  const env = { ...DEFAULT_PORTS };
  const envPath = path.join(rootDir, '.env');
  const envLocalPath = path.join(rootDir, '.env.local');
  
  const files = [envPath, envLocalPath];
  
  for (const file of files) {
    if (fs.existsSync(file)) {
      const content = fs.readFileSync(file, 'utf-8');
      const lines = content.split('\n');
      
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#')) {
          const [key, ...valueParts] = trimmed.split('=');
          const value = valueParts.join('=').trim();
          if (key && value) {
            env[key] = value;
          }
        }
      }
    }
  }
  
  // 系统环境变量覆盖
  for (const key of Object.keys(DEFAULT_PORTS)) {
    if (process.env[key]) {
      env[key] = process.env[key];
    }
  }
  
  return env;
}

function safeWrite(filePath, newContent) {
  const oldContent = fs.readFileSync(filePath, 'utf-8');
  if (oldContent !== newContent) {
    fs.writeFileSync(filePath, newContent);
    return true;
  }
  return false;
}

// 更新 vite.config.js
function updateViteConfig(env) {
  const configPath = path.join(rootDir, 'vite.config.js');
  let content = fs.readFileSync(configPath, 'utf-8');
  
  // 替换端口
  content = content.replace(
    /port:\s*(\d+)/,
    `port: ${env.VITE_DEV_PORT}`
  );
  
  // 替换代理目标
  content = content.replace(
    /target:\s*'http:\/\/localhost:\d+'/g,
    (match) => {
      if (match.includes('deepseek') || match.includes('zhipu')) {
        return `target: 'http://localhost:${env.MOCK_API_PORT}'`;
      } else {
        return `target: 'http://localhost:${env.FLASK_PORT}'`;
      }
    }
  );
  
  if (safeWrite(configPath, content)) {
    console.log('[OK] vite.config.js 已更新');
  } else {
    console.log('⏭️  vite.config.js 无需更新');
  }
}

// 更新 playwright.config.js
function updatePlaywrightConfig(env) {
  const configPath = path.join(rootDir, 'playwright.config.js');
  let content = fs.readFileSync(configPath, 'utf-8');
  
  // 替换 baseURL
  content = content.replace(
    /baseURL:\s*'http:\/\/localhost:\d+'/,
    `baseURL: 'http://localhost:${env.E2E_PORT}'`
  );
  
  // 替换 url
  content = content.replace(
    /url:\s*'http:\/\/localhost:\d+'/g,
    `url: 'http://localhost:${env.E2E_PORT}'`
  );
  
  // 替换 command
  content = content.replace(
    /--port\s+\d+/,
    `--port ${env.E2E_PORT}`
  );
  
  if (safeWrite(configPath, content)) {
    console.log('[OK] playwright.config.js 已更新');
  } else {
    console.log('⏭️  playwright.config.js 无需更新');
  }
}

// 更新 meta/server.py
function updateFlaskServer(env) {
  const serverPath = path.join(rootDir, 'meta', 'server.py');
  let content = fs.readFileSync(serverPath, 'utf-8');
  
  // 替换默认端口
  content = content.replace(
    /port\s*=\s*int\(os\.environ\.get\('PORT',\s*\d+\)\)/,
    `port = int(os.environ.get('PORT', ${env.FLASK_PORT}))`
  );
  
  if (safeWrite(serverPath, content)) {
    console.log('[OK] meta/server.py 已更新');
  } else {
    console.log('⏭️  meta/server.py 无需更新');
  }
}

// 更新 server/server.js
function updateMockServer(env) {
  const serverPath = path.join(rootDir, 'server', 'server.js');
  let content = fs.readFileSync(serverPath, 'utf-8');
  
  // 替换端口
  content = content.replace(
    /const\s+PORT\s*=\s*\d+/,
    `const PORT = ${env.MOCK_API_PORT}`
  );
  
  if (safeWrite(serverPath, content)) {
    console.log('[OK] server/server.js 已更新');
  } else {
    console.log('⏭️  server/server.js 无需更新');
  }
}

// 更新 package.json
function updatePackageJson(env) {
  const pkgPath = path.join(rootDir, 'package.json');
  let content = fs.readFileSync(pkgPath, 'utf-8');
  
  // 替换 electron:dev 脚本中的端口
  content = content.replace(
    /VITE_DEV_SERVER_URL=http:\/\/localhost:\d+/,
    `VITE_DEV_SERVER_URL=http://localhost:${env.VITE_DEV_PORT}`
  );
  
  if (safeWrite(pkgPath, content)) {
    console.log('[OK] package.json 已更新');
  } else {
    console.log('⏭️  package.json 无需更新');
  }
}

// 验证配置一致性
function validateConfig(env) {
  console.log('\n[CLIPBOARD] 当前端口配置：');
  console.log('─'.repeat(40));
  console.log(`  Vite 开发服务器:  http://localhost:${env.VITE_DEV_PORT}`);
  console.log(`  Node.js Mock API: http://localhost:${env.MOCK_API_PORT}`);
  console.log(`  Python Flask:     http://localhost:${env.FLASK_PORT}`);
  console.log(`  E2E 测试:         http://localhost:${env.E2E_PORT}`);
  console.log('─'.repeat(40));
  
  const issues = [];
  
  if (env.VITE_DEV_PORT === env.FLASK_PORT) {
    issues.push('[WARNING]  Vite 和 Flask 不能使用相同端口！');
  }
  
  if (env.VITE_DEV_PORT === env.MOCK_API_PORT) {
    issues.push('[WARNING]  Vite 和 Mock API 不能使用相同端口！');
  }
  
  // 注意：Vite 和 E2E 使用相同端口是允许的，因为 E2E 会自动启动 Vite
  if (env.MOCK_API_PORT === env.FLASK_PORT) {
    issues.push('[WARNING]  Mock API 和 Flask 不能使用相同端口！');
  }
  
  if (issues.length > 0) {
    console.log('\n[X] 配置冲突：');
    issues.forEach(i => console.log(`  ${i}`));
    process.exit(1);
  } else {
    console.log('\n[OK] 端口配置无冲突');
  }
}

// 主函数
function main() {
  console.log('[TOOL] 端口配置同步工具\n');
  
  const env = loadEnv();
  
  console.log('[DECORATIVE] 正在同步配置...\n');
  
  updateViteConfig(env);
  updatePlaywrightConfig(env);
  updateFlaskServer(env);
  updateMockServer(env);
  updatePackageJson(env);
  
  validateConfig(env);
  
  console.log('\n[DECORATIVE] 完成！请通过统一服务管理器重启服务：');
  console.log('\n管理命令：');
  console.log('  查看状态:  powershell -File scripts/service_manager.ps1 status');
  console.log('  启动全部:  powershell -File scripts/service_manager.ps1 start');
  console.log('  重启服务:  powershell -File scripts/service_manager.ps1 restart');
}

main();
