/* Print the existing full-resolution photo locally; no upload or printer service. */
(() => {
  class StampPrinter {
    print(blob) {
      if (this.pending) return this.pending;
      if (!blob) return Promise.reject(new Error('请先完成邮票制作。'));
      const frame = document.createElement('iframe');
      frame.title = '高清邮票打印';
      frame.setAttribute('aria-hidden', 'true'); frame.tabIndex = -1;
      // Keep a real browsing context: display:none can produce blank printouts.
      frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:900px;height:1200px;border:0;pointer-events:none';
      const url = URL.createObjectURL(blob);
      let settle;
      const pending = new Promise((resolve, reject) => { settle = { resolve, reject }; });
      this.pending = pending;
      const job = { frame, url, printing: false, finished: false, timer: 0 };
      this.job = job;
      const finish = error => {
        if (job.finished) return;
        job.finished = true; clearTimeout(job.timer);
        frame.onload = null;
        frame.remove(); URL.revokeObjectURL(url);
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
        <style>@page{size:auto;margin:0}html,body{margin:0;padding:0;width:100%;height:100%;background:white}img{display:block;width:100%;height:100%;object-fit:contain;print-color-adjust:exact;-webkit-print-color-adjust:exact}</style>
        </head><body><img src="${url}" alt=""></body></html>`;
      document.body.append(frame);
      return pending;
    }
    reset() { this.job?.cancel(); }
  }
  window.StampPrinter = StampPrinter;
})();
