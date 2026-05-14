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
const opinionPageSize = ref(200);
const opinionMaxLoadCount = ref(2000);
const savingOpinion = ref(false);

const emailFrom = ref("");
const emailPassword = ref("");
const emailTo = ref("");
const emailSmtpServer = ref("");
const emailSmtpPort = ref("");
const emailSchedule = ref("");
const emailScheduleOptions = ref([]);
const savingEmail = ref(false);

const feishuWebhookUrl = ref("");
const dingtalkWebhookUrl = ref("");
const weworkWebhookUrl = ref("");
const notificationSchedule = ref("");
const notificationScheduleOptions = ref([]);
const savingNotif = ref(false);

async function loadConfig() {
  loading.value = true;
  try {
    const data = await fetchSystemConfig();
    crawlInterval.value = data.crawl_interval_minutes || 0;
    cronSchedule.value = data.cron_schedule || "";
    availableIntervals.value = data.available_intervals || [1, 3, 5, 10, 15, 30];
    opinionPageSize.value = data.opinion_page_size || 200;
    opinionMaxLoadCount.value = data.opinion_max_load_count || 2000;
    emailFrom.value = data.email_from || "";
    emailPassword.value = data.email_password || "";
    emailTo.value = data.email_to || "";
    emailSmtpServer.value = data.email_smtp_server || "";
    emailSmtpPort.value = data.email_smtp_port || "";
    emailSchedule.value = data.email_schedule || "";
    emailScheduleOptions.value = data.email_schedule_options || [];
    feishuWebhookUrl.value = data.feishu_webhook_url || "";
    dingtalkWebhookUrl.value = data.dingtalk_webhook_url || "";
    weworkWebhookUrl.value = data.wework_webhook_url || "";
    notificationSchedule.value = data.notification_schedule || "";
    notificationScheduleOptions.value = data.notification_schedule_options || [];
  } catch (e) {
    ElMessage.error(e.message || "加载系统配置失败");
  } finally {
    loading.value = false;
  }
}

async function saveConfig() {
  saving.value = true;
  try {
    const data = await updateSystemConfig({ crawl_interval_minutes: crawlInterval.value });
    ElMessage.success(data.message || "配置已保存");
  } catch (e) {
    ElMessage.error(e.message || "保存配置失败");
  } finally {
    saving.value = false;
  }
}

async function saveOpinionConfig() {
  savingOpinion.value = true;
  try {
    const data = await updateSystemConfig({
      opinion_page_size: Number(opinionPageSize.value),
      opinion_max_load_count: Number(opinionMaxLoadCount.value),
    });
    if (data.opinion_page_size) opinionPageSize.value = data.opinion_page_size;
    if (data.opinion_max_load_count) opinionMaxLoadCount.value = data.opinion_max_load_count;
    ElMessage.success(data.message || "配置已保存");
  } catch (e) {
    ElMessage.error(e.message || "保存配置失败");
  } finally {
    savingOpinion.value = false;
  }
}

async function saveEmailConfig() {
  savingEmail.value = true;
  try {
    const data = await updateSystemConfig({
      email_from: emailFrom.value,
      email_password: emailPassword.value,
      email_to: emailTo.value,
      email_smtp_server: emailSmtpServer.value,
      email_smtp_port: emailSmtpPort.value,
      email_schedule: emailSchedule.value,
    });
    ElMessage.success(data.message || "邮件配置已保存");
  } catch (e) {
    ElMessage.error(e.message || "保存邮件配置失败");
  } finally {
    savingEmail.value = false;
  }
}

async function saveNotifConfig() {
  savingNotif.value = true;
  try {
    const data = await updateSystemConfig({
      feishu_webhook_url: feishuWebhookUrl.value,
      dingtalk_webhook_url: dingtalkWebhookUrl.value,
      wework_webhook_url: weworkWebhookUrl.value,
      notification_schedule: notificationSchedule.value,
    });
    ElMessage.success(data.message || "推送渠道配置已保存");
  } catch (e) {
    ElMessage.error(e.message || "保存推送渠道配置失败");
  } finally {
    savingNotif.value = false;
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
      <!-- 左列 -->
      <div class="syscfg-col">
        <!-- 抓取频率 -->
        <div class="syscfg-card">
          <h3 class="syscfg-card__title">抓取频率</h3>
          <p class="syscfg-card__desc">控制新闻数据抓取的时间间隔。修改后立即生效，无需重启服务。</p>
          <div class="syscfg-field" v-loading="loading">
            <div class="syscfg-field__row">
              <el-select v-model="crawlInterval" class="syscfg-select" :disabled="saving">
                <el-option v-for="n in availableIntervals" :key="n" :label="intervalLabel(n)" :value="n" />
                <el-option label="跟随外部 Cron" :value="0" />
              </el-select>
              <el-button type="primary" :loading="saving" @click="saveConfig">保存</el-button>
            </div>
            <p class="syscfg-hint" v-if="cronSchedule">
              当前外部 Cron 表达式：<code>{{ cronSchedule }}</code>
            </p>
          </div>
        </div>

        <!-- 资讯列表加载 -->
        <div class="syscfg-card">
          <h3 class="syscfg-card__title">资讯列表加载</h3>
          <p class="syscfg-card__desc">控制前端列表/卡片视图的分页加载。下拉到底时自动加载下一批，达到累计上限后停止。</p>
          <div class="syscfg-field" v-loading="loading">
            <div class="syscfg-field__row">
              <label class="syscfg-label">每次加载</label>
              <el-input-number v-model="opinionPageSize" :min="10" :max="500" :step="50" class="syscfg-input-number" />
              <label class="syscfg-label">最多加载</label>
              <el-input-number v-model="opinionMaxLoadCount" :min="10" :max="10000" :step="500" class="syscfg-input-number" />
              <el-button type="primary" :loading="savingOpinion" @click="saveOpinionConfig">保存</el-button>
            </div>
            <p class="syscfg-hint">保存时若"最多加载"不是"每次加载"的整数倍，会自动向上对齐。</p>
          </div>
        </div>

        <!-- 邮件通知 -->
        <div class="syscfg-card">
          <h3 class="syscfg-card__title">邮件通知</h3>
          <p class="syscfg-card__desc">系统将在指定时间自动发送当前热榜报告（index.html）。</p>
          <div class="syscfg-field" v-loading="loading">
            <div class="syscfg-email-inline">
              <div class="syscfg-email-inline-item">
                <label class="syscfg-email-label">发件邮箱</label>
                <el-input v-model="emailFrom" placeholder="your@example.com" />
              </div>
              <div class="syscfg-email-inline-item">
                <label class="syscfg-email-label">密码 / 授权码</label>
                <el-input v-model="emailPassword" type="password" show-password placeholder="密码或授权码" />
              </div>
              <div class="syscfg-email-inline-item">
                <label class="syscfg-email-label">SMTP 服务器 <span class="syscfg-optional">（可选）</span></label>
                <el-input v-model="emailSmtpServer" placeholder="smtp.example.com" />
              </div>
              <div class="syscfg-email-inline-item syscfg-email-inline-item--narrow">
                <label class="syscfg-email-label">端口 <span class="syscfg-optional">（可选）</span></label>
                <el-input v-model="emailSmtpPort" placeholder="465" />
              </div>
            </div>
            <div class="syscfg-email-row">
              <label class="syscfg-email-label">收件人邮箱</label>
              <el-input v-model="emailTo" placeholder="多个收件人用英文逗号分隔，如 a@x.com,b@y.com" />
            </div>
            <div class="syscfg-email-row">
              <label class="syscfg-email-label">发送时间</label>
              <el-select v-model="emailSchedule" class="syscfg-email-select">
                <el-option v-for="opt in emailScheduleOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
            <div class="syscfg-email-actions">
              <el-button type="primary" :loading="savingEmail" @click="saveEmailConfig">保存邮件配置</el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右列 -->
      <div class="syscfg-col">
        <div class="syscfg-card">
          <h3 class="syscfg-card__title">推送渠道</h3>
          <p class="syscfg-card__desc">配置飞书、钉钉、企业微信机器人 Webhook，三个渠道共用同一发送时间。留空的渠道不会推送。</p>
          <div class="syscfg-field" v-loading="loading">
            <div class="syscfg-email-row">
              <label class="syscfg-email-label">飞书 Webhook URL</label>
              <el-input v-model="feishuWebhookUrl" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
            </div>
            <div class="syscfg-email-row">
              <label class="syscfg-email-label">钉钉 Webhook URL</label>
              <el-input v-model="dingtalkWebhookUrl" placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
            </div>
            <div class="syscfg-email-row">
              <label class="syscfg-email-label">企业微信 Webhook URL</label>
              <el-input v-model="weworkWebhookUrl" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." />
            </div>
            <div class="syscfg-email-row">
              <label class="syscfg-email-label">发送时间（三个渠道共用）</label>
              <el-select v-model="notificationSchedule" class="syscfg-email-select">
                <el-option v-for="opt in notificationScheduleOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
            <div class="syscfg-email-actions">
              <el-button type="primary" :loading="savingNotif" @click="saveNotifConfig">保存推送渠道配置</el-button>
            </div>
          </div>
        </div>
      </div>
    </section>
  </ConsoleLayout>
</template>

<style scoped>
.syscfg-page {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}

@media (max-width: 900px) {
  .syscfg-page {
    grid-template-columns: 1fr;
  }
}

.syscfg-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
  flex-wrap: wrap;
}

.syscfg-label {
  font-size: 13px;
  color: var(--console-muted);
}

.syscfg-select {
  width: 200px;
}

.syscfg-input-number {
  width: 140px;
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

.syscfg-email-inline {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.syscfg-email-inline-item {
  flex: 1 1 120px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.syscfg-email-inline-item--narrow {
  flex: 0 0 80px;
}

.syscfg-email-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 16px;
}

.syscfg-email-label {
  font-size: 13px;
  color: var(--console-muted);
}

.syscfg-optional {
  font-size: 12px;
  opacity: 0.7;
}

.syscfg-email-select {
  width: 100%;
}

.syscfg-email-actions {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
