import type { ThemeConfig } from 'ant-design-vue/es/config-provider/context';

// SROP 控制台主题 token，注入 a-config-provider :theme="sropTheme"
// components 内部使用了组件级私有 token (headerBg, darkItemBg)，AntD Vue 4 的类型签名较严格，
// 此处强制断言为 ThemeConfig['components']，运行期行为不变
export const sropTheme: ThemeConfig = {
  token: {
    colorPrimary: '#2563EB',
    colorSuccess: '#0E9F6E',
    colorError: '#DC2626',
    colorWarning: '#D97706',
    colorInfo: '#2563EB',
    colorTextBase: '#111827',
    colorBgLayout: '#F3F6FB',
    colorBgContainer: '#FFFFFF',
    colorBorder: '#E5E7EB',
    colorBorderSecondary: '#EEF2F7',
    borderRadius: 8,
    borderRadiusSM: 4,
    controlHeight: 34,
    fontSize: 13,
    fontFamily:
      '"Hiragino Sans GB", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Noto Sans SC", sans-serif',
    boxShadow: '0 8px 24px rgba(15, 23, 42, 0.05)',
  },
  components: {
    Layout: {
      headerBg: '#FFFFFF',
      headerHeight: 56,
      headerPadding: '0 24px',
      siderBg: '#001529',
      bodyBg: '#F3F6FB',
    },
    Menu: {
      darkItemBg: '#001529',
      darkSubMenuItemBg: '#000C17',
      darkItemSelectedBg: '#2563EB',
    },
    Table: {
      headerBg: '#FAFBFD',
      headerColor: '#4B5563',
      rowHoverBg: '#F8FAFD',
      borderColor: '#EEF2F7',
    },
    Card: {
      headerBg: 'transparent',
    },
    Tag: {
      borderRadiusSM: 4,
    },
  } as ThemeConfig['components'],
};

// 业务状态色（StatusTag 组件查询用，禁止在页面里另行映射）
export const statusColors: Record<string, string> = {
  // Source & Rule 生命周期
  ACTIVE: 'green',
  PAUSED: 'red',
  PRODUCTION: 'green',
  TESTING: 'blue',
  DRAFT: 'gold',
  DEPRECATED: 'red',
  // Task NG 状态机
  PENDING: 'blue',
  QUEUED: 'blue',
  RUNNING: 'blue',
  SUCCESS: 'green',
  PARTIAL_SUCCESS: 'gold',
  FAILED: 'red',
  RETRYING: 'gold',
  CANCELLED: 'red',
  // Governance
  WARNING: 'gold',
  // Archive boolean 标志
  YES: 'blue',
  NO: 'default',
  // 通用
  ENABLED: 'green',
  DISABLED: 'default',
  ON: 'green',
  OFF: 'default',
};

export const statusLabels: Record<string, string> = {
  ACTIVE: '已启用',
  PAUSED: '已停用',
  PRODUCTION: '生产',
  TESTING: '测试',
  DRAFT: '草稿',
  DEPRECATED: '已弃用',
  PENDING: '待执行',
  QUEUED: '排队中',
  RUNNING: '执行中',
  SUCCESS: '成功',
  PARTIAL_SUCCESS: '部分成功',
  FAILED: '失败',
  RETRYING: '重试中',
  CANCELLED: '已取消',
  WARNING: '警告',
  YES: '是',
  NO: '否',
  ENABLED: '启用',
  DISABLED: '停用',
  ON: '启用',
  OFF: '停用',
};
