<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Lock, User, DataAnalysis, Cpu, Bell, Timer } from "@element-plus/icons-vue";
import { useSessionStore } from "../../stores/session";

const router = useRouter();
const session = useSessionStore();
const loading = ref(false);

const form = reactive({
  username: "admin",
  password: "abc123456",
});

const features = [
  {
    icon: DataAnalysis,
    title: "多平台聚合监控",
    desc: "覆盖微博、知乎、抖音、百度、头条等 14+ 主流资讯平台与 RSS 订阅源，关键词精准匹配，告别无效刷屏。",
  },
  {
    icon: Cpu,
    title: "AI 增强分析",
    desc: "基于 LiteLLM 统一接口接入 100+ AI 模型，智能判别舆情方向与等级，自动生成趋势概括与情感分析。",
  },
  {
    icon: Bell,
    title: "多渠道实时推送",
    desc: "飞书、钉钉、企业微信、Telegram、Email、ntfy、Bark、Slack 等 9 种通知渠道一键触达，格式自动适配。",
  },
  {
    icon: Timer,
    title: "30 秒极速部署",
    desc: "Docker 与 GitHub Actions 双模式，轻量易维护，定时自动抓取，真正实现零运维的舆情监控体验。",
  },
];

async function submit() {
  loading.value = true;
  try {
    await session.login(form);
    ElMessage.success("登录成功");
    router.replace("/");
  } catch (error) {
    ElMessage.error(error.message || "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-card__intro">
        <div class="intro-header">
          <div class="intro-header__icon">
            <span class="intro-header__pulse"></span>
          </div>
          <h2 class="intro-header__title">舆情预警系统</h2>
          <p class="intro-header__sub">
            多源聚合 · AI 增强 · 实时推送 · 极速部署
          </p>
        </div>

        <ul class="intro-features">
          <li v-for="(item, i) in features" :key="i" class="intro-feature">
            <div class="intro-feature__icon">
              <el-icon :size="22"><component :is="item.icon" /></el-icon>
            </div>
            <div class="intro-feature__body">
              <strong>{{ item.title }}</strong>
              <span>{{ item.desc }}</span>
            </div>
          </li>
        </ul>

        <p class="intro-footer">Powered by TrendRadar v6.0</p>
      </div>

      <div class="login-card__form">
        <div class="login-panel__brand">
          <div class="login-panel__logo">
            <img src="https://assets.honqun.cn/hy-static/static/images/ai/ai1.png" alt="恒银期货 Logo" />
          </div>
          <div class="login-panel__headline">
            <p class="login-panel__eyebrow">HENGYIN FUTURES CONSOLE</p>
            <h1>恒银期货</h1>
          </div>
        </div>

        <el-form class="login-form" @submit.prevent="submit">
          <el-form-item class="login-form__item">
            <el-input v-model="form.username" placeholder="请输入用户名" size="large" class="login-input">
              <template #prefix>
                <el-icon><User /></el-icon>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item class="login-form__item">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              placeholder="请输入密码"
              size="large"
              class="login-input"
              @keyup.enter="submit"
            >
              <template #prefix>
                <el-icon><Lock /></el-icon>
              </template>
            </el-input>
          </el-form-item>
          <div class="login-submit-wrap">
            <el-button class="login-submit" type="primary" size="large" :loading="loading" @click="submit">
              登录系统
            </el-button>
          </div>
        </el-form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.login-card {
  display: grid;
  grid-template-columns: 1fr 1fr;
  width: min(100%, 960px);
  min-height: 580px;
  border-radius: 16px;
  border: 1px solid rgba(0, 212, 255, 0.22);
  background:
    radial-gradient(circle at top center, rgba(0, 212, 255, 0.08), transparent 44%),
    linear-gradient(180deg, rgba(0, 212, 255, 0.02), transparent 24%),
    rgba(8, 13, 34, 0.94);
  backdrop-filter: blur(18px);
  box-shadow:
    0 0 0 1px rgba(0, 212, 255, 0.08) inset,
    0 0 44px rgba(0, 212, 255, 0.18),
    0 24px 72px rgba(0, 0, 0, 0.44);
  overflow: hidden;
  position: relative;
}

.login-card::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.08), transparent 38%, rgba(34, 211, 238, 0.04));
  z-index: 0;
}

.login-card__intro {
  position: relative;
  z-index: 1;
  padding: 40px 36px 32px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(0, 212, 255, 0.12);
  background: linear-gradient(180deg, rgba(0, 212, 255, 0.04), transparent 32%, rgba(168, 85, 247, 0.03));
}

.intro-header {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 32px;
}

.intro-header__icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.16), rgba(168, 85, 247, 0.12));
  border: 1px solid rgba(0, 212, 255, 0.28);
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.14);
  margin-bottom: 8px;
  position: relative;
}

.intro-header__pulse {
  display: block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--console-cyan);
  box-shadow: 0 0 14px var(--console-cyan);
  animation: introPulse 2.4s ease-in-out infinite;
}

.intro-header__title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: transparent;
  background: linear-gradient(90deg, #b9eaff 0%, #7ed8ff 42%, #2edcff 72%, #9ee8ff 100%);
  -webkit-background-clip: text;
  background-clip: text;
  text-shadow: 0 0 18px rgba(0, 212, 255, 0.18);
}

.intro-header__sub {
  margin: 0;
  font-size: 13px;
  color: var(--console-muted);
  letter-spacing: 0.06em;
}

.intro-features {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
  flex: 1;
}

.intro-feature {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(0, 212, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
  transition: border-color 0.26s ease, background 0.26s ease, transform 0.26s ease;
}

.intro-feature:hover {
  border-color: rgba(0, 212, 255, 0.22);
  background: rgba(0, 212, 255, 0.04);
  transform: translateX(3px);
}

.intro-feature__icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  flex-shrink: 0;
  color: var(--console-cyan);
  background: rgba(0, 212, 255, 0.08);
  border: 1px solid rgba(0, 212, 255, 0.16);
  margin-top: 2px;
}

.intro-feature__body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.intro-feature__body strong {
  font-size: 15px;
  color: #d8ecff;
  letter-spacing: 0.03em;
}

.intro-feature__body span {
  font-size: 13px;
  color: var(--console-text-soft);
  line-height: 1.65;
}

.intro-footer {
  margin: 28px 0 0;
  font-size: 12px;
  color: var(--console-faint);
  letter-spacing: 0.08em;
}

.login-card__form {
  position: relative;
  z-index: 1;
  padding: 40px 36px 32px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.login-panel__brand {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
}

.login-panel__logo {
  width: 64px;
  height: 64px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background:
    linear-gradient(180deg, rgba(0, 212, 255, 0.14), rgba(34, 211, 238, 0.06)),
    rgba(21, 46, 86, 0.92);
  border: 1px solid rgba(0, 212, 255, 0.28);
  box-shadow:
    inset 0 0 24px rgba(0, 212, 255, 0.08),
    0 0 24px rgba(0, 212, 255, 0.16);
  flex-shrink: 0;
}

.login-panel__logo img {
  width: 82%;
  height: 82%;
  object-fit: contain;
  filter: drop-shadow(0 0 8px rgba(0, 212, 255, 0.08));
}

.login-panel__headline {
  min-width: 0;
}

.login-panel__brand h1 {
  margin: 6px 0 0;
  font-size: 24px;
  font-weight: 800;
  line-height: 1.18;
  letter-spacing: 0.04em;
  color: transparent;
  background: linear-gradient(90deg, #b9eaff 0%, #7ed8ff 42%, #2edcff 72%, #9ee8ff 100%);
  -webkit-background-clip: text;
  background-clip: text;
  text-shadow: 0 0 18px rgba(0, 212, 255, 0.18);
}

.login-panel__eyebrow {
  margin: 0;
  color: var(--console-cyan);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  text-shadow: 0 0 20px rgba(0, 212, 255, 0.18);
}

.login-form {
  width: 100%;
}

.login-form__item {
  margin-bottom: 16px;
}

.login-submit-wrap {
  margin-top: 8px;
}

.login-submit {
  width: 100%;
  height: 50px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.04em;
  border-radius: 8px;
  border: 1px solid rgba(0, 212, 255, 0.3);
  background:
    linear-gradient(180deg, rgba(0, 212, 255, 0.22), rgba(0, 118, 255, 0.2)),
    rgba(8, 28, 56, 0.92);
  box-shadow:
    0 0 18px rgba(0, 212, 255, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.16);
  color: #e8f8ff;
}

.login-submit:hover {
  transform: translateY(-1px);
  box-shadow:
    0 0 24px rgba(0, 212, 255, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.22);
}

@keyframes introPulse {
  0%, 100% {
    opacity: 0.5;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1.2);
  }
}

@media (max-width: 767px) {
  .login-card {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .login-card__intro {
    display: none;
  }

  .login-card__form {
    padding: 28px 22px 28px;
  }

  .login-panel__brand {
    margin-bottom: 24px;
  }

  .login-panel__logo {
    width: 56px;
    height: 56px;
  }

  .login-panel__brand h1 {
    font-size: 20px;
  }
}
</style>
