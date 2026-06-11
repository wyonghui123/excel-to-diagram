<!--
  @deprecated 2026-06-11 旧 6 步骤模式第 1 步，入口已废弃。
    入口: /archdata-chart 路由已在菜单中隐藏 (hiddenFromMenu: true)
    替代: 用户应从 "架构数据管理" 页面选择数据后 navigate 到图表页
    状态: 保留为 fallback（用户直接 URL 访问 /archdata-chart 时仍能工作）
    TODO: 下轮清理时连同 useDiagramSteps 的 STEPS 0 一起删除
-->
<template>
  <div class="step-upload">
    <div class="upload-panel">
      <div class="panel-header">
        <h2>数据来源</h2>
        <p class="panel-desc">请选择包含业务对象和关系的Excel文件</p>
      </div>
      <div class="panel-body">
        <FileUploader
          :loading="loading"
          :error="error"
          button-text="选择Excel文件"
          @file-selected="handleFileSelected"
        />
      </div>
    </div>
  </div>
</template>

<script>
import FileUploader from '../../../../components/FileUploader.vue'

export default {
  name: 'StepUpload',
  components: { FileUploader },
  props: {
    loading: Boolean,
    error: String
  },
  emits: ['file-selected'],
  methods: {
    handleFileSelected(file) {
      this.$emit('file-selected', file)
    }
  }
}
</script>

<style scoped lang="scss">
@import '../../../../styles/mixins.scss';

.step-upload {
  max-width: 800px;
  margin: 0 auto;
}

.upload-panel {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.panel-header {
  padding: var(--spacing-xl);
  border-bottom: 1px solid var(--color-border);

  h2 {
    font-size: var(--font-size-xxl);
    font-weight: 600;
    color: var(--color-text-primary);
    margin-bottom: var(--spacing-sm);
  }
}

.panel-desc {
  font-size: var(--font-size-md);
  color: var(--color-text-secondary);
}

.panel-body {
  padding: var(--spacing-xl);
}

@include respond-to('sm') {
  .panel-header {
    padding: var(--spacing-lg);

    h2 {
      font-size: var(--font-size-xl);
    }
  }

  .panel-body {
    padding: var(--spacing-lg);
  }
}
</style>
