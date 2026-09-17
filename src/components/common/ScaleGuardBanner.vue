<template>
  <div class="scale-guard-banner" role="alert">
    <span class="sgb-text">{{ message }}</span>
    <el-button size="small" type="primary" data-test="fold" @click="$emit('fold-to-sm')">
      一键折叠到服务模块层
    </el-button>
    <el-button size="small" text data-test="close" @click="$emit('close')">知道了</el-button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  nodes: { type: Number, default: 0 },
  relations: { type: Number, default: 0 }
})
defineEmits(['fold-to-sm', 'close'])

const message = computed(() =>
  `当前图含 ${props.relations} 关系 / ${props.nodes} 节点, 超出推荐可读范围, 建议缩小对象范围或折叠到服务模块层。`
)
</script>

<style scoped>
.scale-guard-banner {
  position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
  z-index: 30; display: flex; align-items: center; gap: 8px;
  max-width: 70%; padding: 8px 14px; border-radius: 8px;
  background: #fff7e6; border: 1px solid #ffd591; color: #874d00;
  font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.12);
}
.sgb-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
