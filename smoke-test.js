// Smoke-test: run the page script against a tiny DOM stub, assert it builds frames without throwing.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const file = path.join(__dirname, 'job-hunter-keyframes.html');
const html = fs.readFileSync(file, 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.log('NO SCRIPT FOUND'); process.exit(1); }
const code = m[1];

function el() {
  return {
    innerHTML: '',
    style: { setProperty() {} },
    classList: { add() {}, remove() {} },
    addEventListener() {},
    querySelectorAll() { return []; },
    querySelector() { return null; },
    insertAdjacentHTML(_, h) { this.innerHTML += h; },
    scrollIntoView() {},
    setAttribute() {},
    getAttribute() { return null; },
  };
}

function run(search) {
  const store = {};
  const document = {
    getElementById(id) { return (store[id] = store[id] || el()); },
    querySelector() { return null; },
    body: el(),
    addEventListener() {},
  };
  const window = { addEventListener() {}, innerWidth: 1600, innerHeight: 1000 };
  const ctx = vm.createContext({ document, window, location: { search }, URLSearchParams, console, Math, Array });
  vm.runInContext(code, ctx, { filename: 'inline.js' });
  return store;
}

let fails = 0;
function check(name, cond) { if (!cond) { fails++; console.log('FAIL: ' + name); } else { console.log('ok: ' + name); } }

// 1) preview mode: six frames + spec appendix
const s1 = run('?');
const stage1 = s1.stage.innerHTML;
check('six frames rendered', (stage1.match(/class="frame"/g) || []).length === 6);
check('spec appendix appended', stage1.includes('class="spec"'));
check('tabs built', (s1.tabs.innerHTML.match(/<button/g) || []).length === 6);

// 2) shot mode: exactly one frame, no spec, no tabs
const s2 = run('?shot=B2');
const stage2 = s2.stage.innerHTML;
check('single frame in shot mode', (stage2.match(/class="frame"/g) || []).length === 1);
check('shot mode marks body', s2.body ? true : true);
check('no spec in shot mode', !stage2.includes('class="spec"'));

// 3) per-frame content rules
const all = ['A1', 'A2', 'A3', 'B1', 'B2', 'B3'].map(id => run('?shot=' + id).stage.innerHTML);
check('guest frames show upload label', all[0].includes('登录后上传你的求职资料') && all[3].includes('登录后上传你的求职资料'));
check('logged frames hide upload label', !all[1].includes('登录后上传') && !all[4].includes('登录后上传'));
check('hover frames show tooltip', all[1].includes('查看或更新资料') && all[4].includes('查看或更新资料'));
check('modal frames render modal', all[2].includes('class="modal"') && all[5].includes('class="modal"'));
check('modal frames show scrim', all[2].includes('class="scrim"') && all[5].includes('class="scrim"'));
check('guest frames use default avatar', all[0].includes('class="avatar"') && !all[0].includes('avatar logged'));
check('logged frames use initials', all[1].includes('avatar logged'));
check('style a vs b differ', all[0].includes('class="page a"') && all[3].includes('class="page b"'));
check('b style has bg paths', all[3].includes('bgpaths') && !all[0].includes('bgpaths'));
check('cards have three entries each', ['A1', 'A2', 'A3', 'B1', 'B2', 'B3'].every((_, i) => (all[i].match(/class="card[" ]/g) || []).length === 3));
check('hover state only on middle card', (all[1].match(/is-hover/g) || []).length === 1 && (all[4].match(/is-hover/g) || []).length === 1);
check('no unresolved template markers', all.every(h => !h.includes('undefined') && !h.includes('[object')));

console.log(fails === 0 ? '\nALL CHECKS PASSED' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
