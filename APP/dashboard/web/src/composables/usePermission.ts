import { usePermissionStore } from '@/stores/permission';

// usePermission：脚本中判断按钮权限。skeleton — 当前后端无权限接口，超管态总是返回 true
export function usePermission() {
  const store = usePermissionStore();

  function has(action: string): boolean {
    if (!action) return true;
    if (store.isSuperAdmin) return true;
    return store.permissions.has(action);
  }

  return { has };
}
