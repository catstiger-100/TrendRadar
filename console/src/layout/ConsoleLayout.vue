<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { ArrowDown, House, Lock, Menu, Setting, User, UserFilled } from "@element-plus/icons-vue";
import { useSessionStore } from "../stores/session";

const collapsed = ref(true);
const mobileMenuOpen = ref(false);
const isMobile = ref(false);
const settingsOpen = ref(true);
const route = useRoute();
const router = useRouter();
const session = useSessionStore();

const menuItems = [
  { key: "dashboard", label: "态势总览", icon: House, route: "/" },
];

const settingsItems = [
  { key: "roles", label: "角色管理", icon: Setting, route: "/roles" },
  { key: "users", label: "用户管理", icon: UserFilled, route: "/users" },
];

const sidebarWidth = computed(() => {
  if (isMobile.value) return "100%";
  return collapsed.value ? "80px" : "240px";
});
const settingsLabelHidden = computed(() => collapsed.value && !isMobile.value);
const isSettingsActive = computed(() => settingsItems.some((item) => item.route === route.path));
const settingsHoverOpen = ref(false);
let settingsHoverTimer = null;

const username = computed(() => session.state.user?.username || "");
const pageTitle = computed(() => route.meta?.title || "控制台");
const fullName = computed(() => session.state.user?.full_name || session.state.user?.username || "");
const passwordDialogVisible = ref(false);
const passwordForm = ref({
  old_password: "",
  new_password: "",
  confirm_password: "",
});

function syncViewport() {
  isMobile.value = window.innerWidth < 992;
  if (!isMobile.value) {
    mobileMenuOpen.value = false;
  }
}

function toggleSidebar() {
  if (isMobile.value) {
    mobileMenuOpen.value = !mobileMenuOpen.value;
    return;
  }
  collapsed.value = !collapsed.value;
}

function closeMobileMenu() {
  if (isMobile.value) {
    mobileMenuOpen.value = false;
  }
}

function navigateTo(item) {
  router.push(item.route);
  closeMobileMenu();
}

function toggleSettings() {
  if (settingsLabelHidden.value) {
    collapsed.value = false;
    settingsOpen.value = true;
    return;
  }
  settingsOpen.value = !settingsOpen.value;
}

function handleSettingsMouseEnter() {
  if (settingsLabelHidden.value) {
    if (settingsHoverTimer) {
      clearTimeout(settingsHoverTimer);
      settingsHoverTimer = null;
    }
    settingsHoverOpen.value = true;
  }
}

function handleSettingsMouseLeave() {
  if (settingsHoverTimer) {
    clearTimeout(settingsHoverTimer);
  }
  settingsHoverTimer = setTimeout(() => {
    settingsHoverOpen.value = false;
    settingsHoverTimer = null;
  }, 120);
}

function openPasswordDialog() {
  passwordForm.value = {
    old_password: "",
    new_password: "",
    confirm_password: "",
  };
  passwordDialogVisible.value = true;
}

async function submitPasswordChange() {
  if (!passwordForm.value.old_password || !passwordForm.value.new_password) {
    ElMessage.error("请完整填写密码信息");
    return;
  }
  if (passwordForm.value.new_password !== passwordForm.value.confirm_password) {
    ElMessage.error("两次输入的新密码不一致");
    return;
  }
  try {
    await session.changePassword(passwordForm.value);
    await session.logout();
    passwordDialogVisible.value = false;
    ElMessage.success("密码已修改，请重新登录");
    router.replace("/login");
  } catch (error) {
    ElMessage.error(error.message || "密码修改失败");
  }
}

async function handleLogout() {
  await session.logout();
  ElMessage.success("已退出登录");
  router.replace("/login");
}

onMounted(() => {
  syncViewport();
  window.addEventListener("resize", syncViewport);
});

onBeforeUnmount(() => {
  if (settingsHoverTimer) {
    clearTimeout(settingsHoverTimer);
  }
  window.removeEventListener("resize", syncViewport);
});
</script>

<template>
  <div class="console-shell">
    <transition name="console-fade">
      <button
        v-if="isMobile && mobileMenuOpen"
        class="console-mask"
        type="button"
        aria-label="关闭菜单"
        @click="closeMobileMenu"
      />
    </transition>

    <aside
      class="console-sidebar"
      :class="{
        'is-collapsed': collapsed && !isMobile,
        'is-mobile': isMobile,
        'is-open': mobileMenuOpen,
      }"
      :style="{ width: sidebarWidth }"
    >
      <div class="console-brand">
        <div class="console-brand__badge">
          <img src="https://assets.honqun.cn/hy-static/static/images/ai/ai1.png" alt="恒银期货 Logo" />
        </div>
        <div class="console-brand__text" :class="{ 'is-hidden': collapsed && !isMobile }">
          <strong>恒银期货</strong>
        </div>
      </div>

      <nav class="console-nav">
        <button
          v-for="item in menuItems"
          :key="item.key"
          class="console-nav__item"
          :class="{ 'is-active': route.path === item.route }"
          type="button"
          @click="navigateTo(item)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span class="console-nav__label" :class="{ 'is-hidden': collapsed && !isMobile }">
            {{ item.label }}
          </span>
        </button>

        <div
          class="console-nav__group"
          :class="{ 'is-open': settingsOpen && !settingsLabelHidden, 'is-hover-open': settingsHoverOpen }"
          @mouseenter="handleSettingsMouseEnter"
          @mouseleave="handleSettingsMouseLeave"
        >
          <button
            class="console-nav__item console-nav__item--group"
            :class="{ 'is-active': isSettingsActive }"
            type="button"
            @click="toggleSettings"
          >
            <el-icon><Setting /></el-icon>
            <span class="console-nav__label" :class="{ 'is-hidden': settingsLabelHidden }">
              系统设置
            </span>
            <span
              v-if="!settingsLabelHidden"
              class="console-nav__chevron"
              :class="{ 'is-open': settingsOpen }"
            >
              <el-icon><ArrowDown /></el-icon>
            </span>
          </button>

          <div
            class="console-nav__sublist"
            :class="{
              'is-open': settingsOpen && !settingsLabelHidden,
              'is-floating': settingsLabelHidden,
              'is-visible': settingsHoverOpen && settingsLabelHidden,
            }"
          >
            <button
              v-for="item in settingsItems"
              :key="item.key"
              class="console-nav__subitem"
              :class="{ 'is-active': route.path === item.route }"
              type="button"
              @click="navigateTo(item)"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </button>
          </div>
        </div>
      </nav>

    </aside>

    <div class="console-main">
      <header class="console-header">
        <div class="console-header__left">
          <button class="console-toggle" type="button" @click="toggleSidebar">
            <el-icon><Menu /></el-icon>
          </button>
          <div>
            <p class="console-eyebrow">HENGYIN FUTURES CONSOLE</p>
            <h1>{{ pageTitle }}</h1>
          </div>
        </div>
        <div class="console-header__right">
          <div class="console-status">
            <span class="console-status__dot"></span>
            <span>实时监测中</span>
          </div>
          <el-dropdown trigger="click" placement="bottom-end">
            <button class="console-user" type="button">
              <span class="console-user__avatar">
                <el-icon><User /></el-icon>
              </span>
              <span class="console-user__name">{{ username }}</span>
              <el-icon class="console-user__arrow"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu class="console-user-menu">
                <el-dropdown-item class="console-user-menu__meta" disabled>
                  {{ fullName }}
                </el-dropdown-item>
                <el-dropdown-item @click="openPasswordDialog">
                  <el-icon><Lock /></el-icon>
                  修改密码
                </el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="console-content">
        <slot />
      </main>
    </div>

    <el-dialog v-model="passwordDialogVisible" title="修改密码" width="420px">
      <el-form label-position="top">
        <el-form-item label="原密码">
          <el-input v-model="passwordForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="passwordForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitPasswordChange">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
