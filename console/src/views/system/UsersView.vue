<script setup>
import { reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { createUser, deleteUser, fetchRoles, fetchUsers, updateUser } from "../../api/system";
import ConsoleLayout from "../../layout/ConsoleLayout.vue";

const loading = ref(false);
const dialogVisible = ref(false);
const editingId = ref(null);
const items = ref([]);
const roleOptions = ref([]);

const form = reactive({
  username: "",
  password: "",
  full_name: "",
  role_ids: [],
  is_active: true,
});

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

function resetForm() {
  form.username = "";
  form.password = "";
  form.full_name = "";
  form.role_ids = [];
  form.is_active = true;
  editingId.value = null;
}

async function loadData() {
  loading.value = true;
  try {
    const [usersData, rolesData] = await Promise.all([fetchUsers(), fetchRoles()]);
    items.value = usersData.items || [];
    roleOptions.value = rolesData.items || [];
  } catch (error) {
    ElMessage.error(error.message || "用户数据加载失败");
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
  form.username = row.username;
  form.password = "";
  form.full_name = row.full_name;
  form.role_ids = [...(row.role_ids || [])];
  form.is_active = row.is_active;
  dialogVisible.value = true;
}

async function submitUser() {
  try {
    if (editingId.value) {
      await updateUser(editingId.value, form);
      ElMessage.success("用户已更新");
    } else {
      await createUser(form);
      ElMessage.success("用户已创建");
    }
    dialogVisible.value = false;
    resetForm();
    await loadData();
  } catch (error) {
    ElMessage.error(error.message || "用户保存失败");
  }
}

async function removeUser(row) {
  try {
    await ElMessageBox.confirm(`确定删除用户“${row.username}”吗？`, "删除用户", {
      type: "warning",
    });
    await deleteUser(row.id);
    ElMessage.success("用户已删除");
    await loadData();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error.message || "用户删除失败");
    }
  }
}

loadData();
</script>

<template>
  <ConsoleLayout>
    <section class="console-panel">
      <div class="console-panel__header">
        <div>
          <p class="console-panel__eyebrow">User Management</p>
          <h3>用户管理</h3>
        </div>
        <el-button type="primary" @click="openCreate">新增用户</el-button>
      </div>

      <el-table :data="items" v-loading="loading" class="console-table">
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="full_name" label="姓名" min-width="140" />
        <el-table-column label="角色" min-width="220">
          <template #default="{ row }">
            <div class="role-tag-list">
              <el-tag v-for="role in row.roles" :key="role.id" effect="plain">{{ role.name }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="登录时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.last_login_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="last_login_ip" label="登录 IP" min-width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? "启用" : "禁用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="removeUser(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-dialog v-model="dialogVisible" :title="editingId ? '编辑用户' : '新增用户'" width="560px">
        <el-form label-position="top">
          <el-form-item label="用户名">
            <el-input v-model="form.username" maxlength="64" />
          </el-form-item>
          <el-form-item label="姓名">
            <el-input v-model="form.full_name" maxlength="64" />
          </el-form-item>
          <el-form-item :label="editingId ? '密码（留空则不修改）' : '密码'">
            <el-input v-model="form.password" type="password" show-password />
          </el-form-item>
          <el-form-item label="角色">
            <el-select v-model="form.role_ids" multiple collapse-tags collapse-tags-tooltip style="width: 100%">
              <el-option
                v-for="role in roleOptions"
                :key="role.id"
                :label="role.name"
                :value="role.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="启用状态">
            <el-switch v-model="form.is_active" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitUser">保存</el-button>
        </template>
      </el-dialog>
    </section>
  </ConsoleLayout>
</template>
