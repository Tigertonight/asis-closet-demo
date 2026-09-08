(function (root) {
  'use strict';

  const create = ({stages, art, lines, percent, loadImage, random = Math.random}) => {
    let run = 0, active = false, requested = 0;
    const stop = () => { active = false; run += 1; };

    const start = () => {
      stop();
      active = true;
      requested = 0;
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
          art.dataset.stage = String(illustration.percent);
        }
        art.hidden = false;
      });
    };

    const update = (value) => {
      if (!active) return;
      const progress = Number(value);
      if (!Number.isFinite(progress)) return;
      const target = [...stages].reverse().find(stage => progress >= stage.percent) || stages[0];
      for (const stage of stages.filter(stage => stage.percent > requested && stage.percent <= target.percent)) {
        percent.textContent = `${stage.percent}%`;
        percent.setAttribute('aria-valuenow', String(stage.percent));
        const row = lines.ownerDocument.createElement('p');
        row.className = 'loading-line';
        row.dataset.progress = String(stage.percent);
        row.textContent = stage.line;
        lines.append(row);
      }
      requested = Math.max(requested, target.percent);
    };

    return {start, update, stop};
  };

  root.SelfitLoadingStory = {create};
})(window);
