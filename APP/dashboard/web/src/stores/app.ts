import { defineStore } from 'pinia';

interface AppState {
  collapsed: boolean;
  currentMenuKey: string;
}

export const useAppStore = defineStore('app', {
  state: (): AppState => ({
    collapsed: false,
    currentMenuKey: 'source',
  }),
  actions: {
    toggleSider() {
      this.collapsed = !this.collapsed;
    },
    setMenuKey(key: string) {
      this.currentMenuKey = key;
    },
  },
});
