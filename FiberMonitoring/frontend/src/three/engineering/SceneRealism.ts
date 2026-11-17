import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader.js';
import type { SceneManager } from '../core/SceneManager';
import { disposeObject } from '../effects/PathEffects';
import { createCanopyFill } from './TreeFoliage';
import { enhanceVehicles } from './VehicleAssets';
import { invalidateRoadReflection } from './RoadReflection';

const asset=(name:string)=>'/assets/realism/'+name;
type SurfaceSet={color:THREE.Texture;normal:THREE.Texture;roughness:THREE.Texture};
async function loadSurface(kind:string):Promise<SurfaceSet> {
  const loader=new THREE.TextureLoader();
  const results=await Promise.allSettled(['color','normal','roughness'].map(name=>loader.loadAsync(asset(kind+'-'+name+'.jpg'))));
  if(results.some(result=>result.status==='rejected')){
    results.forEach(result=>{if(result.status==='fulfilled')result.value.dispose()});
    throw new Error('Material maps unavailable: '+kind);
  }
  const [color,normal,roughness]=results.map(result=>(result as PromiseFulfilledResult<THREE.Texture>).value);
  color.colorSpace=THREE.SRGBColorSpace;return {color,normal,roughness};
}
function applySurface(material:THREE.MeshStandardMaterial,maps:SurfaceSet,repeat:THREE.Vector2):void {
  material.map?.dispose();
  const prepare=(source:THREE.Texture)=>{
    const texture=source.clone();texture.wrapS=texture.wrapT=THREE.RepeatWrapping;
    texture.repeat.copy(repeat);texture.anisotropy=8;texture.needsUpdate=true;return texture;
  };
  material.map=prepare(maps.color);material.normalMap=prepare(maps.normal);material.roughnessMap=prepare(maps.roughness);
  material.normalScale.set(.8,.8);material.needsUpdate=true;
}
function replaceTrees(manager:SceneManager,prototype:THREE.Group,low:THREE.Group):void {
  const roots:THREE.Object3D[]=[];
  manager.envGroup.traverse(object=>{if(object.userData.treeCanopy)roots.push(object)});
  if(!roots.length)return;
  prototype.updateMatrixWorld(true);low.updateMatrixWorld(true);
  const bounds=new THREE.Box3().setFromObject(prototype),size=bounds.getSize(new THREE.Vector3()),center=bounds.getCenter(new THREE.Vector3());
  if(size.y<.1)return;
  const forest=new THREE.Group();forest.name='roadsideTrees';
  const sources=(source:THREE.Group)=>{const meshes:THREE.Mesh[]=[];source.traverse(object=>{if(object instanceof THREE.Mesh)meshes.push(object)});return meshes};
  const variants=[sources(prototype),sources(low)];
  const clusters=new Map<string,{root:THREE.Object3D;index:number}[]>();
  roots.forEach((root,index)=>{
    const key=Math.floor(root.position.x/40)+':'+Math.floor(root.position.z/40);
    const cluster=clusters.get(key)??[];cluster.push({root,index});clusters.set(key,cluster);
  });
  for(const cluster of clusters.values()){
    const origin=cluster.reduce((sum,{root})=>sum.add(root.position),new THREE.Vector3()).divideScalar(cluster.length);
    const lod=new THREE.LOD();lod.position.copy(origin);lod.name='treeCluster';
    variants.forEach((meshes,level)=>{
      const group=new THREE.Group();
      for(const mesh of meshes){
        const materials=Array.isArray(mesh.material)?mesh.material:[mesh.material];
        materials.forEach(material=>{if(material instanceof THREE.MeshStandardMaterial){material.envMapIntensity=.35;material.roughness=Math.max(.65,material.roughness);material.side=THREE.DoubleSide;material.forceSinglePass=true}});
        const instances=new THREE.InstancedMesh(mesh.geometry,mesh.material,cluster.length);
        instances.raycast=()=>{};instances.name='tree-'+mesh.name;instances.castShadow=instances.receiveShadow=true;
        cluster.forEach(({root,index},i)=>{
          const scale=(13.5+Math.sin(index*3.7)*1.3)/size.y;
          const normalize=new THREE.Matrix4().makeTranslation(-center.x,-bounds.min.y,-center.z);
          const placement=new THREE.Matrix4().compose(root.position.clone().sub(origin),new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),index*2.399),new THREE.Vector3(scale,scale,scale));
          instances.setMatrixAt(i,placement.multiply(normalize).multiply(mesh.matrixWorld));
        });
        instances.computeBoundingSphere();group.add(instances);
      }
      lod.addLevel(group,level===0?0:100,.12);
    });
    forest.add(lod);
  }
  roots.forEach(root=>[...root.children].forEach(disposeObject));
  forest.add(createCanopyFill(roots));
  manager.envGroup.add(forest);
}
export async function enhanceScene(manager:SceneManager,isDisposed:()=>boolean):Promise<void> {
  const results=await Promise.allSettled([
    loadSurface('asphalt'),loadSurface('soil'),loadSurface('rock'),loadSurface('sand'),
    new GLTFLoader().loadAsync(asset('tree/roadside-tree.glb')),
    new RGBELoader().loadAsync(asset('daylight.hdr')),
    enhanceVehicles(manager,isDisposed),
  ]);
  if(isDisposed()) {
    results.forEach((result,index)=>{if(result.status==='fulfilled'){
      if(index<4)Object.values(result.value as SurfaceSet).forEach(t=>t.dispose());
      else if(index===4)(result.value as {scenes:THREE.Group[]}).scenes.forEach(disposeObject);
      else if(index===5)(result.value as THREE.Texture).dispose();
    }});return;
  }
  const [asphalt,soil,rock,sand,tree,sky]=results;
  if(asphalt.status==='fulfilled') {
    const maps=asphalt.value as SurfaceSet;
    const apply=(object:THREE.Object3D)=>{
      if(object instanceof THREE.Mesh&&object.name==='roadSurface'){
        const mat=object.material as THREE.MeshStandardMaterial;
        applySurface(mat,maps,new THREE.Vector2(8,25));mat.color.setHex(0xadb3b7);mat.roughness=.45;mat.metalness=.22;
      }
    };
    manager.roadGroup.traverse(apply);manager.envGroup.traverse(apply);
  }
  const tints=[0xb6b6b3,0xffe0ac,0xf1c697,0xd9af7e,0xe5c897];
  const terrain=[asphalt,rock,soil,rock,sand];
  manager.geologyGroup.getObjectByName('underground')?.children.forEach((object,index)=>{
    const layer=object as THREE.Mesh<THREE.BoxGeometry,THREE.MeshStandardMaterial>;
    const set=terrain[index];
    if(set.status==='fulfilled'){
      applySurface(layer.material,set.value as SurfaceSet,new THREE.Vector2(layer.geometry.parameters.width/5,layer.geometry.parameters.height/3));
      layer.material.color.setHex(tints[index]).multiplyScalar(1.8);layer.material.roughness=1;
      const details=layer.getObjectByName('strataDetails') as THREE.InstancedMesh | undefined;
      if(details){
        const mat=details.material as THREE.MeshStandardMaterial;
        applySurface(mat,set.value as SurfaceSet,new THREE.Vector2(1.2,1.2));
        mat.color.setHex(tints[index]).multiplyScalar(1.8);
      }
    }
  });
  const bedding=manager.geologyGroup.getObjectByName('trenchBedding') as THREE.Mesh<THREE.BufferGeometry,THREE.MeshStandardMaterial> | undefined;
  if(bedding&&rock.status==='fulfilled'){
    applySurface(bedding.material,rock.value as SurfaceSet,new THREE.Vector2(65,20));
    bedding.material.color.setHex(0xc3a77f).multiplyScalar(1.3);
  }
  if(tree.status==='fulfilled'){
    const gltf=tree.value as {scene:THREE.Group;scenes:THREE.Group[]};
    replaceTrees(manager,gltf.scene,gltf.scenes[1]??gltf.scene);
  }
  if(sky.status==='fulfilled')manager.setDaylightEnvironment(sky.value as THREE.DataTexture);
  manager.envGroup.traverse(object=>{if(object instanceof THREE.Mesh&&object.userData.cityGlass)(object.material as THREE.MeshStandardMaterial).envMapIntensity=.9});
  results.slice(0,4).forEach(result=>{if(result.status==='fulfilled')Object.values(result.value as SurfaceSet).forEach(t=>t.dispose())});
  manager.getRenderer().shadowMap.needsUpdate=true;
  invalidateRoadReflection(manager.getScene());
  if(results.some(r=>r.status==='rejected'))console.warn('部分写实资源未加载，使用完整备用模型');
}
