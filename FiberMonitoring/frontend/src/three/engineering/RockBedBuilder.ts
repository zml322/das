import * as THREE from 'three';
import { displayLength } from './layout';
import { HERO } from '../hero/config';
export function buildRockBed():THREE.Group {
  const group=new THREE.Group();group.name='cutawayRockBed';
  const earth=new THREE.MeshStandardMaterial({color:0x927044,roughness:1});
  const bed=new THREE.Mesh(new THREE.BoxGeometry(340,1.4,100),earth);
  bed.position.set(0,HERO.baseY+3.0,53);bed.name='trenchBedding';bed.receiveShadow=true;group.add(bed);
  const geometry=new THREE.IcosahedronGeometry(.52,1);
  const vertices=geometry.attributes.position;
  for(let i=0;i<vertices.count;i++){
    const scale=.78+.32*Math.abs(Math.sin(vertices.getX(i)*31+vertices.getY(i)*17+vertices.getZ(i)*11));
    vertices.setXYZ(i,vertices.getX(i)*scale,vertices.getY(i)*scale,vertices.getZ(i)*scale);
  }
  geometry.computeVertexNormals();
  const count=3000, rocks=new THREE.InstancedMesh(geometry,new THREE.MeshStandardMaterial({color:0xa8a49a,roughness:.98}),count);
  rocks.raycast=()=>{};
  const object=new THREE.Object3D();
  for(let i=0;i<count;i++){
    const a=i*2.39996;
    const front=i%4===0?36+((i*.754877)%1)*45:16+Math.pow((i*.754877)%1,1.7)*20;
    object.position.set(((i*0.6180339)%1-.5)*(displayLength+90),HERO.baseY+3.75+Math.sin(a)*.12,front);
    object.rotation.set(a,a*.6,a*.37);
    const size=.28+Math.pow((i*.37)%1,3)*2.3;
    object.scale.set(size*(.8+((i*.23)%1)*.5),size*.6,size*(.7+((i*.47)%1)*.4));
    object.updateMatrix();rocks.setMatrixAt(i,object.matrix);
    rocks.setColorAt(i,new THREE.Color().setHSL(.085+(i%5)*.007,.06+(i%3)*.025,.24+(i%7)*.035));
  }
  rocks.castShadow=rocks.receiveShadow=true;group.add(rocks);return group;
}
