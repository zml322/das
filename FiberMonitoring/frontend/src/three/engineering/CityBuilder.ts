import * as THREE from 'three';
import { displayLength } from './layout';
import { createSurfaceTexture } from './SurfaceTextures';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

function meshBox(width: number, height: number, depth: number, color: number): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(width, height, depth), new THREE.MeshStandardMaterial({ color, roughness: .8 }));
  mesh.castShadow = mesh.receiveShadow = true;
  return mesh;
}
export function createTree(x: number, z: number, index: number): THREE.Group {
  const group = new THREE.Group();
  group.userData.treeCanopy = true;
  group.userData.treeIndex = index;
  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(.16, .33, 4.8, 10), new THREE.MeshStandardMaterial({color:0x69513b,roughness:1}));
  trunk.position.y = 2.4; trunk.castShadow = true;
  group.add(trunk);
  // Complete fallback crown remains until the full, normalized tree asset is ready.
  for (let i=0;i<5;i++) {
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(2.2,14,10), new THREE.MeshStandardMaterial({color:[0x4c7828,0x668b2b,0x759c36][(i+index)%3],roughness:1}));
    leaf.position.set(Math.sin(i*2.4)*1.3,5.3+(i%2)*1.1,Math.cos(i*2.4)*1.3);
    leaf.scale.set(1,1.15,.95); leaf.castShadow=true;
    group.add(leaf);
  }
  group.position.set(x,0,z);
  return group;
}
export function createLamp(x: number,z: number):THREE.Group {
  const group=new THREE.Group(), metal=new THREE.MeshStandardMaterial({color:0xcbd6d9,metalness:.75,roughness:.27});
  const pole=new THREE.Mesh(new THREE.CylinderGeometry(.1,.2,9,12),metal);pole.position.y=4.5;
  const points=[new THREE.Vector3(0,8.8,0),new THREE.Vector3(0,9.5,z>0?-.8:.8),new THREE.Vector3(0,9.6,z>0?-3.1:3.1)];
  const arm=new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),12,.09,8,false),metal);
  const lamp=meshBox(.55,.12,1.25,0xe1ebec);lamp.position.set(0,9.5,z>0?-3:3);
  group.add(pole,arm,lamp);group.position.set(x,0,z);return group;
}
export function createBuilding(x:number,index:number):THREE.Mesh {
  const height=18+(index*11)%24, width=13+(index%3)*5, depth=11+(index%2)*5;
  const glass=new THREE.MeshPhysicalMaterial({color:[0x438fc4,0x2378a9,0x396e9d,0x69a8c9][index%4],map:createSurfaceTexture('windows',index+1),roughness:.16,metalness:.62,clearcoat:1,envMapIntensity:.9});
  const building=new THREE.Mesh(new THREE.BoxGeometry(width,height,depth),glass);
  building.position.set(x,height/2,-72-(index%3)*15);building.castShadow=building.receiveShadow=true;
  building.userData.cityGlass=true;
  const frame=new THREE.MeshStandardMaterial({color:0xb8cad6,metalness:.55,roughness:.4});
  const strips: {size:number[];position:number[]}[]=[];
  for(let y=-height/2+3;y<height/2;y+=3.2) {
    strips.push({size:[width+.12,.06,depth+.12],position:[0,y,0]});
  }
  for(let px=-width/2;px<=width/2;px+=width/5) {
    strips.push({size:[.065,height,.13],position:[px,0,depth/2+.04]});
    strips.push({size:[.065,height,.13],position:[px,0,-depth/2-.04]});
  }
  const frameParts=strips.map(strip=>new THREE.BoxGeometry(...strip.size as [number,number,number]).translate(...strip.position as [number,number,number]));
  const facade=new THREE.Mesh(mergeGeometries(frameParts)!,frame);
  frameParts.forEach(geometry=>geometry.dispose());building.add(facade);
  const roof=meshBox(width+.5,.5,depth+.5,0xa8b6bb);roof.position.y=height/2;building.add(roof);
  const podium=meshBox(width+3,3.2,depth+2,0xa9b3b7);podium.position.y=-height/2+1.6;building.add(podium);
  return building;
}
export function buildCity():THREE.Group {
  const group=new THREE.Group();group.name='roadEnvironment';
  for(let x=-displayLength/2+6,index=0;x<displayLength/2;x+=12,index++) {
    group.add(createTree(x,-21,index));
    if(index%2===0)group.add(createLamp(x,18),createLamp(x,-18));
    if(index%3===0)group.add(createBuilding(x*1.7,index));
    const hedge=meshBox(10,.65,1.2,0x426528);hedge.position.set(x,.4,-16.5);group.add(hedge);
    const median=meshBox(10,.25,3,0x4a6a2f);median.position.set(x,.2,0);group.add(median);
  }
  return group;
}
