<script setup>
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Search, RefreshRight } from "@element-plus/icons-vue";
import ConsoleLayout from "../layout/ConsoleLayout.vue";
import { fetchNews, fetchSources } from "../api/news";

const items = ref([]);
const total = ref(0);
const loading = ref(false);
const sources = ref([]);

const keyword = ref("");
const selectedDate = ref("");
const selectedSource = ref("");

const highlightKeyword = ref("");
const now = ref(Date.now());

function escapeHtml(text) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(text).replace(/[&<>"']/g, (c) => map[c]);
}

function highlight(text, kw) {
  const safe = escapeHtml(text);
  if (!kw || !kw.trim()) return safe;
  const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return safe.replace(new RegExp(`(${escaped})`, "gi"), '<mark class="opinion-highlight">$1</mark>');
}

function formatTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function heatLevel(count) {
  if (count >= 10) return "high";
  if (count >= 3) return "mid";
  return "low";
}

async function loadSources() {
  try {
    const data = await fetchSources();
    sources.value = data.sources || [];
  } catch {
    // 来源加载失败不影响主流程
  }
}

async function loadNews() {
  loading.value = true;
  try {
    const params = { page: 1, page_size: 200 };
    if (keyword.value.trim()) {
      params.keyword = keyword.value.trim();
      highlightKeyword.value = keyword.value.trim();
    } else {
      highlightKeyword.value = "";
    }
    if (selectedDate.value) params.date = selectedDate.value;
    if (selectedSource.value) params.source = selectedSource.value;

    const data = await fetchNews(params);
    items.value = data.items || [];
    total.value = data.total || 0;
    now.value = Date.now();
  } catch (e) {
    ElMessage.error(e.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  loadNews();
}

function onClear() {
  keyword.value = "";
  selectedDate.value = "";
  selectedSource.value = "";
  highlightKeyword.value = "";
  loadNews();
}

onMounted(() => {
  loadSources();
  loadNews();
});
</script>

<template>
  <ConsoleLayout>
    <section class="opinion-page">
      <!-- 工具栏 -->
      <div class="opinion-toolbar">
        <div class="opinion-toolbar__left">
          <el-input
            v-model="keyword"
            placeholder="输入关键词，回车搜索..."
            :prefix-icon="Search"
            clearable
            class="opinion-search"
            @keyup.enter="onSearch"
            @clear="onSearch"
          />
          <el-date-picker
            v-model="selectedDate"
            type="date"
            placeholder="选择日期"
            format="YYYY/MM/DD"
            value-format="YYYY-MM-DD"
            clearable
            class="opinion-date"
            @change="onSearch"
          />
          <el-select
            v-model="selectedSource"
            placeholder="全部来源"
            clearable
            class="opinion-source"
            @change="onSearch"
          >
            <el-option
              v-for="src in sources"
              :key="src"
              :label="src"
              :value="src"
            />
          </el-select>
        </div>
        <div class="opinion-toolbar__right">
          <span class="opinion-meta" :key="now">
            <span class="opinion-meta__count">{{ total }}</span> 条资讯
          </span>
          <el-button
            :icon="RefreshRight"
            circle
            class="opinion-refresh"
            @click="onClear"
            title="重置筛选"
          />
        </div>
      </div>

      <!-- 表格 -->
      <div class="opinion-panel console-panel">
        <el-table
          :data="items"
          v-loading="loading"
          class="opinion-table console-table"
          row-class-name="opinion-row"
          stripe
          height="100%"
        >
          <el-table-column prop="published_at" label="时间" width="170" align="center">
            <template #default="{ row }">
              <span class="opinion-time">{{ formatTime(row.published_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="新闻标题" min-width="280">
            <template #default="{ row }">
              <span
                class="opinion-title"
                v-html="highlight(row.title, highlightKeyword)"
              ></span>
            </template>
          </el-table-column>
          <el-table-column prop="source_name" label="来源" width="120" align="center">
            <template #default="{ row }">
              <span class="opinion-source-tag">{{ row.source_name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="crawl_count" label="热度" width="90" align="center">
            <template #default="{ row }">
              <span
                class="opinion-heat"
                :class="`opinion-heat--${heatLevel(row.crawl_count || 1)}`"
              >
                {{ row.crawl_count || 1 }} 
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="keywords" label="匹配关键词" width="180">
            <template #default="{ row }">
              <div class="opinion-keywords">
                <el-tag
                  v-for="kw in (row.keywords || [])"
                  :key="kw"
                  size="small"
                  class="opinion-kw-tag"
                  :type="highlightKeyword && kw.toLowerCase().includes(highlightKeyword.toLowerCase()) ? 'danger' : ''"
                >
                  {{ kw }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>
  </ConsoleLayout>
</template>

<style scoped>
.opinion-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 16px;
}

/* ── 工具栏 ── */
.opinion-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 12px;
  border: 1px solid var(--console-line);
  background:
    linear-gradient(180deg, rgba(0, 212, 255, 0.02), transparent 24%),
    var(--console-panel);
  backdrop-filter: blur(12px);
  flex-wrap: wrap;
}

.opinion-toolbar__left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.opinion-toolbar__right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.opinion-search {
  width: 220px;
}

.opinion-date {
  width: 156px;
}

.opinion-source {
  width: 164px;
}

.opinion-meta {
  font-size: 13px;
  color: var(--console-muted);
  white-space: nowrap;
}

.opinion-meta__count {
  font-family: var(--console-mono);
  font-size: 15px;
  color: var(--console-cyan);
  text-shadow: 0 0 10px rgba(0, 212, 255, 0.28);
}

.opinion-refresh {
  --el-button-bg-color: rgba(0, 212, 255, 0.08);
  --el-button-border-color: rgba(0, 212, 255, 0.18);
  --el-button-text-color: var(--console-text-soft);
}

/* ── 面板 & 表格 ── */
.opinion-panel {
  flex: 1;
  min-height: 0;
  padding: 0;
  overflow: hidden;
}

.opinion-table {
  --el-table-border-color: rgba(0, 212, 255, 0.06);
  --el-table-header-bg-color: rgba(0, 212, 255, 0.08);
  --el-table-row-hover-bg-color: rgba(0, 212, 255, 0.1);
  --el-table-text-color: var(--console-text-soft);
  --el-table-header-text-color: #b8d8f8;
  --el-table-current-row-bg-color: rgba(0, 212, 255, 0.06);
  font-size: 13px;
}

/* 表头固定 - sticky */
.opinion-table :deep(.el-table__header-wrapper) {
  position: sticky;
  top: 0;
  z-index: 10;
}

.opinion-table :deep(.el-table__header-wrapper th.el-table__cell) {
  background: rgba(0, 212, 255, 0.08);
  backdrop-filter: blur(8px);
  border-bottom: 2px solid rgba(0, 212, 255, 0.18);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-size: 12px;
}

/* 覆盖 Element Plus 默认条纹背景 */
.opinion-table :deep(.el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: rgba(255, 255, 255, 0.025) !important;
}

/* 奇偶行 hover 统一 */
.opinion-table :deep(.el-table__body tr.opinion-row:hover > td.el-table__cell) {
  background: rgba(0, 212, 255, 0.08) !important;
}

/* ── 单元格 ── */
.opinion-time {
  font-family: var(--console-mono);
  font-size: 12px;
  color: var(--console-muted);
}

.opinion-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  color: #d5ebf8;
}

.opinion-title :deep(.opinion-highlight) {
  color: #ffd54f;
  background: rgba(255, 213, 79, 0.16);
  border-radius: 3px;
  padding: 0 2px;
  font-weight: 600;
}

.opinion-source-tag {
  font-size: 12px;
  color: var(--console-muted);
}

.opinion-heat {
  font-family: var(--console-mono);
  font-size: 12px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  padding: 4px 10px;
  border-radius: 999px;
}

.opinion-heat--low {
  color: #95ffe3;
  background: rgba(34, 211, 238, 0.08);
  border: 1px solid rgba(34, 211, 238, 0.12);
}

.opinion-heat--mid {
  color: var(--console-gold);
  background: rgba(240, 165, 0, 0.1);
  border: 1px solid rgba(240, 165, 0, 0.2);
  box-shadow: 0 0 8px rgba(240, 165, 0, 0.12);
}

.opinion-heat--high {
  color: var(--console-danger);
  background: rgba(255, 107, 107, 0.12);
  border: 1px solid rgba(255, 107, 107, 0.2);
  box-shadow: 0 0 12px rgba(255, 107, 107, 0.18);
}

.opinion-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.opinion-kw-tag {
  --el-tag-bg-color: rgba(0, 212, 255, 0.08);
  --el-tag-border-color: rgba(0, 212, 255, 0.14);
  --el-tag-text-color: var(--console-text-soft);
  font-size: 11px;
}

/* ── Loading ── */
.opinion-table :deep(.el-loading-mask) {
  background: rgba(5, 10, 26, 0.6);
  backdrop-filter: blur(2px);
}

/* ── 响应式 ── */
@media (max-width: 1199px) {
  .opinion-search { width: 180px; }
  .opinion-date { width: 140px; }
  .opinion-source { width: 140px; }
}

@media (max-width: 767px) {
  .opinion-toolbar {
    padding: 12px 14px;
    gap: 10px;
  }

  .opinion-toolbar__left {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .opinion-search,
  .opinion-date,
  .opinion-source {
    width: 100%;
  }

  .opinion-toolbar__right {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
