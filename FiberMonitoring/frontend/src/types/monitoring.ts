/**
 * 车辆类型，供场景构建器共用。
 */
export enum VehicleType {
  SEDAN = "sedan",
  SUV = "suv",
  TRUCK = "truck",
  BUS = "bus",
  VAN = "van",
}

/** 光纤用途；枚举与数据源、场景共用。 */
export enum FiberType {
  DAS = "DAS", // 分布式声学传感
  DSS = "DSS", // 分布式应变传感
  COMM = "COMM", // 通信光缆
  BURIED = "BURIED", // 地埋光缆
}

/**
 * 设备状态
 */
export enum DeviceStatus {
  ONLINE = "online",
  OFFLINE = "offline",
  WARNING = "warning",
  ERROR = "error",
}

/**
 * 事件类型
 */
export enum EventType {
  VEHICLE_PASS = "vehicle_pass", // 车辆经过
  VEHICLE_ANOMALY = "vehicle_anomaly", // 车辆异常振动
  CONSTRUCTION = "construction", // 施工扰动
  PIPE_VIBRATION = "pipe_vibration", // 管道振动异常
  FIBER_OFFLINE = "fiber_offline", // 光纤设备离线
}

/**
 * 事件等级
 */
export enum EventSeverity {
  INFO = "info",
  LOW = "low",
  MEDIUM = "medium",
  HIGH = "high",
  CRITICAL = "critical",
}

/**
 * 光纤信息
 */
export interface Fiber {
  fiberId: string;
  fiberName: string;
  fiberType: FiberType;
  channelCount: number;
  samplingRate: number;
  spatialInterval: number;
  startChainage: number;
  endChainage: number;
  status: DeviceStatus;
  color: string;
  path3D: Array<{ x: number; y: number; z: number }>;
}

/**
 * 监测事件
 */
export interface MonitoringEvent {
  eventId: string;
  eventType: EventType;
  eventName: string;
  startTime: Date;
  endTime?: Date;
  fiberId: string;
  startChannel: number;
  endChannel: number;
  position: { x: number; y: number; z: number };
  confidence: number;
  severity: EventSeverity;
  status: "active" | "resolved" | "processing";
  description?: string;
}

/**
 * 设备状态
 */
export interface Device {
  deviceId: string;
  deviceName: string;
  deviceType: "DAS" | "DSS" | "SENSOR";
  online: boolean;
  lastUpdateTime: Date;
  status: DeviceStatus;
  position?: { x: number; y: number; z: number };
}

/**
 * 系统概览数据
 */
export interface SystemOverview {
  onlineDevices: number;
  totalDevices: number;
  monitoringFibers: number;
  monitoringSegments: number;
  todayEvents: number;
  activeVehicles: number;
  activeAlarms: number;
  timestamp: Date;
}

/**
 * 波形数据
 */
export interface WaveformData {
  fiberId: string;
  channelIndex: number;
  timestamp: Date;
  values: number[];
  samplingRate: number;
}
