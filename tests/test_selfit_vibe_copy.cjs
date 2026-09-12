const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');

test('Vibe third question shows copy only and preserves answer identities', () => {
  const html = fs.readFileSync(path.resolve(__dirname, '../app/static/selfit/index.html'), 'utf8');
  const field = html.match(/<fieldset data-question="expression">([\s\S]*?)<\/fieldset>/)?.[1];
  assert.ok(field, 'expression question exists');
  const answers = [...field.matchAll(/<button\b[^>]*data-answer="([A-E])"[^>]*>([^<]*)<\/button>/g)]
    .map(([, value, label]) => [value, label.trim()]);
  assert.deepEqual(answers, [
    ['A', '宽松叠穿、自然妆发、舒服最重要'],
    ['B', '水光妆、精致发型、配色必须统一'],
    ['C', '修身剪裁、立体妆容、气场必须到位'],
    ['D', '东方元素、利落眉眼、含蓄但有神韵'],
    ['E', '衬衫牛仔、微乱卷发、再加一抹红唇'],
  ]);
  assert.equal((field.match(/aria-pressed="false"/g) || []).length, 5);
});
