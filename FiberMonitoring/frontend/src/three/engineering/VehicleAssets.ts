import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VehicleType } from '@/types/monitoring';
import type { SceneManager } from '../core/SceneManager';
import { disposeObject } from '../effects/PathEffects';

const ASSETS = [
  {type:VehicleType.SEDAN,file:'sedan'},
  {type:VehicleType.TRUCK,file:'truck'},
  {type:VehicleType.BUS,file:'bus'},
];

/** Keep the existing selectable vehicle root, replacing only its visual children. */
export function installVehicleAsset(root:THREE.Object3D,prototype:THREE.Group):void {
  const model=prototype.clone(true);
  // Cars/trucks face -X in the source; this bus faces +X. All local roots face -Z.
  model.rotation.y=root.userData.vehicleInfo.type===VehicleType.BUS?Math.PI/2:-Math.PI/2;
  model.updateMatrixWorld(true);
  const bounds=new THREE.Box3().setFromObject(model),center=bounds.getCenter(new THREE.Vector3());
  model.position.set(-center.x,-bounds.min.y,-center.z);
  const materials=new Map<THREE.Material,THREE.Material>();
  const color=root.userData.vehicleInfo.color;
  model.traverse(object=>{
    if(!(object instanceof THREE.Mesh))return;
    const tune=(source:THREE.Material)=>{
      if(materials.has(source))return materials.get(source)!;
      let material:THREE.Material;
      if(source instanceof THREE.MeshStandardMaterial){
        const name=source.name.toLowerCase();
        if(name==='paint'||name.includes('body paint')){
          // Source paint maps are graphite gray. Keep surface data maps, while the configured paint owns color.
          material=new THREE.MeshPhysicalMaterial({color,metalness:.48,roughness:.23,clearcoat:1,clearcoatRoughness:.16,normalMap:source.normalMap,roughnessMap:source.roughnessMap,metalnessMap:source.metalnessMap,aoMap:source.aoMap,normalScale:source.normalScale.clone()});
          material.name=source.name;
        }else material=source.clone();
        const pbr=material as THREE.MeshStandardMaterial;
        pbr.envMapIntensity=1.1;pbr.forceSinglePass=true;
        if(pbr instanceof THREE.MeshPhysicalMaterial){pbr.transmission=0;pbr.thickness=0}
        if(name.includes('glass')||name.includes('glazing')){
          pbr.color.setHex(0x24424e);pbr.roughness=.12;pbr.metalness=.3;pbr.transparent=true;pbr.opacity=.86;pbr.depthWrite=false;
          if(root.userData.vehicleInfo.type===VehicleType.BUS){pbr.color.setHex(0x0c2b3f);pbr.opacity=.98;pbr.metalness=.65}
        }
        if(name.includes('lamp')||name==='clearlens'){
          pbr.emissive.setHex(0xffead2);pbr.emissiveIntensity=.3;
        }
      }else material=source.clone();
      materials.set(source,material);return material;
    };
    object.material=Array.isArray(object.material)?object.material.map(tune):tune(object.material);
    object.castShadow=object.receiveShadow=true;
  });
  for(const child of [...root.children])disposeObject(child);
  model.name='vehicleAsset';root.add(model);root.userData.assetModel=true;
}

export async function enhanceVehicles(manager:SceneManager,isDisposed:()=>boolean):Promise<void>{
  const loader=new GLTFLoader();
  const results=await Promise.allSettled(ASSETS.map(({file})=>loader.loadAsync('/assets/realism/vehicles/'+file+'.glb')));
  results.forEach((result,index)=>{
    if(result.status==='rejected')return;
    const prototype=result.value.scene;
    const targets=manager.vehicleGroup.children.filter(root=>root.userData.vehicleInfo?.type===ASSETS[index].type);
    if(isDisposed()||!targets.length){disposeObject(prototype);return}
    targets.forEach(root=>installVehicleAsset(root,prototype));
    // Geometry is owned by the installed clones. Release only the unused source materials.
    const sourceMaterials=new Set<THREE.Material>();
    const usedTextures=new Set<THREE.Texture>();
    targets.forEach(root=>root.traverse(object=>{if(object instanceof THREE.Mesh)(Array.isArray(object.material)?object.material:[object.material]).forEach(material=>Object.values(material).forEach(value=>{if(value instanceof THREE.Texture)usedTextures.add(value)}))}));
    prototype.traverse(object=>{if(object instanceof THREE.Mesh)(Array.isArray(object.material)?object.material:[object.material]).forEach(material=>sourceMaterials.add(material))});
    const unusedTextures=new Set<THREE.Texture>();
    sourceMaterials.forEach(material=>{Object.values(material).forEach(value=>{if(value instanceof THREE.Texture&&!usedTextures.has(value))unusedTextures.add(value)});material.dispose()});
    unusedTextures.forEach(texture=>texture.dispose());
  });
  if(results.some(result=>result.status==='rejected')&&!isDisposed())console.warn('部分车辆资源未加载，保留备用车辆模型');
}
