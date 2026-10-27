const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/selfit/stamp/printing.js', 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

function fixture({ decode, supported = true, load = true } = {}) {
  const frames = [], blobs = [], revoked = [], events = {}, timers = new Map();
  let prints = 0, decoded = false;
  const photo = { decode: async () => { if (decode) await decode(); decoded = true; } };
  const context = { window: {}, Error,
    URL: { createObjectURL(blob) { blobs.push(blob); return `blob:local-${blobs.length}`; }, revokeObjectURL(url) { revoked.push(url); } },
    setTimeout(fn) { const id = timers.size + 1; timers.set(id, fn); return id; }, clearTimeout(id) { timers.delete(id); },
    document: {
      createElement(tag) {
        assert.equal(tag, 'iframe');
        return { style: {}, setAttribute() {}, remove() { this.removed = true; },
          contentDocument: { querySelector(selector) { assert.equal(selector, 'img'); return photo; } },
          contentWindow: {
            addEventListener(event, cb) { events[event] = cb; }, focus() {},
            print() { assert.ok(decoded, 'print must wait for the PNG to decode'); prints++; if (supported) events.beforeprint(); },
          },
        };
      },
      body: { append(frame) { frames.push(frame); if (load) queueMicrotask(() => frame.onload?.()); } },
    },
  };
  vm.runInNewContext(source, context);
  return { printer: new context.window.StampPrinter(), frames, blobs, revoked, timers, events, prints: () => prints };
}

test('prints the exact PNG locally only after decode; duplicate clicks share one job', async () => {
  let release;
  const f = fixture({ decode: () => new Promise(resolve => { release = resolve; }) });
  const blob = new Blob(['full resolution'], { type: 'image/png' });
  const first = f.printer.print(blob);
  assert.equal(f.printer.print(blob), first);
  await flush(); assert.equal(f.prints(), 0);
  release(); await flush();
  assert.equal(f.prints(), 1); assert.equal(f.blobs[0], blob);
  assert.match(f.frames[0].srcdoc, /object-fit:contain/);
  assert.match(f.frames[0].srcdoc, /@page\{size:4in 6in;margin:0\}/);
  assert.match(f.frames[0].srcdoc, /html\{width:4in;height:6in\}/);
  assert.equal((f.frames[0].srcdoc.match(/<img /g) || []).length, 1);
  assert.doesNotMatch(f.frames[0].srcdoc, /<button|<canvas|https?:/);
  assert.equal(f.frames[0].removed, undefined, 'keep photo until dialog closes');
  assert.equal(f.timers.size, 0, 'no timeout while user chooses a printer');
  f.events.afterprint(); await first;
  assert.equal(f.frames[0].removed, true); assert.deepEqual(f.revoked, ['blob:local-1']);
  assert.equal(f.printer.pending, null);
});

test('cancelled or completed print dialog can be opened again', async () => {
  const f = fixture(); const blob = new Blob(['png']);
  for (let i = 0; i < 2; i++) {
    const result = f.printer.print(blob); await flush(); f.events.afterprint(); await result;
  }
  assert.equal(f.prints(), 2); assert.equal(f.revoked.length, 2);
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
