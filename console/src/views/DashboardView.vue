<script setup>
import ConsoleLayout from "../layout/ConsoleLayout.vue";

const overviewCards = [
  {
    title: "登录认证",
    value: "READY",
    hint: "会话校验已启用",
  },
  {
    title: "角色管理",
    value: "CRUD",
    hint: "支持增删改查",
  },
  {
    title: "用户管理",
    value: "CRUD",
    hint: "支持多角色绑定",
  },
  {
    title: "密码存储",
    value: "PBKDF2",
    hint: "加密保存到 PostgreSQL",
  },
];

const pulseFeeds = [
  "默认管理员账号已初始化：admin / abc123456",
  "未登录访问 /console 内部页面时会自动跳转登录页",
  "角色支持独立维护，用户编辑时可进行多角色绑定",
  "登录成功后会记录最近登录时间与登录 IP",
];

const alertRows = [
  { level: "P1", topic: "登录页接入", source: "Console", status: "已完成" },
  { level: "P1", topic: "会话拦截", source: "Router Guard", status: "已完成" },
  { level: "P2", topic: "角色 CRUD", source: "PostgreSQL", status: "已完成" },
  { level: "P2", topic: "用户 CRUD", source: "PostgreSQL", status: "已完成" },
];
</script>

<template>
  <ConsoleLayout>
    <section class="hero-panel">
      <div class="hero-panel__content">
        <p class="hero-panel__eyebrow">CYBERPUNK COMMAND CENTER</p>
        <h2>为后台补齐登录、用户与权限基础能力</h2>
        <p class="hero-panel__desc">
          当前版本已经接入 PostgreSQL 用户体系，具备登录拦截、默认管理员、角色管理和用户管理能力。
        </p>
      </div>
      <div class="hero-panel__grid">
        <div class="hero-kpi" v-for="card in overviewCards" :key="card.title">
          <span>{{ card.title }}</span>
          <strong>{{ card.value }}</strong>
          <em>{{ card.hint }}</em>
        </div>
      </div>
    </section>

    <section class="dashboard-grid">
      <article class="console-panel">
        <div class="console-panel__header">
          <div>
            <p class="console-panel__eyebrow">Signal Stream</p>
            <h3>实时舆情脉冲</h3>
          </div>
          <span class="console-chip">Live</span>
        </div>
        <div class="pulse-list">
          <div class="pulse-item" v-for="feed in pulseFeeds" :key="feed">
            <span class="pulse-item__line"></span>
            <p>{{ feed }}</p>
          </div>
        </div>
      </article>

      <article class="console-panel">
        <div class="console-panel__header">
          <div>
            <p class="console-panel__eyebrow">Alert Queue</p>
            <h3>预警工单队列</h3>
          </div>
          <span class="console-chip console-chip--warn">Priority</span>
        </div>
        <div class="alert-table">
          <div class="alert-row alert-row--head">
            <span>等级</span>
            <span>主题</span>
            <span>来源</span>
            <span>状态</span>
          </div>
          <div class="alert-row" v-for="row in alertRows" :key="row.topic">
            <span>{{ row.level }}</span>
            <span>{{ row.topic }}</span>
            <span>{{ row.source }}</span>
            <span>{{ row.status }}</span>
          </div>
        </div>
      </article>

      <article class="console-panel console-panel--wide">
        <div class="console-panel__header">
          <div>
            <p class="console-panel__eyebrow">Architecture</p>
            <h3>后台框架说明</h3>
          </div>
        </div>
        <div class="roadmap-grid">
          <div class="roadmap-card">
            <span>01</span>
            <strong>独立子应用</strong>
            <p>基于 Vue 3 + Vite + Element Plus，部署路径固定为 `/console`。</p>
          </div>
          <div class="roadmap-card">
            <span>02</span>
            <strong>认证拦截</strong>
            <p>未登录用户访问后台页面时自动跳转登录页，登录状态通过 Cookie 会话维持。</p>
          </div>
          <div class="roadmap-card">
            <span>03</span>
            <strong>用户角色体系</strong>
            <p>角色可独立维护，用户支持多角色绑定，密码以加密形式存储在 PostgreSQL。</p>
          </div>
        </div>
      </article>
    </section>
  </ConsoleLayout>
</template>
