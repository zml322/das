import type {
  SystemOverview,
  Device,
  Fiber,
  MonitoringEvent,
  WaveformData,
} from "@/types/monitoring";

/**
 * 监测数据源接口
 * 所有数据访问必须通过此接口，便于后期替换为真实数据源
 */
export interface MonitoringDataSource {
  /**
   * 获取系统概览数据
   */
  getOverview(): Promise<SystemOverview>;

  /**
   * 获取设备列表
   */
  getDevices(): Promise<Device[]>;

  /**
   * 获取光纤列表
   */
  getFiberList(): Promise<Fiber[]>;

  /**
   * 获取监测事件列表
   */
  getMonitoringEvents(): Promise<MonitoringEvent[]>;

  /**
   * 获取波形数据
   */
  getWaveform(fiberId: string, channelIndex: number): Promise<WaveformData>;

  /**
   * 订阅事件更新
   */
  subscribeEvents(callback: (event: MonitoringEvent) => void): () => void;

  /**
   * 订阅设备状态更新
   */
  subscribeDeviceStatus(callback: (device: Device) => void): () => void;
}
