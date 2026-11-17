import * as THREE from 'three';
import { RoadBuilder } from '../models/RoadBuilder';
import { buildCity,createTree,createLamp,createBuilding } from '../engineering/CityBuilder';
import { HERO } from './config';
import { displayLength,DISPLAY } from '../engineering/layout';

export function buildHeroEnvironment():THREE.Group {
  const group=new THREE.Group();group.name='heroEnvironment';
  group.add(buildCity());
  const ground=new THREE.Mesh(new THREE.BoxGeometry(600,.7,500),new THREE.MeshStandardMaterial({color:0x71894b,roughness:1}));
  ground.name='urbanBackdrop';ground.position.set(0,-.55,-270);ground.receiveShadow=true;group.add(ground);
  for(const side of [-1,1]){
    const road=RoadBuilder.build({roadLength:180,roadWidth:32,laneWidth:(32-DISPLAY.roadMedian)/6,laneCount:6,sidewalkWidth:4,medianStripWidth:DISPLAY.roadMedian});
    road.rotation.y=Math.PI/2;road.position.x=side*(displayLength/2+90);road.name='roadExtension';group.add(road);
  }
  for(let x=-150,index=0;x<=260;x+=18,index++){
    if(Math.abs(x)>HERO.length/2)group.add(createTree(x,-21,index),createLamp(x,-18));
    group.add(createTree(x,-36,index+1));
  }
  for(let i=0;i<22;i++){
    const building=createBuilding((i-6)*28,i+3);
    building.position.z=-72-(i%3)*18;building.scale.set(1,.7+(i%4)*.11,1);
    group.add(building);
  }
  return group;
}
