// Rasterize bitmap-heavy design SVGs without changing their composition/alpha.
// Requires Playwright and Chrome; set PLAYWRIGHT_MODULE for a bundled runtime.
const fs = require('node:fs'), path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
(async () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'app/static/selfit/display-assets.json')));
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  let count = 0, before = 0, after = 0;
  try {
    const page = await browser.newPage();
    for (const [source, target] of Object.entries(manifest)) {
      if (!source.endsWith('.svg')) continue;
      const svg = fs.readFileSync(path.join(root, source), 'utf8');
      const data = await page.evaluate(async svg => {
        const doc = new DOMParser().parseFromString(svg, 'image/svg+xml').documentElement;
        const box = doc.getAttribute('viewBox').split(/[ ,]+/).map(Number);
        const width = parseFloat(doc.getAttribute('width')) || box[2];
        const height = parseFloat(doc.getAttribute('height')) || box[3];
        const ratio = Math.min(2, 1600 / Math.max(width, height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
        doc.setAttribute('width', canvas.width); doc.setAttribute('height', canvas.height);
        const object = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(doc)], {type:'image/svg+xml'}));
        try {
          const image = new Image(); image.src = object; await image.decode();
          canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
          return canvas.toDataURL('image/webp', .9).split(',')[1];
        } finally { URL.revokeObjectURL(object); }
      }, svg);
      const bytes = Buffer.from(data, 'base64');
      fs.writeFileSync(path.join(root, target), bytes);
      count++; before += Buffer.byteLength(svg); after += bytes.length;
    }
  } finally { await browser.close(); }
  console.log(JSON.stringify({count, before, after}));
})().catch(error => { console.error(error); process.exitCode = 1; });
