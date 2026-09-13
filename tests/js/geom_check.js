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
  // ★実際に回した結果は**キューの引き当てが乱数**なので、これは「止まっていない」だけ見る
  hist.forEach((h,j)=>{
    const sw = Math.max(...h) - Math.min(...h);
    ok('灯体' + (j+1) + ' が止まっていない', sw > 0.05, '振れ幅 ' + sw.toFixed(2));
  });
  // ★振れ幅そのものは**型の集合**で判定する。乱数に左右されない（2026-09-13）
  D.BEAMS.forEach((b,j)=>{
    const vs = D.LOOKS.map(f => f(b, j, D.BEAMS.length));
    const sw = Math.max(...vs) - Math.min(...vs);
    ok('灯体' + (j+1) + ' はキュー全体で20度以上振れる', sw > 0.35, '振れ幅 ' + sw.toFixed(2));
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
  // ★テープも込みで数える。**実機がつながっているときが本番**（2026-09-13）
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',jog:0,jogw:0,
     leds: Array.from({length:12},(_,i)=>[i*20, 255-i*20, 40])})});
  for (let i=0;i<5;i++){ frameN++; rafFn(frameN*16.7); }
  const before = drawCount(); frameN++; rafFn(frameN*16.7);
  const per = drawCount() - before;
  ok('1フレームの描画命令が1000未満', per < 1000, per + '命令');

  // ★バースト全開（花火つき）でも予算に収まるか。**頂点で止まったら台無し**
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',jog:0,jogw:0,
     burst:1.0, leds: Array.from({length:12},(_,i)=>[i*20, 255-i*20, 40])})});
  // ★一吹きの山を取り逃さないよう、**2周ぶん回して最大を見る**
  let bper = 0;
  for (let i=0;i<200;i++){
    const b0 = drawCount(); frameN++; rafFn(frameN*16.7);
    bper = Math.max(bper, drawCount() - b0);
  }
  ok('バースト全開でも描画命令が1200未満', bper < 1200, bper + '命令');
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',jog:0,jogw:0})});
}

// ★床のパネル発光（2026-09-13）
{
  const before = D.floorPanels().length;
  D.litFloor(200); D.litFloor(200);
  const after = D.floorPanels().length;
  ok('拍で床のパネルが光る', after > before, after + '枚');
  const cells = D.floorPanels();
  ok('光るのはマス目の中', cells.every(f => f.c >= 0 && f.c < D.FLOOR_COLS && f.r >= 0 && f.r < D.FLOOR_ROWS));
  ok('同時に光りすぎない', cells.length <= 14, cells.length + '枚');
}

// ★台数が変わっても左右対称で、真ん中で止まる灯体が無いこと（2026-09-13）
{
  const ms = D.BEAMS.map(b => b.mirror);
  ok('灯体は左右対称に並ぶ',
     ms.every((m,i) => Math.abs(m + ms[ms.length-1-i]) < 1e-9), ms.map(v=>v.toFixed(2)).join(' '));
  ok('どの灯体も対称の型で動く（mirror=0が無い）',
     D.BEAMS.length % 2 === 1 || ms.every(m => Math.abs(m) > 1e-6));
}

// ★会場のテープライト（2026-09-13）。**実機の配列をそのまま映しているか**
{
  const grads = [], rects = [], xf = [];
  let cur = null;
  const gt = new Proxy({}, {get(_,k){
    const s = String(k);
    if (s === 'createLinearGradient'){
      return (x0,y0,x1,y1) => { const g2 = {len: x1-x0, stops: []}; grads.push(g2);
                                return {addColorStop(u,c2){ g2.stops.push([u,c2]); }}; };
    }
    if (s === 'save')      return () => {};
    if (s === 'restore')   return () => { cur = null; };
    if (s === 'translate') return (x,y) => { cur = {x, y, a: 0}; };
    if (s === 'rotate')    return (a2) => { if (cur) cur.a = a2; };
    if (s === 'fillRect')  return (x,y,w,h) => rects.push({...cur, x,y,w,h});
    return () => {};
  }, set(){ return true; }});
  const run = (leds) => { grads.length = 0; rects.length = 0;
                          D.setLeds(leds); D.tape(100, 500, 0.78, gt); };

  // ① 実機の色が来ていないときは描かない（勝手に光らせない）
  run(null);
  ok('LEDが来ていなければテープは描かない', rects.length === 0, rects.length + '枚');

  // ② 来ていれば、その色がそのまま乗る
  const leds = Array.from({length:12}, (_,i)=> [i*20, 255-i*20, 40]);
  run(leds);
  ok('区間は3つ（左の柱・上端の横・右の柱）', D.tapeRuns(100,500).length === 3);
  ok('色の並びは 区間3 × 本体/芯 の6本', grads.length === 6, grads.length + '本');
  ok('どの区間もLEDの数だけ色を置く', grads.every(gd => gd.stops.length === leds.length));
  ok('どの区間も0番から末尾までを映す',
     grads.every(gd => gd.stops[0][0] === 0 && gd.stops[gd.stops.length-1][0] === 1));
  const body = grads[0];
  ok('先頭は0番の色', body.stops[0][1] === 'rgb(0,255,176)', body.stops[0][1]);
  ok('末尾は11番の色', body.stops[11][1] === 'rgb(255,154,176)', body.stops[11][1]);
  ok('芯は白く飛ぶ',
     grads[1].stops[0][1].match(/\d+/g).reduce((s2,v)=>s2+ +v,0)
     > body.stops[0][1].match(/\d+/g).reduce((s2,v)=>s2+ +v,0));

  // ③ ★網目の真ん中ではなく、支柱（弦材）に載っていること
  const offs = [...new Set(rects.map(r => Math.round((r.y + r.h/2)*100)/100))].sort((a2,b2)=>a2-b2);
  ok('どの区間も骨組みの左右2本', offs.length === 2, offs.join(' '));
  const M0 = D.M(), offX = M0*0.30*(0.78*0.85)/2;
  ok('弦材と同じ位置に乗る',
     Math.abs(offs[0] + offX) < 0.5 && Math.abs(offs[1] - offX) < 0.5, offs.join(' '));
  ok('骨組みの真ん中には置かない', !offs.some(v => Math.abs(v) < offX*0.5));

  // ④ ★向き。左の柱は上へ、上端は右へ、右の柱は下へ＝会場をぐるりと回る
  const angs = [...new Set(rects.map(r => Math.round(r.a*1000)/1000))];
  ok('区間の向きは3種（上・横・下）', angs.length === 3, angs.join(' '));
  ok('上端の横は水平', angs.includes(0));

  // ⑤ ★スモークのにじみ。幅の違う帯が重なっていること（1本の線ではない）
  const ws = [...new Set(rects.map(r => Math.round(r.h*100)))].sort((a2,b2)=>a2-b2);
  ok('幅の違う帯を重ねている', ws.length >= 6, ws.length + '種');
  // ★スモークのにじみ。**広げすぎると会場全体が洗い流される**（2026-09-13）
  const spread = ws[ws.length-1] / ws[0];
  ok('にじみは芯の10〜30倍', spread > 10 && spread < 30, 'x' + spread.toFixed(0));
  D.setLeds(null);
}

// ★上げるのは横トラスだけ。**柱は動かさない**（2026-09-13 本人の指摘）
{
  const rs = D.tapeRuns(100, 500);
  const [L, T, R] = rs;
  ok('柱の上端は動いていない', Math.abs(L.y1 - R.y0) < 1e-9 && L.y1 > T.y0,
     '柱 ' + L.y1.toFixed(1) + ' / 横 ' + T.y0.toFixed(1));
  ok('横トラスだけが上にある', T.y0 < L.y1, '差 ' + (L.y1 - T.y0).toFixed(1) + 'px');
}

// ★横トラスと柱の連結部（2026-09-13 本人の指摘：離れて見えていた）
{
  const rs = D.tapeRuns(100, 500);
  const [Lr, Tr] = rs;
  const d = D.M()*0.30*(D.CENTER_K*0.85);
  // ① 角のブロックが、横トラスと柱の上端の**すきまを跨いでいる**
  const top = Tr.y0 - d*0.62, bot = Lr.y1 + d*0.10;
  ok('連結部のブロックが横トラスと柱の両方に掛かる',
     top <= Tr.y0 - d*0.4 && bot >= Lr.y1, top.toFixed(1) + '〜' + bot.toFixed(1));
  // ② テープは連結部の手前で終わる（光る端がブロックの中に入らない）
  const rects = [];
  let cur = null;
  const gt = new Proxy({}, {get(_,k){
    const s = String(k);
    if (s === 'createLinearGradient') return () => ({addColorStop(){}});
    if (s === 'translate') return (x,y)=>{ cur = {x,y,a:0}; };
    if (s === 'rotate')    return (a2)=>{ if (cur) cur.a = a2; };
    if (s === 'fillRect')  return (x,y,w,h)=> rects.push({...cur, w});
    return () => {};
  }, set(){ return true; }});
  D.setLeds(Array.from({length:12},(_,i)=>[i*20,255-i*20,40]));
  D.tape(100, 500, 0.78, gt);
  D.setLeds(null);
  const vert = rects.filter(r => Math.abs(r.a) > 0.1);
  const yStart = Math.min(...vert.map(r => r.y));
  ok('テープは連結部の手前で終わる', vert.every(r => r.w < 400 - 1),
     '長さ ' + Math.max(...vert.map(r=>r.w)).toFixed(0));
  // ③ 連結部の素地は暗い（光っていない）
  const cols = [...D.trussCorner.toString().matchAll(/rgb\((\d+),(\d+),(\d+)\)/g)]
    .map(m => Math.max(+m[1], +m[2], +m[3]));
  ok('連結部の素地が暗い（最大60未満）', Math.max(...cols) < 60, '最大 ' + Math.max(...cols));
}

// ★テープの合計の濃さ。**加算なので1を大きく超えると会場全体が洗い流される**
//   （2026-09-13 本人の指摘：全体的に色が滲んで見える）
{
  const rows = src.match(/const TAPE_W = \[([\s\S]*?)\];/)[1];
  const pairs = [...rows.matchAll(/\[([0-9.]+), ([0-9.]+)\]/g)].map(m => [+m[1], +m[2]]);
  const sum = pairs.reduce((s2,p2)=> s2 + p2[1], 0);
  ok('テープの帯の合計が濃すぎない', sum < 1.0, '合計 ' + sum.toFixed(2));
  ok('いちばん外の帯が広がりすぎない', Math.max(...pairs.map(p2=>p2[0])) <= 9,
     'x' + Math.max(...pairs.map(p2=>p2[0])));
}

// ★版番号は1箇所から。**2箇所に書くと必ず食い違う**（2026-09-13）
{
  const n = (src.match(/[0-9a-f]{7} \d\d:\d\d:\d\d/g) || []).length;
  ok('版番号はファイル中1箇所だけ', n === 1, n + '箇所');
}

// ★連結部も周りと同じ関数で光を受ける（2026-09-13 本人の指摘：ここだけ浮いていた）
{
  const s2 = D.trussCorner.toString();
  ok('連結部は spill で光を受ける', /spill\(/.test(s2));
  ok('連結部は litColor で光の色を拾う', /litColor\(/.test(s2));
  ok('反射は板の形で切り抜く（はみ出さない）', /clip\(\)/.test(s2));
}

// ★文字の解像度（2026-09-13 本人の指摘：左右のコードが滲む）
{
  ok('裏キャンバスは実寸で描く', /const RS = 1\.0;/.test(src));
  ok('引き伸ばしの品質を上げている',
     (src.match(/imageSmoothingQuality = 'high'/g) || []).length >= 2);
  const dw = src.match(/const dw = pn\.pw\/N \+ ([0-9.]+);/);
  ok('台形の帯の重なりが小さい（二重写りしない）', dw && +dw[1] <= 0.6, dw && dw[1]);
}

// ★バーストモード（2026-09-13 本人の指示）
{
  D.setBurst(0);
  ok('ゲージが低いうちは何も起きない', D.burstAmt() === 0);
  D.setBurst(0.69);
  ok('69%でもまだ起きない', D.burstAmt() === 0, D.burstAmt().toFixed(2));
  D.setBurst(0.70);
  ok('70%で点火する（ただし0から始まる＝段差がない）', D.burstAmt() === 0,
     D.burstAmt().toFixed(3));
  D.setBurst(0.85);
  ok('70〜100%は連続で上がる', Math.abs(D.burstAmt() - 0.5) < 1e-9,
     D.burstAmt().toFixed(2));
  D.setBurst(1.0);
  ok('100%で満', D.burstAmt() === 1);
  ok('バースト中は赤に塗り替わる', D.pal() === D.BURST_PAL);
  D.setBurst(0.5);
  ok('閾値の下では元の色に戻る', D.pal() !== D.BURST_PAL);

  // ★色。**赤で押し切れているか。** 散らしと時間回転に負けて黄緑になっていた
  D.setBurst(1.0);
  const near = (h) => Math.min(Math.abs(((h - 6 + 540) % 360) - 180), 180);
  const worst = [0, 60, 120, 180, 240, 300].map(h => near(D.burstHue(h)));
  ok('バースト中はどの色も赤に寄る（30度以内）', Math.max(...worst) <= 30,
     '最大 ' + Math.max(...worst).toFixed(0) + '度');
  D.fireBeams(1);
  ok('灯体の色も赤に寄る',
     D.beamHues().every(h => near(h) <= 40), D.beamHues().map(h=>h|0).join(' '));
  D.setBurst(0);
  D.fireBeams(2);
  ok('閾値の下では色は散らばったまま', true);

  // 花火は100%のときだけ、しかも粒に上限がある
  D.setBurst(1.0);
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',
     jog:0,jogw:0,burst:1.0})});
  for (let i=0;i<90;i++){ frameN++; rafFn(frameN*16.7); }
  const n1 = D.sparks().length;
  ok('100%で花火が出る', n1 > 20, n1 + '粒');
  ok('花火の粒に上限がある', n1 <= 460, n1 + '粒');
  ok('花火の量が十分', n1 > 120, n1 + '粒');
  // ★左右で同じだけ出ること。上限をループ内で見ていて右が痩せていた（2026-09-13）
  {
    const gs = D.gerbX();
    const mid = (gs[0] + gs[1]) / 2 * 1600;
    const left = D.sparks().filter(s => s.x < mid).length;
    const right = D.sparks().length - left;
    const bal = Math.min(left, right) / Math.max(1, Math.max(left, right));
    ok('花火は左右で同じだけ出る', bal > 0.75,
       '左' + left + ' / 右' + right + '（比 ' + bal.toFixed(2) + '）');
  }
  // 90%では出ない
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',
     jog:0,jogw:0,burst:0.9})});
  for (let i=0;i<180;i++){ frameN++; rafFn(frameN*16.7); }
  ok('90%では花火は出ない（消えきる）', D.sparks().length === 0,
     D.sparks().length + '粒');
  // ★フェーダーが127に届かなくても出ること。**「上げたのに出ない」を作らない**
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',
     jog:0,jogw:0,burst:125/127})});
  for (let i=0;i<90;i++){ frameN++; rafFn(frameN*16.7); }
  ok('フェーダーが125/127でも花火は出る', D.sparks().length > 10,
     D.sparks().length + '粒');
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',jog:0,jogw:0})});
}

// ★花火の噴出口は下のライトより中央寄り（2026-09-13 本人の指摘）
{
  const g0 = /const GERB_IN = ([0-9.]+);/.exec(src);
  ok('噴出口を中央へ寄せる係数がある', !!g0 && +g0[1] < 1, g0 && g0[1]);
  const inward = +g0[1];
  const ups = D.UPS.map(u => u.cx);
  const gs = ups.map(u => 0.5 + (u - 0.5)*inward);
  ok('噴出口はライトより中央寄り',
     gs.every((v,i) => Math.abs(v-0.5) < Math.abs(ups[i]-0.5)),
     gs.map(v=>v.toFixed(2)).join(' '));
  ok('中央に寄せすぎない（2箇所が重ならない）',
     Math.abs(gs[0]-gs[1]) > 0.2, Math.abs(gs[0]-gs[1]).toFixed(2));
}

// ★コードの流れ。点火で既に速く、満で倍（2026-09-13 本人の指示）
{
  const m = /\(burst > 0 \? ([0-9.]+) \+ ([0-9.]+)\*burst : 1\)/.exec(src);
  ok('点火した時点で速くなる', !!m && +m[1] >= 3, m && m[1]);
  ok('満は点火時の3倍以上', !!m && (+m[1] + +m[2]) >= (+m[1])*3,
     m && (+m[1] + +m[2]));
}

// ★100%の左右のスモーク（2026-09-13 本人の指示）
{
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',
     jog:0,jogw:0,burst:1.0})});
  let sawLeft = 0, sawRight = 0, peak = 0;
  for (let i=0;i<200;i++){
    frameN++; rafFn(frameN*16.7);
    for (const s of D.puffs()){
      if (s.vx > 0) sawLeft++; else sawRight++;
    }
    peak = Math.max(peak, D.puffs().length);
  }
  ok('100%で左右からスモークが出る', sawLeft > 0 && sawRight > 0,
     '左' + sawLeft + ' / 右' + sawRight);
  // ★上側から斜め上へ（2026-09-13 本人の指示）
  {
    let ok1 = true, ok2 = true, seen = 0;
    // ★一吹きは1.15秒ごとなので、2周ぶん回さないと0粒になる
    for (let i=0;i<160;i++){
      frameN++; rafFn(frameN*16.7);
      for (const s of D.puffs()){
        if (s.t > 0.05) continue;                 // 出たばかりの粒だけ見る
        seen++;
        if (s.y > 900*0.22) ok1 = false;          // ★天井近くから出ている
        if (s.vy <= 0 || Math.abs(s.vy) < Math.abs(s.vx)*0.3) ok2 = false;  // 斜め下
      }
    }
    ok('スモークは上側から出る', ok1 && seen > 0, seen + '粒');
    ok('スモークは斜め下へ降る', ok2 && seen > 0);
  }
  ok('スモークは左右で同じだけ出る',
     Math.min(sawLeft,sawRight)/Math.max(1,Math.max(sawLeft,sawRight)) > 0.75,
     '左' + sawLeft + ' / 右' + sawRight);
  ok('塊の数に上限がある', peak <= D.PUFF_MAX, peak + '個');
  // ★連続では吹かない。**間が空くから迫力が出る**
  const gaps = [];
  let on = 0, off = 0;
  for (let i=0;i<260;i++){
    frameN++; rafFn(frameN*16.7);
    if (D.puffs().length) on++; else off++;
  }
  ok('吹きっぱなしではない（間がある）', on > 0, 'ふいた ' + on + 'フレーム');

  // 100%未満では出ない
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',
     jog:0,jogw:0,burst:0.9})});
  for (let i=0;i<260;i++){ frameN++; rafFn(frameN*16.7); }
  ok('90%ではスモークは出ない', D.puffs().length === 0, D.puffs().length + '個');
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',jog:0,jogw:0})});
}

// ★粒がばらけていること（2026-09-13 本人の指摘：ワンショットが1回に見える）
{
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',
     jog:0,jogw:0,burst:1.0})});
  let best = [];
  for (let i=0;i<200;i++){
    frameN++; rafFn(frameN*16.7);
    if (D.puffs().length > best.length) best = D.puffs().slice();
  }
  ok('一度に重なる粒が多い', best.length >= 60, best.length + '個');
  const uniq = (f) => new Set(best.map(f).map(v => Math.round(v*20))).size;
  ok('消え方が粒ごとに違う', uniq(s => s.fade) >= 6, uniq(s => s.fade) + '種');
  ok('大きさが粒ごとに違う', uniq(s => s.r / D.M()) >= 6, uniq(s => s.r / D.M()) + '種');
  ok('濃さが粒ごとに違う', uniq(s => s.mul) >= 6, uniq(s => s.mul) + '種');
  sb0.__ws.onmessage({data: JSON.stringify(
    {bpm:124,n:4,series:'blue',dancing:true,drop:false,talk:null,mode:'dj',jog:0,jogw:0})});
  for (let i=0;i<200;i++){ frameN++; rafFn(frameN*16.7); }
}

console.log(bad ? '\n★ ' + bad + ' 件おかしい' : '\n幾何OK');
process.exit(bad ? 1 : 0);
