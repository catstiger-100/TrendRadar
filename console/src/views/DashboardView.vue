<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import { ElMessage } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import VChart from "vue-echarts";
import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import ConsoleLayout from "../layout/ConsoleLayout.vue";
import { fetchSituationOverview } from "../api/situation";

echarts.use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

const loading = ref(false);
const stats = ref({ overview: {}, source_stats: [], hourly_stats: [] });
const symbolStats = ref({ direction_stats: [], top_symbols: [] });
const articles = ref([]);
const analysis = ref({ success: false, error: "", analyzed_at: 0 });
let refreshTimer = null;

const theme = ref("dark");
const THEME_KEY = "trendradar:console-theme";

function readTheme() {
  if (typeof document === "undefined") return;
  theme.value = document.documentElement.dataset.theme || "dark";
}

function chartTextColor() {
  return theme.value === "light" ? "#303133" : "#b8d8f8";
}

function chartBorderColor() {
  return theme.value === "light" ? "#e4e7ed" : "rgba(0,212,255,0.12)";
}

const overviewCards = computed(() => {
  const o = stats.value.overview || {};
  return [
    { title: "24h 新闻总数", value: o.total_articles || 0, accent: "cyan" },
    { title: "已 AI 解读", value: o.interpreted_count || 0, accent: "green" },
    { title: "品种提及", value: symbolStats.value.top_symbols?.length || 0, accent: "gold" },
    {
      title: "解读覆盖率",
      value: o.total_articles
        ? Math.round(((o.interpreted_count || 0) / o.total_articles) * 100) + "%"
        : "0%",
      accent: "purple",
    },
  ];
});

const sourceChartOption = computed(() => {
  const data = (stats.value.source_stats || []).slice(0, 12);
  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: "3%", right: "8%", bottom: "3%", top: "8%", containLabel: true },
    xAxis: {
      type: "category",
      data: data.map((d) => d.source_name),
      axisLabel: { color: chartTextColor(), rotate: 30, fontSize: 11 },
      axisLine: { lineStyle: { color: chartBorderColor() } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: chartTextColor(), fontSize: 11 },
      splitLine: { lineStyle: { color: chartBorderColor() } },
    },
    series: [
      {
        type: "bar",
        data: data.map((d) => d.count),
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: theme.value === "light" ? "#409eff" : "#00d4ff" },
            { offset: 1, color: theme.value === "light" ? "#b3d8ff" : "rgba(0,212,255,0.2)" },
          ]),
        },
      },
    ],
  };
});

const hourlyChartOption = computed(() => {
  const data = stats.value.hourly_stats || [];
  const hours = Array.from({ length: 24 }, (_, i) => i);
  const map = {};
  data.forEach((d) => (map[d.hour] = d.count));
  return {
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "3%", top: "8%", containLabel: true },
    xAxis: {
      type: "category",
      data: hours.map((h) => `${h}:00`),
      axisLabel: { color: chartTextColor(), fontSize: 10, interval: 3 },
      axisLine: { lineStyle: { color: chartBorderColor() } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: chartTextColor(), fontSize: 11 },
      splitLine: { lineStyle: { color: chartBorderColor() } },
    },
    series: [
      {
        type: "line",
        data: hours.map((h) => map[h] || 0),
        smooth: true,
        symbol: "circle",
        symbolSize: 4,
        lineStyle: { color: theme.value === "light" ? "#409eff" : "#22d3ee", width: 2 },
        itemStyle: { color: theme.value === "light" ? "#409eff" : "#22d3ee" },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: theme.value === "light" ? "rgba(64,158,255,0.35)" : "rgba(34,211,238,0.32)" },
            { offset: 1, color: theme.value === "light" ? "rgba(64,158,255,0.0)" : "rgba(34,211,238,0.0)" },
          ]),
        },
      },
    ],
  };
});

const directionChartOption = computed(() => {
  const data = symbolStats.value.direction_stats || [];
  const colors = {
    "看多": theme.value === "light" ? "#f56c6c" : "#ff6b6b",
    "看空": theme.value === "light" ? "#67c23a" : "#3df6b0",
    "中性": theme.value === "light" ? "#909399" : "#7b7b9e",
  };
  return {
    tooltip: { trigger: "item" },
    legend: {
      bottom: 0,
      textStyle: { color: chartTextColor(), fontSize: 11 },
    },
    series: [
      {
        type: "pie",
        radius: ["45%", "72%"],
        center: ["50%", "46%"],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 14, fontWeight: "bold" } },
        data: data.map((d) => ({
          name: d.direction || "未知",
          value: d.count || 0,
          itemStyle: { color: colors[d.direction] || "#7b7b9e" },
        })),
      },
    ],
  };
});

const topSymbolsChartOption = computed(() => {
  const data = (symbolStats.value.top_symbols || []).slice(0, 10).reverse();
  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: "3%", right: "10%", bottom: "3%", top: "8%", containLabel: true },
    xAxis: {
      type: "value",
      axisLabel: { color: chartTextColor(), fontSize: 11 },
      splitLine: { lineStyle: { color: chartBorderColor() } },
    },
    yAxis: {
      type: "category",
      data: data.map((d) => d.symbol_code || d.symbol_name),
      axisLabel: { color: chartTextColor(), fontSize: 11, fontWeight: "bold" },
      axisLine: { lineStyle: { color: chartBorderColor() } },
    },
    series: [
      {
        type: "bar",
        data: data.map((d) => ({
          value: d.mention_count || 0,
          itemStyle: {
            borderRadius: [0, 4, 4, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: theme.value === "light" ? "#a855f7" : "#a855f7" },
              { offset: 1, color: theme.value === "light" ? "#d4bfff" : "rgba(168,85,247,0.3)" },
            ]),
          },
        })),
      },
    ],
  };
});

function formatTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatShortTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function analysisTimeAgo() {
  const ts = analysis.value.analyzed_at;
  if (!ts) return "暂无数据";
  const diff = Math.floor((Date.now() / 1000) - ts);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  return `${Math.floor(diff / 3600)} 小时前`;
}

async function loadData() {
  try {
    const data = await fetchSituationOverview();
    stats.value = data.stats || { overview: {}, source_stats: [], hourly_stats: [] };
    symbolStats.value = data.symbol_stats || { direction_stats: [], top_symbols: [] };
    articles.value = data.articles || [];
    analysis.value = data.analysis || { success: false, error: "", analyzed_at: 0 };
  } catch (e) {
    // 首次加载静默失败，后续轮询不弹错误
  }
}

function onChartReady() {
  readTheme();
}

onMounted(() => {
  readTheme();
  loadData().then(() => {
    onChartReady();
  });
  refreshTimer = setInterval(() => {
    loadData();
  }, 60000);

  // 监听主题变化以更新图表
  if (typeof window !== "undefined") {
    const observer = new MutationObserver(() => {
      readTheme();
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }
});

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<template>
  <ConsoleLayout :show-header="false">
    <div class="situation-page">
      <!-- 统计卡片 -->
      <div class="situation-kpi-row">
        <div
          v-for="card in overviewCards"
          :key="card.title"
          class="situation-kpi"
          :class="`situation-kpi--${card.accent}`"
        >
          <span class="situation-kpi__label">{{ card.title }}</span>
          <strong class="situation-kpi__value">{{ card.value }}</strong>
        </div>
      </div>

      <!-- 3 列两行布局 -->
      <div class="situation-main-grid">
        <!-- Row 1: 最新新闻 | 来源分布 | 品种多空分布 -->
        <div class="console-panel situation-news-panel">
          <div class="situation-news-panel__header">
            <div>
              <p class="console-panel__eyebrow">Live Feed</p>
              <h3>最新新闻</h3>
            </div>
            <span class="console-chip">{{ articles.length }} 条</span>
          </div>
          <div class="situation-news-viewport">
            <div v-if="articles.length === 0" class="situation-news-empty">
              24 小时内暂无新闻
            </div>
            <div v-else class="situation-news-track">
              <template v-for="article in articles" :key="article.id">
                <a
                  class="situation-news-item"
                  :href="article.source_url || '#'"
                  target="_blank"
                  rel="noreferrer"
                >
                  <span class="situation-news-item__time">{{ formatShortTime(article.published_at || article.created_at) }}</span>
                  <span class="situation-news-item__source">{{ article.source_name || "-" }}</span>
                  <span class="situation-news-item__title" :title="article.title">{{ article.title }}</span>
                </a>
              </template>
              <template v-for="article in articles" :key="'dup-' + article.id">
                <a
                  class="situation-news-item"
                  :href="article.source_url || '#'"
                  target="_blank"
                  rel="noreferrer"
                  aria-hidden="true"
                >
                  <span class="situation-news-item__time">{{ formatShortTime(article.published_at || article.created_at) }}</span>
                  <span class="situation-news-item__source">{{ article.source_name || "-" }}</span>
                  <span class="situation-news-item__title" :title="article.title">{{ article.title }}</span>
                </a>
              </template>
            </div>
          </div>
        </div>

        <div class="console-panel situation-chart-panel">
          <div class="console-panel__header">
            <div>
              <p class="console-panel__eyebrow">Source Distribution</p>
              <h3>来源分布</h3>
            </div>
          </div>
          <v-chart class="situation-chart" :option="sourceChartOption" autoresize />
        </div>

        <div class="console-panel situation-chart-panel">
          <div class="console-panel__header">
            <div>
              <p class="console-panel__eyebrow">Direction Distribution</p>
              <h3>品种多空分布</h3>
            </div>
          </div>
          <v-chart class="situation-chart" :option="directionChartOption" autoresize />
        </div>

        <!-- Row 2: 24h 采集时序 | 热门品种 TOP 10 | AI 态势解读 -->
        <div class="console-panel situation-chart-panel">
          <div class="console-panel__header">
            <div>
              <p class="console-panel__eyebrow">Hourly Activity</p>
              <h3>24h 采集时序</h3>
            </div>
          </div>
          <v-chart class="situation-chart" :option="hourlyChartOption" autoresize />
        </div>

        <div class="console-panel situation-chart-panel">
          <div class="console-panel__header">
            <div>
              <p class="console-panel__eyebrow">Hot Symbols</p>
              <h3>热门品种 TOP 10</h3>
            </div>
          </div>
          <v-chart class="situation-chart" :option="topSymbolsChartOption" autoresize />
        </div>

        <div class="console-panel situation-analysis-panel">
          <div class="console-panel__header">
            <div>
              <p class="console-panel__eyebrow">AI Situation Analysis</p>
              <h3>AI 态势解读</h3>
            </div>
            <span class="console-chip" :class="{ 'console-chip--warn': !analysis.success }">
              {{ analysis.success ? `${analysisTimeAgo()}` : "暂未生成" }}
            </span>
          </div>
          <div v-if="analysis.success" class="situation-analysis-body">
            <div class="situation-analysis-section">
              <h4>核心热点态势</h4>
              <p>{{ analysis.core_trends || "暂无" }}</p>
            </div>
            <div class="situation-analysis-section">
              <h4>舆论风向争议</h4>
              <p>{{ analysis.sentiment_controversy || "暂无" }}</p>
            </div>
            <div class="situation-analysis-section">
              <h4>异动与弱信号</h4>
              <p>{{ analysis.signals || "暂无" }}</p>
            </div>
            <div class="situation-analysis-section">
              <h4>RSS 深度洞察</h4>
              <p>{{ analysis.rss_insights || "暂无" }}</p>
            </div>
            <div class="situation-analysis-section">
              <h4>研判策略建议</h4>
              <p>{{ analysis.outlook_strategy || "暂无" }}</p>
            </div>
          </div>
          <div v-else class="situation-analysis-empty">
            <el-icon class="is-loading" v-if="!analysis.error"><Loading /></el-icon>
            <p>{{ analysis.error || "等待首次 AI 解读..." }}</p>
          </div>
        </div>
      </div>
    </div>
  </ConsoleLayout>
</template>

<style scoped>
.situation-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 16px;
  padding: 4px 0;
}

/* ── KPI 卡片 ── */
.situation-kpi-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

@keyframes kpi-breathe-cyan {
  0%, 100% {
    box-shadow: 0 0 12px rgba(0, 212, 255, 0.12), inset 0 1px 0 rgba(0, 212, 255, 0.06);
    border-color: rgba(0, 212, 255, 0.12);
  }
  50% {
    box-shadow: 0 0 28px rgba(0, 212, 255, 0.24), inset 0 1px 0 rgba(0, 212, 255, 0.14);
    border-color: rgba(0, 212, 255, 0.28);
  }
}

@keyframes kpi-breathe-green {
  0%, 100% {
    box-shadow: 0 0 12px rgba(61, 246, 176, 0.1), inset 0 1px 0 rgba(61, 246, 176, 0.05);
    border-color: rgba(61, 246, 176, 0.1);
  }
  50% {
    box-shadow: 0 0 26px rgba(61, 246, 176, 0.22), inset 0 1px 0 rgba(61, 246, 176, 0.12);
    border-color: rgba(61, 246, 176, 0.26);
  }
}

@keyframes kpi-breathe-gold {
  0%, 100% {
    box-shadow: 0 0 12px rgba(240, 165, 0, 0.1), inset 0 1px 0 rgba(240, 165, 0, 0.05);
    border-color: rgba(240, 165, 0, 0.1);
  }
  50% {
    box-shadow: 0 0 26px rgba(240, 165, 0, 0.22), inset 0 1px 0 rgba(240, 165, 0, 0.12);
    border-color: rgba(240, 165, 0, 0.26);
  }
}

@keyframes kpi-breathe-purple {
  0%, 100% {
    box-shadow: 0 0 12px rgba(168, 85, 247, 0.1), inset 0 1px 0 rgba(168, 85, 247, 0.05);
    border-color: rgba(168, 85, 247, 0.1);
  }
  50% {
    box-shadow: 0 0 26px rgba(168, 85, 247, 0.22), inset 0 1px 0 rgba(168, 85, 247, 0.12);
    border-color: rgba(168, 85, 247, 0.26);
  }
}

.situation-kpi {
  padding: 18px 20px;
  border-radius: 12px;
  border: 1px solid var(--console-line);
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
  overflow: hidden;
}

.situation-kpi::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  opacity: 0.4;
  transition: opacity 0.3s ease;
}

.situation-kpi:hover::before {
  opacity: 0.7;
}

.situation-kpi--cyan {
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.08), rgba(0, 150, 200, 0.03) 50%, rgba(5, 10, 26, 0.6));
  animation: kpi-breathe-cyan 3s ease-in-out infinite;
}

.situation-kpi--cyan::before {
  background: radial-gradient(ellipse at 80% 20%, rgba(0, 212, 255, 0.12), transparent 60%);
}

.situation-kpi--green {
  background: linear-gradient(135deg, rgba(61, 246, 176, 0.08), rgba(30, 200, 140, 0.03) 50%, rgba(5, 10, 26, 0.6));
  animation: kpi-breathe-green 3.4s ease-in-out infinite;
}

.situation-kpi--green::before {
  background: radial-gradient(ellipse at 80% 20%, rgba(61, 246, 176, 0.1), transparent 60%);
}

.situation-kpi--gold {
  background: linear-gradient(135deg, rgba(240, 165, 0, 0.08), rgba(200, 140, 0, 0.03) 50%, rgba(5, 10, 26, 0.6));
  animation: kpi-breathe-gold 3.2s ease-in-out infinite;
}

.situation-kpi--gold::before {
  background: radial-gradient(ellipse at 80% 20%, rgba(240, 165, 0, 0.1), transparent 60%);
}

.situation-kpi--purple {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.08), rgba(130, 60, 200, 0.03) 50%, rgba(5, 10, 26, 0.6));
  animation: kpi-breathe-purple 3.6s ease-in-out infinite;
}

.situation-kpi--purple::before {
  background: radial-gradient(ellipse at 80% 20%, rgba(168, 85, 247, 0.1), transparent 60%);
}

:global(.theme--light .situation-kpi--cyan) {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.06), rgba(64, 158, 255, 0.01) 50%, #ffffff);
  animation: none;
}

:global(.theme--light .situation-kpi--green) {
  background: linear-gradient(135deg, rgba(103, 194, 58, 0.06), rgba(103, 194, 58, 0.01) 50%, #ffffff);
  animation: none;
}

:global(.theme--light .situation-kpi--gold) {
  background: linear-gradient(135deg, rgba(230, 162, 60, 0.06), rgba(230, 162, 60, 0.01) 50%, #ffffff);
  animation: none;
}

:global(.theme--light .situation-kpi--purple) {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.06), rgba(168, 85, 247, 0.01) 50%, #ffffff);
  animation: none;
}

.situation-kpi__label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--console-muted);
  position: relative;
  z-index: 1;
}

.situation-kpi__value {
  font-family: var(--console-mono);
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
  position: relative;
  z-index: 1;
}

.situation-kpi--cyan .situation-kpi__value {
  color: var(--console-cyan);
  text-shadow: 0 0 18px rgba(0, 212, 255, 0.28);
}

:global(.theme--light .situation-kpi--cyan .situation-kpi__value) {
  color: #409eff;
  text-shadow: none;
}

.situation-kpi--green .situation-kpi__value {
  color: #3df6b0;
  text-shadow: 0 0 18px rgba(61, 246, 176, 0.22);
}

:global(.theme--light .situation-kpi--green .situation-kpi__value) {
  color: #67c23a;
  text-shadow: none;
}

.situation-kpi--gold .situation-kpi__value {
  color: var(--console-gold);
  text-shadow: 0 0 18px rgba(240, 165, 0, 0.22);
}

:global(.theme--light .situation-kpi--gold .situation-kpi__value) {
  text-shadow: none;
}

.situation-kpi--purple .situation-kpi__value {
  color: var(--console-purple);
  text-shadow: 0 0 18px rgba(168, 85, 247, 0.22);
}

:global(.theme--light .situation-kpi--purple .situation-kpi__value) {
  text-shadow: none;
}

/* ── 3 列两行主布局 ── */
.situation-main-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-template-rows: 1fr 1fr;
  gap: 14px;
  flex: 1;
  min-height: 0;
}

.situation-chart-panel {
  padding: 16px;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.situation-chart {
  flex: 1;
  min-height: 0;
}

.situation-news-panel {
  padding: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.situation-news-panel__header {
  flex-shrink: 0;
  padding: 16px 16px 12px;
  border-bottom: 1px solid var(--console-line);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.situation-news-panel__header h3 {
  margin: 0;
  font-size: 18px;
  color: var(--console-heading);
}

.situation-news-viewport {
  flex: 1;
  overflow: hidden;
  position: relative;
  min-height: 0;
}

@keyframes scroll-news {
  0% { transform: translateY(0); }
  100% { transform: translateY(-50%); }
}

.situation-news-track {
  animation: scroll-news 80s linear infinite;
}

.situation-news-track:hover {
  animation-play-state: paused;
}

.situation-news-empty {
  padding: 40px 16px;
  text-align: center;
  color: var(--console-muted);
  font-size: 13px;
}

.situation-news-item {
  display: grid;
  grid-template-columns: 85px 72px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 7px 16px;
  font-size: 13px;
  text-decoration: none;
  transition: background 0.2s ease;
  cursor: pointer;
}

.situation-news-item:hover {
  background: rgba(0, 212, 255, 0.06);
}

.situation-news-item[aria-hidden="true"] {
  /* 副本不额外加交互 */
}

.situation-news-item__time {
  font-family: var(--console-mono);
  font-size: 11px;
  color: var(--console-muted);
  white-space: nowrap;
}

.situation-news-item__source {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 10px;
  white-space: nowrap;
  border: 1px solid rgba(0, 212, 255, 0.14);
  color: var(--console-text-soft);
  background: rgba(0, 212, 255, 0.06);
}

.situation-news-item__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--console-text);
}

/* ── AI 解读面板 ── */
.situation-analysis-panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.situation-analysis-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.situation-analysis-section {
  padding: 12px 14px;
  border-radius: 8px;
  background: rgba(0, 212, 255, 0.03);
  border: 1px solid rgba(0, 212, 255, 0.06);
}

.situation-analysis-section h4 {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--console-cyan);
  letter-spacing: 0.04em;
}

.situation-analysis-section p {
  margin: 0;
  font-size: 12px;
  color: var(--console-text-soft);
  line-height: 1.7;
  white-space: pre-wrap;
}

.situation-analysis-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--console-muted);
  font-size: 14px;
}

.situation-analysis-empty .el-icon {
  font-size: 28px;
  color: var(--console-cyan);
}

/* ── 响应式 ── */
@media (max-width: 1199px) {
  .situation-kpi-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .situation-main-grid {
    grid-template-columns: 1fr;
    grid-template-rows: auto;
  }

  .situation-news-panel,
  .situation-analysis-panel {
    max-height: 400px;
  }

  .situation-chart {
    min-height: 240px;
  }
}

@media (max-width: 767px) {
  .situation-kpi-row {
    grid-template-columns: 1fr;
  }

  .situation-news-item {
    grid-template-columns: 100px 60px minmax(0, 1fr);
    font-size: 12px;
    gap: 6px;
  }
}
</style>
