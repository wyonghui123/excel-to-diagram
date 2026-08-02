export function useMermaidDataMap() {

  const buildObjectToModuleMap = (data) => {
    const objectToModuleMap = new Map()

    // [FIX 2026-08-02] 提前返回只能针对 !data:
    //   之前 `if (!data || !data.domainProducts) return` 会在服务模块图 (统一管道输出
    //   不含 domainProducts) 时直接返回空 map, 导致下方 data.nodes 兜底永远不执行,
    //   updateColorsOnly 对所有 SM 节点静默跳过 → 切配色/颜色分组 fill 不更新。
    //   domainProducts 循环改为内部守卫, SM 图走 data.nodes 兜底补建索引。
    if (!data) {
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

    if (data.domainProducts) {
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
    }  // end if (data.domainProducts)

    // [FIX 2026-08-02] 统一管道兜底: 服务模块图 (serviceModuleDiagramBuilder) 输出的
    //   diagramData 不含 domainProducts → 上面循环不会写入任何 key → buildColorMap /
    //   updateNodeColors 里 objectToModuleMap.get(mapping.nodeCode) 恒为 undefined,
    //   切换配色/颜色分组时 updateColorsOnly 对所有 SM 节点静默跳过 → fill 不更新
    //   (用户报告"SM 图切配色/颜色分组非增量")。
    //   统一管道的投影终端节点 (data.nodes) 自带 domain/subDomain (L1 树派生),
    //   以此补建 code/name 索引; 仅当 domainProducts 未覆盖时写入, 不影响 BO 图既有行为。
    if (data.nodes && Array.isArray(data.nodes)) {
      data.nodes.forEach(node => {
        if (!node || !(node.code || node.name)) return
        if (!node.domain && !node.subDomain) return
        const key = node.code || node.name
        if (objectToModuleMap.has(key)) return
        objectToModuleMap.set(key, {
          type: 'projection',
          name: node.name || node.code,
          code: node.code,
          domain: node.domain,
          subDomain: node.subDomain,
          serviceModule: node.name || node.code,
          serviceModuleName: node.name || node.code
        })
      })
    }

    return objectToModuleMap
  }

  return {
    buildObjectToModuleMap
  }
}