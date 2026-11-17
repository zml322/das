<template>
  <aside class="dashboard-right">
    <section class="instrument-panel layer-panel">
      <h2><AppIcon name="layers" />图层控制</h2>
      <div class="layer-list">
        <label v-for="layer in layers" :key="layer.key"
          ><input
            type="checkbox"
            :checked="layer.visible"
            @change="emit('layer', layer.key, !layer.visible)"
          /><span>{{ layer.label }}</span></label
        >
      </div>
      <div class="soil-opacity">
        <label for="soil-opacity">地下透明度</label>
        <div class="opacity-control"><input
          id="soil-opacity"
          type="range"
          min="0"
          max="100"
          :value="opacity"
          @input="
            emit('opacity', Number(($event.target as HTMLInputElement).value))
          "
        /><output for="soil-opacity">{{ opacity }}%</output></div>
      </div>
    </section>
    <section class="instrument-panel scene-status">
      <h2><AppIcon name="wave" />场景状态</h2>
      <div class="status-tiles">
        <div>
          <AppIcon name="chart" /><span>监测区段</span><strong
            >{{ overview?.monitoringSegments ?? 0 }} <small>个</small></strong
          >
        </div>
        <div>
          <AppIcon name="pin" /><span>监测设备</span><strong
            >{{ devices.length }} <small>台</small></strong
          >
        </div>
        <div>
          <AppIcon name="fiber" /><span>光纤总长</span><strong
            >{{ totalLength }} <small>km</small></strong
          >
        </div>
      </div>
      <div class="connection-state">
        <i class="online-dot" />模拟数据源 · 已连接
      </div>
      <details v-if="settingsOpen" open>
        <summary>视觉与动画设置</summary>
        <div class="visual-settings">
          <label
            >动画状态<select
              :value="visual.playback"
              @change="
                emit('visual', {
                  playback: ($event.target as HTMLSelectElement)
                    .value as VisualState['playback'],
                })
              "
            >
              <option value="running">运行</option>
              <option value="paused">暂停</option>
              <option value="stopped">停止复位</option>
            </select></label
          ><label v-for="effect in effects" :key="effect.key"
            ><input
              type="checkbox"
              :checked="visual[effect.key]"
              @change="emit('visual', { [effect.key]: !visual[effect.key] })"
            />{{ effect.label }}</label
          ><label
            >速度 {{ visual.speed }}×<input
              type="range"
              min="0.25"
              max="3"
              step="0.25"
              :value="visual.speed"
              @input="
                emit('visual', {
                  speed: Number(($event.target as HTMLInputElement).value),
                })
              "
          /></label>
        </div>
      </details>
    </section>
  </aside>
</template>
<script setup lang="ts">
import { computed } from "vue";
import type { Device, Fiber, SystemOverview } from "@/types/monitoring";
import type { VisualState } from "@/three/effects/PathEffects";
import AppIcon from "./AppIcon.vue";
const props = defineProps<{
  layers: { key: string; label: string; visible: boolean }[];
  opacity: number;
  visual: VisualState;
  overview: SystemOverview | null;
  devices: Device[];
  fibers: Fiber[];
  settingsOpen: boolean;
}>();
const emit = defineEmits<{
  layer: [key: string, visible: boolean];
  opacity: [value: number];
  visual: [patch: Partial<VisualState>];
}>();
const effects: {
  key: "flow" | "scan" | "markers" | "boundary" | "reflection";
  label: string;
}[] = [
  { key: "flow", label: "光纤流光" },
  { key: "scan", label: "管线扫描" },
  { key: "markers", label: "监测标记" },
  { key: "boundary", label: "工程边界" },
  { key: "reflection", label: "环境反射" },
];
const totalLength = computed(() =>
  (
    props.fibers.reduce((sum, f) => sum + f.endChainage - f.startChainage, 0) /
    1000
  ).toFixed(2),
);
</script>
