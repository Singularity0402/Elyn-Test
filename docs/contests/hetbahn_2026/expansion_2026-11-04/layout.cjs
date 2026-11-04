'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const sharp=require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const ROOT=__dirname,W=1080,H=1350,RECORD=path.join(ROOT,'원본과기록'),PRIVATE=path.join(ROOT,'.private');
const CACHE=path.resolve(ROOT,'../automation_2026-11-03/.private');
const FONT='C:/Users/user/S-Core_Dream_OTF/';
const FOOT='미래 제품 상상 · 실제 출시 제품 아님';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const lum=rgb=>rgb.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
const contrast=(a,b)=>{const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
const overlaps=(a,b)=>Math.min(a.x+a.width,b.x+b.width)>Math.max(a.x,b.x)&&Math.min(a.y+a.height,b.y+b.height)>Math.max(a.y,b.y);
async function textLayer(e){
 const bytes=await sharp({text:{text:'<span foreground="'+e.color+'">'+esc(e.text)+'</span>',font:'S-Core Dream '+e.size,fontfile:FONT+(e.bold?'SCDream7.otf':'SCDream4.otf'),rgba:true,dpi:72}}).png().toBuffer();
 const m=await sharp(bytes).metadata(),x=Math.round(e.center?e.x-m.width/2:e.right?e.x-m.width:e.x),y=Math.round(e.y);
 const bounds={text:e.text,x,y,width:m.width,height:m.height,size:e.size,color:e.color,role:e.role||'copy'};
 if(x<24||y<24||x+m.width>W-24||y+m.height>H-18)throw Error('Unsafe text bounds '+e.text);
 return {input:bytes,left:x,top:y,bounds};
}
async function make(a){
 const fallback=path.join(RECORD,a.key+'_선택생성원본.png');
 const source=fs.readFileSync(fs.existsSync(a.native)?a.native:fallback),sourceMeta=await sharp(source,{failOn:'warning'}).metadata();
 const sourceName=a.key+'_선택생성원본.png';
 fs.writeFileSync(path.join(RECORD,sourceName),source);
 const base=await sharp(source).resize(W,H,{fit:'cover'}).toColourspace('srgb').png().toBuffer();
 const es=[
 {text:a.headline[0],x:64,y:a.key==='G'?142:156,size:a.key==='G'?60:62,bold:true,color:a.colors[0],role:'headline'},
 {text:a.headline[1],x:64,y:a.key==='G'?214:236,size:a.key==='G'?62:64,bold:true,color:a.colors[1],role:'headline'},
 {text:a.sub,x:67,y:a.key==='G'?289:322,size:a.key==='G'?24:25,color:a.colors[2],role:'sub'},
 {text:a.title+' · 미래 제품 상상',x:a.key==='H'?67:1016,y:a.key==='H'?370:65,size:20,right:a.key!=='H',color:a.colors[2],role:'concept'},
 {text:FOOT,x:a.key==='C'?64:1016,y:1302,size:24,right:a.key!=='C',color:a.key==='H'?'#14232c':a.colors[2],role:'footer'}
 ];
 const tl=[];for(const e of es)tl.push(await textLayer(e));
 for(let i=0;i<tl.length;i++)for(let j=i+1;j<tl.length;j++)if(overlaps(tl[i].bounds,tl[j].bounds))throw Error('Text collision '+a.key);
 const logoBounds={x:64,y:49,width:170,height:69};for(const t of tl)if(overlaps(t.bounds,logoBounds))throw Error('Logo collision');
 fs.writeFileSync(path.join(PRIVATE,a.key+'_resized_photo.png'),base);
 const background=await sharp(base).ensureAlpha().raw().toBuffer();
 const contrastRows=[];
 for(const t of tl){
  const {data,info}=await sharp(t.input).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  const rgb=t.bounds.color.slice(1).match(/../g).map(v=>parseInt(v,16));let min=99,checked=0;
  for(let y=0;y<info.height;y++)for(let x=0;x<info.width;x++)if(data[(y*info.width+x)*4+3]>=220){
   const i=((t.top+y)*W+t.left+x)*4;min=Math.min(min,contrast(rgb,[background[i],background[i+1],background[i+2]]));checked++;
  }
  if(!checked||min<4.5)throw Error('Text contrast '+a.key+' '+t.bounds.text+' '+min);
  contrastRows.push({text:t.bounds.text,minimum_ratio:+min.toFixed(3),sampled_glyph_pixels:checked,target:4.5,note:'내부 조판 목표; 실제 인간 가독성·시선 측정 아님'});
 }
 const pre=await sharp(base).composite(tl.map(({input,left,top})=>({input,left,top}))).png().toBuffer();
 fs.writeFileSync(path.join(PRIVATE,a.key+'_before_logo.png'),pre);
 const logo=fs.readFileSync(path.join(CACHE,'logo_'+a.logo+'.png'));
 const policy=JSON.parse(fs.readFileSync(path.resolve(ROOT,'../automation_2026-11-03/policy.json'),'utf8'));
 if(sha(logo)!==policy.logos[a.logo].sha256)throw Error('Official logo hash mismatch');
 const final=await sharp(pre).composite([{input:logo,left:0,top:0}]).png({compressionLevel:9}).toBuffer();
 const expected=await sharp(pre).composite([{input:logo,left:0,top:0}]).ensureAlpha().raw().toBuffer();
 const actual=await sharp(final).ensureAlpha().raw().toBuffer(),lo=await sharp(logo).ensureAlpha().raw().toBuffer();let visible=0,mismatch=0;
 for(let i=0;i<lo.length;i+=4)if(lo[i+3]>0){visible++;if(actual[i]!==expected[i]||actual[i+1]!==expected[i+1]||actual[i+2]!==expected[i+2]||actual[i+3]!==expected[i+3])mismatch++;}
 if(!visible||mismatch)throw Error('Official logo alpha pixels mismatch');
 fs.writeFileSync(path.join(ROOT,a.stem+'.png'),final);
 await sharp(final).jpeg({quality:97,chromaSubsampling:'4:4:4'}).toFile(path.join(ROOT,a.stem+'.jpg'));
 await sharp(final).resize(360,450).png().toFile(path.join(RECORD,a.key+'_360폭.png'));
 await sharp(final).greyscale().resize(360,450).png().toFile(path.join(RECORD,a.key+'_흑백360.png'));
 fs.writeFileSync(path.join(ROOT,a.key+'_제출문구.md'),'# '+a.title+'\n\n주제: '+a.theme+'\n\n## 신청서 설명\n\n'+a.description+'\n\n공백 포함 '+[...a.description].length+'자 / 500자 제한\n\n## AI 활용\n\n'+a.service+'. 제품·음식·손·포장 장면을 생성하고 검토 지적에 따라 수정했습니다. 한국어 문구는 S-Core Dream으로 별도 조판하고, 공식 제공 로고를 원본 그대로 합성했습니다. 실제 제작 히스토리 화면 캡처는 별도 제출해야 합니다.\n\n## SNS 캡션\n\n'+a.caption+'\n','utf8');
 if([...a.description].length>500)throw Error('Description exceeds500');
 return {key:a.key,title:a.title,file:a.stem+'.png',jpg:a.stem+'.jpg',source:path.join('원본과기록',sourceName).replaceAll('\\','/'),selected_version:a.version,source_dimensions:[sourceMeta.width,sourceMeta.height],source_sha256:sha(source),final_dimensions:[W,H],png_sha256:sha(final),logo_variant:a.logo,logo_sha256:sha(logo),logo_alpha_positive_pixels:visible,logo_mismatches:mismatch,text_bounds:tl.map(t=>t.bounds),contrast:contrastRows,description_chars:[...a.description].length};
}
(async()=>{
 fs.mkdirSync(PRIVATE,{recursive:true});fs.mkdirSync(RECORD,{recursive:true});
 const assets=JSON.parse(fs.readFileSync(path.join(ROOT,'assets.json'),'utf8'));
 const entries=[];for(const a of assets.entries)entries.push(await make(a));
 const records={date:assets.date,scope:assets.scope,entries,notice:FOOT,limitation:'파일·조판 검사는 실제 제품 성능·사람 반응·수상 검증이 아니다.'};
 fs.writeFileSync(path.join(RECORD,'출력검수.json'),JSON.stringify(records,null,2)+'\n','utf8');
 const layers=[],CW=1080,CH=980;
 for(let i=0;i<entries.length;i++){
  const a=entries[i],x=(i%3)*360,y=Math.floor(i/3)*490;
  layers.push({input:await sharp(path.join(ROOT,a.file)).resize(360,450).toBuffer(),left:x,top:y});
  const label=await textLayer({text:a.key+' · '+a.title,x:40,y:24,size:20,color:'#2b2825'});
  layers.push({input:label.input,left:x+18,top:y+462});
 }
 await sharp({create:{width:CW,height:CH,channels:3,background:'#f8f5ef'}}).composite(layers).png().toFile(path.join(ROOT,'추가6작품_한눈에.png'));
 for(const group of [['C','D','E'],['F','G','H']]){
  const ps=[];for(let i=0;i<3;i++){const a=entries.find(a=>a.key===group[i]);ps.push({input:await sharp(path.join(ROOT,a.file)).resize(360,450).png().toBuffer(),left:i*360,top:0});}
  await sharp({create:{width:1080,height:450,channels:3,background:'#ffffff'}}).composite(ps).png().toFile(path.join(RECORD,group.join('')+'_360실제축소.png'));
 }
 console.log(JSON.stringify(entries.map(e=>({key:e.key,source:e.source_dimensions,logo_mismatches:e.logo_mismatches,min_text_contrast:Math.min(...e.contrast.map(c=>c.minimum_ratio)),description_chars:e.description_chars}))));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
