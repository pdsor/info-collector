import { createRouter, createWebHistory, type Router } from 'vue-router';
import { routes } from './routes';

export const router: Router = createRouter({
  history: createWebHistory('/'),
  routes,
});

router.afterEach((to) => {
  const title = to.meta?.title;
  if (title) {
    document.title = `${title} · 信息采集控制台`;
  }
});
