<template>
  <div ref="chartRef" class="report-chart"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, GridComponent, TitleComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  items: { type: Array, default: () => [] },
  title: { type: String, default: '' },
  categoryField: { type: String, default: 'bucket' },
  valueField: { type: String, default: 'qty' },
})

const chartRef = ref(null)
let chart = null
let observer = null

function render() {
  if (!chart) return
  const categories = props.items.map((item) => item?.[props.categoryField] ?? '')
  const values = props.items.map((item) => Number(item?.[props.valueField] ?? 0))
  chart.setOption({
    title: props.title ? { text: props.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 24, top: props.title ? 44 : 24, bottom: 32 },
    xAxis: { type: 'category', data: categories, axisLabel: { color: '#8c8c8c' } },
    yAxis: { type: 'value', axisLabel: { color: '#8c8c8c' } },
    series: [{
      type: 'bar',
      data: values,
      barMaxWidth: 48,
      itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] },
    }],
  }, true)
}

onMounted(() => {
  chart = echarts.init(chartRef.value)
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(chartRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})

watch(() => props.items, render, { deep: true })
</script>

<style scoped>
.report-chart {
  width: 100%;
  height: 260px;
}
</style>
