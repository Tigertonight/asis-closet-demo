/* Wardrobe item controls: a hold reveals deletion; releasing never deletes. */
(function (global) {
  function bind(root) {
    const doc = root.ownerDocument, view = doc.defaultView;
    let hold = null, active = null, suppressCard = null;
    const listeners = [];
    const on = (node, type, handler, options) => {
      node.addEventListener(type, handler, options);
      listeners.push(() => node.removeEventListener(type, handler, options));
    };
    const cardFor = target => target?.closest?.('[data-wardrobe-card]');
    const photoFor = target => target?.closest?.('[data-wardrobe-hold]');
    function cancel() {
      if (hold) view.clearTimeout(hold.timer);
      hold = null;
    }
    function dismiss() {
      cancel();
      if (!active) return;
      active.classList.remove('show-delete');
      active.querySelector('[data-action="delete-item"]').hidden = true;
      active.querySelector('[data-wardrobe-hold]').setAttribute('aria-expanded', 'false');
      active = null;
    }
    function reveal(photo, keyboard = false) {
      const card = cardFor(photo);
      if (!card?.isConnected || photo.disabled) return;
      dismiss();
      active = card;
      card.classList.add('show-delete');
      photo.setAttribute('aria-expanded', 'true');
      const button = card.querySelector('[data-action="delete-item"]');
      button.hidden = false;
      if (keyboard) button.focus({preventScroll:true});
    }
    on(doc, 'pointerdown', event => {
      suppressCard = null;
      cancel();
      if (cardFor(event.target) !== active) dismiss();
      const photo = photoFor(event.target);
      if (!photo || !root.contains(photo) || photo.disabled || event.button !== 0 || event.isPrimary === false) return;
      hold = {id:event.pointerId, x:event.clientX, y:event.clientY, timer:view.setTimeout(() => {
        reveal(photo);
        suppressCard = cardFor(photo);
      }, 500)};
    });
    on(view, 'pointermove', event => {
      if (hold && event.pointerId === hold.id && Math.hypot(event.clientX - hold.x, event.clientY - hold.y) > 10) cancel();
    }, {passive:true});
    on(view, 'pointerup', cancel);
    on(view, 'pointercancel', dismiss);
    on(view, 'blur', dismiss);
    on(root, 'scroll', dismiss, {capture:true, passive:true});
    on(root, 'click', event => {
      if (event.detail !== 0 && suppressCard && cardFor(event.target) === suppressCard) {
        event.preventDefault();
        event.stopImmediatePropagation();
        suppressCard = null;
      }
    }, true);
    on(root, 'contextmenu', event => {
      const photo = photoFor(event.target);
      if (!photo) return;
      event.preventDefault();
      reveal(photo);
    });
    on(root, 'keydown', event => {
      if (event.key === 'Escape' && active) {
        const photo = active.querySelector('[data-wardrobe-hold]');
        dismiss();
        photo.focus({preventScroll:true});
        event.preventDefault();
      } else if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
        const photo = photoFor(event.target);
        if (!photo) return;
        event.preventDefault();
        reveal(photo, true);
      }
    });
    return {reset() { dismiss(); suppressCard = null; }, destroy() { dismiss(); listeners.forEach(remove => remove()); }};
  }
  global.SelfitWardrobeGestures = {bind};
})(typeof window === 'undefined' ? globalThis : window);
