<template>
  <section class="overview-strip" aria-label="监测概览">
    <div class="overview-clock">
      <span>{{ date }}</span
      ><strong>{{ time }}</strong>
    </div>
    <article
      v-for="metric in metrics"
      :key="metric.label"
      class="overview-card"
      :class="metric.tone"
    >
      <MetricIcon :name="metric.icon" />
      <div>
        <span>{{ metric.label }}</span
        ><strong
          >{{ metric.value }} <small>{{ metric.unit }}</small></strong
        >
      </div>
      <i />
    </article>
  </section>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import type { SystemOverview } from "@/types/monitoring";
import MetricIcon from "./MetricIcon.vue";
const props = defineProps<{ overview: SystemOverview | null }>();
const now = ref(new Date());
let timer: ReturnType<typeof setInterval>;
const date = computed(
  () =>
    now.value.toLocaleDateString("zh-CN") +
    " " +
    ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"][
      now.value.getDay()
    ],
);
const time = computed(() =>
  now.value.toLocaleTimeString("zh-CN", { hour12: false }),
);
const metrics = computed(() => {
  const o = props.overview;
  return [
    {
      label: "设备在线",
      value: o ? `${o.onlineDevices}/${o.totalDevices}` : "—",
      unit: "",
      icon: "device",
      tone: "green",
    },
    {
      label: "监测光纤",
      value: o?.monitoringFibers ?? "—",
      unit: "条",
      icon: "fiber",
      tone: "green",
    },
    {
      label: "监测区段",
      value: o?.monitoringSegments ?? "—",
      unit: "个",
      icon: "pin",
      tone: "green",
    },
    {
      label: "今日事件",
      value: o?.todayEvents ?? "—",
      unit: "次",
      icon: "chart",
      tone: "cyan",
    },
    {
      label: "实时车辆",
      value: o?.activeVehicles ?? "—",
      unit: "辆",
      icon: "car",
      tone: "cyan",
    },
    {
      label: "异常告警",
      value: o?.activeAlarms ?? "—",
      unit: "条",
      icon: "alert",
      tone: "amber",
    },
  ];
});
onMounted(() => {
  timer = setInterval(() => (now.value = new Date()), 1000);
});
onUnmounted(() => clearInterval(timer));
</script>
