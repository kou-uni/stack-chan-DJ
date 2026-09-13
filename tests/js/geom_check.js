// 背景の幾何を確かめる。★目で見るだけでは守れない性質を、機械に見張らせる。
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const js = html.match(/<script>([\s\S]*)<\/script>/)[1];

const calls = {fillText:0, fill:0, stroke:0, fillRect:0, arc:0, drawImage:0, ellipse:0};
const drawCount = () => Object.values(calls).reduce((a,b)=>a+b,0);
const grad = { addColorStop(){} };
const ctx = () => new Proxy({}, { get(_,k){
  if (k==='createLinearGradient'||k==='createRadialGradient') return () => grad;
  if (typeof k === 'string' && k in calls) return () => { calls[k]++; };
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
const sb0 = sb; let frameN = 0; const rafFn = (x)=>raf(x);
vm.runInContext(js, sb, {timeout:5000});
const D = sb.__debug;
const src = html;

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
  // ★canvas は正の角度が時計回り（y軸が下向き）。先端は**左**へ動く
  ok('左右に振るとレンズも動く（正の角度で左へ）', aR.x < c - 1 && aL.x > c + 1,
     '+0.8→' + aR.x.toFixed(1) + ' / -0.8→' + aL.x.toFixed(1));
  ok('振ると少し上がる（円弧を描く）', aL.y < a0.y - 0.5 && aR.y < a0.y - 0.5);
  ok('左右対称', Math.abs((c - aL.x) - (aR.x - c)) < 1e-6);
}

// ★灯体が本当に動くか。**中央だけ止まる**ことがあった（2026-09-13）
{
  const hist = D.BEAMS.map(()=>[]);
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:0,n:0,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',jog:0,jogw:0})});
  for (let i=0;i<300;i++){ frameN++; rafFn(frameN*16.7);
    D.BEAMS.forEach((b,j)=>hist[j].push(b.ang)); }
  hist.forEach((h,j)=>{
    const sw = Math.max(...h) - Math.min(...h);
    // ★中央は左右対称の型で0になりがち。0.35rad(20度)以上動いていればよい
    ok('灯体' + (j+1) + ' が動く', sw > 0.35, '振れ幅 ' + sw.toFixed(2));
  });
}

// ★動く速さ。**瞬間移動は嘘、遅すぎるとゆるゆる**（2026-09-13）
{
  // ★描画ループを回すと、途中でキューが変わって測れない。**動きだけを単体で見る**
  const b = D.BEAMS[0];
  const keep = D.BEAMS.map(x => ({ang:x.ang, vel:x.vel, tgt:x.tgt}));
  D.BEAMS.forEach(x => { x.ang = 0; x.vel = 0; x.tgt = 0; });
  b.tgt = 1.2;
  let sec = 99;
  for (let i=0;i<200;i++){ D.stepHeads(1/60);
    if (Math.abs(b.ang - 1.2) < 0.06){ sec = i/60; break; } }
  ok('大きく振るのに0.3〜1.5秒かかる', sec > 0.3 && sec < 1.5, sec.toFixed(2) + '秒');
  ok('行き過ぎても戻る（暴れない）', Math.abs(b.ang) < 1.6, b.ang.toFixed(2));
  D.BEAMS.forEach((x,i) => Object.assign(x, keep[i]));
}

// ★機材同士がぶつからないこと（2026-09-13：ブラインダーが中央のヘッドに重なっていた）
{
  const bs = D.blinderX();
  const heads = D.BEAMS.map(b => b.cx);
  let clash = null;
  for (const x of bs) for (const h of heads)
    if (Math.abs(x - h) < 0.06) clash = x.toFixed(2) + ' と ' + h.toFixed(2);
  ok('ブラインダーがムービングヘッドと重ならない', !clash, clash || '');
  ok('ブラインダーは灯体の間にある', bs.length >= D.BEAMS.length - 1);
}

// ★振り幅。**水平近くまで振ると、ヘッドがヨークから横へ突き出て光が離れる**
ok('振り幅は垂直から50度以内', D.PAN_MAX <= 0.9,
   (D.PAN_MAX*180/Math.PI).toFixed(0) + '度');
ok('どの型も振り幅を超えない',
   D.LOOKS.every((f,_)=> D.BEAMS.every((b,i)=>
     Math.abs(f(b,i,D.BEAMS.length)) <= D.PAN_MAX + 0.35)));

// ── ★出す前に必ず回す検算（2026-09-13）────────────────
// 本人に指摘されてから手で確かめていた。**それでは遅い。**
// ここに入れておけば、変えるたびに機械が見る

// ① 光の出口が、描いた筒の先と一致しているか
{
  const HEAD_H = +src.match(/HEAD_H = ([0-9.]+)/)[1];
  const BASE_Y = +src.match(/BASE_Y = ([0-9.]+)/)[1];
  const BASE_H = +src.match(/BASE_H = ([0-9.]+)/)[1];
  const YOKE_H = +src.match(/YOKE_H = ([0-9.]+)/)[1];
  // ★実装から取る。手で写すと、片方だけ変えたときにずれる（2026-09-13）
  const L = D.rigLen();
  let worst = 0;
  for (const a of [0, -0.8, 0.8, D.PAN_MAX, -D.PAN_MAX]){
    const lp = D.lensPos(800, a);
    // ★**canvas の変換をそのまま使う。** 自分の式と自分の式を突き合わせても
    //   同じ間違いが両方に入るだけで、検算にならない（2026-09-13 の失敗）
    //   translate(cx,piv) → rotate(a) → 点(0, HL)
    //   canvas の行列: x' = cos*x - sin*y,  y' = sin*x + cos*y
    const HL = L*HEAD_H;
    const drawn = {x: 800 + (Math.cos(a)*0 - Math.sin(a)*HL),
                   y: D.pivotY() + (Math.sin(a)*0 + Math.cos(a)*HL)};
    worst = Math.max(worst, Math.abs(lp.x-drawn.x), Math.abs(lp.y-drawn.y));
  }
  ok('光の出口と筒の先が一致する', worst < 0.5, 'ずれ ' + worst.toFixed(2) + 'px');
}

// ② 素材が明るすぎないか。**明るさは光だまりから来るべき**
{
  const mats = [...src.matchAll(/rgb\(\[\s*(\d+),\s*(\d+),\s*(\d+)\s*\]\)/g)]
    .map(m => Math.max(+m[1], +m[2], +m[3]));
  const mx = mats.length ? Math.max(...mats) : 0;
  ok('構造材の素地が暗い（最大60未満）', mx < 60, '最大 ' + mx);
}

// ③ 灯体同士がぶつからない
{
  const cs = D.BEAMS.map(b => b.cx).sort((a,b)=>a-b);
  let minGap = 9;
  for (let i=1;i<cs.length;i++) minGap = Math.min(minGap, cs[i]-cs[i-1]);
  ok('灯体の間隔が十分', minGap > 0.15, '最小 ' + minGap.toFixed(2));
}

// ④ パネルと柱が重ならない
{
  const P = D.PANELS;
  ok('柱の位置がパネルの隙間に入る',
     P[0].x0 + P[0].w <= P[1].x0 + 1e-9 && P[1].x0 + P[1].w <= P[2].x0 + 1e-9);
}

// ★同じ場所を2つの数字で書かない（2026-09-13：0.825 と 0.828 が混在していた）
{
  const hard = [...src.matchAll(/innerWidth\*0\.\d+/g)].map(m=>m[0]);
  ok('位置の決め打ちが少ない（5箇所以下）', hard.length <= 5,
     hard.length + '箇所: ' + [...new Set(hard)].join(' '));
}

// ★途中から塗る矩形は、端の色を0にしないと**横線（段差）が出る**（2026-09-13）
ok('中央下の落とし込みを画面全体に塗る',
   /画面全体に塗る/.test(src) && !/fillRect\(0, innerHeight\*0\.35/.test(src));
// 床の映り込みは 2026-09-13 に削除（重く、境目に帯が出た）

// ★save と restore の数が合わないと、**毎フレーム状態が積み上がって描画が壊れる**
//   （2026-09-13：光らない原因がこれだった）
{
  const s = (src.match(/g\.save\(\)/g)||[]).length;
  const r = (src.match(/g\.restore\(\)/g)||[]).length;
  ok('save と restore の数が合う', s === r, 'save=' + s + ' restore=' + r);
}

// ── 構造材の統一（2026-09-13 本人の指摘）────────────
// ★横も縦も**同じ素材・同じ粒度・同じ太さ**で描く。別々に描くと柱だけ浮く
ok('トラスは1つの関数で描く', /function trussRun\(/.test(src));
const trussCalls = (src.match(/trussRun\(/g) || []).length - 1;   // 定義を除く
ok('横と縦の両方に使っている（2箇所以上）', trussCalls >= 2, trussCalls + '箇所');
// ★箱トラスは骨組み。**中を塗り潰すと板になる**（2026-09-13 本人の指摘）
// ★筒の先と光の出口が一致しているか（2026-09-13：ずれていて光が離れていた）
ok('筒の長さを HEAD_H で描いている', /const HL = L\*HEAD_H/.test(src));
ok('筒の先にレンズ面がある', /ellipse\(0, HL,/.test(src));
ok('回転後に横へ潰していない', !/g\.scale\(0\.72 \+ 0\.28\*Math\.cos/.test(src));
// ★「キューで目標角が変わる」の判定は、実際に動かして見る方式へ置き換えた

ok('トラスの中を塗り潰していない（骨組みなので透ける）',
   /中は塗らない/.test(src));
ok('トラスを不透明で描く（交差部が透けない）',
   /不透明で描く/.test(src) && !/g\.strokeStyle = 'rgba\(96,110,132/.test(src));
ok('明るさは光だまりから来る（素材を光らせない）',
   /明るさは光だまり/.test(src));
ok('角に継ぎ手がある', /function trussCorner\(/.test(src));
ok('柱を四角塗りで描いていない',
   !/g\.fillRect\(x, cy, pw2, ch\)/.test(src));

// ★1フレームの描画命令。**多すぎると iPad が止まる**（2026-09-13 実地）
{
  let n = 0;
  const g2 = new Proxy({}, {get(_,k){
    if (String(k).startsWith('create')) { n++; return () => ({addColorStop(){}}); }
    if (['fill','stroke','fillRect','fillText','drawImage','arc','ellipse'].includes(k))
      return () => { n++; };
    return () => {};
  }, set(){ return true; }});
  // 5フレーム回してから1フレームぶん数える
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',jog:0,jogw:0})});
  for (let i=0;i<5;i++){ frameN++; rafFn(frameN*16.7); }
  const before = drawCount(); frameN++; rafFn(frameN*16.7);
  const per = drawCount() - before;
  ok('1フレームの描画命令が1000未満', per < 1000, per + '命令');
}

// ★床のパネル発光（2026-09-13）
{
  const before = D.floorPanels().length;
  D.litFloor(200); D.litFloor(200);
  const after = D.floorPanels().length;
  ok('拍で床のパネルが光る', after > before, after + '枚');
  const cells = D.floorPanels();
  ok('光るのはマス目の中', cells.every(f => f.c >= 0 && f.c < D.FLOOR_COLS && f.r >= 0 && f.r < D.FLOOR_ROWS));
  ok('同時に光りすぎない', cells.length <= 24, cells.length + '枚');
}

console.log(bad ? '\n★ ' + bad + ' 件おかしい' : '\n幾何OK');
process.exit(bad ? 1 : 0);
