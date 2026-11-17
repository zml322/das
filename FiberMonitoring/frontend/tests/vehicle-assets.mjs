import assert from 'node:assert/strict'
import {build} from 'esbuild'
import {readFile,mkdir,writeFile,rm} from 'node:fs/promises'
import {createHash} from 'node:crypto'
import * as THREE from 'three'
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js'

const temp=new URL('../.asset-test/',import.meta.url),assets=new URL('../public/assets/realism/',import.meta.url)
await mkdir(temp,{recursive:true})
try{
  await writeFile(new URL('entry.ts',temp),`export {installVehicleAsset} from '../src/three/engineering/VehicleAssets';export {invalidateRoadReflection} from '../src/three/engineering/RoadReflection';`)
  await build({entryPoints:[new URL('entry.ts',temp).pathname.replace(/^\/([A-Za-z]:)/,'$1')],outfile:new URL('assets.mjs',temp).pathname.replace(/^\/([A-Za-z]:)/,'$1'),bundle:true,platform:'node',format:'esm',external:['three'],logLevel:'silent'})
  const {installVehicleAsset,invalidateRoadReflection}=await import(new URL('assets.mjs',temp))
  const manifest=JSON.parse(await readFile(new URL('vehicles/SOURCE.json',assets),'utf8'))
  for(const item of manifest.files){
    const bytes=await readFile(new URL('vehicles/'+item.path,assets))
    assert.equal(createHash('sha256').update(bytes).digest('hex'),item.sha256,'prepared asset checksum')
    // This test verifies real geometry/material metadata. Browser QA decodes the embedded images.
    const loader=new GLTFLoader().register(()=>({name:'geometry-test-textures',loadTexture:()=>Promise.resolve(new THREE.Texture())}))
    const gltf=await loader.parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'')
    const type=item.path.replace('.glb',''),root=new THREE.Group(),parent=new THREE.Group()
    root.name='business-root';root.userData={clickable:true,vehicleInfo:{type,color:0xedeeee},businessId:'stable-id'};parent.add(root)
    let disposed=0;const old=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial());old.geometry.addEventListener('dispose',()=>disposed++);root.add(old)
    installVehicleAsset(root,gltf.scene);root.updateMatrixWorld(true)
    assert.equal(disposed,1,'fallback geometry is released only after replacement is ready')
    assert.equal(parent.children[0],root);assert.equal(root.userData.businessId,'stable-id');assert.equal(root.userData.clickable,true)
    assert.equal(root.children.length,1);assert.equal(root.children[0].name,'vehicleAsset')
    assert.ok(Math.abs(new THREE.Box3().setFromObject(root).min.y)<1e-6,'normalized wheels stand on the road plane')
    let rear
    root.traverse(object=>{if(object instanceof THREE.Mesh){
      for(const material of Array.isArray(object.material)?object.material:[object.material]){
        if(/redlens|Tail lamps/.test(material.name))rear=new THREE.Box3().setFromObject(object).getCenter(new THREE.Vector3())
        if(material instanceof THREE.MeshPhysicalMaterial)assert.equal(material.transmission,0,'small car windows must not trigger a full-scene refraction pass')
      }
    }})
    assert.ok(rear&&rear.z>0,'source orientation differs: every vehicle rear must face local +Z')
    const other=new THREE.Group();other.userData.vehicleInfo={type,color:0x19384a};installVehicleAsset(other,gltf.scene)
    let paintA,paintB;const paint=root=>{let result;root.traverse(o=>{if(o instanceof THREE.Mesh&&/^(paint|Body paint)/.test(o.material.name))result=o.material});return result}
    paintA=paint(root);paintB=paint(other);assert.ok(paintA&&paintB);assert.notEqual(paintA,paintB);assert.equal(paintB.color.getHex(),0x19384a);assert.equal(paintA.map,null,'source graphite base-color texture must not turn configured white paint gray')
  }
  const treeSource=JSON.parse(await readFile(new URL('tree/SOURCE.json',assets),'utf8')),treeBytes=await readFile(new URL('tree/roadside-tree.glb',assets))
  assert.equal(createHash('sha256').update(treeBytes).digest('hex'),treeSource.sha256)
  const treeDoc=JSON.parse(treeBytes.subarray(20,20+treeBytes.readUInt32LE(12)).toString())
  assert.equal(treeDoc.scenes.length,2);assert.ok(treeSource.lowTriangles<treeSource.highTriangles/4)
  const scene=new THREE.Scene(),reflection=new THREE.Object3D();reflection.name='wetRoadReflection';scene.add(reflection)
  invalidateRoadReflection(scene);assert.equal(reflection.userData.reflectionDirty,true)
  console.log('PASS: prepared asset hashes, grounded vehicles, bus/car orientation, stable picking roots, independent paint, refraction budget, tree LOD, reflection invalidation')
}finally{
  assert.ok(temp.pathname.endsWith('/frontend/.asset-test/'));await rm(temp,{recursive:true,force:true})
}
