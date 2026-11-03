'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const sharp = require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const { runChecks } = require('../asset_checks.cjs');
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const clone = value => structuredClone(value);
const inside = (root, target) => {
  const relative = path.relative(root, target);
  return relative !== '' && relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative);
};

async function main() {
  const automation = path.resolve(__dirname, '..');
  const projectRoot = path.resolve(automation, '..');
  const cacheRoot = path.join(automation, '.private');
  const policy = JSON.parse((await fs.readFile(path.join(automation, 'policy.json'), 'utf8')).replace(/^\uFEFF/, ''));
  const testRoot = path.join(automation, '.test-runs');
  await fs.mkdir(testRoot, { recursive: true });
  const realTestRoot = await fs.realpath(testRoot);
  if (realTestRoot !== path.resolve(testRoot)) throw new Error('Refusing a redirected .test-runs root');
  const runRoot = await fs.mkdtemp(path.join(realTestRoot, 'assets-'));
  const fixtureProject = path.join(runRoot, 'project');
  const fixtureCache = path.join(runRoot, 'cache');
  const results = [];
  let baseline;
  const originals = new Map();
  const fixturePath = (root, relative) => {
    const destination = path.resolve(root, relative);
    assert(inside(runRoot, destination), 'Fixture target must stay inside this isolated run');
    assert(inside(root, destination), 'Fixture path must stay inside its designated root');
    return destination;
  };
  const copyFile = async (root, relative, source) => {
    const destination = fixturePath(root, relative);
    const bytes = await fs.readFile(source);
    await fs.mkdir(path.dirname(destination), { recursive: true });
    await fs.writeFile(destination, bytes);
    originals.set(destination, bytes);
    return destination;
  };
  const reset = async () => {
    for (const [file, bytes] of originals) await fs.writeFile(file, bytes);
  };
  const fingerprint = async () => {
    const hashes = {};
    for (const file of originals.keys()) hashes[file] = sha256(await fs.readFile(file));
    return hashes;
  };
  const expectFail = (result, id, entry) => {
    assert.equal(result.status, 'FAIL');
    assert(result.checks.some(c => c.id === id && c.status === 'FAIL' && (!entry || c.entry === entry)),
      'Expected failed check ' + id + (entry ? ' for ' + entry : '') + ': ' + JSON.stringify(result));
  };
  const check = async (name, action) => {
    try {
      await reset();
      await action();
      results.push({ name, status: 'PASS' });
    } catch (error) {
      results.push({ name, status: 'FAIL', message: error.message });
    }
  };
  const run = (injected = policy) => runChecks(injected, fixtureProject, fixtureCache);
  const mutatePixel = async (file, pixel = 0, rgb) => {
    const decoded = await sharp(await fs.readFile(file)).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
    const offset = pixel * 4;
    if (rgb) rgb.forEach((value, channel) => { decoded.data[offset + channel] = value; });
    else decoded.data[offset] ^= 1;
    await fs.writeFile(file, await sharp(decoded.data, { raw: decoded.info }).png().toBuffer());
  };
  try {
    await fs.mkdir(fixtureProject);
    await fs.mkdir(fixtureCache);
    for (const asset of Object.values(policy.assets)) {
      for (const key of ['path', 'source_path']) {
        const source = path.resolve(projectRoot, asset[key]);
        assert(inside(projectRoot, source));
        await copyFile(fixtureProject, asset[key], source);
      }
    }
    for (const logo of Object.values(policy.logos)) {
      await copyFile(fixtureCache, logo.cache_name, path.join(cacheRoot, logo.cache_name));
    }
    const reportPaths = ['audit_2026-11-03/원본과기록/출력검수.json', 'audit_2026-11-03/원본과기록/최종파일_재검수.json'];
    for (const relative of reportPaths) await copyFile(fixtureProject, relative, path.join(projectRoot, relative));
    const policyFile = await copyFile(fixtureProject, 'policy.json', path.join(automation, 'policy.json'));
    const finalA = fixturePath(fixtureProject, policy.assets.A.path);
    const sourceA = fixturePath(fixtureProject, policy.assets.A.source_path);
    const cacheWhite = fixturePath(fixtureCache, policy.logos.white.cache_name);
    const cli = args => {
      const process = spawnSync(global.process.execPath, [path.join(automation, 'asset_checks.cjs'), ...args], { encoding: 'utf8' });
      assert.ifError(process.error);
      assert.equal(process.stderr, '', 'CLI must only emit JSON on stdout');
      const result = JSON.parse(process.stdout);
      assert(['PASS', 'FAIL'].includes(result.status));
      assert(Array.isArray(result.checks));
      return { exit: process.status, result };
    };
    const cliArgs = ['--policy', policyFile, '--project-root', fixtureProject, '--cache', fixtureCache];

    await check('baseline: real copied PNGs, pins, logo pixels, contrast, bounds and calendar pass', async () => {
      const before = await fingerprint();
      const untouchedPolicy = JSON.stringify(policy);
      baseline = await run();
      assert.equal(baseline.status, 'PASS', JSON.stringify(baseline));
      assert(baseline.checks.every(c => c.status === 'PASS'));
      for (const entry of ['A', 'B']) {
        assert(baseline.details.entries[entry].logo.pixels_checked > 0);
        assert(baseline.details.entries[entry].logo.semitransparent_pixels_checked > 0);
        assert.equal(baseline.details.entries[entry].logo.mismatches, 0);
        assert(baseline.details.entries[entry].notice_contrast.every(c => c.minimum_ratio >= 4.5 && c.glyph_samples > 0));
      }
      assert.equal(JSON.stringify(policy), untouchedPolicy, 'Policy must not be modified');
      assert.deepEqual(await fingerprint(), before, 'Checks must not modify assets, reports, policy or cache');
    });
    await check('CLI baseline emits exactly one JSON result and exits zero', async () => {
      const actual = cli(cliArgs);
      assert.equal(actual.exit, 0);
      assert.deepEqual(actual.result, await run());
    });
    await check('tampered logo pixel fails even when historical report still says zero mismatches', async () => {
      const reportFile = fixturePath(fixtureProject, reportPaths[0]);
      const reportBefore = await fs.readFile(reportFile);
      const historical = JSON.parse(reportBefore.toString('utf8').replace(/^\uFEFF/, ''));
      assert(historical.entries.every(e => e.official_logo_mismatches === 0));
      const logo = await sharp(await fs.readFile(cacheWhite)).ensureAlpha().raw().toBuffer();
      let pixel = -1;
      for (let i = 3; i < logo.length; i += 4) if (logo[i] === 255) { pixel = (i - 3) / 4; break; }
      assert(pixel >= 0);
      await mutatePixel(finalA, pixel);
      const result = await run();
      expectFail(result, 'asset_sha256', 'A');
      expectFail(result, 'logo_pixels', 'A');
      assert(result.details.entries.A.logo.mismatches > 0);
      assert.deepEqual(await fs.readFile(reportFile), reportBefore, 'Historical zero report must remain untouched');
    });
    await check('one semitransparent official edge pixel is directly checked', async () => {
      const logo = await sharp(await fs.readFile(cacheWhite)).ensureAlpha().raw().toBuffer();
      let pixel = -1;
      for (let i = 3; i < logo.length; i += 4) if (logo[i] > 0 && logo[i] < 255) { pixel = (i - 3) / 4; break; }
      assert(pixel >= 0);
      await mutatePixel(finalA, pixel);
      const injected = clone(policy);
      injected.assets.A.sha256 = sha256(await fs.readFile(finalA));
      const result = await run(injected);
      expectFail(result, 'logo_pixels', 'A');
      assert(result.checks.some(c => c.id === 'asset_sha256' && c.entry === 'A' && c.status === 'PASS'));
    });
    await check('tampering away from logo fails the whole-file pin', async () => {
      await mutatePixel(finalA);
      expectFail(await run(), 'asset_sha256', 'A');
      const actual = cli(cliArgs);
      assert.notEqual(actual.exit, 0);
      expectFail(actual.result, 'asset_sha256', 'A');
    });
    await check('tampered source fails independently of final PNG', async () => {
      await mutatePixel(sourceA);
      expectFail(await run(), 'source_sha256', 'A');
    });
    await check('tampered final and source together cannot bypass both pins', async () => {
      await mutatePixel(sourceA);
      await mutatePixel(finalA);
      const result = await run();
      expectFail(result, 'source_sha256', 'A');
      expectFail(result, 'asset_sha256', 'A');
    });
    await check('tampered official cache fails pin before logo composition', async () => {
      await mutatePixel(cacheWhite);
      const result = await run();
      expectFail(result, 'official_logo_sha256', 'white');
      expectFail(result, 'logo_pixels', 'A');
      assert.equal(result.details.entries.A.logo, undefined);
    });
    await check('missing official cache fails', async () => {
      await fs.unlink(cacheWhite);
      expectFail(await run(), 'official_logo', 'white');
    });
    await check('overlapping injected text boxes fail', async () => {
      const injected = clone(policy);
      Object.assign(injected.assets.A.text_bounds[1], { x: injected.assets.A.text_bounds[0].x, y: injected.assets.A.text_bounds[0].y });
      expectFail(await run(injected), 'text_bounds', 'A');
    });
    await check('out-of-range text box fails', async () => {
      const injected = clone(policy);
      injected.assets.B.text_bounds[0].x = -1;
      expectFail(await run(injected), 'text_bounds', 'B');
    });
    await check('reordered calendar policy terms fail', async () => {
      const injected = clone(policy);
      injected.assets.B.calendar.terms.reverse();
      expectFail(await run(injected), 'calendar', 'B');
    });
    await check('missing calendar label fails even when count remains 24', async () => {
      const injected = clone(policy);
      injected.assets.B.text_bounds = injected.assets.B.text_bounds.filter(b => b.text !== '입춘');
      expectFail(await run(injected), 'calendar', 'B');
    });
    await check('swapped calendar label positions fail clockwise geometry', async () => {
      const injected = clone(policy);
      const a = injected.assets.B.text_bounds.find(b => b.text === '우수');
      const b = injected.assets.B.text_bounds.find(b => b.text === '소만');
      const previous = { x: a.x, y: a.y, width: a.width, height: a.height };
      Object.assign(a, { x: b.x, y: b.y, width: b.width, height: b.height });
      Object.assign(b, previous);
      expectFail(await run(injected), 'calendar', 'B');
    });
    await check('low actual glyph contrast fails even if source and final pins are updated', async () => {
      const box = policy.assets.A.text_bounds.find(b => b.text === '미래 제품 상상 · 실제 출시 제품 아님');
      const final = await sharp(await fs.readFile(finalA)).ensureAlpha().raw().toBuffer();
      const color = [255, 248, 233];
      let pixel;
      for (let y = box.y; y < box.y + box.height && pixel === undefined; y++) {
        for (let x = box.x; x < box.x + box.width; x++) {
          const k = (y * 1080 + x) * 4;
          if (color.every((v, i) => final[k + i] === v) && final[k + 3] === 255) { pixel = y * 1080 + x; break; }
        }
      }
      assert.notEqual(pixel, undefined);
      // Replace the copied source with a same-size light background; genuine rendered glyphs stay in the final.
      // Slightly offset the background color so opaque-glyph detection includes every ink pixel.
      await fs.writeFile(sourceA, await sharp({ create: { width: 1080, height: 1350, channels: 3, background: '#fff8e8' } }).png().toBuffer());
      const injected = clone(policy);
      injected.assets.A.source_sha256 = sha256(await fs.readFile(sourceA));
      injected.assets.A.sha256 = sha256(await fs.readFile(finalA));
      const result = await run(injected);
      expectFail(result, 'notice_contrast', 'A');
      assert(result.details.entries.A.notice_contrast.some(c => c.glyph_samples > 0 && c.minimum_ratio < 4.5));
    });
    await check('absence of opaque notice glyphs fails', async () => {
      const box = policy.assets.A.text_bounds.find(b => b.text.includes('미래 제품 상상') && b.y < 675);
      const raw = await sharp(await fs.readFile(finalA)).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
      for (let y = box.y; y < box.y + box.height; y++) for (let x = box.x; x < box.x + box.width; x++) raw.data[(y * 1080 + x) * 4 + 3] = 254;
      await fs.writeFile(finalA, await sharp(raw.data, { raw: raw.info }).png().toBuffer());
      expectFail(await run(), 'notice_contrast', 'A');
    });
    await check('truncated PNG fails actual decode even when its pin is injected', async () => {
      await fs.writeFile(finalA, (await fs.readFile(finalA)).subarray(0, 200));
      const injected = clone(policy);
      injected.assets.A.sha256 = sha256(await fs.readFile(finalA));
      expectFail(await run(injected), 'asset_png', 'A');
    });
    await check('wrong PNG dimensions fail', async () => {
      await fs.writeFile(finalA, await sharp(await fs.readFile(finalA)).resize(540, 675).png().toBuffer());
      expectFail(await run(), 'asset_png', 'A');
    });
    await check('grayscale final is rejected even when pin is injected', async () => {
      await fs.writeFile(finalA, await sharp(await fs.readFile(finalA)).greyscale().toColourspace('b-w').png().toBuffer());
      const injected = clone(policy);
      injected.assets.A.sha256 = sha256(await fs.readFile(finalA));
      expectFail(await run(injected), 'asset_png', 'A');
    });
    await check('project path traversal fails', async () => {
      const injected = clone(policy);
      injected.assets.A.path = '../cache/' + policy.logos.white.cache_name;
      expectFail(await run(injected), 'asset_png', 'A');
    });
    await check('cache path traversal fails', async () => {
      const injected = clone(policy);
      injected.logos.white.cache_name = '../project/policy.json';
      expectFail(await run(injected), 'official_logo', 'white');
    });
    await check('junction/symlink escape from project root fails', async () => {
      const link = fixturePath(fixtureProject, 'escape');
      await fs.symlink(fixtureCache, link, process.platform === 'win32' ? 'junction' : 'dir');
      const injected = clone(policy);
      injected.assets.A.path = 'escape/' + policy.logos.white.cache_name;
      expectFail(await run(injected), 'asset_png', 'A');
      await fs.unlink(link);
    });
    await check('CLI malformed arguments fail with JSON and nonzero exit', async () => {
      const actual = cli(['--policy']);
      assert.notEqual(actual.exit, 0);
      expectFail(actual.result, 'asset_cli');
    });
    await check('CLI invalid JSON policy fails with JSON and nonzero exit', async () => {
      await fs.writeFile(policyFile, '{invalid json');
      const actual = cli(cliArgs);
      assert.notEqual(actual.exit, 0);
      expectFail(actual.result, 'asset_cli');
    });
    await check('invalid module policy returns JSON FAIL rather than rejecting', async () => {
      expectFail(await run(null), 'asset_policy');
    });
    await check('invalid module root returns JSON FAIL rather than rejecting', async () => {
      expectFail(await runChecks(policy, 'relative', fixtureCache), 'asset_roots');
    });
  } finally {
    // Delete only the one directory this invocation created, after resolving both targets.
    const resolvedRoot = await fs.realpath(testRoot);
    const resolvedRun = await fs.realpath(runRoot);
    if (resolvedRoot !== realTestRoot || !inside(resolvedRoot, resolvedRun) ||
        resolvedRun !== path.resolve(runRoot) || !path.basename(resolvedRun).startsWith('assets-')) {
      throw new Error('Refusing unsafe cleanup target: ' + resolvedRun);
    }
    await fs.rm(resolvedRun, { recursive: true, force: true });
  }
  const failed = results.filter(r => r.status === 'FAIL').length;
  const result = { status: failed ? 'FAIL' : 'PASS', tests_run: results.length, tests: results.length,
    passed: results.length - failed, failed, results,
    baseline: baseline ? { status: baseline.status, checks: baseline.checks.length,
      entries: Object.fromEntries(Object.entries(baseline.details.entries).map(([key, value]) => [key,
        { logo: value.logo, notice_contrast: value.notice_contrast }])) } : null,
    cleanup: 'Removed only the resolved isolated run directory' };
  process.stdout.write(JSON.stringify(result) + '\n');
  process.exitCode = failed ? 1 : 0;
}

main().catch(error => {
  process.stdout.write(JSON.stringify({ status: 'FAIL', message: error.message }) + '\n');
  process.exitCode = 1;
});
