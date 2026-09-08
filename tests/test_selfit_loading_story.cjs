const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function element() {
  const classes = new Set();
  return {children: [], dataset: {}, attributes: {}, textContent: '', hidden: false,
    classList: {add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value)},
    setAttribute(name, value) {this.attributes[name] = value;},
    append(child) {this.children.push(child);}, replaceChildren() {this.children = [];},
    ownerDocument: {createElement: () => element()},
  };
}
const root = {};
vm.runInNewContext(fs.readFileSync('app/static/selfit/selfit-loading.js', 'utf8'), {window: root});
const stages = [25, 50, 75, 100].map((percent, i) => ({percent, src: `art-${i}.png`, line: `文案第${i + 1}行`}));
const tick = async () => {for (let i = 0; i < 8; i++) await Promise.resolve();};

(async () => {
  const art = element(), lines = element(), percent = element(), images = [], chosen = [];
  let random = .6;
  const story = root.SelfitLoadingStory.create({stages, art, lines, percent,
    random: () => random,
    loadImage: src => {chosen.push(src); return new Promise(resolve => images.push({src, resolve}));},
  });
  story.start();
  images[0].resolve(images[0].src);
  story.update(25);
  assert.equal(lines.children[0].textContent, stages[0].line, 'whole sentence appears synchronously');
  await tick();
  assert.equal(art.src, 'art-2.png');
  assert.equal(percent.textContent, '25%');
  assert.equal(lines.children.length, 1);
  story.update(25); story.update(75); story.update(50); story.update(75);
  assert.equal(percent.textContent, '75%');
  assert.deepEqual(lines.children.map(row => row.dataset.progress), ['25', '50', '75']);
  assert.deepEqual(lines.children.map(row => row.textContent), stages.slice(0, 3).map(stage => stage.line));
  assert.equal(art.src, 'art-2.png');
  assert.equal(chosen.length, 1, 'progress must not pick another illustration');
  story.update(100);
  assert.equal(lines.children.length, 4);
  assert.deepEqual(lines.children.map(row => row.textContent), stages.map(stage => stage.line));
  assert.equal(percent.attributes['aria-valuenow'], '100');
  assert(!lines.children.some(row => row.classList.contains('is-typing')));

  random = .1; story.start(); story.update(25); await tick();
  random = .9; story.start();
  assert.equal(lines.children.length, 0, 'a new run clears previous sentences');
  story.update(100);
  images[2].resolve('latest-art.png'); images[1].resolve('stale-art.png');
  await tick();
  assert.equal(art.src, 'latest-art.png', 'a late image cannot replace the next run');
  assert.equal(lines.children.length, 4);
  assert.equal(chosen.length, 3);
  story.stop(); story.update(100); await tick();
  assert.equal(lines.children.length, 4);

  for (const sample of [0, .25, .5, .999]) {
    random = sample; story.start(); story.update(25);
    images.at(-1).resolve(images.at(-1).src);
    await tick();
    assert.equal(art.src, stages[Math.floor(sample * 4)].src);
    assert.equal(lines.children.length, 1, 'every visit starts a fresh story');
  }
  const previousArt = art.src;
  story.start(); story.update(100);
  images.at(-1).resolve(''); await tick();
  assert.equal(art.src, previousArt, 'failed artwork keeps the existing fallback');
  assert.equal(art.hidden, false);
  assert.equal(percent.textContent, '100%', 'image failure must not block the text or report');
  console.log('Random artwork, immediate cumulative text, ordered progress, deduplication, resets and image recovery passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
