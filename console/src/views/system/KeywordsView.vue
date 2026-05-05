<script setup>
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Upload } from "@element-plus/icons-vue";
import ConsoleLayout from "../../layout/ConsoleLayout.vue";
import { fetchKeywords, saveKeywords, uploadKeywords, fetchBackups, downloadTemplate } from "../../api/keywords";

const loading = ref(false);
const saving = ref(false);
const uploading = ref(false);
const modules = ref([]);
const updatedAt = ref("");
const rawContent = ref("");
const showEditor = ref(false);
const backups = ref([]);
const showBackups = ref(false);

async function loadData() {
  loading.value = true;
  try {
    const data = await fetchKeywords();
    modules.value = data.modules || [];
    updatedAt.value = data.updated_at || "";
  } catch (e) {
    ElMessage.error(e.message || "加载关键词失败");
  } finally {
    loading.value = false;
  }
}

async function loadBackups() {
  try {
    const data = await fetchBackups();
    backups.value = data.backups || [];
    showBackups.value = true;
  } catch (e) {
    ElMessage.error(e.message || "加载备份列表失败");
  }
}

async function handleSave() {
  if (!rawContent.value.trim()) {
    ElMessage.warning("关键词内容不能为空");
    return;
  }
  saving.value = true;
  try {
    const data = await saveKeywords(rawContent.value);
    modules.value = data.modules || [];
    updatedAt.value = data.updated_at || "";
    showEditor.value = false;
    ElMessage.success(data.message || "关键词已保存");
  } catch (e) {
    ElMessage.error(e.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

function openEditor() {
  if (!rawContent.value) {
    // 构建 raw content from modules 用于编辑
    rawContent.value = buildFrequencyText();
  }
  showEditor.value = true;
}

function buildFrequencyText() {
  const lines = [];
  lines.push("# ═══════════════════════════════════════════════════════════════");
  lines.push("#              TrendRadar 关键词 / 频率配置");
  lines.push("# ═══════════════════════════════════════════════════════════════");
  lines.push("");
  lines.push("[GLOBAL_FILTER]");
  lines.push("# 全局过滤词（标题中包含任一词汇的新闻将被排除）");
  lines.push("");
  lines.push("[WORD_GROUPS]");
  lines.push("# 关键词分组定义");
  lines.push("");

  for (const mod of modules.value) {
    lines.push(`# ═══ ${mod.name} ═══`);
    for (const cat of mod.categories || []) {
      lines.push(`[${cat.name}]`);
      for (const group of cat.groups || []) {
        const kw = (group.keywords || []).join("|");
        lines.push(`${kw} => ${group.title}`);
      }
      lines.push("");
    }
  }
  return lines.join("\n");
}

async function handleUpload(file) {
  if (!file) return;
  uploading.value = true;
  try {
    const data = await uploadKeywords(file);
    modules.value = data.modules || [];
    updatedAt.value = data.updated_at || "";
    rawContent.value = "";
    showEditor.value = false;
    ElMessage.success(data.message || "上传成功");
  } catch (e) {
    ElMessage.error(e.message || "上传失败");
  } finally {
    uploading.value = false;
  }
  return false;
}

onMounted(() => {
  loadData();
});
</script>

<template>
  <ConsoleLayout>
    <section class="console-panel" v-loading="loading">
      <div class="console-panel__header">
        <div>
          <p class="console-panel__eyebrow">Keyword Management</p>
          <h3>关键词管理</h3>
        </div>
        <div class="keyword-header-right">
          <div class="keyword-actions">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".md,.markdown,.xlsx"
              :on-change="(f) => handleUpload(f.raw)"
              :disabled="uploading"
            >
              <el-button class="keyword-btn" :loading="uploading" :icon="Upload">
                上传文件
              </el-button>
            </el-upload>
            <el-button class="keyword-btn" @click="openEditor">文本编辑</el-button>
            <el-button class="keyword-btn" @click="loadBackups">备份管理</el-button>
          </div>
          <p class="keyword-upload-hint">
            支持 .md / .xlsx 格式，上传将覆盖当前配置 ·
            <a :href="downloadTemplate('md')" class="keyword-template-link">下载 Markdown 样板</a> ·
            <a :href="downloadTemplate('xlsx')" class="keyword-template-link">下载 XLSX 样板</a>
          </p>
        </div>
      </div>

      <div v-if="updatedAt" class="keyword-meta">
        最后更新：{{ updatedAt }}
      </div>

      <!-- 编辑器 -->
      <div v-if="showEditor" class="keyword-editor">
        <el-input
          v-model="rawContent"
          type="textarea"
          :rows="20"
          placeholder="编辑 frequency_words.txt 格式内容..."
        />
        <div class="keyword-editor__actions">
          <el-button @click="showEditor = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
        </div>
      </div>

      <!-- 关键词结构展示 -->
      <div v-if="!showEditor" class="keyword-modules">
        <div v-if="modules.length === 0 && !loading" class="keyword-empty">
          暂无关键词配置，请上传或编辑添加
        </div>
        <div
          v-for="mod in modules"
          :key="mod.name"
          class="keyword-module"
        >
          <div class="keyword-module__header">
            <h4>{{ mod.name }}</h4>
            <span class="console-chip">{{ (mod.categories || []).length }} 个分类</span>
          </div>
          <div
            v-for="cat in mod.categories || []"
            :key="cat.name"
            class="keyword-category"
          >
            <h5>{{ cat.name }}</h5>
            <div class="keyword-group-list">
              <div
                v-for="group in cat.groups || []"
                :key="group.title"
                class="keyword-group"
              >
                <span class="keyword-group__title">{{ group.title }}</span>
                <span class="keyword-group__sep">→</span>
                <span class="keyword-group__words">{{ (group.keywords || []).join("、") }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 备份列表弹窗 -->
    <el-dialog v-model="showBackups" title="备份管理" width="520px">
      <div v-if="backups.length === 0" class="keyword-backups-empty">
        暂无备份文件
      </div>
      <div v-else class="keyword-backup-list">
        <div
          v-for="bk in backups"
          :key="bk.name"
          class="keyword-backup-item"
        >
          <span class="keyword-backup-item__name">{{ bk.name }}</span>
          <span class="keyword-backup-item__size">{{ (bk.size / 1024).toFixed(1) }} KB</span>
          <span class="keyword-backup-item__time">{{ bk.created_at }}</span>
        </div>
      </div>
    </el-dialog>
  </ConsoleLayout>
</template>

<style scoped>
.keyword-header-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.keyword-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.keyword-upload-hint {
  margin: 0;
  font-size: 11px;
  color: var(--console-muted);
  line-height: 1.5;
  text-align: right;
}

.keyword-template-link {
  color: var(--console-cyan);
  text-decoration: none;
  transition: color 0.2s ease;
}

.keyword-template-link:hover {
  color: var(--console-blue);
  text-decoration: underline;
}

.keyword-btn {
  --el-button-bg-color: var(--console-control-bg);
  --el-button-border-color: var(--console-control-border);
  --el-button-text-color: var(--console-text-soft);
  --el-button-hover-bg-color: rgba(0, 212, 255, 0.14);
  --el-button-hover-border-color: rgba(0, 212, 255, 0.32);
  --el-button-hover-text-color: #e7faff;
}

:global(.theme--light .keyword-btn) {
  --el-button-bg-color: #ffffff;
  --el-button-border-color: #dcdfe6;
  --el-button-text-color: #606266;
  --el-button-hover-bg-color: #ecf5ff;
  --el-button-hover-border-color: #b3d8ff;
  --el-button-hover-text-color: #409eff;
}

.keyword-meta {
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--console-muted);
}

.keyword-editor {
  margin-bottom: 20px;
}

.keyword-editor__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.keyword-empty {
  padding: 40px 0;
  text-align: center;
  color: var(--console-muted);
  font-size: 14px;
}

.keyword-modules {
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
  max-height: calc(100vh - 260px);
  min-height: 200px;
  padding-right: 4px;
}

.keyword-module {
  padding: 16px 18px;
  border-radius: 12px;
  border: 1px solid rgba(0, 212, 255, 0.08);
  background: rgba(0, 212, 255, 0.02);
}

.keyword-module__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(0, 212, 255, 0.1);
}

.keyword-module__header h4 {
  margin: 0;
  font-size: 16px;
  color: var(--console-cyan);
}

.keyword-category {
  margin-bottom: 12px;
  padding-left: 8px;
}

.keyword-category h5 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--console-text);
}

.keyword-group-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.keyword-group {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.7;
  transition: background 0.2s ease;
}

.keyword-group:hover {
  background: rgba(0, 212, 255, 0.04);
}

.keyword-group__title {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--console-gold);
  min-width: 80px;
}

.keyword-group__sep {
  flex-shrink: 0;
  color: var(--console-muted);
}

.keyword-group__words {
  color: var(--console-text-soft);
  word-break: break-all;
}

.keyword-backups-empty {
  padding: 30px 0;
  text-align: center;
  color: var(--console-muted);
}

.keyword-backup-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.keyword-backup-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(0, 212, 255, 0.03);
  border: 1px solid rgba(0, 212, 255, 0.06);
  font-size: 13px;
}

.keyword-backup-item__name {
  flex: 1;
  font-family: var(--console-mono);
  font-size: 12px;
  color: var(--console-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.keyword-backup-item__size {
  flex-shrink: 0;
  color: var(--console-muted);
  font-size: 12px;
}

.keyword-backup-item__time {
  flex-shrink: 0;
  color: var(--console-muted);
  font-size: 12px;
}
</style>
