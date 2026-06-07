<template>
  <div class="enum-type-detail">
    <ObjectPageWithChildren
      :object-type="'enum_type'"
      :record-id="enumTypeId"
      :title="pageTitle"
      :subtitle="data?.id || ''"
      :loading="loading"
      :show-back-button="true"
      :breadcrumbs="breadcrumbs"
      :sections="sectionsConfig"
      :form-data="formData"
      :field-definitions="fieldDefinitions"
      :child-sections="childSections"
      @back="handleBack"
      @tab-change="handleTabChange"
      @field-update="handleFieldUpdate"
      @navigate="handleBreadcrumbNavigate"
    >
      <template #actions>
        <el-button @click="handleEdit">编辑</el-button>
        <el-button type="danger" @click="handleDelete">删除</el-button>
      </template>
    </ObjectPageWithChildren>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/appStore'
import { ElMessage } from 'element-plus'
import { ObjectPageWithChildren } from '@/components/common'
import { boService } from '@/services/boService'
import metaService from '@/services/metaService'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const enumTypeId = computed(() => route.params.id)
const editMode = computed(() => route.query.mode === 'edit')

const loading = ref(false)
const data = ref(null)
const parentDetail = ref(null)

const pageTitle = computed(() => {
  if (editMode.value) return `编辑: ${data.value?.name || '枚举类型'}`
  return data.value?.name || '枚举类型详情'
})

const breadcrumbs = computed(() => [
  { label: '系统管理', to: '/system' },
  { label: '业务配置', to: '/business-config' },
  { label: '枚举管理', to: '/business-config?tab=enums' },
  { label: data.value?.name || '枚举类型详情' }
])

function handleBreadcrumbNavigate(crumb) {
  if (crumb.to) {
    router.push(crumb.to)
  }
}

const formData = reactive({
  id: '',
  name: '',
  category: '',
  mutability: '',
  description: ''
})

const fieldDefinitions = computed(() => ({
  id: { label: '编码', type: 'text', editable: false, required: true },
  name: { label: '名称', type: 'text', editable: editMode.value, required: true },
  category: {
    label: '分类', type: 'select',
    options: [
      { label: '系统', value: 'system' },
      { label: '业务', value: 'business' },
      { label: '用户', value: 'user' }
    ],
    editable: editMode.value
  },
  mutability: {
    label: '可维护性', type: 'select',
    options: [
      { label: '系统定义（不可修改）', value: 'system' },
      { label: '业务定义（可修改）', value: 'business' },
      { label: '用户定义（可修改）', value: 'user' }
    ],
    editable: false
  },
  description: { label: '描述', type: 'textarea', editable: editMode.value }
}))

const sectionsConfig = computed(() => [
  {
    key: 'basic',
    label: '基本信息',
    icon: 'info',
    type: 'standard',
    fieldGroups: [
      { title: '标识信息', icon: 'tag', layout: 'grid-2', fields: ['id', 'name'] },
      { title: '分类与权限', icon: 'settings', layout: 'grid-2', fields: ['category', 'mutability'] },
      { title: '详细描述', icon: 'file-text', layout: 'grid-1', collapsed: true, fields: ['description'] }
    ]
  }
])

const childSections = computed(() => {
  return [
    {
      child_object: 'enum_value',
      title: '枚举值',
      display: 'expandable',
      pageSize: 20,
      useMetaList: true,
      enableDetail: true,
      enableAutoCrud: true,
      rowMutability: data.value?.mutability === 'system' ? 'locked' : null
    }
  ]
})

function handleBack() {
  const tabId = route.path
  appStore.closeTab(tabId)

  const remaining = appStore.tabs
  if (remaining.length === 0) {
    router.push('/')
  } else {
    const activeTab = remaining.find(t => t.id === appStore.activeTabId)
    if (activeTab?.path) {
      router.push(activeTab.path)
    } else {
      router.push({ name: 'business-config' })
    }
  }
}

function handleTabChange(tabKey) {
  console.log('Tab 切换:', tabKey)
}

function handleFieldUpdate(updateData) {
  Object.assign(formData, updateData)
}

async function handleEdit() {
  router.push(`/${objectType.value}/${enumTypeId.value}/edit`)
}

async function handleDelete() {
  // 删除逻辑
}

async function loadData() {
  if (!enumTypeId.value) return

  loading.value = true
  try {
    const result = await boService.read('enum_type', enumTypeId.value)
    if (result.success) {
      data.value = result.data
      parentDetail.value = result.data

      Object.assign(formData, {
        id: result.data.id || '',
        name: result.data.name || '',
        category: result.data.category || '',
        mutability: result.data.mutability || '',
        description: result.data.description || ''
      })
    } else {
      ElMessage.error(result.message || '加载失败')
    }
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.enum-type-detail {
  height: 100%;
  padding: var(--spacing-md);
}
</style>
