<template>
  <div class="product-detail-page">
    <ObjectPageWithChildren
      :object-type="objectType"
      :record-id="recordId"
      :title="parentDetail.name"
      :subtitle="parentDetail.code"
      :status="parentDetail.is_active ? '启用' : '禁用'"
      :status-type="parentDetail.is_active ? 'success' : 'default'"
      :breadcrumbs="breadcrumbs"
      :tabs="tabs"
      :sections="sections"
      :form-data="formData"
      :field-definitions="fieldDefinitions"
      :child-sections="childSections"
      show-back-button
      @back="handleBack"
      @tab-change="handleTabChange"
      @field-update="handleFieldUpdate"
      @child-create="handleChildCreate"
      @child-edit="handleChildEdit"
      @child-delete="handleChildDelete"
      @child-success="handleChildSuccess"
    >
      <template #actions>
        <el-button @click="handleEdit">编辑</el-button>
        <el-button type="danger" @click="handleDelete">删除</el-button>
      </template>
    </ObjectPageWithChildren>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ObjectPageWithChildren } from '@/components/common'
import { useParentChild } from '@/composables/useParentChild'
import metaService from '@/services/metaService'

const route = useRoute()
const router = useRouter()

const objectType = 'product'
const recordId = computed(() => route.params.id)

const parentDetail = ref({})
const formData = ref({})
const fieldDefinitions = ref({})

const {
  parentDetail: parentDetailData,
  breadcrumbs,
  loadParent
} = useParentChild(objectType, 'version', {
  parentId: recordId,
  autoLoadChild: false
})

const sections = computed(() => {
  return [
    {
      key: 'basic',
      label: '基本信息',
      icon: 'info',
      display: 'always',
      fieldGroups: [
        {
          title: '基本信息',
          fields: ['name', 'code', 'description', 'is_active']
        }
      ]
    },
    {
      key: 'system',
      label: '系统信息',
      icon: 'settings',
      fieldGroups: [
        {
          title: '审计信息',
          fields: ['created_at', 'updated_at', 'created_by', 'updated_by']
        }
      ]
    }
  ]
})

const childSections = computed(() => {
  return metaService.getChildSections(objectType) || []
})

const tabs = computed(() => {
  return sections.value
    .filter(s => s.display !== 'always')
    .map(s => ({ key: s.key, label: s.label }))
})

function handleBack() {
  router.push(`/${objectType}`)
}

function handleTabChange(tabKey) {
  console.log('Tab changed:', tabKey)
}

function handleFieldUpdate({ field, value }) {
  formData.value[field] = value
}

function handleChildCreate(childObjectType) {
  console.log('Create child:', childObjectType)
}

function handleChildEdit({ childObjectType, row }) {
  console.log('Edit child:', childObjectType, row)
}

async function handleChildDelete({ childObjectType, row }) {
  console.log('Delete child:', childObjectType, row)
}

function handleChildSuccess({ childObjectType, type, data }) {
  ElMessage.success('操作成功')
}

async function handleEdit() {
  router.push(`/${objectType}/${recordId.value}/edit`)
}

async function handleDelete() {
  // 删除逻辑
}

onMounted(async () => {
  await loadParent()
  parentDetail.value = parentDetailData.value || {}

  const metaResult = await metaService.getViewConfig(objectType)
  if (metaResult.success) {
    fieldDefinitions.value = metaResult.data.fields || {}
  }
})
</script>

<style scoped>
.product-detail-page {
  height: 100%;
}
</style>
