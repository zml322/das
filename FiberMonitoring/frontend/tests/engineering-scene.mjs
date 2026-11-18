import assert from 'node:assert/strict'
import {build} from 'esbuild'
import {writeFile,mkdir,rm} from 'node:fs/promises'
import * as THREE from 'three'

// Geometry-only integration test: a minimal canvas supplies texture generation APIs,
// without claiming a WebGL renderer or a screenshot was exercised.
const context={fillRect(){},beginPath(){},ellipse(){},fill(){},createLinearGradient(){return{addColorStop(){}}}}
globalThis.document={createElement:()=>({width:0,height:0,getContext:()=>context})}
globalThis.window={setInterval:()=>0,clearInterval(){}}
const temp=new URL('../.engineering-test/',import.meta.url)
await mkdir(temp,{recursive:true})
try{
  const entry=new URL('entry.ts',temp)
  await writeFile(entry,`export {buildScene} from '../src/three/core/SceneBuilder'; export {SceneManager} from '../src/three/core/SceneManager';
    export {syncSceneMonitoring} from '../src/three/core/MonitoringSceneSync';
    export {mockDataSource} from '../src/services/mock/MockMonitoringDataSource';
    export {DISPLAY,GEOLOGY,toDisplay,displayLength} from '../src/three/engineering/layout'; export {createHeroGroups,HERO_GROUP_NAMES} from '../src/three/hero/HeroGroups'; export {HERO,insideHero} from '../src/three/hero/config'; export {clipFiberSection} from '../src/three/hero/FiberSection'; export {HeroCameraController,HERO_VIEWS} from '../src/three/hero/HeroCameraController'; export {gsap} from 'gsap';`)
  await build({entryPoints:[entry.pathname.replace(/^\/([A-Za-z]:)/,'$1')],outfile:new URL('scene.mjs',temp).pathname.replace(/^\/([A-Za-z]:)/,'$1'),bundle:true,platform:'node',format:'esm',external:['three'],logLevel:'silent'})
  const {gsap,HeroCameraController,HERO_VIEWS,HERO,HERO_GROUP_NAMES,createHeroGroups,insideHero,clipFiberSection,SceneManager,buildScene,syncSceneMonitoring,mockDataSource,DISPLAY,GEOLOGY,toDisplay,displayLength}=await import(new URL('scene.mjs',temp))
  const store={fibers:await mockDataSource.getFiberList(),devices:await mockDataSource.getDevices(),events:await mockDataSource.getMonitoringEvents()}
  const labels=[]
  const annotations={add:(...args)=>labels.push(args)}
  const scene=new THREE.Scene(),groups=createHeroGroups(scene)
  const manager={...groups,roadGroup:groups.heroRoadGroup,undergroundGroup:groups.geologyGroup,pipeGroup:groups.sewerGroup,annotations,frameEngineeringModels(){},syncMonitoring(fibers,devices,events){syncSceneMonitoring(this,annotations,fibers,devices,events)}}
  assert.deepEqual(scene.children.map(group=>group.name),[...HERO_GROUP_NAMES])
  await buildScene(manager,store)
  const road=manager.roadGroup.getObjectByName('road');road.updateMatrixWorld(true)
  const roadSize=new THREE.Box3().setFromObject(road).getSize(new THREE.Vector3())
  assert.ok(Math.abs(roadSize.x-displayLength)<.1)
  assert.ok(Math.abs(roadSize.z-40)<.1,'visual road envelope remains 40m wide')
  const soil=manager.undergroundGroup.getObjectByName('underground')
  assert.equal(soil.children.length,5)
  assert.equal(GEOLOGY.reduce((sum,layer)=>sum+layer.thickness,0),10)
  assert.ok(Math.abs(new THREE.Box3().setFromObject(soil).min.y+10*DISPLAY.depth)<.001)
  assert.equal(manager.fiberGroup.children.length,store.fibers.length)
  for(const model of manager.fiberGroup.children){
    const fiber=store.fibers.find(f=>f.fiberId===model.userData.fiberId)
    assert.ok(model.userData.curve.getPoint(0).distanceTo(toDisplay(clipFiberSection(fiber.path3D)[model.userData.sectionIndex][0]))<1e-6)
    assert.equal(model.getObjectByName('fiberCore').geometry.parameters.path,model.getObjectByName('pathEffects').geometry.parameters.path)
    const original=clipFiberSection(fiber.path3D)[model.userData.sectionIndex]
    const sourceLength=original.slice(1).reduce((length,point,index)=>length+point.distanceTo(original[index]),0)
    assert.ok(Math.abs(model.userData.fiberInfo.length-sourceLength)<1e-6,'fiber metadata must retain source metres')
  }
  const pipe=manager.pipeGroup.children[0]
  assert.deepEqual(pipe.userData.inspectionWindow,{start:-36*DISPLAY.longitudinal,end:36*DISPLAY.longitudinal})
  assert.deepEqual(pipe.userData.sourceRange,[300,400],'visual compression must retain engineering chainage')
  assert.equal(pipe.userData.pipeInfo.length,100,'detail panel must show the source length')
  assert.equal(pipe.scale.x,DISPLAY.pipeCrossSection)
  assert.equal(pipe.getObjectByName('pipeJointBolts').count,80)
  pipe.updateMatrixWorld(true)
  assert.ok(Math.abs(new THREE.Box3().setFromObject(pipe.getObjectByName('pipeCylinder')).getSize(new THREE.Vector3()).x-displayLength)<.01,'solid inspection wall must span the same transformed source section as the fibers')
  assert.ok(Math.abs(pipe.position.y-(-6.4*DISPLAY.depth))<.001)
  assert.equal(manager.vehicleGroup.children.length,4)
  const alarmLabels=labels.filter(args=>args[3]==='red'&&!args[0].includes('光纤'))
  assert.ok(alarmLabels.length<=3,'scene must not drown the physical models in alarm labels')
  assert.ok(store.devices.every(device=>!device.position||Math.abs(device.position.x)<=455))
  const resizeCalls=[]
  const resizeTarget={container:{clientWidth:960,clientHeight:540},viewportWidth:0,viewportHeight:0,camera:{updateProjectionMatrix(){}},renderer:{setSize:(...args)=>resizeCalls.push(args)}}
  SceneManager.prototype.handleResize.call(resizeTarget)
  SceneManager.prototype.handleResize.call(resizeTarget)
  assert.equal(resizeCalls.length,1,'same-size observer notifications must not reset the WebGL buffer')
  assert.equal(resizeCalls[0][2],false,'resizing the render buffer must not rewrite CSS dimensions')
  resizeTarget.container.clientWidth=1000
  SceneManager.prototype.handleResize.call(resizeTarget)
  assert.equal(resizeCalls.length,2)
  // ResizeObserver must not clear the live canvas outside a rendered frame.
  let resizeCallback
  globalThis.ResizeObserver=class { constructor(callback){resizeCallback=callback} observe(){} }
  const frameCalls=[]
  const frameTarget={
    container:{clientWidth:800,clientHeight:500},lastFrame:100,resizePending:false,
    scene:new THREE.Scene(),camera:new THREE.PerspectiveCamera(),
    visualState:{},effectClock:{time:0,advance(){}},
    cameraController:{update(){}},controls:{update(){}},annotations:{update(){}},
    handleResize(){frameCalls.push('resize')},renderer:{render(){frameCalls.push('render')}},
  }
  SceneManager.prototype.setupResizeObserver.call(frameTarget)
  resizeCallback();resizeCallback()
  assert.deepEqual(frameCalls,[],'resize notifications only queue the latest dimensions')
  SceneManager.prototype.renderFrame.call(frameTarget,110)
  assert.deepEqual(frameCalls,[],'a skipped frame must not clear the canvas')
  SceneManager.prototype.renderFrame.call(frameTarget,140)
  assert.deepEqual(frameCalls,['resize','render'],'resize is immediately followed by rendering')
  SceneManager.prototype.renderFrame.call(frameTarget,180)
  assert.deepEqual(frameCalls,['resize','render','render'],'unchanged dimensions do not resize again')
  delete globalThis.ResizeObserver
  SceneManager.prototype.setUndergroundOpacity.call(manager,.6)
  assert.equal(soil.children[0].material.depthWrite,false)
  SceneManager.prototype.setUndergroundOpacity.call(manager,1)
  assert.equal(soil.children[0].material.transparent,false)
  assert.equal(soil.children[0].material.depthWrite,true)
  const disjoint=clipFiberSection([{x:-160,y:-1,z:18},{x:-120,y:-1,z:18},{x:-170,y:-2,z:18},{x:-110,y:-2,z:18},{x:-50,y:-2,z:18}])
  assert.equal(disjoint.length,2,'disconnected clipped routes must not be joined across outside geometry')
  for(const section of disjoint)assert.ok(section.every(point=>insideHero(point)))
  pipe.updateMatrixWorld(true)
  const origin=pipe.localToWorld(new THREE.Vector3(-5,1,0)),direction=new THREE.Vector3(1,0,0).transformDirection(pipe.matrixWorld)
  const hits=new THREE.Raycaster(origin,direction).intersectObject(pipe.getObjectByName('pipeCylinder'))
  assert.ok(hits.length>0&&hits.every(hit=>pipe.worldToLocal(hit.point.clone()).x>0),'inspection window removes the front wall while keeping the back wall')
  assert.equal(displayLength,100*DISPLAY.longitudinal)
  assert.equal(HERO.length,100,'source section remains 100m')
  assert.ok(manager.envGroup.getObjectByName('urbanBackdrop'),'continuous urban backdrop replaces the unrelated river scene')
  assert.ok(new THREE.Box3().setFromObject(manager.envGroup).getSize(new THREE.Vector3()).x>300)
  const activeEvents=store.events.filter(event=>insideHero(event.position)&&event.status!=='resolved'&&event.severity!=='info')
  assert.equal(manager.markerGroup.children.filter(marker=>marker.userData.eventId).length,activeEvents.length)
  assert.ok(manager.markerGroup.children.some(marker=>marker.userData.monitoringAnchor))
  const camera=new THREE.PerspectiveCamera(42,2,1,1200)
  class FakeControls extends THREE.EventDispatcher {target=new THREE.Vector3();enableDamping=true;update(){}}
  const controls=new FakeControls(),controller=new HeroCameraController(camera,controls)
  controller.setView('overview',false)
  const start=camera.position.clone()
  controller.setView('top');controller.update(.1)
  assert.ok(camera.position.distanceTo(start)>0&&camera.position.distanceTo(new THREE.Vector3(...HERO_VIEWS.top.position))>1)
  controller.setView('underground')
  for(let frame=0;frame<40;frame++)controller.update(.04)
  assert.equal(controller.transitioning,false)
  assert.ok(camera.position.distanceTo(new THREE.Vector3(...HERO_VIEWS.underground.position))<1e-5)
  controller.setView('cross');controls.dispatchEvent({type:'start'})
  assert.equal(controller.transitioning,false)
  for(const view of Object.keys(HERO_VIEWS)){
    controller.setView(view,false)
    assert.ok(camera.position.y>=controls.target.y)
  }
  controller.dispose()
  const reduced=new HeroCameraController(camera,controls,true)
  reduced.setView('top');assert.equal(reduced.transitioning,false);reduced.dispose()
  gsap.ticker.sleep()
  console.log('PASS: 100m Hero, eight groups, 40m road, cutaway soil/sewer, cropped fibers, filled environment, event range filtering, GSAP transitions/interruption/reduced motion')
}finally{
  assert.ok(temp.pathname.endsWith('/frontend/.engineering-test/'))
  await rm(temp,{recursive:true,force:true})
}
