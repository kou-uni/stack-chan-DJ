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

// ── 灯体の動き（2026-09-13 本人の指摘）──────────────
// ★ヘッドはビームと同じ向きに回る。**レンズもそれについて動く。**
//   横に潰して固定すると、最初の姿勢のまま止まって見える
{
  const c = 800;
  const a0 = D.lensPos(c, 0), aL = D.lensPos(c, -0.8), aR = D.lensPos(c, 0.8);
  ok('真下では支点の真下にレンズが来る', Math.abs(a0.x - c) < 1e-6);
  ok('左右に振るとレンズも動く', aL.x < c - 1 && aR.x > c + 1,
     'L=' + aL.x.toFixed(1) + ' R=' + aR.x.toFixed(1));
  ok('振ると少し上がる（円弧を描く）', aL.y < a0.y - 0.5 && aR.y < a0.y - 0.5);
  ok('左右対称', Math.abs((c - aL.x) - (aR.x - c)) < 1e-6);
}

// ── 構造材の統一（2026-09-13 本人の指摘）────────────
// ★横も縦も**同じ素材・同じ粒度・同じ太さ**で描く。別々に描くと柱だけ浮く
const src = fs.readFileSync(process.argv[2], 'utf8');
ok('トラスは1つの関数で描く', /function trussRun\(/.test(src));
const calls = (src.match(/trussRun\(/g) || []).length - 1;   // 定義を除く
ok('横と縦の両方に使っている（3箇所以上）', calls >= 3, calls + '箇所');
// ★箱トラスは骨組み。**中を塗り潰すと板になる**（2026-09-13 本人の指摘）
// ★筒の先と光の出口が一致しているか（2026-09-13：ずれていて光が離れていた）
ok('筒の長さを HEAD_H で描いている', /const HL = L\*HEAD_H/.test(src));
ok('筒の先にレンズ面がある', /ellipse\(0, HL,/.test(src));
ok('回転後に横へ潰していない', !/g\.scale\(0\.72 \+ 0\.28\*Math\.cos/.test(src));
{
  // 灯体が実際に動くか（キューが変われば角度が変わる）
  const b = D.BEAMS[0];
  const before = b.ang;
  D.BEAMS.forEach((x,i)=> x.tgt = D.LOOKS[3](x, i, D.BEAMS.length));
  for (let i=0;i<40;i++){ /* stepHeads は draw の中。ここでは目標が変わることだけ見る */ }
  ok('キューで目標角が変わる', Math.abs(b.tgt - before) > 0.05,
     'tgt=' + b.tgt.toFixed(2) + ' ang=' + before.toFixed(2));
}

ok('トラスの中を塗り潰していない（骨組みなので透ける）',
   /中は塗らない/.test(src));
ok('トラスを不透明で描く（交差部が透けない）',
   /不透明で描く/.test(src) && !/g\.strokeStyle = 'rgba\(96,110,132/.test(src));
ok('明るさは光だまりから来る（素材を光らせない）',
   /明るさは光だまり/.test(src));
ok('角に継ぎ手がある', /function trussCorner\(/.test(src));
ok('柱を四角塗りで描いていない',
   !/g\.fillRect\(x, cy, pw2, ch\)/.test(src));

console.log(bad ? '\n★ ' + bad + ' 件おかしい' : '\n幾何OK');
process.exit(bad ? 1 : 0);
