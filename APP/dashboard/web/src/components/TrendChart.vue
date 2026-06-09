<template>
  <div ref="containerRef" class="srop-trend-chart" :style="{ height: `${height}px` }" />
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, shallowRef } from 'vue';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart, PieChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  TitleComponent,
  LegendComponent,
  DataZoomComponent,
} from 'echarts/components';
import type { EChartsType } from 'echarts/core';

echarts.use([
  CanvasRenderer,
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  TitleComponent,
  LegendComponent,
  DataZoomComponent,
]);

interface Props {
  option: Record<string, unknown>;
  height?: number;
}

const props = withDefaults(defineProps<Props>(), { height: 280 });

const containerRef = ref<HTMLDivElement | null>(null);
const chart = shallowRef<EChartsType | null>(null);

function applyDefaults(option: Record<string, unknown>): Record<string, unknown> {
  const base: Record<string, unknown> = {
    grid: { left: 36, right: 24, top: 48, bottom: 28 },
    tooltip: { trigger: 'axis' },
  };
  return { ...base, ...option };
}

function ensureChart() {
  if (!containerRef.value) return;
  chart.value = echarts.init(containerRef.value);
}

function render(option: Record<string, unknown>) {
  if (!chart.value) return;
  chart.value.setOption(applyDefaults(option), true);
}

function handleResize() {
  chart.value?.resize();
}

onMounted(() => {
  ensureChart();
  render(props.option);
  window.addEventListener('resize', handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
  chart.value?.dispose();
  chart.value = null;
});

watch(
  () => props.option,
  (next) => render(next),
  { deep: true },
);
</script>

<style scoped>
.srop-trend-chart {
  width: 100%;
}
</style>
