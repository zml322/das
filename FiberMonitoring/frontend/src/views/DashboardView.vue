<template>
  <!-- 页面只负责布局和共享开关，渲染逻辑放在 composables/three。 -->
  <main class="monitoring-dashboard">
    <PlatformHeader
      :alarms="store.overview?.activeAlarms ?? 0"
      @settings="settingsOpen = !settingsOpen"
      @scene="viewport?.overview()"
    />
    <OverviewStrip :overview="store.overview" />
    <div class="dashboard-workspace">
      <aside class="dashboard-left">
        <ResourcePanel
          :fibers="store.fibers"
          @focus="viewport?.focusLayer($event)"
          @fiber="viewport?.focusFiber($event)"
        /><LiveEventPanel
          :events="store.events"
          :fibers="store.fibers"
          @select="viewport?.focusEvent($event)"
        />
      </aside>
      <SceneViewport
        ref="viewport"
        :visual="visual"
        :opacity="opacity"
        :layers="layers"
        @visual="setVisual"
      />
      <SceneSidebar
        :layers="layers"
        :opacity="opacity"
        :visual="visual"
        :overview="store.overview"
        :devices="store.devices"
        :fibers="store.fibers"
        :settings-open="settingsOpen"
        @layer="setLayer"
        @opacity="opacity = $event"
        @visual="setVisual"
      />
    </div>
    <TelemetryDock />
  </main>
</template>
<script setup lang="ts">
import { ref } from "vue";
import { useRoute } from "vue-router";
import { useMonitoringStore } from "@/stores/monitoring";
import {
  defaultVisualState,
  type VisualState,
} from "@/three/effects/PathEffects";
import PlatformHeader from "@/components/dashboard/PlatformHeader.vue";
import OverviewStrip from "@/components/dashboard/OverviewStrip.vue";
import ResourcePanel from "@/components/dashboard/ResourcePanel.vue";
import LiveEventPanel from "@/components/dashboard/LiveEventPanel.vue";
import SceneSidebar from "@/components/dashboard/SceneSidebar.vue";
import SceneViewport from "@/components/dashboard/SceneViewport.vue";
import TelemetryDock from "@/components/dashboard/TelemetryDock.vue";
import "@/assets/styles/dashboard.css";
const store = useMonitoringStore(),
  viewport = ref<InstanceType<typeof SceneViewport> | null>(null);
const settingsOpen = ref(useRoute().query.panel === "settings"),
  opacity = ref(100),
  visual = ref(defaultVisualState());
if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  visual.value.playback = "paused";
const layers = ref([
  { key: "road", label: "地面设施", visible: true },
  { key: "underground", label: "地下土层", visible: true },
  { key: "pipe", label: "排污管道", visible: true },
  { key: "fiber", label: "光纤网络", visible: true },
  { key: "vehicle", label: "车辆", visible: true },
  { key: "marker", label: "监测点", visible: true },
]);
function setLayer(key: string, visible: boolean) {
  const layer = layers.value.find((item) => item.key === key);
  if (layer) layer.visible = visible;
}
function setVisual(patch: Partial<VisualState>) {
  visual.value = { ...visual.value, ...patch };
}
</script>
