(function (root) {
  'use strict';

  const create = ({stages, art, lines, percent, loadImage, random = Math.random}) => {
    let run = 0, active = false, requested = 0;
    let queue = Promise.resolve(), lastShownAt = 0;
    const stop = () => { active = false; run += 1; };

    const start = () => {
      stop();
      active = true;
      requested = 0;
      queue = Promise.resolve();
      lastShownAt = 0;
      lines.replaceChildren();
      percent.textContent = '';
      percent.setAttribute('aria-valuenow', '0');
      const currentRun = run;
      const illustration = stages[Math.min(stages.length - 1, Math.floor(random() * stages.length))];
      art.hidden = true;
      // Pick once for this visit. Progress only changes the text below the image.
      void loadImage(illustration.src).then(source => {
        if (!active || run !== currentRun) return;
        if (source) {
          art.src = source;
          art.dataset.stage = String(illustration.artStage || illustration.percent);
        }
        art.hidden = false;
      });
    };

    const update = (value) => {
      if (!active) return;
      const progress = Number(value);
      if (!Number.isFinite(progress)) return;
      const target = [...stages].reverse().find(stage => progress >= stage.percent) || stages[0];
      const currentRun = run;
      for (const stage of stages.filter(stage => stage.percent > requested && stage.percent <= target.percent)) {
        queue = queue.then(async () => {
        if (!active || run !== currentRun) return;
        const wait = Math.max(0, 1400 - (Date.now() - lastShownAt));
        if (wait) await new Promise(resolve => setTimeout(resolve, wait));
        if (!active || run !== currentRun) return;
        percent.textContent = `${stage.percent}%`;
        percent.setAttribute('aria-valuenow', String(stage.percent));
        const row = lines.ownerDocument.createElement('p');
        row.className = 'loading-line';
        row.dataset.progress = String(stage.percent);
        row.textContent = stage.line;
        lines.prepend(row);
        lastShownAt = Date.now();
        if (!root.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
          const shift = row.getBoundingClientRect().height + 8;
          [...lines.children].slice(1).forEach(previous => previous.animate?.(
            [{ transform: `translateY(-${shift}px)` }, { transform: 'translateY(0)' }],
            { duration: 650, easing: 'cubic-bezier(.22,1,.36,1)' },
          ));
        }
        });
      }
      requested = Math.max(requested, target.percent);
      return queue;
    };

    return {start, update, stop};
  };

  root.SelfitLoadingStory = {create};
})(window);
