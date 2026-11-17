// 各业务页面按路由懒加载，首页只加载监测所需模块。
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue')
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('../views/HistoryView.vue')
    },
    {
      path: '/config',
      name: 'config',
      component: () => import('../views/SceneConfigView.vue')
    },
    {
      path: '/events',
      name: 'events',
      component: () => import('../views/EventView.vue')
    }
  ]
})

export default router
