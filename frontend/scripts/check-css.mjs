// 检查跨文件重复定义的选择器（值不同就可能互相覆盖）
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src/styles");
const files = fs.readdirSync(ROOT).filter((f) => f.endsWith(".css"));

const map = new Map(); // selector -> [{file, body}]

for (const f of files) {
  const css = fs.readFileSync(path.join(ROOT, f), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(css))) {
    const sel = m[1].trim().replace(/\s+/g, " ");
    const body = m[2].trim().replace(/\s+/g, " ");
    if (!sel || sel.startsWith("@")) continue;
    if (!map.has(sel)) map.set(sel, []);
    map.get(sel).push({ file: f, body });
  }
}

let conflicts = 0;
for (const [sel, defs] of map) {
  if (defs.length < 2) continue;
  const bodies = new Set(defs.map((d) => d.body));
  if (bodies.size > 1) {
    conflicts++;
    console.log(`⚠ ${sel}`);
    defs.forEach((d) => console.log(`    ${d.file}: ${d.body.slice(0, 90)}`));
  }
}
console.log(`\n重复定义且取值不同的选择器：${conflicts}`);
