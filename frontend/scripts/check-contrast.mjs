// تحقق آلي من نسب التباين (WCAG 2.1) لثنائيات الألوان في tokens.css
// التشغيل:  node check-contrast.mjs ./tokens.css      (يخرج بالرمز 1 عند أي فشل)
import { readFileSync } from "node:fs";

const file = process.argv[2] ?? "./tokens.css";
const css = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

// 1) اقرأ كتل CSS وخذ التعريفات --name: value
const blocks = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, sel, body]) => ({
  sel: sel.trim(),
  vars: Object.fromEntries([...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(([, k, v]) => [k, v.trim()])),
}));
const prim  = blocks.find((b) => b.sel === ":root")?.vars ?? {};
const dark  = blocks.find((b) => b.sel.includes('[data-theme="dark"]'))?.vars ?? {};
const light = blocks.find((b) => b.sel === '[data-theme="light"]')?.vars ?? {};

const resolve = (map, name, depth = 0) => {
  let v = map[name];
  if (v === undefined || depth > 8) return undefined;
  const m = v.match(/^var\((--[\w-]+)\)$/);
  return m ? resolve(map, m[1], depth + 1) : v;
};

// 2) أدوات اللون
const hex2rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const lum = ([r, g, b]) => {
  const f = (c) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a, b) => {
  const [x, y] = [lum(hex2rgb(a)), lum(hex2rgb(b))].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

// 3) الثنائيات المطلوبة: [نص/عنصر, خلفية, الحد الأدنى]
const pairs = [
  ["--text-1", "--bg-app", 7], ["--text-1", "--bg-panel", 7], ["--text-1", "--bg-raised", 7],
  ["--text-2", "--bg-panel", 4.5], ["--text-2", "--bg-raised", 4.5],
  ["--text-3", "--bg-panel", 4.5], ["--text-3", "--bg-raised", 4.5],
  ["--brand-text", "--bg-panel", 4.5], ["--brand-text", "--bg-app", 4.5],
  ["--text-on-brand", "--brand", 4.5],
  ["--ok", "--bg-panel", 4.5], ["--warn", "--bg-panel", 4.5], ["--crit", "--bg-panel", 4.5],
  ["--brand", "--bg-panel", 3],          // عناصر غير نصية (حلقة الثقة، الحدود النشطة)
  ["--focus-ring", "--bg-panel", 3],
];

let failed = 0;
for (const [name, map] of [["dark", { ...prim, ...dark }], ["light", { ...prim, ...dark, ...light }]]) {
  console.log(`\n[${name}]`);
  for (const [fg, bg, min] of pairs) {
    const a = resolve(map, fg), b = resolve(map, bg);
    if (!/^#[0-9a-f]{6}$/i.test(a ?? "") || !/^#[0-9a-f]{6}$/i.test(b ?? "")) {
      console.log(`  SKIP  ${fg} on ${bg}  (${a} / ${b})`); failed++; continue;
    }
    const r = ratio(a, b);
    const ok = r >= min;
    if (!ok) failed++;
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${fg.padEnd(16)} on ${bg.padEnd(12)} ${r.toFixed(2).padStart(5)}:1  (min ${min})`);
  }
}
console.log(failed ? `\n${failed} check(s) failed` : "\nAll contrast checks passed");
process.exit(failed ? 1 : 0);
