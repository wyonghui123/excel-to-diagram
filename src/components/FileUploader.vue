<template>
  <div class="file-uploader">
    <input
      type="file"
      ref="fileInput"
      @change="onFileChange"
      accept=".xlsx,.xls,.csv"
      style="display: none"
    />
    <button
      class="upload-btn"
      :disabled="loading"
      @click="$refs.fileInput.click()"
    >
      {{ loading ? '处理中...' : buttonText }}
    </button>
    <div v-if="error" class="error-message">{{ error }}</div>
  </div>
</template>

<script>
export default {
  name: 'FileUploader',
  props: {
    loading: {
      type: Boolean,
      default: false
    },
    error: {
      type: String,
      default: ''
    },
    buttonText: {
      type: String,
      default: '选择Excel文件'
    }
  },
  emits: ['file-selected'],
  methods: {
    onFileChange(event) {
      const file = event.target.files[0];
      if (file) {
        this.$emit('file-selected', file);
      }
    }
  }
};
</script>

<style scoped>
.file-uploader {
  margin-bottom: var(--spacing-md);
}

.upload-btn {
  /* 使用YonDesign主色 */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  height: var(--btn-height-lg);
  padding: 0 var(--spacing-xl);
  font-family: var(--font-family);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-medium);
  color: #ffffff;
  background: var(--color-primary);
  border: none;
  border-radius: var(--radius-button);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.upload-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.upload-btn:active:not(:disabled) {
  background: var(--color-primary-active);
}

.upload-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-message {
  color: var(--color-error);
  margin-top: var(--spacing-sm);
  font-size: var(--font-size-md);
}
</style>
