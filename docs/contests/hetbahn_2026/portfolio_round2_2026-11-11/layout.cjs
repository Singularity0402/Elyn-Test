'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const sharp=require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const root=__dirname,project=path.resolve(root,'..'),W=1080,H=1350,FONT='C:/Users/user/S-Core_Dream_OTF/';
const records=path.join(root,'원본과기록');fs.mkdirSync(records,{recursive:true});
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const lum=a=>a.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
const contrast=(a,b)=>{let x=lum(a),y=lum(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
const overlap=(a,b)=>Math.min(a.x+a.width,b.x+b.width)>Math.max(a.x,b.x)&&Math.min(a.y+a.height,b.y+b.height)>Math.max(a.y,b.y);
async function txt(d){
 const buf=await sharp({text:{text:'<span foreground="'+d.color+'">'+esc(d.text)+'</span>',font:'S-Core Dream '+d.size,fontfile:FONT+(d.bold?'SCDream7.otf':'SCDream4.otf'),rgba:true,dpi:72}}).png().toBuffer();
 const m=await sharp(buf).metadata(),x=d.right?d.x-m.width:d.x;
 return {input:buf,left:x,top:d.y,bounds:{text:d.text,x,y:d.y,width:m.width,height:m.height,color:d.color}};
}
async function make(a){
 const src=fs.readFileSync(a.native),sm=await sharp(src).metadata();
 fs.writeFileSync(path.join(records,a.key+'_선택생성원본.png'),src);
 let base=await sharp(src).resize(W,H,{fit:'cover'}).toColourspace('srgb').png().toBuffer();
 const labels=[],rects=[];
 for(const c of a.chips||[]){
   const l=await txt({text:c.text,x:c.x+14,y:c.y+11,size:22,color:'#fff5e6'});
   labels.push(l);
   const r=Buffer.from('<svg width="'+W+'" height="'+H+'"><rect x="'+c.x+'" y="'+c.y+'" width="'+(l.bounds.width+28)+'" height="'+(l.bounds.height+22)+'" rx="8" fill="#102232" fill-opacity=".94"/></svg>');
   rects.push({input:r,left:0,top:0});
 }
 if(a.key==='J')rects.push({input:Buffer.from('<svg width="1080" height="1350"><rect x="0" y="1284" width="1080" height="66" fill="#102232"/></svg>'),left:0,top:0}); if(rects.length)base=await sharp(base).composite(rects).png().toBuffer();
 const defs=[
 {text:a.headline[0],x:64,y:a.key==='K'?130:156,size:a.key==='K'?38:59,bold:true,color:a.colors?.[0]||'#fff3df'},
 {text:a.headline[1],x:64,y:a.key==='K'?180:232,size:a.key==='K'?40:62,bold:true,color:a.colors?.[1]||'#f5c27d'},
 ...a.sub.map((text,i)=>({text,x:a.key==='K'?720:67,y:a.key==='K'?388+i*53:314+i*35,size:a.key==='K'?31:25,color:a.colors?.[2]||'#fff3df'})),
 {text:a.title+' · 미래 상상',x:['I','K'].includes(a.key)?260:1016,y:65,size:22,right:!['I','K'].includes(a.key),color:a.colors?.[2]||'#fff3df'},
 {text:a.footer,x:1016,y:1298,size:26,right:true,color:a.footerColor||'#fff3df'}
 ];
 if(a.key==='K')defs.push({text:'미래 제휴 일터 구상',x:720,y:505,size:20,color:'#bce3e4'}); for(const d of defs)labels.push(await txt(d));
 const bg=await sharp(base).ensureAlpha().raw().toBuffer(),checks=[];
 for(let i=0;i<labels.length;i++){
   const t=labels[i],b=t.bounds;
   if(b.x<24||b.y<24||b.x+b.width>W-24||b.y+b.height>H-18)throw Error('text bounds '+b.text);
   if(overlap(b,{x:64,y:49,width:170,height:69}))throw Error('logo overlap');
   for(let j=i+1;j<labels.length;j++)if(overlap(b,labels[j].bounds))throw Error('text collision');
   const {data,info}=await sharp(t.input).ensureAlpha().raw().toBuffer({resolveWithObject:true});
   const fg=b.color.slice(1).match(/../g).map(s=>parseInt(s,16));let min=100,n=0;
   for(let y=0;y<info.height;y++)for(let x=0;x<info.width;x++)if(data[(y*info.width+x)*4+3]>=220){
     const k=((b.y+y)*W+b.x+x)*4;min=Math.min(min,contrast(fg,[bg[k],bg[k+1],bg[k+2]]));n++;
   }
   if(!n||min<4.5)throw Error('contrast '+a.key+' '+b.text+' '+min);
   checks.push({text:b.text,min_contrast:min,pixels:n});
 }
 fs.mkdirSync(path.join(root,'.private'),{recursive:true}); fs.writeFileSync(path.join(root,'.private',a.key+'_background.png'),base); const pre=await sharp(base).composite(labels.map(({input,left,top})=>({input,left,top}))).png().toBuffer();
 const policy=JSON.parse(fs.readFileSync(path.join(project,'automation_2026-11-03/policy.json'),'utf8'));
 const logo=fs.readFileSync(path.join(project,'automation_2026-11-03/.private/logo_'+a.logo+'.png'));
 if(sha(logo)!==policy.logos[a.logo].sha256)throw Error('official logo source');
 fs.writeFileSync(path.join(root,'.private',a.key+'_prelogo.png'),pre); const fin=await sharp(pre).composite([{input:logo,left:0,top:0}]).png({compressionLevel:9}).toBuffer();
 fs.writeFileSync(path.join(root,a.stem+'.png'),fin);
 await sharp(fin).jpeg({quality:97,chromaSubsampling:'4:4:4'}).toFile(path.join(root,a.stem+'.jpg'));
 await sharp(fin).resize(360,450).png().toFile(path.join(records,a.key+'_360폭.png'));
 await sharp(fin).greyscale().resize(360,450).png().toFile(path.join(records,a.key+'_흑백360.png'));
 const caption=a.headline.join(' ')+'\n\n'+a.sub.join(' ')+'\n\nAI로 만든 미래 상상 이미지입니다. 실제 출시 제품·시행 서비스가 아닙니다.\n\n@hetbahn.30years\n#햇반 #햇반AI공모전 #갓지은아이디어';
 if([...a.description].length>500)throw Error('description500');
 fs.writeFileSync(path.join(root,a.key+'_제출문구.md'),'# '+a.title+'\n\n'+a.theme+'\n\n## 작품 설명\n'+a.description+'\n\n공백 포함 '+[...a.description].length+'자 /500자\n\n## AI 활용\nOpenAI Codex 내장 이미지 생성 기능으로 장면을 생성·수정했습니다. 한글과 공식 제공 로고는 별도 조판했습니다.\n\n## SNS 문구\n'+caption+'\n\n실제 서비스 제작 화면 캡처는 별도로 확보해야 합니다.\n','utf8');
 return {key:a.key,title:a.title,file:a.stem+'.png',jpg:a.stem+'.jpg',source:'원본과기록/'+a.key+'_선택생성원본.png',source_dimensions:[sm.width,sm.height],source_sha256:sha(src),dimensions:[W,H],final_sha256:sha(fin),logo_variant:a.logo,logo_sha256:sha(logo),text_bounds:labels.map(l=>l.bounds),contrast:checks,description_chars:[...a.description].length};
}
(async()=>{
 const assets=JSON.parse(fs.readFileSync(path.join(root,'assets.json'),'utf8')),out=[];
 for(const a of assets.entries)out.push(await make(a));
 fs.writeFileSync(path.join(records,'출력검수.json'),JSON.stringify({date:assets.date,entries:out,scope:'파일/조판 검사, 실제 제품/관객/수상 검증 아님'},null,2)+'\n','utf8');

 const selected=out.filter(e=>e.key!=='K'),tiles=[],cols=3,rows=1;
 for(let i=0;i<selected.length;i++){
  tiles.push({input:await sharp(path.join(root,selected[i].file)).resize(360,450).png().toBuffer(),left:i*360,top:0});
  const l=await txt({text:selected[i].key+' · '+selected[i].title,x:0,y:0,size:20,color:'#192c35'});
  tiles.push({input:l.input,left:i*360+18,top:465});
 }
 const contact=await sharp({create:{width:1080,height:495,channels:3,background:'#f5f3ee'}}).composite(tiles).png().toBuffer();
 fs.writeFileSync(path.join(root,'최종선별_한눈에.png'),contact);
 console.log(JSON.stringify(out.map(e=>({key:e.key,min_contrast:Math.min(...e.contrast.map(c=>c.min_contrast)),description_chars:e.description_chars}))));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
