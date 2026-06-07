// 在浏览器控制台执行，检查 columns 数据
(async () => {
  // 获取 Vue 应用
  const app = document.querySelector('#app');
  const vueApp = app?.__vue_app__;
  if (!vueApp) {
    console.log('Vue app not found');
    return;
  }

  // 获取组件实例
  const instance = vueApp._instance;
  if (!instance) {
    console.log('Root instance not found');
    return;
  }

  // 递归查找 MetaListPage
  function findMetaListPage(comp) {
    if (!comp) return null;
    const name = comp.type?.name;
    if (name === 'MetaListPage') return comp;
    
    // 检查 children
    if (comp.children) {
      for (const child of comp.children) {
        const result = findMetaListPage(child);
        if (result) return result;
      }
    }
    
    // 检查 subtree
    if (comp.subTree) {
      const result = findMetaListPage(comp.subTree);
      if (result) return result;
    }
    
    return null;
  }

  const metaListInstance = findMetaListPage(instance);
  if (!metaListInstance) {
    console.log('MetaListPage not found');
    return;
  }

  // 获取 columns（可能是 ref 或直接值）
  const columns = metaListInstance.columns;
  const actualColumns = columns?.value || columns;
  
  if (!actualColumns || !Array.isArray(actualColumns)) {
    console.log('columns not found or not array');
    return;
  }

  // 查找 parent_id 列
  const parentCol = actualColumns.find(c => c.key === 'parent_id' || c.prop === 'parent_id');
  if (!parentCol) {
    console.log('parent_id column not found');
    console.log('Available columns:', actualColumns.map(c => ({ key: c.key, prop: c.prop, filterable: c.filterable })));
    return;
  }

  console.log('parent_id column:');
  console.log(JSON.stringify(parentCol, null, 2));
})();
