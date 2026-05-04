<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import ConsoleLayout from "../../layout/ConsoleLayout.vue";
import {
  createFuturesSymbol,
  deleteFuturesSymbol,
  fetchFuturesSymbols,
  updateFuturesSymbol,
} from "../../api/system";

const FUTURES_FILTER_STORAGE_KEY = "trendradar:futures-symbol-form";

const BOARD_OPTIONS = [
  "金融",
  "贵金属",
  "农产品",
  "化工",
  "有色",
  "煤炭",
  "黑色",
  "建材",
  "其他",
];

const EXCHANGE_OPTIONS = [
  "中国金融期货交易所",
  "上海期货交易所",
  "上海国际能源交易中心",
  "郑州商品交易所",
  "大连商品交易所",
  "广州期货交易所",
];

const FUTURES_PRESETS = {
  金融: [
    { name: "沪深300股指期货", code: "IF", exchange: "中国金融期货交易所" },
    { name: "上证50股指期货", code: "IH", exchange: "中国金融期货交易所" },
    { name: "中证500股指期货", code: "IC", exchange: "中国金融期货交易所" },
    { name: "中证1000股指期货", code: "IM", exchange: "中国金融期货交易所" },
    { name: "2年期国债期货", code: "TS", exchange: "中国金融期货交易所" },
    { name: "5年期国债期货", code: "TF", exchange: "中国金融期货交易所" },
    { name: "10年期国债期货", code: "T", exchange: "中国金融期货交易所" },
    { name: "30年期国债期货", code: "TL", exchange: "中国金融期货交易所" },
  ],
  贵金属: [
    { name: "黄金", code: "AU", exchange: "上海期货交易所" },
    { name: "白银", code: "AG", exchange: "上海期货交易所" },
  ],
  农产品: [
    { name: "豆一", code: "A", exchange: "大连商品交易所" },
    { name: "豆二", code: "B", exchange: "大连商品交易所" },
    { name: "玉米", code: "C", exchange: "大连商品交易所" },
    { name: "玉米淀粉", code: "CS", exchange: "大连商品交易所" },
    { name: "豆粕", code: "M", exchange: "大连商品交易所" },
    { name: "豆油", code: "Y", exchange: "大连商品交易所" },
    { name: "棕榈油", code: "P", exchange: "大连商品交易所" },
    { name: "鸡蛋", code: "JD", exchange: "大连商品交易所" },
    { name: "生猪", code: "LH", exchange: "大连商品交易所" },
    { name: "花生", code: "PK", exchange: "郑州商品交易所" },
    { name: "苹果", code: "AP", exchange: "郑州商品交易所" },
    { name: "红枣", code: "CJ", exchange: "郑州商品交易所" },
    { name: "棉花", code: "CF", exchange: "郑州商品交易所" },
    { name: "白糖", code: "SR", exchange: "郑州商品交易所" },
    { name: "菜籽油", code: "OI", exchange: "郑州商品交易所" },
    { name: "菜籽粕", code: "RM", exchange: "郑州商品交易所" },
    { name: "菜籽", code: "RS", exchange: "郑州商品交易所" },
    { name: "强麦", code: "WH", exchange: "郑州商品交易所" },
    { name: "普麦", code: "PM", exchange: "郑州商品交易所" },
  ],
  化工: [
    { name: "原油", code: "SC", exchange: "上海国际能源交易中心" },
    { name: "低硫燃料油", code: "LU", exchange: "上海国际能源交易中心" },
    { name: "燃料油", code: "FU", exchange: "上海期货交易所" },
    { name: "沥青", code: "BU", exchange: "上海期货交易所" },
    { name: "天然橡胶", code: "RU", exchange: "上海期货交易所" },
    { name: "丁二烯橡胶", code: "BR", exchange: "上海期货交易所" },
    { name: "对二甲苯", code: "PX", exchange: "郑州商品交易所" },
    { name: "精对苯二甲酸", code: "TA", exchange: "郑州商品交易所" },
    { name: "短纤", code: "PF", exchange: "郑州商品交易所" },
    { name: "瓶片", code: "PR", exchange: "郑州商品交易所" },
    { name: "甲醇", code: "MA", exchange: "郑州商品交易所" },
    { name: "尿素", code: "UR", exchange: "郑州商品交易所" },
    { name: "烧碱", code: "SH", exchange: "郑州商品交易所" },
    { name: "线型低密度聚乙烯", code: "L", exchange: "大连商品交易所" },
    { name: "聚氯乙烯", code: "V", exchange: "大连商品交易所" },
    { name: "聚丙烯", code: "PP", exchange: "大连商品交易所" },
    { name: "乙二醇", code: "EG", exchange: "大连商品交易所" },
    { name: "苯乙烯", code: "EB", exchange: "大连商品交易所" },
  ],
  有色: [
    { name: "铜", code: "CU", exchange: "上海期货交易所" },
    { name: "铝", code: "AL", exchange: "上海期货交易所" },
    { name: "锌", code: "ZN", exchange: "上海期货交易所" },
    { name: "铅", code: "PB", exchange: "上海期货交易所" },
    { name: "镍", code: "NI", exchange: "上海期货交易所" },
    { name: "锡", code: "SN", exchange: "上海期货交易所" },
    { name: "氧化铝", code: "AO", exchange: "上海期货交易所" },
    { name: "工业硅", code: "SI", exchange: "广州期货交易所" },
    { name: "碳酸锂", code: "LC", exchange: "广州期货交易所" },
  ],
  煤炭: [
    { name: "焦煤", code: "JM", exchange: "大连商品交易所" },
    { name: "焦炭", code: "J", exchange: "大连商品交易所" },
  ],
  黑色: [
    { name: "螺纹钢", code: "RB", exchange: "上海期货交易所" },
    { name: "热轧卷板", code: "HC", exchange: "上海期货交易所" },
    { name: "不锈钢", code: "SS", exchange: "上海期货交易所" },
    { name: "线材", code: "WR", exchange: "上海期货交易所" },
    { name: "铁矿石", code: "I", exchange: "大连商品交易所" },
  ],
  建材: [
    { name: "玻璃", code: "FG", exchange: "郑州商品交易所" },
    { name: "纯碱", code: "SA", exchange: "郑州商品交易所" },
    { name: "硅铁", code: "SF", exchange: "郑州商品交易所" },
    { name: "锰硅", code: "SM", exchange: "郑州商品交易所" },
  ],
  其他: [
    { name: "集运指数（欧线）", code: "EC", exchange: "上海国际能源交易中心" },
    { name: "工业碳排放配额", code: "CEA", exchange: "广州期货交易所" },
  ],
};

const loading = ref(false);
const dialogVisible = ref(false);
const editingId = ref(null);
const items = ref([]);

const form = reactive({
  sector: "",
  exchange: "",
  name: "",
  code: "",
});

const dialogTitle = computed(() => (editingId.value ? "编辑期货品种" : "新增期货品种"));
const currentProductOptions = computed(() => FUTURES_PRESETS[form.sector] || []);

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

function saveFormPreference() {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    FUTURES_FILTER_STORAGE_KEY,
    JSON.stringify({
      sector: form.sector || "",
      exchange: form.exchange || "",
    })
  );
}

function loadFormPreference() {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(FUTURES_FILTER_STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    form.sector = saved?.sector || "";
    form.exchange = saved?.exchange || "";
  } catch {
    // 本地缓存损坏时忽略即可
  }
}

function resetForm() {
  loadFormPreference();
  form.name = "";
  form.code = "";
  editingId.value = null;
}

watch(
  () => form.sector,
  (next, prev) => {
    if (!next) {
      form.name = "";
      form.code = "";
      form.exchange = "";
      return;
    }
    if (next !== prev) {
      form.name = "";
      form.code = "";
      form.exchange = "";
    }
  }
);

watch(
  () => form.name,
  (next) => {
    const matched = currentProductOptions.value.find((item) => item.name === next);
    if (!matched) return;
    form.code = matched.code;
    form.exchange = matched.exchange;
  }
);

watch(
  () => [form.sector, form.exchange],
  () => {
    if (editingId.value) return;
    saveFormPreference();
  }
);

async function loadData() {
  loading.value = true;
  try {
    const data = await fetchFuturesSymbols();
    items.value = data.items || [];
  } catch (error) {
    ElMessage.error(error.message || "期货品种列表加载失败");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  dialogVisible.value = true;
}

function openEdit(row) {
  editingId.value = row.id;
  form.sector = row.sector || "";
  form.exchange = row.exchange || "";
  form.name = row.name || "";
  form.code = row.code || "";
  dialogVisible.value = true;
}

async function submitForm() {
  try {
    if (editingId.value) {
      await updateFuturesSymbol(editingId.value, form);
      ElMessage.success("期货品种已更新");
    } else {
      await createFuturesSymbol(form);
      ElMessage.success("期货品种已创建");
    }
    dialogVisible.value = false;
    resetForm();
    await loadData();
  } catch (error) {
    ElMessage.error(error.message || "期货品种保存失败");
  }
}

async function removeItem(row) {
  try {
    await ElMessageBox.confirm(`确定删除期货品种“${row.name}（${row.code}）”吗？`, "删除期货品种", {
      type: "warning",
    });
    await deleteFuturesSymbol(row.id);
    ElMessage.success("期货品种已删除");
    await loadData();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error.message || "期货品种删除失败");
    }
  }
}

loadData();
loadFormPreference();
</script>

<template>
  <ConsoleLayout>
    <section class="console-panel">
      <div class="console-panel__header">
        <div>
          <p class="console-panel__eyebrow">Futures Symbols</p>
          <h3>期货品种</h3>
        </div>
        <el-button type="primary" @click="openCreate">新增期货品种</el-button>
      </div>

      <el-table :data="items" v-loading="loading" class="console-table">
        <el-table-column prop="sector" label="板块" min-width="120" />
        <el-table-column prop="exchange" label="交易所" min-width="220" />
        <el-table-column prop="name" label="品种名称" min-width="220" />
        <el-table-column prop="code" label="品种代码" min-width="120" />
        <el-table-column label="更新时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="removeItem(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px">
        <el-form label-position="top">
          <el-form-item label="板块">
            <el-select v-model="form.sector" placeholder="请选择板块" style="width: 100%">
              <el-option
                v-for="item in BOARD_OPTIONS"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="交易所">
            <el-select v-model="form.exchange" placeholder="请选择交易所" style="width: 100%">
              <el-option
                v-for="item in EXCHANGE_OPTIONS"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="品种名称">
            <el-select
              v-model="form.name"
              placeholder="请先选择板块，再选择品种"
              filterable
              allow-create
              default-first-option
              style="width: 100%"
            >
              <el-option
                v-for="item in currentProductOptions"
                :key="item.name"
                :label="item.name"
                :value="item.name"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="品种代码">
            <el-input v-model="form.code" maxlength="32" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitForm">保存</el-button>
        </template>
      </el-dialog>
    </section>
  </ConsoleLayout>
</template>
