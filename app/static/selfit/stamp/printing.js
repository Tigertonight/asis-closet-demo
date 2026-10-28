/* Build a six-inch print locally; preserve the original stamp for saving/sharing. */
(() => {
  async function sixInchPhoto(photo) {
    if (photo.naturalWidth !== 900 || photo.naturalHeight !== 1200) throw new Error('Unexpected stamp size');
    const canvas = document.createElement('canvas');
    canvas.width = 900; canvas.height = 1350;
    try {
      const ctx = canvas.getContext('2d');
      // Flatten transparent backgrounds onto paper white. For colored stamps,
      // extend only the outermost background rows, including their paper tint.
      // The entire original remains centered, pixel-for-pixel, without cropping.
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, 900, 1350);
      ctx.drawImage(photo, 0, 0, 900, 1, 0, 0, 900, 75);
      ctx.drawImage(photo, 0, 1199, 900, 1, 0, 1275, 900, 75);
      ctx.drawImage(photo, 0, 75);
      return await new Promise((resolve, reject) => canvas.toBlob(
        blob => blob ? resolve(blob) : reject(new Error('Print image could not be prepared')), 'image/png'));
    } finally { canvas.width = canvas.height = 1; }
  }
  class StampPrinter {
    print(blob) {
      if (this.pending) return this.pending;
      if (!blob) return Promise.reject(new Error('请先完成邮票制作。'));
      const frame = document.createElement('iframe');
      frame.title = '高清邮票打印';
      frame.setAttribute('aria-hidden', 'true'); frame.tabIndex = -1;
      // Keep a real browsing context: display:none can produce blank printouts.
      frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:900px;height:1350px;border:0;pointer-events:none';
      const url = URL.createObjectURL(blob);
      let settle;
      const pending = new Promise((resolve, reject) => { settle = { resolve, reject }; });
      this.pending = pending;
      const job = { frame, urls: [url], printing: false, finished: false, timer: 0 };
      this.job = job;
      const finish = error => {
        if (job.finished) return;
        job.finished = true; clearTimeout(job.timer);
        frame.onload = null;
        frame.remove(); job.urls.forEach(value => URL.revokeObjectURL(value));
        if (this.job === job) { this.job = null; this.pending = null; }
        if (error) settle.reject(error); else settle.resolve();
      };
      job.cancel = () => finish(new Error('打印已取消。'));
      job.timer = setTimeout(() => finish(new Error('打印照片加载有些久，请重新尝试。')), 20000);
      frame.onload = async () => {
        try {
          const photo = frame.contentDocument.querySelector('img');
          await photo.decode();
          if (job.finished) return;
          const printBlob = await sixInchPhoto(photo);
          if (job.finished) return;
          const printUrl = URL.createObjectURL(printBlob);
          job.urls.push(printUrl); photo.src = printUrl;
          await photo.decode();
          if (job.finished) return;
          clearTimeout(job.timer);
          const target = frame.contentWindow;
          target.addEventListener('beforeprint', () => { job.printing = true; }, { once: true });
          // Closing/cancelling the dialog is not evidence of a physical print.
          target.addEventListener('afterprint', () => finish(), { once: true });
          target.focus(); target.print();
          if (!job.printing && !job.finished) finish(new Error('打印窗口未打开，请使用电脑浏览器，或先保存照片后打印。'));
        } catch (_) {
          finish(new Error('暂时无法打开打印，请重试或先保存照片后打印。'));
        }
      };
      frame.srcdoc = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>WOKEN DAY 纪念邮票</title>
        <style>@page{size:4in 6in;margin:0}html{width:4in;height:6in}body{margin:0;padding:0;width:100%;height:100%;background:white}img{display:block;width:100%;height:100%;object-fit:contain;break-inside:avoid;print-color-adjust:exact;-webkit-print-color-adjust:exact}</style>
        </head><body><img src="${url}" alt=""></body></html>`;
      document.body.append(frame);
      return pending;
    }
    reset() { this.job?.cancel(); }
  }
  window.StampPrinter = StampPrinter;
})();
