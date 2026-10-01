(()=>{const L=window.__lib,V=THREE.Vector3,res={};
const spinAnc=o=>{let p=o;while(p){if(p.userData&&p.userData.spin)return p;p=p.parent;}return null;};
const hasAnc=(o,f)=>{let p=o;while(p){if(p.userData&&f(p.userData))return true;p=p.parent;}return false;};
const skip=o=>hasAnc(o,u=>u.flow||u.sensor||u.guard||u.tape);
const rateOf=sp=>sp.userData.spinRate===undefined?1:sp.userData.spinRate;
const axisOf=sp=>new V(sp.userData.spin==='y'?0:1,sp.userData.spin==='y'?1:0,0).transformDirection(sp.parent.matrixWorld);
function perp(a){const t=Math.abs(a.x)<0.9?new V(1,0,0):new V(0,1,0);const e1=t.clone().sub(a.clone().multiplyScalar(t.dot(a))).normalize();return [e1,a.clone().cross(e1)];}
function run(d,mode){L.show(d);const o=window.__obj();o.updateMatrixWorld(true);const out={bugs:[],meshes:0,tris:0};
 const meshes=[];o.traverse(m=>{if(m.isMesh){out.meshes++;const g=m.geometry;out.tris+=Math.round((g.index?g.index.count:g.attributes.position.count)/3);if(!skip(m))meshes.push(m);}});
 const shafts=[];meshes.forEach(m=>{const sp=spinAnc(m);if(!sp||m.geometry.type!=='CylinderGeometry')return;const p=m.geometry.parameters;if(Math.abs(p.radiusTop-p.radiusBottom)>1e-6)return;shafts.push({a:new V(0,1,0).transformDirection(m.matrixWorld),c:m.getWorldPosition(new V()),r:p.radiusTop,h:p.height});});
 const coax=(c,a,maxOff)=>shafts.filter(s=>{if(Math.abs(s.a.dot(a))<0.999)return false;const v=c.clone().sub(s.c),t=v.dot(s.a);if(Math.abs(t)>s.h/2+0.005)return false;return v.clone().sub(s.a.clone().multiplyScalar(t)).length()<=maxOff;});
 // A. bearings
 o.traverse(b=>{if(!b.userData.bearing)return;const c=b.getWorldPosition(new V()),a=new V(1,0,0).applyQuaternion(b.getWorldQuaternion(new THREE.Quaternion()));let ri=1e9,ro=0;
  b.children.forEach(ch=>{if(ch.geometry&&ch.geometry.type==='LatheGeometry')ch.geometry.parameters.points.forEach(p=>{ri=Math.min(ri,p.x);ro=Math.max(ro,p.x);});});
  const cs=coax(c,a,0.01);if(!cs.length){out.bugs.push(['A','Critical','Bearing with no shaft through it',`bore Ø${Math.round(2000*ri)} mm at (${c.x.toFixed(2)}, ${c.y.toFixed(2)}, ${c.z.toFixed(2)})`]);return;}
  const j=cs.reduce((p,q)=>q.r<p.r?q:p),bore=ri-0.002;
  if(bore>j.r*1.06+0.003)out.bugs.push(['A',bore>j.r*1.6?'Critical':'Minor',bore>j.r*1.6?'Bearing sized on a rotor/hub instead of the shaft journal':'Bearing bore slightly larger than shaft journal',`bearing bore Ø${Math.round(2000*bore)} mm, OD Ø${Math.round(2000*ro)} mm; shaft Ø${Math.round(2000*j.r)} mm at x ${c.x.toFixed(2)} y ${c.y.toFixed(2)}`]);
  else if(ro/bore>2.4)out.bugs.push(['A','Minor','Bearing OD/bore above ISO range',`OD/bore ${(ro/bore).toFixed(2)} at x ${c.x.toFixed(2)}`]);});
 // B. shaft-line continuity and rotating parts mounted on a shaft
 const roots=[];o.traverse(s=>{if(s.userData.spin&&!s.userData.tape&&!skip(s)&&!(s.parent&&spinAnc(s.parent)))roots.push(s);});
 const lines={};roots.forEach(s=>{const bb=new THREE.Box3();s.traverse(m=>{if(m.isMesh&&!skip(m))bb.expandByObject(m);});if(bb.isEmpty())return;const a=axisOf(s),cen=bb.getCenter(new V());
  const dom=Math.abs(a.y)>0.9?'y':(Math.abs(a.z)>0.9?'z':'x');const P=[cen.x,cen.y,cen.z].map(v=>Math.abs(v)<0.005?0:v);let k=dom==='x'?`x@${P[1].toFixed(2)},${P[2].toFixed(2)}`:dom==='y'?`y@${P[0].toFixed(2)},${P[2].toFixed(2)}`:`z@${P[0].toFixed(2)},${P[1].toFixed(2)}`;const kk=Object.keys(lines).find(q=>{if(q[0]!==k[0])return false;const c1=q.slice(2).split(',').map(Number),c2=k.slice(2).split(',').map(Number);return Math.hypot(c1[0]-c2[0],c1[1]-c2[1])<0.03;});if(kk)k=kk;
  (lines[k]=lines[k]||[]).push({a:bb.min[dom],b:bb.max[dom],n:s.name,int:hasAnc(s,u=>u.internal),w:rateOf(s)*Math.sign(a[dom])});
  const big=Math.max(bb.max.x-bb.min.x,bb.max.y-bb.min.y,bb.max.z-bb.min.z);let isShaft=false;s.traverse(m=>{if(m.isMesh&&m.geometry.type==='CylinderGeometry'){const p=m.geometry.parameters;const ma=new V(0,1,0).transformDirection(m.matrixWorld);if(Math.abs(ma.dot(a))>0.99&&p.height>=0.15&&(p.radiusTop<0.13||p.radiusTop<0.3*big))isShaft=true;}});
  if(!isShaft&&big>0.1){const cs=coax(cen,a,0.02).filter(q=>q.r<0.16);if(!cs.length)out.bugs.push(['B','Major','Rotating part not mounted on a shaft',`${s.name||'part'} centre (${cen.x.toFixed(2)}, ${cen.y.toFixed(2)}, ${cen.z.toFixed(2)}), size ${big.toFixed(2)} m`]);}});
 const allL=Object.entries(lines);Object.entries(lines).forEach(([k,l])=>{l.sort((p,q)=>p.a-q.a);let e=l[0].b;for(let i=1;i<l.length;i++){const g0=e,g1=l[i].a;const bridged=allL.some(([k2,l2])=>k2!==k&&k2[0]===k[0]&&(()=>{const c1=k.slice(2).split(',').map(Number),c2=k2.slice(2).split(',').map(Number);return Math.hypot(c1[0]-c2[0],c1[1]-c2[1])<0.6;})()&&l2.some(q=>q.a<=g0+0.02&&q.b>=g1-0.02));const prev=l.filter(q=>q.b<=l[i].a+0.001).sort((p,q)=>q.b-p.b)[0];const same=prev&&Math.abs(prev.w-l[i].w)<=0.01*Math.max(1,Math.abs(prev.w));if(l[i].a>e+0.01&&!bridged&&same)out.bugs.push(['B','Major','Gap in shaft line',`axis ${k}: nothing rotating between ${e.toFixed(2)} and ${l[i].a.toFixed(2)} (gap ${Math.round((l[i].a-e)*1000)} mm)`]);e=Math.max(e,l[i].b);}});
 // C. vane direction vs rotation, volute spiral vs rotation
 const imps=new Map();meshes.forEach(m=>{if(!m.userData.vane)return;const sp=spinAnc(m);if(!sp)return;const a=axisOf(sp),rt=rateOf(sp),piv=sp.getWorldPosition(new V()),[e1,e2]=perp(a);
  const P=m.geometry.attributes.position,v=new V();let pts=[];for(let i=0;i<P.count;i+=3){v.fromBufferAttribute(P,i).applyMatrix4(m.matrixWorld).sub(piv);const r=Math.hypot(v.dot(e1),v.dot(e2));pts.push([r,Math.atan2(v.dot(e2),v.dot(e1))]);}
  pts.sort((p,q)=>p[0]-q[0]);let ph=pts.map(p=>p[1]);for(let i=1;i<ph.length;i++){while(ph[i]-ph[i-1]>Math.PI)ph[i]-=2*Math.PI;while(ph[i]-ph[i-1]<-Math.PI)ph[i]+=2*Math.PI;}
  const n=pts.length,mr=pts.reduce((s,p)=>s+p[0],0)/n,mp=ph.reduce((s,p)=>s+p,0)/n;let sxy=0,sxx=0;for(let i=0;i<n;i++){sxy+=(pts[i][0]-mr)*(ph[i]-mp);sxx+=(pts[i][0]-mr)**2;}
  const sl=sxy/sxx;const key=sp.uuid;if(!imps.has(key)){const bb=new THREE.Box3().setFromObject(sp);imps.set(key,{sp,a,rt,piv:bb.getCenter(new V()),votes:0,rmax:0});}const im=imps.get(key);im.votes+=Math.sign(sl)*Math.sign(rt);im.rmax=Math.max(im.rmax,pts[n-1][0]);});
 imps.forEach(im=>{if(im.votes>0)out.bugs.push(['C','Critical','Vanes forward-curved for the set rotation (tips lead instead of trail)',`impeller/wheel Ø${Math.round(2000*im.rmax)} mm at (${im.piv.x.toFixed(2)}, ${im.piv.y.toFixed(2)}, ${im.piv.z.toFixed(2)}), rotation ${im.rt>0?'+':'-'}`]);});
 meshes.forEach(m=>{if(!m.userData.scroll&&!m.userData.scrollM)return;const av=new V(0,0,m.userData.scrollM?-1:1).transformDirection(m.matrixWorld),c=m.getWorldPosition(new V());let best=null;
  imps.forEach(im=>{if(Math.abs(im.a.dot(av))<0.99)return;const v=c.clone().sub(im.piv);const off=v.clone().sub(im.a.clone().multiplyScalar(v.dot(im.a))).length();if(off<0.1&&Math.abs(v.dot(im.a))<0.6&&(!best||off<best.off))best={im,off};});
  if(!best){out.bugs.push(['C','Major','Volute/scroll with no rotating impeller or wheel inside',`casing at (${c.x.toFixed(2)}, ${c.y.toFixed(2)}, ${c.z.toFixed(2)})`]);return;}
  if(Math.sign(best.im.a.dot(av))*Math.sign(best.im.rt)<0)out.bugs.push(['C','Critical','Volute spiral opens against the rotation',`casing at x ${c.x.toFixed(2)}`]);});
 // D. floating parts (contact graph), sunk parts, points off the surface
 const bxs=meshes.map(m=>new THREE.Box3().setFromObject(m).expandByScalar(0.006));const par=bxs.map((_,i)=>i),f=i=>par[i]===i?i:(par[i]=f(par[i]));
 for(let i=0;i<bxs.length;i++)for(let j=i+1;j<bxs.length;j++)if(bxs[i].intersectsBox(bxs[j]))par[f(i)]=f(j);
 const grp={};bxs.forEach((_,i)=>{const r=f(i);(grp[r]=grp[r]||[]).push(i);});const big=Object.values(grp).sort((p,q)=>q.length-p.length);
 big.slice(1).forEach(g=>{const bb=new THREE.Box3();g.forEach(i=>bb.union(bxs[i]));const c=bb.getCenter(new V());const nm=g.map(i=>meshes[i].material.name||'?');out.bugs.push(['D','Major','Floating part (touches nothing else)',`${g.length} mesh(es) [${[...new Set(nm)].slice(0,3).join(', ')}] at (${c.x.toFixed(2)}, ${c.y.toFixed(2)}, ${c.z.toFixed(2)})`]);});
 let sunk=0;meshes.forEach(m=>{if(hasAnc(m,u=>u.internal))return;const b=new THREE.Box3().setFromObject(m);if(b.min.y<-0.03)sunk++;});if(sunk)out.bugs.push(['D','Minor','Parts below floor level',`${sunk} meshes below y = 0`]);
 o.traverse(p=>{if(!p.userData.pt)return;const w=p.getWorldPosition(new V());let dm=1e9;meshes.forEach((m,i)=>{if(!hasAnc(m,u=>u.internal))dm=Math.min(dm,bxs[i].distanceToPoint(w));});if(dm>0.08)out.bugs.push(['D','Minor','Measurement point floating off the machine',`"${p.userData.pt.label}" is ${Math.round(dm*1000)} mm from the nearest surface`]);});
 if(out.meshes>250||out.tris>60000)out.bugs.push(['G','Minor','Above phone budget',`${out.meshes} meshes, ${out.tris} triangles`]);
 return out;}
for(const [m,l] of [['eq',L.EQ],['co',L.CO]]){L.setMode(m);for(const d of l){try{res[d.id]=run(d,m);}catch(e){res[d.id]={err:e.message};}}}
return res;})()
