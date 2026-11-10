'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const sharp=require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const ROOT=__dirname,W=1080,H=1350;
const project=path.resolve(ROOT,'..'), FONT='C:/Users/user/S-Core_Dream_OTF/';
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const overlap=(a,b)=>Math.min(a.x+a.width,b.x+b.width)>Math.max(a.x,b.x)&&Math.min(a.y+a.height,b.y+b.height)>Math.max(a.y,b.y);
const lum=a=>a.map(v=>{v/=255;return v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
const cr=(a,b)=>{let x=lum(a),y=lum(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
async function label(e){
 const b=await sharp({text:{text:'<span foreground="'+e.color+'">'+esc(e.text)+'</span>',font:'S-Core Dream '+e.size,fontfile:FONT+(e.bold?'SCDream7.otf':'SCDream4.otf'),rgba:true,dpi:72}}).png().toBuffer();
 const m=await sharp(b).metadata(),x=Math.round(e.right?e.x-m.width:e.x);
 return {input:b,left:x,top:e.y,bounds:{text:e.text,x,y:e.y,width:m.width,height:m.height,color:e.color}};
}
(async()=>{
 const native=fs.readFileSync("C:/Users/user/.codex/generated_images/01a18909-ba7e-7b71-be45-6d9a63b0b87d/exec-e43353d4-051d-45c1-aaeb-d5953a1ce03c.png"),nm=await sharp(native).metadata();
 fs.writeFileSync(path.join(ROOT,'H2_생성원본.png'),native);
 const base=await sharp(native).resize(W,H,{fit:'cover'}).toColourspace('srgb').png().toBuffer();
 const defs=[
 {text:'밥 한 끼,',x:64,y:156,size:62,bold:true,color:'#142b38'},
 {text:'여는 것부터 편하게.',x:64,y:236,size:64,bold:true,color:'#822333'},
 {text:'넓게 잡는 일체형 필름 손잡이.',x:67,y:322,size:25,color:'#243b47'},
 {text:'편하게 여는 햇반 · 개봉 구조 제안',x:1016,y:65,size:20,right:true,color:'#243b47'},
 {text:'미래 제품 상상 · 실물 성능 검증 전',x:1016,y:1302,size:24,right:true,color:'#142b38'}];
 const layers=[];for(const d of defs)layers.push(await label(d));
 const pixels=await sharp(base).ensureAlpha().raw().toBuffer();
 const contrast=[];
 for(let n=0;n<layers.length;n++){
   const t=layers[n],b=t.bounds;
   if(b.x<24||b.y<24||b.x+b.width>W-24||b.y+b.height>H-18)throw Error('text bounds');
   for(let j=n+1;j<layers.length;j++)if(overlap(b,layers[j].bounds))throw Error('text overlap');
   if(overlap(b,{x:64,y:49,width:170,height:69}))throw Error('logo overlap');
   const {data,info}=await sharp(t.input).ensureAlpha().raw().toBuffer({resolveWithObject:true});
   const rgb=b.color.slice(1).match(/../g).map(s=>parseInt(s,16));let minimum=100,count=0;
   for(let y=0;y<info.height;y++)for(let x=0;x<info.width;x++)if(data[(y*info.width+x)*4+3]>=220){
      const k=((b.y+y)*W+b.x+x)*4;minimum=Math.min(minimum,cr(rgb,[pixels[k],pixels[k+1],pixels[k+2]]));count++;
   }
   if(!count||minimum<4.5)throw Error('contrast '+b.text+' '+minimum);
   contrast.push({text:b.text,minimum,count,target:4.5});
 }
 const pre=await sharp(base).composite(layers.map(({input,left,top})=>({input,left,top}))).png().toBuffer();
 const logo=fs.readFileSync(path.join(project,'automation_2026-11-03/.private/logo_red.png'));
 const policy=JSON.parse(fs.readFileSync(path.join(project,'automation_2026-11-03/policy.json'),'utf8'));
 if(hash(logo)!==policy.logos.red.sha256)throw Error('official logo hash');
 const final=await sharp(pre).composite([{input:logo,left:0,top:0}]).png({compressionLevel:9}).toBuffer();
 const expected=await sharp(pre).composite([{input:logo,left:0,top:0}]).ensureAlpha().raw().toBuffer();
 const actual=await sharp(final).ensureAlpha().raw().toBuffer(),mask=await sharp(logo).ensureAlpha().raw().toBuffer();
 let visible=0,mismatch=0;for(let i=0;i<mask.length;i+=4)if(mask[i+3]){visible++;for(let c=0;c<4;c++)if(expected[i+c]!==actual[i+c]){mismatch++;break;}}
 if(mismatch)throw Error('logo mismatch');
 fs.writeFileSync(path.join(ROOT,'H2_편하게여는햇반.png'),final);
 await sharp(final).jpeg({quality:97,chromaSubsampling:'4:4:4'}).toFile(path.join(ROOT,'H2_편하게여는햇반.jpg'));
 await sharp(final).resize(360,450).png().toFile(path.join(ROOT,'H2_360폭.png'));
 const inputs=[path.join(project,'expansion_2026-11-04/H_한손의식사.png'),path.join(ROOT,'H2_편하게여는햇반.png'),path.join(project,'audit_2026-11-03/A_갓지은편지.png')];
 const captions=['수정 전 · 고리와 받침','이번 수정 · 넓은 탭과 두 손','기존 주력 후보 · 갓 지은 편지'];
 const cl=[];
 for(let i=0;i<3;i++){
    cl.push({input:await sharp(inputs[i]).resize(360,450).png().toBuffer(),left:i*360,top:0});
    const l=await label({text:captions[i],x:0,y:0,size:17,color:'#182b34'});
    cl.push({input:l.input,left:i*360+Math.round((360-l.bounds.width)/2),top:468});
 }
 await sharp({create:{width:1080,height:510,channels:3,background:'#f3f3ee'}}).composite(cl).png().toFile(path.join(ROOT,'수정전후_주력비교.png'));
 const outputs={date:'2026-11-11',source_dimensions:[nm.width,nm.height],source_sha256:hash(native),final_dimensions:[W,H],final_sha256:hash(final),text_bounds:layers.map(l=>l.bounds),contrast,logo_sha256:hash(logo),logo_alpha_positive_pixels:visible,logo_mismatches:mismatch,classification:'IMAGINED_PRODUCT_COMPARISON_CANDIDATE',limits:'File and layout checks only. No physical performance, audience or prize validation.'};
 fs.writeFileSync(path.join(ROOT,'출력검사.json'),JSON.stringify(outputs,null,2)+'\n','utf8');
 console.log(JSON.stringify({dimensions:outputs.final_dimensions,logo_mismatches:mismatch,min_contrast:Math.min(...contrast.map(c=>c.minimum))}));
})().catch(e=>{console.error(e);process.exitCode=1;});
