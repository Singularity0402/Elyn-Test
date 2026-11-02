const fs=require('fs'),path=require('path'),crypto=require('crypto'),assert=require('assert');
const sharp=require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const R=__dirname, Q=path.join(R,'../quality_2026-11-02'),OLD=path.join(R,'../portfolio_2026-11-02');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const lum=rgb=>rgb.map(v=>{v/=255;return v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4)}).reduce((v,c,i)=>v+c*[.2126,.7152,.0722][i],0);
(async()=>{
 const out=read(path.join(R,'원본과기록/출력검수.json')), audit=read(path.join(R,'원본과기록/120규칙_재감찰.json'));
 const originalRules=read(path.join(Q,'규칙120.json')).rules;
 assert.equal(originalRules.length,120);assert.equal(audit.manual_sha256,sha(fs.readFileSync(path.join(Q,'규칙120.json'))));
 const checks=[];
 for(const e of out.entries){
  const png=fs.readFileSync(path.join(R,e.file)),m=await sharp(png).metadata();
  assert.equal(m.width,1080);assert.equal(m.height,1350);assert.equal(sha(png),e.png_sha256);assert.equal(e.official_logo_mismatches,0);
  const original=fs.readFileSync(path.join(R,'원본과기록',e.key+'_선택생성원본.png'));
  assert.equal(sha(original),e.source_sha256);
  const rectangles=[];
  for(let i=0;i<e.text_bounds.length;i++)for(let j=i+1;j<e.text_bounds.length;j++){
   const a=e.text_bounds[i],b=e.text_bounds[j];
   if(Math.min(a.x+a.width,b.x+b.width)>Math.max(a.x,b.x)&&Math.min(a.y+a.height,b.y+b.height)>Math.max(a.y,b.y))rectangles.push([a.text,b.text]);
  }
  assert.equal(rectangles.length,0,JSON.stringify(rectangles));
  const base=await sharp(original).resize(1080,1350,{fit:'cover'}).ensureAlpha().raw().toBuffer(),final=await sharp(png).ensureAlpha().raw().toBuffer();
  const contrast=[];
  for(const b of e.text_bounds.filter(x=>x.text.includes('미래 제품 상상'))){
   const footer=b.text==='미래 제품 상상 · 실제 출시 제품 아님';
   const color=(e.key==='A'?(footer?'fff8e9':'e8ddd0'):(footer?'625b51':'665f56')).match(/../g).map(x=>parseInt(x,16));
   const inkL=lum(color),ratios=[];
   for(let y=b.y;y<b.y+b.height;y++)for(let x=b.x;x<b.x+b.width;x++){
    const k=(y*1080+x)*4;if(color.every((c,j)=>final[k+j]===c)){const bg=lum([base[k],base[k+1],base[k+2]]);ratios.push((Math.max(inkL,bg)+.05)/(Math.min(inkL,bg)+.05));}
   }
   assert(ratios.length>0,'No opaque glyph samples');ratios.sort((a,b)=>a-b);
   const item={text:b.text,size:b.size,glyph_samples:ratios.length,minimum_ratio:+ratios[0].toFixed(2),median_ratio:+ratios[Math.floor(ratios.length/2)].toFixed(2)};
   assert(item.minimum_ratio>=4.5,'Contrast below internal4.5 target: '+JSON.stringify(item));contrast.push(item);
  }
  if(e.key==='B'){assert.deepEqual(e.calendar.terms,'입춘 우수 경칩 춘분 청명 곡우 입하 소만 망종 하지 소서 대서 입추 처서 백로 추분 한로 상강 입동 소설 대설 동지 소한 대한'.split(' '));assert.equal(new Set(e.calendar.terms).size,24);}
  const rows=audit.rows.filter(x=>x.entry===e.key);assert.equal(rows.length,120);assert.equal(new Set(rows.map(x=>x.id)).size,120);
  for(const row of rows)assert.equal(row.rule,originalRules.find(x=>x.id===row.id).rule);
  assert.deepEqual(rows.filter(x=>x.status==='미확인').map(x=>x.id).sort(),['J08','L02','L03','L04','L05','L06','L08']);
  const copy=fs.readFileSync(path.join(R,e.key+'_제출문구.md'),'utf8').replace(/^\uFEFF/,'');
  const desc=copy.replace(/\r\n/g,'\n').split('## 작품 설명\n')[1].split('\n## ')[0].trim();assert(desc.length<=500);
  checks.push({entry:e.key,png_sha256:sha(png),native_dimensions:e.source_dimensions,final_dimensions:[m.width,m.height],png_decoded:true,text_intersections:0,official_logo_pixels_checked:e.official_logo_opaque_pixels,official_logo_mismatches:0,notice_contrast:contrast,description_chars:desc.length,audit_rows:120,missing_rule_ids:0});
 }
 const history=read(path.join(R,'원본과기록/실제생성기록.json'));
 for(const rec of history.records){
  assert(rec.prompt.length>100);const p=path.join(R,'원본과기록',rec.result);assert(fs.existsSync(p));rec.sha256=sha(fs.readFileSync(p));
  for(const ref of rec.references)assert(fs.existsSync(path.join(R,'원본과기록',ref)));
 }
 fs.writeFileSync(path.join(R,'원본과기록/실제생성기록.json'),JSON.stringify(history,null,2)+'\n');
 const info={date:'2026-11-03',checks,manual_rule_changes:0,classification_corrections:['D10'],real_audience_responses:0,real_generation_screenshots_received:0,supplied_table_is_generation_proof:false,actual_social_metrics_available:false,remaining_unverified_per_entry:7,note:'contrast4.5 is an internal screen-craft target on opaque glyph pixels, not certification of mobile readability or audience effect. AI craft judgments remain internal.'};
 fs.writeFileSync(path.join(R,'원본과기록/최종파일_재검수.json'),JSON.stringify(info,null,2)+'\n');
 console.log(JSON.stringify(info));
})();
