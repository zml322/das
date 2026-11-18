import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import {
  VisualClock,
  defaultVisualState,
  updateVisuals,
  disposeObject,
  type VisualState,
} from "../effects/PathEffects";
import { syncSceneMonitoring } from "./MonitoringSceneSync";
import { SceneAnnotations } from "../engineering/SceneAnnotations";
import { setupEngineeringLighting } from "../engineering/SceneLighting";
import {
  HeroCameraController,
  type HeroView,
} from "../hero/HeroCameraController";
import { createHeroGroups } from "../hero/HeroGroups";
import type { Fiber, Device, MonitoringEvent } from "@/types/monitoring";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Reflector } from 'three/examples/jsm/objects/Reflector.js';
import { invalidateRoadReflection } from '../engineering/RoadReflection';
/**
 * Three.js 场景管理器
 * 负责场景初始化、渲染循环、交互控制
 */
export class SceneManager {
  public annotations: SceneAnnotations;
  private container: HTMLElement;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls;
  private cameraController: HeroCameraController;
  private raycaster: THREE.Raycaster;
  private mouse: THREE.Vector2;
  private animationId: number | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private visualState = defaultVisualState();
  private effectClock = new VisualClock();
  private lastFrame = 0;
  private disposed = false;
  private viewportWidth = 0;
  private viewportHeight = 0;
  private resizePending = false;
  private environmentTarget?: THREE.WebGLRenderTarget;
  private clickHandler = (event: MouseEvent) => this.onMouseClick(event);
  private moveHandler = (event: MouseEvent) => this.onMouseMove(event);
  public envGroup: THREE.Group;
  public heroRoadGroup: THREE.Group;
  public geologyGroup: THREE.Group;
  public sewerGroup: THREE.Group;
  public effectGroup: THREE.Group;
  public roadGroup: THREE.Group;
  public undergroundGroup: THREE.Group;
  public pipeGroup: THREE.Group;
  public fiberGroup: THREE.Group;
  public vehicleGroup: THREE.Group;
  public markerGroup: THREE.Group;
  private onObjectClickCallback?: (object: THREE.Object3D) => void;
  private onObjectHoverCallback?: (object: THREE.Object3D | null) => void;
  constructor(container: HTMLElement) {
    this.container = container;
    this.annotations = new SceneAnnotations(container);
    this.mouse = new THREE.Vector2();
    this.raycaster = new THREE.Raycaster();
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0e1a);
    this.scene.fog = new THREE.Fog(0x0a0e1a, 800, 2000);
    this.camera = new THREE.PerspectiveCamera(
      40, // 城市与地下剖面的展示机位，兼顾道路和管口的透视。
      container.clientWidth / container.clientHeight,
      1,
      1200,
    );
    this.camera.position.set(-200, 150, 250);
    this.camera.lookAt(0, -5, 0); // 看向地下区域
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      // Qt WebEngine can composite DOM changes between our throttled WebGL frames.
      // Keep the last completed image available until the next render replaces it.
      preserveDrawingBuffer: true,
      powerPreference: "high-performance",
    });
    this.renderer.setClearAlpha(1);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    this.handleResize();
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.localClippingEnabled = true;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    const environment = new RoomEnvironment();
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.environmentTarget = pmrem.fromScene(environment, 0.04);
    this.scene.environment = this.environmentTarget.texture;
    environment.dispose();
    pmrem.dispose();
    container.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.minDistance = 25;
    this.controls.maxDistance = 250;
    this.controls.minPolarAngle = 0.01;
    this.controls.enablePan = true;
    this.controls.screenSpacePanning = false;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.04; // 保持在观察目标上方，避免翻到底部。
    this.controls.target.set(0, -5, 0); // 控制器焦点在地下
    const groups = createHeroGroups(this.scene);
    this.envGroup = groups.envGroup;
    this.heroRoadGroup = this.roadGroup = groups.heroRoadGroup;
    this.geologyGroup = this.undergroundGroup = groups.geologyGroup;
    this.sewerGroup = this.pipeGroup = groups.sewerGroup;
    this.fiberGroup = groups.fiberGroup;
    this.vehicleGroup = groups.vehicleGroup;
    this.markerGroup = groups.markerGroup;
    this.effectGroup = groups.effectGroup;
    this.cameraController = new HeroCameraController(
      this.camera,
      this.controls,
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    );
    setupEngineeringLighting(this.scene);
    this.setupEventListeners();
    this.animate();
    this.setupResizeObserver();
  }
  private setupEventListeners(): void {
    this.renderer.domElement.addEventListener("click", this.clickHandler);
    this.renderer.domElement.addEventListener("mousemove", this.moveHandler);
  }
  private setupResizeObserver(): void {
    this.resizeObserver = new ResizeObserver(() => {
      // setSize clears the drawing buffer. Resize and redraw in the same callback,
      // rather than exposing a cleared canvas while waiting for the next frame.
      this.resizePending = true;
    });
    this.resizeObserver.observe(this.container);
  }
  private handleResize(): void {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (width < 1 || height < 1) return;
    if (width === this.viewportWidth && height === this.viewportHeight) return;
    this.viewportWidth = width;
    this.viewportHeight = height;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
  }
  private onMouseClick(event: MouseEvent): void {
    this.updateMousePosition(event);
    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster
      .intersectObjects(this.scene.children, true)
      .filter((hit) => {
        let object: THREE.Object3D | null = hit.object;
        while (object) {
          if (!object.visible) return false;
          object = object.parent;
        }
        return true;
      });
    if (intersects.length > 0) {
      let object = intersects[0].object;
      while (object.parent && !object.userData.clickable) {
        object = object.parent;
      }
      if (object.userData.clickable && this.onObjectClickCallback) {
        this.onObjectClickCallback(object);
      }
    }
  }
  private onMouseMove(event: MouseEvent): void {
    this.updateMousePosition(event);
    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster
      .intersectObjects(this.scene.children, true)
      .filter((hit) => {
        let object: THREE.Object3D | null = hit.object;
        while (object) {
          if (!object.visible) return false;
          object = object.parent;
        }
        return true;
      });
    if (intersects.length > 0 && this.onObjectHoverCallback) {
      let object = intersects[0].object;
      while (
        object.parent &&
        !object.userData.hoverable &&
        !object.userData.clickable
      ) {
        object = object.parent;
      }
      if (object.userData.hoverable || object.userData.clickable) {
        this.onObjectHoverCallback(object);
        this.renderer.domElement.style.cursor = "pointer";
        return;
      }
    }
    if (this.onObjectHoverCallback) {
      this.onObjectHoverCallback(null);
    }
    this.renderer.domElement.style.cursor = "default";
  }
  private updateMousePosition(event: MouseEvent): void {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  }
  private animate = (): void => {
    if (this.disposed) return;
    this.animationId = requestAnimationFrame(this.animate);
    this.renderFrame(performance.now());
  };
  private renderFrame(now: number): void {
    if (document.hidden || now - this.lastFrame < 1000 / 30) return;
    const delta = this.lastFrame
      ? Math.min((now - this.lastFrame) / 1000, 0.1)
      : 0;
    this.lastFrame = now;
    if (this.resizePending) {
      this.resizePending = false;
      this.handleResize();
    }
    this.effectClock.advance(delta, this.visualState, document.hidden);
    updateVisuals(this.scene, this.effectClock.time, this.visualState);
    this.cameraController.update(delta);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.annotations.update(
      this.camera,
      this.container.clientWidth,
      this.container.clientHeight,
    );
  }
  setVisualState(patch: Partial<VisualState>): void {
    this.visualState = { ...this.visualState, ...patch };
    this.visualState.speed = Math.max(0, Math.min(3, this.visualState.speed));
    if (patch.playback === "stopped") this.effectClock.time = 0;
    this.scene.environment = this.visualState.reflection
      ? this.environmentTarget!.texture
      : null;
    updateVisuals(this.scene, this.effectClock.time, this.visualState);
  }
  setDaylightEnvironment(texture: THREE.DataTexture): void {
    texture.mapping = THREE.EquirectangularReflectionMapping;
    // HDR supplies reflections and indirect light; retain the art-directed blue sky.
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.environmentTarget?.dispose();
    this.environmentTarget = pmrem.fromEquirectangular(texture);
    texture.dispose();
    this.scene.environment = this.visualState.reflection
      ? this.environmentTarget.texture
      : null;
    pmrem.dispose();
  }
  frameEngineeringModels(): void {
    this.scene.traverse((object) => {
      if (
        object instanceof THREE.Mesh &&
        object.material instanceof THREE.MeshStandardMaterial
      )
        object.material.envMapIntensity = 0.35;
    });
    this.cameraController.setView("overview", false);
    this.renderer.shadowMap.autoUpdate = false;
    this.renderer.shadowMap.needsUpdate = true;
  }
  syncMonitoring(
    fibers: Fiber[],
    devices: Device[],
    events: MonitoringEvent[],
  ): void {
    syncSceneMonitoring(this, this.annotations, fibers, devices, events);
  }
  onObjectClick(callback: (object: THREE.Object3D) => void): void {
    this.onObjectClickCallback = callback;
  }
  onObjectHover(callback: (object: THREE.Object3D | null) => void): void {
    this.onObjectHoverCallback = callback;
  }
  toggleLayer(layerName: string, visible: boolean): void {
    const layerMap: Record<string, THREE.Group> = {
      env: this.envGroup,
      envGroup: this.envGroup,
      heroRoadGroup: this.heroRoadGroup,
      geologyGroup: this.geologyGroup,
      sewerGroup: this.sewerGroup,
      effect: this.effectGroup,
      effectGroup: this.effectGroup,
      fiberGroup: this.fiberGroup,
      vehicleGroup: this.vehicleGroup,
      markerGroup: this.markerGroup,
      road: this.roadGroup,
      underground: this.undergroundGroup,
      pipe: this.pipeGroup,
      fiber: this.fiberGroup,
      vehicle: this.vehicleGroup,
      marker: this.markerGroup,
    };
    const group = layerMap[layerName];
    if (group) {
      group.visible = visible;
      if (layerName === "road") this.envGroup.visible = visible;
      this.renderer.shadowMap.needsUpdate = true;
      invalidateRoadReflection(this.scene);
    }
  }
  setUndergroundOpacity(opacity: number): void {
    this.undergroundGroup.traverse((child) => {
      if (child instanceof THREE.Mesh && child.material) {
        if (
          child.material instanceof THREE.ShaderMaterial &&
          child.material.uniforms.uOpacity
        ) {
          child.material.uniforms.uOpacity.value = 0.2 * opacity;
          return;
        }
        if (Array.isArray(child.material)) {
          child.material.forEach((mat) => {
            mat.transparent = opacity < 1;
            mat.opacity = opacity;
            mat.depthWrite = opacity >= 1;
            mat.needsUpdate = true;
          });
        } else {
          child.material.transparent = opacity < 1;
          child.material.opacity = opacity;
          child.material.depthWrite = opacity >= 1;
          child.material.needsUpdate = true;
        }
      }
    });
  }
  focusOnObject(object: THREE.Object3D, distance = 45): void {
    this.cameraController.focus(object, distance);
  }
  setViewPreset(preset: HeroView): void {
    this.cameraController.setView(preset);
  }
  getScene(): THREE.Scene {
    return this.scene;
  }
  getCamera(): THREE.PerspectiveCamera {
    return this.camera;
  }
  getRenderer(): THREE.WebGLRenderer {
    return this.renderer;
  }
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.animationId !== null) {
      cancelAnimationFrame(this.animationId);
    }
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
    this.renderer.domElement.removeEventListener("click", this.clickHandler);
    this.renderer.domElement.removeEventListener("mousemove", this.moveHandler);
    this.annotations.dispose();
    if (this.scene.background instanceof THREE.Texture)
      this.scene.background.dispose();
    this.environmentTarget?.dispose();
    this.scene.traverse(object=>{if(object instanceof Reflector)object.dispose()});
    disposeObject(this.scene);
    this.renderer.dispose();
    this.cameraController.dispose();
    this.controls.dispose();
    if (this.container.contains(this.renderer.domElement)) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}
