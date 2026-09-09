/* Display-only photo framing. Original files and try-on inputs are never changed. */
((root) => {
  "use strict";
  function detectSolidFrame({data, width, height}) {
    if (width < 32 || height < 32) return null;
    const background = Array.from(data.slice(0, 3));
    const matches = (x, y) => {
      const i = (y * width + x) * 4;
      return data[i + 3] >= 250 && background.every((c, k) => Math.abs(data[i + k] - c) <= 3);
    };
    const row = y => {
      for (let x = 0; x < width; x++) if (!matches(x, y)) return false;
      return true;
    };
    const column = x => {
      for (let y = 0; y < height; y++) if (!matches(x, y)) return false;
      return true;
    };
    // All four edges must be the same opaque, uniform color. A wall, gradient,
    // transparent cutout or subject touching an edge must keep its original crop.
    if (!row(0) || !row(height - 1) || !column(0) || !column(width - 1)) return null;
    let left = 0, right = 0, top = 0, bottom = 0;
    while (left < width * .22 && column(left)) left++;
    while (right < width * .22 && column(width - 1 - right)) right++;
    while (top < height * .12 && row(top)) top++;
    while (bottom < height * .12 && row(height - 1 - bottom)) bottom++;
    if (Math.min(left, right) < width * .01 || Math.min(top, bottom) < height * .01 ||
        Math.max(left, right) >= width * .22 || Math.max(top, bottom) >= height * .12 ||
        Math.abs(left - right) > Math.max(2, width * .02) ||
        Math.abs(top - bottom) > Math.max(2, height * .02)) return null;
    const corners = [[left, top], [width - 1 - right, top],
      [left, height - 1 - bottom], [width - 1 - right, height - 1 - bottom]];
    const fill = [0, 1, 2].map(channel => Math.round(corners.reduce((sum, [x, y]) =>
      sum + data[(y * width + x) * 4 + channel], 0) / corners.length));
    return {x:left / width, y:top / height, width:(width - left - right) / width,
      height:(height - top - bottom) / height, background:`rgb(${fill.join(',')})`};
  }

  function createPresenter({Image, document, URL, setTimeout, clearTimeout}) {
    const cache = new Map();
    function prepare(src) {
      if (cache.has(src)) return cache.get(src).promise;
      const entry = {};
      cache.set(src, entry);
      entry.promise = new Promise(resolve => {
        const image = new Image();
        let finished = false;
        let fit = "contain";
        const finish = (displaySrc = src, crop = null) => {
          if (finished) {
            if (displaySrc !== src) URL.revokeObjectURL(displaySrc);
            return;
          }
          finished = true;
          clearTimeout(timer);
          image.onload = image.onerror = null;
          resolve({src:displaySrc, crop, fit});
          // The active decoded image remains usable after revocation, while
          // old model/result previews cannot accumulate without a bound.
          while (cache.size > 12) {
            const [key, old] = cache.entries().next().value;
            cache.delete(key);
            old.promise.then(value => { if (value.src !== key) URL.revokeObjectURL(value.src); });
          }
        };
        const timer = setTimeout(() => finish(), 5000);
        image.crossOrigin = "anonymous";
        image.onerror = () => finish();
        image.onload = () => {
          // Full-body portraits share a vertical scale before and after try-on.
          // Keep wide/unknown photos contained instead of magnifying a narrow slice.
          const aspect = image.naturalWidth / image.naturalHeight;
          fit = aspect > 0 && aspect <= .75 ? "height" : "contain";
          try {
            // Keep normal model photos at native resolution. A 512px probe
            // rounded the crop outward and left a visible one-pixel seam.
            const scale = Math.min(1, 1600 / Math.max(image.naturalWidth, image.naturalHeight));
            const probe = document.createElement("canvas");
            probe.width = Math.max(1, Math.round(image.naturalWidth * scale));
            probe.height = Math.max(1, Math.round(image.naturalHeight * scale));
            const context = probe.getContext("2d", {willReadFrequently:true});
            context.drawImage(image, 0, 0, probe.width, probe.height);
            const crop = detectSolidFrame(context.getImageData(0, 0, probe.width, probe.height));
            if (!crop) return finish();
            const w = image.naturalWidth * crop.width, h = image.naturalHeight * crop.height;
            const outputScale = Math.min(1, 1600 / Math.max(w, h));
            const output = document.createElement("canvas");
            output.width = Math.max(1, Math.round(w * outputScale));
            output.height = Math.max(1, Math.round(h * outputScale));
            output.getContext("2d").drawImage(image, image.naturalWidth * crop.x,
              image.naturalHeight * crop.y, w, h, 0, 0, output.width, output.height);
            output.toBlob(blob => finish(blob ? URL.createObjectURL(blob) : src, blob ? crop : null), "image/png");
          } catch {
            // If pixel inspection is unavailable, retain the original source;
            // its decoded dimensions still determine the display fit.
            finish();
          }
        };
        image.src = src;
      });
      return entry.promise;
    }
    function show(photo, src) {
      if (!photo) return;
      const frame = photo.closest(".mirror-photo-frame");
      photo.dataset.mirrorSource = src;
      if (!frame) { photo.src = src; return; }
      photo.src = src;
      photo.style.backgroundColor = "";
      frame.dataset.trimmed = "false";
      frame.dataset.fit = "contain";
      prepare(src).then(display => {
        if (!photo.isConnected || photo.dataset.mirrorSource !== src) return;
        photo.src = display.src;
        photo.style.backgroundColor = display.crop?.background || "";
        frame.dataset.trimmed = String(Boolean(display.crop));
        frame.dataset.fit = display.fit;
      });
    }
    function clear() {
      for (const [src, entry] of cache) entry.promise.then(value => {
        if (value.src !== src) URL.revokeObjectURL(value.src);
      });
      cache.clear();
    }
    return {show, clear};
  }
  if (typeof module !== "undefined" && module.exports) module.exports = {detectSolidFrame, createPresenter};
  else root.SelfitMirrorPhoto = createPresenter(root);
})(typeof window !== "undefined" ? window : globalThis);
