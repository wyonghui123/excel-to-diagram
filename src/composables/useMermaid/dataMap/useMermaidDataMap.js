export function useMermaidDataMap() {

  const buildObjectToModuleMap = (data) => {
    const objectToModuleMap = new Map()

    if (!data || !data.domainProducts) {
      return objectToModuleMap
    }

    data.domainProducts.forEach(domain => {
      if (domain.businessObjects) {
        domain.businessObjects.forEach(bo => {
          objectToModuleMap.set(bo.code || bo.name, {
            type: 'domain',
            name: domain.name,
            domain: domain.name,
            subDomain: domain.name
          })
        })
      }
      if (domain.modules) {
        domain.modules.forEach(module => {
          if (module.businessObjects) {
            module.businessObjects.forEach(bo => {
              objectToModuleMap.set(bo.code || bo.name, {
                type: 'module',
                name: module.name,
                parent: domain.name,
                domain: domain.name,
                subDomain: module.name
              })
            })
          }
          if (module.submodules) {
            module.submodules.forEach(submodule => {
              if (submodule.businessObjects) {
                submodule.businessObjects.forEach(bo => {
                  objectToModuleMap.set(bo.code || bo.name, {
                    type: 'submodule',
                    name: submodule.name,
                    parent: module.name,
                    grandparent: domain.name,
                    domain: domain.name,
                    subDomain: module.name
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