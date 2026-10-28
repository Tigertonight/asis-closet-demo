const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit/stamp/printing.js', 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

function fixture({ decode, supported = true, load = true, encode, naturalWidth = 900 } = {}) {
  const frames = [], blobs = [], revoked = [], events = {}, timers = new Map(), drawing = [];
  let prints = 0, decoded = 0;
  const photo = { naturalWidth, naturalHeight: 1200, decode: async () => { if (decode && decoded === 0) await decode(); decoded++; } };
  const canvas = { width: 0, height: 0,
    getContext: () => ({ fillRect(...args) { drawing.push(['fill', ...args]); }, drawImage(...args) { drawing.push(['image', ...args]); } }),
    toBlob(cb, type) { drawing.push(['encoded', this.width, this.height, type]); if (encode) encode(cb); else cb(new Blob(['six-inch PNG'], { type })); },
  };
  const context = { window: {}, Error,
    URL: { createObjectURL(blob) { blobs.push(blob); return `blob:local-${blobs.length}`; }, revokeObjectURL(url) { revoked.push(url); } },
    setTimeout(fn) { const id = timers.size + 1; timers.set(id, fn); return id; }, clearTimeout(id) { timers.delete(id); },
    document: {
      createElement(tag) {
        if (tag === 'canvas') return canvas;
        assert.equal(tag, 'iframe');
        decoded = 0;
        return { style: {}, setAttribute() {}, remove() { this.removed = true; },
          contentDocument: { querySelector(selector) { assert.equal(selector, 'img'); return photo; } },
          contentWindow: {
            addEventListener(event, cb) { events[event] = cb; }, focus() {},
            print() { assert.equal(decoded, 2, 'print must wait for both original and composed PNG to decode'); prints++; if (supported) events.beforeprint(); },
          },
        };
      },
      body: { append(frame) { frames.push(frame); if (load) queueMicrotask(() => frame.onload?.()); } },
    },
  };
  vm.runInNewContext(source, context);
  return { printer: new context.window.StampPrinter(), frames, blobs, revoked, timers, events, canvas, drawing, photo, prints: () => prints };
}

test('prints DS620 bleed raster with the complete stamp scaled uniformly and no uncovered area', async () => {
  let release;
  const f = fixture({ decode: () => new Promise(resolve => { release = resolve; }) });
  const blob = new Blob(['full resolution'], { type: 'image/png' });
  const first = f.printer.print(blob);
  assert.equal(f.printer.print(blob), first);
  await flush(); assert.equal(f.prints(), 0);
  release(); await flush();
  assert.equal(f.prints(), 1); assert.equal(f.blobs[0], blob);
  assert.equal(f.blobs.length, 2);
  assert.deepEqual(f.drawing.at(-1), ['encoded', 1240, 1844, 'image/png']);
  const tiles = f.drawing.filter(op => op[0] === 'image');
  const center = tiles.filter(op => op[4] === 900 && op[5] === 1200);
  assert.equal(center.length, 1, 'the complete source must appear once without cropping');
  assert.deepEqual(center[0].slice(2), [0, 0, 900, 1200, 20, 122, 1200, 1600]);
  const coverage = new Uint8Array(1240 * 1844);
  for (const [, , sx, sy, sw, sh, dx, dy, dw, dh] of tiles) {
    assert.ok(sx >= 0 && sy >= 0 && sx + sw <= 900 && sy + sh <= 1200);
    assert.ok(dx >= 0 && dy >= 0 && dx + dw <= 1240 && dy + dh <= 1844);
    for (let y = dy; y < dy + dh; y++) for (let x = dx; x < dx + dw; x++) coverage[y * 1240 + x]++;
  }
  assert.ok(coverage.every(n => n === 1), 'every pixel, including all four edges, must be covered once');
  assert.equal(f.photo.src, 'blob:local-2');
  assert.equal(f.canvas.width, 1, 'release the temporary raster after encoding');
  assert.match(f.frames[0].srcdoc, /object-fit:cover/);
  assert.match(f.frames[0].srcdoc, /@page\{size:105mm 156.1mm;margin:0\}/);
  assert.match(f.frames[0].srcdoc, /html\{width:105mm;height:156.1mm\}/);
  assert.equal((f.frames[0].srcdoc.match(/<img /g) || []).length, 1);
  assert.doesNotMatch(f.frames[0].srcdoc, /<button|<canvas|https?:/);
  assert.equal(f.frames[0].removed, undefined, 'keep photo until dialog closes');
  assert.equal(f.timers.size, 0, 'no timeout while user chooses a printer');
  f.events.afterprint(); await first;
  assert.equal(f.frames[0].removed, true); assert.deepEqual(f.revoked, ['blob:local-1', 'blob:local-2']);
  assert.equal(f.printer.pending, null);
});

test('cancelled or completed print dialog can be opened again', async () => {
  const f = fixture(); const blob = new Blob(['png']);
  for (let i = 0; i < 2; i++) {
    const result = f.printer.print(blob); await flush(); f.events.afterprint(); await result;
  }
  assert.equal(f.prints(), 2); assert.equal(f.revoked.length, 4);
});

test('image failure offers recovery without opening native printing', async () => {
  const f = fixture({ decode: async () => { throw new Error('invalid'); } });
  await assert.rejects(f.printer.print(new Blob(['bad'])), /暂时无法打开打印/);
  assert.equal(f.prints(), 0); assert.equal(f.revoked.length, 1);
});

test('blocked print API does not leave the app waiting forever', async () => {
  const f = fixture({ supported: false });
  await assert.rejects(f.printer.print(new Blob(['png'])), /打印窗口未打开/);
  assert.equal(f.printer.pending, null); assert.equal(f.frames[0].removed, true);
});

test('loading timeout cleans up the local image and allows retry', async () => {
  const f = fixture({ load: false }); const result = f.printer.print(new Blob(['png']));
  const rejected = assert.rejects(result, /加载有些久/);
  [...f.timers.values()][0](); await rejected;
  assert.equal(f.frames[0].removed, true); assert.equal(f.prints(), 0);
});

test('reset prevents a late decoded photo from opening the print window', async () => {
  let release;
  const f = fixture({ decode: () => new Promise(resolve => { release = resolve; }) });
  const result = f.printer.print(new Blob(['old']));
  const rejected = assert.rejects(result, /打印已取消/);
  await flush(); f.printer.reset(); release(); await rejected; await flush();
  assert.equal(f.prints(), 0); assert.equal(f.revoked.length, 1);
});

test('reset during encoding ignores the result and releases the canvas', async () => {
  let complete;
  const f = fixture({ encode: cb => { complete = cb; } });
  const result = f.printer.print(new Blob(['original']));
  const rejected = assert.rejects(result, /打印已取消/);
  await flush(); f.printer.reset(); complete(new Blob(['late PNG'])); await rejected; await flush();
  assert.equal(f.prints(), 0); assert.equal(f.blobs.length, 1);
  assert.equal(f.canvas.width, 1);
});

test('invalid dimensions or failed encoding cannot print a cropped or blank result', async () => {
  for (const options of [{ naturalWidth: 800 }, { encode: cb => cb(null) }]) {
    const f = fixture(options);
    await assert.rejects(f.printer.print(new Blob(['original'])), /暂时无法打开打印/);
    assert.equal(f.prints(), 0); assert.equal(f.printer.pending, null);
    assert.equal(f.revoked.length, 1);
  }
});
