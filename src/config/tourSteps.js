export const WORKSPACE_TOUR_STEPS = [
  {
    id: 'welcome',
    title: '欢迎使用 BIP 应用架构管理系统',
    content: '这是一个帮助您管理产品架构、业务对象和生成关系图的工具。让我们花1分钟了解主要功能。',
    placement: 'center'
  },
  {
    id: 'apps-section',
    target: '.apps-tiles',
    title: '快捷应用区',
    content: '这里列出了系统的四个核心功能模块，点击即可进入对应功能。',
    placement: 'bottom',
    highlight: true
  },
  {
    id: 'product-version',
    target: '.app-tile:nth-child(1)',
    title: '产品版本管理',
    content: '管理您的产品线和版本信息。在这里可以创建产品、添加版本、查看版本历史。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'arch-data',
    target: '.app-tile:nth-child(2)',
    title: '架构数据管理',
    content: '管理领域、子领域、服务模块和业务对象。这是系统的核心数据管理模块。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'aa-diagram',
    target: '.app-tile:nth-child(3)',
    title: 'AA图生成',
    content: '通过向导式步骤，从Excel文件生成业务对象关系图。支持多种图表类型和布局方式。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'frequent-products',
    target: '.frequent-products-section',
    title: '常用产品',
    content: '这里显示您最近访问的产品版本，方便快速进入工作。',
    placement: 'top',
    highlight: true
  },
  {
    id: 'get-started',
    title: '准备就绪！',
    content: '您已经了解了系统的基本功能。建议从"产品版本管理"开始，创建您的第一个产品。',
    placement: 'center'
  }
]

export const DIAGRAM_TOUR_STEPS = [
  {
    id: 'step-navigator',
    target: '.step-navigator',
    title: '步骤导航',
    content: 'AA图生成分为6个步骤：导入、中心、关系、类型、配置、展示。您可以在已完成步骤间自由切换。',
    placement: 'bottom',
    highlight: true
  },
  {
    id: 'upload-file',
    target: '.file-upload-area',
    title: '上传Excel文件',
    content: '点击或拖拽Excel文件到此处。支持.xlsx、.xls和.csv格式。文件需包含业务对象、模块和关联对象列。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'center-scope',
    target: '.center-scope-panel',
    title: '选择中心范围',
    content: '选择要在图表中心显示的业务对象。可以通过领域、子领域或服务模块进行筛选。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'relation-scope',
    target: '.relation-scope-panel',
    title: '选择关系范围',
    content: '选择要显示的对象关系类型。系统会根据中心对象自动推荐相关关系。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'chart-type',
    target: '.chart-type-selector',
    title: '选择图表类型',
    content: '选择业务对象图或服务模块图。业务对象图显示对象间关系，服务模块图显示模块间关系。',
    placement: 'bottom',
    highlight: true
  },
  {
    id: 'diagram-config',
    target: '.diagram-config-panel',
    title: '配置图表参数',
    content: '设置布局方式（ELK/Dagre）、颜色分组、标签显示等参数。配置完成后点击"生成图表"。',
    placement: 'left',
    highlight: true
  },
  {
    id: 'diagram-display',
    target: '.diagram-display-area',
    title: '查看关系图',
    content: '生成的关系图支持拖拽调整、缩放查看。点击"导出"按钮可保存为PNG图片。',
    placement: 'top',
    highlight: true
  }
]

export const ARCH_DATA_TOUR_STEPS = [
  {
    id: 'tree-nav',
    target: '.tree-navigator',
    title: '树形导航',
    content: '使用左侧树形导航快速定位到不同层级的架构数据：产品 → 版本 → 领域 → 子领域 → 服务模块 → 业务对象。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'filter-panel',
    target: '.dynamic-filter',
    title: '数据筛选',
    content: '使用筛选器快速过滤数据。支持按名称、状态、创建时间等条件筛选。',
    placement: 'bottom',
    highlight: true
  },
  {
    id: 'data-table',
    target: '.dynamic-table',
    title: '数据列表',
    content: '查看和管理当前层级的所有数据。支持排序、分页、批量操作。',
    placement: 'top',
    highlight: true
  },
  {
    id: 'import-btn',
    target: '.import-btn',
    title: '批量导入',
    content: '支持从Excel批量导入数据。下载模板后填写数据，上传即可快速导入。',
    placement: 'bottom',
    highlight: true
  },
  {
    id: 'export-btn',
    target: '.export-btn',
    title: '数据导出',
    content: '将当前筛选的数据导出为Excel文件，方便离线查看和编辑。',
    placement: 'bottom',
    highlight: true
  }
]

export const FEATURE_HINTS = {
  'product-create': {
    target: '.create-product-btn',
    content: '点击这里创建您的第一个产品',
    placement: 'right'
  },
  
  'version-create': {
    target: '.create-version-btn',
    content: '为产品添加版本，记录架构演进历史',
    placement: 'right'
  },
  
  'arch-tree-expand': {
    target: '.tree-node-toggle',
    content: '点击展开/折叠子节点，快速浏览层级结构',
    placement: 'right'
  },
  
  'arch-filter-save': {
    target: '.save-filter-btn',
    content: '保存常用的筛选条件，下次快速加载',
    placement: 'bottom'
  },
  
  'diagram-preset': {
    target: '.preset-selector',
    content: '保存常用的范围配置，下次快速加载',
    placement: 'bottom'
  },
  
  'diagram-layout': {
    target: '.layout-selector',
    content: 'ELK适合复杂图，Dagre适合简单图',
    placement: 'left'
  },
  
  'diagram-color-group': {
    target: '.color-group-selector',
    content: '按领域、子领域或服务模块分组显示颜色',
    placement: 'left'
  }
}
