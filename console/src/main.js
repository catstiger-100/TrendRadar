import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import App from "./App.vue";
import router from "./router";
import "./styles.css";

const THEME_STORAGE_KEY = "trendradar:console-theme";
const DEFAULT_THEME = "dark";

if (typeof window !== "undefined") {
  const savedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  const theme = savedTheme === "light" ? "light" : DEFAULT_THEME;
  document.documentElement.dataset.theme = theme;
}

createApp(App).use(router).use(ElementPlus).mount("#app");
