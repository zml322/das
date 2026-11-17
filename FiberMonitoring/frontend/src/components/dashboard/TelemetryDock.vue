<template>
  <section class="instrument-panel telemetry-dock">
    <div class="telemetry-heading">
      <h2><AppIcon name="chart" />监测数据</h2>
      <div role="tablist" aria-label="监测数据类型" @keydown="navigateTabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          role="tab"
          :id="'telemetry-tab-' + tab.key"
          aria-controls="telemetry-panel"
          :tabindex="active === tab.key ? 0 : -1"
          :aria-selected="active === tab.key"
          :class="{ active: active === tab.key }"
          @click="active = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>
      <span class="telemetry-source"
        ><i class="online-dot" />{{
          store.selectedFiber?.fiberName || "DAS监测光纤-01"
        }}
        · 模拟数据</span
      >
    </div>
    <div v-if="active === 'realtime'" id="telemetry-panel" role="tabpanel" :aria-labelledby="'telemetry-tab-' + active" class="telemetry-content">
      <div class="signal-metrics">
        <article v-for="metric in metrics" :key="metric.label">
          <AppIcon :name="metric.icon" :style="{ color: metric.color }" />
          <div>
            <span>{{ metric.label }}</span
            ><strong :style="{ color: metric.color }"
              >{{ metric.value }} <small>{{ metric.unit }}</small></strong
            >
          </div>
        </article>
      </div>
      <MonitoringChart
        title="振动监测"
        subtitle="实时波形"
        kind="line"
        :values="samples"
        :sampling-rate="samplingRate"
      /><MonitoringChart
        title="事件统计"
        subtitle="最近事件 / 小时"
        kind="bar"
        :values="bars"
      /><MonitoringChart
        title="区段风险分布"
        subtitle="关联事件"
        kind="risk"
        :values="risks"
      />
    </div>
    <div v-else-if="active === 'device'" id="telemetry-panel" role="tabpanel" :aria-labelledby="'telemetry-tab-' + active" class="dock-device-list">
      <article v-for="device in store.devices" :key="device.deviceId">
        <AppIcon name="device" />
        <div>
          <strong>{{ device.deviceName }}</strong
          ><small>{{ device.deviceId }}</small>
        </div>
        <span :class="device.online ? 'text-green' : 'text-amber'">{{
          device.online ? "在线" : "离线"
        }}</span>
      </article>
    </div>
    <div v-else-if="active === 'history'" id="telemetry-panel" role="tabpanel" :aria-labelledby="'telemetry-tab-' + active" class="dock-history">
      <div v-for="event in store.events.slice(0, 6)" :key="event.eventId">
        <time>{{ new Date(event.startTime).toLocaleTimeString() }}</time
        ><strong>{{ event.eventName }}</strong
        ><span>{{ event.fiberId }}</span
        ><span>{{ event.status === "resolved" ? "已恢复" : "待关注" }}</span>
      </div>
    </div>
    <div v-else id="telemetry-panel" role="tabpanel" :aria-labelledby="'telemetry-tab-' + active" class="analysis-summary">
      <AppIcon name="wave" />
      <div>
        <strong>信号统计分析</strong>
        <p>
          均方根振幅 {{ rms.toFixed(3) }} mV · 峰值 {{ peak.toFixed(3) }} mV ·
          {{ samples.length }} 个采样点
        </p>
        <small>来源：当前选中光纤单通道模拟波形</small>
      </div>
      <RouterLink to="/history">进入数据分析 →</RouterLink>
    </div>
    <p v-if="error" class="data-error" role="status">{{ error }}</p>
  </section>
</template>
<script setup lang="ts">
import { ref, computed } from "vue";
import { useMonitoringStore } from "@/stores/monitoring";
import { useTelemetry } from "@/composables/useTelemetry";
import AppIcon from "./AppIcon.vue";
import MonitoringChart from "./MonitoringChart.vue";
const store = useMonitoringStore(),
  active = ref("realtime");
const { samples, samplingRate, rms, peak, bars, risks, error } = useTelemetry();
const tabs = [
  { key: "realtime", label: "实时数据" },
  { key: "history", label: "历史数据" },
  { key: "analysis", label: "分析结果" },
  { key: "device", label: "设备状态" },
];
function navigateTabs(event: KeyboardEvent) {
  const index = tabs.findIndex(tab => tab.key === active.value);
  let next: number;
  if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
  else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
  else if (event.key === 'Home') next = 0;
  else if (event.key === 'End') next = tabs.length - 1;
  else return;
  event.preventDefault();
  active.value = tabs[next].key;
  const buttons = (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="tab"]');
  buttons[next].focus();
}
const metrics = computed(() => [
  {
    label: "通道振幅 RMS",
    value: rms.value.toFixed(2),
    unit: "mV",
    icon: "wave",
    color: "#4ed9ff",
  },
  {
    label: "通道峰值",
    value: peak.value.toFixed(2),
    unit: "mV",
    icon: "wave",
    color: "#38e59a",
  },
  {
    label: "采样率",
    value:
      store.selectedFiber?.samplingRate ?? store.fibers[0]?.samplingRate ?? "—",
    unit: "Hz",
    icon: "chart",
    color: "#4ed9ff",
  },
  {
    label: "空间间隔",
    value:
      store.selectedFiber?.spatialInterval ??
      store.fibers[0]?.spatialInterval ??
      "—",
    unit: "m",
    icon: "fiber",
    color: "#ffc354",
  },
]);
</script>
