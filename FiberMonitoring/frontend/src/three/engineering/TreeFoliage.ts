import * as THREE from 'three';

/** Small alpha-cut leaf clusters supplement the scanned tree's airy species canopy. */
export function createCanopyFill(roots:THREE.Object3D[]):THREE.InstancedMesh {
  const canvas=document.createElement('canvas');canvas.width=canvas.height=256;
  const ctx=canvas.getContext('2d')!;
  for(let i=0;i<25;i++){
    const x=22+(i*71)%215,y=18+(i*113)%220;
    ctx.save();ctx.translate(x,y);ctx.rotate(i*2.399);
    ctx.fillStyle=['#517624','#89a632','#b5b339','#628f26'][i%4];
    ctx.beginPath();ctx.moveTo(0,-16);ctx.quadraticCurveTo(11,-4,0,18);ctx.quadraticCurveTo(-12,0,0,-16);ctx.fill();
    ctx.strokeStyle='#abc06b';ctx.lineWidth=.8;ctx.beginPath();ctx.moveTo(0,-12);ctx.lineTo(0,13);ctx.stroke();ctx.restore();
  }
  const map=new THREE.CanvasTexture(canvas);map.colorSpace=THREE.SRGBColorSpace;map.anisotropy=4;
  const material=new THREE.MeshLambertMaterial({map,alphaTest:.35,side:THREE.DoubleSide,emissive:0x233407,emissiveIntensity:.12});
  const cardsPerTree=700,count=roots.length*cardsPerTree;
  const leaves=new THREE.InstancedMesh(new THREE.PlaneGeometry(2.1,1.8),material,count);
  leaves.name='broadleafCanopies';leaves.castShadow=true;leaves.receiveShadow=false;
  leaves.raycast=()=>{};
  const object=new THREE.Object3D();let seed=4351;
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296};
  roots.forEach((root,index)=>{
    for(let i=0;i<cardsPerTree;i++){
      const phi=random()*Math.PI*2,cos=random()*2-1,r=Math.cbrt(random())*4.6;
      object.position.set(root.position.x+Math.cos(phi)*Math.sqrt(1-cos*cos)*r,root.position.y+9.8+cos*r*.8,root.position.z+Math.sin(phi)*Math.sqrt(1-cos*cos)*r);
      object.rotation.set(random()*Math.PI,random()*Math.PI,random()*Math.PI);
      object.scale.setScalar(.65+random()*.7);object.updateMatrix();leaves.setMatrixAt(index*cardsPerTree+i,object.matrix);
      leaves.setColorAt(index*cardsPerTree+i,new THREE.Color([0xe1e9b5,0xc7dba8,0xf0edbc,0xc9dda5][i%4]));
    }
  });
  leaves.computeBoundingSphere();return leaves;
}
