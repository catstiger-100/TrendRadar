<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import ConsoleLayout from "../../layout/ConsoleLayout.vue";
import { fetchAiModels, testAiModel, updateAiModels } from "../../api/system";

const loading = ref(false);
const saving = ref(false);
const testingFast = ref(false);
const testingReasoning = ref(false);
const providerPresets = ref({});

const form = reactive({
  fast_provider: "",
  fast_model_name: "",
  fast_base_url: "",
  fast_api_key: "",
  reasoning_provider: "",
  reasoning_model_name: "",
  reasoning_base_url: "",
  reasoning_api_key: "",
});

const providerOptions = computed(() => Object.keys(providerPresets.value || {}));

function applyPreset(prefix) {
  const provider = form[`${prefix}_provider`];
  const preset = providerPresets.value?.[provider];
  if (!preset) return;

  form[`${prefix}_base_url`] = preset.base_url || "";
  if (prefix === "fast") {
    form.fast_model_name = preset.fast_model_name || "";
  } else {
    form.reasoning_model_name = preset.reasoning_model_name || "";
  }
}

function fillFromPreset(prefix) {
  applyPreset(prefix);
}

async function loadData() {
  loading.value = true;
  try {
    const data = await fetchAiModels();
    providerPresets.value = data.provider_presets || {};
    Object.assign(form, data.settings || {});
  } catch (error) {
    ElMessage.error(error.message || "AI 模型配置加载失败");
  } finally {
    loading.value = false;
  }
}

async function saveSettings() {
  saving.value = true;
  try {
    const data = await updateAiModels({ ...form });
    Object.assign(form, data.settings || {});
    ElMessage.success(data.message || "AI 模型配置已保存");
  } catch (error) {
    ElMessage.error(error.message || "AI 模型配置保存失败");
  } finally {
    saving.value = false;
  }
}

async function runTest(modelType) {
  const loadingRef = modelType === "fast" ? testingFast : testingReasoning;
  loadingRef.value = true;
  try {
    const data = await testAiModel({
      model_type: modelType,
      ...form,
    });
    ElMessage.success(`${data.message}${data.reply ? `：${data.reply}` : ""}`);
  } catch (error) {
    ElMessage.error(error.message || "模型测试失败");
  } finally {
    loadingRef.value = false;
  }
}

loadData();
</script>

<template>
  <ConsoleLayout>
    <section class="console-panel" v-loading="loading">
      <div class="console-panel__header">
        <div>
          <p class="console-panel__eyebrow">AI Model Management</p>
          <h3>AI模型管理</h3>
        </div>
        <el-button type="primary" :loading="saving" @click="saveSettings">保存配置</el-button>
      </div>

      <div class="ai-model-grid">
        <section class="ai-model-card">
          <div class="ai-model-card__header">
            <div>
              <h4>快速模型</h4>
              <p>适合摘要、翻译、轻量任务，系统默认优先用于 AI 翻译。</p>
            </div>
            <el-button class="ai-model-card__test-btn" :loading="testingFast" @click="runTest('fast')">测试快速模型</el-button>
          </div>

          <el-form label-position="top">
            <el-form-item label="供应商">
              <el-select v-model="form.fast_provider" placeholder="请选择供应商" @change="fillFromPreset('fast')">
                <el-option
                  v-for="item in providerOptions"
                  :key="item"
                  :label="item"
                  :value="item"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="form.fast_model_name" placeholder="例如：gpt-5.5-mini、gemini-2.5-flash、qwen-max" />
            </el-form-item>
            <el-form-item label="BASE URL">
              <el-input v-model="form.fast_base_url" placeholder="选择供应商后会自动填充，可手动修改" />
            </el-form-item>
            <el-form-item label="API_KEY">
              <el-input v-model="form.fast_api_key" type="password" show-password placeholder="请输入快速模型 API Key" />
            </el-form-item>
          </el-form>
        </section>

        <section class="ai-model-card">
          <div class="ai-model-card__header">
            <div>
              <h4>深度思考模型</h4>
              <p>适合复杂分析与研判，系统默认优先用于 AI 热点分析。</p>
            </div>
            <el-button class="ai-model-card__test-btn" :loading="testingReasoning" @click="runTest('reasoning')">测试深度模型</el-button>
          </div>

          <el-form label-position="top">
            <el-form-item label="供应商">
              <el-select v-model="form.reasoning_provider" placeholder="请选择供应商" @change="fillFromPreset('reasoning')">
                <el-option
                  v-for="item in providerOptions"
                  :key="item"
                  :label="item"
                  :value="item"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="form.reasoning_model_name" placeholder="例如：gpt-5.5、claude-opus-4-1、deepseek-reasoner" />
            </el-form-item>
            <el-form-item label="BASE URL">
              <el-input v-model="form.reasoning_base_url" placeholder="选择供应商后会自动填充，可手动修改" />
            </el-form-item>
            <el-form-item label="API_KEY">
              <el-input v-model="form.reasoning_api_key" type="password" show-password placeholder="请输入深度模型 API Key" />
            </el-form-item>
          </el-form>
        </section>
      </div>
    </section>
  </ConsoleLayout>
</template>

<style scoped>
.ai-model-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.ai-model-card {
  padding: 20px;
  border-radius: 18px;
  border: 1px solid var(--console-line);
  background: rgba(255, 255, 255, 0.02);
}

.ai-model-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.ai-model-card__header h4 {
  margin: 0 0 8px;
  font-size: 18px;
  color: var(--console-text);
}

.ai-model-card__header p {
  margin: 0;
  color: var(--console-muted);
  line-height: 1.6;
}

.ai-model-card__test-btn {
  flex-shrink: 0;
  --el-button-bg-color: transparent;
  --el-button-border-color: var(--console-line);
  --el-button-text-color: var(--console-muted);
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.06);
  --el-button-hover-border-color: var(--console-cyan);
  --el-button-hover-text-color: var(--console-cyan);
}

@media (max-width: 991px) {
  .ai-model-grid {
    grid-template-columns: 1fr;
  }

  .ai-model-card__header {
    flex-direction: column;
  }
}
</style>
