// 浏览器模式不显示原生按钮；桌面模式通过 WebChannel 调用窗口动作。
import { onMounted, onUnmounted, ref } from "vue";

interface DesktopWindow {
  minimize(): void;
  toggleMaximize(): void;
  close(): void;
  startMove(): void;
}
declare global {
  interface Window {
    desktopWindow?: DesktopWindow;
  }
}

export function useDesktopWindow() {
  const desktop = ref(Boolean(window.desktopWindow));
  const refresh = () => {
    desktop.value = Boolean(window.desktopWindow);
  };
  onMounted(() => {
    refresh();
    window.addEventListener("desktop-window-ready", refresh);
  });
  onUnmounted(() =>
    window.removeEventListener("desktop-window-ready", refresh),
  );
  return {
    desktop,
    minimize: () => window.desktopWindow?.minimize(),
    maximize: () => window.desktopWindow?.toggleMaximize(),
    close: () => window.desktopWindow?.close(),
    move: () => window.desktopWindow?.startMove(),
  };
}
