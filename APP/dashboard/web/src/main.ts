import { createApp } from 'vue';
import { createPinia } from 'pinia';
import Antd from 'ant-design-vue';
import 'ant-design-vue/dist/reset.css';
import 'dayjs/locale/zh-cn';
import dayjs from 'dayjs';

import App from './App.vue';
import { router } from './router';
import { permissionDirective } from './directives/permission';
import './styles/global.css';

dayjs.locale('zh-cn');

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(Antd);
app.directive('permission', permissionDirective);
app.mount('#app');
