import * as THREE from 'three'

// All time comes from SceneManager. No independent RAF, timers, React or texture assets.
export interface VisualState {
  playback: 'running' | 'paused' | 'stopped'
  flow: boolean
  scan: boolean
  markers: boolean
  boundary: boolean
  reflection: boolean
  speed: number
}
export const defaultVisualState = (): VisualState => ({
  playback: 'running', flow: true, scan: true, markers: true,
  boundary: true, reflection: true, speed: 1
})

export class VisualClock {
  time = 0
  advance(delta: number, state: VisualState, hidden = false): number {
    if (state.playback === 'stopped') this.time = 0
    if (state.playback === 'running' && !hidden) this.time += Math.min(Math.max(delta,0),0.1)*state.speed
    return this.time
  }
}

export function disposeObject(root: THREE.Object3D): void {
  const textures = new Set<THREE.Texture>()
  root.traverse(object => {
    const drawable = object as THREE.Mesh
    drawable.geometry?.dispose()
    if (drawable.material) {
      const materials = Array.isArray(drawable.material) ? drawable.material : [drawable.material]
      materials.forEach(material => {
        Object.values(material).forEach(value => { if (value instanceof THREE.Texture) textures.add(value) })
        material.dispose()
      })
    }
  })
  textures.forEach(texture => texture.dispose())
  root.removeFromParent()
}

/** A TubeGeometry uses getPointAt internally: uv.x therefore measures arc length.
 * The scan and luminous packets share exactly the same centerline as the solid cable.
 * Open routes fade at both endpoints instead of drawing a closing segment.
 */
export function addPathEffects(
  parent: THREE.Group, curve: THREE.Curve<THREE.Vector3>, radius: number,
  color: THREE.ColorRepresentation, segments = 240, radialSegments = 8
): void {
  const length = Math.max(curve.getLength(), 0.001)
  const material = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 }, uLength: { value: length },
      uColor: { value: new THREE.Color(color) },
      uFlow: { value: 1 }, uScan: { value: 1 }
    },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader: `uniform float uTime,uLength,uFlow,uScan;
      uniform vec3 uColor; varying vec2 vUv;
      void main(){
        float s=vUv.x*uLength;
        float packet=fract((s-uTime*18.0)/42.0);
        float trail=pow(smoothstep(0.62,0.96,packet),2.0)*(1.0-smoothstep(0.96,1.0,packet));
        float head=mod(uTime*28.0,uLength+24.0)-12.0;
        float band=pow(max(0.0,1.0-abs(s-head)/12.0),2.0);
        float ends=smoothstep(0.0,1.0,s)*smoothstep(0.0,1.0,uLength-s);
        float strength=ends*(trail*uFlow*0.85+band*uScan*0.65);
        if(strength<0.005) discard;
        gl_FragColor=vec4(uColor*(1.0+strength),min(strength,0.85));
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    transparent: true, blending: THREE.AdditiveBlending,
    depthWrite: false, depthTest: true
  })
  const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, segments, radius, radialSegments, false), material)
  mesh.name = 'pathEffects'
  mesh.userData.visualEffect = 'path'
  mesh.raycast = () => {} // Solid geometry remains the picking target.
  parent.add(mesh)
}

export function createMarker(position: THREE.Vector3, color: THREE.ColorRepresentation): THREE.Group {
  const group = new THREE.Group()
  group.position.copy(position)
  group.userData.visualEffect = 'marker'
  const cone = new THREE.Mesh(new THREE.ConeGeometry(0.65, 1.8, 4),
    new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.5, roughness: 0.4 }))
  cone.rotation.z = Math.PI
  cone.position.y = 2
  cone.name = 'markerCone'
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.8, 1.05, 40),
    new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, transparent: true, opacity: 0.65, depthWrite: false }))
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.15
  ring.name = 'markerRing'
  const anchor = new THREE.Mesh(new THREE.SphereGeometry(0.28, 12, 8), new THREE.MeshBasicMaterial({ color }))
  group.add(cone, ring, anchor)
  return group
}

/** Camera-facing concentric rings identify the labelled alarm/monitoring anchors. */
export function emphasizeMarker(group: THREE.Object3D, color: THREE.ColorRepresentation): void {
  if (group.getObjectByName('markerHalo')) return
  const canvas=document.createElement('canvas');canvas.width=canvas.height=256
  const ctx=canvas.getContext('2d')!
  if(ctx.createRadialGradient){
    const glow=ctx.createRadialGradient(128,128,0,128,128,125)
    glow.addColorStop(0,'rgba(255,255,255,1)');glow.addColorStop(.09,'rgba(255,255,255,.95)')
    glow.addColorStop(.2,'rgba(255,255,255,.15)');glow.addColorStop(.6,'rgba(255,255,255,.04)');glow.addColorStop(1,'rgba(255,255,255,0)')
    ctx.fillStyle=glow;ctx.fillRect(0,0,256,256)
    for(const radius of [49]){
      ctx.strokeStyle='rgba(255,255,255,'+(.65-radius*.004)+')';ctx.lineWidth=2
      ctx.beginPath();ctx.arc(128,128,radius,0,Math.PI*2);ctx.stroke()
    }
  }
  const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace
  const halo=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,color,transparent:true,opacity:.65,depthWrite:false,toneMapped:false,blending:THREE.AdditiveBlending}))
  halo.name='markerHalo';halo.scale.setScalar(2.6);group.add(halo)
  group.getObjectByName('markerCone')!.visible=false
}

/** Four real vertical faces around a model-derived footprint. Y is the up axis. */
export function addBoundary(parent: THREE.Group, box: THREE.Box3, height: number, color: number): void {
  if (box.isEmpty()) return
  const { min, max } = box
  const vertices: number[] = [], uv: number[] = []
  const corners = [[min.x,min.z],[max.x,min.z],[max.x,max.z],[min.x,max.z]]
  for (let i=0;i<4;i++) {
    const a=corners[i], b=corners[(i+1)%4]
    for (const [x,z,h] of [[a[0],a[1],0],[b[0],b[1],0],[b[0],b[1],1],
      [a[0],a[1],0],[b[0],b[1],1],[a[0],a[1],1]]) {
      vertices.push(x,min.y+h*height,z); uv.push(0,h)
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3))
  geometry.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2))
  const material = new THREE.ShaderMaterial({
    uniforms: { uColor: {value:new THREE.Color(color)}, uOpacity:{value:0.2} },
    vertexShader: `varying float vHeight; void main(){vHeight=uv.y;
      gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `uniform vec3 uColor; uniform float uOpacity; varying float vHeight;
      void main(){gl_FragColor=vec4(uColor,pow(1.0-vHeight,1.8)*uOpacity);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
      }`,
    transparent:true, depthWrite:false, side:THREE.DoubleSide,
    polygonOffset:true, polygonOffsetFactor:-1, polygonOffsetUnits:-1
  })
  const mesh = new THREE.Mesh(geometry,material)
  mesh.name='engineeringBoundary'
  mesh.userData.visualEffect='boundary'
  mesh.raycast=()=>{}
  parent.add(mesh)
}

export function updateVisuals(root: THREE.Object3D, time: number, state: VisualState): void {
  root.traverse(object => {
    const kind = object.userData.visualEffect
    if (kind === 'path') {
      let owner: THREE.Object3D | null = object.parent
      let active = true
      while (owner) {
        if (owner.userData.fiberInfo?.status === 'offline') active = false
        owner = owner.parent
      }
      const mesh = object as THREE.Mesh<THREE.BufferGeometry,THREE.ShaderMaterial>
      mesh.visible = active && (state.flow || state.scan)
      mesh.material.uniforms.uTime.value = time
      mesh.material.uniforms.uFlow.value = state.flow && !object.userData.scanOnly ? 1 : 0
      mesh.material.uniforms.uScan.value = state.scan ? 1 : 0
    } else if (kind === 'water') {
      const mesh = object as THREE.Mesh<THREE.BufferGeometry,THREE.ShaderMaterial>
      mesh.material.uniforms.uTime.value = state.flow ? time : 0
    } else if (kind === 'marker') {
      object.visible = state.markers && object.userData.inHero !== false
      const cone = object.getObjectByName('markerCone')!
      const ring = object.getObjectByName('markerRing') as THREE.Mesh<THREE.BufferGeometry,THREE.MeshBasicMaterial>
      const active = object.userData.active !== false
      cone.rotation.y = active ? time*0.7 : 0
      cone.position.y = 2 + (active ? Math.sin(time*2)*0.3 : 0)
      ring.scale.setScalar(active ? 1+((time*0.5)%1)*0.6 : 1)
      ring.material.opacity = active ? 0.65*(1-((time*0.5)%1)*0.7) : 0.3
      const halo = object.getObjectByName('markerHalo') as THREE.Sprite | undefined
      if(halo){
        halo.scale.setScalar(2.6+(active?Math.sin(time*2)*.1:0))
        halo.material.color.copy((object.getObjectByName('markerCone') as THREE.Mesh<THREE.BufferGeometry,THREE.MeshStandardMaterial>).material.color)
      }
    } else if (kind === 'reflection') object.visible = state.reflection
    else if (kind === 'boundary') object.visible = state.boundary && (!object.userData.ownerLayer || root.getObjectByName(object.userData.ownerLayer)?.visible !== false)
  })
}
