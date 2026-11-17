import * as THREE from "three";
import { addPathEffects } from "../effects/PathEffects";

/**
 * 管道配置接口
 */
interface PipeConfig {
  diameter: number; // 管道直径（米）
  startPosition: THREE.Vector3; // 起始位置
  endPosition: THREE.Vector3; // 终止位置
  pipeType?: "water" | "gas" | "electric" | "sewage" | "other"; // 管道类型
  material?: "steel" | "pvc" | "concrete" | "copper"; // 管道材质
  color?: number; // 自定义颜色
  segments?: number; // 圆柱分段数（影响圆滑度）
  name?: string; // 管道名称
}

/**
 * 管道类型默认颜色配置
 */
const PIPE_TYPE_COLORS: Record<string, number> = {
  water: 0x4a90e2, // 蓝色 - 给水管
  gas: 0xf5a623, // 黄色 - 燃气管
  electric: 0xe74c3c, // 红色 - 电力管
  sewage: 0x7f8c8d, // 灰色 - 排污管
  other: 0x95a5a6, // 浅灰 - 其他
};

/**
 * 管道材质纹理配置
 */
const MATERIAL_PROPERTIES: Record<
  string,
  { roughness: number; metalness: number }
> = {
  steel: { roughness: 0.4, metalness: 0.8 },
  pvc: { roughness: 0.6, metalness: 0.1 },
  concrete: { roughness: 0.9, metalness: 0.0 },
  copper: { roughness: 0.3, metalness: 0.9 },
};

/**
 * 管道模型构建器
 * 创建圆柱形管道，支持点击高亮和多种材质
 */
export class PipeBuilder {
  /**
   * 构建管道模型
   * @param config 管道配置参数
   * @returns THREE.Group 包含管道及其端盖的组
   */
  static build(config: PipeConfig): THREE.Group {
    const {
      diameter,
      startPosition,
      endPosition,
      pipeType = "other",
      material = "steel",
      color,
      segments = 32,
      name = `pipe_${pipeType}`,
    } = config;

    const pipeGroup = new THREE.Group();
    pipeGroup.name = name;
    pipeGroup.userData.clickable = true;
    pipeGroup.userData.pipeInfo = {
      diameter,
      pipeType,
      material,
      length: startPosition.distanceTo(endPosition),
    };

    // 计算管道长度和方向
    const length = startPosition.distanceTo(endPosition);
    const direction = new THREE.Vector3()
      .subVectors(endPosition, startPosition)
      .normalize();

    // 确定管道颜色
    const pipeColor =
      color ?? PIPE_TYPE_COLORS[pipeType] ?? PIPE_TYPE_COLORS.other;

    // 创建主管道
    const pipe = this.createPipeCylinder(
      diameter,
      length,
      pipeColor,
      material,
      segments,
    );
    pipeGroup.add(pipe);
    // Local Z is the existing pipe axis; the parent quaternion handles arbitrary endpoints.
    const curve = new THREE.LineCurve3(
      new THREE.Vector3(0, 0, -length / 2),
      new THREE.Vector3(0, 0, length / 2),
    );
    addPathEffects(pipeGroup, curve, diameter / 2 + 0.025, 0x65bff5, 240, 64);
    pipeGroup.getObjectByName("pathEffects")!.userData.scanOnly = true;

    // 创建端盖（两端封闭）
    const startCap = this.createPipeCap(
      diameter,
      pipeColor,
      material,
      segments,
    );
    const endCap = this.createPipeCap(diameter, pipeColor, material, segments);

    startCap.position.z = -length / 2;
    endCap.position.z = length / 2;
    endCap.rotation.y = Math.PI; // 翻转端盖方向

    pipeGroup.add(startCap, endCap);

    // 定位和旋转管道组
    this.positionAndOrientPipe(
      pipeGroup,
      startPosition,
      endPosition,
      direction,
    );

    return pipeGroup;
  }

  /**
   * 创建管道圆柱体
   */
  private static createPipeCylinder(
    diameter: number,
    length: number,
    color: number,
    materialType: string,
    segments: number,
  ): THREE.Mesh {
    const radius = diameter / 2;
    const geometry = new THREE.CylinderGeometry(
      radius,
      radius,
      length,
      segments,
      1,
      true,
    );

    // 旋转几何体使其沿Z轴（默认圆柱沿Y轴）
    geometry.rotateX(Math.PI / 2);

    const materialProps =
      MATERIAL_PROPERTIES[materialType] || MATERIAL_PROPERTIES.steel;

    const material = new THREE.MeshStandardMaterial({
      color: color,
      roughness: materialProps.roughness,
      metalness: materialProps.metalness,
      side: THREE.DoubleSide,
    });

    const pipe = new THREE.Mesh(geometry, material);
    pipe.castShadow = true;
    pipe.receiveShadow = true;
    pipe.name = "pipeCylinder";

    return pipe;
  }

  /**
   * 创建管道端盖
   */
  private static createPipeCap(
    diameter: number,
    color: number,
    materialType: string,
    segments: number,
  ): THREE.Mesh {
    const radius = diameter / 2;
    const geometry = new THREE.CircleGeometry(radius, segments);

    const materialProps =
      MATERIAL_PROPERTIES[materialType] || MATERIAL_PROPERTIES.steel;

    const material = new THREE.MeshStandardMaterial({
      color: color,
      roughness: materialProps.roughness,
      metalness: materialProps.metalness,
    });

    const cap = new THREE.Mesh(geometry, material);
    cap.castShadow = true;
    cap.receiveShadow = true;

    return cap;
  }

  /**
   * 定位和旋转管道
   */
  private static positionAndOrientPipe(
    pipeGroup: THREE.Group,
    startPosition: THREE.Vector3,
    endPosition: THREE.Vector3,
    direction: THREE.Vector3,
  ): void {
    // 设置管道中心位置
    const center = new THREE.Vector3()
      .addVectors(startPosition, endPosition)
      .multiplyScalar(0.5);
    pipeGroup.position.copy(center);

    // 计算旋转
    const up = new THREE.Vector3(0, 0, 1); // 默认方向是Z轴
    const quaternion = new THREE.Quaternion();
    quaternion.setFromUnitVectors(up, direction);
    pipeGroup.quaternion.copy(quaternion);
  }
}
