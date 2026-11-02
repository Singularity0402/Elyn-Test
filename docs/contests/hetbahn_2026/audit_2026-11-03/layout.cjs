const fs=require('fs'), path=require('path'), crypto=require('crypto');
const sharp=require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const ROOT=__dirname, W=1080,H=1350;
const FONT='C:/Users/user/S-Core_Dream_OTF/';
const head=FONT+'SCDream7.otf', body=FONT+'SCDream4.otf';
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const terms='입춘 우수 경칩 춘분 청명 곡우 입하 소만 망종 하지 소서 대서 입추 처서 백로 추분 한로 상강 입동 소설 대설 동지 소한 대한'.split(' ');
if(terms.length!==24||new Set(terms).size!==24)throw Error('Calendar count');
async function renderText(e){
 const input=await sharp({text:{text:'<span foreground="'+e.color+'">'+esc(e.text)+'</span>',font:'S-Core Dream '+e.size,fontfile:e.bold?head:body,rgba:true,dpi:72}}).png().toBuffer();
 const m=await sharp(input).metadata();
 const left=Math.round(e.center?e.x-m.width/2:e.right?e.x-m.width:e.x),top=Math.round(e.y);
 if(left<12||top<12||left+m.width>W-12||top+m.height>H-12)throw Error('Text overflow '+e.text);
 return {layer:{input,left,top},bounds:{text:e.text,x:left,y:top,width:m.width,height:m.height,size:e.size}};
}
async function make(key,source,logo,els,graphic){
 const original=fs.readFileSync(source), sm=await sharp(original).metadata();
 fs.writeFileSync(path.join(ROOT,'원본과기록',key+'_선택생성원본.png'),original);
 const base=await sharp(original).resize(W,H,{fit:'cover'}).png().toBuffer();
 const layers=[],bounds=[];
 if(graphic)layers.push({input:Buffer.from(graphic),left:0,top:0});
 for(const e of els){const r=await renderText(e);layers.push(r.layer);bounds.push(r.bounds);}
 const lb=fs.readFileSync(logo),lm=await sharp(lb).metadata();
 if(lm.width!==W||lm.height!==H||!lm.hasAlpha)throw Error('Official template');
 layers.push({input:lb,left:0,top:0});
 const png=await sharp(base).composite(layers).png({compressionLevel:9}).toBuffer();
 const name=key==='A'?'A_갓지은편지':'B_스물네장의계절';
 fs.writeFileSync(path.join(ROOT,name+'.png'),png);
 await sharp(png).jpeg({quality:97,chromaSubsampling:'4:4:4'}).toFile(path.join(ROOT,name+'.jpg'));
 await sharp(png).resize(360,450).png().toFile(path.join(ROOT,'원본과기록',key+'_360폭확인.png'));
 await sharp(png).greyscale().resize(540,675).png().toFile(path.join(ROOT,'원본과기록',key+'_흑백확인.png'));
 const out=await sharp(png).ensureAlpha().raw().toBuffer(),off=await sharp(lb).ensureAlpha().raw().toBuffer();
 let opaque=0,mismatch=0;for(let i=0;i<off.length;i+=4)if(off[i+3]===255){opaque++;if(out[i]!==off[i]||out[i+1]!==off[i+1]||out[i+2]!==off[i+2])mismatch++;}
 if(!opaque||mismatch)throw Error('Official logo mismatch');
 return {key,file:name+'.png',source_dimensions:[sm.width,sm.height],final_dimensions:[W,H],source_sha256:hash(original),png_sha256:hash(png),official_logo_sha256:hash(lb),official_logo_opaque_pixels:opaque,official_logo_mismatches:mismatch,text_bounds:bounds,calendar:key==='B'?{terms,count:24,direction:'입춘부터 시계방향, 봄·여름·가을·겨울 각6개',food_samples:4,claim:'네 계절 대표 예시, 24종 전체 실물 사진 아님'}:null};
}
(async()=>{
 const sourceA=process.argv[2],sourceB=process.argv[3];if(!sourceA||!sourceB)throw Error('Sources required');
 const A=[
 {text:'밥을 데웠더니,',x:64,y:156,size:58,bold:true,color:'#f5f1e8'},
 {text:'네 그림이 피었다.',x:64,y:232,size:61,bold:true,color:'#f0c796'},
 {text:'보내온 그림을 담은 햇반.',x:67,y:312,size:23,color:'#eee6da'},
 {text:'데우면 김서림 속에 나타납니다.',x:67,y:348,size:23,color:'#eee6da'},
 {text:'갓 지은 편지 · 미래 제품 상상',x:1016,y:64,size:20,right:true,color:'#e8ddd0'},
 {text:'미래 제품 상상 · 실제 출시 제품 아님',x:1007,y:1307,size:24,right:true,color:'#fff8e9'}
 ];
 const colors=['#3f6848','#98761f','#985a38','#535d7b'];
 const B=[
 {text:'밥으로 넘기는,',x:64,y:146,size:58,bold:true,color:'#302c28'},
 {text:'스물네 장의 계절.',x:64,y:222,size:61,bold:true,color:'#b62e35'},
 {text:'24절기 햇반 컬렉션 · 네 계절 대표 디자인',x:67,y:294,size:20,color:'#5f5b53'},
 {text:'스물네 장의 계절 · 미래 제품 상상',x:1016,y:64,size:20,right:true,color:'#665f56'},
 {text:'24',x:540,y:774,size:67,bold:true,center:true,color:'#b62e35'},
 {text:'절기마다 한 공기',x:540,y:849,size:17,center:true,color:'#655e54'},
 {text:'겨울 · 무흑미밥',x:330,y:779,size:18,center:true,color:colors[3]},
 {text:'봄 · 달래보리밥',x:750,y:779,size:18,center:true,color:colors[0]},
 {text:'가을 · 밤버섯잡곡밥',x:330,y:1169,size:18,center:true,color:colors[2]},
 {text:'여름 · 옥수수기장밥',x:750,y:1169,size:18,center:true,color:colors[1]},
 {text:'미래 제품 상상 · 실제 출시 제품 아님',x:540,y:1310,size:24,center:true,color:'#625b51'}
 ];
 const cx=540,cy=810,rx=490,ry=460;
 let shapes='';
 for(let i=0;i<24;i++){
  const a=(-82.5+15*i)*Math.PI/180,c=colors[Math.floor(i/6)];
  const px=cx+rx*Math.cos(a),py=cy+ry*Math.sin(a),qx=cx+(rx-12)*Math.cos(a),qy=cy+(ry-12)*Math.sin(a);
  shapes+='<line x1="'+qx+'" y1="'+qy+'" x2="'+px+'" y2="'+py+'" stroke="'+c+'" stroke-width="2"/>';
  B.push({text:terms[i],x:cx+508*Math.cos(a),y:cy+488*Math.sin(a)-8,size:16,center:true,color:c});
 }
 shapes='<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350"><ellipse cx="540" cy="810" rx="490" ry="460" fill="none" stroke="#c8bca9" stroke-width="1"/>'+shapes+'</svg>';
 const report=[];
 report.push(await make('A',sourceA,path.join(ROOT,'원본과기록','logo_white.png'),A,null));
 report.push(await make('B',sourceB,path.join(ROOT,'원본과기록','logo_red.png'),B,shapes));
 fs.writeFileSync(path.join(ROOT,'원본과기록','출력검수.json'),JSON.stringify({entries:report,fonts:'S-Core Dream 7 / 4, copyright S-Core; font files not redistributed',photo_changes:'image generation tool only; typography, calendar and original logo composed separately'},null,2)+'\n');
 console.log(JSON.stringify(report.map(r=>({key:r.key,dimensions:r.final_dimensions,logo_pixels:r.official_logo_opaque_pixels,mismatches:r.official_logo_mismatches}))));
})();
