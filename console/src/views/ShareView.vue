<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElResult } from "element-plus";
import { fetchPublicShare } from "../api/news";

const route = useRoute();
const loading = ref(false);
const share = ref(null);
const errorMessage = ref("");

function formatTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

const displayTitle = computed(() => share.value?.title || share.value?.shared_title || "分享文章");

async function loadShare() {
  loading.value = true;
  errorMessage.value = "";
  try {
    const data = await fetchPublicShare(route.params.token);
    share.value = data.share || null;
    if (!share.value) {
      errorMessage.value = "分享内容不存在或已失效";
    }
  } catch (e) {
    errorMessage.value = e.message || "加载分享内容失败";
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadShare();
});
</script>

<template>
  <main class="share-page">
    <div v-if="loading" class="share-loading">正在加载分享内容...</div>

    <section v-else-if="share" class="share-card">
      <div class="share-eyebrow">TrendRadar Share</div>
      <h1 class="share-title">{{ displayTitle }}</h1>

      <div class="share-meta">
        <span class="share-pill">{{ share.source_name || "未知来源" }}</span>
        <span class="share-pill">{{ formatTime(share.published_at) }}</span>
        <span class="share-pill share-pill--gold">分享人：{{ share.share_user_name || "-" }}</span>
      </div>

      <section v-if="share.thought" class="share-block share-block--highlight">
        <h2>分享思路</h2>
        <p>{{ share.thought }}</p>
      </section>

      <section v-if="share.summary" class="share-block">
        <h2>摘要</h2>
        <p>{{ share.summary }}</p>
      </section>

      <section v-if="share.content" class="share-block">
        <h2>内容</h2>
        <p>{{ share.content }}</p>
      </section>
    </section>

    <el-result
      v-else
      icon="warning"
      title="分享内容不可用"
      :sub-title="errorMessage || '未找到对应分享记录'"
      class="share-empty"
    />
  </main>
</template>

<style scoped>
.share-page {
  min-height: 100vh;
  padding: 32px 20px;
  background:
    radial-gradient(circle at top, rgba(0, 212, 255, 0.12), transparent 35%),
    linear-gradient(180deg, #091226, #040918 78%);
  color: #d5ebf8;
}

.share-loading {
  max-width: 960px;
  margin: 0 auto;
  text-align: center;
  color: rgba(184, 216, 248, 0.82);
}

.share-card {
  max-width: 960px;
  margin: 0 auto;
  padding: 28px;
  border-radius: 24px;
  background: rgba(8, 14, 34, 0.9);
  border: 1px solid rgba(0, 212, 255, 0.1);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.28);
}

.share-eyebrow {
  color: #8ff4ff;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.share-title {
  margin: 12px 0 18px;
  font-size: clamp(28px, 4vw, 40px);
  line-height: 1.3;
}

.share-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 24px;
}

.share-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(0, 212, 255, 0.08);
  border: 1px solid rgba(0, 212, 255, 0.14);
  color: rgba(184, 216, 248, 0.88);
  font-size: 13px;
}

.share-pill--gold {
  color: #2b1a00;
  background: linear-gradient(90deg, #f0a500, #ffd166);
  border-color: rgba(240, 165, 0, 0.35);
}

.share-block {
  margin-top: 18px;
  padding: 18px 20px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.share-block--highlight {
  background: rgba(255, 209, 102, 0.08);
  border-color: rgba(255, 209, 102, 0.16);
}

.share-block h2 {
  margin: 0 0 10px;
  font-size: 16px;
  color: #8ff4ff;
}

.share-block p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.8;
  color: rgba(213, 235, 248, 0.9);
}

.share-empty {
  max-width: 760px;
  margin: 0 auto;
}

@media (max-width: 767px) {
  .share-page {
    padding: 18px 12px;
  }

  .share-card {
    padding: 18px 16px;
    border-radius: 18px;
  }
}
</style>
