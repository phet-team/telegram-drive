import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import DriveView from '../views/DriveView.vue';
import LoginView from '../views/LoginView.vue';
import RegisterView from '../views/RegisterView.vue';
import SharedLinkView from '../views/SharedLinkView.vue';

const routes = [
  {
    path: '/',
    name: 'Drive',
    component: DriveView,
    meta: { requiresAuth: true },
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
