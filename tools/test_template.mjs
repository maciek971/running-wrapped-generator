import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const path = process.argv[2] || new URL('../template.html', import.meta.url);
const src = readFileSync(path, 'utf8');
// Parse every inline script too: malformed generated JSON must block publishing.
for (const m of src.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)) {
  if (!/\bsrc\s*=/.test(m[1])) new vm.Script(m[2]);
}
const hostile = '<img src=x onerror="alert(1)"> & Łódź';
const escaped = '&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; Łódź';
const nodes = new Map();
const $ = id => {
  if (!nodes.has(id)) nodes.set(id, {innerHTML: '', children: [], querySelectorAll: () => [], addEventListener() {}});
  return nodes.get(id);
};
const helper = src.match(/\/\* --HTML-ESCAPE-START-- \*\/([\s\S]*?)\/\* --HTML-ESCAPE-END-- \*\//)?.[1] || '';
const carousel = src.split('/* ---------- map carousel on dark Leaflet tiles ---------- */')[1]
  .split('/* ---------- scale / perspective ---------- */')[0];
vm.runInNewContext(helper + carousel, {
  DATA: {maps: [{id: 'home', title: hostile, subtitle: hostile, tracks: []}]},
  $, window: {L: {map() {}}}, matchMedia: () => ({matches: true}),
  addEventListener() {}, IntersectionObserver: class {observe() {}},
});
assert.ok($('#mapSlides').innerHTML.includes(escaped), 'map labels must display literal text');
assert.ok(!$('#mapSlides').innerHTML.includes('<img'), 'map label injected an HTML element');
assert.ok($('#mapDots').innerHTML.includes(escaped), 'map accessibility label must escape quotes');
console.log('OK — inline JavaScript syntax and map label escaping');
const pinMap = src.split('/* ---------- gdzie: dom + Polska pin-map ---------- */')[1]
  .split('/* ---------- screenshot mode')[0];
vm.runInNewContext(helper + pinMap, {
  $, DATA: {lifetime: {runs: 2}, poland: {
    w: 1000, h: 600, outline: 'M0,0 L100,100', home: {x: 200, y: 200, count: 1},
    places: [{x: 400, y: 400, count: 1, names: [hostile]}],
  }},
});
assert.ok($('#plMap').innerHTML.includes(escaped), 'pin names must display literal text');
assert.ok(!$('#plMap').innerHTML.includes('<img'), 'pin name injected an HTML element');
console.log('OK — SVG pin label escaping');
