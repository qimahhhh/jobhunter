// 静态检查：TSX 里用到的 class 是否都在 CSS 里定义过
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

const files = walk(ROOT);
const cssFiles = files.filter((f) => f.endsWith(".css"));
const tsxFiles = files.filter((f) => f.endsWith(".tsx"));

const defined = new Set();
for (const f of cssFiles) {
  const css = fs.readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of css.matchAll(/\.([a-zA-Z][\w-]*)/g)) defined.add(m[1]);
}

const used = new Map(); // class -> Set<file>
for (const f of tsxFiles) {
  const src = fs.readFileSync(f, "utf8");
  const rel = path.relative(ROOT, f);

  // className="a b c"
  for (const m of src.matchAll(/className=(?:"([^"]*)"|{`([^`]*)`})/g)) {
    const raw = (m[1] ?? m[2] ?? "").replace(/\$\{[^}]*\}/g, " ");
    for (const c of raw.split(/\s+/)) {
      if (!c || !/^[a-zA-Z][\w-]*$/.test(c)) continue;
      if (!used.has(c)) used.set(c, new Set());
      used.get(c).add(rel);
    }
  }
  // className={`...`} 三元里的字符串字面量
  for (const m of src.matchAll(/className=\{`([^`]*)`\}/g)) {
    for (const s of m[1].matchAll(/"([^"]+)"|'([^']+)'/g)) {
      for (const c of (s[1] ?? s[2]).split(/\s+/)) {
        if (!/^[a-zA-Z][\w-]*$/.test(c)) continue;
        if (!used.has(c)) used.set(c, new Set());
        used.get(c).add(rel);
      }
    }
  }
}

const missing = [...used.entries()]
  .filter(([c]) => !defined.has(c))
  .map(([c, fs]) => `${c}  ←  ${[...fs].join(", ")}`);

console.log("CSS 类总数:", defined.size);
console.log("TSX 使用的类:", used.size);
console.log("未定义:", missing.length);
missing.forEach((m) => console.log("  " + m));
