<template>
  <a-layout class="srop-app-layout">
    <a-layout-sider
      v-model:collapsed="appStore.collapsed"
      :trigger="null"
      collapsible
      :width="220"
      :collapsed-width="64"
      theme="dark"
      class="srop-sider"
    >
      <div class="srop-brand">
        <span class="srop-brand-mark">数采</span>
        <span v-show="!appStore.collapsed" class="srop-brand-text">信息采集控制台</span>
      </div>
      <a-menu
        :selected-keys="selectedKeys"
        mode="inline"
        theme="dark"
        @click="onMenuClick"
      >
        <a-menu-item v-for="item in menuList" :key="item.key">
          <template #icon>
            <component :is="iconMap[item.icon]" />
          </template>
          <span>{{ item.label }}</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="srop-header">
        <a-button type="text" class="srop-toggle" @click="appStore.toggleSider">
          <MenuFoldOutlined v-if="!appStore.collapsed" />
          <MenuUnfoldOutlined v-else />
        </a-button>
        <div class="srop-header-title">{{ currentTitle }}</div>
        <div class="srop-header-spacer" />
        <a-tooltip title="刷新页面">
          <a-button type="text" @click="reloadPage"><ReloadOutlined /></a-button>
        </a-tooltip>
      </a-layout-header>

      <a-layout-content class="srop-page-content">
        <router-view v-slot="{ Component, route }">
          <component :is="Component" :key="route.fullPath" />
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  DatabaseOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
  SafetyCertificateOutlined,
  FolderOpenOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue';
import { usePermissionStore } from '@/stores/permission';
import { useAppStore } from '@/stores/app';

const iconMap: Record<string, unknown> = {
  DatabaseOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
  SafetyCertificateOutlined,
  FolderOpenOutlined,
};

const route = useRoute();
const router = useRouter();
const permissionStore = usePermissionStore();
const appStore = useAppStore();

const menuList = computed(() => permissionStore.menuList);

const selectedKeys = computed(() => {
  const key = String(route.meta?.menuKey || route.name || '');
  return key ? [key] : [];
});

const currentTitle = computed(() => String(route.meta?.title || '信息采集控制台'));

function onMenuClick(payload: { key: string }) {
  const target = menuList.value.find((item) => item.key === payload.key);
  if (target) {
    appStore.setMenuKey(target.key);
    router.push(target.path);
  }
}

function reloadPage() {
  router.go(0);
}
</script>

<style scoped>
.srop-app-layout {
  min-height: 100vh;
}

.srop-sider {
  position: sticky;
  top: 0;
  height: 100vh;
}

.srop-sider :deep(.ant-layout-sider-children) {
  display: flex;
  flex-direction: column;
}

.srop-brand {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  color: #fff;
  font-weight: 600;
  font-size: 15px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.srop-brand-mark {
  width: 26px;
  height: 26px;
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  letter-spacing: 0.5px;
}

.srop-brand-text {
  white-space: nowrap;
}

.srop-header {
  background: #fff;
  border-bottom: 1px solid #eef2f7;
  padding: 0 12px 0 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  position: sticky;
  top: 0;
  z-index: 10;
}

.srop-toggle {
  width: 44px;
  height: 44px;
  font-size: 16px;
}

.srop-header-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--srop-text);
}

.srop-header-spacer {
  flex: 1;
}
</style>
