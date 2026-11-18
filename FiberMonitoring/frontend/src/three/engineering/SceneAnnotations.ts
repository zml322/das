import * as THREE from 'three';
type Dock='left'|'right'|'bottom';
interface Annotation {
  element:HTMLDivElement;position:THREE.Vector3;owner:THREE.Object3D;offset:number;offsetX:number;
  leader:SVGPathElement;dock?:Dock;rank:number;width:number;height:number;
}
type Rect={x:number;y:number;w:number;h:number};
export class SceneAnnotations {
  private labels:Annotation[]=[];
  private root:HTMLDivElement;
  private leaders:SVGSVGElement;
  private viewport='';
  private detailed=false;
  setDetailed(value:boolean):void { this.detailed=value; }
  private reserved:Rect[]=[];
  constructor(container:HTMLElement){
    this.root=document.createElement('div');this.root.className='scene-annotations';
    this.leaders=document.createElementNS('http://www.w3.org/2000/svg','svg');
    this.leaders.setAttribute('class','scene-annotation-leaders');this.root.appendChild(this.leaders);container.appendChild(this.root);
  }
  add(text:string,position:THREE.Vector3,owner:THREE.Object3D,tone='cyan',offset=-25,offsetX=0,placement?:{dock:Dock;rank?:number}):void {
    const element=document.createElement('div');element.className='scene-annotation '+tone;element.textContent=text;this.root.appendChild(element);
    const leader=document.createElementNS('http://www.w3.org/2000/svg','path');
    leader.setAttribute('fill','none');leader.setAttribute('stroke-width','1');leader.setAttribute('opacity','.5');
    leader.setAttribute('stroke',({red:'#ff6565',green:'#3afc8f',amber:'#ffbc48',purple:'#bc92ff'} as Record<string,string>)[tone]??'#54dbff');
    this.leaders.appendChild(leader);
    this.labels.push({element,position,owner,offset,offsetX,leader,dock:placement?.dock,rank:placement?.rank??0,width:0,height:0});
    this.viewport='';
  }
  update(camera:THREE.Camera,width:number,height:number):void {
    const lookingDown=camera.getWorldDirection(new THREE.Vector3()).y<-.72;
    const resize=this.viewport!==width+'x'+height;this.viewport=width+'x'+height;
    this.labels=this.labels.filter(label=>{
      if(label.owner.parent)return true;
      label.element.remove();label.leader.remove();return false;
    });
    if(resize){
      // Measure all labels together, including labels hidden by the previous camera/viewport.
      this.labels.forEach(label=>{label.element.hidden=false});
      this.labels.forEach(label=>{label.width=label.element.offsetWidth||130;label.height=label.element.offsetHeight||32});
      const bounds=this.root.getBoundingClientRect();
      this.reserved=[...this.root.parentElement!.parentElement!.querySelectorAll('.scene-view-tabs,.scene-playback,.annotation-toggle,.fiber-legend')].map(element=>{
        const box=element.getBoundingClientRect();return {x:box.left-bounds.left,y:box.top-bounds.top,w:box.width,h:box.height};
      });
    }
    const occupied:Rect[]=[...this.reserved];
    for(const label of [...this.labels].sort((a,b)=>Number(Boolean(b.dock))-Number(Boolean(a.dock)))){
      let owner:THREE.Object3D|null=label.owner,visible=true;
      while(owner){if(!owner.visible)visible=false;owner=owner.parent}
      const point=label.position.clone().project(camera);
      let hidden=(!this.detailed&&!label.owner.userData.eventId)||!visible||(lookingDown&&label.position.y<0)||label.owner.userData.labelVisible===false||point.z>1||point.z< -1||Math.abs(point.x)>1.15||Math.abs(point.y)>1.12;
      const anchorX=(point.x+1)*width/2,anchorY=(1-point.y)*height/2;
      let x=anchorX+label.offsetX,y=anchorY+label.offset;
      if(label.dock==='left'){x=18;y=height*(.50+label.rank*.1)-label.height/2}
      if(label.dock==='right'){x=width-label.width-20;y=height*(.53+label.rank*.09)-label.height/2}
      if(label.dock==='bottom'){x=width*.57-label.width/2;y=height-label.height-25}
      x=Math.max(12,Math.min(width-label.width-12,x));
      y=Math.max(65,Math.min(height-label.height-12,y));
      if(!hidden){
        const intersects=(cy:number)=>occupied.some(r=>x<r.x+r.w+8&&x+label.width+8>r.x&&cy<r.y+r.h+8&&cy+label.height+8>r.y);
        if(intersects(y)){
          const origin=y;let found=false;
          for(const step of [-1,1,-2,2,-3,3]){
            const trial=origin+step*(label.height+10);
            if(trial>=65&&trial+label.height<height-12&&!intersects(trial)){y=trial;found=true;break}
          }
          if(!found)hidden=true;
        }
      }
      label.element.hidden=hidden;label.leader.style.display=hidden?'none':'';
      if(hidden)continue;
      occupied.push({x,y,w:label.width,h:label.height});
      label.element.style.transform='translate('+Math.round(x)+'px,'+Math.round(y)+'px)';
      const edge=anchorX>x+label.width/2?x+label.width:x;
      const lineY=y+label.height/2;
      label.leader.setAttribute('d','M'+anchorX.toFixed(1)+' '+anchorY.toFixed(1)+' L'+(edge+(edge===x?-12:12)).toFixed(1)+' '+lineY.toFixed(1)+' L'+edge.toFixed(1)+' '+lineY.toFixed(1));
    }
  }
  dispose():void{this.root.remove();this.labels=[]}
}
