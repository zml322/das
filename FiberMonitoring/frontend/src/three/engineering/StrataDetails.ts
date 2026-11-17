import * as THREE from 'three';
import { displayLength } from './layout';

/** A real, uneven front surface: deterministic clods, not another flat color band. */
export function createStrataDetails(height:number,width:number,index:number):THREE.InstancedMesh{
  const geometry=new THREE.IcosahedronGeometry(1,1),vertices=geometry.attributes.position;
  for(let i=0;i<vertices.count;i++){
    const x=vertices.getX(i),y=vertices.getY(i),z=vertices.getZ(i);
    const r=.88+.18*Math.sin(x*12+y*19+z*7);
    vertices.setXYZ(i,x*r,y*r,z*r);
  }
  geometry.computeVertexNormals();
  const count=Math.ceil((displayLength+100)*height*.9);
  const clods=new THREE.InstancedMesh(geometry,new THREE.MeshStandardMaterial({color:0xc2a37f,roughness:1}),count);
  clods.name='strataDetails';clods.castShadow=clods.receiveShadow=true;
  clods.raycast=()=>{}; // The parent layer remains the picking surface.
  const object=new THREE.Object3D();let seed=571+index*127;
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296};
  for(let i=0;i<count;i++){
    const radius=Math.min(height*.2,.18+Math.pow(random(),2)*.8),sy=radius*(.65+random()*.4);
    object.position.set((random()-.5)*(displayLength+100),(random()-.5)*(height-radius*4.5),width/2-.05+random()*.03);
    object.rotation.set(0,0,random()*.5);object.scale.set(radius*(.8+random()),sy,Math.min(.25,radius*.55));
    object.updateMatrix();clods.setMatrixAt(i,object.matrix);
    clods.setColorAt(i,new THREE.Color().setHSL(.075+random()*.035,index===0?0:.1+random()*.1,.50+random()*.35));
  }
  clods.computeBoundingSphere();return clods;
}
