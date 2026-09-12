// 背景の幾何を確かめる。★目で見るだけでは守れない性質を、機械に見張らせる。
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const js = html.match(/<script>([\s\S]*)<\/script>/)[1];

const grad = { addColorStop(){} };
const ctx = () => new Proxy({}, { get(_,k){
  if (k==='createLinearGradient'||k==='createRadialGradient') return () => grad;
  return () => {};
}, set(){ return true; }});
const el = () => ({ getContext: ctx, style:{}, width:0, height:0, textContent:'',
                    classList:{add(){},remove(){},toggle(){}} });
let raf = null;
const sb = {
  document:{ getElementById: el, createElement: () => el(), addEventListener(){} },
  addEventListener(){}, innerWidth:1600, innerHeight:900, devicePixelRatio:1,
  performance:{now:()=>0}, requestAnimationFrame(f){ raf=f; },
  WebSocket: function(){ this.close=()=>{}; sb.__ws=this; },
  location:{host:'x',protocol:'http:',search:'',pathname:'/'},
  Math, JSON, console, setTimeout(){}, setInterval(){},
};
sb.window = sb; vm.createContext(sb);
vm.runInContext(js, sb, {timeout:5000});
const D = sb.__debug;

let bad = 0;
const ok = (name, cond, extra='') => {
  if (cond) console.log('  ○ ' + name);
  else { console.log('  × ' + name + (extra ? '  ' + extra : '')); bad++; }
};

// ── 遠近の式 ──────────────────────────────
const k = D.CENTER_K;
ok('手前の倍率が 1', Math.abs(D.persp(k,0)-1) < 1e-9);
ok('奥の倍率が k',   Math.abs(D.persp(k,1)-k) < 1e-9, 'k='+k);
ok('途中は単調に縮む', D.persp(k,0.25) > D.persp(k,0.5) && D.persp(k,0.5) > D.persp(k,0.75));
ok('線形ではない（射影）', Math.abs(D.persp(k,0.5) - (1+k)/2) > 1e-3,
   '線形なら ' + ((1+k)/2).toFixed(3) + ' / 実際 ' + D.persp(k,0.5).toFixed(3));
ok('元画像の位置が端で 0 と 1',
   Math.abs(D.tex(k,0)) < 1e-9 && Math.abs(D.tex(k,1)-1) < 1e-9);

// ── パネルの配置 ──────────────────────────
const P = D.PANELS;
ok('パネルは3枚', P.length === 3);
ok('正面がいちばん広い', P[1].w > P[0].w && P[1].w > P[2].w,
   P.map(x=>x.w).join(' / '));
ok('左右が対称', Math.abs(P[0].w - P[2].w) < 1e-9);
ok('継ぎ目に隙間がある（柱の分）',
   P[0].x0 + P[0].w < P[1].x0 && P[1].x0 + P[1].w < P[2].x0);
ok('画面をはみ出さない', P[2].x0 + P[2].w <= 1.0001);
ok('奥ほど暗い', P[0].dim < P[1].dim && P[2].dim < P[1].dim);

// ── 消失点とトラス ────────────────────────
ok('消失点が画面の下寄り（見上げる構図）', D.HORIZON > 0.5 && D.HORIZON < 0.9,
   'HORIZON=' + D.HORIZON);
ok('トラスは壁より手前（縮尺が大きい）', D.TRUSS_NEAR > 1.0, 'x' + D.TRUSS_NEAR);

// ── 灯体 ──────────────────────────────────
const B = D.BEAMS;
ok('灯体は4〜8台（1本のトラスの実際の規模）', B.length >= 2 && B.length <= 8,
   B.length + '台');
ok('灯体は左右対称に並ぶ',
   Math.abs((B[0].cx + B[B.length-1].cx) - 1) < 1e-6);
ok('照明の型が複数ある', D.LOOKS.length >= 5, D.LOOKS.length + '種');
ok('演者を狙う型がある（中央下へ向く）',
   D.LOOKS.some(f => Math.abs(f(B[0], 0, B.length)) > 0.1
                  && Math.sign(f(B[0],0,B.length)) !== Math.sign(f(B[B.length-1],B.length-1,B.length))));

// ── 下からの光 ────────────────────────────
ok('下からの光は2本', D.UPS.length === 2);
ok('下からの光は実機の外側', D.UPS[0].cx < 0.30 && D.UPS[1].cx > 0.70,
   D.UPS.map(u=>u.cx).join(' / '));

console.log(bad ? '\n★ ' + bad + ' 件おかしい' : '\n幾何OK');
process.exit(bad ? 1 : 0);
