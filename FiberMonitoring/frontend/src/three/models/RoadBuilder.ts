import * as THREE from 'three';

/**
 * 道路配置接口
 */
interface RoadConfig {
  roadLength?: number;      // 道路长度（米）
  roadWidth?: number;       // 道路宽度（米）
  laneWidth?: number;       // 车道宽度（米）
  laneCount?: number;       // 车道数量
  hasSidewalk?: boolean;    // 是否包含人行道
  sidewalkWidth?: number;   // 人行道宽度（米）
  hasMedianStrip?: boolean; // 是否包含中央绿化带
  medianStripWidth?: number;// 中央绿化带宽度（米）
}

/**
 * 道路模型构建器
 * 创建完整的道路模型，包括路面、车道标线、人行道和中央绿化带
 */
export class RoadBuilder {
  /**
   * 构建道路模型
   * @param config 道路配置参数
   * @returns THREE.Group 包含所有道路元素的组
   */
  static build(config: RoadConfig = {}): THREE.Group {
    const {
      roadLength = 800,
      roadWidth = 40,
      laneWidth = 3.5,
      laneCount = 6,
      hasSidewalk = true,
      sidewalkWidth = 3,
      hasMedianStrip = true,
      medianStripWidth = 4,
    } = config;

    const roadGroup = new THREE.Group();
    roadGroup.name = 'road';
    roadGroup.userData.clickable = true;

    // 1. 创建主路面（沥青材质）
    const roadSurface = this.createRoadSurface(roadLength, roadWidth);
    roadGroup.add(roadSurface);

    // 2. 创建车道标线
    const laneMarkings = this.createLaneMarkings(
      roadLength,
      roadWidth,
      laneWidth,
      laneCount,
      medianStripWidth
    );
    roadGroup.add(laneMarkings);

    // 3. 创建人行道
    if (hasSidewalk) {
      const leftSidewalk = this.createSidewalk(
        roadLength,
        sidewalkWidth,
        -roadWidth / 2 - sidewalkWidth / 2
      );
      const rightSidewalk = this.createSidewalk(
        roadLength,
        sidewalkWidth,
        roadWidth / 2 + sidewalkWidth / 2
      );
      roadGroup.add(leftSidewalk, rightSidewalk);
    }

    // 4. 创建中央绿化带
    if (hasMedianStrip) {
      const medianStrip = this.createMedianStrip(roadLength, medianStripWidth);
      roadGroup.add(medianStrip);
    }

    return roadGroup;
  }

  /**
   * 创建路面
   */
  private static createRoadSurface(length: number, width: number): THREE.Mesh {
    const geometry = new THREE.PlaneGeometry(width, length);

    // 沥青材质 - 深灰色带轻微粗糙度
    const material = new THREE.MeshPhysicalMaterial({
      color: 0x2a2a2a,
      roughness: 0.9,
      metalness: 0.1,
      clearcoat: .65,
      clearcoatRoughness: .22,
    });

    const surface = new THREE.Mesh(geometry, material);
    surface.rotation.x = -Math.PI / 2; // 水平放置
    surface.position.y = 0.01; // 略高于地面，避免z-fighting
    surface.receiveShadow = true;
    surface.name = 'roadSurface';

    return surface;
  }

  /**
   * 创建车道标线
   */
  private static createLaneMarkings(
    length: number,
    _roadWidth: number,
    laneWidth: number,
    laneCount: number,
    medianStripWidth: number
  ): THREE.Group {
    const markingsGroup = new THREE.Group();
    markingsGroup.name = 'laneMarkings';

    const lineWidth = 0.15; // 标线宽度
    const lineHeight = 0.06; // 与沥青面留足深度间隔，避免远景闪烁
    const dashLength = 6; // 虚线段长度
    const gapLength = 9; // 虚线间隙长度

    // 白色标线材质
    const whiteMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff });

    // 黄色实线材质（用于中央分隔线）
    const yellowMaterial = new THREE.MeshBasicMaterial({ color: 0xffd700 });

    // 计算左右两侧的车道数
    const lanesPerSide = Math.floor(laneCount / 2);
    const halfMedian = medianStripWidth / 2;

    // 左侧车道标线（从中央绿化带向外）
    for (let i = 0; i <= lanesPerSide; i++) {
      const xPos = -halfMedian - i * laneWidth;

      if (i === 0) {
        // 中央分隔线 - 黄色实线
        const solidLine = this.createSolidLine(length, lineWidth, yellowMaterial);
        solidLine.position.set(xPos, lineHeight, 0);
        markingsGroup.add(solidLine);
      } else if (i === lanesPerSide) {
        // 路边实线
        const solidLine = this.createSolidLine(length, lineWidth, whiteMaterial);
        solidLine.position.set(xPos, lineHeight, 0);
        markingsGroup.add(solidLine);
      } else {
        // 车道分隔虚线
        const dashedLine = this.createDashedLine(
          length,
          lineWidth,
          dashLength,
          gapLength,
          whiteMaterial
        );
        dashedLine.position.set(xPos, lineHeight, 0);
        markingsGroup.add(dashedLine);
      }
    }

    // 右侧车道标线
    for (let i = 0; i <= lanesPerSide; i++) {
      const xPos = halfMedian + i * laneWidth;

      if (i === 0) {
        // 中央分隔线 - 黄色实线
        const solidLine = this.createSolidLine(length, lineWidth, yellowMaterial);
        solidLine.position.set(xPos, lineHeight, 0);
        markingsGroup.add(solidLine);
      } else if (i === lanesPerSide) {
        // 路边实线
        const solidLine = this.createSolidLine(length, lineWidth, whiteMaterial);
        solidLine.position.set(xPos, lineHeight, 0);
        markingsGroup.add(solidLine);
      } else {
        // 车道分隔虚线
        const dashedLine = this.createDashedLine(
          length,
          lineWidth,
          dashLength,
          gapLength,
          whiteMaterial
        );
        dashedLine.position.set(xPos, lineHeight, 0);
        markingsGroup.add(dashedLine);
      }
    }

    return markingsGroup;
  }

  /**
   * 创建实线
   */
  private static createSolidLine(
    length: number,
    width: number,
    material: THREE.Material
  ): THREE.Mesh {
    const geometry = new THREE.PlaneGeometry(width, length);
    const line = new THREE.Mesh(geometry, material);
    line.rotation.x = -Math.PI / 2;
    return line;
  }

  /**
   * 创建虚线
   */
  private static createDashedLine(
    totalLength: number,
    width: number,
    dashLength: number,
    gapLength: number,
    material: THREE.Material
  ): THREE.Group {
    const dashedGroup = new THREE.Group();
    const segmentLength = dashLength + gapLength;
    const segmentCount = Math.floor(totalLength / segmentLength);

    const geometry = new THREE.PlaneGeometry(width, dashLength);

    for (let i = 0; i < segmentCount; i++) {
      const dash = new THREE.Mesh(geometry, material);
      dash.rotation.x = -Math.PI / 2;
      dash.position.z = -totalLength / 2 + i * segmentLength + dashLength / 2;
      dashedGroup.add(dash);
    }

    return dashedGroup;
  }

  /**
   * 创建人行道
   */
  private static createSidewalk(
    length: number,
    width: number,
    xPosition: number
  ): THREE.Mesh {
    const geometry = new THREE.BoxGeometry(width, 0.2, length);

    // 浅灰色水泥材质
    const material = new THREE.MeshStandardMaterial({
      color: 0x8a8a8a,
      roughness: 0.8,
      metalness: 0.0,
    });

    const sidewalk = new THREE.Mesh(geometry, material);
    sidewalk.position.set(xPosition, 0.1, 0);
    sidewalk.receiveShadow = true;
    sidewalk.castShadow = true;
    sidewalk.name = 'sidewalk';
    sidewalk.userData.clickable = true;

    return sidewalk;
  }

  /**
   * 创建中央绿化带
   */
  private static createMedianStrip(length: number, width: number): THREE.Mesh {
    const geometry = new THREE.BoxGeometry(width, 0.15, length);

    // 绿色植被材质
    const material = new THREE.MeshStandardMaterial({
      color: 0x3a5c37,
      roughness: 0.95,
      metalness: 0.0,
    });

    const medianStrip = new THREE.Mesh(geometry, material);
    medianStrip.position.set(0, 0.075, 0);
    medianStrip.receiveShadow = true;
    medianStrip.castShadow = true;
    medianStrip.name = 'medianStrip';
    medianStrip.userData.clickable = true;

    return medianStrip;
  }
}
