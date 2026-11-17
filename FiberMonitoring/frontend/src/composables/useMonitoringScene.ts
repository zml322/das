// Vue 与 Three.js 的连接层：初始化、状态监听、交互及销毁。
import { ref, onMounted, onUnmounted, watch, type Ref } from "vue";
import * as THREE from "three";
import { SceneManager } from "@/three/core/SceneManager";
import { buildScene } from "@/three/core/SceneBuilder";
import { useMonitoringStore } from "@/stores/monitoring";
import type { MonitoringEvent } from "@/types/monitoring";
import type { VisualState } from "@/three/effects/PathEffects";
import { enhanceScene } from "@/three/engineering/SceneRealism";
import { insideHero } from "@/three/hero/config";
export function useMonitoringScene(
  container: Ref<HTMLElement | null>,
  visual: () => VisualState,
  onSelect: (value: Record<string, unknown>) => void,
) {
  const store = useMonitoringStore(),
    error = ref(""),
    notice = ref(""),
    ready = ref(false);
  let manager: SceneManager | null = null,
    disposed = false;
  onMounted(async () => {
    try {
      await store.initialize();
      if (disposed || !container.value) return;
      manager = new SceneManager(container.value);
      await buildScene(manager, store);
      if (disposed) return;
      await enhanceScene(manager, () => disposed);
      if (disposed) return;
      manager.setVisualState(visual());
      ready.value = true;
      manager.onObjectClick((object) => {
        onSelect({ ...object.userData, name: object.name });
        if (object.userData.fiberId) store.selectFiber(object.userData.fiberId);
      });
      manager.onObjectHover(() => {});
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : "场景加载失败";
    }
  });
  watch(
    () => visual(),
    (value) => manager?.setVisualState(value),
    { deep: true },
  );
  watch(
    () => [store.fibers, store.devices, store.events],
    () => manager?.syncMonitoring(store.fibers, store.devices, store.events),
    { deep: true },
  );
  onUnmounted(() => {
    disposed = true;
    manager?.dispose();
    manager = null;
  });
  function setLayer(key: string, visible: boolean) {
    manager?.toggleLayer(key, visible);
  }
  function setOpacity(value: number) {
    manager?.setUndergroundOpacity(value / 100);
  }
  function preset(key: string) {
    manager?.setViewPreset(key as Parameters<SceneManager["setViewPreset"]>[0]);
  }
  function focusFiber(id: string) {
    store.selectFiber(id);
    const model = manager?.fiberGroup.children.find(
      (child) => child.userData.fiberId === id,
    );
    if (model) manager?.focusOnObject(model, 85);
  }
  function focusEvent(event: MonitoringEvent) {
    if (!insideHero(event.position)) {
      notice.value = "该事件位于当前 K0+300～K0+400 精细展示区段之外";
      return;
    }
    notice.value = "";
    const marker = manager?.markerGroup.children.find(
      (child) => child.userData.eventId === event.eventId,
    );
    if (marker) manager?.focusOnObject(marker, 35);
  }
  function focusLayer(key: string) {
    if (!manager) return;
    const groups: Record<string, THREE.Group> = {
      road: manager.roadGroup,
      pipe: manager.pipeGroup,
      fiber: manager.fiberGroup,
      underground: manager.undergroundGroup,
    };
    if (groups[key]) manager.focusOnObject(groups[key], 85);
  }
  return {
    error,
    notice,
    ready,
    setLayer,
    setOpacity,
    preset,
    focusFiber,
    focusEvent,
    focusLayer,
  };
}
