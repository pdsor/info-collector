// Vitest 测试启动文件 — 全局 stub 与 polyfill
import { config } from '@vue/test-utils';

// 全局 stub ant-design-vue 常用组件，便于组件渲染测试
config.global.stubs = {
  'a-button': { template: '<button><slot /></button>' },
  'a-input': { template: '<input />' },
  'a-tooltip': { template: '<span><slot /></span>' },
  'a-tag': {
    props: ['color'],
    template: '<span class="a-tag" :data-color="color"><slot /></span>',
  },
};
