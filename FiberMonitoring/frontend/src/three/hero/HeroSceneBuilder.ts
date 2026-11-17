import * as THREE from "three";
import type { SceneManager } from "../core/SceneManager";
import type { useMonitoringStore } from "@/stores/monitoring";
import { VehicleType } from "@/types/monitoring";
import { RoadBuilder } from "../models/RoadBuilder";
import { buildGeology } from "../engineering/GeologyBuilder";
import { buildRockBed } from "../engineering/RockBedBuilder";
import { buildMonitoringHardware } from "../engineering/MonitoringHardware";
import { buildDetailedVehicle } from "../engineering/DetailedVehicleBuilder";
import { createSurfaceTexture } from "../engineering/SurfaceTextures";
import {
  toDisplay,
  GEOLOGY,
  DISPLAY,
  chainagePoint,
  displayLength,
} from "../engineering/layout";
import { addBoundary, createMarker, emphasizeMarker } from "../effects/PathEffects";
import { buildHeroEnvironment } from "./HeroEnvironment";
import { buildHeroSewer } from "./HeroSewer";
import { buildHeroRoadDetails } from "./HeroRoadDetails";
import { addHeroFibers } from "./HeroFibers";
import { HERO, insideHero } from "./config";
import { createRoadReflection } from '../engineering/RoadReflection';

type Store = ReturnType<typeof useMonitoringStore>;
function addRoad(manager: SceneManager): void {
  const road = RoadBuilder.build({
    roadLength: displayLength,
    roadWidth: 32,
    laneWidth: (32-DISPLAY.roadMedian)/6,
    laneCount: 6,
    sidewalkWidth: 4,
    medianStripWidth: DISPLAY.roadMedian,
  });
  road.rotation.y = Math.PI / 2;
  road.name = "road";
  const surface = road.getObjectByName("roadSurface") as THREE.Mesh<
    THREE.BufferGeometry,
    THREE.MeshStandardMaterial
  >;
  surface.material.map = createSurfaceTexture("asphalt");
  surface.material.color.setHex(0x5a6065);
  road.add(createRoadReflection(displayLength,32));
  manager.heroRoadGroup.add(
    road,
    buildHeroRoadDetails(),
    buildMonitoringHardware(),
  );
}
function addVehicles(manager: SceneManager): void {
  const vehicles = [
    { x: -4, z: 8.5, type: VehicleType.TRUCK, color: 0xce252d },
    { x: -20, z: 13.5, type: VehicleType.SEDAN, color: 0xe9edf0 },
    { x: 12, z: 8.5, type: VehicleType.BUS, color: 0xe0e7e5 },
    { x: 26, z: 13.5, type: VehicleType.SEDAN, color: 0x18374a },
  ];
  vehicles.forEach((vehicle) =>
    manager.vehicleGroup.add(
      buildDetailedVehicle({
        vehicleType: vehicle.type,
        color: vehicle.color,
        position: new THREE.Vector3(vehicle.x, 0.12, vehicle.z),
        rotation: vehicle.z > 0 ? Math.PI / 2 : -Math.PI / 2,
        scale: vehicle.type === VehicleType.SEDAN ? 1.9 : vehicle.type === VehicleType.TRUCK ? 1.55 : 1.45,
      }),
    ),
  );
}
function addMarkers(manager: SceneManager, store: Store): void {
  store.devices
    .filter((device) => device.position && insideHero(device.position))
    .forEach((device) => {
      const marker = createMarker(
        toDisplay(device.position!),
        device.online ? 0x55edb1 : 0x75808d,
      );
      marker.name = device.deviceId;
      Object.assign(marker.userData, {
        deviceId: device.deviceId,
        deviceType: device.deviceType,
        clickable: true,
        active: device.online,
      });
      manager.markerGroup.add(marker);
    });
  // 展示区内的里程监测锚点，保留关联 fiberId，后续可由设备数据替换。
  for (const chainage of [325, 360, 385]) {
    const position = chainagePoint(chainage, 1.1, 18.3),
      marker = createMarker(position, 0x3eebad);
    marker.name = `监测点 K0+${chainage}`;
    Object.assign(marker.userData, {
      clickable: true,
      chainage,
      fiberId: "FIBER-DAS-001",
      monitoringAnchor: true,
    });
    manager.markerGroup.add(marker);
    if (chainage === 360) {
      emphasizeMarker(marker,0x3eebad);
      manager.annotations.add(
        marker.name,
        marker.position,
        marker,
        "green",
        -40,
      );
    }
  }
}
function addAnnotations(manager: SceneManager): void {
  GEOLOGY.forEach((layer, index) =>
    manager.annotations.add(
      layer.name,
      new THREE.Vector3(
        -displayLength * .43,
        -(layer.depth + layer.thickness * 0.5) * DISPLAY.depth,
        HERO.excavationZ,
      ),
      manager.geologyGroup,
      "soil",
      0,
      0,
      { dock: 'left', rank: index },
    ),
  );
  manager.annotations.add(
    "排污管道 · 检修观察窗",
    new THREE.Vector3(8, -6.4 * DISPLAY.depth, 21),
    manager.sewerGroup,
    "cyan",
    25,
    0,
    { dock: 'bottom' },
  );
}
export async function buildHeroScene(
  manager: SceneManager,
  store: Store,
): Promise<void> {
  manager.envGroup.add(buildHeroEnvironment());
  addRoad(manager);
  manager.geologyGroup.add(buildGeology(), buildRockBed());
  manager.sewerGroup.add(buildHeroSewer());
  addHeroFibers(manager, store.fibers);
  addVehicles(manager);
  addMarkers(manager, store);
  addAnnotations(manager);
  addBoundary(
    manager.effectGroup,
    new THREE.Box3(
      new THREE.Vector3(-displayLength/2, HERO.baseY, -20),
      new THREE.Vector3(displayLength/2, 0, HERO.excavationZ),
    ),
    1.2,
    0x5ba9ce,
  );
  manager.syncMonitoring(store.fibers, store.devices, store.events);
  manager.effectGroup.children.forEach(effect=>{effect.userData.ownerLayer='geologyGroup'});
  manager.frameEngineeringModels();
}
