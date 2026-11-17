import * as THREE from 'three';
import { Reflector } from 'three/examples/jsm/objects/Reflector.js';

/** A restrained, locally wet road. Cache its planar reflection while the camera is still. */
export function createRoadReflection(length:number,width:number):Reflector {
  const reflector=new Reflector(new THREE.PlaneGeometry(width,length),{
    textureWidth:1024,textureHeight:512,clipBias:.002,multisample:0,
    shader:{
      uniforms:{color:{value:new THREE.Color(0xa8bed0)},tDiffuse:{value:null},textureMatrix:{value:new THREE.Matrix4()}},
      vertexShader:`uniform mat4 textureMatrix;varying vec4 vUv;varying vec2 vRoadUv;
        void main(){vRoadUv=uv;vUv=textureMatrix*vec4(position,1.);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
      fragmentShader:`uniform sampler2D tDiffuse;varying vec4 vUv;varying vec2 vRoadUv;
        float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
        float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
          return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+1.),f.x),f.y);}
        void main(){vec2 uv=vUv.xy/vUv.w;vec2 d=vec2(.003,.003);
          vec3 reflected=texture2D(tDiffuse,uv).rgb*.4;
          reflected+=(texture2D(tDiffuse,uv+d).rgb+texture2D(tDiffuse,uv-d).rgb+texture2D(tDiffuse,uv+vec2(d.x,-d.y)).rgb+texture2D(tDiffuse,uv+vec2(-d.x,d.y)).rgb)*.15;
          float wetness=smoothstep(.28,.72,noise(vRoadUv*vec2(8.,15.))*.7+noise(vRoadUv*vec2(24.,50.))*.3);
          float edge=smoothstep(0.,.08,vRoadUv.y)*smoothstep(0.,.08,1.-vRoadUv.y);
          gl_FragColor=vec4(reflected,(.03+wetness*.30)*edge);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    },
  });
  reflector.name='wetRoadReflection';reflector.rotation.x=-Math.PI/2;reflector.position.y=.035;
  const material=reflector.material as THREE.ShaderMaterial;material.transparent=true;material.depthWrite=false;
  material.polygonOffset=true;material.polygonOffsetFactor=-1;material.polygonOffsetUnits=-1;
  reflector.raycast=()=>{};reflector.userData.visualEffect='reflection';reflector.userData.reflectionDirty=true;
  const render=reflector.onBeforeRender,world=new THREE.Matrix4(),projection=new THREE.Matrix4();
  reflector.onBeforeRender=function(...args){
    const camera=args[2];
    if(!reflector.userData.reflectionDirty&&world.equals(camera.matrixWorld)&&projection.equals(camera.projectionMatrix))return;
    render.apply(this,args);world.copy(camera.matrixWorld);projection.copy(camera.projectionMatrix);
    reflector.userData.reflectionDirty=false;
  };
  return reflector;
}

export function invalidateRoadReflection(root:THREE.Object3D):void{
  const reflector=root.getObjectByName('wetRoadReflection');
  if(reflector)reflector.userData.reflectionDirty=true;
}
