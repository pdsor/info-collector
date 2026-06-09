<template>
  <a-config-provider :theme="sropTheme" :locale="zhCN">
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
import { ConfigProvider as AConfigProvider } from 'ant-design-vue';
import zhCN from 'ant-design-vue/es/locale/zh_CN';
import { sropTheme } from '@/styles/theme';
// 显式引用以便 IDE 类型推断
void AConfigProvider;
</script>
