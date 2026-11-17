import ts from 'typescript'
import { readFile, mkdir, writeFile, rm } from 'node:fs/promises'
import assert from 'node:assert/strict'
import * as THREE from 'three'

// Compile the real modules into an isolated directory, then exercise their geometry and state.
const temp = new URL('../.visual-test/', import.meta.url)
await mkdir(temp, {recursive:true})
try {
  for (const [source,name] of [['effects/PathEffects','PathEffects'],['models/FiberBuilder','FiberBuilder'],['models/PipeBuilder','PipeBuilder']]) {
    const input = (await readFile(new URL(`../src/three/${source}.ts`,import.meta.url),'utf8'))
      .replace(/(['"])\.\.\/effects\/PathEffects\1/g,"'./PathEffects.mjs'")
    const output = ts.transpileModule(input,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.ESNext}}).outputText
    await writeFile(new URL(`${name}.mjs`,temp),output)
  }
  const {defaultVisualState,updateVisuals,disposeObject,VisualClock}=await import(new URL('PathEffects.mjs',temp))
  const {FiberBuilder,FiberStatus}=await import(new URL('FiberBuilder.mjs',temp))
  const {PipeBuilder}=await import(new URL('PipeBuilder.mjs',temp))
  const fiber=FiberBuilder.build({id:'curved',name:'curved',pathPoints:[new THREE.Vector3(-20,-3,5),new THREE.Vector3(-5,-8,15),new THREE.Vector3(8,-1,-12),new THREE.Vector3(20,-4,8)]})
  const core=fiber.getObjectByName('fiberCore'),effect=fiber.getObjectByName('pathEffects')
  assert.equal(core.geometry.parameters.path,effect.geometry.parameters.path,'solid and glow must share the exact curve')
  const positions=effect.geometry.attributes.position
  for(let i=0;i<=200;i++) {
    const center=new THREE.Vector3()
    for(let j=0;j<8;j++) center.add(new THREE.Vector3().fromBufferAttribute(positions,i*9+j))
    center.divideScalar(8)
    assert.ok(center.distanceTo(fiber.userData.curve.getPointAt(i/200))<1e-5,'every glow cross-section follows the actual 3D route')
  }
  const state=defaultVisualState(),clock=new VisualClock()
  clock.advance(.1,state);const before=clock.time
  state.playback='paused';clock.advance(.1,state);assert.equal(clock.time,before)
  state.playback='running';clock.advance(.1,state);assert.ok(clock.time>before)
  const resumed=clock.time;clock.advance(.1,state,true);assert.equal(clock.time,resumed)
  state.playback='stopped';clock.advance(.1,state);assert.equal(clock.time,0)
  updateVisuals(fiber,2,state);assert.equal(effect.material.uniforms.uTime.value,2)
  const water=new THREE.Mesh(new THREE.PlaneGeometry(1,1),new THREE.ShaderMaterial({uniforms:{uTime:{value:0}}}))
  water.userData.visualEffect='water'
  updateVisuals(water,2,state);assert.equal(water.material.uniforms.uTime.value,2)
  state.playback='paused';clock.time=2;clock.advance(.1,state);updateVisuals(water,clock.time,state)
  assert.equal(water.material.uniforms.uTime.value,2,'water follows the paused shared clock')
  state.flow=false;updateVisuals(water,3,state);assert.equal(water.material.uniforms.uTime.value,0,'flow switch disables water movement')
  state.flow=true;state.playback='running';disposeObject(water)
  const reflection=new THREE.Object3D();reflection.userData.visualEffect='reflection'
  state.reflection=false;updateVisuals(reflection,0,state);assert.equal(reflection.visible,false)
  state.reflection=true;updateVisuals(reflection,0,state);assert.equal(reflection.visible,true)
  state.flow=false;state.scan=false;updateVisuals(fiber,2,state);assert.equal(effect.visible,false)
  FiberBuilder.updateStatus(fiber,FiberStatus.OFFLINE);state.flow=true;state.scan=true
  updateVisuals(fiber,3,state);assert.equal(effect.visible,false,'offline fiber must not emit moving packets')
  FiberBuilder.updateStatus(fiber,FiberStatus.ALERT);updateVisuals(fiber,3,state)
  assert.equal(effect.visible,true);assert.equal(effect.material.uniforms.uColor.value.getHex(),0xff0000)
  assert.ok(fiber.getObjectByName('warningMarkers'))
  let disposed=0;fiber.getObjectByName('warningMarkers').children[0].children[0].geometry.addEventListener('dispose',()=>disposed++)
  FiberBuilder.updateStatus(fiber,FiberStatus.NORMAL);assert.equal(disposed,1);assert.equal(fiber.getObjectByName('warningMarkers'),undefined)
  const start=new THREE.Vector3(0,-4,0),end=new THREE.Vector3(20,-8,30)
  const pipe=PipeBuilder.build({diameter:1.5,startPosition:start,endPosition:end})
  pipe.updateMatrixWorld(true)
  const path=pipe.getObjectByName('pathEffects').geometry.parameters.path
  assert.ok(pipe.localToWorld(path.getPoint(0)).distanceTo(start)<1e-6)
  assert.ok(pipe.localToWorld(path.getPoint(1)).distanceTo(end)<1e-6)
  assert.equal(pipe.getObjectByName('pathEffects').userData.scanOnly,true)
  disposeObject(fiber);disposeObject(pipe)
  console.log('PASS: curved route fidelity, arbitrary pipe axis, controls, pause/resume/reset, hidden page, offline/recovery, alarm lifecycle, disposal')
} finally {
  // temp is a fixed sibling directory created by this test, within frontend.
  assert.equal(temp.pathname.endsWith('/frontend/.visual-test/'),true)
  await rm(temp,{recursive:true,force:true})
}
