#!/usr/bin/env python3
"""Local gallery browser for selfit content_v2 assets.

Usage:
    python3 scripts/serve_asset_gallery.py [--port 8899] [--no-browser]

Serves:
    /               gallery page
    /api/manifest   asset manifest JSON (built at startup)
    /img/<rel>      image file under content_v2
    /qa/<rel>       sidecar .qa.json for an image
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1] / "app" / "static" / "selfit" / "assets" / "content_v2"
IMG_MIME = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _safe_resolve(rel: str) -> Path | None:
    try:
        p = (ROOT / rel).resolve()
        p.relative_to(ROOT.resolve())
        return p
    except (ValueError, OSError):
        return None


def _read_qa(img: Path) -> dict | None:
    qa = img.parent / (img.stem + ".qa.json")
    if not qa.exists():
        return None
    try:
        return json.loads(qa.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_manifest() -> dict:
    personas = sorted(d.name for d in ROOT.iterdir() if d.is_dir() and d.name != "layouts")
    garments, outfits, layouts = [], [], []

    for p in personas:
        gdir = ROOT / p / "garments"
        if gdir.is_dir():
            for f in sorted(gdir.iterdir()):
                if f.suffix.lower() not in IMG_MIME:
                    continue
                parts = f.stem.split("-")
                cat = parts[1] if len(parts) >= 3 and p == parts[0] else "other"
                garments.append({"n": f.stem, "p": f"{p}/garments/{f.name}", "e": p, "cat": cat})
        odir = ROOT / p / "outfits"
        if odir.is_dir():
            for f in sorted(odir.iterdir()):
                if f.suffix.lower() not in IMG_MIME:
                    continue
                parts = f.stem.split("_")
                master = parts[3] if len(parts) > 3 else ""
                ver = parts[4] if len(parts) > 4 else "base"
                outfits.append({"n": f.stem, "p": f"{p}/outfits/{f.name}", "e": p, "m": master, "v": ver})

    ldir = ROOT / "layouts"
    if ldir.is_dir():
        for layout in sorted(d for d in ldir.iterdir() if d.is_dir()):
            for f in sorted(layout.iterdir()):
                if f.suffix.lower() not in IMG_MIME:
                    continue
                entry = {"n": f.stem, "p": f"layouts/{layout.name}/{f.name}", "layout": layout.name,
                         "e": [], "slots": [], "count": 0}
                qa = _read_qa(f)
                if qa:
                    pl = qa.get("placements", [])
                    entry["count"] = len(pl)
                    entry["slots"] = [str(x.get("slot", "")) for x in pl]
                    ps = set()
                    for x in pl:
                        gp = str(x.get("garment_id", "")).split("_")
                        if len(gp) >= 2 and gp[0] == "garment":
                            ps.add(gp[1])
                    entry["e"] = sorted(ps)
                layouts.append(entry)

    manifest = {
        "personas": personas,
        "garments": garments,
        "outfits": outfits,
        "layouts": layouts,
    }
    print(f"[manifest] personas={len(personas)} garments={len(garments)} "
          f"outfits={len(outfits)} layouts={len(layouts)}", file=sys.stderr)
    return manifest


PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Selfit content_v2 素材浏览</title>
<style>
  :root{
    --bg:#faf9f8; --card:#ffffff; --ink:#2a2530; --ink2:#8a8494;
    --rose:#ff4f86; --rose-soft:#fff0f5; --line:#ece8ec;
    --shadow:0 4px 18px rgba(120,90,110,.08);
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif;
       background:var(--bg);color:var(--ink)}
  header{position:sticky;top:0;z-index:20;background:rgba(250,249,248,.92);backdrop-filter:blur(10px);
         border-bottom:1px solid var(--line);padding:14px 20px 10px}
  h1{font-size:17px;margin:0 0 10px;display:flex;align-items:baseline;gap:10px}
  h1 small{color:var(--ink2);font-weight:400;font-size:12px}
  .tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
  .tab{border:1px solid var(--line);background:var(--card);border-radius:999px;padding:6px 14px;
       font-size:13px;font-weight:600;cursor:pointer;color:var(--ink)}
  .tab.on{background:var(--rose);border-color:var(--rose);color:#fff}
  .tab .cnt{opacity:.65;font-weight:400;font-size:11px;margin-left:4px}
  .bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .chips{display:flex;gap:6px;flex-wrap:wrap;flex:1;min-width:200px}
  .chip{border:1px solid var(--line);background:var(--card);border-radius:999px;padding:3px 11px;
        font-size:12px;cursor:pointer;color:var(--ink)}
  .chip.on{background:var(--rose-soft);border-color:var(--rose);color:var(--rose);font-weight:600}
  .chip.g{border-radius:8px}
  input[type=search]{border:1px solid var(--line);border-radius:999px;padding:6px 14px;font-size:13px;
        width:180px;outline:none;background:var(--card)}
  input[type=search]:focus{border-color:var(--rose)}
  #meta{font-size:12px;color:var(--ink2);padding:12px 20px 0}
  main{padding:12px 20px 60px}
  #grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:14px}
  .cell{background:var(--card);border-radius:16px;box-shadow:var(--shadow);overflow:hidden;cursor:zoom-in;
        display:flex;flex-direction:column}
  .cell .img{background:
      repeating-conic-gradient(#f2eef2 0 25%,#faf7fa 0 50%) 0 0/16px 16px}
  .cell img{display:block;width:100%;height:100%;object-fit:contain}
  .cell.r1 .img{aspect-ratio:1/1}
  .cell.r45 .img{aspect-ratio:4/5}
  .cap{padding:7px 10px 8px;font-size:11px;color:var(--ink2);display:flex;justify-content:space-between;
       gap:6px;border-top:1px solid var(--line)}
  .cap b{color:var(--ink);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .tag{background:var(--rose-soft);color:var(--rose);border-radius:6px;padding:1px 6px;font-weight:600;
       white-space:nowrap;font-size:10px}
  #sentinel{height:10px}
  #lb{position:fixed;inset:0;background:rgba(30,24,28,.82);z-index:50;display:none;
      align-items:center;justify-content:center;padding:24px}
  #lb.on{display:flex}
  #lb .box{background:var(--card);border-radius:20px;max-width:min(96vw,900px);max-height:92vh;
           display:flex;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.35)}
  #lb .pic{background:repeating-conic-gradient(#f2eef2 0 25%,#faf7fa 0 50%) 0 0/20px 20px;
           display:flex;align-items:center;justify-content:center;flex:1;min-width:0}
  #lb img{max-width:100%;max-height:88vh;display:block}
  #lb aside{width:300px;max-width:38vw;padding:16px;overflow:auto;font-size:12px;color:var(--ink2)}
  #lb aside h3{margin:0 0 4px;font-size:13px;color:var(--ink);word-break:break-all}
  #lb aside pre{background:#f6f3f6;border-radius:10px;padding:10px;white-space:pre-wrap;
                word-break:break-all;font-size:11px;max-height:50vh;overflow:auto}
  #lb .close{position:absolute;top:14px;right:18px;font-size:26px;color:#fff;cursor:pointer;
             background:none;border:none;line-height:1}
  .empty{padding:60px;text-align:center;color:var(--ink2)}
</style>
</head>
<body>
<header>
  <h1>Selfit content_v2 素材浏览 <small id="rootnote"></small></h1>
  <div class="tabs" id="tabs"></div>
  <div class="bar">
    <div class="chips" id="personaChips"></div>
    <div class="chips" id="subChips"></div>
    <input type="search" id="q" placeholder="搜索文件名 / 单品…">
  </div>
</header>
<div id="meta"></div>
<main><div id="grid"></div><div id="sentinel"></div><div class="empty" id="empty" style="display:none">没有匹配的图片</div></main>

<div id="lb">
  <button class="close" onclick="closeLb()">×</button>
  <div class="box">
    <div class="pic"><img id="lbImg" alt=""></div>
    <aside>
      <h3 id="lbName"></h3>
      <div id="lbInfo" style="margin-bottom:10px"></div>
      <div style="font-weight:600;color:var(--ink);margin-bottom:6px">QA 元数据</div>
      <pre id="lbQa">加载中…</pre>
    </aside>
  </div>
</div>

<script>
const S = {tab:null, persona:'', sub:'', q:'', items:[], shown:0};
const BATCH = 60;
let M = null;

const el = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function tabDefs(){
  return [
    {id:'garments', label:'单品图', count:M.garments.length, ratio:'r1'},
    {id:'outfits', label:'穿搭图', count:M.outfits.length, ratio:'r45'},
    ...[...new Set(M.layouts.map(x=>x.layout))].map(l=>({
      id:'layout:'+l, label:l, count:M.layouts.filter(x=>x.layout===l).length,
      ratio:l.includes('flatlay')?'r45':'r45'})),
  ];
}

function chipRow(rowId, opts, cur, onpick){
  const row = el(rowId); row.innerHTML='';
  opts.forEach(([val,label,count])=>{
    const b = document.createElement('button');
    b.className = 'chip' + (val===cur?' on':'');
    b.textContent = label + (count!=null?` (${count})`:'');
    b.onclick = ()=>onpick(val);
    row.appendChild(b);
  });
}

function renderTabs(){
  const tabs = el('tabs'); tabs.innerHTML='';
  tabDefs().forEach(t=>{
    const b=document.createElement('button');
    b.className='tab'+(S.tab===t.id?' on':'');
    b.innerHTML = esc(t.label)+`<span class="cnt">${t.count}</span>`;
    b.onclick=()=>{S.tab=t.id;S.sub='';S.shown=0;render();};
    tabs.appendChild(b);
  });
}

function currentList(){
  let list;
  if(S.tab==='garments') list=M.garments;
  else if(S.tab==='outfits') list=M.outfits;
  else list=M.layouts.filter(x=>x.layout===S.tab.slice(7));
  if(S.persona){
    list=list.filter(x=> S.tab.startsWith('layout:') ? x.e.includes(S.persona) : x.e===S.persona);
  }
  if(S.sub){
    if(S.tab==='garments') list=list.filter(x=>x.cat===S.sub);
    else if(S.tab==='outfits') list=list.filter(x=>x.v===S.sub);
    else list=list.filter(x=>String(x.count)===S.sub);
  }
  if(S.q){
    const q=S.q.toLowerCase();
    list=list.filter(x=>(x.n+' '+((x.slots||[]).join(' '))+' '+((x.e instanceof Array)?x.e.join(' '):x.e)).toLowerCase().includes(q));
  }
  return list;
}

function render(){
  renderTabs();
  // persona chips
  chipRow('personaChips', [['','全部人格'],...M.personas.map(p=>{
    const c=S.tab.startsWith('layout:') ? M.layouts.filter(x=>x.layout===S.tab.slice(7)&&x.e.includes(p)).length
      : (S.tab==='outfits'?M.outfits:M.garments).filter(x=>x.e===p).length;
    return [p,p,c];
  })], S.persona, v=>{S.persona=v;S.shown=0;render();});
  // sub chips
  let subs=[];
  if(S.tab==='garments'){
    const cats={};
    M.garments.forEach(x=>{if(!S.persona||x.e===S.persona)cats[x.cat]=(cats[x.cat]||0)+1;});
    subs=[...Object.entries(cats)].sort().map(([c,n])=>[c,c,n]);
  }else if(S.tab==='outfits'){
    const vs={};
    M.outfits.forEach(x=>{if(!S.persona||x.e===S.persona)vs[x.v]=(vs[x.v]||0)+1;});
    subs=[...Object.entries(vs)].sort().map(([v,n])=>[v,v==='base'?'原版':v,n]);
  }else{
    const cs={};
    M.layouts.filter(x=>x.layout===S.tab.slice(7)).forEach(x=>{
      if(S.persona&&!x.e.includes(S.persona))return;
      cs[x.count]=(cs[x.count]||0)+1;});
    subs=[...Object.entries(cs)].sort((a,b)=>a[0]-b[0]).map(([c,n])=>[c,c+' 件',n]);
  }
  chipRow('subChips',[['','全部',null],...subs],S.sub,v=>{S.sub=v;S.shown=0;render();});

  S.items=currentList();
  el('meta').textContent=`共 ${S.items.length} 张` + (S.persona?` · 人格 ${S.persona}`:'') + (S.sub?` · ${S.sub}`:'');
  el('grid').innerHTML='';
  el('empty').style.display = S.items.length? 'none':'block';
  S.shown=0;
  loadMore();
}

function ratioClass(){
  const t=tabDefs().find(t=>t.id===S.tab);
  return t?t.ratio:'r1';
}

function loadMore(){
  const items=S.items, grid=el('grid'), rc=ratioClass();
  const end=Math.min(items.length, S.shown+BATCH);
  for(let i=S.shown;i<end;i++){
    const x=items[i];
    const d=document.createElement('div');
    d.className='cell '+rc;
    let tag = x.cat || (x.v&&x.v!=='base'?x.v:'') || (x.count?x.count+'件':'');
    let name = x.n;
    if(S.tab==='outfits'&&!x.v) name+=' (原版)';
    d.innerHTML=`<div class="img"><img loading="lazy" src="/img/${encodeURI(x.p)}" alt=""></div>
      <div class="cap"><b title="${esc(x.n)}">${esc(name)}</b>${tag?`<span class="tag">${esc(tag)}</span>`:''}</div>`;
    d.onclick=()=>openLb(x);
    grid.appendChild(d);
  }
  S.shown=end;
}

function openLb(x){
  el('lbImg').src='/img/'+encodeURI(x.p);
  el('lbName').textContent=x.n;
  let info=[];
  if(x.e instanceof Array) info.push('人格: '+(x.e.join(', ')||'—'));
  else info.push('人格: '+x.e);
  if(x.cat) info.push('类别: '+x.cat);
  if(x.m) info.push('Master: '+x.m+' / '+(x.v==='base'?'原版':x.v));
  if(x.layout) info.push('Layout: '+x.layout+' · '+x.count+' 件 · '+(x.slots||[]).join(' + '));
  el('lbInfo').innerHTML=info.map(esc).join('<br>');
  el('lbQa').textContent='加载中…';
  el('lb').classList.add('on');
  fetch('/qa/'+encodeURI(x.p)).then(r=>r.ok?r.json():Promise.reject())
    .then(j=>el('lbQa').textContent=JSON.stringify(j,null,2))
    .catch(()=>el('lbQa').textContent='（无 QA 元数据）');
}
function closeLb(){el('lb').classList.remove('on');el('lbImg').src='';}
el('lb').addEventListener('click',e=>{if(e.target===el('lb'))closeLb();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeLb();});

el('q').addEventListener('input',e=>{S.q=e.target.value.trim();S.shown=0;
  // debounce
  clearTimeout(window._qt); window._qt=setTimeout(()=>{render();},200);});
new IntersectionObserver(es=>{
  if(es[0].isIntersecting && S.shown<S.items.length) loadMore();
},{rootMargin:'800px'}).observe(el('sentinel'));

fetch('/api/manifest').then(r=>r.json()).then(m=>{
  M=m;
  S.tab='garments';
  render();
});
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    manifest: dict = {}

    def log_message(self, fmt, *args):
        pass  # keep terminal quiet; errors still raise

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/manifest":
            body = json.dumps(self.manifest, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        elif path.startswith("/img/"):
            self._serve_file(path[5:])
        elif path.startswith("/qa/"):
            img = _safe_resolve(path[4:])
            if not img or not img.is_file():
                self._send(404, b"{}", "application/json")
                return
            qa = img.parent / (img.stem + ".qa.json")
            if qa.exists():
                self._send(200, qa.read_bytes(), "application/json; charset=utf-8")
            else:
                self._send(404, b"{}", "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def _serve_file(self, rel: str):
        p = _safe_resolve(rel)
        if not p or not p.is_file() or p.suffix.lower() not in IMG_MIME:
            self._send(404, b"not found", "text/plain")
            return
        self._send(200, p.read_bytes(), IMG_MIME[p.suffix.lower()])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if not ROOT.is_dir():
        sys.exit(f"asset root not found: {ROOT}")
    Handler.manifest = build_manifest()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"* Serving content_v2 gallery at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
