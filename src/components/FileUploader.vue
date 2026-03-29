<template>
  <div class="file-uploader">
    <input
      type="file"
      ref="fileInput"
      @change="onFileChange"
      accept=".xlsx,.xls,.csv"
      style="display: none"
    />
    <button @click="$refs.fileInput.click()" :disabled="loading">
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
  margin-bottom: 30px;
}

.file-uploader button {
  padding: 10px 20px;
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.file-uploader button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.error-message {
  color: #ff4d4f;
  margin-top: 10px;
  font-size: 14px;
}
</style>
