<template>
  <section class="instrument-panel live-event-panel">
    <h2>
      <AppIcon name="wave" />实时事件
    </h2>
    <div class="event-cards">
      <button
        v-for="event in displayed"
        :key="event.eventId"
        class="live-event-card"
        :class="[tone(event.severity), { 'long-title': event.eventName.length >= 6 }]"
        @click="emit('select', event)"
      >
        <div class="event-card-title">
          <AppIcon
            :name="
              event.eventType.includes('vehicle')
                ? 'car'
                : event.eventType === 'construction'
                  ? 'alert'
                  : 'wave'
            "
          /><strong :title="event.eventName">{{ event.eventName }}</strong
          ><b>{{ severityLabel[event.severity] }}</b><time>{{ elapsed(event.startTime) }}</time>
        </div>
        <div class="event-chainage">
          <span>{{ channelLabel(event) }}</span><time class="compact-event-time">{{ elapsed(event.startTime) }}</time>
        </div>
        <p :title="event.description">{{ event.description || "监测到信号变化，请关注现场状态" }}</p>
      </button>
      <div v-if="!displayed.length" class="empty-state">当前无监测事件</div>
    </div>
    <RouterLink to="/events" class="panel-link">查看更多事件 →</RouterLink>
  </section>
</template>
<script setup lang="ts">
import { computed } from "vue";
import type { MonitoringEvent, Fiber } from "@/types/monitoring";
import AppIcon from "./AppIcon.vue";
const props = defineProps<{ events: MonitoringEvent[]; fibers: Fiber[] }>();
const emit = defineEmits<{ select: [event: MonitoringEvent] }>();
const severityLabel: Record<string, string> = {
  critical: "紧急",
  high: "高",
  medium: "中",
  low: "低",
  info: "信息",
};
const displayed = computed(() =>
  [...props.events]
    .filter((event) => event.status !== "resolved")
    .sort((a, b) => {
      const levels = ["critical", "high", "medium", "low", "info"];
      return levels.indexOf(a.severity) - levels.indexOf(b.severity);
    })
    .slice(0, 3),
);
function tone(severity: string) {
  return ["critical", "high"].includes(severity)
    ? "danger"
    : severity === "medium"
      ? "amber"
      : "cyan";
}
function elapsed(date: Date) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(date).getTime()) / 60000),
  );
  return minutes ? `${minutes} 分钟前` : "刚刚";
}
function channelLabel(event: MonitoringEvent) {
  const fiber = props.fibers.find((f) => f.fiberId === event.fiberId);
  const metre = event.startChannel * (fiber?.spatialInterval ?? 1);
  return `K${Math.floor(metre / 1000)}+${Math.round(metre % 1000)
    .toString()
    .padStart(3, "0")}`;
}
</script>
