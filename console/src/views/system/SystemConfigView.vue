<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import ConsoleLayout from "../../layout/ConsoleLayout.vue";
import { fetchSystemConfig, updateSystemConfig } from "../../api/system";

const loading = ref(false);
const saving = ref(false);
const crawlInterval = ref(0);
const cronSchedule = ref("");
const availableIntervals = ref([1, 3, 5, 10, 15, 30]);

async function loadConfig() {
  loading.value = true;
  try {
    const data = await fetchSystemConfig();
    crawlInterval.value = data.crawl_interval_minutes || 0;
    cronSchedule.value = data.cron_schedule || "";
    availableIntervals.value = data.available_intervals || [1, 3, 5, 10, 15, 30];
  } catch (e) {
    ElMessage.error(e.message || "加载系统配置失败");
  } finally {
    loading.value = false;
  }
}

async function saveConfig() {
  saving.value = true;
  try {
    const data = await updateSystemConfig({
      crawl_interval_minutes: crawlInterval.value,
    });
    ElMessage.success(data.message || "配置已保存");
  } catch (e) {
    ElMessage.error(e.message || "保存配置失败");
  } finally {
    saving.value = false;
  }
}

function intervalLabel(minutes) {
  if (minutes === 0) return "跟随外部 Cron";
  return `每 ${minutes} 分钟`;
}

onMounted(() => {
  loadConfig();
});
</script>

<template>
  <ConsoleLayout>
    <section class="syscfg-page">
      <div class="syscfg-card">
        <h3 class="syscfg-card__title">抓取频率</h3>
        <p class="syscfg-card__desc">
          控制新闻数据抓取的时间间隔。修改后立即生效，无需重启服务。
        </p>
        <div class="syscfg-field" v-loading="loading">
          <div class="syscfg-field__row">
            <el-select
              v-model="crawlInterval"
              class="syscfg-select"
              :disabled="saving"
            >
              <el-option
                v-for="n in availableIntervals"
                :key="n"
                :label="intervalLabel(n)"
                :value="n"
              />
              <el-option label="跟随外部 Cron" :value="0" />
            </el-select>
            <el-button
              type="primary"
              :loading="saving"
              @click="saveConfig"
            >
              保存
            </el-button>
          </div>
          <p class="syscfg-hint" v-if="cronSchedule">
            当前外部 Cron 表达式：<code>{{ cronSchedule }}</code>
          </p>
        </div>
      </div>
    </section>
  </ConsoleLayout>
</template>

<style scoped>
.syscfg-page {
  max-width: 640px;
}

.syscfg-card {
  padding: 24px;
  border-radius: 12px;
  border: 1px solid var(--console-line);
  background:
    linear-gradient(180deg, rgba(0, 212, 255, 0.02), transparent 24%),
    var(--console-panel);
  backdrop-filter: blur(12px);
}

:global(.theme--light .syscfg-card) {
  background: #ffffff;
  backdrop-filter: none;
}

.syscfg-card__title {
  margin: 0 0 8px;
  font-size: 18px;
  color: var(--console-heading);
}

.syscfg-card__desc {
  margin: 0 0 20px;
  font-size: 13px;
  color: var(--console-muted);
  line-height: 1.6;
}

.syscfg-field__row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.syscfg-select {
  width: 200px;
}

.syscfg-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--console-muted);
}

.syscfg-hint code {
  font-family: var(--console-mono);
  color: var(--console-cyan);
  background: rgba(0, 212, 255, 0.08);
  padding: 2px 8px;
  border-radius: 4px;
}
</style>
