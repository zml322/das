<template>
  <header class="platform-header">
    <div class="platform-brand" @mousedown.left="move" @dblclick="maximize">
      <svg class="brand-mark" viewBox="0 0 90 64" fill="none" aria-hidden="true">
        <path d="M75 10C42-7 30 7 11 27c-9 10-2 23 12 22h53M73 21C48 6 36 18 20 30c-7 6-1 12 9 11h45M76 32H29M32 55h38" stroke="currentColor" stroke-width="4" stroke-linecap="round" />
        <circle cx="76" cy="10" r="5" fill="currentColor" /><circle cx="77" cy="21" r="4" fill="currentColor" /><circle cx="79" cy="32" r="4" fill="currentColor" /><circle cx="80" cy="49" r="4" fill="currentColor" /><circle cx="75" cy="55" r="4" fill="currentColor" />
      </svg>
      <h1>光纤全场景三维智能监测平台</h1>
    </div>
    <nav aria-label="平台导航">
      <button
        v-for="item in navigation"
        :key="item.label"
        :class="{ active: isActive(item.path) }"
        :aria-current="isActive(item.path) ? 'page' : undefined"
        @click="navigate(item)"
      >
        <AppIcon :name="item.icon" /><span>{{ item.label }}</span>
      </button>
    </nav>
    <div class="header-actions">
      <button aria-label="查看告警" @click="$router.push('/events')">
        <AppIcon name="bell" /><b>{{ alarms }}</b></button
      ><span class="avatar" aria-hidden="true"><svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="8" r="4" /><path d="M4 22v-3a8 8 0 0 1 16 0v3" /></svg></span><span class="administrator">管理员</span
      ><button aria-label="切换全屏" @click="fullscreen">
        <AppIcon name="expand" />
      </button>
      <template v-if="desktop">
        <button aria-label="最小化窗口" @click="minimize">—</button>
        <button class="window-maximize" aria-label="最大化或还原窗口" @click="maximize">▢</button>
        <button aria-label="关闭窗口" @click="close">
          <AppIcon name="close" />
        </button>
      </template>
    </div>
  </header>
</template>
<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import AppIcon from "./AppIcon.vue";
import { useDesktopWindow } from "@/composables/useDesktopWindow";
const { desktop, minimize, maximize, close, move } = useDesktopWindow();
defineProps<{ alarms: number }>();
const emit = defineEmits<{ settings: []; scene: [] }>();
const router = useRouter();
const route = useRoute();
function isActive(path: string) {
  if (path === "scene") return route.path === "/" && route.query.view === "scene";
  return route.path === path && (path !== "/" || !route.query.view);
}
const navigation = [
  { label: "首页", icon: "home", path: "/" },
  { label: "三维监测", icon: "cube", path: "scene" },
  { label: "事件管理", icon: "alert", path: "/events" },
  { label: "数据分析", icon: "chart", path: "/history" },
  { label: "工程档案", icon: "file", path: "/config" },
  { label: "系统管理", icon: "settings", path: "settings" },
];
function navigate(item: (typeof navigation)[number]) {
  if (item.path === "settings") {
    if (route.path === "/") emit("settings");
    else router.push({ path: "/", query: { panel: "settings" } });
  } else if (item.path === "scene") {
    if (route.path === "/") {
      router.replace({ path: "/", query: { view: "scene" } });
      emit("scene");
    } else router.push({ path: "/", query: { view: "scene" } });
  } else router.push(item.path);
}
function fullscreen() {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen();
}
</script>
