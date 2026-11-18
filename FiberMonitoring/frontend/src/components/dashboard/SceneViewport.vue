<template>
  <section class="scene-viewport" aria-label="城市道路与地下管线三维场景" :aria-busy="!ready">
    <div ref="container" class="three-surface" />
    <div class="scene-view-tabs">
      <button
        v-for="view in views"
        :key="view.key"
        :class="{ active: activeView === view.key }"
        :aria-pressed="activeView === view.key"
        @click="changeView(view.key)"
      >
        <AppIcon :name="view.icon" />{{ view.label }}
      </button>
    </div>
    <button class="annotation-toggle" :aria-pressed="detailedAnnotations" @click="detailedAnnotations = !detailedAnnotations">
      <AppIcon name="layers" />{{ detailedAnnotations ? '收起工程标注' : '工程标注' }}
    </button>
    <div v-if="!detailedAnnotations" class="fiber-legend" aria-label="光纤图例">
      <span><i class="das" />DAS 声学</span><span><i class="dss" />DSS 应变</span><span><i class="comm" />通信光缆</span>
    </div>
    <div v-if="!ready && !error" class="scene-indicators">
      <span
        ><i class="online-dot" />{{
          ready ? "三维场景已连接" : "正在加载场景"
        }}</span
      ><span>精细区段 K0+300 — K0+400 · 100 m</span>
    </div>
    <div class="scene-playback">
      <button
        @click="
          emit('visual', {
            playback: visual.playback === 'running' ? 'paused' : 'running',
          })
        "
        :aria-label="
          visual.playback === 'running' ? '暂停场景动画' : '播放场景动画'
        "
      >
        <AppIcon
          :name="visual.playback === 'running' ? 'pause' : 'play'"
        /></button
      ><span>{{
        visual.playback === "running"
          ? "实时监测"
          : visual.playback === "paused"
            ? "动画已暂停"
            : "动画已复位"
      }}</span
      ><button @click="changeView('overview')">重置视角</button>
    </div>
    <div v-if="error" class="scene-error" role="alert">
      场景加载失败：{{ error }}
    </div>
    <div v-if="notice" class="scene-notice" role="status">
      {{ notice }}<button aria-label="关闭提示" @click="notice = ''">×</button>
    </div>
    <div v-if="selection" class="scene-selection">
      <button aria-label="关闭对象详情" @click="selection = null">
        <AppIcon name="close" /></button
      ><strong>{{ selection.name || "已选对象" }}</strong
      ><small>{{
        selection.fiberId ||
        selection.deviceId ||
        selection.eventId ||
        "工程模型"
      }}</small>
      <DetailPanel :selected-object="selection" :fiber="selectedFiber" />
    </div>
  </section>
</template>
<script setup lang="ts">
import { ref, watch, computed } from "vue";
import { useMonitoringStore } from "@/stores/monitoring";
import DetailPanel from "./DetailPanel.vue";
import type { VisualState } from "@/three/effects/PathEffects";
import { useMonitoringScene } from "@/composables/useMonitoringScene";
import AppIcon from "./AppIcon.vue";
const props = defineProps<{
  visual: VisualState;
  opacity: number;
  layers: { key: string; visible: boolean }[];
}>();
const emit = defineEmits<{ visual: [patch: Partial<VisualState>] }>();
const container = ref<HTMLElement | null>(null),
  selection = ref<Record<string, unknown> | null>(null),
  activeView = ref("overview");
const detailedAnnotations = ref(false);
const scene = useMonitoringScene(
  container,
  () => props.visual,
  (value) => (selection.value = value),
);
const { ready, error, notice } = scene;
watch(() => [detailedAnnotations.value, ready.value], () => scene.setAnnotationsDetailed(detailedAnnotations.value));
const store = useMonitoringStore();
const selectedFiber = computed(
  () =>
    store.fibers.find((fiber) => fiber.fiberId === selection.value?.fiberId) ??
    null,
);
const views = [
  { key: "overview", label: "全景", icon: "cube" },
  { key: "top", label: "俯视", icon: "pin" },
  { key: "underground", label: "地下", icon: "pipe" },
  { key: "cross", label: "横断面", icon: "layers" },
  { key: "longitudinal", label: "纵断面", icon: "chart" },
];
watch(
  () => [props.opacity, ready.value],
  () => {
    if (ready.value) scene.setOpacity(props.opacity);
  },
);
watch(
  () => [props.layers, ready.value],
  () => {
    if (ready.value)
      props.layers.forEach((layer) => scene.setLayer(layer.key, layer.visible));
  },
  { deep: true },
);
function changeView(key: string) {
  activeView.value = key;
  scene.preset(key);
}
defineExpose({
  focusEvent: scene.focusEvent,
  focusFiber: scene.focusFiber,
  focusLayer: scene.focusLayer,
  overview: () => changeView("overview"),
});
</script>
