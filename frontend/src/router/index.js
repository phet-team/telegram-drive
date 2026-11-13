import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import DriveView from '../views/DriveView.vue';
import LoginView from '../views/LoginView.vue';
import RegisterView from '../views/RegisterView.vue';
import SharedLinkView from '../views/SharedLinkView.vue';
import ApiTokensView from '../views/ApiTokensView.vue';
import StorageSettingsView from '../views/StorageSettingsView.vue';

const routes = [
  {
    path: '/',
    name: 'Drive',
    component: DriveView,
    meta: { requiresAuth: true },
  },
  {
    path: '/settings/my-storage',
    name: 'MyStorage',
    component: () => import('../views/MyStorageView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings/users',
    name: 'AdminUsers',
    component: () => import('../views/AdminUsersView.vue'),
    meta: { requiresAuth: true, requiresSuperuser: true },
  },
  {
    path: '/settings/tokens',
    name: 'ApiTokens',
    component: ApiTokensView,
    meta: { requiresAuth: true },
  },
  {
    path: '/settings/storage',
    name: 'StorageSettings',
    component: StorageSettingsView,
    meta: { requiresAuth: true, requiresSuperuser: true },
  },
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
  },
  {
    path: '/register',
    name: 'Register',
    component: RegisterView,
  },
  {
    path: '/share/:token',
    name: 'SharedLink',
    component: SharedLinkView,
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore();
  if (!authStore.isInitialized) {
    await authStore.initAuth();
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({
      path: '/login',
      query: to.fullPath && to.fullPath !== '/' ? { redirect: to.fullPath } : {},
    });
  } else if (to.meta.requiresSuperuser && !authStore.user?.is_superuser) {
    next('/');
  } else if ((to.name === 'Login' || to.name === 'Register') && authStore.isAuthenticated) {
    const redirectStr = String(to.query.redirect || '');
    const redirect = redirectStr.startsWith('/') && !redirectStr.startsWith('//')
      ? redirectStr
      : '/';
    next(redirect);
  } else {
    next();
  }
});

export default router;
