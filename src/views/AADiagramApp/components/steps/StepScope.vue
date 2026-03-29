<template>
  <div class="step-scope">
    <div class="scope-panel">
      <div class="panel-header-simple">
        <AppButton type="primary" @click="$emit('next')">下一步 →</AppButton>
      </div>
      <div class="panel-body no-padding-top">
        <DataPreview
          v-if="previewData"
          :preview-data="previewData"
          :raw-data="rawData"
          :model-value="modelValue"
          @update:model-value="$emit('update:modelValue', $event)"
          @update:selected-stats="$emit('update:selectedStats', $event)"
        />
      </div>
    </div>
  </div>
</template>

<script>
import { AppButton } from '../../../../components/common'
import DataPreview from '../../../../components/DataPreview.vue'

export default {
  name: 'StepScope',
  components: { AppButton, DataPreview },
  props: {
    previewData: Object,
    rawData: Object,
    modelValue: Array
  },
  emits: ['update:modelValue', 'update:selectedStats', 'next', 'prev']
}
</script>

<style scoped lang="scss">
@import '../../../../styles/mixins.scss';

.step-scope {
  height: 100%;
}

.scope-panel {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-header-simple {
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: flex-end;
}

.panel-body {
  flex: 1;
  padding: var(--spacing-lg);
  overflow: auto;

  &.no-padding-top {
    padding-top: 0;
  }
}

@include respond-to('sm') {
  .panel-header-simple {
    padding: var(--spacing-sm) var(--spacing-md);
  }

  .panel-body {
    padding: var(--spacing-md);
  }
}
</style>
