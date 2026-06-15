export function useMermaidDataMap() {

  const buildObjectToModuleMap = (data) => {
    const objectToModuleMap = new Map()

    if (!data || !data.domainProducts) {
      return objectToModuleMap
    }

    // [v34 颜色修复] 先建一个 BO code/name -> serviceModule 信息的索引
    // 之前 buildObjectToModuleMap 只在 moduleInfo 上挂 domain/subDomain/name
    // 导致 buildColorMap 在 colorGroupBy='serviceModule' 时 groupKey 永远是 undefined
    // 全部 BO 落到同一个 group → 全部同色 (用户报告"按服务模块 蓝绿黄"配置后看到 3 个其他颜色)
    const boServiceModuleMap = new Map()
    if (data.businessObjects) {
      data.businessObjects.forEach(bo => {
        if (bo.code || bo.name) {
          boServiceModuleMap.set(bo.code || bo.name, {
            serviceModule: bo.serviceModule,
            serviceModuleName: bo.serviceModuleName
          })
        }
      })
    }

    data.domainProducts.forEach(domain => {
      if (domain.businessObjects) {
        domain.businessObjects.forEach(bo => {
          const smInfo = boServiceModuleMap.get(bo.code || bo.name) || {}
          objectToModuleMap.set(bo.code || bo.name, {
            type: 'domain',
            name: domain.name,
            code: domain.code,
            domain: domain.name,
            subDomain: domain.name,
            serviceModule: smInfo.serviceModule || bo.serviceModule,
            serviceModuleName: smInfo.serviceModuleName || bo.serviceModuleName
          })
        })
      }
      if (domain.modules) {
        domain.modules.forEach(module => {
          if (module.businessObjects) {
            module.businessObjects.forEach(bo => {
              const smInfo = boServiceModuleMap.get(bo.code || bo.name) || {}
              objectToModuleMap.set(bo.code || bo.name, {
                type: 'module',
                name: module.name,
                code: module.code,
                parent: domain.name,
                domain: domain.name,
                subDomain: module.name,
                serviceModule: smInfo.serviceModule || bo.serviceModule,
                serviceModuleName: smInfo.serviceModuleName || bo.serviceModuleName
              })
            })
          }
          if (module.submodules) {
            module.submodules.forEach(submodule => {
              if (submodule.businessObjects) {
                submodule.businessObjects.forEach(bo => {
                  const smInfo = boServiceModuleMap.get(bo.code || bo.name) || {}
                  objectToModuleMap.set(bo.code || bo.name, {
                    type: 'submodule',
                    name: submodule.name,
                    code: submodule.code,
                    parent: module.name,
                    grandparent: domain.name,
                    domain: domain.name,
                    subDomain: module.name,
                    serviceModule: smInfo.serviceModule || bo.serviceModule,
                    serviceModuleName: smInfo.serviceModuleName || bo.serviceModuleName
                  })
                })
              }
            })
          }
        })
      }
    })

    return objectToModuleMap
  }

  return {
    buildObjectToModuleMap
  }
}