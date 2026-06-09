<template>
  <a-tag :color="color">{{ label }}</a-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { statusColors, statusLabels } from '@/styles/theme';

interface Props {
  value?: string | number | boolean | null;
  // 自定义文案，传入则覆盖 statusLabels 查表结果
  label?: string;
  // 自定义色，传入则覆盖 statusColors 查表结果
  color?: string;
}

const props = defineProps<Props>();

const normalized = computed(() => {
  if (props.value === true) return 'ENABLED';
  if (props.value === false) return 'DISABLED';
  return String(props.value ?? '').trim().toUpperCase();
});

const label = computed(() => props.label || statusLabels[normalized.value] || normalized.value || '-');

const color = computed(() => props.color || statusColors[normalized.value] || 'default');
</script>
