(() => {
  'use strict';
  // Both editors use the same catalog. Gender comes only from the saved profile,
  // never from a photo, persona, URL, or the current manual selection.
  const root = '/static/selfit/assets/manual-selection/';
  const skinValues = ['冷白肤', '暖白肤', '中性自然肤', '橄榄肤', '暖黄肤', '小麦色'];
  const skin = (colors, labels) => skinValues.map((value, i) => ({value, label: labels[i], color: colors[i]}));
  const art = (value, label, name, male, body = false, aliases = []) => ({
    value, label, aliases,
    src: root + (male ? 'male/' + name + '.png' : name + '@4x.png?v=20260826'),
    width: male ? (body ? 328 : 359) : (body ? 144 : 156),
    height: male ? (body ? 800 : 680) : (body ? 408 : 240),
  });
  const catalogs = {
    female: {
      skin: skin(['#FFDED7','#FCD1BB','#F2C9B8','#E6D3AF','#E6BEAA','#CB956C'], ['冷白','暖白','中性','橄榄','暖黄','小麦']),
      faceShape: [
        art('菱形脸','菱型脸','face-diamond',false), art('方脸','方型脸','face-square',false),
        art('圆脸','圆型脸','face-round',false), art('椭圆脸','鹅蛋脸','face-oval',false),
        art('心形脸','心型脸','face-heart',false),
      ],
      bodyShape: [
        art('梨型','梨型','body-pear',false,true), art('倒三角型','倒三角型','body-inverted-triangle',false,true),
        art('沙漏型','沙漏型','body-hourglass',false,true), art('矩型','矩型','body-rectangle',false,true),
        art('苹果型','苹果型','body-apple',false,true),
      ],
    },
    male: {
      // Exact reference values from male-skin-tone-palette/colors.json.
      skin: skin(['#F2D0C7','#EFC2A8','#E5B4A1','#D5B987','#DDA17E','#C98256'], ['冷白','暖白','中性自然肤','橄榄','暖黄','小麦']),
      faceShape: [
        art('方脸','方形脸','face-square',true), art('菱形脸','菱形脸','face-diamond',true),
        art('倒三角脸','倒三角脸','face-inverted-triangle',true), art('椭圆脸','椭圆脸','face-oval',true),
        art('圆脸','圆形脸','face-round',true),
      ],
      bodyShape: [
        // Text-free artwork; the option label below each image remains accessible.
        art('梯形','梯形','body-trapezoid-no-label',true,true), art('三角形','三角形','body-triangle-no-label',true,true,['梨型']),
        art('倒三角形','倒三角形','body-inverted-triangle-no-label',true,true,['倒三角型']),
        art('矩形','矩形','body-rectangle-no-label',true,true,['矩型']), art('椭圆形','椭圆形','body-oval-no-label',true,true,['苹果型']),
      ],
    },
  };
  const getOptions = (gender, field) => catalogs[gender === 'male' ? 'male' : 'female'][field] || [];
  const matches = (option, value) => option.value === value || (option.aliases || []).includes(value);
  const findOption = (gender, field, value) => getOptions(gender, field).find(option => matches(option, value));
  const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const renderOnboarding = (form, gender) => {
    form.dataset.gender = gender === 'male' ? 'male' : 'female';
    for (const [field, selector] of Object.entries({skin:'.skin-options', faceShape:'.manual-visual-options--face', bodyShape:'.manual-visual-options--body'})) {
      form.querySelector(selector).innerHTML = getOptions(gender, field).map(option => {
        const visual = field === 'skin'
          ? `<i style="--tone:${option.color}"></i>`
          : `<span class="manual-art"><img src="${esc(option.src)}" width="${option.width}" height="${option.height}" alt="${esc(option.label)}示意" /></span>`;
        return `<button type="button" data-manual="${field}" data-value="${esc(option.value)}" aria-pressed="false">${visual}<span class="${field === 'skin' ? '' : 'manual-option-label'}">${esc(option.label)}</span></button>`;
      }).join('');
    }
  };
  window.SelfitManualOptions = {getOptions, findOption, matches, renderOnboarding};
})();
