"""Build a single self-contained HTML page for people who do not run code.

This is the part that makes the output usable by designers: one file, no
server, no build step, no network. Open it from a download and search by
the words that are on the screen.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .parser import Route

TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --bg:#f4f6f8; --card:#fff; --line:#dfe5ec; --ink:#121a24; --dim:#5f6f80;
  --ok:#0b6b53; --ok-bg:#dcefe8; --gate:#8a5a06; --gate-bg:#faeedb;
  --off:#8c2f2a; --off-bg:#f8e2e0; --mark:#ffe8a3;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#10151b; --card:#171e26; --line:#273140; --ink:#e4eaf1; --dim:#93a3b5;
  --ok:#5bc3a6; --ok-bg:#12302a; --gate:#d79f4e; --gate-bg:#33260f;
  --off:#e08c84; --off-bg:#361c1a; --mark:#5c4a12;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,
  -apple-system,"Segoe UI","Noto Sans",sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:20px 16px 64px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--dim);font-size:13px;margin:0 0 18px}
.search{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0 12px;
  margin-bottom:4px}
input[type=search]{width:100%;padding:12px 14px;font-size:16px;border-radius:9px;
  border:1px solid var(--line);background:var(--card);color:var(--ink)}
input[type=search]:focus{outline:2px solid var(--ok);outline-offset:1px}
.hint{color:var(--dim);font-size:12.5px;margin:8px 2px 0}
.count{color:var(--dim);font-size:13px;margin:10px 2px 14px}
.row{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:12px 14px;margin-bottom:8px}
.top{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.route{font:600 14.5px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
  cursor:pointer;border:0;background:none;color:var(--ink);padding:0;text-align:left}
.route:hover{text-decoration:underline}
.badge{font-size:11.5px;padding:2px 8px;border-radius:999px;white-space:nowrap}
.mounted{color:var(--ok);background:var(--ok-bg)}
.conditional{color:var(--gate);background:var(--gate-bg)}
.unresolved,.unmounted{color:var(--off);background:var(--off-bg)}
.title{font-weight:600;margin:6px 0 2px}
.texts{color:var(--dim);font-size:13.5px}
.meta{color:var(--dim);font-size:12.5px;margin-top:6px;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}
mark{background:var(--mark);color:inherit;border-radius:2px}
.empty{color:var(--dim);padding:28px 2px}
#toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(12px);
  background:var(--ink);color:var(--bg);padding:9px 16px;border-radius:999px;
  font-size:13.5px;opacity:0;transition:.18s;pointer-events:none}
#toast.on{opacity:1;transform:translateX(-50%)}
@media (max-width:420px){.wrap{padding:16px 12px 56px}}
</style>
<div class="wrap">
<h1>__TITLE__</h1>
<p class="sub">__SUBTITLE__</p>

<div class="search">
  <input id="q" type="search" placeholder="Type any words you can see on the screen…"
         autocomplete="off" autofocus>
  <p class="hint">Searches the screen title, the words on the screen and the route
  name. Punctuation and spacing are ignored. Click a route name to copy it.</p>
</div>

<p class="count" id="count"></p>
<div id="list"></div>
</div>
<div id="toast" role="status" aria-live="polite"></div>

<script>
var ROUTES = __DATA__;

function norm(s){
  return (s||"").normalize("NFKC").replace(/[\\s\\W_]+/gu,"").toLowerCase();
}
var INDEX = ROUTES.map(function(r){
  return norm([r.route, r.screen_title, r.sample_texts, r.component].join(" "));
});

function esc(s){
  return (s||"").replace(/[&<>"]/g,function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];
  });
}
// Highlight the matched run by walking the normalized string back to the
// original: the query has its punctuation stripped, so a plain indexOf on
// the original text would miss every match that spans a space or a comma.
function mark(text, q){
  if(!q) return esc(text);
  var map=[], n="";
  for(var i=0;i<text.length;i++){
    var c=norm(text[i]);
    if(c){ n+=c; for(var k=0;k<c.length;k++) map.push(i); }
  }
  var at=n.indexOf(q);
  if(at<0) return esc(text);
  var s=map[at], e=map[Math.min(at+q.length-1, map.length-1)]+1;
  return esc(text.slice(0,s))+"<mark>"+esc(text.slice(s,e))+"</mark>"+esc(text.slice(e));
}

function render(){
  var raw=document.getElementById("q").value.trim(), q=norm(raw);
  var hits=[];
  for(var i=0;i<ROUTES.length;i++) if(!q || INDEX[i].indexOf(q)>=0) hits.push(ROUTES[i]);

  document.getElementById("count").textContent =
    q ? hits.length+" of "+ROUTES.length+" screens" : ROUTES.length+" screens";

  if(!hits.length){
    document.getElementById("list").innerHTML =
      '<p class="empty">Nothing matches. Try fewer words, or a phrase you can '+
      'read on the screen exactly as it appears.</p>';
    return;
  }
  var html="";
  for(var j=0;j<hits.length;j++){
    var r=hits[j];
    html+='<div class="row"><div class="top">'+
      '<button class="route" data-route="'+esc(r.route)+'">'+mark(r.route,q)+'</button>'+
      '<span class="badge '+esc(r.status)+'">'+esc(r.status)+
      (r.condition?" · "+esc(r.condition):"")+'</span></div>';
    if(r.screen_title) html+='<div class="title">'+mark(r.screen_title,q)+'</div>';
    if(r.sample_texts) html+='<div class="texts">'+mark(r.sample_texts,q)+'</div>';
    if(r.file) html+='<div class="meta">'+esc(r.file)+'</div>';
    html+='</div>';
  }
  document.getElementById("list").innerHTML=html;
}

function toast(msg){
  var t=document.getElementById("toast");
  t.textContent=msg; t.className="on";
  clearTimeout(t._h); t._h=setTimeout(function(){t.className="";},1400);
}
document.getElementById("list").addEventListener("click",function(e){
  var b=e.target.closest(".route"); if(!b) return;
  var v=b.getAttribute("data-route");
  // Opened from a file:// download, clipboard access can be blocked; fall
  // back to a selection so the value is still copyable by hand.
  if(navigator.clipboard && window.isSecureContext){
    navigator.clipboard.writeText(v).then(function(){toast("Copied  "+v);},fallback);
  } else fallback();
  function fallback(){
    var r=document.createRange(); r.selectNodeContents(b);
    var s=getSelection(); s.removeAllRanges(); s.addRange(r);
    toast("Select and copy: "+v);
  }
});
document.getElementById("q").addEventListener("input",render);
render();
</script>
"""

#: Only what the page shows. Keeping the payload small matters: the whole
#: point is a file somebody can email or drop in a shared folder.
FIELDS = ("route", "status", "condition", "screen_title", "sample_texts", "file")


def build(routes: list[Route], title: str = "Screens", subtitle: str = "") -> str:
    data = [{k: getattr(r, k) if k != "sample_texts" else " · ".join(r.sample_texts)
             for k in FIELDS} for r in routes]
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # U+2028/U+2029 are JavaScript line terminators that json.dumps leaves
    # raw, and "</" would close the script tag early. Both have broken this
    # page before; neither shows up in testing with ASCII fixtures.
    blob = (blob.replace("\u2028", "\\u2028")
                .replace("\u2029", "\\u2029")
                .replace("</", "<\\/"))

    if not subtitle:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        subtitle = f"{len(routes)} screens · generated {now}"

    # str.replace, never re.sub: re.sub interprets escapes in the
    # replacement, which mangles the JSON and leaves a page whose script
    # never runs -- the search box simply does nothing, with no error.
    page = (TEMPLATE.replace("__DATA__", blob)
                    .replace("__TITLE__", _text(title))
                    .replace("__SUBTITLE__", _text(subtitle)))

    if len([l for l in page.split("\n") if l.startswith("var ROUTES")]) != 1:
        raise RuntimeError("the data is not on a single line; the page would break")
    return page


def _text(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def write(routes: list[Route], path: str | Path, **kw) -> Path:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build(routes, **kw), encoding="utf-8")
    return p
