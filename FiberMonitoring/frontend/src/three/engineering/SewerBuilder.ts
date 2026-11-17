import * as THREE from "three";
import { PipeBuilder } from "../models/PipeBuilder";
import { toDisplay } from "./layout";

export function buildSewer(
  start: { x: number; y: number; z: number },
  end: { x: number; y: number; z: number },
  name: string,
): THREE.Group {
  const a = toDisplay(start),
    b = toDisplay(end),
    radius = 2.25,
    length = a.distanceTo(b);
  const group = PipeBuilder.build({
    startPosition: a,
    endPosition: b,
    diameter: radius * 2,
    pipeType: "sewage",
    material: "steel",
    color: 0x7b99ac,
    name,
  });
  for (const child of [...group.children])
    if (child.name !== "pipeCylinder" && child.name !== "pathEffects") {
      const mesh = child as THREE.Mesh;
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
      group.remove(child);
    }
  const inner = new THREE.Mesh(
    new THREE.CylinderGeometry(
      radius - 0.22,
      radius - 0.22,
      length,
      32,
      1,
      true,
    ),
    new THREE.MeshStandardMaterial({
      color: 0x294d61,
      metalness: 0.55,
      roughness: 0.4,
      side: THREE.BackSide,
    }),
  );
  inner.geometry.rotateX(Math.PI / 2);
  group.add(inner);
  const collarMaterial = new THREE.MeshStandardMaterial({
    color: 0x9caeb8, metalness: .85, roughness: .32,
  });
  const boltGeometry = new THREE.CylinderGeometry(.085,.085,.22,6);
  const bolts = new THREE.InstancedMesh(boltGeometry,collarMaterial,5*16);
  bolts.name = 'pipeJointBolts';
  const bolt = new THREE.Object3D();
  for (let joint=0; joint<=4; joint++) {
    const z = -length/2 + joint*length/4;
    const rim = new THREE.Mesh(
      new THREE.TorusGeometry(radius+.04, 0.19, 12, 64), collarMaterial,
    );
    rim.position.z = z;
    group.add(rim);
    for(let index=0;index<16;index++) {
      const angle=index*Math.PI/8;
      bolt.position.set(Math.cos(angle)*(radius+.11),Math.sin(angle)*(radius+.11),z+.17);
      bolt.rotation.x=Math.PI/2;bolt.updateMatrix();bolts.setMatrixAt(joint*16+index,bolt.matrix);
    }
  }
  bolts.castShadow=true;group.add(bolts);
  for(const z of [-length/2,length/2]) {
    const edge = new THREE.Mesh(new THREE.RingGeometry(radius-.22,radius,64),collarMaterial);
    edge.material.side=THREE.DoubleSide;edge.position.z=z;group.add(edge);
  }
  const water = new THREE.Mesh(
    new THREE.PlaneGeometry(radius * 1.7, length,12,120),
    new THREE.ShaderMaterial({
      uniforms: { uTime: { value: 0 } },
      vertexShader: `varying vec2 vUv;uniform float uTime;
        void main(){vUv=uv;vec3 p=position;p.z+=.06*sin(uv.y*170.-uTime*2.+uv.x*13.);gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}`,
      fragmentShader: `varying vec2 vUv;uniform float uTime;
        float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
        float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+1.),f.x),f.y);}
        float height(vec2 p){return noise(p)*.58+noise(p*2.13)*.28+noise(p*4.3)*.14;}
        void main(){vec2 p=vec2(vUv.x*14.,vUv.y*160.-uTime*6.);float h=height(p);
          vec2 gradient=vec2(height(p+vec2(.14,0))-h,height(p+vec2(0,.14))-h);
          vec3 n=normalize(vec3(-gradient.x*2.4,-gradient.y*.9,1.));
          float spec=pow(max(0.,dot(n,normalize(vec3(-.12,.18,1.)))),70.);
          float edge=smoothstep(0.,.1,vUv.x)*smoothstep(0.,.1,1.-vUv.x);
          vec3 color=mix(vec3(.003,.075,.15),vec3(.005,.27,.40),h)*(.55+edge*.45);
          color+=vec3(.045,.42,.58)*spec*.65;gl_FragColor=vec4(color,.97);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
      transparent: true, side: THREE.DoubleSide, depthWrite: false,
    }),
  );
  // Plane local Y follows the tube's local Z after rotation.
  water.rotation.x = Math.PI / 2;
  water.position.y = -radius * 0.35;
  water.name = 'sewerWater';
  water.userData.visualEffect = 'water';
  group.add(water);
  return group;
}
