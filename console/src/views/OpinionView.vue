<script setup>
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search, RefreshRight, Share } from "@element-plus/icons-vue";
import QRCode from "qrcode";
import ConsoleLayout from "../layout/ConsoleLayout.vue";
import {
  fetchNews,
  fetchSources,
  createFavorite,
  deleteFavorite,
  createOrUpdateShare,
  interpretArticle,
} from "../api/news";

const items = ref([]);
const total = ref(0);
const loading = ref(false);
const sources = ref([]);

const keyword = ref("");
const selectedDate = ref("");
const selectedSource = ref("");
const favoriteOnly = ref(false);

const highlightKeyword = ref("");
const now = ref(Date.now());

const TABLE_FONT_STORAGE_KEY = "trendradar:opinion-table-font-size";
const LAYOUT_MODE_STORAGE_KEY = "trendradar:opinion-layout-mode";
const TABLE_FONT_MIN = 12;
const TABLE_FONT_MAX = 24;
const TABLE_FONT_DEFAULT = 13;
const tableFontSize = ref(TABLE_FONT_DEFAULT);
const layoutMode = ref("table");
const favoriteDialogVisible = ref(false);
const favoriteSubmitting = ref(false);
const favoriteRemoving = ref(false);
const favoriteForm = ref({
  article_id: null,
  title: "",
  thought: "",
  is_favorite: false,
});
const shareDialogVisible = ref(false);
const shareSubmitting = ref(false);
const shareQrCode = ref("");
const shareForm = ref({
  article_id: null,
  title: "",
  thought: "",
  share_url: "",
});

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

function aiDirectionClass(direction) {
  if (direction === "看多") return "opinion-ai-pill--bull";
  if (direction === "看空") return "opinion-ai-pill--bear";
  return "opinion-ai-pill--neutral";
}

function aiDirectionLabel(direction) {
  if (direction === "看多") return "利多";
  if (direction === "看空") return "利空";
  return "中性";
}

function aiInterpretTooltip(row) {
  if (row?.ai_interpret_status !== "已解读") return "";
  return row.ai_one_line_summary || row.ai_interpret_result || "暂无解读内容";
}

function aiSymbolCode(symbol) {
  return symbol?.symbol_code || symbol?.symbol_name || "-";
}

function aiStrengthStars(strength) {
  const count = Math.min(5, Math.max(1, Number(strength || 1)));
  return "★".repeat(count) + "☆".repeat(5 - count);
}

function strongestSymbol(symbols) {
  if (!symbols || !symbols.length) return null;
  return [...symbols].sort((a, b) => (b.strength || 0) - (a.strength || 0))[0];
}

function interpretStatusLabel(status) {
  if (status === "已解读") return "已解读";
  if (status === "解读中") return "解读中";
  if (status === "解读失败") return "解读失败";
  return "待解读";
}

function interpretStatusClass(status) {
  if (status === "已解读") return "opinion-status--done";
  if (status === "解读中") return "opinion-status--running";
  if (status === "解读失败") return "opinion-status--failed";
  return "opinion-status--pending";
}

async function triggerInterpret(row) {
  if (row.ai_interpret_status === "已解读" || row.ai_interpret_status === "解读中") return;
  try {
    await ElMessageBox.confirm("是否立即解读？", "AI 解读", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "info",
    });
  } catch {
    return;
  }
  row.ai_interpret_status = "解读中";
  try {
    const result = await interpretArticle(row.id);
    if (result.success) {
      row.ai_interpret_status = "已解读";
      row.ai_one_line_summary = result.one_line_summary || "";
      row.ai_interpret_result = result.one_line_summary || "";
      if (result.symbols && result.symbols.length) {
        row.ai_symbols = result.symbols.map((s) => ({
          symbol_name: s.symbol_name,
          symbol_code: s.symbol_code,
          direction: s.direction,
          strength: s.strength,
        }));
      }
      ElMessage.success("解读完成");
    } else if (result.reason && result.reason.includes("已解读")) {
      row.ai_interpret_status = "已解读";
      ElMessage.info("该文章已被后台解读完成，刷新页面可查看完整结果");
    } else {
      row.ai_interpret_status = "解读失败";
      ElMessage.warning(result.reason || "解读失败");
    }
  } catch (e) {
    row.ai_interpret_status = "解读失败";
    ElMessage.error(e.message || "解读失败");
  }
}

function clampTableFontSize(size) {
  return Math.min(TABLE_FONT_MAX, Math.max(TABLE_FONT_MIN, size));
}

function loadTableFontSize() {
  if (typeof window === "undefined") return;
  const raw = window.localStorage.getItem(TABLE_FONT_STORAGE_KEY);
  const parsed = Number.parseInt(raw || "", 10);
  if (Number.isFinite(parsed)) {
    tableFontSize.value = clampTableFontSize(parsed);
  }
}

function saveTableFontSize() {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TABLE_FONT_STORAGE_KEY, String(tableFontSize.value));
}

function loadLayoutMode() {
  if (typeof window === "undefined") return;
  const saved = window.localStorage.getItem(LAYOUT_MODE_STORAGE_KEY);
  if (saved === "table" || saved === "card") {
    layoutMode.value = saved;
  }
}

function setLayoutMode(mode) {
  if (mode !== "table" && mode !== "card") return;
  layoutMode.value = mode;
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LAYOUT_MODE_STORAGE_KEY, mode);
}

function increaseTableFontSize() {
  const nextSize = clampTableFontSize(tableFontSize.value + 1);
  if (nextSize !== tableFontSize.value) {
    tableFontSize.value = nextSize;
    saveTableFontSize();
  }
}

function decreaseTableFontSize() {
  const nextSize = clampTableFontSize(tableFontSize.value - 1);
  if (nextSize !== tableFontSize.value) {
    tableFontSize.value = nextSize;
    saveTableFontSize();
  }
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
    if (favoriteOnly.value) params.favorite_only = true;

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
  favoriteOnly.value = false;
  highlightKeyword.value = "";
  loadNews();
}

function openFavoriteDialog(row) {
  favoriteForm.value = {
    article_id: row.id,
    title: row.title || "",
    thought: row.favorite?.thought || "",
    is_favorite: Boolean(row.is_favorite),
  };
  favoriteDialogVisible.value = true;
}

async function openShareDialog(row) {
  shareForm.value = {
    article_id: row.id,
    title: row.title || "",
    thought: row.share?.thought || "",
    share_url: row.share?.share_url || "",
  };
  shareQrCode.value = "";
  if (shareForm.value.share_url) {
    shareQrCode.value = await QRCode.toDataURL(shareForm.value.share_url, {
      width: 220,
      margin: 1,
    });
  }
  shareDialogVisible.value = true;
}

async function submitFavorite() {
  if (!favoriteForm.value.article_id) return;
  favoriteSubmitting.value = true;
  try {
    const data = await createFavorite({
      article_id: favoriteForm.value.article_id,
      title: favoriteForm.value.title,
      thought: favoriteForm.value.thought,
    });
    const current = items.value.find((item) => item.id === favoriteForm.value.article_id);
    if (current) {
      current.is_favorite = true;
      current.favorite = data.favorite || null;
    }
    favoriteForm.value.is_favorite = true;
    favoriteDialogVisible.value = false;
    ElMessage.success("收藏已保存");
  } catch (e) {
    ElMessage.error(e.message || "收藏失败");
  } finally {
    favoriteSubmitting.value = false;
  }
}

async function removeFavorite(articleId) {
  await deleteFavorite(articleId);
  if (favoriteOnly.value) {
    items.value = items.value.filter((item) => item.id !== articleId);
    total.value = Math.max(0, total.value - 1);
    return;
  }
  const current = items.value.find((item) => item.id === articleId);
  if (current) {
    current.is_favorite = false;
    current.favorite = null;
  }
}

async function removeFavoriteFromDialog() {
  if (!favoriteForm.value.article_id) return;
  favoriteRemoving.value = true;
  try {
    await removeFavorite(favoriteForm.value.article_id);
    favoriteDialogVisible.value = false;
    favoriteForm.value.is_favorite = false;
    ElMessage.success("已取消收藏");
  } catch (e) {
    ElMessage.error(e.message || "取消收藏失败");
  } finally {
    favoriteRemoving.value = false;
  }
}

function toggleFavorite(row) {
  openFavoriteDialog(row);
}

async function submitShare() {
  if (!shareForm.value.article_id) return;
  shareSubmitting.value = true;
  try {
    const data = await createOrUpdateShare({
      article_id: shareForm.value.article_id,
      title: shareForm.value.title,
      thought: shareForm.value.thought,
    });
    shareForm.value.share_url = data.share?.share_url || "";
    shareQrCode.value = shareForm.value.share_url
      ? await QRCode.toDataURL(shareForm.value.share_url, { width: 220, margin: 1 })
      : "";
    const current = items.value.find((item) => item.id === shareForm.value.article_id);
    if (current) {
      current.is_shared = true;
      current.share = data.share || null;
    }
    ElMessage.success("分享已生成");
  } catch (e) {
    ElMessage.error(e.message || "分享失败");
  } finally {
    shareSubmitting.value = false;
  }
}

onMounted(() => {
  loadTableFontSize();
  loadLayoutMode();
  loadSources();
  loadNews();
});
</script>

<template>
  <ConsoleLayout :show-header="false">
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
          <el-switch
            v-model="favoriteOnly"
            class="opinion-favorite-filter"
            inline-prompt
            active-text="我的收藏"
            inactive-text="全部文章"
            @change="onSearch"
          />
        </div>
        <div class="opinion-toolbar__right">
          <span class="opinion-meta" :key="now">
            <span class="opinion-meta__count">{{ total }}</span> 条资讯
          </span>
          <div class="opinion-view-tools">
            <div class="opinion-layout-toggle">
              <button
                type="button"
                class="opinion-layout-btn"
                :class="{ 'is-active': layoutMode === 'table' }"
                @click="setLayoutMode('table')"
              >
                列表
              </button>
              <button
                type="button"
                class="opinion-layout-btn"
                :class="{ 'is-active': layoutMode === 'card' }"
                @click="setLayoutMode('card')"
              >
                卡片
              </button>
            </div>
            <div class="opinion-font-tools">
              <el-button
                class="opinion-font-btn"
                @click="decreaseTableFontSize"
                title="缩小字号"
              >
                A-
              </el-button>
              <el-button
                class="opinion-font-btn"
                @click="increaseTableFontSize"
                title="放大字号"
              >
                A+
              </el-button>
            </div>
          </div>
          <el-button
            :icon="RefreshRight"
            circle
            class="opinion-refresh"
            @click="onClear"
            title="重置筛选"
          />
        </div>
      </div>

      <div
        v-if="layoutMode === 'table'"
        class="opinion-panel console-panel"
      >
        <el-table
          :data="items"
          v-loading="loading"
          class="opinion-table console-table"
          :style="{ '--opinion-table-font-size': `${tableFontSize}px` }"
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
              <div class="opinion-title-wrap">
                <div class="opinion-action-group">
                  <button
                    type="button"
                    class="opinion-favorite-btn"
                    :class="{ 'is-active': row.is_favorite }"
                    :title="row.is_favorite ? '取消收藏' : '收藏文章'"
                    @click="toggleFavorite(row)"
                  >
                    {{ row.is_favorite ? "★" : "☆" }}
                  </button>
                  <button
                    type="button"
                    class="opinion-share-btn"
                    :class="{ 'is-active': row.is_shared }"
                    :title="row.is_shared ? '编辑分享' : '分享文章'"
                    @click="openShareDialog(row)"
                  >
                    <el-icon><Share /></el-icon>
                  </button>
                </div>
                <div class="opinion-title-main">
                  <a
                    :href="row.source_url || '#'"
                    target="_blank"
                    rel="noreferrer"
                    class="opinion-title"
                    v-html="highlight(row.title, highlightKeyword)"
                  ></a>
                  <p
                    v-if="row.favorite?.thought"
                    class="opinion-thought"
                  >
                    我的思路：{{ row.favorite.thought }}
                  </p>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="source_name" label="来源" width="120" align="center">
            <template #default="{ row }">
              <span class="opinion-source-tag">{{ row.source_name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="解读状态" width="110" align="center">
            <template #default="{ row }">
              <span
                class="opinion-status-tag"
                :class="[interpretStatusClass(row.ai_interpret_status), { 'opinion-status-tag--clickable': row.ai_interpret_status !== '已解读' && row.ai_interpret_status !== '解读中' }]"
                @click="triggerInterpret(row)"
              >
                {{ interpretStatusLabel(row.ai_interpret_status) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="AI解读" width="170" align="center">
            <template #default="{ row }">
              <el-tooltip
                v-if="strongestSymbol(row.ai_symbols)"
                :content="aiInterpretTooltip(row)"
                :disabled="!aiInterpretTooltip(row)"
                placement="top"
                effect="dark"
              >
                <span
                  class="opinion-ai-pill"
                  :class="aiDirectionClass(strongestSymbol(row.ai_symbols).direction)"
                >
                  <span>{{ aiSymbolCode(strongestSymbol(row.ai_symbols)) }}</span>
                  <span>{{ aiDirectionLabel(strongestSymbol(row.ai_symbols).direction) }}</span>
                  <span>{{ aiStrengthStars(strongestSymbol(row.ai_symbols).strength) }}</span>
                </span>
              </el-tooltip>
              <span
                v-else
                class="opinion-interpret-now"
                @click="triggerInterpret(row)"
              >立即解读</span>
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

      <div
        v-else
        class="opinion-card-board console-panel"
        :style="{ '--opinion-table-font-size': `${tableFontSize}px` }"
      >
        <div v-loading="loading" class="opinion-card-wrap">
          <article
            v-for="(row, index) in items"
            :key="row.id"
            class="opinion-card-item"
          >
            <div class="opinion-card-index">
              <strong>{{ index + 1 }}</strong>
              <span>No.</span>
            </div>

            <div class="opinion-card-main">
              <div class="opinion-card-meta">
                <span class="opinion-card-pill source">{{ row.source_name || "-" }}</span>
                <span class="opinion-card-pill time">{{ formatTime(row.published_at) }}</span>
                <span class="opinion-card-pill freq">{{ row.crawl_count || 1 }}次</span>
                <span class="opinion-card-pill opinion-card-ai-status">
                  {{ interpretStatusLabel(row.ai_interpret_status) }}
                </span>
                <button
                  type="button"
                  class="opinion-card-pill opinion-card-pill--favorite"
                  :class="{ 'is-active': row.is_favorite }"
                  :title="row.is_favorite ? '取消收藏' : '收藏文章'"
                  @click="toggleFavorite(row)"
                >
                  <span>{{ row.is_favorite ? "★" : "☆" }}</span>
                  <span>{{ row.is_favorite ? "已收藏" : "收藏" }}</span>
                </button>
                <button
                  type="button"
                  class="opinion-card-pill opinion-card-pill--share"
                  :class="{ 'is-active': row.is_shared }"
                  :title="row.is_shared ? '编辑分享' : '分享文章'"
                  @click="openShareDialog(row)"
                >
                  <el-icon><Share /></el-icon>
                  <span>{{ row.is_shared ? "已分享" : "分享" }}</span>
                </button>
                <span
                  v-for="kw in (row.keywords || [])"
                  :key="kw"
                  class="opinion-card-keyword"
                >
                  {{ kw }}
                </span>
                <div
                  v-if="row.ai_symbols && row.ai_symbols.length"
                  class="opinion-card-ai-list"
                >
                  <span
                    v-for="item in row.ai_symbols"
                    :key="`${row.id}-${item.symbol_code}-${item.direction}`"
                    class="opinion-ai-pill"
                    :class="aiDirectionClass(item.direction)"
                  >
                    <span>{{ aiSymbolCode(item) }}</span>
                    <span>{{ aiDirectionLabel(item.direction) }}</span>
                    <span>{{ aiStrengthStars(item.strength) }}</span>
                  </span>
                </div>
              </div>

              <div class="opinion-card-title-row">
                <a
                  :href="row.source_url || '#'"
                  target="_blank"
                  rel="noreferrer"
                  class="opinion-card-link"
                >
                  {{ row.title }}
                </a>
              </div>

              <p v-if="row.summary" class="opinion-card-summary">
                {{ row.summary }}
              </p>
              <p v-if="row.ai_one_line_summary" class="opinion-card-ai-summary">
                ✨ {{ row.ai_one_line_summary }}
              </p>
              <p v-if="row.favorite?.thought" class="opinion-card-thought">
                我的思路：{{ row.favorite.thought }}
              </p>
            </div>
          </article>
        </div>
      </div>

      <el-dialog
        v-model="favoriteDialogVisible"
        title="收藏文章"
        width="560px"
        class="opinion-favorite-dialog"
      >
        <div class="opinion-favorite-dialog__body">
          <div class="opinion-favorite-dialog__title">
            {{ favoriteForm.title || "-" }}
          </div>
          <el-input
            v-model="favoriteForm.thought"
            type="textarea"
            :rows="6"
            maxlength="2000"
            show-word-limit
            placeholder="记录你的研判思路、后续跟踪方向或关注点..."
          />
        </div>
        <template #footer>
          <div class="opinion-favorite-dialog__footer">
            <el-button @click="favoriteDialogVisible = false">取消</el-button>
            <el-button
              v-if="favoriteForm.is_favorite"
              type="danger"
              plain
              :loading="favoriteRemoving"
              @click="removeFavoriteFromDialog"
            >
              取消收藏
            </el-button>
            <el-button
              type="primary"
              :loading="favoriteSubmitting"
              @click="submitFavorite"
            >
              {{ favoriteForm.is_favorite ? "保存思路" : "确认收藏" }}
            </el-button>
          </div>
        </template>
      </el-dialog>

      <el-dialog
        v-model="shareDialogVisible"
        title="分享文章"
        width="640px"
        class="opinion-share-dialog"
      >
        <div class="opinion-share-dialog__body">
          <div class="opinion-share-dialog__title">
            {{ shareForm.title || "-" }}
          </div>
          <el-input
            v-model="shareForm.thought"
            type="textarea"
            :rows="6"
            maxlength="2000"
            show-word-limit
            placeholder="写下你的分享思路、判断逻辑或推荐阅读角度..."
          />
          <div v-if="shareForm.share_url" class="opinion-share-result">
            <img
              v-if="shareQrCode"
              :src="shareQrCode"
              alt="分享二维码"
              class="opinion-share-qrcode"
            />
            <div class="opinion-share-result__meta">
              <div class="opinion-share-result__label">访问地址</div>
              <a
                :href="shareForm.share_url"
                target="_blank"
                rel="noreferrer"
                class="opinion-share-link"
              >
                {{ shareForm.share_url }}
              </a>
            </div>
          </div>
        </div>
        <template #footer>
          <div class="opinion-share-dialog__footer">
            <el-button @click="shareDialogVisible = false">关闭</el-button>
            <el-button
              type="primary"
              :loading="shareSubmitting"
              @click="submitShare"
            >
              {{ shareForm.share_url ? "更新分享" : "生成分享" }}
            </el-button>
          </div>
        </template>
      </el-dialog>
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

:global(.theme--light .opinion-toolbar) {
  background: #ffffff;
  backdrop-filter: none;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
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

.opinion-view-tools {
  display: inline-flex;
  align-items: center;
  gap: 10px;
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

.opinion-favorite-filter {
  --el-switch-on-color: rgba(255, 209, 102, 0.96);
  --el-switch-off-color: rgba(0, 212, 255, 0.22);
  white-space: nowrap;
  flex-shrink: 0;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.02);
}

:global(.theme--light .opinion-favorite-filter) {
  --el-switch-on-color: #409eff;
  --el-switch-off-color: #a8abb2;
  background: transparent;
}

.opinion-favorite-filter :deep(.el-switch) {
  --el-switch-height: 30px;
  --el-switch-button-size: 26px;
}

.opinion-favorite-filter :deep(.el-switch__label) {
  color: rgba(184, 216, 248, 0.78);
  font-size: 12px;
  transition: color 0.2s ease;
}

.opinion-favorite-filter :deep(.el-switch__label.is-active) {
  color: #e7faff;
}

:global(.theme--light .opinion-favorite-filter .el-switch__label) {
  color: #606266;
}

:global(.theme--light .opinion-favorite-filter .el-switch__label.is-active) {
  color: #303133;
}

.opinion-favorite-filter :deep(.el-switch__core) {
  min-width: 100px;
  height: 30px;
  border-radius: 15px;
  border: 1px solid rgba(0, 212, 255, 0.32);
  box-shadow:
    inset 0 0 0 1px rgba(0, 212, 255, 0.05),
    0 0 0 1px rgba(0, 212, 255, 0.08);
}

:global(.theme--light .opinion-favorite-filter .el-switch__core) {
  border: 1px solid #dcdfe6;
  box-shadow: none;
}

.opinion-favorite-filter :deep(.el-switch__core .el-switch__action) {
  left: 8px;
  background: #bfefff;
  border: 1px solid rgba(0, 212, 255, 0.32);
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.18);
}

:global(.theme--light .opinion-favorite-filter .el-switch__core .el-switch__action) {
  background: #ffffff;
  border: 1px solid #dcdfe6;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

.opinion-favorite-filter :deep(.el-switch.is-checked .el-switch__core) {
  border-color: rgba(255, 209, 102, 0.78);
  box-shadow:
    inset 0 0 0 1px rgba(255, 209, 102, 0.12),
    0 0 14px rgba(255, 209, 102, 0.22);
}

:global(.theme--light .opinion-favorite-filter .el-switch.is-checked .el-switch__core) {
  border-color: #409eff;
  box-shadow: none;
}

.opinion-favorite-filter :deep(.el-switch.is-checked .el-switch__core .el-switch__action) {
  left: calc(100% - 26px - 8px);
  background: #fff0b8;
  border-color: rgba(255, 209, 102, 0.68);
}

:global(.theme--light .opinion-favorite-filter .el-switch.is-checked .el-switch__core .el-switch__action) {
  background: #ffffff;
  border-color: #409eff;
}

.opinion-favorite-filter :deep(.el-switch__core .el-switch__inner) {
  width: 100%;
  padding: 0 8px 0 20px;
  box-sizing: border-box;
}

.opinion-favorite-filter :deep(.el-switch.is-checked .el-switch__core .el-switch__inner) {
  padding: 0 20px 0 8px;
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

:global(.theme--light .opinion-meta__count) {
  text-shadow: none;
}

.opinion-refresh {
  --el-button-bg-color: rgba(0, 212, 255, 0.08);
  --el-button-border-color: rgba(0, 212, 255, 0.18);
  --el-button-text-color: var(--console-text-soft);
}

:global(.theme--light .opinion-refresh) {
  --el-button-bg-color: #ffffff;
  --el-button-border-color: #dcdfe6;
}

.opinion-font-tools {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.opinion-layout-toggle {
  display: inline-flex;
  align-items: center;
  padding: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(0, 212, 255, 0.12);
  box-shadow: inset 0 0 0 1px rgba(0, 212, 255, 0.04);
}

:global(.theme--light .opinion-layout-toggle) {
  background: #ffffff;
  border-color: #dcdfe6;
  box-shadow: none;
}

.opinion-layout-btn {
  border: 0;
  background: transparent;
  color: rgba(184, 216, 248, 0.76);
  min-width: 54px;
  padding: 7px 14px;
  border-radius: 999px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

:global(.theme--light .opinion-layout-btn) {
  color: #909399;
}

.opinion-layout-btn:hover {
  color: #e7faff;
}

:global(.theme--light .opinion-layout-btn:hover) {
  color: #409eff;
}

.opinion-layout-btn.is-active {
  color: #03111d;
  background: linear-gradient(135deg, #54e4ff, #8ff4ff);
  box-shadow: 0 0 16px rgba(0, 212, 255, 0.22);
}

:global(.theme--light .opinion-layout-btn.is-active) {
  color: #ffffff;
  background: #409eff;
  box-shadow: none;
}

.opinion-font-btn {
  --el-button-bg-color: rgba(0, 212, 255, 0.08);
  --el-button-border-color: rgba(0, 212, 255, 0.18);
  --el-button-text-color: var(--console-text-soft);
  --el-button-hover-bg-color: rgba(0, 212, 255, 0.18);
  --el-button-hover-border-color: rgba(0, 212, 255, 0.34);
  --el-button-hover-text-color: #e7faff;
  --el-button-active-bg-color: rgba(0, 212, 255, 0.22);
  --el-button-active-border-color: rgba(0, 212, 255, 0.42);
  min-width: 44px;
  padding: 8px 12px;
  font-family: var(--console-mono);
  font-size: 12px;
  letter-spacing: 0.04em;
}

:global(.theme--light .opinion-font-btn) {
  --el-button-bg-color: #ffffff;
  --el-button-border-color: #dcdfe6;
  --el-button-text-color: #606266;
  --el-button-hover-bg-color: #ecf5ff;
  --el-button-hover-border-color: #b3d8ff;
  --el-button-hover-text-color: #409eff;
  --el-button-active-bg-color: #ecf5ff;
  --el-button-active-border-color: #409eff;
}

/* ── 面板 & 表格 ── */
.opinion-panel {
  flex: 1;
  min-height: 0;
  padding: 0;
  overflow: hidden;
}

.opinion-card-board {
  flex: 1;
  min-height: 0;
  padding: 16px;
  overflow: auto;
}

.opinion-card-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.opinion-card-item {
  padding: 16px 18px;
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  background: rgba(8, 14, 34, 0.88);
  border: 1px solid rgba(0, 212, 255, 0.08);
  border-radius: 12px;
  transition: background 0.25s ease, border-color 0.25s ease, transform 0.25s ease;
}

:global(.theme--light .opinion-card-item) {
  background: #ffffff;
  border-color: #ebeef5;
}

.opinion-card-item:hover {
  background: rgba(0, 212, 255, 0.05);
  border-color: rgba(0, 212, 255, 0.22);
  transform: translateY(-1px);
}

:global(.theme--light .opinion-card-item:hover) {
  background: #ffffff;
  border-color: #dcdfe6;
}

.opinion-card-index {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  font-family: var(--console-mono);
  color: var(--console-cyan);
}

.opinion-card-index strong {
  font-size: 28px;
  line-height: 1;
  font-weight: 800;
  text-shadow: 0 0 14px rgba(0, 212, 255, 0.12);
}

:global(.theme--light .opinion-card-index strong) {
  text-shadow: none;
}

.opinion-card-index span {
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--console-muted);
}

.opinion-card-main {
  min-width: 0;
}

.opinion-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  font-size: 11px;
  color: var(--console-muted);
}

.opinion-card-pill,
.opinion-card-keyword {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 999px;
  white-space: nowrap;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

:global(.theme--light .opinion-card-pill,)
:global(.theme--light .opinion-card-keyword) {
  border-color: #dcdfe6;
}

.opinion-card-pill.source {
  color: var(--console-text-soft);
  background: rgba(0, 212, 255, 0.08);
  border-color: rgba(0, 212, 255, 0.14);
}

:global(.theme--light .opinion-card-pill.source) {
  background: #ecf5ff;
  border-color: #d9ecff;
}

.opinion-card-pill.time {
  color: var(--console-muted);
  background: rgba(255, 255, 255, 0.03);
}

:global(.theme--light .opinion-card-pill.time) {
  background: #f5f7fa;
}

.opinion-card-pill.freq {
  color: #95ffe3;
  background: rgba(34, 211, 238, 0.08);
  border-color: rgba(34, 211, 238, 0.12);
}

:global(.theme--light .opinion-card-pill.freq) {
  color: #67c23a;
  background: #f0f9eb;
  border-color: #e1f3d8;
}

.opinion-card-pill--favorite {
  border: 1px solid rgba(0, 212, 255, 0.12);
  background: rgba(255, 255, 255, 0.03);
  color: rgba(184, 216, 248, 0.82);
  cursor: pointer;
  transition: all 0.2s ease;
}

:global(.theme--light .opinion-card-pill--favorite,)
:global(.theme--light .opinion-card-pill--share) {
  background: #ffffff;
  color: #606266;
  border-color: #dcdfe6;
}

.opinion-card-pill--favorite:hover {
  color: #e7faff;
  background: rgba(0, 212, 255, 0.1);
  border-color: rgba(0, 212, 255, 0.22);
}

:global(.theme--light .opinion-card-pill--favorite:hover,)
:global(.theme--light .opinion-card-pill--share:hover) {
  color: #409eff;
  background: #ecf5ff;
  border-color: #b3d8ff;
}

.opinion-card-pill--favorite.is-active {
  color: #2b1a00;
  background: linear-gradient(90deg, #f0a500, #ffd166);
  border-color: rgba(240, 165, 0, 0.35);
  box-shadow: 0 0 18px rgba(240, 165, 0, 0.16);
}

:global(.theme--light .opinion-card-pill--favorite.is-active) {
  color: #e6a23c;
  background: #fdf6ec;
  border-color: #f5dab1;
  box-shadow: none;
}

.opinion-card-pill--share {
  border: 1px solid rgba(0, 212, 255, 0.12);
  background: rgba(255, 255, 255, 0.03);
  color: rgba(184, 216, 248, 0.82);
  cursor: pointer;
  transition: all 0.2s ease;
}

.opinion-card-pill--share:hover {
  color: #e7faff;
  background: rgba(0, 212, 255, 0.1);
  border-color: rgba(0, 212, 255, 0.22);
}

.opinion-card-pill--share.is-active {
  color: #03111d;
  background: linear-gradient(135deg, #54e4ff, #8ff4ff);
  border-color: rgba(84, 228, 255, 0.34);
  box-shadow: 0 0 18px rgba(0, 212, 255, 0.16);
}

:global(.theme--light .opinion-card-pill--share.is-active) {
  color: #409eff;
  background: #ecf5ff;
  border-color: #b3d8ff;
  box-shadow: none;
}

.opinion-card-keyword {
  color: #9ff6ff;
  background: rgba(0, 212, 255, 0.08);
  border-color: rgba(0, 212, 255, 0.15);
}

:global(.theme--light .opinion-card-keyword) {
  color: #409eff;
  background: #ecf5ff;
  border-color: #d9ecff;
}

.opinion-card-link {
  color: #d5ebf8;
  font-size: calc(var(--opinion-table-font-size) + 2px);
  font-weight: 600;
  line-height: 1.55;
  text-decoration: none;
  transition: color 0.25s ease;
  display: block;
}

:global(.theme--light .opinion-card-link) {
  color: #303133;
}

.opinion-card-link:hover {
  color: var(--console-cyan);
}

.opinion-card-summary,
.opinion-card-thought {
  margin: 10px 0 0;
  color: rgba(184, 216, 248, 0.76);
  font-size: var(--opinion-table-font-size);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

:global(.theme--light .opinion-card-summary) {
  color: #606266;
}

.opinion-card-thought {
  color: rgba(255, 209, 102, 0.88);
}

.opinion-card-ai-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.opinion-card-ai-summary {
  margin: 10px 0 0;
  color: rgba(255, 209, 102, 0.88);
  font-size: var(--opinion-table-font-size);
  line-height: 1.7;
}

:global(.theme--light .opinion-card-ai-summary) {
  color: #b8860b;
}

.opinion-ai-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  padding: 4px 10px;
  border-radius: 999px;
  color: rgba(184, 216, 248, 0.62);
  background: rgba(100, 116, 139, 0.16);
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 0 12px rgba(100, 116, 139, 0.12);
  font-size: calc(var(--opinion-table-font-size) - 2px);
}

:global(.theme--light .opinion-ai-status) {
  color: #606266;
  background: #f4f4f5;
  border-color: #dcdfe6;
  box-shadow: none;
}

.opinion-card-ai-status {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(0, 212, 255, 0.08);
  color: var(--console-text-soft);
  font-size: calc(var(--opinion-table-font-size) - 2px);
}

.opinion-card-ai-status--done {
  cursor: help;
}

.opinion-card-ai-status--done:hover,
.opinion-ai-status:hover {
  border-color: rgba(0, 212, 255, 0.32);
  box-shadow: 0 0 16px rgba(0, 212, 255, 0.18);
}

/* ── 立即解读按钮 ── */
.opinion-interpret-now {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: calc(var(--opinion-table-font-size) - 2px);
  color: rgba(56, 189, 248, 0.9);
  background: rgba(56, 189, 248, 0.1);
  border: 1px solid rgba(56, 189, 248, 0.28);
  cursor: pointer;
  transition: all 0.2s ease;
}

.opinion-interpret-now:hover {
  color: #fff;
  background: rgba(56, 189, 248, 0.32);
  border-color: rgba(56, 189, 248, 0.5);
  box-shadow: 0 0 12px rgba(56, 189, 248, 0.28);
}

:global(.theme--light .opinion-interpret-now) {
  color: #409eff;
  background: #ecf5ff;
  border-color: #b3d8ff;
}

:global(.theme--light .opinion-interpret-now:hover) {
  color: #fff;
  background: #409eff;
  border-color: #409eff;
}

/* ── 解读状态标签 ── */
.opinion-status-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: calc(var(--opinion-table-font-size) - 2px);
  border: 1px solid transparent;
  transition: all 0.2s ease;
}

.opinion-status-tag--clickable {
  cursor: pointer;
}

.opinion-status-tag--clickable:hover {
  filter: brightness(1.15);
  transform: scale(1.04);
}

.opinion-status--pending {
  color: rgba(184, 216, 248, 0.62);
  background: rgba(100, 116, 139, 0.16);
  border-color: rgba(148, 163, 184, 0.2);
}

:global(.theme--light .opinion-status--pending) {
  color: #909399;
  background: #f4f4f5;
  border-color: #dcdfe6;
}

.opinion-status--running {
  color: rgba(56, 189, 248, 0.9);
  background: rgba(56, 189, 248, 0.12);
  border-color: rgba(56, 189, 248, 0.28);
}

:global(.theme--light .opinion-status--running) {
  color: #409eff;
  background: #ecf5ff;
  border-color: #b3d8ff;
}

.opinion-status--done {
  color: rgba(74, 222, 128, 0.9);
  background: rgba(74, 222, 128, 0.1);
  border-color: rgba(74, 222, 128, 0.24);
}

:global(.theme--light .opinion-status--done) {
  color: #67c23a;
  background: #f0f9eb;
  border-color: #c2e7b0;
}

.opinion-status--failed {
  color: rgba(248, 113, 113, 0.9);
  background: rgba(248, 113, 113, 0.1);
  border-color: rgba(248, 113, 113, 0.24);
}

:global(.theme--light .opinion-status--failed) {
  color: #f56c6c;
  background: #fef0f0;
  border-color: #fab6b6;
}

:global(.theme--light .opinion-card-thought) {
  color: #e6a23c;
}

.opinion-table {
  --el-table-border-color: rgba(0, 212, 255, 0.06);
  --el-table-header-bg-color: rgba(0, 212, 255, 0.08);
  --el-table-row-hover-bg-color: rgba(0, 212, 255, 0.1);
  --el-table-text-color: var(--console-text-soft);
  --el-table-header-text-color: #b8d8f8;
  --el-table-current-row-bg-color: rgba(0, 212, 255, 0.06);
  --opinion-table-font-size: 13px;
  font-size: var(--opinion-table-font-size);
}

:global(.theme--light .opinion-table) {
  --el-table-border-color: #ebeef5;
  --el-table-header-bg-color: #f5f7fa;
  --el-table-row-hover-bg-color: #f5f7fa;
  --el-table-text-color: #606266;
  --el-table-header-text-color: #303133;
  --el-table-current-row-bg-color: #ecf5ff;
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
  font-size: calc(var(--opinion-table-font-size) - 1px);
}

:global(.theme--light .opinion-table .el-table__header-wrapper th.el-table__cell) {
  background: #f5f7fa;
  backdrop-filter: none;
  border-bottom: 1px solid #ebeef5;
}

/* 覆盖 Element Plus 默认条纹背景 */
.opinion-table :deep(.el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: rgba(255, 255, 255, 0.025) !important;
}

:global(.theme--light .opinion-table .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: #fafafa !important;
}

/* 奇偶行 hover 统一 */
.opinion-table :deep(.el-table__body tr.opinion-row:hover > td.el-table__cell) {
  background: rgba(0, 212, 255, 0.08) !important;
}

:global(.theme--light .opinion-table .el-table__body tr.opinion-row:hover > td.el-table__cell) {
  background: #f5f7fa !important;
}

/* ── 单元格 ── */
.opinion-time {
  font-family: var(--console-mono);
  font-size: calc(var(--opinion-table-font-size) - 1px);
  color: var(--console-muted);
}

:global(.theme--light .opinion-time) {
  color: #606266;
}

.opinion-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  color: #d5ebf8;
}

:global(.theme--light .opinion-title) {
  color: #303133;
}

.opinion-title-wrap {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.opinion-action-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding-top: 1px;
}

.opinion-title-main {
  flex: 1;
  min-width: 0;
}

.opinion-favorite-btn {
  flex: 0 0 auto;
  border: 0;
  background: transparent;
  color: rgba(184, 216, 248, 0.55);
  font-size: calc(var(--opinion-table-font-size) + 3px);
  line-height: 1;
  padding: 0;
  cursor: pointer;
  transition: color 0.2s ease, transform 0.2s ease, text-shadow 0.2s ease;
}

.opinion-favorite-btn:hover {
  color: #ffd166;
  transform: scale(1.08);
  text-shadow: 0 0 10px rgba(255, 209, 102, 0.24);
}

:global(.theme--light .opinion-favorite-btn) {
  color: #909399;
}

:global(.theme--light .opinion-favorite-btn:hover) {
  color: #e6a23c;
  text-shadow: none;
}

:global(.theme--light .opinion-favorite-btn.is-active) {
  color: #e6a23c;
  text-shadow: none;
}

.opinion-favorite-btn.is-active {
  color: #ffd166;
  text-shadow: 0 0 12px rgba(255, 209, 102, 0.26);
}

.opinion-share-btn {
  flex: 0 0 auto;
  width: 26px;
  height: 26px;
  border: 1px solid rgba(0, 212, 255, 0.16);
  border-radius: 999px;
  background: rgba(0, 212, 255, 0.06);
  color: rgba(184, 216, 248, 0.68);
  font-size: calc(var(--opinion-table-font-size) - 2px);
  line-height: 1;
  padding: 0;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
}

:global(.theme--light .opinion-share-btn) {
  border-color: #c0c4cc;
  background: #f5f7fa;
  color: #606266;
}

.opinion-share-btn:hover {
  color: #8ff4ff;
  border-color: rgba(0, 212, 255, 0.3);
  background: rgba(0, 212, 255, 0.14);
  transform: translateY(-1px);
}

:global(.theme--light .opinion-share-btn:hover) {
  color: #409eff;
  border-color: #b3d8ff;
  background: #ecf5ff;
}

.opinion-share-btn.is-active {
  color: #03111d;
  border-color: rgba(84, 228, 255, 0.42);
  background: linear-gradient(135deg, #54e4ff, #8ff4ff);
  box-shadow: 0 0 14px rgba(0, 212, 255, 0.2);
}

:global(.theme--light .opinion-share-btn.is-active) {
  color: #409eff;
  border-color: #b3d8ff;
  background: #ecf5ff;
  box-shadow: none;
}

.opinion-thought {
  margin: 6px 0 0;
  color: rgba(184, 216, 248, 0.72);
  font-size: calc(var(--opinion-table-font-size) - 1px);
  line-height: 1.45;
  white-space: normal;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.opinion-ai-inline {
  margin-top: 8px;
}

.opinion-ai-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: calc(var(--opinion-table-font-size) - 2px);
  line-height: 1;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.opinion-ai-pill--bull {
  color: var(--console-danger);
  background: rgba(255, 107, 107, 0.12);
  border: 1px solid rgba(255, 107, 107, 0.2);
  box-shadow: 0 0 12px rgba(255, 107, 107, 0.18);
}

.opinion-ai-pill--bear {
  color: #3df6b0;
  background: rgba(61, 246, 176, 0.11);
  border: 1px solid rgba(61, 246, 176, 0.2);
  box-shadow: 0 0 12px rgba(61, 246, 176, 0.16);
}

.opinion-ai-pill--neutral {
  color: rgba(184, 216, 248, 0.62);
  background: rgba(100, 116, 139, 0.16);
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 0 12px rgba(100, 116, 139, 0.12);
}

:global(.theme--light .opinion-thought) {
  color: #909399;
}

.opinion-title :deep(.opinion-highlight) {
  color: #ffd54f;
  background: rgba(255, 213, 79, 0.16);
  border-radius: 3px;
  padding: 0 2px;
  font-weight: 600;
}

:global(.theme--light .opinion-title .opinion-highlight) {
  color: #e6a23c;
  background: #fdf6ec;
}

.opinion-source-tag {
  font-size: calc(var(--opinion-table-font-size) - 1px);
  color: var(--console-muted);
}

.opinion-heat {
  font-family: var(--console-mono);
  font-size: calc(var(--opinion-table-font-size) - 1px);
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

:global(.theme--light .opinion-heat--low) {
  color: #409eff;
  background: #ecf5ff;
  border-color: #d9ecff;
}

:global(.theme--light .opinion-heat--mid) {
  color: #b88230;
  background: #fdf6ec;
  border-color: #f5dab1;
  box-shadow: none;
}

:global(.theme--light .opinion-heat--high) {
  color: #d9534f;
  background: #fef0f0;
  border-color: #fbc4c4;
  box-shadow: none;
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
  font-size: calc(var(--opinion-table-font-size) - 2px);
}

:global(.theme--light .opinion-kw-tag) {
  --el-tag-bg-color: #ecf5ff;
  --el-tag-border-color: #d9ecff;
  --el-tag-text-color: #409eff;
}

/* ── Loading ── */
.opinion-table :deep(.el-loading-mask) {
  background: rgba(5, 10, 26, 0.6);
  backdrop-filter: blur(2px);
}

:global(.theme--light .opinion-table .el-loading-mask) {
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: none;
}

.opinion-favorite-dialog :deep(.el-dialog) {
  background: linear-gradient(180deg, rgba(8, 18, 42, 0.98), rgba(4, 10, 28, 0.98));
  border: 1px solid rgba(0, 212, 255, 0.14);
}

:global(.theme--light .opinion-favorite-dialog .el-dialog,)
:global(.theme--light .opinion-share-dialog .el-dialog) {
  background: #ffffff;
  border: 1px solid #e4e7ed;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
}

.opinion-favorite-dialog :deep(.el-dialog__title) {
  color: var(--console-text-soft);
}

.opinion-favorite-dialog__body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.opinion-favorite-dialog__title {
  color: #d5ebf8;
  line-height: 1.6;
}

:global(.theme--light .opinion-favorite-dialog__title,)
:global(.theme--light .opinion-share-dialog__title) {
  color: #303133;
}

.opinion-favorite-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.opinion-share-dialog :deep(.el-dialog) {
  background: linear-gradient(180deg, rgba(8, 18, 42, 0.98), rgba(4, 10, 28, 0.98));
  border: 1px solid rgba(0, 212, 255, 0.14);
}

.opinion-share-dialog :deep(.el-dialog__title) {
  color: var(--console-text-soft);
}

.opinion-share-dialog__body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.opinion-share-dialog__title {
  color: #d5ebf8;
  line-height: 1.6;
}

.opinion-share-result {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
  align-items: center;
  padding: 18px;
  border-radius: 18px;
  background: rgba(0, 212, 255, 0.04);
  border: 1px solid rgba(0, 212, 255, 0.08);
}

:global(.theme--light .opinion-share-result) {
  background: #f5f7fa;
  border-color: #ebeef5;
}

.opinion-share-qrcode {
  width: 220px;
  height: 220px;
  padding: 10px;
  border-radius: 18px;
  background: #ffffff;
  object-fit: contain;
}

.opinion-share-result__meta {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.opinion-share-result__label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(143, 244, 255, 0.8);
}

:global(.theme--light .opinion-share-result__label) {
  color: #909399;
}

.opinion-share-link {
  color: #8ff4ff;
  text-decoration: none;
  line-height: 1.7;
  word-break: break-all;
}

:global(.theme--light .opinion-share-link) {
  color: #409eff;
}

.opinion-share-link:hover {
  color: #bff8ff;
}

.opinion-share-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
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

  .opinion-view-tools {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .opinion-card-item {
    grid-template-columns: 1fr;
  }

  .opinion-card-index {
    flex-direction: row;
    justify-content: flex-start;
  }

  .opinion-share-result {
    grid-template-columns: 1fr;
    justify-items: center;
  }

  .opinion-share-result__meta {
    width: 100%;
  }
}
</style>
