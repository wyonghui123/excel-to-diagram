<template>
  <el-dropdown
    trigger="click"
    @command="handleSelect"
    :data-testid="'locale-switcher'"
  >
    <span class="locale-switcher-trigger">
      <AppIcon name="globe" size="sm" />
      <span class="locale-switcher-label">{{ currentLabel }}</span>
      <el-icon class="locale-switcher-arrow"><ArrowDown /></el-icon>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="loc in availableLocales"
          :key="loc.code"
          :command="loc.code"
          :disabled="loc.code === locale"
        >
          <el-icon v-if="loc.code === locale"><Check /></el-icon>
          <span>{{ loc.label }}</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import { computed } from 'vue'
import { ArrowDown, Check } from '@element-plus/icons-vue'
import { AppIcon } from '@/components/common'
import { useLocale } from '@/composables/useLocale'

const { locale, availableLocales, setLocale } = useLocale()

const currentLabel = computed(() => {
  const found = availableLocales.find(l => l.code === locale.value)
  return found ? found.label : locale.value
})

function handleSelect(code) {
  setLocale(code)
}
</script>

<style scoped>
.locale-switcher-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  color: var(--el-text-color-regular, #606266);
  font-size: 14px;
  transition: background 0.2s;
}
.locale-switcher-trigger:hover {
  background: var(--el-fill-color-light, #f5f7fa);
}
.locale-switcher-label {
  user-select: none;
}
.locale-switcher-arrow {
  font-size: 12px;
}
</style>
