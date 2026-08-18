<template>
  <el-dialog
    :model-value="true" :close-on-click-modal="false" :show-close="false"
    width="440px" title="图表范围过大" append-to-body
  >
    <p class="sgd-text">{{ message }}</p>
    <template #footer>
      <el-button data-test="back" @click="$emit('back')">返回缩小对象范围</el-button>
      <el-button type="primary" data-test="fold" @click="$emit('fold-to-sm')">
        折叠到服务模块层展示
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  nodes: { type: Number, default: 0 },
  relations: { type: Number, default: 0 }
})
defineEmits(['fold-to-sm', 'back'])

const message = computed(() =>
  `所选范围过大（约 ${props.relations} 关系 / ${props.nodes} 节点），渲染会明显卡顿。请选择折叠到服务模块层展示，或返回缩小对象范围。`
)
</script>

<style scoped>
.sgd-text { margin: 0 0 4px; font-size: 14px; line-height: 1.7; }
</style>
