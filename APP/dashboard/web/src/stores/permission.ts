import { defineStore } from 'pinia';

// 菜单项定义 — defaultMenuList 与 routes.ts 中的 path 对齐
export interface MenuItem {
  key: string;
  label: string;
  icon: string;
  path: string;
}

export const defaultMenuList: MenuItem[] = [
  { key: 'source', label: '来源中心', icon: 'DatabaseOutlined', path: '/source/index' },
  { key: 'rule', label: '规则中心', icon: 'FileTextOutlined', path: '/rule/index' },
  { key: 'task', label: '任务中心', icon: 'ThunderboltOutlined', path: '/task/index' },
  { key: 'governance', label: '治理中心', icon: 'SafetyCertificateOutlined', path: '/governance/index' },
  { key: 'archive', label: '归档中心', icon: 'FolderOpenOutlined', path: '/archive/index' },
];

interface PermissionState {
  isSuperAdmin: boolean;
  permissions: Set<string>;
  routeAliases: Record<string, string>;
}

// 当前后端无认证，默认按超管态运行。保留 store 结构为将来扩展登录、动态菜单与按钮权限准备
export const usePermissionStore = defineStore('permission', {
  state: (): PermissionState => ({
    isSuperAdmin: true,
    permissions: new Set<string>(),
    routeAliases: {},
  }),
  getters: {
    menuList(): MenuItem[] {
      return defaultMenuList;
    },
  },
  actions: {
    hasPermission(action: string): boolean {
      if (this.isSuperAdmin) return true;
      return this.permissions.has(action);
    },
    setPermissions(actions: string[]) {
      this.permissions = new Set(actions);
    },
    setSuperAdmin(value: boolean) {
      this.isSuperAdmin = value;
    },
  },
});
