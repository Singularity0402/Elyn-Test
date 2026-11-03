'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const SHARP = 'C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp';
const WIDTH = 1080, HEIGHT = 1350;
const TERMS = '입춘 우수 경칩 춘분 청명 곡우 입하 소만 망종 하지 소서 대서 입추 처서 백로 추분 한로 상강 입동 소설 대설 동지 소한 대한'.split(' ');
const FOOTER = '미래 제품 상상 · 실제 출시 제품 아님';
const NOTICE_COLORS = { A: { footer: 'fff8e9', top: 'e8ddd0' }, B: { footer: '625b51', top: '665f56' } };
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const errorText = error => error instanceof Error ? error.message : String(error);
const inside = (root, target) => {
  const relative = path.relative(root, target);
  return relative !== '' && relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative);
};

async function rootDirectory(value, label) {
  if (typeof value !== 'string' || !path.isAbsolute(value)) throw new Error(label + ' must be absolute');
  const resolved = await fs.realpath(value);
  if (!(await fs.stat(resolved)).isDirectory()) throw new Error(label + ' must be a directory');
  return resolved;
}

// Both lexical traversal and symlink/junction traversal must remain inside the supplied root.
async function readContained(root, relative) {
  if (typeof relative !== 'string' || !relative || relative.includes('\0') || path.isAbsolute(relative) || path.win32.isAbsolute(relative)) {
    throw new Error('Expected a relative file path inside the root');
  }
  const target = path.resolve(root, relative);
  if (!inside(root, target)) throw new Error('Path escapes root: ' + relative);
  const real = await fs.realpath(target);
  if (!inside(root, real)) throw new Error('Resolved path escapes root: ' + relative);
  if (!(await fs.stat(real)).isFile()) throw new Error('Expected a regular file: ' + relative);
  return fs.readFile(real);
}

function luminance(rgb) {
  const linear = rgb.map(value => {
    const channel = value / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}

function geometry(bounds) {
  if (!Array.isArray(bounds) || !bounds.length) throw new Error('text_bounds must be nonempty');
  const invalid = [], intersections = [];
  for (const [index, b] of bounds.entries()) {
    if (!b || typeof b.text !== 'string' || !b.text ||
        !['x', 'y', 'width', 'height'].every(k => Number.isSafeInteger(b[k])) ||
        b.width <= 0 || b.height <= 0 || b.x < 0 || b.y < 0 ||
        b.x + b.width > WIDTH || b.y + b.height > HEIGHT) invalid.push(index);
  }
  if (!invalid.length) {
    for (let i = 0; i < bounds.length; i++) {
      for (let j = i + 1; j < bounds.length; j++) {
        const a = bounds[i], b = bounds[j];
        if (Math.min(a.x + a.width, b.x + b.width) > Math.max(a.x, b.x) &&
            Math.min(a.y + a.height, b.y + b.height) > Math.max(a.y, b.y)) {
          intersections.push({ indices: [i, j], texts: [a.text, b.text] });
        }
      }
    }
  }
  return { invalid_bounds: invalid, intersections, count: bounds.length };
}

function calendarDetails(asset) {
  const c = asset.calendar;
  if (!c || c.count !== 24 || !Array.isArray(c.terms) || c.terms.length !== 24 ||
      !c.terms.every((term, i) => term === TERMS[i])) throw new Error('Calendar must contain the canonical 24 terms in order');
  const boxes = asset.text_bounds.filter(b => TERMS.includes(b.text));
  if (boxes.length !== 24 || !boxes.every((box, i) => box.text === TERMS[i])) {
    throw new Error('Text bounds must contain all 24 calendar labels exactly once in canonical order');
  }
  // Verify the actual label positions progress clockwise around the printed calendar.
  const angles = boxes.map(b => (Math.atan2((b.y + b.height / 2 - 810) / 488,
    (b.x + b.width / 2 - 540) / 508) * 180 / Math.PI + 360) % 360);
  if (angles[0] < 270 || angles[0] >= 300) throw new Error('입춘 must start just clockwise of the top of the calendar');
  const steps = angles.map((angle, i) => (angles[(i + 1) % 24] - angle + 360) % 360);
  if (steps.some(step => step < 10 || step > 20)) throw new Error('Calendar positions do not progress clockwise in 24 steps');
  return { count: boxes.length, terms: boxes.map(b => b.text), clockwise_steps_degrees: steps };
}

async function runChecks(policy, projectRoot, cacheRoot) {
  const checks = [];
  const details = { dimensions: [WIDTH, HEIGHT], contrast_target: 4.5, color_space: 'srgb', entries: {} };
  const record = (id, entry, passed, message, data) => {
    const item = { id, status: passed ? 'PASS' : 'FAIL', ...(entry ? { entry } : {}), message };
    if (data !== undefined) item.details = data;
    checks.push(item);
    return item;
  };
  const attempt = async (id, entry, action) => {
    try { return await action(); }
    catch (error) { record(id, entry, false, errorText(error)); return null; }
  };
  const finish = () => ({ status: checks.length && checks.every(c => c.status === 'PASS') ? 'PASS' : 'FAIL', checks, details });
  try {
    const roots = await attempt('asset_roots', null, async () => {
      const project = await rootDirectory(projectRoot, 'project-root');
      const cache = await rootDirectory(cacheRoot, 'cache');
      record('asset_roots', null, true, 'Project and cache roots resolved');
      return { project, cache };
    });
    if (!roots) return finish();
    if (!policy || typeof policy !== 'object' || !policy.assets?.A || !policy.assets?.B ||
        !policy.logos?.white || !policy.logos?.red) {
      record('asset_policy', null, false, 'Policy requires assets.A/B and logos.white/red');
      return finish();
    }
    record('asset_policy', null, true, 'Required asset and logo policy entries present');
    const sharp = require(SHARP);
    const decode = async (bytes, dimensions, rgbOnly) => {
      const decoder = sharp(bytes, { failOn: 'warning' });
      const meta = await decoder.metadata();
      if (meta.format !== 'png') throw new Error('Asset must decode as PNG');
      if (dimensions && (meta.width !== WIDTH || meta.height !== HEIGHT)) throw new Error('PNG must be 1080x1350');
      if (rgbOnly && (meta.space !== 'srgb' || ![3, 4].includes(meta.channels) || meta.isPalette)) {
        throw new Error('Final PNG must use RGB/RGBA, not palette or grayscale');
      }
      const raw = await decoder.toColourspace('srgb').ensureAlpha().raw().toBuffer({ resolveWithObject: true });
      if (raw.info.channels !== 4 || raw.data.length !== meta.width * meta.height * 4) throw new Error('Incomplete PNG decode');
      return { bytes, meta, raw: raw.data };
    };
    const pinned = (id, entry, bytes, expected) => {
      const actual = sha256(bytes);
      const ok = typeof expected === 'string' && /^[a-f0-9]{64}$/i.test(expected) && actual === expected.toLowerCase();
      record(id, entry, ok, ok ? 'SHA-256 pin matched' : 'SHA-256 pin mismatch or invalid pin', { expected, actual });
      return ok;
    };
    const logos = {};
    for (const variant of ['white', 'red']) {
      logos[variant] = await attempt('official_logo', variant, async () => {
        const logo = policy.logos[variant];
        const bytes = await readContained(roots.cache, logo.cache_name);
        // Never build an expected logo image from an unverified cache entry.
        if (!pinned('official_logo_sha256', variant, bytes, logo.sha256)) return null;
        const decoded = await decode(bytes, true, false);
        if (!decoded.meta.hasAlpha) throw new Error('Official PNG must have an alpha channel');
        let visible = 0;
        for (let i = 3; i < decoded.raw.length; i += 4) if (decoded.raw[i] > 0) visible++;
        if (!visible) throw new Error('Official logo has no visible pixels');
        record('official_logo', variant, true, 'Pinned official PNG decoded at 1080x1350', { alpha_positive_pixels: visible });
        return decoded;
      });
    }
    for (const entry of ['A', 'B']) {
      const asset = policy.assets[entry];
      const info = details.entries[entry] = {};
      const final = await attempt('asset_png', entry, async () => {
        const bytes = await readContained(roots.project, asset.path);
        pinned('asset_sha256', entry, bytes, asset.sha256);
        const image = await decode(bytes, true, true);
        info.final_dimensions = [image.meta.width, image.meta.height];
        record('asset_png', entry, true, 'Final RGB/RGBA PNG fully decoded at 1080x1350');
        return image;
      });
      const source = await attempt('source_png', entry, async () => {
        const bytes = await readContained(roots.project, asset.source_path);
        pinned('source_sha256', entry, bytes, asset.source_sha256);
        const image = await decode(bytes, false, false);
        info.source_dimensions = [image.meta.width, image.meta.height];
        record('source_png', entry, true, 'Source PNG fully decoded');
        return image;
      });
      const bounds = await attempt('text_bounds', entry, async () => {
        const data = geometry(asset.text_bounds);
        const valid = !data.invalid_bounds.length && !data.intersections.length;
        record('text_bounds', entry, valid, valid ? 'All text boxes are in range and do not overlap' : 'Text boxes overlap or extend outside the image', data);
        return data.invalid_bounds.length ? null : asset.text_bounds;
      });
      await attempt('calendar', entry, async () => {
        if (entry === 'A') {
          if (asset.calendar !== null) throw new Error('A calendar must be null');
          record('calendar', entry, true, 'A has no calendar');
        } else {
          if (!bounds) throw new Error('Valid text bounds required for calendar verification');
          info.calendar = calendarDetails(asset);
          record('calendar', entry, true, 'All 24 terms and their clockwise label order verified', info.calendar);
        }
      });
      const base = source ? await attempt('source_resize', entry, async () => {
        // Match the production composition, including its intermediate PNG encoding.
        const bytes = await sharp(source.bytes).resize(WIDTH, HEIGHT, { fit: 'cover' }).png().toBuffer();
        const raw = await sharp(bytes).toColourspace('srgb').ensureAlpha().raw().toBuffer();
        record('source_resize', entry, true, 'Source independently resized with fit:cover');
        return { bytes, raw };
      }) : null;
      await attempt('logo_pixels', entry, async () => {
        const requiredVariant = entry === 'A' ? 'white' : 'red';
        if (asset.logo_variant !== requiredVariant) throw new Error('Unexpected official logo variant');
        const logo = logos[requiredVariant];
        if (!final || !base || !logo) throw new Error('Decoded final/source and hash-verified official logo required');
        const expected = await sharp(base.bytes).composite([{ input: logo.bytes, left: 0, top: 0 }])
          .toColourspace('srgb').ensureAlpha().raw().toBuffer();
        let pixels = 0, semi = 0, mismatches = 0;
        const samples = [];
        for (let k = 0; k < logo.raw.length; k += 4) {
          if (logo.raw[k + 3] === 0) continue;
          pixels++;
          if (logo.raw[k + 3] < 255) semi++;
          if ([0, 1, 2, 3].some(c => final.raw[k + c] !== expected[k + c])) {
            mismatches++;
            if (samples.length < 8) samples.push({ x: (k / 4) % WIDTH, y: Math.floor(k / 4 / WIDTH),
              expected_rgba: [...expected.subarray(k, k + 4)], actual_rgba: [...final.raw.subarray(k, k + 4)] });
          }
        }
        info.logo = { pixels_checked: pixels, semitransparent_pixels_checked: semi, mismatches, mismatch_samples: samples };
        record('logo_pixels', entry, pixels > 0 && mismatches === 0,
          mismatches ? 'Official logo pixels differ from independent composition' : 'Every official alpha>0 pixel matches independent composition', info.logo);
      });
      await attempt('notice_contrast', entry, async () => {
        if (!bounds || !final || !base) throw new Error('Decoded images and valid text bounds required');
        const notices = bounds.filter(b => b.text.includes('미래 제품 상상'));
        const footer = notices.filter(b => b.text === FOOTER && b.y >= HEIGHT / 2);
        const top = notices.filter(b => b.text !== FOOTER && b.y < HEIGHT / 2);
        if (notices.length !== 2 || footer.length !== 1 || top.length !== 1) throw new Error('Exactly one top and one footer future-product notice required');
        const results = [];
        for (const [role, box] of [['top', top[0]], ['footer', footer[0]]]) {
          const ink = NOTICE_COLORS[entry][role].match(/../g).map(v => parseInt(v, 16));
          const inkL = luminance(ink);
          let count = 0, minimum = Infinity, worst;
          for (let y = box.y; y < box.y + box.height; y++) {
            for (let x = box.x; x < box.x + box.width; x++) {
              const k = (y * WIDTH + x) * 4;
              // Exact rendered ink and opaque alpha identify interior glyph pixels.
              if (final.raw[k + 3] !== 255 || !ink.every((v, c) => final.raw[k + c] === v) ||
                  ink.every((v, c) => base.raw[k + c] === v)) continue;
              const background = [...base.raw.subarray(k, k + 3)];
              const bgL = luminance(background);
              const ratio = (Math.max(inkL, bgL) + 0.05) / (Math.min(inkL, bgL) + 0.05);
              count++;
              if (ratio < minimum) { minimum = ratio; worst = { x, y, background_rgb: background }; }
            }
          }
          results.push({ role, text: box.text, ink_rgb: ink, glyph_samples: count,
            minimum_ratio: count ? minimum : null, worst_pixel: worst || null,
            status: count > 0 && minimum >= 4.5 ? 'PASS' : 'FAIL' });
        }
        info.notice_contrast = results;
        const valid = results.every(item => item.status === 'PASS');
        record('notice_contrast', entry, valid, valid ? 'Opaque notice glyphs meet the internal minimum 4.5 contrast target' : 'Missing opaque glyph samples or contrast below 4.5', results);
      });
    }
  } catch (error) {
    record('asset_checks_error', null, false, errorText(error));
  }
  return finish();
}

async function main(argv) {
  try {
    const options = {};
    for (let i = 0; i < argv.length; i += 2) {
      const flag = argv[i], value = argv[i + 1];
      if (!['--policy', '--project-root', '--cache'].includes(flag) || !value || options[flag]) throw new Error('Expected --policy ABS --project-root ABS --cache ABS');
      if (!path.isAbsolute(value)) throw new Error(flag + ' must be absolute');
      options[flag] = value;
    }
    if (Object.keys(options).length !== 3) throw new Error('Expected --policy ABS --project-root ABS --cache ABS');
    const project = await rootDirectory(options['--project-root'], 'project-root');
    const policyPath = path.resolve(options['--policy']);
    if (!inside(project, policyPath)) throw new Error('Policy path must be inside project-root');
    const bytes = await readContained(project, path.relative(project, policyPath));
    const policy = JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/, ''));
    const result = await runChecks(policy, project, options['--cache']);
    process.stdout.write(JSON.stringify(result) + '\n');
    process.exitCode = result.status === 'PASS' ? 0 : 1;
  } catch (error) {
    process.stdout.write(JSON.stringify({ status: 'FAIL', checks: [{ id: 'asset_cli', status: 'FAIL', message: errorText(error) }], details: {} }) + '\n');
    process.exitCode = 1;
  }
}

module.exports = { runChecks };
if (require.main === module) void main(process.argv.slice(2));
