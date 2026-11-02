const fs = require('fs');
const path = require('path');
const sharp = require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const crypto = require('crypto');
const ROOT = __dirname;
const FONT_DIR = 'C:/Users/user/S-Core_Dream_OTF';
const WIDTH = 1080;
const HEIGHT = 1350;
const source = process.argv[2];
const logo = process.argv[3];
if (!source || !logo) throw new Error('Usage: node layout.cjs artwork.png official_logo_4x5.png');
const headFont = path.join(FONT_DIR, 'SCDream7.otf');
const bodyFont = path.join(FONT_DIR, 'SCDream4.otf');
const esc = s => s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const elements = [
  {text:'부엌을 접고,', x:64, y:160, size:62, font:headFont, color:'#25231f'},
  {text:'내 삶을 펼치다.', x:64, y:238, size:62, font:headFont, color:'#bc171e'},
  {text:'갓 지은 한 끼에서 시작되는, 더 넓은 일상.', x:67, y:324, size:20, font:bodyFont, color:'#514940'},
  {text:'2056 · 햇반이 지을 미래', x:729, y:65, size:14, font:bodyFont, color:'#63584a'},
  {text:'※ 미래 생활을 상상한 이미지입니다. 실제 제품의 기능이 아닙니다.', x:64, y:1309, size:14, font:bodyFont, color:'#463f35'}
];
(async () => {
  const metadata = await sharp(source).metadata();
  const logoMeta = await sharp(logo).metadata();
  if(logoMeta.width!==WIDTH || logoMeta.height!==HEIGHT || !logoMeta.hasAlpha) throw new Error('Official logo must be the unchanged 1080x1350 RGBA template.');
  const original = path.join(ROOT, '02_생성원본.png');
  fs.copyFileSync(source, original);
  const base = await sharp(source).resize(WIDTH,HEIGHT,{fit:'cover',position:'centre'}).png().toBuffer();
  const composites = [];
  for(const e of elements){
    const input = await sharp({text:{text:`<span foreground="${e.color}">${esc(e.text)}</span>`,font:`S-Core Dream ${e.size}`,fontfile:e.font,rgba:true,dpi:72}}).png().toBuffer();
    const m=await sharp(input).metadata();
    if(e.x+m.width>WIDTH-40 || e.y+m.height>HEIGHT-18) throw new Error(`Text overflow: ${e.text} (${m.width}x${m.height})`);
    composites.push({input,left:e.x,top:e.y});
  }
  composites.push({input:fs.readFileSync(logo),left:0,top:0});
  const filename = '01_출품작_부엌을접고_내삶을펼치다';
  const png = await sharp(base).composite(composites).png({compressionLevel:9}).toBuffer();
  fs.writeFileSync(path.join(ROOT, filename+'.png'),png);
  await sharp(png).jpeg({quality:97,chromaSubsampling:'4:4:4'}).toFile(path.join(ROOT, filename+'.jpg'));
  const rgba = await sharp(png).ensureAlpha().raw().toBuffer();
  const under = await sharp(base).ensureAlpha().raw().toBuffer();
  const official = await sharp(logo).ensureAlpha().raw().toBuffer();
  let opaquePixels=0, mismatches=0, outsideChanged=0;
  for(let y=30;y<135;y++) for(let x=35;x<260;x++){
    const i=(y*WIDTH+x)*4;
    if(official[i+3]===255){opaquePixels++; for(let c=0;c<3;c++) if(rgba[i+c]!==official[i+c]) {mismatches++;break;}}
  }
  if(!opaquePixels || mismatches) throw new Error('Official opaque logo pixels changed.');
  const font64 = fs.readFileSync(headFont).toString('base64');
  const body64 = fs.readFileSync(bodyFont).toString('base64');
  const svgTexts=elements.map(e=>`<text x="${e.x}" y="${e.y+e.size*.82}" font-family="${e.font===headFont?'EntryHead':'EntryBody'}" font-size="${e.size}" fill="${e.color}">${esc(e.text)}</text>`).join('\n');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350" viewBox="0 0 1080 1350"><metadata>Typeface: S-Core Dream, copyright S-Core. Original font files embedded without modification under the S-Core Dream license.</metadata><defs><style>@font-face{font-family:EntryHead;src:url(data:font/otf;base64,${font64})}@font-face{font-family:EntryBody;src:url(data:font/otf;base64,${body64})}</style></defs><image width="1080" height="1350" href="data:image/png;base64,${base.toString('base64')}"/>${svgTexts}<image width="1080" height="1350" href="data:image/png;base64,${fs.readFileSync(logo).toString('base64')}"/></svg>`;
  fs.writeFileSync(path.join(ROOT,'03_편집원본.svg'),svg);
  const report={source_dimensions:[metadata.width,metadata.height],final_dimensions:[WIDTH,HEIGHT],format:'PNG + JPEG',official_logo_dimensions:[logoMeta.width,logoMeta.height],opaque_logo_pixels_checked:opaquePixels,opaque_logo_pixel_mismatches:mismatches,source_sha256:crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex'),final_sha256:crypto.createHash('sha256').update(png).digest('hex'),official_logo_sha256:crypto.createHash('sha256').update(fs.readFileSync(logo)).digest('hex'),font:'S-Core Dream 7 / 4',layout_note:'Official PNG overlaid without cropping, recoloring or regenerating. Artwork resized only; photographic edits used image generation tool.'};
  fs.writeFileSync(path.join(ROOT,'검수결과.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
})();
