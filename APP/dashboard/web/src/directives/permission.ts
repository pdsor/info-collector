import type { Directive, DirectiveBinding } from 'vue';
import { usePermissionStore } from '@/stores/permission';

// v-permission="'/module/controller/action'" — 按钮权限指令
// 当前 store 默认为超管态，所有指令通过；保留 hook 以便后续接入登录态
export const permissionDirective: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding<string | string[]>) {
    apply(el, binding.value);
  },
  updated(el: HTMLElement, binding: DirectiveBinding<string | string[]>) {
    apply(el, binding.value);
  },
};

function apply(el: HTMLElement, value: string | string[] | undefined) {
  const store = usePermissionStore();
  const actions = Array.isArray(value) ? value : value ? [value] : [];
  if (!actions.length) return;
  const allowed = actions.some((a) => store.hasPermission(a));
  if (!allowed) {
    el.parentNode?.removeChild(el);
  }
}
