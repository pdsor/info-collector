import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import StatusTag from '@/components/StatusTag.vue';

vi.mock('ant-design-vue', () => ({
  default: {},
  Tag: {
    name: 'ATag',
    props: ['color'],
    template: '<span :data-color="color"><slot /></span>',
  },
}));

describe('StatusTag', () => {
  it('展示已知状态的中文标签', async () => {
    const wrapper = mount(StatusTag, {
      props: { value: 'ACTIVE' },
      global: {
        stubs: {
          'a-tag': {
            props: ['color'],
            template: '<span class="a-tag" :data-color="color"><slot /></span>',
          },
        },
      },
    });
    expect(wrapper.text()).toBe('已启用');
    expect(wrapper.find('.a-tag').attributes('data-color')).toBe('green');
  });

  it('未知状态回落到原始大写文本', () => {
    const wrapper = mount(StatusTag, {
      props: { value: 'UNKNOWN' },
      global: {
        stubs: {
          'a-tag': {
            props: ['color'],
            template: '<span class="a-tag" :data-color="color"><slot /></span>',
          },
        },
      },
    });
    expect(wrapper.text()).toBe('UNKNOWN');
    expect(wrapper.find('.a-tag').attributes('data-color')).toBe('default');
  });

  it('布尔值映射为 ENABLED / DISABLED', () => {
    const enabled = mount(StatusTag, {
      props: { value: true },
      global: {
        stubs: {
          'a-tag': {
            props: ['color'],
            template: '<span class="a-tag" :data-color="color"><slot /></span>',
          },
        },
      },
    });
    expect(enabled.text()).toBe('启用');
    expect(enabled.find('.a-tag').attributes('data-color')).toBe('green');

    const disabled = mount(StatusTag, {
      props: { value: false },
      global: {
        stubs: {
          'a-tag': {
            props: ['color'],
            template: '<span class="a-tag" :data-color="color"><slot /></span>',
          },
        },
      },
    });
    expect(disabled.text()).toBe('停用');
    expect(disabled.find('.a-tag').attributes('data-color')).toBe('default');
  });
});
