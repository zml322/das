import type { MonitoringDataSource } from "../interfaces/MonitoringDataSource";
import type {
  SystemOverview,
  Device,
  Fiber,
  MonitoringEvent,
  WaveformData,
} from "@/types/monitoring";
import {
  FiberType,
  DeviceStatus,
  EventType,
  EventSeverity,
} from "@/types/monitoring";

/**
 * Mock 数据服务
 * 第一版使用模拟数据，后期替换为真实 HTTP/WebSocket 数据源
 */
export class MockMonitoringDataSource implements MonitoringDataSource {
  private eventCallbacks: Array<(event: MonitoringEvent) => void> = [];
  private deviceCallbacks: Array<(device: Device) => void> = [];
  private eventInterval?: number;
  private deviceInterval?: number;

  constructor() {
    // 启动模拟事件生成器
    this.startSimulation();
  }

  /**
   * 启动模拟数据生成
   */
  private startSimulation() {
    // 每5秒生成一个随机事件
    this.eventInterval = window.setInterval(() => {
      const event = this.generateRandomEvent();
      this.eventCallbacks.forEach((cb) => cb(event));
    }, 5000);

    // 每10秒更新一次设备状态
    this.deviceInterval = window.setInterval(() => {
      const devices = this.getMockDevices();
      const randomDevice = devices[Math.floor(Math.random() * devices.length)];
      this.deviceCallbacks.forEach((cb) => cb(randomDevice));
    }, 10000);
  }

  /**
   * 停止模拟
   */
  stopSimulation() {
    if (this.eventInterval) clearInterval(this.eventInterval);
    if (this.deviceInterval) clearInterval(this.deviceInterval);
  }

  async getOverview(): Promise<SystemOverview> {
    return {
      onlineDevices: 4,
      totalDevices: 5,
      monitoringFibers: 4,
      monitoringSegments: 3,
      todayEvents: 127,
      activeVehicles: 8,
      activeAlarms: 3,
      timestamp: new Date(),
    };
  }

  async getDevices(): Promise<Device[]> {
    return this.getMockDevices();
  }

  private getMockDevices(): Device[] {
    return [
      {
        deviceId: "DAS-001",
        deviceName: "DAS监测设备-01",
        deviceType: "DAS",
        online: true,
        lastUpdateTime: new Date(),
        status: DeviceStatus.ONLINE,
        position: { x: -440, y: 0, z: 18 },
      },
      {
        deviceId: "DSS-001",
        deviceName: "DSS监测设备-01",
        deviceType: "DSS",
        online: true,
        lastUpdateTime: new Date(),
        status: DeviceStatus.ONLINE,
        position: { x: -260, y: 0, z: 18 },
      },
      {
        deviceId: "DAS-002",
        deviceName: "DAS监测设备-02",
        deviceType: "DAS",
        online: true,
        lastUpdateTime: new Date(),
        status: DeviceStatus.ONLINE,
        position: { x: 440, y: 0, z: 18 },
      },
      {
        deviceId: "SENSOR-002",
        deviceName: "?????-02",
        deviceType: "SENSOR",
        online: true,
        lastUpdateTime: new Date(),
        status: DeviceStatus.ONLINE,
        position: { x: -30, y: 0, z: -18 },
      },
      {
        deviceId: "SENSOR-001",
        deviceName: "环境传感器-01",
        deviceType: "SENSOR",
        online: false,
        lastUpdateTime: new Date(Date.now() - 3600000),
        status: DeviceStatus.OFFLINE,
        position: { x: 225, y: -1.1, z: 18.3 },
      },
    ];
  }

  async getFiberList(): Promise<Fiber[]> {
    return this.getMockFibers();
  }

  private getMockFibers(): Fiber[] {
    return [
      {
        fiberId: "FIBER-DAS-001",
        fiberName: "DAS监测光纤-01",
        fiberType: FiberType.DAS,
        channelCount: 910,
        samplingRate: 1000,
        spatialInterval: 1.0,
        startChainage: 0,
        endChainage: 910,
        status: DeviceStatus.ONLINE,
        color: "#ff4a4f",
        path3D: this.generateFiberPath(18.3, -1.1, 0),
      },
      {
        fiberId: "FIBER-DSS-001",
        fiberName: "DSS应变光纤-01",
        fiberType: FiberType.DSS,
        channelCount: 455,
        samplingRate: 100,
        spatialInterval: 2.0,
        startChainage: 0,
        endChainage: 910,
        status: DeviceStatus.ONLINE,
        color: "#11caff",
        path3D: this.generateFiberPath(18.3, -2.0, 0),
      },
      {
        fiberId: "FIBER-COMM-001",
        fiberName: "通信光缆-01",
        fiberType: FiberType.COMM,
        channelCount: 182,
        samplingRate: 50,
        spatialInterval: 5.0,
        startChainage: 0,
        endChainage: 910,
        status: DeviceStatus.ONLINE,
        color: "#38ed86",
        path3D: this.generateFiberPath(19.8, -2.9, 0),
      },
      {
        fiberId: "FIBER-BURIED-001",
        fiberName: "地埋光缆-01",
        fiberType: FiberType.BURIED,
        channelCount: 182,
        samplingRate: 50,
        spatialInterval: 5.0,
        startChainage: 0,
        endChainage: 910,
        status: DeviceStatus.WARNING,
        color: "#ff6600",
        path3D: this.generateFiberPath(17, -1.6, 0),
      },
    ];
  }

  private generateFiberPath(
    offsetZ: number,
    offsetY: number,
    offsetX: number,
  ): Array<{ x: number; y: number; z: number }> {
    const points: Array<{ x: number; y: number; z: number }> = [];
    const segments = 50;
    const length = 910;

    for (let i = 0; i <= segments; i++) {
      const t = i / segments;
      const x = (t - 0.5) * length + offsetX;
      const y = offsetY + Math.sin(t * Math.PI * 2) * 0.2;
      const z = offsetZ;
      points.push({ x, y, z });
    }

    if (offsetZ !== 19.8)
      points.push(
        { x: length / 2 + 3, y: offsetY, z: offsetZ },
        { x: length / 2 + 5, y: -2.9, z: 19.8 },
        { x: length / 2, y: -2.9, z: 19.8 },
      );
    return points;
  }

  async getMonitoringEvents(): Promise<MonitoringEvent[]> {
    return this.getMockEvents();
  }

  private getMockEvents(): MonitoringEvent[] {
    const now = new Date();
    const events: MonitoringEvent[] = [
      {
        eventId: "EVT-001",
        eventType: EventType.VEHICLE_PASS,
        eventName: "车辆经过",
        startTime: new Date(now.getTime() - 120000),
        fiberId: "FIBER-DAS-001",
        startChannel: 234,
        endChannel: 256,
        position: { x: -200, y: 0, z: 5 },
        confidence: 0.95,
        severity: EventSeverity.INFO,
        status: "resolved",
        description: "轿车通过，速度60km/h",
      },
      {
        eventId: "EVT-002",
        eventType: EventType.VEHICLE_ANOMALY,
        eventName: "车辆异常振动",
        startTime: new Date(now.getTime() - 60000),
        fiberId: "FIBER-DAS-001",
        startChannel: 680,
        endChannel: 700,
        position: { x: 50, y: 0, z: 5 },
        confidence: 0.87,
        severity: EventSeverity.MEDIUM,
        status: "active",
        description: "重型货车产生异常振动",
      },
      {
        eventId: "EVT-003",
        eventType: EventType.CONSTRUCTION,
        eventName: "施工扰动",
        startTime: new Date(now.getTime() - 180000),
        fiberId: "FIBER-DSS-001",
        startChannel: 160,
        endChannel: 180,
        position: { x: -350, y: 0, z: -10 },
        confidence: 0.92,
        severity: EventSeverity.HIGH,
        status: "active",
        description: "道路维护施工活动",
      },
      {
        eventId: "EVT-004",
        eventType: EventType.PIPE_VIBRATION,
        eventName: "管道振动异常",
        startTime: new Date(now.getTime() - 30000),
        fiberId: "FIBER-DSS-001",
        startChannel: 300,
        endChannel: 320,
        position: { x: 100, y: -4.5, z: 0 },
        confidence: 0.78,
        severity: EventSeverity.HIGH,
        status: "processing",
        description: "排污管道振动超出正常范围",
      },
      {
        eventId: "EVT-005",
        eventType: EventType.FIBER_OFFLINE,
        eventName: "光纤设备离线",
        startTime: new Date(now.getTime() - 3600000),
        fiberId: "FIBER-BURIED-001",
        startChannel: 0,
        endChannel: 182,
        position: { x: -450, y: 0, z: 8 },
        confidence: 1.0,
        severity: EventSeverity.CRITICAL,
        status: "resolved",
        description: "地埋光缆连接中断",
      },
    ];
    return events.map((event) => {
      const fiber = this.getMockFibers().find(
        (item) => item.fiberId === event.fiberId,
      )!;
      return {
        ...event,
        position: this.positionOnFiber(fiber, event.startChannel),
      };
    });
  }

  private positionOnFiber(
    fiber: Fiber,
    channel: number,
  ): { x: number; y: number; z: number } {
    const chainage = Math.min(
      910,
      Math.max(0, channel * fiber.spatialInterval),
    );
    const depth = fiber.path3D[0].y;
    return {
      x: chainage - 455,
      y: depth + Math.sin((chainage / 910) * Math.PI * 2) * 0.2,
      z: fiber.path3D[0].z,
    };
  }

  private generateRandomEvent(): MonitoringEvent {
    const eventTypes = Object.values(EventType);
    const severities = Object.values(EventSeverity);
    const fibers = this.getMockFibers();

    const randomType =
      eventTypes[Math.floor(Math.random() * eventTypes.length)];
    const randomFiber = fibers[Math.floor(Math.random() * fibers.length)];
    const randomChannel = Math.floor(Math.random() * randomFiber.channelCount);

    return {
      eventId: `EVT-${Date.now()}`,
      eventType: randomType,
      eventName: this.getEventTypeName(randomType),
      startTime: new Date(),
      fiberId: randomFiber.fiberId,
      startChannel: randomChannel,
      endChannel: Math.min(
        randomFiber.channelCount - 1,
        randomChannel + Math.floor(Math.random() * 50),
      ),
      position: this.positionOnFiber(randomFiber, randomChannel),
      confidence: 0.7 + Math.random() * 0.3,
      severity: severities[Math.floor(Math.random() * severities.length)],
      status: "active",
      description: `随机生成的${this.getEventTypeName(randomType)}事件`,
    };
  }

  private getEventTypeName(type: EventType): string {
    const names: Record<EventType, string> = {
      [EventType.VEHICLE_PASS]: "车辆经过",
      [EventType.VEHICLE_ANOMALY]: "车辆异常振动",
      [EventType.CONSTRUCTION]: "施工扰动",
      [EventType.PIPE_VIBRATION]: "管道振动异常",
      [EventType.FIBER_OFFLINE]: "光纤设备离线",
    };
    return names[type];
  }

  async getWaveform(
    fiberId: string,
    channelIndex: number,
  ): Promise<WaveformData> {
    const samplingRate = 1000;
    const duration = 10; // 10秒数据
    const samples = samplingRate * duration;

    // 生成模拟波形：正弦波 + 噪声
    const values: number[] = [];
    for (let i = 0; i < samples; i++) {
      const t = i / samplingRate;
      const signal = Math.sin(2 * Math.PI * 5 * t) * 100; // 5Hz 正弦波
      const noise = (Math.random() - 0.5) * 20;
      values.push(signal + noise);
    }

    return {
      fiberId,
      channelIndex,
      timestamp: new Date(),
      values,
      samplingRate,
    };
  }

  subscribeEvents(callback: (event: MonitoringEvent) => void): () => void {
    this.eventCallbacks.push(callback);
    return () => {
      const index = this.eventCallbacks.indexOf(callback);
      if (index > -1) {
        this.eventCallbacks.splice(index, 1);
      }
    };
  }

  subscribeDeviceStatus(callback: (device: Device) => void): () => void {
    this.deviceCallbacks.push(callback);
    return () => {
      const index = this.deviceCallbacks.indexOf(callback);
      if (index > -1) {
        this.deviceCallbacks.splice(index, 1);
      }
    };
  }
}

// 导出单例
export const mockDataSource = new MockMonitoringDataSource();
