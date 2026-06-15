// Debug script: trace the relation scope tree building and el-tree @check flow
// Run: node debug_relation_scope.mjs
import { createRequire } from 'module'
import { fileURLToPath } from 'url'
import path from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const require = createRequire(import.meta.url)

// 1) Fetch relationships from the API
async function fetchAll() {
  // Login first to get auth_token cookie
  const loginRes = await fetch('http://localhost:3010/api/v1/auth/dev-login?username=admin', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  const setCookie = loginRes.headers.get('set-cookie')
  console.log('[login] status', loginRes.status, 'cookie set:', !!setCookie)

  // Extract auth_token
  const cookieMatch = setCookie?.match(/auth_token=[^;]+/)
  const authCookie = cookieMatch ? cookieMatch[0] : ''
  console.log('[login] authCookie:', authCookie)

  // Fetch version
  const versionsRes = await fetch('http://localhost:3010/api/v1/versions?page_size=10', {
    headers: { Cookie: authCookie }
  })
  const versionsData = await versionsRes.json()
  console.log('[versions] total:', versionsData.data?.total || versionsData.total)
  const v1 = versionsData.data?.items?.[0] || versionsData.items?.[0]
  console.log('[versions] first version:', { id: v1?.id, name: v1?.name })

  // Fetch relationships
  const relsRes = await fetch(`http://localhost:3010/api/v1/relationships?version_id=${v1.id}&page_size=10000`, {
    headers: { Cookie: authCookie }
  })
  const relsData = await relsRes.json()
  const rels = relsData.data?.items || relsData.data || []
  console.log('[relationships] count:', rels.length)
  console.log('[relationships] sample[0]:', JSON.stringify(rels[0], null, 2).slice(0, 800))
  return { rels, versionId: v1.id, authCookie }
}

const { rels, versionId, authCookie } = await fetchAll()

// 2) Now fetch business objects and other hierarchy data
async function fetchBos() {
  const res = await fetch(`http://localhost:3010/api/v1/business-objects?version_id=${versionId}&page_size=10000`, {
    headers: { Cookie: authCookie }
  })
  const data = await res.json()
  const bos = data.data?.items || data.data || []
  console.log('[business_objects] count:', bos.length)
  return bos
}
async function fetchSms() {
  const res = await fetch(`http://localhost:3010/api/v1/service-modules?version_id=${versionId}&page_size=5000`, {
    headers: { Cookie: authCookie }
  })
  const data = await res.json()
  return data.data?.items || data.data || []
}
async function fetchSds() {
  const res = await fetch(`http://localhost:3010/api/v1/sub-domains?version_id=${versionId}&page_size=1000`, {
    headers: { Cookie: authCookie }
  })
  const data = await res.json()
  return data.data?.items || data.data || []
}
async function fetchDomains() {
  const res = await fetch(`http://localhost:3010/api/v1/domains?version_id=${versionId}&page_size=100`, {
    headers: { Cookie: authCookie }
  })
  const data = await res.json()
  return data.data?.items || data.data || []
}

const [bos, sms, sds, domains] = await Promise.all([fetchBos(), fetchSms(), fetchSds(), fetchDomains()])
console.log('[hierarchy] bos=%d, sms=%d, sds=%d, domains=%d', bos.length, sms.length, sds.length, domains.length)

// 3) Build the boById map (mimicking loadBusinessObjectsWithHierarchy)
const smById = new Map()
sms.forEach(sm => {
  const smId = sm.id ?? sm.service_module_id
  if (smId != null) smById.set(String(smId), sm)
})
const sdById = new Map()
sds.forEach(sd => {
  const sdId = sd.id ?? sd.sub_domain_id
  if (sdId != null) sdById.set(String(sdId), sd)
})
const boInfos = bos.map(bo => {
  const smId = bo.service_module_id ?? bo.serviceModuleId
  const sm = smId != null ? smById.get(String(smId)) : null
  const sdId = sm ? (sm.sub_domain_id ?? sm.subDomainId) : null
  const sd = sdId != null ? sdById.get(String(sdId)) : null
  return {
    id: bo.id,
    code: bo.code,
    name: bo.name,
    domainId: sd ? (sd.domain_id ?? sd.domainId) : bo.domain_id ?? bo.domainId,
    domain: sd ? (sd.domain_name ?? sd.domainName) : bo.domain_name ?? bo.domainName,
    subDomainId: sd ? (sd.id ?? sd.sub_domain_id) : bo.sub_domain_id ?? bo.subDomainId,
    subDomain: sd ? (sd.name ?? sd.sub_domain_name) : bo.sub_domain_name ?? bo.subDomainName,
    serviceModuleId: smId,
    serviceModule: sm ? (sm.name ?? sm.service_module_name) : bo.service_module_name ?? bo.serviceModuleName,
    serviceModuleName: sm ? (sm.name ?? sm.service_module_name) : bo.service_module_name ?? bo.serviceModuleName
  }
})

// 4) Find the procurement domain (the one matching the user's "采购管理领域")
// First, let's just check the first domain in domains list, or look for procurement
console.log('[domains] sample:', JSON.stringify(domains[0], null, 2).slice(0, 400))
const procurementDomain = domains.find(d => /采购|procurement/i.test(d.name || d.domain_name || '')) || domains[0]
console.log('[debug] Using domain:', { id: procurementDomain.id, name: procurementDomain.name })

// 5) Now run buildRelationScopeTree
// We need to import the actual function. Let's transpile the .js file
// or just inline the logic
const { buildRelationScopeTree, classifyRelation, ScopeType, CategoryType } = await import('./src/services/relationClassifier.js').catch(async () => {
  // The .js file uses ES modules - try the .mjs path
  return await import('./src/services/relationClassifier.js')
})

console.log('[debug] buildRelationScopeTree:', typeof buildRelationScopeTree)

const tree = buildRelationScopeTree(
  { domainIds: [procurementDomain.id], subDomainIds: [], serviceModuleIds: [], businessObjectIds: [] },
  rels,
  boInfos
)

console.log('\n========== TREE STRUCTURE ==========')
function printTree(nodes, depth = 0) {
  for (const n of nodes) {
    const indent = '  '.repeat(depth)
    const ids = n.relationIds ? ` [ids: ${n.relationIds.length} - first 3: ${n.relationIds.slice(0, 3).join(',')}]` : ''
    const codes = n.relationCodes ? ` [codes: ${n.relationCodes.length}]` : ''
    console.log(`${indent}${n.name} (count=${n.count}, scopeType=${n.scopeType}, categoryType=${n.categoryType})${ids}${codes}`)
    if (n.children) printTree(n.children, depth + 1)
  }
}
printTree(tree)

// 6) Collect all leaf relationIds
console.log('\n========== ALL LEAF RELATION IDS ==========')
const allLeafIds = []
const allLeafKeys = []
function walkLeaves(nodes) {
  for (const n of nodes) {
    if (n.relationIds?.length > 0) {
      allLeafIds.push(...n.relationIds)
      allLeafKeys.push({ nodeId: n.id, name: n.name, scopeType: n.scopeType, count: n.relationIds.length })
    }
    if (n.children) walkLeaves(n.children)
  }
}
walkLeaves(tree)
console.log('Total leaves with relationIds:', allLeafKeys.length)
console.log('Total unique relationIds:', new Set(allLeafIds).size)
console.log('Leaf details:')
allLeafKeys.forEach(k => console.log(`  ${k.nodeId} (${k.scopeType}, count=${k.count}): ${k.name}`))

// 7) Now check: do the union of "internal" leaves + "cross-boundary" leaves = 29 unique IDs?
const internalLeaves = []
const crossBoundaryLeaves = []
function collectByScope(nodes, scopeType) {
  for (const n of nodes) {
    if (n.relationIds?.length > 0 && n.scopeType === scopeType) {
      if (scopeType === 'internal') internalLeaves.push(...n.relationIds)
      if (scopeType === 'cross-boundary') crossBoundaryLeaves.push(...n.relationIds)
    }
    if (n.children) collectByScope(n.children, scopeType)
  }
}
collectByScope(tree, 'internal')
collectByScope(tree, 'cross-boundary')

console.log('\n========== SCOPE BREAKDOWN ==========')
console.log('Internal (范围内) relationIds count:', new Set(internalLeaves).size)
console.log('Cross-boundary (范围内与外部) relationIds count:', new Set(crossBoundaryLeaves).size)
console.log('Total unique (internal ∪ cross-boundary):', new Set([...internalLeaves, ...crossBoundaryLeaves]).size)
console.log('Cross-boundary IDs:', [...new Set(crossBoundaryLeaves)])
