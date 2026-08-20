<template>
  <!-- [SYS 2026-08-07] 系统自动分组(无关系/有关系, _elkGroup=inner/boundary)默认隐藏,
       仅"高级设置"开关打开时展示. 与用户手动分组(自定义)区分开, 减少默认视觉噪音. -->
  <div v-if="!isSystemAuto || showAdvancedSettings" class="lgn-node">
    <div class="lgn-row" :class="{ 'row-drag-over': isRowDragOver, 'is-left-drop-zone': isLeftDropZone, 'is-hidden': group.visible === false }"
      draggable="true"
      @click="handleRowClick"
      @dragstart="handleGroupDragStart" @dragend="handleGroupDragEnd"
      @dragover.prevent="handleRowDragOver" @dragleave="handleRowDragLeave" @drop="handleRowDrop">
      <!-- [DROP-ZONE 2026-08-20] 拖拽 group 悬停左侧区时提示: 拖到此处将成为子分组 -->
      <span v-if="isLeftDropZone" class="lgn-drop-into-hint">成为其子分组</span>
      <button class="lgn-caret" @click="toggleExpanded" :class="{ expanded: expanded }"
        :title="hasChildren ? (expanded ? '收起' : '展开') : ''">
        <span v-if="hasChildren" class="caret-arrow">▸</span>
        <span v-else class="caret-placeholder"></span>
      </button>
      <!-- [ICON-REMOVE 2026-08-20] 分组行类型图标已移除 (用户确认不需要), 仅保留叶子图标 -->
      <!-- [COLOR 2026-08-05] 分组级色点：展示当前分组色（与图表一致），点击弹出调色板选色
           写入 store.customColors[分组key]，经增量 updateColorsOnly 即时变色 -->
      <el-color-picker
        v-if="groupColorInfo.color"
        class="lgn-color-picker"
        size="small"
        :model-value="groupColorInfo.color"
        :show-alpha="false"
        :clearable="hasCustomColor"
        :predefine="PALETTE"
        :title="(groupColorInfo.isCenter ? '此分组含对象范围节点，颜色跟随『对象范围颜色』配置，点击修改（可清除恢复默认灰）'
                  : (hasCustomColor ? '自定义颜色，点击修改（可清除恢复配色默认）' : '点击打开调色板自定义分组颜色'))"
        @update:model-value="onColorChange"
        @clear="onColorClear"
      />
      <div class="lgn-title">
        <template v-if="!isEditingTitle">
          <!-- [CUSTOM-TAG 2026-08-20] 用户自定义分组前置小『自』记号, 与系统自动分组区分 (不占额外空格).
               系统分组(领域/子领域/服务模块/ELK系统分组)无此标记, 悬停标题可看类型说明。 -->
          <span v-if="isUserCustomGroup" class="lgn-custom-tag" title="用户自定义分组">自</span>
          <!-- [中心范围 2026-08-05] 中心分组用标题文字样式区分（bold + 中心色），替代 ◆ 标识，省空间 -->
          <span class="lgn-title-text" :class="{ 'is-center': groupColorInfo.isCenter, 'is-hidden': group.visible === false }"
            @dblclick.stop="startEditTitle"
            :style="groupColorInfo.isCenter ? { color: centerScopeColorText } : {}"
            :title="groupTitleTooltip">{{ group.title }}</span>
          <span v-if="group.title === '无关系' || group.title === '有关系'"
            class="elk-hint" :title="getElkGroupHint(group._elkGroup)">ⓘ</span>
        </template>
        <input v-else ref="titleInput" v-model="editTitle" class="title-input"
          @blur="finishEditTitle" @keyup.enter="finishEditTitle" @keyup.escape="cancelEditTitle" />
      </div>
      <div class="lgn-inline-actions">
        <!-- [DEL 2026-08-19] 删除自定义分组: 仅用户自定义分组(非系统/非ELK)显示,
             默认隐藏, hover 行才显现 → 不挤占常显的启用/隐藏按钮. 置于操作区首位. -->
        <button v-if="isUserCustomGroup" class="lgn-group-del" :title="'删除分组（含其子分组与叶子）'"
          @click.stop="handleDelete">
          <AppIcon name="trash" size="sm" />
        </button>
        <!-- [ADV 2026-08-07] 启用/禁用按钮: 默认隐藏, 仅"高级设置"开关打开时展示.
             与"可见/隐藏"正交: disabled=隐藏自身+子孙上浮打平 (全量重排);
             visible=false=整棵子树不渲染 (增量隐藏, 留空位).
             [ICON 2026-08-07] 用 enabled/disabled 图标替代 eye/eye-off, 更贴合启用/禁用语义.
             折叠/展开由左侧树箭头 (collapsed) 驱动, 与启用禁用正交. -->
        <button v-if="showAdvancedSettings" class="lgn-eye" :class="{ off: group.enabled === false }"
          :title="group.enabled !== false ? '禁用（隐藏自身，子孙上浮）' : '启用（保留此层级）'" @click="toggleEnabled">
          <AppIcon :name="group.enabled !== false ? 'enabled' : 'disabled'" size="sm" />
        </button>
        <!-- [VIS 2026-08-07] 可见/隐藏: visible=false 只隐藏本分组容器框, 子节点保留 (见 collectHiddenState),
             [HIDE 2026-08-19] 不再级联子孙 (与"禁用: 子孙上浮"区分) -->
        <button class="lgn-eye" :class="{ off: group.visible === false }"
          :title="group.visible !== false ? '隐藏（仅容器框，子节点保留）' : '显示'" @click="toggleVisible">
          <AppIcon :name="group.visible !== false ? 'view' : 'hide'" size="sm" />
        </button>
      </div>
    </div>

    <div v-if="expanded && (group.children?.length || (showBusinessObjects && group.containers?.length))" class="lgn-children">
      <LayoutGroupNode
        v-for="(child, idx) in group.children" :key="child.id"
        :group="child" :depth="depth + 1" :containers="containers" :index="idx"
        :color-mapping="colorMapping"
        :show-business-objects="showBusinessObjects"
        :show-advanced-settings="showAdvancedSettings"
        @update="handleChildUpdate" @delete="handleChildDelete" @add-child="handleChildAddChild"
        @assign-container="handleChildAssignContainer" @remove-container="handleChildRemoveContainer"
        @reorder-groups="handleChildReorderGroups" @move-group="handleChildMoveGroup"
        @reorder-containers="handleChildReorderContainers" @update-container="handleChildUpdateContainer"
        @request-chart-focus="handleChildChartFocus" @subtree-action="handleChildSubtreeAction"
        @set-visible-recursive="handleChildSetVisibleRecursive" />
      <template v-if="showBusinessObjects">
      <div
        v-for="container in group.containers" :key="container.id"
        class="lgn-container-leaf"
        :class="{ 'leaf-disabled': container.enabled === false }"
        :title="getContainerName(container)"
        draggable="true"
        @click="handleLeafClick(container, $event)"
        @dragstart="handleContainerDragStart($event, container)"
        @dragend="handleContainerDragEnd"
        @dragover.prevent="handleContainerDragOver"
        @drop="handleContainerDrop($event, container)"
      >
        <!-- [ALIGN 2026-08-19] 与分组行(.lgn-row)对齐: 分组行先有 caret(18px) 再标题,
             叶子行补同宽占位, 使 file 图标/名称列与分组标题列对齐; 高度统一 28px. -->
        <span class="lgn-leaf-caret-placeholder"></span>
        <AppIcon name="file" size="xs" />
        <span class="leaf-name">{{ getContainerName(container) }}</span>
        <div class="lgn-leaf-actions">
          <!-- [ALIGN 2026-08-19] 操作按钮与分组行按钮同尺寸(22px), 右侧对齐 -->
          <button v-if="showAdvancedSettings" class="lgn-leaf-toggle" :class="{ off: container.enabled === false }"
            :title="container.enabled !== false ? '点击禁用（禁用即从图表移除）' : '点击启用'"
            @click.stop="toggleContainerEnabled(container)">
            <AppIcon :name="container.enabled !== false ? 'enabled' : 'disabled'" size="xs" />
          </button>
          <button class="lgn-leaf-toggle" :class="{ off: container.visible === false }"
            :title="container.visible !== false ? '隐藏' : '显示'"
            @click.stop="toggleContainerVisible(container)">
            <AppIcon :name="container.visible !== false ? 'view' : 'hide'" size="xs" />
          </button>
        </div>
      </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { AppIcon } from '@/components/common/AppIcon'
import { useGroupDisplay } from '@/composables/useGroupDisplay'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'

// [COLOR 2026-08-05] 分组级调色板预设色（与 COLOR_SCHEMES.default 前段一致，作为快速取色）
const PALETTE = ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB', '#FF6B6B', '#4ECDC4']

const props = defineProps({
  group: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  containers: { type: Array, default: () => [] },
  index: { type: Number, default: -1 },
  colorMapping: { type: Object, default: () => ({}) },
  // [BO 2026-08-07] 是否显示业务对象叶子节点列表 (仅影响面板树, 由 LayoutControlPanel 顶部开关控制)
  showBusinessObjects: { type: Boolean, default: false },
  // [ADV 2026-08-07] 高级设置开关: 打开时才展示"启用/禁用"按钮 (默认隐藏, 避免噪音)
  showAdvancedSettings: { type: Boolean, default: false }
})

const emit = defineEmits(['update', 'delete', 'add-child', 'assign-container', 'remove-container', 'reorder-groups', 'remove-node', 'move-group', 'update-container', 'reorder-containers', 'request-chart-focus', 'subtree-action', 'set-visible-recursive'])

// [FIX 2026-08-05] 传 getter 而非 props.colorMapping 值：
//   useGroupDisplay 闭包需实时读取当前 colorMapping (chartDataSnapshot.groupColorMap
//   每次 re-colorize 都是新对象)，否则清空自定义色后色点回不到默认分组色。
const { getElkGroupHint, getGroupColor } = useGroupDisplay(() => props.colorMapping)

const diagramConfigStore = useDiagramConfigStore()

// [COLOR 2026-08-05] 分组当前展示色 + 写入键（custom 分组不显示色点）
//   isCenter=true: 该分组属于中心范围且区分开启，色点显示 centerScopeColor，改色写 centerScopeColor。
const groupColorInfo = computed(() => getGroupColor(props.group))
// [中心范围 2026-08-05] 中心分组标题文字用中心色（替代 ◆ 标识），与灰点同源
const centerScopeColorText = computed(() => {
  const cc = diagramConfigStore.centerScopeColor
  return (cc && cc !== 'gray') ? cc : '#808080'
})
const hasCustomColor = computed(() => {
  // [CUSTOM-COLOR 2026-08-19] 用户自定义分组: 色点始终可清除 (恢复默认 group.style)
  if (props.group.groupType === 'custom' && !(props.group._elkGroup === 'inner' || props.group._elkGroup === 'boundary')) return true
  const info = groupColorInfo.value
  if (info.isCenter) return true // 中心范围：允许清除恢复默认 centerScopeColor
  return !!info.key && !!diagramConfigStore.customColors[info.key]
})

// 选色：custom 分组 → 写 group.style (容器/节点复用); 中心范围分组 → 写 centerScopeColor（方案C 联动）；
//   否则写 store.customColors[分组key]（增量变色）
function onColorChange(color) {
  if (!color) { onColorClear(); return }
  if (props.group.groupType === 'custom' && !(props.group._elkGroup === 'inner' || props.group._elkGroup === 'boundary')) {
    const style = { ...(props.group.style || {}), fill: color, stroke: color }
    emit('update', { id: props.group.id, updates: { style } })
    return
  }
  const info = groupColorInfo.value
  if (info.isCenter) {
    diagramConfigStore.updateCenterScopeColor(color || '#808080')
    return
  }
  const key = info.key
  if (!key) return
  diagramConfigStore.updateCustomColors({ ...diagramConfigStore.customColors, [key]: color })
}

// 清除：custom 分组 → 恢复默认 group.style；中心范围分组 → 恢复默认 centerScopeColor；否则删除该分组自定义色
function onColorClear() {
  if (props.group.groupType === 'custom' && !(props.group._elkGroup === 'inner' || props.group._elkGroup === 'boundary')) {
    // [FIX 2026-08-19] defStyle 必须放在展开的 group.style **之后**, 才能覆盖重置 fill/stroke.
    //   原 `{ ...defStyle, ...group.style }` 顺序相反 → 用户已设置的 fill 覆盖默认白 → 清空无效.
    const defStyle = { fill: '#ffffff', stroke: '#666666', strokeWidth: 2, strokeDasharray: '' }
    emit('update', { id: props.group.id, updates: { style: { ...(props.group.style || {}), ...defStyle } } })
    return
  }
  const info = groupColorInfo.value
  if (info.isCenter) {
    diagramConfigStore.updateCenterScopeColor('#808080')
    return
  }
  const key = info.key
  if (!key) return
  const next = { ...diagramConfigStore.customColors }
  delete next[key]
  diagramConfigStore.updateCustomColors(next)
}

// [EXPAND 2026-08-05] 树的展开态完全由 group.collapsed 驱动 (单一数据源):
//   collapsed !== true → 展开; collapsed === true → 收起. 默认(未定义) → 展开.
//   之前用 props.depth<1 默认收起深层, 且与 group.collapsed 脱节 → 树收起但图表全展开,
//   不一致. 现展开态跟随数据, 图表与树始终同步.
const expanded = ref(props.group.collapsed !== true)
const isEditingTitle = ref(false)
const editTitle = ref('')
const titleInput = ref(null)
const isRowDragOver = ref(false)
const isLeftDropZone = ref(false)  // [DROP-ZONE 2026-08-20] 拖拽悬停在本行左侧(将成子分组)

// [EXPAND 2026-08-05] 跟随 group.collapsed 数据变化 (模板应用/全部展开收起/外部写回),
//   保证树的展开态始终反映图表渲染用的 collapsed 状态.
watch(() => props.group.collapsed, (val) => {
  expanded.value = val !== true
})

const hasChildren = computed(() => {
  const childCount = props.group.children?.length || 0
  const containerCount = props.group.containers?.length || 0
  return childCount > 0 || containerCount > 0
})

// [SYS 2026-08-07] 系统自动分组识别: ELK 布局自动生成的无关系/有关系分组
const isSystemAuto = computed(() => {
  const elk = props.group._elkGroup
  return elk === 'inner' || elk === 'boundary'
})

// [DEL 2026-08-19] 用户自定义分组(可删除): groupType=custom 且非 ELK 系统自动分组.
//   系统分组(领域/子领域/服务模块)与 ELK 分组不允许删除.
const isUserCustomGroup = computed(() => {
  return props.group.groupType === 'custom' && !isSystemAuto.value
})
// [CUSTOM-TAG 2026-08-20] 分组类型悬停提示 (中心范围与类型组合), 零占位区分自定义/系统分组
const groupTitleTooltip = computed(() => {
  const parts = []
  if (groupColorInfo.value.isCenter) parts.push('对象范围分组：颜色跟随『对象范围颜色』配置')
  if (isUserCustomGroup.value) parts.push('用户自定义分组（可拖拽调整层级/排序，可删除）')
  else if (isSystemAuto.value) parts.push('系统自动分组（无关系/有关系）')
  else if (props.group.groupType === 'domain') parts.push('领域 · 系统分组')
  else if (props.group.groupType === 'subDomain') parts.push('子领域 · 系统分组')
  else if (props.group.groupType === 'serviceModule') parts.push('服务模块 · 系统分组')
  else parts.push('系统分组')
  return parts.join(' · ')
})

// 容器叶子节点名称：兼容 name / title / code 等多种字段
function getContainerName(container) {
  if (!container) return ''
  return container.name || container.title || container.code || container.id || ''
}

function toggleExpanded() {
  if (hasChildren.value) {
    const nextExpanded = !expanded.value
    expanded.value = nextExpanded
    // [EXPAND 2026-08-05] 树折叠箭头同时驱动渲染折叠 (与 enabled 正交):
    //   收起(expanded=false) → collapsed=true  → 图表中该层级上提为聚合彩色节点;
    //   展开(expanded=true)  → collapsed=false → 恢复为容器 (内部渲染启用子孙).
    //   collapsed 由 computeUplift 视为"强制上提"条件, 无需改子孙 enabled.
    emit('update', { id: props.group.id, updates: { collapsed: !nextExpanded } })
    // [EXPAND-SYNC 2026-08-20] 面板箭头折叠/展开 = 用户显式干预分组展开层级.
    //   必须标记 groupManualSet, 与图表双击/右键链路 (MermaidComponent.executeContextMenuAction)
    //   一致: 否则 EmbeddedChartView.layoutControlConfig computed 在 groupManualSet=false 且
    //   expandLevelUserSet=false 时仍执行 applyDefaultExpandByCount(mergedGroups) 覆盖本处
    //   修改后的 collapsed → 面板展开/折叠图表无反应 (用户反馈).
    diagramConfigStore.markGroupManualSet()
  }
}

function startEditTitle() {
  editTitle.value = props.group.title
  isEditingTitle.value = true
  nextTick(() => { titleInput.value?.focus(); titleInput.value?.select() })
}
function finishEditTitle() {
  if (editTitle.value.trim() && editTitle.value !== props.group.title) {
    emit('update', { id: props.group.id, updates: { title: editTitle.value.trim() } })
  }
  isEditingTitle.value = false
}
function cancelEditTitle() { isEditingTitle.value = false }

// [FOCUS 2026-08-06] 分组行单击 → 图表高亮居中 (原为双击).
//   单击位置区分: 编辑标题输入框/颜色选择器/眼睛/展开箭头等交互控件 → 不触发联动;
//   其余行内区域 (含标题文字) → 聚焦图表元素。
//   [FIX 2026-08-06] 领域/子领域/服务模块分组行在图中通常渲染为 subgraph (容器),
//   标题即分组名. 故统一发 type:'container' + 分组标题 (title), 让容器按 label 文本命中;
//   若折叠/上提后渲染为单节点, 由 highlightTargetElement 的跨类型兜底按标题命中节点。
//   [FIX 2026-08-06] 之前用 elementCode (编码) 作 id, 而 subgraph 标题是分组名, 匹配不到;
//   且服务模块行误发 type:'node' (其实际渲染为容器), 导致领域/子领域/服务模块高亮失效。
function handleRowClick(e) {
  if (e.target.closest('.title-input') || e.target.closest('.lgn-color-picker') || e.target.closest('.lgn-eye') || e.target.closest('.lgn-group-del') || e.target.closest('.lgn-caret') || e.target.closest('.el-dropdown') || e.target.closest('.lgn-multistate')) return
  emit('request-chart-focus', {
    type: 'container',
    id: props.group.title || props.group.elementCode
  })
}

// [FOCUS 2026-08-06] 叶子节点单击 → 图表高亮居中 (原为双击).
//   叶子节点可能是业务对象 (BO图, 渲染为 g.node, 带 data-code=elementCode)
//   或服务模块 (SM图, 渲染为 subgraph 容器, 标题为模块名)。
//   [FIX 2026-08-06] 服务模块叶子按容器匹配 (type:'container' + 标题);
//   业务对象叶子按节点匹配 (type:'node' + elementCode)。渲染形态有出入时由
//   highlightTargetElement 的跨类型兜底处理。
function handleLeafClick(container, e) {
  if (e.target.closest('.lgn-leaf-actions') || e.target.closest('.lgn-leaf-toggle')) return
  const isServiceModuleLeaf = container.groupType === 'serviceModule'
    || container.elementRef?.type === 'serviceModule'
    || container.elementRef?.type === 'SERVICE_MODULE'
  if (isServiceModuleLeaf) {
    emit('request-chart-focus', {
      type: 'container',
      id: container.title || container.name || container.elementRef?.code || container.code || container.id || getContainerName(container)
    })
  } else {
    emit('request-chart-focus', {
      type: 'node',
      id: container.elementCode || container.elementRef?.code || container.code || container.id || getContainerName(container)
    })
  }
}

// [VIS 2026-08-07] 可见/隐藏: 递归切换自身+所有子孙的 visible (面板树状态与渲染一致)
function toggleVisible() {
  emit('set-visible-recursive', { id: props.group.id, visible: props.group.visible === false })
}
// [EXPAND 2026-08-05] 启用/禁用开关 (替代原多态下拉): 只切自身 enabled,
//   是否上提/隐藏由渲染引擎按 enabled 自动推导.
function toggleEnabled() {
  emit('update', { id: props.group.id, updates: { enabled: props.group.enabled === false } })
}
function handleDelete() { emit('delete', props.group.id) }

function handleChildUpdate(d) { emit('update', d) }
function handleChildDelete(id) { emit('delete', id) }
function handleChildAddChild(parentId) { emit('add-child', parentId) }
function handleChildAssignContainer(d) { emit('assign-container', d) }
function handleChildRemoveContainer(d) { emit('remove-container', d) }
function handleChildReorderGroups(d) { emit('reorder-groups', d) }
function handleChildMoveGroup(d) { emit('move-group', d) }
function handleChildReorderContainers(d) { emit('reorder-containers', d) }
function handleChildUpdateContainer(d) { emit('update-container', d) }
function handleChildChartFocus(d) { emit('request-chart-focus', d) }
function handleChildSubtreeAction(d) { emit('subtree-action', d) }
// [VIS 2026-08-07] 子节点请求级联可见性切换 → 冒泡到 LayoutControlPanel 统一处理
function handleChildSetVisibleRecursive(d) { emit('set-visible-recursive', d) }

function handleGroupDragStart(event) {
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'group',
    groupId: props.group.id,
    sourceGroupId: props.group.id,
    sourceIndex: props.index,
    parentId: props.group.parentId
  }))
  // [MOVE-TOP 2026-08-19] 通知顶层放置区显示 (dragstart 不冒泡, 经 window 自定义事件,
  //   LayoutControlPanel 监听后显现顶层放置区, 拖拽结束再隐藏).
  // [DRAG-FIX 2026-08-19] 延迟到宏任务再显示: dragstart 同步修改 DOM (显示放置区/
  //   容器 padding 变化) 会让浏览器在拖拽图像创建前取消原生拖拽会话
  //   (用户反馈"新增后无法拖拽", 实测 dragstart→dragend 仅 ~2ms). 拖拽会话建立后再显示.
  const _show = () => { try { window.dispatchEvent(new CustomEvent('lcp-group-drag', { detail: { dragging: true } })) } catch (e) {} }
  setTimeout(_show, 0)
  event.stopPropagation()
}
function handleGroupDragEnd() {
  try { window.dispatchEvent(new CustomEvent('lcp-group-drag', { detail: { dragging: false } })) } catch (e) {}
}

// [LEAF 2026-08-04] 业务对象叶子节点可拖拽（在各分组间移动）+ 可见/禁用开关
function handleContainerDragStart(event, container) {
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'container',
    container,
    sourceType: 'group',
    sourceGroupId: props.group.id
  }))
  event.stopPropagation()
}
function handleContainerDragEnd() {}

// [REORDER 2026-08-04] 群组内叶子容器同级重排：拖到同组另一个容器上时重排
function handleContainerDragOver() {}
function handleContainerDrop(event, targetContainer) {
  event.preventDefault()
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    if (data.type !== 'container' || !data.container) return
    if (data.sourceGroupId === props.group.id && data.container.id !== targetContainer.id) {
      emit('reorder-containers', {
        groupId: props.group.id,
        sourceContainerId: data.container.id,
        targetContainerId: targetContainer.id
      })
    }
  } catch (e) { /* 忽略非法拖拽数据 */ }
}

function toggleContainerEnabled(container) {
  emit('update-container', {
    groupId: props.group.id,
    containerId: container.id,
    updates: { enabled: container.enabled === false }
  })
}
function toggleContainerVisible(container) {
  emit('update-container', {
    groupId: props.group.id,
    containerId: container.id,
    updates: { visible: container.visible === false }
  })
}

// [DROP-ZONE 2026-08-20] 拖拽 group 悬停位置: leftZone=true 表示拖到本行左侧区(将成子分组).
function handleRowDragOver(event) {
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    if (data.type === 'container') {
      isRowDragOver.value = true
    } else if (data.type === 'group') {
      const rect = event.currentTarget.getBoundingClientRect()
      const dropX = event.clientX - (rect ? rect.left : 0)
      isRowDragOver.value = true
      isLeftDropZone.value = rect ? (dropX < rect.width * 0.35) : false
    }
  } catch { isRowDragOver.value = true }
}
function handleRowDragLeave() { isRowDragOver.value = false; isLeftDropZone.value = false }
function handleRowDrop(event) {
  isRowDragOver.value = false
  isLeftDropZone.value = false
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    if (data.type === 'container') {
      const container = data.container
      if (data.sourceType === 'group' && data.sourceGroupId && data.sourceGroupId !== props.group.id) {
        emit('remove-container', { groupId: data.sourceGroupId, containerId: container.id })
      }
      emit('assign-container', { groupId: props.group.id, container })
    } else if (data.type === 'group') {
      // [TREE 2026-08-04] 支持拖拽 group 到当前 group 作为子分组
      // [REORDER 2026-08-04] 同级（parentId 相同）拖拽 → 重排；跨级 → 作为子分组
      // [DROP-ZONE 2026-08-20] 根级分组(parentId 相同)之间: 拖到行的左侧区 = 成为子分组(move-group);
      //   拖到右侧区 = 同级重排(reorder-groups). 因为根级行无缩进, 左侧本是 caret/icon 区,
      //   天然作为"拖入成为子分组"的命中区 (用户心智: 拖到分组"里面/下面"= 成为其子分组).
      if (data.groupId !== props.group.id) {
        const rect = event.currentTarget.getBoundingClientRect()
        const dropX = event.clientX - (rect ? rect.left : 0)
        const isLeftZone = rect ? (dropX < rect.width * 0.35) : false
        if (data.parentId === props.group.parentId) {
          if (isLeftZone) {
            emit('move-group', { sourceGroupId: data.groupId, targetGroupId: props.group.id })
          } else {
            emit('reorder-groups', {
              sourceGroupId: data.groupId,
              targetGroupId: props.group.id,
              parentId: props.group.parentId
            })
          }
        } else {
          emit('move-group', { sourceGroupId: data.groupId, targetGroupId: props.group.id })
        }
      }
    }
  } catch (e) { console.error('Failed to parse drop data:', e) }
}
</script>

<style scoped lang="scss">
.lgn-row {
  display: flex; align-items: center; gap: 4px; height: 28px;
  padding: 0 6px; border-radius: 4px; cursor: grab; user-select: none;
  position: relative;  // [DROP-ZONE 2026-08-20] 供 .lgn-drop-into-hint 绝对定位锚定
  &:active { cursor: grabbing; }
  &:hover { background: var(--color-primary-bg); }
  &.row-drag-over { background: var(--color-success-bg); outline: 1px dashed var(--color-success); }
  // [DROP-ZONE 2026-08-20] 拖拽 group 悬停左侧区 → 将成为子分组, 左侧高亮引导.
  &.is-left-drop-zone { box-shadow: inset 3px 0 0 var(--color-primary); }
  .lgn-drop-into-hint {
    position: absolute; left: 34px; font-size: 11px; color: var(--color-primary);
    background: var(--color-primary-bg); padding: 1px 6px; border-radius: 3px;
    pointer-events: none; white-space: nowrap; z-index: 3;
  }
  &.is-hidden { opacity: 0.5; }
}
.lgn-caret { width: 18px; height: 18px; border: none; background: transparent; cursor: pointer; color: var(--color-text-tertiary); padding: 0; flex-shrink: 0; }
.caret-arrow { display: inline-block; transition: transform 0.15s; }
.lgn-caret.expanded .caret-arrow { transform: rotate(90deg); }
.caret-placeholder { display: inline-block; width: 8px; }
.lgn-color-picker {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  :deep(.el-color-picker__trigger) { width: 22px; height: 22px; padding: 1px; border-radius: 4px; }
  :deep(.el-color-picker__color) { border-radius: 3px; }
  :deep(.el-color-picker__icon) { display: none; }
}
.lgn-title { flex: 1; display: flex; align-items: center; gap: 4px; overflow: hidden;
  white-space: nowrap; text-overflow: ellipsis; }
/* [CUSTOM-TAG 2026-08-20] 自定义分组前置小『自』记号: 与系统自动分组区分, 占用极小不撑排版 */
.lgn-custom-tag {
  display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto;
  font-size: 9px; line-height: 1; font-weight: 600; padding: 2px 3px; border-radius: 3px;
  color: var(--color-primary); background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-4, rgba(24,144,255,.35));
  user-select: none; cursor: default;
}
.lgn-title-text { font-size: var(--font-size-sm); font-weight: 500; overflow: hidden; text-overflow: ellipsis; }
/* [中心范围 2026-08-05] 中心分组标题：加粗 + 中心色（替代 ◆ 标识），行内样式绑定 centerScopeColor */
.lgn-title-text.is-center { font-weight: 700; }
/* [VIS 2026-08-07] 隐藏分组标题划线 + 半透明，与图例隐藏风格一致 */
.lgn-title-text.is-hidden { text-decoration: line-through; opacity: 0.6; }
.elk-hint { font-size: var(--font-size-xs); color: var(--color-text-tertiary); cursor: help; }
.title-input { padding: 2px 6px; border: 1px solid var(--color-primary); border-radius: 4px; font-size: var(--font-size-sm); min-width: 100px; }
.lgn-inline-actions { display: flex; align-items: center; gap: 2px; opacity: 1; }
.lgn-eye, .lgn-delete, .lgn-collapse, .lgn-multistate {
  display: flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border: none; background: transparent; color: var(--color-text-tertiary); cursor: pointer; border-radius: 3px;
  &:hover { background: var(--color-bg-secondary); color: var(--color-text-primary); }
}
/* [DEL 2026-08-19] 删除按钮: 默认隐藏, hover 行才显现, 避免挤占常显的启用/隐藏按钮 */
.lgn-group-del {
  display: flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border: none; background: transparent; color: var(--color-text-tertiary); cursor: pointer; border-radius: 3px;
  opacity: 0; transition: opacity .12s;
  &:hover { background: var(--color-bg-secondary); color: var(--color-error); }
}
.lgn-row:hover .lgn-group-del { opacity: 1; }
.lgn-eye.off, .lgn-collapse.off, .lgn-multistate.off { color: var(--color-text-disabled); }
.lgn-delete:hover { color: var(--color-error); }
.lgn-context-anchor { display: none; }

/* [TREE 2026-08-04] 层级进深：子节点缩进 + 左侧层级引导线 */
.lgn-children {
  margin-left: 14px;
  padding-left: 8px;
  border-left: 1px solid var(--color-border-light);
}

/* 容器叶子节点（如服务模块下的业务对象） */
.lgn-container-leaf {
  display: flex; align-items: center; gap: 4px; height: 28px; padding: 0 6px;
  border-radius: 4px; font-size: var(--font-size-xs); color: var(--color-text-secondary);
  overflow: hidden; user-select: none; cursor: grab;
  &:hover { background: var(--color-bg-secondary); color: var(--color-text-primary); }
  &:active { cursor: grabbing; opacity: 0.7; }
  &.leaf-disabled { opacity: 0.5; }
  /* [ALIGN 2026-08-19] 与分组行 .lgn-caret 同宽占位, 使名称列与分组标题列对齐 */
  .lgn-leaf-caret-placeholder { width: 18px; flex-shrink: 0; }
  .leaf-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .lgn-leaf-actions { display: flex; align-items: center; gap: 2px; opacity: 1; }
  .lgn-leaf-toggle {
    display: flex; align-items: center; justify-content: center; width: 22px; height: 22px;
    border: none; background: transparent; color: var(--color-text-tertiary); cursor: pointer; border-radius: 3px;
    &:hover { background: var(--color-bg-secondary); color: var(--color-text-primary); }
    &.off { color: var(--color-text-disabled); }
  }
}
</style>