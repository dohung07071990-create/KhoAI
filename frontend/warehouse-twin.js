import { TrackInterpolator } from './digital-twin/track-interpolator.js';

const canvas = document.getElementById('warehouse-twin');
const stage = canvas?.closest('.twin-stage');
if (canvas && stage) {
  const setUnavailable = (message) => {
    stage.classList.add('twin-unavailable');
    const canvasNode=stage.querySelector('#warehouse-twin'); if(canvasNode) canvasNode.hidden=true;
    const map2d=stage.querySelector('#twin-2d-fallback'); if(map2d) map2d.hidden=false;
    stage.querySelectorAll('.twin-fallback').forEach(node => node.remove());
    const note = stage.querySelector('#twin-2d-fallback p');
    if(note) note.textContent = 'Mô hình 3D hiện không khả dụng. Đang hiển thị sơ đồ kho 2D dự phòng.';
  };

  try {
    const THREE = globalThis.__KHOAI_TEST_THREE__ || await import('https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js');
    // Bố cục nhà kho theo sơ đồ người dùng cung cấp. Tọa độ là đơn vị cảnh,
    // không phải số đo thực địa; khu vực ngoài và vùng cấm vẫn là minh họa.
    const LAYOUT = Object.freeze({
      x0:-7.5, x1:7.5, z0:-5, z1:5,
      aisleL:-1.36, aisleR:3.61, bandTop:-1.89, bandBottom:.81,
      entrance:{x0:0,x1:2.11},
      doors:{A:[-2.86,-2.03],B:[-2.86,-2.03],C:[.97,1.81],D:[.97,1.81]},
      outside:{x0:-7.5,x1:7.5,z0:-8.4,z1:-5.5},
      restricted:{x0:-2.2,x1:4.3,z0:-8,z1:-5.9},
      wallHeight:1.5,wallThickness:.14
    });
    const L=LAYOUT;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#07131e');
    scene.fog = new THREE.Fog('#07131e', 42, 78);
    // Góc nhìn lùi rộng hơn để thấy toàn bộ nhà kho, lối đi và khu vực ngoài.
    const camera = new THREE.PerspectiveCamera(46,1,.1,120);
    camera.position.set(5.5,18,22);
    camera.lookAt(0,.15,0);
    const renderer = new THREE.WebGLRenderer({canvas,antialias:true,alpha:false});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.7));
    renderer.shadowMap.enabled=true; renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    renderer.outputColorSpace=THREE.SRGBColorSpace;
    renderer.toneMapping=THREE.ACESFilmicToneMapping; renderer.toneMappingExposure=1.15;
    scene.add(new THREE.HemisphereLight('#b7e8f2','#132333',2));
    const keyLight=new THREE.DirectionalLight('#d6f4ff',2.4);
    keyLight.position.set(7,14,8); keyLight.castShadow=true;
    keyLight.shadow.mapSize.set(1024,1024);
    Object.assign(keyLight.shadow.camera,{left:-12,right:12,top:12,bottom:-12,near:1,far:45});
    keyLight.shadow.camera.updateProjectionMatrix(); scene.add(keyLight);
    const cyanLight=new THREE.PointLight('#27cde0',22,20,2); cyanLight.position.set(-6,4,-2); scene.add(cyanLight);
    const mat=(color,roughness=.72,metalness=.08,extra={})=>new THREE.MeshStandardMaterial({color,roughness,metalness,...extra});
    const floorMat=mat('#142737',.92,.12), insideFloorMat=mat('#1a3144',.9,.1), roomFloorMat=mat('#1f3a4d',.88,.08);
    const aisleMat=mat('#294a5e',.86,.08), outsideMat=mat('#0f2231',.94,.06), wallMat=mat('#2a4a5e',.85,.12);
    const rackMat=mat('#36566a',.58,.48), shelfMat=mat('#24485d',.68,.25), boxMats=[mat('#b6c6ce',.84,.02),mat('#9daeb8',.86,.02),mat('#c2ad87',.88,.01)];
    const darkMat=mat('#0b1a27',.9,.1), hazardMat=mat('#d9a93b',.6,.1,{emissive:'#5c4308',emissiveIntensity:.35});
    const doorMat=mat('#41d7e5',.4,.2,{emissive:'#147e90',emissiveIntensity:.8});
    const safeMat=mat('#20d6b1',.34,.25,{emissive:'#087d70',emissiveIntensity:.22,transparent:true,opacity:.38});
    const warnMat=mat('#f4b94e',.34,.2,{emissive:'#8d5b13',emissiveIntensity:.45,transparent:true,opacity:.48});
    const alarmMat=mat('#ff5268',.3,.2,{emissive:'#a30f30',emissiveIntensity:.7,transparent:true,opacity:.55});
    const suspiciousMat=mat('#bd8cff',.32,.18,{emissive:'#603d91',emissiveIntensity:.5,transparent:true,opacity:.5});
    const unknownMat=mat('#7890a3',.82,.04,{emissive:'#263b4b',emissiveIntensity:.12,transparent:true,opacity:.42});
    const disabledMat=mat('#647789',.9,.02,{emissive:'#263746',emissiveIntensity:.08,transparent:true,opacity:.32});
    const world=new THREE.Group(); world.position.z=1.7; scene.add(world);
    const slab=(w,h,d,material,x,y,z,opts={})=>{
      const mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),material); mesh.position.set(x,y,z);
      mesh.castShadow=!!opts.cast; mesh.receiveShadow=!!opts.receive; if(opts.kind) mesh.userData.kind=opts.kind; world.add(mesh); return mesh;
    };
    const groundCenterZ=(L.outside.z0+L.z1)/2;
    slab(18,.2,15.6,floorMat,0,-.11,groundCenterZ,{receive:true});
    const grid=new THREE.GridHelper(18,36,'#326076','#203b4d'); grid.position.set(0,-.005,groundCenterZ); grid.material.transparent=true; grid.material.opacity=.3; world.add(grid);
    slab(L.x1-L.x0-.1,.04,L.z1-L.z0-.1,insideFloorMat,0,.02,0,{receive:true,kind:'inside-floor'});
    const rooms={A:[L.x0,L.z0,L.aisleL,L.bandTop],B:[L.aisleR,L.z0,L.x1,L.bandTop],C:[L.x0,L.bandBottom,L.aisleL,L.z1],D:[L.aisleR,L.bandBottom,L.x1,L.z1]};
    const interactiveTargets=[];
    for(const [name,[xa,za,xb,zb]] of Object.entries(rooms)){
      const roomMesh=slab(xb-xa-.1,.03,zb-za-.1,roomFloorMat.clone(),(xa+xb)/2,.045,(za+zb)/2,{receive:true,kind:'room-floor'});
      roomMesh.userData.roomName=name; interactiveTargets.push(roomMesh);
    }
    slab(L.aisleR-L.aisleL-.1,.03,L.z1-L.z0-.1,aisleMat,(L.aisleL+L.aisleR)/2,.045,0,{receive:true,kind:'aisle-floor'});
    slab(L.x1-L.x0-.1,.03,L.bandBottom-L.bandTop-.1,aisleMat,0,.047,(L.bandTop+L.bandBottom)/2,{receive:true,kind:'aisle-floor'});
    for(const sx of [L.aisleL+.12,L.aisleR-.12]) for(const [za,zb] of [[L.z0+.05,L.bandTop],[L.bandBottom,L.z1-.05]]) slab(.07,.02,zb-za,hazardMat,sx,.075,(za+zb)/2);
    const hWall=(z,xa,xb)=>{const a=Math.min(xa,xb),b=Math.max(xa,xb);if(b-a>=.01)slab(b-a,L.wallHeight,L.wallThickness,wallMat,(a+b)/2,L.wallHeight/2,z,{cast:true,kind:'wall'});};
    const vWall=(x,za,zb,gap)=>{const a=Math.min(za,zb),b=Math.max(za,zb);if(gap){vWall(x,a,gap[0]);vWall(x,gap[1],b);return;}if(b-a>=.01)slab(L.wallThickness,L.wallHeight,b-a,wallMat,x,L.wallHeight/2,(a+b)/2,{cast:true,kind:'wall'});};
    hWall(L.z0,L.x0,L.entrance.x0); hWall(L.z0,L.entrance.x1,L.x1); hWall(L.z1,L.x0,L.x1);
    vWall(L.x0,L.z0,L.z1); vWall(L.x1,L.z0,L.z1);
    vWall(L.aisleL,L.z0,L.bandTop,L.doors.A); hWall(L.bandTop,L.x0,L.aisleL);
    vWall(L.aisleR,L.z0,L.bandTop,L.doors.B); hWall(L.bandTop,L.aisleR,L.x1);
    hWall(L.bandBottom,L.x0,L.aisleL); vWall(L.aisleL,L.bandBottom,L.z1,L.doors.C);
    hWall(L.bandBottom,L.aisleR,L.x1); vWall(L.aisleR,L.bandBottom,L.z1,L.doors.D);
    for(const [name,[za,zb]] of Object.entries(L.doors)){const x=(name==='A'||name==='C')?L.aisleL:L.aisleR;slab(.2,.03,zb-za,doorMat,x,.08,(za+zb)/2,{kind:'door-marker'});}
    // Kệ hàng có khung thép, mặt kệ, pallet và thùng hàng; bố trí tránh lối đi/cửa.
    function addRack(x,z,rotation=0,levels=2){
      const g=new THREE.Group();
      for(const dx of [-.68,.68]) for(const dz of [-.34,.34]){const post=new THREE.Mesh(new THREE.BoxGeometry(.075,1.75,.075),rackMat);post.position.set(dx,.88,dz);post.castShadow=true;g.add(post);}
      for(let level=0;level<levels;level++){
        const y=.32+level*.72; const shelf=new THREE.Mesh(new THREE.BoxGeometry(1.48,.075,.82),shelfMat);shelf.position.set(0,y,0);shelf.castShadow=true;shelf.receiveShadow=true;g.add(shelf);
        const pallet=new THREE.Mesh(new THREE.BoxGeometry(1.34,.09,.7),mat('#806b4e',.9,.02));pallet.position.set(0,y+.08,0);g.add(pallet);
        for(let n=0;n<3;n++){
          const bw=n===1?.38:.34,bh=.38,bd=.29;const crate=new THREE.Mesh(new THREE.BoxGeometry(bw,bh,bd),boxMats[(n+level)%boxMats.length]);
          crate.position.set((n-1)*.43,y+.31,0);crate.castShadow=true;g.add(crate);
          const band=new THREE.Mesh(new THREE.BoxGeometry(bw+.008,.035,bd+.008),mat('#536f7e',.7,.08));band.position.set(crate.position.x,y+.39,0);g.add(band);
        }
      }
      g.position.set(x,0,z);g.rotation.y=rotation;world.add(g);return g;
    }
    // Hai dãy kệ nhỏ trong mỗi phòng, giữ khoảng trống trung tâm để nhìn rõ bố cục.
    addRack(-5.95,-4.05); addRack(-3.55,-4.05); addRack(4.55,-4.05); addRack(6.55,-4.05);
    addRack(-5.95,3.95); addRack(-3.55,3.95); addRack(4.55,3.95); addRack(6.55,3.95);
    // Một số pallet/thùng đặt thấp ở cuối phòng để kho bớt trống nhưng không lấp cửa.
    function addPalletStack(x,z,count=3){
      slab(.92,.12,.72,mat('#806b4e',.9,.02),x,.13,z,{cast:true});
      for(let i=0;i<count;i++){const box=new THREE.Mesh(new THREE.BoxGeometry(.38,.42,.31),boxMats[i%boxMats.length]);box.position.set(x+(i%2? .2:-.2),.4+Math.floor(i/2)*.43,z);box.castShadow=true;world.add(box);}
    }
    addPalletStack(-6.5,-2.65,3); addPalletStack(6.5,-2.65,3); addPalletStack(-6.5,2.0,3); addPalletStack(6.5,2.0,3);
    const out=L.outside;
    slab(out.x1-out.x0,.03,out.z1-out.z0,outsideMat,(out.x0+out.x1)/2,.02,(out.z0+out.z1)/2,{receive:true,kind:'outside-floor'});
    const outsideEdges=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(out.x1-out.x0,.06,out.z1-out.z0)),new THREE.LineBasicMaterial({color:'#3d7189',transparent:true,opacity:.7}));
    outsideEdges.position.set((out.x0+out.x1)/2,.04,(out.z0+out.z1)/2);world.add(outsideEdges);
    const r=L.restricted,rw=r.x1-r.x0,rd=r.z1-r.z0,rcx=(r.x0+r.x1)/2,rcz=(r.z0+r.z1)/2;
    const zoneGroup=new THREE.Group();
    const zoneFloor=new THREE.Mesh(new THREE.BoxGeometry(rw,.035,rd),safeMat.clone());zoneFloor.position.set(rcx,.06,rcz);zoneFloor.userData.kind='zone-floor';zoneGroup.add(zoneFloor);interactiveTargets.push(zoneFloor);
    const zoneEdges=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(rw,.08,rd)),new THREE.LineBasicMaterial({color:'#24d9c0',transparent:true,opacity:.95}));zoneEdges.position.set(rcx,.1,rcz);zoneGroup.add(zoneEdges);
    const zonePosts=[];for(const [x,z] of [[r.x0,r.z0],[r.x1,r.z0],[r.x0,r.z1],[r.x1,r.z1]]){const post=new THREE.Mesh(new THREE.CylinderGeometry(.045,.06,.9,8),mat('#7edbd8',.35,.25,{emissive:'#0c6667',emissiveIntensity:.35}));post.position.set(x,.5,z);zoneGroup.add(post);zonePosts.push(post);}world.add(zoneGroup);
    const ew=L.entrance.x1-L.entrance.x0,ecx=(L.entrance.x0+L.entrance.x1)/2;
    slab(.2,1.7,.2,rackMat,L.entrance.x0,.85,L.z0,{cast:true});slab(.2,1.7,.2,rackMat,L.entrance.x1,.85,L.z0,{cast:true});
    slab(ew+.2,.22,.24,darkMat,ecx,1.62,L.z0,{cast:true});slab(ew-.1,.5,.08,mat('#8fa6b5',.5,.4),ecx,1.3,L.z0,{cast:true});
    slab(.34,.8,.3,mat('#1e4357',.5,.25),L.entrance.x0-.7,.4,L.z0-.6,{cast:true});
    slab(.2,.04,.04,mat('#42e7d1',.2,.1,{emissive:'#14c7b0',emissiveIntensity:1}),L.entrance.x0-.7,.82,L.z0-.75);
    function addCamera(x,y,z,aim,ledColor){
      const g=new THREE.Group();const mount=new THREE.Mesh(new THREE.BoxGeometry(.16,.32,.16),rackMat);mount.position.y=-.2;g.add(mount);
      const body=new THREE.Mesh(new THREE.BoxGeometry(.58,.3,.32),mat('#c2d5df',.36,.42));body.castShadow=true;g.add(body);
      const lens=new THREE.Mesh(new THREE.CylinderGeometry(.105,.105,.06,18),mat('#102a3a',.2,.55,{emissive:'#0c6579',emissiveIntensity:.55}));lens.rotation.x=Math.PI/2;lens.position.set(0,0,.19);g.add(lens);
      const led=new THREE.Mesh(new THREE.SphereGeometry(.045,10,10),mat(ledColor,.2,.1,{emissive:ledColor,emissiveIntensity:1.2}));led.position.set(.2,.08,.17);g.add(led);g.userData.led=led;
      g.position.set(x,y,z);g.rotation.y=Math.atan2(aim[0]-x,aim[1]-z);world.add(g);return g;
    }
    const usbCamera=addCamera(-5,2.4,-8,[rcx,rcz],'#42e7d1');
    const insideCamera=addCamera(-.9,1.9,-4.7,[1.1,0],'#7f9bb0');
    const trackBeacon=new THREE.Group();
    const beaconBase=new THREE.Mesh(new THREE.CylinderGeometry(.65,.78,.12,32),mat('#1b3c50',.48,.4));beaconBase.position.y=.08;trackBeacon.add(beaconBase);
    const beaconRing=new THREE.Mesh(new THREE.TorusGeometry(.55,.025,8,48),new THREE.MeshBasicMaterial({color:'#41d7e5'}));beaconRing.rotation.x=Math.PI/2;beaconRing.position.y=.2;trackBeacon.add(beaconRing);
    const trackDots=[];for(let i=0;i<12;i++){const dot=new THREE.Mesh(new THREE.SphereGeometry(.095,12,12),mat('#42d9e7',.28,.15,{emissive:'#147e90',emissiveIntensity:.65}));const a=i/12*Math.PI*2;dot.position.set(Math.cos(a)*.42,.28+Math.sin(i*2.1)*.08,Math.sin(a)*.42);trackBeacon.add(dot);trackDots.push(dot);}trackBeacon.position.set(5.9,0,-6.9);world.add(trackBeacon);
    // Live Track markers are created only from valid, camera-specific floor coordinates.
    const trackInterpolator=new TrackInterpolator({smoothingMs:220,fadeAfterMs:8000,staleAfterMs:15000});
    const spatialMarkers=new Map();
    const trackStateColors={SAFE:'#20d6b1',PASSERBY:'#20d6b1',AUTHORIZED:'#20d6b1',WARNING:'#f4b94e',REVIEW:'#f4b94e',SUSPICIOUS:'#bd8cff',ALARM:'#ff5268',UNKNOWN:'#8ba0b2'};
    function createSpatialMarker(trackId){
      const group=new THREE.Group();
      const ring=new THREE.Mesh(new THREE.TorusGeometry(.22,.025,7,28),new THREE.MeshBasicMaterial({color:'#42d9e7',transparent:true,opacity:.9}));
      ring.rotation.x=Math.PI/2;ring.position.y=.075;group.add(ring);
      const stem=new THREE.Mesh(new THREE.CylinderGeometry(.012,.012,.28,7),new THREE.MeshBasicMaterial({color:'#8be9f2',transparent:true,opacity:.72}));stem.position.y=.22;group.add(stem);
      const dot=new THREE.Mesh(new THREE.SphereGeometry(.105,12,12),new THREE.MeshStandardMaterial({color:'#42d9e7',emissive:'#147e90',emissiveIntensity:.8,roughness:.3}));dot.position.y=.39;group.add(dot);
      const label=labelSprite(`TRACK ${trackId}`,'#d9faff',1.05);label.position.set(0,.72,0);group.add(label);
      group.userData={ring,dot,stem};world.add(group);return group;
    }
    function clearSpatialMarkers(){trackInterpolator.clear();for(const marker of spatialMarkers.values())world.remove(marker);spatialMarkers.clear();}
    function updateSpatialMarkers(now=Date.now()){
      const visible=new Set();
      for(const item of trackInterpolator.step(now)){
        const bounds=spatialFloorBounds;
        if(!bounds)continue;
        const spanX=bounds.max_x-bounds.min_x,spanY=bounds.max_y-bounds.min_y;
        if(!(spanX>1e-9&&spanY>1e-9))continue;
        const nx=(item.x-bounds.min_x)/spanX,ny=(item.y-bounds.min_y)/spanY;
        // Do not extrapolate beyond the calibrated control-point envelope.
        if(nx<0||nx>1||ny<0||ny>1)continue;
        // The warehouse model is explicitly schematic; map calibrated bounds to its floor footprint.
        const x=L.x0+.45+nx*(L.x1-L.x0-.9);
        const z=L.z1-.45-ny*(L.z1-L.z0-.9);
        let marker=spatialMarkers.get(item.key);
        if(!marker){marker=createSpatialMarker(item.trackId);spatialMarkers.set(item.key,marker);}
        marker.position.set(x,.05,z);
        const color=item.stale?'#8293a1':(trackStateColors[item.state]||trackStateColors.UNKNOWN);
        marker.userData.ring.material.color.set(color);marker.userData.dot.material.color.set(color);
        marker.userData.dot.material.emissive.set(color);marker.userData.stem.material.color.set(color);
        marker.traverse(node=>{if(node.material && 'opacity' in node.material && node!==marker.userData.ring){node.material.transparent=true;node.material.opacity=item.opacity;}});
        marker.userData.ring.material.opacity=.9*item.opacity;
        visible.add(item.key);
      }
      for(const [key,marker] of spatialMarkers){if(!visible.has(key)){world.remove(marker);spatialMarkers.delete(key);}}
    }
    let spatialFloorBounds=null;
    function acceptSpatialData(data={}){
      const mapping=data.spatial_mapping||{};
      const bounds=mapping.floor_bounds;
      const boundsValid=bounds&&[bounds.min_x,bounds.max_x,bounds.min_y,bounds.max_y].every(Number.isFinite)&&
        bounds.max_x>bounds.min_x&&bounds.max_y>bounds.min_y;
      const valid=mapping.valid===true&&boundsValid&&data.camera_ok===true&&data.ai_ok===true;
      const status=document.getElementById('twin-spatial-status');
      if(!valid){spatialFloorBounds=null;clearSpatialMarkers();if(status)status.textContent=data.camera_ok!==true?'CAMERA NGOẠI TUYẾN · VỊ TRÍ CHƯA CẬP NHẬT':data.ai_ok!==true?'AI CHƯA CẬP NHẬT · VỊ TRÍ CHƯA CẬP NHẬT':mapping.valid?'KHÔNG ĐỦ PHẠM VI HIỆU CHUẨN':'CHƯA HIỆU CHUẨN · CHƯA ĐỊNH VỊ';return;}
      spatialFloorBounds=bounds;
      trackInterpolator.update(data.spatial_tracks||{}, {mappingValid:true,cameraId:mapping.camera_id,calibrationId:mapping.calibration_id});
      if(status)status.textContent=`SPATIAL MAPPING · ${mapping.floor_units||'ĐƠN VỊ SÀN'} · VỊ TRÍ TƯƠNG ĐỐI`;
    }
    const pathPoints=[new THREE.Vector3(-4.8,.1,-7.6),new THREE.Vector3(-3.6,.1,-7.1),new THREE.Vector3(-2.6,.1,-6.9),new THREE.Vector3(r.x0,.1,rcz)];
    const path=new THREE.Line(new THREE.BufferGeometry().setFromPoints(pathPoints),new THREE.LineDashedMaterial({color:'#39b9d0',dashSize:.22,gapSize:.18,transparent:true,opacity:.7}));path.computeLineDistances();world.add(path);
    // Giảm nhãn nổi: chỉ giữ tên bốn phòng, vùng cấm và lối vào; camera/Track đã có biểu tượng.
    function labelSprite(text,color='#bdebf1',scaleX=2.2){const c=document.createElement('canvas');c.width=512;c.height=96;const ctx=c.getContext('2d');ctx.fillStyle='rgba(4,17,27,.78)';ctx.strokeStyle='rgba(70,190,210,.45)';ctx.lineWidth=2;ctx.beginPath();ctx.roundRect(2,2,508,92,12);ctx.fill();ctx.stroke();let size=30;ctx.font=`600 ${size}px Arial`;while(size>16&&ctx.measureText(text).width>468){size-=2;ctx.font=`600 ${size}px Arial`;}ctx.fillStyle=color;ctx.fillText(text,22,60);const texture=new THREE.CanvasTexture(c);texture.colorSpace=THREE.SRGBColorSpace;const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthWrite:false}));sprite.scale.set(scaleX,scaleX*.1875,1);return sprite;}
    const addLabel=(text,x,y,z,color,scale)=>{const label=labelSprite(text,color,scale);label.position.set(x,y,z);world.add(label);return label;};
    addLabel('CAMERA NGOÀI · USB / AI',-5,3.15,-8.05,'#55e7d2',2.9);
    addLabel('CAMERA TRONG · ESP32-CAM',-.9,2.65,-4.7,'#b8d3e5',3.0);
    addLabel('VÙNG CẤM NGOÀI',rcx,1.1,rcz,'#bdebf1',2.6);
    addLabel('LỐI VÀO · RFID',ecx,2.5,L.z0-.4,'#bdebf1',2.4);
    for(const [name,[xa,za,xb,zb]] of Object.entries(rooms)) addLabel(`PHÒNG ${name}`,(xa+xb)/2,1.95,(za+zb)/2,'#a9bfce',1.7);

    // Inspector tương tác: chỉ cung cấp thông tin đã có; không suy diễn vị trí Track trong từng phòng.
    const inspector=document.createElement('div'); inspector.className='twin-inspector'; inspector.hidden=true;
    inspector.setAttribute('role','status'); inspector.setAttribute('aria-live','polite');
    const inspectorTitle=document.createElement('b'), inspectorBody=document.createElement('span');
    const inspectorClose=document.createElement('button'); inspectorClose.type='button'; inspectorClose.textContent='Đóng'; inspectorClose.setAttribute('aria-label','Đóng thông tin khu vực');
    inspector.append(inspectorTitle,inspectorBody,inspectorClose); stage.append(inspector);
    inspectorClose.addEventListener('click',()=>{inspector.hidden=true;});
    const raycaster=new THREE.Raycaster(), pointerNdc=new THREE.Vector2();
    function showInspector(target){
      const room=target.userData.roomName;
      if(room){
        inspectorTitle.textContent=`PHÒNG ${room}`;
        inspectorBody.textContent='Khu vực thuộc sơ đồ bố trí minh họa. Hệ thống hiện không có dữ liệu định vị người/Track riêng cho phòng này.';
      }else{
        inspectorTitle.textContent='VÙNG GIÁM SÁT NGOÀI';
        inspectorBody.textContent=`Trạng thái an ninh: ${lastState}. Người trong vùng: ${lastPeople}. Track đang theo dõi: ${lastTracks}. Trạng thái được lấy từ backend; hình khối không biểu diễn tọa độ người thực tế.`;
      }
      inspector.hidden=false;
    }
    let movedDuringPointer=false;
    stage.addEventListener('click',event=>{
      if(movedDuringPointer || event.target.closest?.('.twin-view-controls,.twin-inspector'))return;
      const rect=canvas.getBoundingClientRect(); if(rect.width<=0||rect.height<=0)return;
      pointerNdc.set(((event.clientX-rect.left)/rect.width)*2-1,-((event.clientY-rect.top)/rect.height)*2+1);
      raycaster.setFromCamera(pointerNdc,camera);
      const hit=raycaster.intersectObjects(interactiveTargets,false)[0];
      if(hit)showInspector(hit.object); else inspector.hidden=true;
    });

    // Camera orbit controls: navigation changes only the view, never AI zone geometry.
    const overviewView={x:0,y:.15,z:0,radius:29,azimuth:.245,polar:.69};
    const view={...overviewView};
    const MIN_RADIUS=17,MAX_RADIUS=43,MIN_POLAR=.28,MAX_POLAR=1.28;
    function applyView(){
      const sin=Math.sin(view.polar);
      camera.position.set(
        view.x+view.radius*sin*Math.sin(view.azimuth),
        view.y+view.radius*Math.cos(view.polar),
        view.z+view.radius*sin*Math.cos(view.azimuth)
      );
      camera.lookAt(view.x,view.y,view.z);
    }
    function zoomView(factor){view.radius=Math.max(MIN_RADIUS,Math.min(MAX_RADIUS,view.radius*factor));applyView();}
    function resetView(){Object.assign(view,overviewView);applyView();}
    function panView(dx,dy){
      const scale=view.radius*.0017;
      const rightX=Math.cos(view.azimuth), rightZ=-Math.sin(view.azimuth);
      const forwardX=-Math.sin(view.azimuth), forwardZ=-Math.cos(view.azimuth);
      view.x+=(-dx*rightX+dy*forwardX)*scale;
      view.z+=(-dx*rightZ+dy*forwardZ)*scale;
      view.y=Math.max(-1,Math.min(4,view.y+dy*scale*.35));
      applyView();
    }
    applyView();
    const activePointers=new Map();
    let dragMode='rotate',lastPointer=null,lastPinchDistance=0;
    stage.addEventListener('contextmenu',e=>e.preventDefault());
    stage.addEventListener('pointerdown',e=>{
      if(e.target.closest?.('.twin-view-controls'))return;
      activePointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
      stage.setPointerCapture?.(e.pointerId);
      if(activePointers.size===1){movedDuringPointer=false;dragMode=(e.button===2||e.button===1||e.shiftKey)?'pan':'rotate';lastPointer={x:e.clientX,y:e.clientY};}
      else if(activePointers.size===2){const pts=[...activePointers.values()];lastPinchDistance=Math.hypot(pts[0].x-pts[1].x,pts[0].y-pts[1].y);}
    });
    stage.addEventListener('pointermove',e=>{
      if(!activePointers.has(e.pointerId))return;
      const prev=activePointers.get(e.pointerId),dx=e.clientX-prev.x,dy=e.clientY-prev.y;
      if(Math.abs(e.clientX-(lastPointer?.x??e.clientX))>5||Math.abs(e.clientY-(lastPointer?.y??e.clientY))>5)movedDuringPointer=true;
      activePointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
      if(activePointers.size>=2){
        const pts=[...activePointers.values()],distance=Math.hypot(pts[0].x-pts[1].x,pts[0].y-pts[1].y);
        if(lastPinchDistance>0&&distance>0)zoomView(lastPinchDistance/distance);
        lastPinchDistance=distance;
      }else if(dragMode==='pan')panView(dx,dy);
      else {view.azimuth-=dx*.006;view.polar=Math.max(MIN_POLAR,Math.min(MAX_POLAR,view.polar+dy*.004));applyView();}
    });
    const releasePointer=e=>{activePointers.delete(e.pointerId);if(activePointers.size<2)lastPinchDistance=0;if(!activePointers.size)lastPointer=null;};
    stage.addEventListener('pointerup',releasePointer);
    stage.addEventListener('pointercancel',releasePointer);
    // Keep ordinary wheel input available for page scrolling; Ctrl+wheel zooms the model.
    stage.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();zoomView(e.deltaY>0?1.08:.92);},{passive:false});
    stage.querySelectorAll('[data-twin-action]').forEach(button=>button.addEventListener('click',()=>{
      const action=button.dataset.twinAction;
      if(action==='zoom-in')zoomView(.82);
      else if(action==='zoom-out')zoomView(1.22);
      else if(action==='reset')resetView();
    }));

    let lastState='UNKNOWN', lastPeople=0, lastTracks=0, systemOnline=null, antiTheftEnabled=null, backendOnline=false, lastDataAt=null;
    const stateColor={SAFE:'#20d6b1',PASSERBY:'#20d6b1',AUTHORIZED:'#20d6b1',WARNING:'#f4b94e',REVIEW:'#f4b94e',SUSPICIOUS:'#bd8cff',ALARM:'#ff5268',UNKNOWN:'#7890a3',DISABLED:'#647789',OFFLINE:'#647789'};
    const stateMat={SAFE:safeMat,PASSERBY:safeMat,AUTHORIZED:safeMat,WARNING:warnMat,REVIEW:warnMat,SUSPICIOUS:suspiciousMat,ALARM:alarmMat,UNKNOWN:unknownMat,DISABLED:disabledMat,OFFLINE:unknownMat};
    function setState(state, people, tracks, data={}) {
      lastState=state||'UNKNOWN'; lastPeople=Number(people)||0; lastTracks=Number(tracks)||0;
      if(data.anti_theft_enabled===false) lastState='DISABLED';
      else if(data.anti_theft_enabled==null && lastState==='SAFE') lastState='UNKNOWN';
      const color=stateColor[lastState]||stateColor.UNKNOWN;
      zoneFloor.material=stateMat[lastState]||unknownMat;
      zoneEdges.material.color.set(color);
      zonePosts.forEach(p=>p.material.emissive.set(color));
      usbCamera.userData.led.material.color.set(data.camera_ok===false?'#ff5268':color);
      usbCamera.userData.led.material.emissive.set(data.camera_ok===false?'#a30f30':color);
      trackDots.forEach((dot,i)=>{dot.visible=i<Math.min(lastTracks,trackDots.length);dot.material.color.set(i<lastPeople?'#ffbd58':'#42d9e7');dot.material.emissive.set(i<lastPeople?'#9a5512':'#147e90');});
      const stateEl=document.getElementById('twin-state'); if(stateEl) stateEl.textContent=({SAFE:'An toàn',PASSERBY:'Người đi qua',AUTHORIZED:'Đã xác thực',WARNING:'Cảnh báo',REVIEW:'Cần kiểm tra',SUSPICIOUS:'Đáng ngờ',ALARM:'Báo động',UNKNOWN:'Chưa xác định',DISABLED:'Đã tắt',OFFLINE:'Mất kết nối'})[lastState]||'Chưa xác định';
      const card=document.getElementById('twin-state-card'); if(card) card.dataset.state=lastState;
      const reason=document.getElementById('twin-state-reason');
      if(reason) reason.textContent=lastState==='DISABLED'?'Chống trộm đang tắt · vùng bảo vệ không được giám sát':lastState==='UNKNOWN'?'Không đủ dữ liệu để xác nhận trạng thái an ninh':data.camera_ok===false?'Camera USB chưa kết nối':data.ai_ok===false?'Pipeline AI chưa có frame mới':lastPeople>0?`${lastPeople} người đang được ghi nhận trong vùng bảo vệ`:`${lastTracks} Track đang được theo dõi · không ghi nhận người trong vùng`;
      const peopleEl=document.getElementById('twin-people'); if(peopleEl) peopleEl.textContent=lastPeople;
      const tracksEl=document.getElementById('twin-tracks'); if(tracksEl) tracksEl.textContent=lastTracks;
      const fpsEl=document.getElementById('twin-fps'); if(fpsEl) fpsEl.textContent=data.process_fps==null?'–':Number(data.process_fps).toFixed(1);
      const latencyEl=document.getElementById('twin-latency'); if(latencyEl) latencyEl.textContent=data.process_latency_ms==null?'–':`${Math.round(data.process_latency_ms)} ms`;
      const sync=document.getElementById('twin-sync-label'); if(sync) sync.textContent=lastState==='DISABLED'?'TẮT CHỐNG TRỘM':data.camera_ok===false?'CAMERA NGOẠI TUYẾN':data.ai_ok===false?'AI CHƯA CẬP NHẬT':lastState==='UNKNOWN'?'TRẠNG THÁI KHÔNG RÕ':'ĐANG NHẬN DỮ LIỆU TRỰC TIẾP';
      const cameraStatus=document.getElementById('twin-camera-status'); if(cameraStatus) cameraStatus.textContent=data.camera_ok===false?'Ngoại tuyến':data.ai_ok===false?'Frame cũ':'Trực tuyến';
      const cameraDot=document.getElementById('twin-camera-dot'); if(cameraDot) cameraDot.className=data.camera_ok===false?'is-down':data.ai_ok===false?'is-warn':'is-up';
      const trackerStatus=document.getElementById('twin-tracker-status'); if(trackerStatus) trackerStatus.textContent=data.tracking_enabled?'Đang chạy':'Không khả dụng';
      const trackerDot=document.getElementById('twin-tracker-dot'); if(trackerDot) trackerDot.className=data.tracking_enabled?'is-up':'is-warn';
      const clock=document.getElementById('twin-clock'); if(clock) clock.textContent=new Date().toLocaleTimeString('vi-VN');
      const systemState=document.getElementById('twin-state-card'); if(systemState) systemState.dataset.antiTheft=antiTheftEnabled===false?'disabled':'enabled';
    }

    let lastWidth=0, lastHeight=0;
    function resize() {
      // A hidden tab reports a 0x0 box. Never resize the WebGL canvas from
      // that transient measurement; wait until the overview is visible again.
      const rect=stage.getBoundingClientRect();
      const w=Math.floor(rect.width), h=Math.floor(rect.height);
      if (w <= 1 || h <= 1) return false;
      // Ignore sub-pixel/no-op observer notifications to avoid resize feedback.
      if (w === lastWidth && h === lastHeight) return true;
      lastWidth=w; lastHeight=h;
      renderer.setSize(w,h,false);
      camera.aspect=w/h;
      camera.updateProjectionMatrix();
      return true;
    }
    let resizeRaf=0;
    function scheduleResize() {
      if (resizeRaf) cancelAnimationFrame(resizeRaf);
      resizeRaf=requestAnimationFrame(()=>{resizeRaf=0;resize();});
    }
    const observer=new ResizeObserver(scheduleResize); observer.observe(stage); scheduleResize();
    // The dashboard uses display:none for inactive pages. Explicitly measure
    // after the overview is restored, once layout has completed.
    window.addEventListener('khoai-tab-changed', event=>{
      if (event.detail?.tab === 'overview') {
        scheduleResize();
        requestAnimationFrame(()=>requestAnimationFrame(resize));
      }
    });
    window.addEventListener('resize',scheduleResize,{passive:true});
    const clock=new THREE.Clock();
    let rafId=0, lastFrameAt=0, inViewport=true;
    const reduceMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const frameInterval=1000/30;
    function animate(now=0) {
      rafId=0;
      if(document.hidden || !inViewport) return;
      if(now-lastFrameAt < frameInterval){rafId=requestAnimationFrame(animate);return;}
      lastFrameAt=now;
      const t=clock.getElapsedTime();
      // Camera orbit is controlled by view/applyView; do not apply the removed
      // No legacy rotation interpolation is needed here.
      if(!reduceMotion){beaconRing.rotation.z=t*.5; trackBeacon.position.y=.03+Math.sin(t*1.5)*.035; path.material.dashOffset=-t*.3; zoneEdges.material.opacity=lastState==='ALARM'?.48+Math.abs(Math.sin(t*4))*.48:lastState==='WARNING'?.62+Math.sin(t*2.2)*.12:.78; if(lastState==='ALARM')zoneFloor.material.emissiveIntensity=.18+Math.abs(Math.sin(t*4))*.42;else zoneFloor.material.emissiveIntensity=lastState==='WARNING'?.25:stateMat[lastState]?.emissiveIntensity??.12;}
      try {
        updateSpatialMarkers(Date.now());
        renderer.render(scene,camera);
      } catch (renderError) {
        console.error('KhoAI 3D render failed:', renderError);
        setUnavailable(`Không thể dựng khung hình 3D: ${renderError?.message || 'Lỗi WebGL không xác định'}`);
        return;
      }
      rafId=requestAnimationFrame(animate);
    }
    function resumeRender(){if(!document.hidden && inViewport && !rafId) rafId=requestAnimationFrame(animate);}
    document.addEventListener('visibilitychange',()=>{if(document.hidden && rafId){cancelAnimationFrame(rafId);rafId=0;}else resumeRender();});
    const visibilityObserver=new IntersectionObserver(entries=>{inViewport=entries.some(entry=>entry.isIntersecting);if(!inViewport && rafId){cancelAnimationFrame(rafId);rafId=0;}else resumeRender();},{threshold:.05});
    visibilityObserver.observe(stage); resumeRender();
    setInterval(()=>{
      const age=document.getElementById('twin-data-age');
      if(age && !backendOnline && lastDataAt){age.textContent=`DỮ LIỆU CUỐI CÁCH ĐÂY ${Math.max(0,Math.floor((Date.now()-lastDataAt)/1000))} GIÂY`;}
    },1000);
    window.KhoAIWarehouseTwin={
      layout: LAYOUT,
      resize: scheduleResize,
      resetView,
      zoomIn:()=>zoomView(.82),
      zoomOut:()=>zoomView(1.22),
      update(data={}) {
        backendOnline=true; lastDataAt=Date.now(); antiTheftEnabled=typeof data.anti_theft_enabled==='boolean'?data.anti_theft_enabled:null;
        const tracks=Object.values(data.decision_tracks||{});
        if(data.frame_stale){
          clearSpatialMarkers();
          setState('UNKNOWN',0,0,{camera_ok:true,ai_ok:false});
          const stateEl=document.getElementById('twin-state'); if(stateEl) stateEl.textContent='Dữ liệu cũ';
          const why=document.getElementById('twin-state-reason'); if(why) why.textContent='Khung hình đã cũ · trạng thái an ninh hiện tại chưa xác định';
          const sync=document.getElementById('twin-sync-label'); if(sync) sync.textContent='DỮ LIỆU CŨ';
          const cam=document.getElementById('twin-camera-status'); if(cam) cam.textContent='Không có frame mới';
          const age=document.getElementById('twin-data-age'); if(age) age.textContent=`KHUNG HÌNH CŨ · ${Math.round(Number(data.frame_age_ms)||0)} ms`;
          return;
        }
        const state=data.anti_theft_enabled===false?'DISABLED':data.alarm_state==='ALARM'?'ALARM':tracks.some(t=>t.state==='SUSPICIOUS')?'SUSPICIOUS':data.alarm_state||'UNKNOWN';
        setState(state,data.people_in_zone,tracks.length,data);
        acceptSpatialData(data);
        const age=document.getElementById('twin-data-age'); if(age) age.textContent='DỮ LIỆU VỪA CẬP NHẬT';
      },
      markOffline(reason='Backend không phản hồi') {
        backendOnline=false; clearSpatialMarkers(); spatialFloorBounds=null; const spatialStatus=document.getElementById('twin-spatial-status'); if(spatialStatus) spatialStatus.textContent='MẤT KẾT NỐI HỆ THỐNG · VỊ TRÍ CHƯA CẬP NHẬT'; const age=document.getElementById('twin-data-age');
        const elapsed=lastDataAt?Math.max(0,Math.floor((Date.now()-lastDataAt)/1000)):null;
        setState('OFFLINE',0,0,{camera_ok:false,ai_ok:false});
        const stateEl=document.getElementById('twin-state'); if(stateEl) stateEl.textContent='MẤT KẾT NỐI';
        const why=document.getElementById('twin-state-reason'); if(why) why.textContent=`MẤT KẾT NỐI HỆ THỐNG · ${reason}`;
        const sync=document.getElementById('twin-sync-label'); if(sync) sync.textContent='MẤT KẾT NỐI HỆ THỐNG';
        const cam=document.getElementById('twin-camera-status'); if(cam) cam.textContent='Không xác định';
        const fps=document.getElementById('twin-fps'); if(fps) fps.textContent='–';
        const latency=document.getElementById('twin-latency'); if(latency) latency.textContent='–';
        if(age) age.textContent=elapsed===null?'CHƯA CÓ DỮ LIỆU':`DỮ LIỆU CUỐI CÁCH ĐÂY ${elapsed} GIÂY`;
      },
      updateSpatial: acceptSpatialData,
      updateSystem(data={}) {
        systemOnline=Boolean(data.device_online);
        const status=document.getElementById('twin-esp-status'); if(status) status.textContent=systemOnline?'Trực tuyến':'Ngoại tuyến';
        const dot=document.getElementById('twin-esp-dot'); if(dot) dot.className=systemOnline?'is-up':'is-down';
      }
    };
    window.dispatchEvent(new CustomEvent('khoai-twin-ready'));
  } catch (error) {
    // Keep implementation/network details in the developer console only.
    // The fallback is a user-facing status, not a raw CDN/import error dump.
    console.warn('KhoAI 3D twin unavailable:', error);
    setUnavailable('3D unavailable');
  }
}
