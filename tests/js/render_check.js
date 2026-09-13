// 画面を実際に描かせて、実行時エラーを捕まえる。
//
// ★HTTP 200 は「配れた」だけで「描けた」ではない（2026-09-12、真っ暗を何度も出した）。
//   canvas を偽物にして、draw() を何度か回す。**落ちれば分かる。**
const fs = require('fs');
// ★乱数を固定する。**落ちたときに同じ条件で再現できないと直せない。**
//   2026-09-13、full run で1回だけ落ちて、単体では21回通った。
//   種を渡せば毎回同じ絵になる（SEED=... で変えて別の並びも試せる）
function seededMath(seed){
  let s = seed >>> 0;
  return new Proxy(Math, {get(t, k){
    if (k === 'random') return () => {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
    const v = t[k];
    return typeof v === 'function' ? v.bind(t) : v;
  }});
}
const SEEDED = seededMath(Number(process.env.SEED || 20260913));

const vm = require('vm');
const path = process.argv[2];
const html = fs.readFileSync(path, 'utf8');
const js = html.match(/<script>([\s\S]*)<\/script>/)[1];

const calls = { fillText: 0, fill: 0, stroke: 0, fillRect: 0, arc: 0 };
function ctx() {
// ★本物の canvas と同じ厳しさにする。**透明度が1を超えると例外**
//   （2026-09-13：検算は緑なのに、実機のブラウザだけ「描画で落ちました」）
function checkColor(c){
  if (typeof c !== 'string') throw new TypeError('色が文字列でない: ' + c);
  const m = /^(?:hsla|rgba)\(([^)]*)\)$/.exec(c);
  if (m){
    const parts = m[1].split(',');
    if (parts.length === 4){
      const a = Number(parts[3]);
      if (!isFinite(a) || a < 0 || a > 1) throw new Error('透明度が範囲外: ' + c);
    }
    for (const q of parts) if (/undefined|NaN/.test(q)) throw new Error('色に NaN: ' + c);
  } else if (/undefined|NaN/.test(c)) throw new Error('色に NaN: ' + c);
  return c;
}
  const grad = { addColorStop(_u, c){ checkColor(c); } };
  return new Proxy({}, {
    get(_, k) {
      if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => grad;
      if (typeof k === 'string' && k in calls) return (...a) => { calls[k]++; };
      if (k === 'canvas') return el();
      return () => {};
    },
    set(_, k, v) { if ((k === 'fillStyle' || k === 'strokeStyle')
                     && typeof v === 'string') checkColor(v);
                   return true; },
  });
}
const el = () => ({ getContext: ctx, style: {}, width: 0, height: 0,
                    textContent: '', classList: { add(){}, remove(){}, toggle(){} } });

let frames = 0, raf = null;
const sandbox = {
  // ★裏キャンバスも作れるようにする（3面ディスプレイの遠近で使う）
  document: { getElementById: el, createElement: () => el(), addEventListener(){} },
  addEventListener(){}, innerWidth: 1440, innerHeight: 900, devicePixelRatio: 2,
  performance: { now: () => frames * 16.7 },
  requestAnimationFrame(fn){ raf = fn; },
  // ★状態は本物と同じ経路（WebSocket）で流す。
  //   VM の中の `let S` は外から差し替えられない（最初これで嘘の結果を出した）
  WebSocket: function(){ this.close = ()=>{}; sandbox.__ws = this; },
  location: { host: 'x', protocol: 'http:', search: '', pathname: '/' },
  Math: SEEDED, JSON, console, setTimeout(){}, setInterval(){},
};
sandbox.window = sandbox;
vm.createContext(sandbox);

try {
  vm.runInContext(js, sandbox, { timeout: 5000 });
} catch (e) {
  console.log('★読み込みで落ちた: ' + e.message);
  process.exit(1);
}

// 状態を変えながら数フレーム回す
const states = [
  { bpm:0, n:0, series:'blue', dancing:false, drop:false, talk:null, mode:'off', jog:0, jogw:0 },
  { bpm:124, n:4, series:'blue', dancing:true, drop:false, talk:null, mode:'dj', jog:0, jogw:0 },
  { bpm:124, n:8, series:'red', dancing:true, drop:true, talk:null, mode:'dj', jog:0.7, jogw:1 },
  { bpm:0, n:8, series:'blue', dancing:false, drop:false, talk:'speaking', mode:'dj', jog:0, jogw:0 },
];
const label = ['静か', '踊り', 'こすり', '会話'];
const per = [];
let bad = 0;
states.forEach((s, si) => {
  Object.keys(calls).forEach(k => calls[k] = 0);
  if (sandbox.__ws && sandbox.__ws.onmessage)
    sandbox.__ws.onmessage({ data: JSON.stringify(s) });
  else { console.log('★WebSocket に繋いでいない'); process.exit(1); }
  for (let i = 0; i < 40; i++) {
    frames++;
    try { raf(frames * 16.7); }
    catch (e) { console.log('★描画で落ちた（' + label[si] + '）: ' + e.message); process.exit(1); }
  }
  per.push(label[si] + ': 文字' + calls.fillText + ' 塗り' + calls.fill + ' 線' + calls.stroke);
  if (calls.fillText < 50) { console.log('★' + label[si] + ' で文字を描いていない'); bad++; }
  // ★踊り・こすりでは光が出ていないとおかしい
  if (si >= 1 && si <= 2 && calls.fill < 5) {
    console.log('★' + label[si] + ' で光を描いていない（塗り ' + calls.fill + '）'); bad++;
  }
});
per.forEach(l => console.log('  ' + l));
if (bad) process.exit(1);
console.log('描画OK');
