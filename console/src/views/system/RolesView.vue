<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { createRole, deleteRole, fetchRoles, updateRole } from "../../api/system";
import ConsoleLayout from "../../layout/ConsoleLayout.vue";

const loading = ref(false);
const dialogVisible = ref(false);
const editingId = ref(null);
const items = ref([]);

const form = reactive({
  name: "",
  description: "",
});

const dialogTitle = computed(() => (editingId.value ? "编辑角色" : "新增角色"));

function resetForm() {
  form.name = "";
  form.description = "";
  editingId.value = null;
}

async function loadRoles() {
  loading.value = true;
  try {
    const data = await fetchRoles();
    items.value = data.items || [];
  } catch (error) {
    ElMessage.error(error.message || "角色列表加载失败");
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
  form.name = row.name;
  form.description = row.description;
  dialogVisible.value = true;
}

async function submitRole() {
  try {
    if (editingId.value) {
      await updateRole(editingId.value, form);
      ElMessage.success("角色已更新");
    } else {
      await createRole(form);
      ElMessage.success("角色已创建");
    }
    dialogVisible.value = false;
    resetForm();
    await loadRoles();
  } catch (error) {
    ElMessage.error(error.message || "角色保存失败");
  }
}

async function removeRole(row) {
  try {
    await ElMessageBox.confirm(`确定删除角色“${row.name}”吗？`, "删除角色", {
      type: "warning",
    });
    await deleteRole(row.id);
    ElMessage.success("角色已删除");
    await loadRoles();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error.message || "角色删除失败");
    }
  }
}

loadRoles();
</script>

<template>
  <ConsoleLayout>
    <section class="console-panel">
      <div class="console-panel__header">
        <div>
          <p class="console-panel__eyebrow">Role Management</p>
          <h3>角色管理</h3>
        </div>
        <el-button type="primary" @click="openCreate">新增角色</el-button>
      </div>

      <el-table :data="items" v-loading="loading" class="console-table">
        <el-table-column prop="name" label="角色名称" min-width="220" />
        <el-table-column prop="description" label="说明" min-width="280" />
        <el-table-column prop="updated_at" label="更新时间" min-width="180" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="removeRole(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-dialog v-model="dialogVisible" :title="dialogTitle" width="480px">
        <el-form label-position="top">
          <el-form-item label="角色名称">
            <el-input v-model="form.name" maxlength="64" />
          </el-form-item>
          <el-form-item label="说明">
            <el-input v-model="form.description" type="textarea" :rows="4" maxlength="200" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitRole">保存</el-button>
        </template>
      </el-dialog>
    </section>
  </ConsoleLayout>
</template>
