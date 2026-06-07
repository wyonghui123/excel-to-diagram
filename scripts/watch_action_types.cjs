#!/usr/bin/env node
/**
 * watch_action_types.cjs
 *
 * E-1: Watch mode - 监控后端 _openapi.json, 变化时自动重生成 TS types
 *
 * 使用: node scripts/watch_action_types.cjs [BASE_URL]
 * 停止: Ctrl+C
 */
'use strict';

const fs = require('fs');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');

const BASE = process.argv[2] || process.env.BO_ACTION_BASE || 'http://localhost:3010';
const POLL_INTERVAL = 5000;  // 5 秒
const OUTPUT = path.join(__dirname, '..', 'src', 'composables', 'useBoAction.types.d.ts');

let lastHash = '';

function fetchAndHash() {
  return new Promise((resolve, reject) => {
    http.get(`${BASE}/api/v2/action/_openapi.json`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          const hash = require('crypto')
            .createHash('md5')
            .update(JSON.stringify(json))
            .digest('hex');
          resolve({ hash, data: json });
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

function regenerate() {
  console.log(`[watch] Regenerating TS types...`);
  const child = spawn('node', ['scripts/generate_action_types.cjs', BASE], {
    stdio: 'inherit',
  });
  child.on('exit', (code) => {
    if (code === 0) {
      console.log(`[watch] ✅ Regenerated at ${new Date().toISOString()}`);
    } else {
      console.error(`[watch] ❌ Failed with code ${code}`);
    }
  });
}

async function poll() {
  try {
    const { hash } = await fetchAndHash();
    if (hash !== lastHash) {
      if (lastHash !== '') {
        console.log(`[watch] OpenAPI spec changed! (hash: ${hash.substring(0, 8)})`);
        regenerate();
      } else {
        console.log(`[watch] Initial hash: ${hash.substring(0, 8)}`);
      }
      lastHash = hash;
    } else {
      process.stdout.write('.');
    }
  } catch (e) {
    console.error(`[watch] Fetch failed: ${e.message}`);
  }
}

console.log(`[watch] Watching ${BASE}/api/v2/action/_openapi.json`);
console.log(`[watch] Output: ${OUTPUT}`);
console.log(`[watch] Poll interval: ${POLL_INTERVAL}ms`);
console.log(`[watch] Press Ctrl+C to stop`);

// 首次跑一次
regenerate();
// 然后 poll
setInterval(poll, POLL_INTERVAL);
