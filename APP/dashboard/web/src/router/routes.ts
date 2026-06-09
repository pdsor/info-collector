import type { RouteRecordRaw } from 'vue-router';

const MainLayout = () => import('@/layouts/MainLayout.vue');

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: MainLayout,
    redirect: '/source/index',
    children: [
      {
        path: 'source/index',
        name: 'source',
        component: () => import('@/views/source/index.vue'),
        meta: { title: '来源中心', menuKey: 'source' },
      },
      {
        path: 'rule/index',
        name: 'rule',
        component: () => import('@/views/rule/index.vue'),
        meta: { title: '规则中心', menuKey: 'rule' },
      },
      {
        path: 'task/index',
        name: 'task',
        component: () => import('@/views/task/index.vue'),
        meta: { title: '任务中心', menuKey: 'task' },
      },
      {
        path: 'governance/index',
        name: 'governance',
        component: () => import('@/views/governance/index.vue'),
        meta: { title: '治理中心', menuKey: 'governance' },
      },
      {
        path: 'archive/index',
        name: 'archive',
        component: () => import('@/views/archive/index.vue'),
        meta: { title: '归档中心', menuKey: 'archive' },
      },
    ],
  },
  {
    path: '/:catchAll(.*)*',
    redirect: '/source/index',
  },
];
