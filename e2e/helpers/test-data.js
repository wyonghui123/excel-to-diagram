export async function findProductWithVersion(request, baseURL) {
  const resp = await request.get(`${baseURL}/api/v2/bo/product`)
  if (!resp.ok()) return null
  const data = await resp.json()
  const products = data.items || data

  for (const product of products) {
    const versionResp = await request.get(`${baseURL}/api/v2/bo/version`, {
      params: { product_id: product.id }
    })
    if (!versionResp.ok()) continue
    const versionData = await versionResp.json()
    const versions = versionData.items || versionData
    if (versions.length > 0) {
      return { product, version: versions[0] }
    }
  }
  return null
}

export async function findEnumByMutability(request, baseURL, mutability) {
  const resp = await request.get(`${baseURL}/api/v2/bo/enum_type`)
  if (!resp.ok()) return null
  const data = await resp.json()
  const enums = data.items || data
  return enums.find(e => e.mutability === mutability) || null
}

export async function findRoleWithPermissions(request, baseURL) {
  const resp = await request.get(`${baseURL}/api/v1/roles`)
  if (!resp.ok()) return null
  const roles = await resp.json()
  return roles[0] || null
}

export async function findUserGroup(request, baseURL) {
  const resp = await request.get(`${baseURL}/api/v2/bo/user_group`)
  if (!resp.ok()) return null
  const data = await resp.json()
  const groups = data.items || data
  return groups[0] || null
}

export async function findBusinessObject(request, baseURL, serviceModuleId) {
  const resp = await request.get(`${baseURL}/api/v2/bo/business_object`, {
    params: { service_module_id: serviceModuleId }
  })
  if (!resp.ok()) return null
  const data = await resp.json()
  const bos = data.items || data
  return bos[0] || null
}

export async function ensureTestData(request, baseURL, type) {
  switch (type) {
    case 'product':
      const product = await findProductWithVersion(request, baseURL)
      if (product) return product

      const createResp = await request.post(`${baseURL}/api/v2/bo/product`, {
        data: {
          id: `test_product_${Date.now()}`,
          name: '测试产品',
          description: 'E2E测试创建'
        }
      })
      if (!createResp.ok()) return null
      return { product: await createResp.json(), version: null }

    default:
      return null
  }
}

export function generateTestId(prefix = 'test') {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

export async function cleanupTestData(request, baseURL, type, ids) {
  const endpointMap = {
    product: '/api/v2/bo/product',
    version: '/api/v2/bo/version',
    business_object: '/api/v2/bo/business_object',
    relationship: '/api/v2/bo/relationship',
    user: '/api/v1/users',
    user_group: '/api/v2/bo/user_group',
    role: '/api/v1/roles'
  }

  const endpoint = endpointMap[type]
  if (!endpoint) return

  for (const id of ids) {
    try {
      await request.delete(`${baseURL}${endpoint}/${id}`)
    } catch (e) {
      console.warn(`Failed to cleanup ${type} ${id}:`, e.message)
    }
  }
}
