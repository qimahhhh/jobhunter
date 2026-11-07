// 只负责下载 tarball（不 spawn 任何进程——沙箱禁止子进程管道）。
// 解包交给 PowerShell 里的 tar.exe 做，见 scripts/vendor.ps1。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MIRROR = "https://registry.npmmirror.com";

const PKGS = [
  ["typescript", "5.6.3"],
  ["react", "18.3.1"],
  ["react-dom", "18.3.1"],
  ["@types/react", "18.3.11"],
  ["@types/react-dom", "18.3.1"],
  ["csstype", "3.1.3"],
];

const tmp = path.join(ROOT, ".tarballs");
fs.mkdirSync(tmp, { recursive: true });

for (const [name, version] of PKGS) {
  const base = name.includes("/") ? name.split("/")[1] : name;
  const file = path.join(tmp, `${base}-${version}.tgz`);
  if (fs.existsSync(file) && fs.statSync(file).size > 1024) {
    console.log(`CACHED ${base}`);
    continue;
  }
  const res = await fetch(`${MIRROR}/${name}/-/${base}-${version}.tgz`);
  if (!res.ok) {
    console.log(`SKIP ${name} HTTP ${res.status}`);
    continue;
  }
  fs.writeFileSync(file, Buffer.from(await res.arrayBuffer()));
  console.log(`GET ${base}-${version}.tgz ${fs.statSync(file).size} bytes`);
}
