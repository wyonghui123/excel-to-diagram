<template>
  <PageShell :title="config.title" :subtitle="config.subtitle">
    <AppCard :title="config.cardTitle">
      <!-- 路由 + YAML 即页面：列 / 筛选 / 徽标 / 动作 / 表单 / 指标条
           全部来自 objectType 对应的 ui_view_config；本视图不含业务逻辑 -->
      <MetaResourcePage
        :key="objectType"
        :object-type="objectType"
        :form-hint="config.formHint || ''"
      />
    </AppCard>
  </PageShell>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { PageShell, AppCard, MetaResourcePage } from '@/components/common'

defineOptions({ name: 'IntegrationResourceView' })

const route = useRoute()
const config = computed(() => route.meta.integrationResource || {})
const objectType = computed(() => config.value.objectType)
</script>
