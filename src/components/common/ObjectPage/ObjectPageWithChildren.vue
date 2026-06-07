<template>
  <PageShell
    :title="title"
    :subtitle="subtitle"
    :breadcrumbs="breadcrumbs"
    :show-back-button="showBackButton"
    @back="$emit('back')"
    @navigate="$emit('navigate', $event)"
  >
    <template #title-bar-actions>
      <slot name="actions" />
    </template>

    <div class="opwc-content">
      <ObjectPage
        :title="title"
        :subtitle="subtitle"
        :status="status"
        :status-type="statusType"
        :show-back-button="false"
        :tabs="tabs"
        :active-tab="activeTab"
        :size="size"
        :sections="mergedSections"
        :form-data="formData"
        :field-definitions="fieldDefinitions"
        :card-size="cardSize"
        :loading="loading"
        @tab-change="$emit('tab-change', $event)"
        @field-update="$emit('field-update', $event)"
      >
        <template v-for="(_, name) in $slots" #[name]="slotData">
          <slot :name="name" v-bind="slotData || {}" />
        </template>

        <template #sections>
          <section
            v-for="section in childSections"
            :key="section.child_object"
            class="op-section op-section--always"
          >
            <div class="op-section-header">
              <AppIcon v-if="section.icon" :name="section.icon" size="sm" />
              <h3>{{ section.title || getChildObjectLabel(section.child_object) }}</h3>
            </div>
            <div class="op-section-content">
              <slot :name="`section-${section.child_object}`">
                <ObjectChildSection
                  :parent-object-type="objectType"
                  :child-object-type="section.child_object"
                  :parent-id="recordId"
                  :config="section"
                  :title="section.title"
                  :create-label="section.createLabel || '新增'"
                  :show-create="section.showCreate !== false"
                  :show-actions="section.showActions !== false"
                  :display-mode="section.display || 'expandable'"
                  :page-size="section.pageSize || 10"
                  @create="$emit('child-create', section.child_object)"
                  @edit="$emit('child-edit', { childObjectType: section.child_object, ...$event })"
                  @delete="$emit('child-delete', { childObjectType: section.child_object, ...$event })"
                  @row-click="$emit('child-row-click', { childObjectType: section.child_object, ...$event })"
                  @action="$emit('child-action', { childObjectType: section.child_object, ...$event })"
                  @refresh="$emit('child-refresh', section.child_object)"
                  @success="$emit('child-success', { childObjectType: section.child_object, ...$event })"
                />
              </slot>
            </div>
          </section>
        </template>
      </ObjectPage>
    </div>
  </PageShell>
</template>

<script setup>
import { computed } from 'vue'
import { PageShell } from '@/components/common/PageShell'
import ObjectPage from './ObjectPage.vue'
import { ObjectChildSection } from '@/components/common/ObjectChildSection'
import { AppIcon } from '@/components/common/AppIcon'

const props = defineProps({
  objectType: { type: String, required: true },
  recordId: { type: [String, Number], required: true },
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  status: { type: String, default: '' },
  statusType: { type: String, default: 'default' },
  breadcrumbs: { type: Array, default: () => [] },
  tabs: { type: Array, default: () => [] },
  activeTab: { type: [String, Number], default: null },
  showBackButton: { type: Boolean, default: true },
  size: { type: String, default: 'md' },
  sections: { type: Array, default: () => [] },
  formData: { type: Object, default: () => ({}) },
  fieldDefinitions: { type: Object, default: () => ({}) },
  cardSize: { type: String, default: 'sm' },
  childSections: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
})

defineEmits([
  'back',
  'navigate',
  'tab-change',
  'field-update',
  'child-create',
  'child-edit',
  'child-delete',
  'child-row-click',
  'child-action',
  'child-refresh',
  'child-success'
])

const mergedSections = computed(() => {
  return props.sections
})

function getChildObjectLabel(childObjectType) {
  return childObjectType
}
</script>

<style scoped lang="scss">
.opwc-content {
  height: 100%;
  overflow: auto;
}
</style>
