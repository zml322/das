import * as THREE from 'three';

/** Low-contrast brushed roughness, in linear data space rather than a painted highlight. */
export function createMetalRoughness():THREE.CanvasTexture{
  const canvas=document.createElement('canvas');canvas.width=128;canvas.height=512;
  const ctx=canvas.getContext('2d')!;let seed=291;
  for(let y=0;y<512;y++){
    seed=(Math.imul(seed,1664525)+1013904223)>>>0;
    const value=Math.round(150+(seed/4294967296)*45+Math.sin(y*.06)*12);
    ctx.fillStyle=`rgb(${value},${value},${value})`;ctx.fillRect(0,y,128,1);
  }
  const texture=new THREE.CanvasTexture(canvas);texture.wrapS=texture.wrapT=THREE.RepeatWrapping;
  texture.repeat.set(1,12);texture.anisotropy=4;return texture;
}
