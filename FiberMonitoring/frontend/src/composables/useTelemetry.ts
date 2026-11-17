// 定时获取当前光纤波形，派生振幅、事件统计和风险数据。
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useMonitoringStore } from "@/stores/monitoring";
import { mockDataSource } from "@/services/mock/MockMonitoringDataSource";
export function useTelemetry() {
  const store = useMonitoringStore(),
    samples = ref<number[]>([]),
    samplingRate = ref(1000),
    error = ref(""),
    updated = ref<Date | null>(null);
  let timer: ReturnType<typeof setInterval>,
    disposed = false,
    loading = false;
  const fiberId = computed(
    () => store.selectedFiberId || store.fibers[0]?.fiberId,
  );
  async function refresh() {
    if (!fiberId.value || loading) return;
    loading = true;
    try {
      const data = await mockDataSource.getWaveform(fiberId.value, 0);
      if (!disposed) {
        samples.value = data.values;
        samplingRate.value = data.samplingRate;
        updated.value = data.timestamp;
        error.value = "";
      }
    } catch {
      if (!disposed) error.value = "监测数据暂不可用";
    } finally {
      loading = false;
    }
  }
  const rms = computed(() =>
    samples.value.length
      ? Math.sqrt(
          samples.value.reduce((sum, value) => sum + value * value, 0) /
            samples.value.length,
        )
      : 0,
  );
  const peak = computed(() =>
    samples.value.reduce(
      (value, sample) => Math.max(value, Math.abs(sample)),
      0,
    ),
  );
  const bars = computed(() =>
    Array.from(
      { length: 24 },
      (_, hour) =>
        store.events.filter(
          (event) => new Date(event.startTime).getHours() === hour,
        ).length,
    ),
  );
  const risks = computed(() =>
    Array.from({ length: 12 }, (_, index) => {
      const levels = { info: 0, low: 1, medium: 2, high: 3, critical: 4 };
      return store.events
        .filter(
          (e) =>
            e.status !== "resolved" &&
            Math.min(
              11,
              Math.floor(
                ((e.startChannel *
                  (store.fibers.find((fiber) => fiber.fiberId === e.fiberId)
                    ?.spatialInterval ?? 1)) /
                  910) *
                  12,
              ),
            ) === index,
        )
        .reduce((max, e) => Math.max(max, levels[e.severity]), 0);
    }),
  );
  watch(fiberId, refresh);
  onMounted(() => {
    refresh();
    timer = setInterval(refresh, 1500);
  });
  onUnmounted(() => {
    disposed = true;
    clearInterval(timer);
  });
  return { samples, samplingRate, rms, peak, bars, risks, error, updated, refresh };
}
