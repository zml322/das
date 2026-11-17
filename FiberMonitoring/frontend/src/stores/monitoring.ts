import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type {
  SystemOverview,
  Fiber,
  MonitoringEvent,
  Device,
} from "@/types/monitoring";
import { mockDataSource } from "@/services/mock/MockMonitoringDataSource";

/**
 * 监测数据状态管理
 */
export const useMonitoringStore = defineStore("monitoring", () => {
  // 状态
  const overview = ref<SystemOverview | null>(null);
  const fibers = ref<Fiber[]>([]);
  const devices = ref<Device[]>([]);
  const events = ref<MonitoringEvent[]>([]);

  const selectedFiberId = ref<string | null>(null);

  const loading = ref(false);
  const error = ref<string | null>(null);

  // 计算属性
  const selectedFiber = computed(() => {
    if (!selectedFiberId.value) return null;
    return (
      fibers.value.find((f) => f.fiberId === selectedFiberId.value) || null
    );
  });

  const onlineDevices = computed(() => {
    return devices.value.filter((d) => d.online);
  });

  const activeEvents = computed(() => {
    return events.value.filter((e) => e.status === "active");
  });

  // 初始化
  let initialization: Promise<void> | null = null;
  function initialize(): Promise<void> {
    if (!initialization) initialization = initializeOnce();
    return initialization;
  }
  async function initializeOnce() {
    loading.value = true;
    error.value = null;

    try {
      // 加载初始数据
      await Promise.all([
        loadOverview(),
        loadFibers(),
        loadDevices(),
        loadEvents(),
      ]);

      // 订阅实时更新
      mockDataSource.subscribeEvents((event) => {
        events.value.unshift(event);
        if (events.value.length > 50) {
          events.value.pop();
        }
      });

      mockDataSource.subscribeDeviceStatus((device) => {
        const index = devices.value.findIndex(
          (d) => d.deviceId === device.deviceId,
        );
        if (index >= 0) {
          devices.value[index] = device;
        }
      });
    } catch (err) {
      error.value = err instanceof Error ? err.message : "初始化失败";
      console.error("初始化失败:", err);
    } finally {
      loading.value = false;
    }
  }

  async function loadOverview() {
    overview.value = await mockDataSource.getOverview();
  }

  async function loadFibers() {
    fibers.value = await mockDataSource.getFiberList();
  }

  async function loadDevices() {
    devices.value = await mockDataSource.getDevices();
  }

  async function loadEvents() {
    events.value = await mockDataSource.getMonitoringEvents();
  }

  function selectFiber(fiberId: string | null) {
    selectedFiberId.value = fiberId;
  }

  return {
    // 状态
    overview,
    fibers,
    devices,
    events,

    selectedFiberId,

    loading,
    error,

    // 计算属性
    selectedFiber,
    onlineDevices,
    activeEvents,

    // 方法
    initialize,
    loadOverview,
    loadFibers,
    loadDevices,
    loadEvents,

    selectFiber,
  };
});
