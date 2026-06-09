<template>
  <a-button size="small" @click="onClick">
    <template #icon><LeftOutlined /></template>
    返回
  </a-button>
</template>

<script setup lang="ts">
import { LeftOutlined } from '@ant-design/icons-vue';

const emit = defineEmits<{ click: [] }>();

function onClick() {
  emit('click');
}
</script>
