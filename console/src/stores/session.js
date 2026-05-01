import { reactive } from "vue";
import { fetchMe, login as loginApi, logout as logoutApi, changePassword as changePasswordApi } from "../api/auth";

const state = reactive({
  user: null,
  loaded: false,
});

export function useSessionStore() {
  async function ensureSession() {
    try {
      const data = await fetchMe();
      state.user = data.user;
    } catch (error) {
      state.user = null;
      if (error.status !== 401) {
        throw error;
      }
    } finally {
      state.loaded = true;
    }
    return state.user;
  }

  async function login(payload) {
    const data = await loginApi(payload);
    state.user = data.user;
    state.loaded = true;
    return data.user;
  }

  async function logout() {
    try {
      await logoutApi();
    } finally {
      state.user = null;
      state.loaded = true;
    }
  }

  async function changePassword(payload) {
    return changePasswordApi(payload);
  }

  function clear() {
    state.user = null;
    state.loaded = true;
  }

  return {
    state,
    ensureSession,
    login,
    logout,
    changePassword,
    clear,
  };
}
