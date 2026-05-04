import { createRouter, createWebHistory } from "vue-router";
import DashboardView from "./views/DashboardView.vue";
import LoginView from "./views/auth/LoginView.vue";
import OpinionView from "./views/OpinionView.vue";
import ShareView from "./views/ShareView.vue";
import AiModelsView from "./views/system/AiModelsView.vue";
import FuturesSymbolsView from "./views/system/FuturesSymbolsView.vue";
import RolesView from "./views/system/RolesView.vue";
import UsersView from "./views/system/UsersView.vue";
import { useSessionStore } from "./stores/session";

const routes = [
  {
    path: "/login",
    name: "login",
    component: LoginView,
    meta: { public: true, title: "登录" },
  },
  {
    path: "/",
    name: "dashboard",
    component: DashboardView,
    meta: { title: "总览" },
  },
  {
    path: "/opinion",
    name: "opinion",
    component: OpinionView,
    meta: { title: "舆情纵览" },
  },
  {
    path: "/share/:token",
    name: "share",
    component: ShareView,
    meta: { public: true, title: "分享详情" },
  },
  {
    path: "/ai-models",
    name: "ai-models",
    component: AiModelsView,
    meta: { title: "AI模型管理" },
  },
  {
    path: "/futures-symbols",
    name: "futures-symbols",
    component: FuturesSymbolsView,
    meta: { title: "期货品种" },
  },
  {
    path: "/roles",
    name: "roles",
    component: RolesView,
    meta: { title: "角色管理" },
  },
  {
    path: "/users",
    name: "users",
    component: UsersView,
    meta: { title: "用户管理" },
  },
];

const router = createRouter({
  history: createWebHistory("/console/"),
  routes,
});

router.beforeEach(async (to) => {
  const session = useSessionStore();

  if (to.meta.public) {
    if (to.name === "login" && session.state.user) {
      return { name: "dashboard" };
    }
    return true;
  }

  if (!session.state.loaded) {
    await session.ensureSession();
  }

  if (!session.state.user) {
    return { name: "login", query: { redirect: to.fullPath } };
  }

  return true;
});

router.afterEach((to) => {
  document.title = to.meta?.title
    ? `${to.meta.title} - 恒银期货舆情预警系统`
    : "恒银期货舆情预警系统";
});

export default router;
