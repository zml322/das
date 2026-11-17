import * as THREE from "three";
import {
  addPathEffects,
  createMarker,
  disposeObject,
} from "../effects/PathEffects";

/**
 * 光纤状态枚举
 */
export enum FiberStatus {
  NORMAL = "normal", // 正常
  WARNING = "warning", // 警告
  ALERT = "alert", // 报警
  OFFLINE = "offline", // 离线
}

/**
 * 光纤配置接口
 */
export interface FiberConfig {
  id: string; // 光纤ID
  name: string; // 光纤名称
  pathPoints: THREE.Vector3[]; // 路径控制点
  status?: FiberStatus; // 光纤状态
  radius?: number; // 光纤半径（米）
  tubularSegments?: number; // 管道分段数
  radialSegments?: number; // 径向分段数
  tension?: number; // 曲线张力（0-1）
  glowIntensity?: number; // 发光强度（0-1）
}

/**
 * 光纤状态颜色配置
 */
const FIBER_STATUS_COLORS: Record<FiberStatus, number> = {
  [FiberStatus.NORMAL]: 0x00ff00, // 绿色 - 正常
  [FiberStatus.WARNING]: 0xffaa00, // 橙色 - 警告
  [FiberStatus.ALERT]: 0xff0000, // 红色 - 报警
  [FiberStatus.OFFLINE]: 0x666666, // 灰色 - 离线
};

/**
 * 光纤线路构建器
 * 使用 TubeGeometry 和 CatmullRomCurve3 创建平滑的光纤线路
 * 支持发光材质和状态指示
 */
export class FiberBuilder {
  /**
   * 构建光纤线路模型
   * @param config 光纤配置参数
   * @returns THREE.Group 包含光纤及其辅助元素的组
   */
  static build(config: FiberConfig): THREE.Group {
    const {
      id,
      name,
      pathPoints,
      status = FiberStatus.NORMAL,
      radius = 0.05,
      tubularSegments = 200,
      radialSegments = 8,
      tension = 0.5,
      glowIntensity = 0.5,
    } = config;

    // 验证路径点
    if (pathPoints.length < 2) {
      throw new Error("Fiber path must have at least 2 points");
    }

    const fiberGroup = new THREE.Group();
    fiberGroup.name = name;
    fiberGroup.userData.clickable = true;
    fiberGroup.userData.fiberInfo = {
      id,
      name,
      status,
      length: this.calculatePathLength(pathPoints),
    };

    // 创建曲线路径
    const curve = new THREE.CatmullRomCurve3(
      pathPoints,
      false,
      "catmullrom",
      tension,
    );
    fiberGroup.userData.pathPoints = pathPoints.map((point) => point.clone());
    fiberGroup.userData.curve = curve;

    // 创建管道几何体
    const geometry = new THREE.TubeGeometry(
      curve,
      tubularSegments,
      radius,
      radialSegments,
      false,
    );

    // 根据状态创建材质
    const material = this.createFiberMaterial(status, glowIntensity);

    // 创建光纤网格
    const fiberMesh = new THREE.Mesh(geometry, material);
    fiberMesh.castShadow = true;
    fiberMesh.receiveShadow = true;
    fiberMesh.name = "fiberCore";

    fiberGroup.add(fiberMesh);
    addPathEffects(
      fiberGroup,
      curve,
      radius * 2.5,
      FIBER_STATUS_COLORS[status],
      tubularSegments,
    );

    // 如果状态异常，添加警示标记
    if (status !== FiberStatus.NORMAL && status !== FiberStatus.OFFLINE) {
      const markers = this.createWarningMarkers(pathPoints, status);
      fiberGroup.add(markers);
    }

    return fiberGroup;
  }

  /**
   * 创建光纤材质
   */
  private static createFiberMaterial(
    status: FiberStatus,
    glowIntensity: number,
  ): THREE.MeshStandardMaterial {
    const color = FIBER_STATUS_COLORS[status];
    const isActive = status !== FiberStatus.OFFLINE;

    const material = new THREE.MeshStandardMaterial({
      color: color,
      emissive: color,
      emissiveIntensity: isActive ? glowIntensity : 0,
      roughness: 0.3,
      metalness: 0.7,
      transparent: true,
      opacity: isActive ? 0.9 : 0.5,
    });

    return material;
  }

  /**
   * 在路径关键点创建标记，动画由场景统一时钟驱动。
   */
  private static createWarningMarkers(
    pathPoints: THREE.Vector3[],
    status: FiberStatus,
  ): THREE.Group {
    const markersGroup = new THREE.Group();
    markersGroup.name = "warningMarkers";

    const color = FIBER_STATUS_COLORS[status];

    // 在起点、中点、终点添加标记
    const keyPoints = [
      pathPoints[0],
      pathPoints[Math.floor(pathPoints.length / 2)],
      pathPoints[pathPoints.length - 1],
    ];

    keyPoints.forEach((point, index) => {
      const marker = createMarker(point, color);
      marker.name = `warningMarker_${index}`;

      markersGroup.add(marker);
    });

    return markersGroup;
  }

  /**
   * 更新光纤状态
   * @param fiberGroup 光纤组
   * @param newStatus 新状态
   * @param glowIntensity 发光强度
   */
  static updateStatus(
    fiberGroup: THREE.Group,
    newStatus: FiberStatus,
    glowIntensity: number = 0.5,
  ): void {
    // 更新用户数据
    if (fiberGroup.userData.fiberInfo) {
      fiberGroup.userData.fiberInfo.status = newStatus;
    }

    // 查找光纤核心网格
    const fiberCore = fiberGroup.getObjectByName("fiberCore") as THREE.Mesh;
    if (fiberCore && fiberCore.material instanceof THREE.MeshStandardMaterial) {
      const color =
        newStatus === FiberStatus.NORMAL && fiberGroup.userData.baseColor
          ? new THREE.Color(fiberGroup.userData.baseColor).getHex()
          : FIBER_STATUS_COLORS[newStatus];
      const isActive = newStatus !== FiberStatus.OFFLINE;

      fiberCore.material.color.setHex(color);
      fiberCore.material.emissive.setHex(color);
      fiberCore.material.emissiveIntensity = isActive ? glowIntensity : 0;
      fiberCore.material.opacity = isActive ? 0.9 : 0.5;
      fiberCore.material.needsUpdate = true;
    }

    const effects = fiberGroup.getObjectByName("pathEffects") as THREE.Mesh<
      THREE.BufferGeometry,
      THREE.ShaderMaterial
    >;
    if (effects)
      effects.material.uniforms.uColor.value.set(
        newStatus === FiberStatus.NORMAL && fiberGroup.userData.baseColor
          ? fiberGroup.userData.baseColor
          : FIBER_STATUS_COLORS[newStatus],
      );

    // 移除旧的警示标记
    const oldMarkers = fiberGroup.getObjectByName("warningMarkers");
    if (oldMarkers) {
      disposeObject(oldMarkers);
    }

    // 如果新状态异常，添加新的警示标记
    if (newStatus !== FiberStatus.NORMAL && newStatus !== FiberStatus.OFFLINE) {
      // 路径在构建时保存，状态切换不改变线路几何。
      const pathPoints = fiberGroup.userData.pathPoints as THREE.Vector3[];
      if (pathPoints) {
        const markers = this.createWarningMarkers(pathPoints, newStatus);
        fiberGroup.add(markers);
      }
    }
  }

  /**
   * 计算路径长度
   */
  private static calculatePathLength(points: THREE.Vector3[]): number {
    let length = 0;
    for (let i = 0; i < points.length - 1; i++) {
      length += points[i].distanceTo(points[i + 1]);
    }
    return length;
  }
}
