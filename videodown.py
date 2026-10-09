#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoDown — Single-File Flask Video Downloader
==============================================
Original HTML/CSS/JS UI embedded as-is; only the mock service layer was
replaced with a real Flask + yt-dlp backend.

Install & run:
    pip install flask yt-dlp
    python videodown.py
    → open http://localhost:5000

Optional but strongly recommended:
    install  ffmpeg  → enables MP3 conversion and 1080p/720p stream merging.
    (Docker image already includes ffmpeg — see Dockerfile / requirements.txt.)

Deploy on Render:
    Push videodown.py + requirements.txt + Dockerfile + render.yaml to GitHub,
    then "New +" -> "Blueprint" in Render and pick the repo. Free plan works
    (sleeps after ~15 min idle); for persistent cookies/settings use the paid
    plan + persistent disk described inside render.yaml.

Notes:
  * Works with YouTube, TikTok, Instagram, Facebook, Vimeo, X (Twitter) and
    1000+ other sites, including short/mobile share links (vm.tiktok.com,
    fb.watch, m.facebook.com, instagram.com/reel/ ...).
  * Private / member-only / age-restricted videos download too when you add
    login cookies of an account that can view them (Settings page, or save a
    videodown_cookies.txt next to this file).
  * Recommended extra: pip install curl-cffi  (browser impersonation; noticeably
    improves TikTok / Instagram / Facebook success when they run bot checks).
  * Downloaded files are kept in a temp dir for 1 hour, then auto-cleaned.
  * This is a personal/local tool — do not expose it publicly without auth.
  * Only download content you have the right to save. DRM streams are
    not supported.
"""

import os
import json
import re
import shutil
import tempfile
import threading
import time
import uuid
from urllib.parse import urlparse

try:
    from flask import Flask, Response, jsonify, request, send_file
    import yt_dlp
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: %s\n"
        "Install with:  pip install flask yt-dlp" % exc
    )

# ============================================================================
# The complete front-end (UI/UX untouched, service layer wired to /api/*).
# ============================================================================
HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8"><meta name="color-scheme" content="dark">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>VideoDown — Download videos in seconds</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
/* ===== 1. DESIGN TOKENS ===== */
:root{
  --lime:#c8f542;--violet:#8b6cff;--cyan:#27d3ee;--coral:#ff6b57;--amber:#ffb830;--mint:#3ee0a0;
  --bg:#0d0b13;--surface:#171321;--surface2:#211b30;--line:#ffffff1f;--text:#f4f1fa;--muted:#a79fba;
  --on-lime:#12140a;--glow1:#8b6cff30;--glow2:#ff6b5722;--glow3:#27d3ee1c;
  --display:'Bricolage Grotesque',system-ui,'Segoe UI',sans-serif;--mono:'JetBrains Mono',ui-monospace,Menlo,monospace;
  --ease:cubic-bezier(.2,.8,.2,1);color-scheme:dark;
}
/* ===== 2. GLOBAL ===== */
*{box-sizing:border-box;margin:0}
html{height:100%}
body{min-height:100%;background:var(--bg);color:var(--text);font:500 16px/1.5 var(--display);
  padding:env(safe-area-inset-top,0) 0 calc(88px + env(safe-area-inset-bottom,0));
  background-image:radial-gradient(60% 40% at 90% 0%,var(--glow1),transparent),radial-gradient(50% 40% at 0% 60%,var(--glow2),transparent),radial-gradient(40% 30% at 100% 100%,var(--glow3),transparent);
  background-attachment:fixed;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.07;z-index:0;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)'/%3E%3C/svg%3E")}
button,input,select{font:inherit;color:inherit}
button{cursor:pointer;background:none;border:0}
:focus-visible{outline:2px solid var(--cyan);outline-offset:3px;border-radius:8px}
.ic{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.mono{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
/* ===== 3. COMPONENTS ===== */
header{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;max-width:1200px;margin:auto;padding:16px 20px}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:20px;letter-spacing:-.02em}
.brand i{color:var(--lime)}
nav.tabs{position:fixed;z-index:10;left:12px;right:12px;bottom:calc(10px + env(safe-area-inset-bottom,0));display:flex;gap:4px;padding:6px;border-radius:22px;background:color-mix(in srgb,var(--surface) 92%,transparent);border:1px solid var(--line);backdrop-filter:blur(10px)}
nav.tabs button{flex:1;min-height:52px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;font-size:12px;border-radius:16px;color:var(--muted);transition:all .18s var(--ease)}
nav.tabs button[aria-current=page]{background:var(--lime);color:var(--on-lime);font-weight:700}
main{position:relative;z-index:1;max-width:1200px;margin:auto;padding:8px 20px 40px}
.view{display:none;animation:rise .4s var(--ease)}
.view.on{display:block}
@keyframes rise{from{opacity:0;transform:translateY(14px)}}
.hero{display:grid;gap:28px;align-items:center}
.sig{display:inline-flex;gap:8px;align-items:center;padding:6px 12px;border:1px solid var(--line);border-radius:99px;margin-bottom:18px}
.sig b{width:8px;height:8px;border-radius:50%;background:var(--mint);box-shadow:0 0 0 4px #3ee0a02b}
h1{font-weight:800;font-size:clamp(46px,13vw,104px);line-height:.9;letter-spacing:-.045em;text-transform:uppercase}
h1 .o{color:transparent;-webkit-text-stroke:2px var(--text)}
h1 .g{background:linear-gradient(95deg,var(--lime),var(--cyan) 60%,var(--violet));-webkit-background-clip:text;background-clip:text;color:transparent;text-transform:none;font-style:italic;letter-spacing:-.05em}
.lede{margin:20px 0 0;max-width:34ch;color:var(--muted);font-size:18px}
.lede em{color:var(--coral);font-style:normal}
.stagewrap{position:relative}
.frames{position:absolute;inset:-14px -10px auto auto;width:88%;height:100%;pointer-events:none}
.frames span{position:absolute;inset:0;border-radius:26px;border:1px solid}
.frames span:nth-child(1){transform:translate(-14px,14px) rotate(-3deg);border-color:var(--violet);background:#8b6cff14}
.frames span:nth-child(2){transform:translate(10px,-10px) rotate(2deg);border-color:var(--coral);background:#ff6b5710}
.stage{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:26px;padding:20px;min-height:250px;box-shadow:0 30px 60px -30px #0008}
.field{display:flex;align-items:center;gap:10px;min-height:58px;padding:0 8px 0 16px;border-radius:16px;background:var(--surface2);border:1.5px solid transparent;transition:border-color .18s,box-shadow .18s}
.field:focus-within{border-color:var(--cyan);box-shadow:0 0 0 4px #27d3ee22}
.field.bad{border-color:var(--coral);animation:shake .3s}
@keyframes shake{25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}
.field input{flex:1;min-width:0;height:56px;background:none;border:0;outline:0}
.field input::placeholder{color:var(--muted)}
.chip{min-height:44px;padding:0 12px;border-radius:12px;display:flex;align-items:center;gap:6px;font-size:14px;color:var(--cyan);border:1px solid var(--line);transition:background .18s}
.chip:hover{background:#27d3ee1a}
.btn{min-height:52px;padding:0 22px;border-radius:14px;display:inline-flex;align-items:center;justify-content:center;gap:10px;font-weight:700;background:var(--lime);color:var(--on-lime);transition:transform .15s var(--ease),box-shadow .2s,filter .2s;box-shadow:0 8px 24px -8px var(--lime)}
.btn:hover{transform:translateY(-2px);filter:brightness(1.06)}
.btn:active{transform:scale(.97)}
.btn:disabled{opacity:.5;pointer-events:none}
.btn.ghost{background:none;color:var(--text);border:1px solid var(--line);box-shadow:none}
.btn.wide{width:100%;margin-top:12px}
.err{margin-top:10px;color:var(--coral);font-size:14px;min-height:21px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.err button{color:var(--text);text-decoration:underline;min-height:44px}
.works{margin-top:14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.works span.p{padding:4px 10px;border-radius:99px;font-size:13px;border:1px solid}
.steps{list-style:none;padding:0;margin:18px 0}
.steps li{display:flex;gap:12px;align-items:center;padding:9px 0;color:var(--muted);transition:color .3s}
.steps li .d{width:22px;height:22px;border-radius:50%;border:2px solid var(--line);display:grid;place-items:center;transition:all .3s}
.steps li.act{color:var(--text)}
.steps li.act .d{border-color:var(--cyan);border-top-color:transparent;animation:spin .8s linear infinite}
.steps li.done{color:var(--text)}
.steps li.done .d{background:var(--mint);border-color:var(--mint);color:#0b1f17}
.steps li.done .ic{width:13px;height:13px;stroke-width:3}
@keyframes spin{to{transform:rotate(360deg)}}
.res{display:grid;gap:16px}
.thumb{position:relative;aspect-ratio:16/9;border-radius:18px;overflow:hidden}
.thumb svg.bgart{width:100%;height:100%;display:block}
.thumb img.bgart{width:100%;height:100%;object-fit:cover;display:block}
.thumb .dur{position:absolute;right:10px;bottom:10px;background:#000b;color:#fff;padding:2px 8px;border-radius:8px;font:600 12px var(--mono)}
.res h2{font-size:22px;line-height:1.15;letter-spacing:-.02em}
.fmts{display:grid;gap:8px;margin-top:10px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
.fmt{text-align:left;padding:12px;border-radius:14px;border:1.5px solid var(--line);min-height:62px;transition:all .18s var(--ease)}
.fmt b{display:block;font-size:16px}
.fmt small{color:var(--muted);font:400 12px var(--mono)}
.fmt:hover{transform:translateY(-2px)}
.fmt[aria-checked=true]{border-color:var(--violet);background:#8b6cff22}
.fmt.audio[aria-checked=true]{border-color:var(--amber);background:#ffb83022}
.bar{height:12px;border-radius:99px;background:var(--surface2);overflow:hidden;margin:14px 0 8px}
.bar i{display:block;height:100%;width:0;border-radius:99px;background:repeating-linear-gradient(115deg,#0002 0 8px,#0000 8px 16px),linear-gradient(90deg,var(--lime),var(--cyan));background-size:32px 100%,100% 100%;animation:slide 1s linear infinite;transition:width .25s linear}
@keyframes slide{to{background-position:32px 0,0 0}}
.pct{font:800 64px/1 var(--display);letter-spacing:-.04em;color:var(--cyan)}
.row{display:flex;gap:12px;align-items:center;justify-content:space-between}
.okmark{width:84px;height:84px;color:var(--mint)}
.okmark circle{stroke-dasharray:252;stroke-dashoffset:252;animation:draw .6s var(--ease) forwards}
.okmark path{stroke-dasharray:50;stroke-dashoffset:50;animation:draw .4s .45s var(--ease) forwards}
@keyframes draw{to{stroke-dashoffset:0}}
.sec-h{display:flex;justify-content:space-between;align-items:end;margin:8px 0 22px;gap:12px}
.sec-h h2{font-size:clamp(34px,8vw,60px);letter-spacing:-.04em;line-height:.95}
.hist{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
.hi{border-radius:18px;overflow:hidden;background:var(--surface);border:1px solid var(--line)}
@media(min-width:620px){.hi:nth-child(3n+2){transform:translateY(10px)}}
.hi .thumb{border-radius:0}
.hi .b{padding:12px 14px;display:grid;gap:4px}
.hi .b h3{font-size:16px;line-height:1.2}
.hi .acts{display:flex;gap:6px;margin-top:6px}
.icb{width:44px;height:44px;border-radius:12px;border:1px solid var(--line);display:grid;place-items:center;transition:all .18s}
.icb:hover{border-color:var(--cyan);color:var(--cyan)}
.empty{text-align:center;padding:40px 10px;max-width:420px;margin:auto}
.empty>svg{width:200px;max-width:70%;margin-bottom:12px}
.empty p{color:var(--muted);margin:6px 0 18px}
.set{display:grid;gap:26px;max-width:720px}
.grp h3{margin-bottom:8px}
.grp .box{border-top:2px solid var(--c,var(--line))}
.grp:nth-child(1){--c:var(--violet)}.grp:nth-child(2){--c:var(--lime)}.grp:nth-child(3){--c:var(--cyan)}.grp:nth-child(4){--c:var(--coral)}
.opt{display:flex;justify-content:space-between;align-items:center;gap:12px;min-height:60px;border-bottom:1px solid var(--line)}
.opt p{color:var(--muted);font-size:14px}
.seg{display:flex;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.seg button{min-height:44px;padding:0 14px;color:var(--muted)}
.seg button[aria-pressed=true]{background:var(--violet);color:#fff}
select{min-height:44px;background:var(--surface2);border:1px solid var(--line);border-radius:12px;padding:0 10px}
.opt.col{flex-direction:column;align-items:stretch;padding:14px 0;gap:10px}
.opt.col .row2{display:flex;gap:8px;flex-wrap:wrap}
textarea{width:100%;min-height:120px;background:var(--surface2);border:1px solid var(--line);border-radius:12px;padding:12px;font:400 12px/1.6 var(--mono);color:var(--text);resize:vertical}
textarea::placeholder{color:var(--muted)}
.sw{width:56px;height:44px;position:relative}
.sw::after{content:"";position:absolute;left:0;right:0;top:10px;height:24px;border-radius:99px;background:var(--surface2);border:1px solid var(--line);transition:background .2s}
.sw::before{content:"";position:absolute;left:4px;top:14px;width:16px;height:16px;border-radius:50%;background:var(--muted);z-index:1;transition:all .2s var(--ease)}
.sw[aria-checked=true]::after{background:var(--lime)}
.sw[aria-checked=true]::before{transform:translateX(28px);background:var(--on-lime)}
.toast{position:fixed;z-index:20;left:50%;top:calc(14px + env(safe-area-inset-top,0));transform:translate(-50%,-140%);padding:12px 18px;border-radius:14px;background:var(--text);color:var(--bg);font-weight:700;transition:transform .35s var(--ease);max-width:90vw;text-align:center}
.toast.show{transform:translate(-50%,0)}
/* ===== 4. RESPONSIVE ===== */
@media(min-width:900px){
  body{padding-bottom:40px}
  header{padding:22px 32px}
  nav.tabs{position:static;margin-left:auto;padding:4px;border-radius:99px}
  nav.tabs button{flex-direction:row;gap:8px;min-height:44px;padding:0 18px;border-radius:99px;font-size:14px}
  main{padding:24px 32px 60px}
  .hero{grid-template-columns:1.15fr .85fr;gap:70px}
  .stage{padding:26px}
  .res{grid-template-columns:1fr 1fr;align-items:start}
  .res .full{grid-column:1/-1}
}
@media(max-width:380px){.pct{font-size:52px}.chip span{display:none}}
/* ===== 5. MOTION ===== */
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
</style>
</head>
<body>
<header>
  <div class="brand">
    <svg width="34" height="34" viewBox="0 0 34 34" aria-hidden="true"><rect x="2" y="2" width="30" height="30" rx="10" fill="var(--violet)"/><path d="M11 9h12v7l-6 7-6-7z" fill="var(--lime)"/><path d="M14 12l5 3-5 3z" fill="var(--violet)"/></svg>
    <span>Video<i>Down</i></span>
  </div>
  <nav class="tabs" aria-label="Main" id="nav"></nav>
</header>

<main id="main">
  <section class="view on" id="v-home" aria-label="Home">
    <div class="hero">
      <div>
        <div class="sig mono"><b></b> v3.0 · Flask edition</div>
        <h1>Download<br><span class="o">videos</span><br><span class="g">in seconds.</span></h1>
        <p class="lede">Paste a link. Pick a format. Done. No accounts, no ads, <em>nothing leaves your device</em> but the link.</p>
      </div>
      <div class="stagewrap">
        <div class="frames" aria-hidden="true"><span></span><span></span></div>
        <div class="stage" id="stage" aria-live="polite"></div>
      </div>
    </div>
  </section>

  <section class="view" id="v-history" aria-label="History">
    <div class="sec-h"><h2>Your<br>library</h2><button class="btn ghost" id="clearH"><svg class="ic"><use href="#i-trash"/></svg>Clear</button></div>
    <div id="histBody"></div>
  </section>

  <section class="view" id="v-settings" aria-label="Settings">
    <div class="sec-h"><h2>Settings</h2></div>
    <div class="set">
      <div class="grp"><h3>Downloads</h3><div class="box">
        <div class="opt"><div>Default format</div><select id="sFormat" aria-label="Default format"><option value="mp4">MP4 video</option><option value="mp3">MP3 audio</option></select></div>
        <div class="opt"><div>Default quality</div><select id="sQuality" aria-label="Default quality"><option>1080p</option><option>720p</option><option>480p</option></select></div>
      </div></div>
      <div class="grp"><h3>Storage</h3><div class="box">
        <div class="opt"><div>Save to history<p>Stored only in this browser.</p></div><button class="sw" id="sHist" role="switch" aria-label="Save to history"></button></div>
        <div class="opt"><div>Clear history<p id="hCount"></p></div><button class="btn ghost" id="clearS">Clear</button></div>
      </div></div>
      <div class="grp"><h3>Login &amp; private videos</h3><div class="box">
        <div class="opt"><div>Browser cookies<p id="sCookieStatus">Not set</p></div><select id="sBrowser" aria-label="Browser cookies"><option value="none">Off</option><option value="chrome">Chrome</option><option value="chromium">Chromium</option><option value="firefox">Firefox</option><option value="edge">Edge</option><option value="brave">Brave</option><option value="opera">Opera</option><option value="vivaldi">Vivaldi</option><option value="safari">Safari</option></select></div>
        <div class="opt col"><div>cookies.txt<p>Paste Netscape cookies.txt exported from your browser. With login cookies, private / member-only videos your account can view — TikTok, Instagram, Facebook, YouTube — download normally.</p></div><textarea id="sCookieText" spellcheck="false" placeholder="# Netscape HTTP Cookie File&#10;.instagram.com  TRUE  /  TRUE  1893456000  sessionid  ..."></textarea><div class="row2"><button class="btn" id="sCookieSave">Save cookies</button><button class="btn ghost" id="sCookieClear">Clear</button></div></div>
      </div></div>
      <div class="grp"><h3>About &amp; privacy</h3><div class="box"><p style="padding-top:12px;color:var(--muted)">VideoDown is powered by yt-dlp on a local Flask server. Works with YouTube, TikTok, Instagram, Facebook, Vimeo, X and more. Private or member-only videos need login cookies (above).  Only respect content you have the right to save — DRM-protected streams are not supported. Settings, history and cookies never leave this device.</p></div></div>
    </div>
  </section>
</main>
<div class="toast" id="toast" role="status"></div>

<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<symbol id="i-link" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></symbol>
<symbol id="i-home" viewBox="0 0 24 24"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/></symbol>
<symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></symbol>
<symbol id="i-set" viewBox="0 0 24 24"><path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/></symbol>
<symbol id="i-dl" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></symbol>
<symbol id="i-check" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></symbol>
<symbol id="i-x" viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></symbol>
<symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></symbol>
<symbol id="i-moon" viewBox="0 0 24 24"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></symbol>
<symbol id="i-trash" viewBox="0 0 24 24"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></symbol>
<symbol id="i-spark" viewBox="0 0 24 24"><path d="m12 3 1.9 5.8L20 10l-6.1 1.2L12 17l-1.9-5.8L4 10l6.1-1.2z"/></symbol>
<symbol id="i-paste" viewBox="0 0 24 24"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></symbol>
<symbol id="i-retry" viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></symbol>
</defs></svg>

<script>
/* ===== 6. HELPERS & STORAGE ===== */
const $=(s,r=document)=>r.querySelector(s);
const ic=n=>`<svg class="ic" aria-hidden="true"><use href="#i-${n}"/></svg>`;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const store={
  get(k,d){try{const v=localStorage.getItem('vd:'+k);return v?JSON.parse(v):d}catch{return d}},
  set(k,v){try{localStorage.setItem('vd:'+k,JSON.stringify(v))}catch{}}
};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

/* ===== 7. SERVICE LAYER (Flask + yt-dlp backend) ===== */
const Service=(()=>{
  const SOURCES=[
    {re:/(youtube\.com|youtu\.be)/i,name:'YouTube'},{re:/vimeo\.com/i,name:'Vimeo'},
    {re:/tiktok\.com/i,name:'TikTok'},{re:/(twitter|x)\.com/i,name:'X'},{re:/instagram\.com/i,name:'Instagram'},
    {re:/(facebook\.com|fb\.watch|fb\.com)/i,name:'Facebook'}
  ];
  const fail=(code,message)=>Object.assign(new Error(message),{code});
  const call=async(path,body,signal)=>{
    let r;
    try{
      r=body===undefined
        ? await fetch(path,{signal})
        : await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
    }catch(e){
      if(e.name==='AbortError'||(signal&&signal.aborted)) throw fail('cancel','Cancelled');
      throw fail('network','Network hiccup. Check your connection.');
    }
    let data=null;try{data=await r.json()}catch{}
    if(!r.ok) throw fail((data&&data.code)||'network',(data&&data.error)||'Something went wrong.');
    return data;
  };
  const nap=(ms,signal)=>new Promise((res,rej)=>{
    const t=setTimeout(res,ms);
    if(signal)signal.addEventListener('abort',()=>{clearTimeout(t);rej(fail('cancel','Cancelled'))},{once:true});
  });
  return {
    validate(raw){
      let url=(raw||'').trim();
      if(!url) throw fail('empty','Paste a video link first.');
      const m=url.match(/https?:\/\/\S+/i);
      if(m)url=m[0];else if(/\s/.test(url))url=url.split(/\s+/)[0];
      url=url.replace(/[),.;'"\u2026]+$/,'');
      let u;try{u=new URL(/^https?:\/\//i.test(url)?url:'https://'+url)}catch{throw fail('invalid','That doesn\u2019t look like a link.')}
      if(!u.hostname.includes('.')) throw fail('invalid','That doesn\u2019t look like a link.');
      const src=SOURCES.find(s=>s.re.test(u.hostname));
      return {url:u.href,source:src?src.name:u.hostname.replace(/^www\./,'')};
    },
    async analyze(raw,onStep,signal){
      this.validate(raw);
      let step=0;onStep(0);
      const tick=setInterval(()=>{if(step<3){step++;onStep(step)}},650);
      try{
        const d=await call('/api/analyze',{url:raw.trim()},signal);
        clearInterval(tick);onStep(3);
        return d;
      }catch(e){clearInterval(tick);throw e}
    },
    async download(fmt,onProgress,signal){
      const start=await call('/api/download',{url:fmt._url,fmt:fmt.id},signal);
      window.__vdFile=null;
      try{
        for(;;){
          await nap(250,signal);
          const s=await call('/api/progress/'+start.job,undefined,signal);
          if(s.total>0)fmt.size=Math.round(s.total*10)/10;
          if(s.state==='error')throw fail(s.code||'download',s.error||'Download interrupted.');
          if(s.state==='cancelled')throw fail('cancel','Download cancelled');
          onProgress(s.pct,s.mb);
          if(s.state==='done'){window.__vdFile='/api/file/'+start.job;onProgress(100,s.mb||fmt.size);return}
        }
      }catch(e){
        fetch('/api/cancel/'+start.job,{method:'POST'}).catch(()=>{});
        throw e;
      }
    }
  };
})();

/* ===== 8. APPLICATION STATE ===== */
const state={
  view:'home',phase:'input',url:'',error:null,step:0,info:null,fmt:null,pct:0,mb:0,ctrl:null,
  history:store.get('history',[]),
  prefs:Object.assign({format:'mp4',quality:'1080p',saveHistory:true},store.get('prefs',{}))
};
const savePrefs=()=>store.set('prefs',state.prefs);
const saveHist=()=>store.set('history',state.history);

/* ===== 9. UI RENDERING ===== */
const PLAT=[['YouTube','--coral'],['Vimeo','--cyan'],['TikTok','--violet'],['X','--amber'],['Instagram','--mint'],['Facebook','--lime']];
function thumbArt(hue,small){
  const a=`hsl(${hue} 80% 55%)`,b=`hsl(${(hue+70)%360} 85% 45%)`,c=`hsl(${(hue+180)%360} 80% 60%)`;
  return `<svg class="bgart" viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <defs><linearGradient id="g${hue}${small?'s':''}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs>
    <rect width="320" height="180" fill="url(#g${hue}${small?'s':''})"/>
    <circle cx="240" cy="55" r="26" fill="${c}" opacity=".85"/>
    <path d="M0 140 L70 80 L125 125 L190 60 L320 150 V180 H0Z" fill="#0000004d"/>
    <path d="M0 160 L90 112 L170 150 L250 100 L320 140 V180 H0Z" fill="#00000066"/>
  </svg>`;
}
const thumb=(x,small)=>x&&x.thumb?`<img class="bgart" src="${esc(x.thumb)}" alt="">`:thumbArt(x.hue,small);
function renderNav(){
  $('#nav').innerHTML=[['home','Home','home'],['history','History','clock'],['settings','Settings','set']]
    .map(([k,l,i])=>`<button data-go="${k}" ${state.view===k?'aria-current="page"':''}>${ic(i)}<span>${l}</span></button>`).join('');
}
function renderStage(){
  const s=$('#stage'),P=state.phase;
  const T={
    input:()=>`<form id="urlForm" novalidate>
        <label class="mono" for="url">Video link</label>
        <div class="field ${state.error?'bad':''}" style="margin-top:8px">
          ${ic('link')}
          <input id="url" type="url" inputmode="url" autocomplete="off" placeholder="Paste video URL…" value="${esc(state.url)}" aria-describedby="err" ${state.error?'aria-invalid="true"':''}>
          <button type="button" class="chip" id="pasteBtn" aria-label="Paste from clipboard">${ic('paste')}<span>Paste</span></button>
        </div>
        <div class="err" id="err" role="alert">${state.error?esc(state.error.message)+(['analysis','network'].includes(state.error.code)?' <button type="submit">Retry</button>':''):''}</div>
        <button class="btn wide" type="submit">${ic('spark')} Analyze video</button>
      </form>
      <div class="works"><span class="mono">Works with</span>${PLAT.map(([n,c])=>`<span class="p" style="color:var(${c});border-color:color-mix(in srgb,var(${c}) 40%,transparent)">${n}</span>`).join('')}</div>`,
    analyzing:()=>{
      const L=['Link detected','Reading link','Analyzing video','Preparing formats'];
      return `<div class="mono">Working on</div><p style="word-break:break-all;color:var(--cyan);margin-top:4px">${esc(state.url)}</p>
      <ol class="steps">${L.map((t,i)=>`<li class="${i<state.step?'done':i===state.step?'act':''}"><span class="d">${i<state.step?ic('check'):''}</span>${t}</li>`).join('')}</ol>
      <button class="btn ghost" id="cancel">${ic('x')} Cancel</button>`;
    },
    result:()=>{const i=state.info;return `<div class="res">
      <div class="thumb">${thumb(i)}<span class="dur">${i.duration}</span></div>
      <div><span class="mono" style="color:var(--amber)">${esc(i.source)}</span><h2>${esc(i.title)}</h2>
        <div class="fmts" role="radiogroup" aria-label="Format">${i.formats.map(f=>`<button class="fmt ${f.type==='mp3'?'audio':''}" role="radio" aria-checked="${f.id===state.fmt.id}" data-fmt="${f.id}"><b>${f.label}</b><small>${f.size} MB</small></button>`).join('')}</div></div>
      <div class="full" style="display:flex;gap:10px;flex-wrap:wrap"><button class="btn" id="dlBtn" style="flex:1">${ic('dl')} Download · ${state.fmt.size} MB</button><button class="btn ghost" id="again">New link</button></div></div>`},
    downloading:()=>`<div class="row"><div><div class="mono">Downloading</div><div style="font-weight:700;margin-top:2px">${esc(fileName())}</div></div><div class="thumb" style="width:92px;flex:none;border-radius:12px">${thumb(state.info,1)}</div></div>
      <div class="pct" aria-hidden="true"><span id="pctN">${Math.round(state.pct)}</span>%</div>
      <div class="bar" role="progressbar" aria-label="Download progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(state.pct)}"><i style="width:${state.pct}%"></i></div>
      <div class="row mono"><span id="mbN">${state.mb.toFixed(1)} / ${state.fmt.size} MB</span><span>${state.pct<100?'Receiving data':'Finishing'}</span></div>
      <button class="btn ghost wide" id="cancel">${ic('x')} Cancel</button>`,
    done:()=>`<div style="text-align:center;padding:6px 0"><svg class="okmark ic" viewBox="0 0 84 84" style="stroke-width:3"><circle cx="42" cy="42" r="40"/><path d="M26 43l11 11 21-23"/></svg>
      <h2 style="font-size:26px;margin-top:6px">Saved.</h2><p class="mono" style="margin:6px 0 4px;word-break:break-all">${esc(fileName())}</p><p style="color:var(--muted)">${state.fmt.label} · ${state.fmt.size} MB</p>
      <button class="btn wide" id="saveBtn">${ic('dl')} Save file</button><button class="btn ghost wide" id="again">Download another</button></div>`
  };
  s.innerHTML=T[P]();
  if(P==='input'&&state.view==='home'&&state._focus){$('#url').focus();state._focus=false}
}
const fileName=()=>`${state.info.title.toLowerCase().replace(/[^a-z0-9]+/g,'-').slice(0,32)}.${state.fmt.type}`;
function renderHistory(){
  const h=state.history,b=$('#histBody');
  $('#hCount').textContent=h.length+' item'+(h.length===1?'':'s');
  if(!h.length){
    b.innerHTML=`<div class="empty"><svg viewBox="0 0 200 130" aria-hidden="true"><rect x="40" y="30" width="120" height="76" rx="12" fill="none" stroke="var(--violet)" stroke-width="3" transform="rotate(-6 100 68)"/><rect x="40" y="26" width="120" height="76" rx="12" fill="var(--surface)" stroke="var(--coral)" stroke-width="3" transform="rotate(4 100 64)"/><path d="M90 48l30 16-30 16z" fill="var(--lime)"/><circle cx="160" cy="24" r="6" fill="var(--cyan)"/><circle cx="34" cy="100" r="4" fill="var(--amber)"/></svg>
      <h3>Nothing here yet</h3><p>Finished downloads land here so you can grab them again later.</p><button class="btn" data-go="home">${ic('link')} Paste a link</button></div>`;return;
  }
  b.innerHTML=`<div class="hist">${h.map((x,i)=>`<article class="hi"><div class="thumb">${thumb(x,1)}<span class="dur">${x.duration}</span></div><div class="b"><span class="mono">${esc(x.source)} · ${esc(x.date)}</span><h3>${esc(x.title)}</h3><span class="mono" style="color:var(--cyan)">${esc(x.label)} · ${x.size} MB</span>
    <div class="acts"><button class="icb" data-redo="${i}" aria-label="Download again: ${esc(x.title)}">${ic('retry')}</button><button class="icb" data-del="${i}" aria-label="Remove: ${esc(x.title)}">${ic('trash')}</button></div></div></article>`).join('')}</div>`;
}
function renderSettings(){
  const p=state.prefs;
  $('#sFormat').value=p.format;$('#sQuality').value=p.quality;
  $('#sHist').setAttribute('aria-checked',p.saveHistory);
  renderCookies();
}
async function renderCookies(){
  try{
    const d=await (await fetch('/api/settings')).json();
    const s=$('#sCookieStatus');
    if(d.cookies==='file')s.textContent='Active — cookies.txt loaded';
    else if(d.cookies==='browser')s.textContent='Active — using '+(d.browser||'browser')+' session';
    else s.textContent='Not set — private videos need login cookies';
    const b=$('#sBrowser');if(b)b.value=d.browser||'none';
  }catch(e){/* server offline */}
}
function show(view){
  state.view=view;
  document.querySelectorAll('.view').forEach(v=>v.classList.toggle('on',v.id==='v-'+view));
  renderNav();
  if(view==='history')renderHistory();
  if(view==='settings'){renderSettings();renderHistory()}
  window.scrollTo({top:0,behavior:'smooth'});
}
/* ===== 10. TOASTS ===== */
let toastT;
function toast(msg){const t=$('#toast');t.textContent=msg;t.classList.add('show');clearTimeout(toastT);toastT=setTimeout(()=>t.classList.remove('show'),2800)}

/* ===== 11. FLOW / EVENT HANDLERS ===== */
async function startAnalyze(){
  state.error=null;
  try{Service.validate(state.url)}catch(e){state.error=e;renderStage();$('#url').focus();return}
  state.phase='analyzing';state.step=0;state.ctrl=new AbortController();renderStage();
  try{
    state.info=await Service.analyze(state.url,i=>{state.step=i;renderStage()},state.ctrl.signal);
    const want=state.info.formats.find(f=>state.prefs.format==='mp3'?f.type==='mp3':f.quality===state.prefs.quality);
    state.fmt=want||state.info.formats[0];state.phase='result';
  }catch(e){
    state.phase='input';
    if(e.code==='cancel')toast('Cancelled');else{state.error=e;toast(e.message)}
  }
  renderStage();
}
async function startDownload(){
  state.phase='downloading';state.pct=0;state.mb=0;state.ctrl=new AbortController();state.fmt._url=state.url;renderStage();
  try{
    await Service.download(state.fmt,(p,mb)=>{
      state.pct=p;state.mb=mb;
      const b=$('.bar i');if(!b)return;b.style.width=p+'%';$('.bar').setAttribute('aria-valuenow',Math.round(p));
      $('#pctN').textContent=Math.round(p);$('#mbN').textContent=`${mb.toFixed(1)} / ${state.fmt.size} MB`;
    },state.ctrl.signal);
    state.phase='done';
    if(state.prefs.saveHistory){
      const i=state.info;
      state.history.unshift({url:i.url,title:i.title,source:i.source,hue:i.hue,thumb:i.thumb,duration:i.duration,label:state.fmt.label,size:state.fmt.size,fmtId:state.fmt.id,date:new Date().toLocaleDateString(undefined,{month:'short',day:'numeric'})});
      state.history=state.history.slice(0,50);saveHist();
    }
    toast('Download complete');
  }catch(e){
    state.phase='result';toast(e.code==='cancel'?'Download cancelled':e.message);
  }
  renderStage();
}
function reset(){state.phase='input';state.url='';state.error=null;state._focus=true;renderStage()}
function clearHistory(){
  if(!state.history.length)return toast('History is already empty');
  state.history=[];saveHist();renderHistory();toast('History cleared');
}
document.addEventListener('click',async e=>{
  const t=e.target.closest('button');if(!t)return;
  if(t.dataset.go)return show(t.dataset.go);
  if(t.dataset.fmt){state.fmt=state.info.formats.find(f=>f.id===t.dataset.fmt);return renderStage()}
  if(t.dataset.del){state.history.splice(+t.dataset.del,1);saveHist();return renderHistory()}
  if(t.dataset.redo){state.url=state.history[+t.dataset.redo].url;state.phase='input';renderStage();show('home');return startAnalyze()}
  switch(t.id){
    case'pasteBtn':
      try{state.url=(await navigator.clipboard.readText()).trim();renderStage();if(state.url)startAnalyze()}
      catch{toast('Clipboard blocked — paste with Ctrl/Cmd+V');$('#url').focus()}break;
    case'cancel':state.ctrl&&state.ctrl.abort();break;
    case'dlBtn':startDownload();break;
    case'again':reset();break;
    case'saveBtn':{if(!window.__vdFile){toast('File is not ready yet');break}const a=document.createElement('a');a.href=window.__vdFile;a.download='';document.body.appendChild(a);a.click();a.remove();toast('Saving file…')}break;
    case'sCookieSave':{
      const txt=($('#sCookieText').value||'').trim();
      if(!txt){toast('Paste cookies.txt content first');break}
      const r=await fetch('/api/cookies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:txt})}).then(r=>r.json());
      toast(r.ok?'Cookies saved \u2014 private videos unlocked':'Could not save cookies');
      if(r.ok)$('#sCookieText').value='';
      renderCookies();break;
    }
    case'sCookieClear':
      await fetch('/api/cookies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clear:true})});
      $('#sCookieText').value='';toast('Cookies cleared');renderCookies();break;
    case'clearH':case'clearS':clearHistory();break;
    case'sHist':state.prefs.saveHistory=!state.prefs.saveHistory;savePrefs();renderSettings();break;
  }
});
document.addEventListener('submit',e=>{if(e.target.id==='urlForm'){e.preventDefault();startAnalyze()}});
document.addEventListener('input',e=>{if(e.target.id==='url'){state.url=e.target.value;if(state.error){state.error=null;e.target.closest('.field').classList.remove('bad');$('#err').textContent=''}}});
$('#sFormat').addEventListener('change',e=>{state.prefs.format=e.target.value;savePrefs()});
$('#sQuality').addEventListener('change',e=>{state.prefs.quality=e.target.value;savePrefs()});
$('#sBrowser').addEventListener('change',e=>{fetch('/api/cookies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({browser:e.target.value})}).then(r=>r.json()).then(r=>{toast(r.ok?'Browser cookies updated':'Could not update');renderCookies()}).catch(()=>toast('Could not update'))});

/* ===== INIT ===== */
renderNav();renderStage();renderHistory();renderSettings();
</script>
</body>
</html>"""

# ============================================================================
# Backend
# ============================================================================
app = Flask(__name__)
FFMPEG = shutil.which("ffmpeg") is not None
JOBS = {}
LOCK = threading.Lock()
JOB_TTL = 3600  # seconds to keep finished jobs (and their files) around
MB = 1024.0 * 1024.0
VALID_FMTS = ("mp4-1080p", "mp4-720p", "mp4-480p", "mp3")
BITRATE_KBPS = {1080: 4500, 720: 2500, 480: 1200}

PLATFORMS = [
    (re.compile(r"(youtube\.com|youtu\.be)", re.I), "YouTube"),
    (re.compile(r"vimeo\.com", re.I), "Vimeo"),
    (re.compile(r"tiktok\.com", re.I), "TikTok"),
    (re.compile(r"(twitter|x)\.com", re.I), "X"),
    (re.compile(r"instagram\.com", re.I), "Instagram"),
    (re.compile(r"(facebook\.com|fb\.watch|fb\.com)", re.I), "Facebook"),
]


class _QuietLogger:
    """Swallow yt-dlp console chatter; errors are surfaced in the UI instead."""
    def debug(self, msg):
        pass
    def info(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        pass


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class JobCancelled(Exception):
    pass


def validate_url(raw):
    url = (raw or "").strip()
    if not url:
        raise ApiError("empty", "Paste a video link first.")
    # tolerate share-text pastes: "Look at this https://vm.tiktok.com/x/ @user | TikTok"
    m = re.search(r"https?://\S+", url, re.I)
    if m:
        url = m.group(0)
    elif any(c.isspace() for c in url):
        url = url.split()[0]
    url = url.rstrip(").,;'\"\u2026")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        raise ApiError("invalid", "That doesn\u2019t look like a link.")
    if "." not in host:
        raise ApiError("invalid", "That doesn\u2019t look like a link.")
    source = next((n for rx, n in PLATFORMS if rx.search(host)), host.replace("www.", ""))
    url = resolve_short(url, host)
    return url, source


# ---- login cookies: private / member-only / age-restricted videos ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("VD_DATA_DIR") or BASE_DIR   # override for Docker: -v data:/app/data
os.makedirs(DATA_DIR, exist_ok=True)
COOKIE_FILE = os.path.join(DATA_DIR, "videodown_cookies.txt")
CONFIG_FILE = os.path.join(DATA_DIR, "videodown_config.json")
BROWSERS = ("chrome", "chromium", "firefox", "edge", "brave", "opera", "vivaldi", "safari")


def load_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def save_config(updates):
    cfg = load_config()
    cfg.update(updates)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except OSError:
        pass


def cookies_state():
    """Return (mode, browser): mode is 'file' | 'browser' | 'none'."""
    has_file = os.path.isfile(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 0
    browser = load_config().get("browser") or "none"
    if has_file:
        return "file", (browser if browser in BROWSERS else None)
    if browser in BROWSERS:
        return "browser", browser
    return "none", None


def cookie_opts():
    """yt-dlp cookie options — saved cookies.txt wins over browser session."""
    mode, browser = cookies_state()
    if mode == "file":
        return {"cookiefile": COOKIE_FILE}
    if mode == "browser":
        return {"cookiesfrombrowser": (browser, None, None, None)}
    return {}


def stable_hash(s):
    a = 7
    for ch in s:
        a = (a * 31 + ord(ch)) & 0xFFFFFFFF
    return a


SHORT_HOSTS = ("vt.tiktok.com", "vm.tiktok.com", "fb.watch")


def resolve_short(url, host):
    """Follow redirects on share short-links (vt.tiktok.com, fb.watch ...) so
    yt-dlp always receives the canonical video URL."""
    if host not in SHORT_HOSTS:
        return url
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=8) as r:
            final = r.geturl()
        if final and "://" in final:
            return final
    except Exception:
        pass
    return url


def is_transient(exc):
    """Errors worth retrying automatically (rate limits, bot checks, hiccups)."""
    s = str(exc).lower()
    return any(k in s for k in (
        "http error 429", "429: too many requests", "too many requests", "rate-limit", "rate limit",
        "http error 403", "403: forbidden", "forbidden", "captcha", "challenge",
        "http error 5", "service unavailable", "bad gateway", "internal server",
        "getaddrinfo", "timed out", "timeout", "connection refused", "network is unreachable",
        "urlopen", "temporary failure", "temporary error", "unable to extract", "empty media response",
    ))


def map_error(exc):
    s = str(exc).lower()
    if "unsupported url" in s:
        return ApiError("unsupported", "This site isn\u2019t supported yet.")
    if "cookie" in s and any(k in s for k in ("database", "keyring", "decrypt", "could not find", "cannot find", "unsupported browser")):
        return ApiError("analysis", "Could not read cookies from your browser. Export cookies.txt and paste it in Settings instead.")
    if any(k in s for k in ("sign in", "log in", "login", "logged-in", "log-in", "use --cookies", "cookies",
                            "members-only", "member-only", "join this channel",
                            "authentication", "not a bot", "confirm your age")):
        return ApiError("analysis", "This video needs your login. Add cookies in Settings (or videodown_cookies.txt next to videodown.py) and try again.")
    if any(k in s for k in ("private video", "private account", "age-restricted", "age restricted")):
        return ApiError("analysis", "This video is private \u2014 it downloads only with cookies of an account that can view it (Settings).")
    if "ffmpeg" in s or "ffprobe" in s:
        return ApiError("download", "FFmpeg is required for this format. Install ffmpeg and retry.")
    if any(k in s for k in ("http error 429", "429: too many requests", "too many requests",
                            "rate-limit", "rate limit")):
        return ApiError("network", "The platform is rate-limiting this link right now. Wait about a minute, then press Retry.")
    if any(k in s for k in ("http error 403", "403: forbidden", "forbidden", "captcha", "challenge")):
        return ApiError("network", "The platform blocked this request (bot check). Wait a minute and Retry \u2014 installing curl-cffi also helps.")
    if any(k in s for k in ("getaddrinfo", "timed out", "timeout", "connection refused",
                            "network is unreachable", "urlopen", "temporary failure",
                            "http error 5", "service unavailable", "bad gateway", "internal server",
                            "unable to extract", "empty media response")):
        return ApiError("network", "The platform didn\u2019t answer properly (temporary). Press Retry \u2014 it usually works on the second try.")
    if any(k in s for k in ("video unavailable", "not available", "removed", "deleted", "does not exist", "no video")):
        return ApiError("analysis", "We couldn\u2019t read that video. It may be private or removed.")
    return ApiError("analysis", "We couldn\u2019t read that video right now. Try again in a minute \u2014 if it keeps failing, it may be private or removed.")


def fmt_size_mb(f, duration):
    size = f.get("filesize") or f.get("filesize_approx") or 0
    if size:
        return size / MB
    tbr = f.get("tbr") or 0
    if tbr and duration:
        return (tbr / 8.0) * duration / 1024.0  # tbr is kb/s
    return 0.0


_HEAD_CACHE = {}
AUDIO_EXT = (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac")


def head_size_mb(url):
    """Quick Content-Length probe for direct file links (cached, best effort)."""
    if not url or url in _HEAD_CACHE:
        return _HEAD_CACHE.get(url, 0.0)
    val = 0.0
    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            cl = r.headers.get("Content-Length")
            if cl and cl.isdigit():
                val = int(cl) / MB
    except Exception:
        val = 0.0
    _HEAD_CACHE[url] = val
    return val


def normalize_formats(info):
    """Uniform view: every entry has usable vcodec/acodec/height semantics."""
    fmts = info.get("formats") or []
    if not fmts and info.get("url"):
        fmts = [info]
    out = []
    for raw in fmts:
        f = dict(raw)
        if not f.get("url"):
            continue
        url = f.get("url", "")
        if f.get("vcodec") in (None, "none") and f.get("acodec") in (None, "none"):
            if url.split("?")[0].lower().endswith(AUDIO_EXT):
                f["acodec"] = "unknown"          # direct audio file
            else:
                f["vcodec"] = "unknown"          # direct progressive file
                f["acodec"] = "unknown"
        if f.get("vcodec") not in (None, "none") and not f.get("height"):
            res = f.get("resolution") or ""
            if "x" in res:
                try:
                    f["height"] = int(res.split("x")[1])
                except ValueError:
                    pass
            if not f.get("height"):
                f["height"] = info.get("height") or 1080
        out.append(f)
    return out


def pick_video(fmts, height, duration):
    cands = [f for f in fmts
             if f.get("vcodec") not in (None, "none") and (f.get("height") or 0) <= height]
    if not cands:
        cands = [f for f in fmts if f.get("vcodec") not in (None, "none")]
    if not cands:
        return None
    return max(cands, key=lambda f: ((f.get("height") or 0), (f.get("tbr") or 0),
                                     fmt_size_mb(f, duration)))


def pick_audio(fmts, duration):
    pure = [f for f in fmts
            if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")]
    cands = pure or [f for f in fmts if f.get("acodec") not in (None, "none")]
    if not cands:
        return None
    return max(cands, key=lambda f: ((f.get("abr") or 0), (f.get("tbr") or 0),
                                     fmt_size_mb(f, duration)))


def build_formats(info, duration):
    fmts = normalize_formats(info)
    out = []
    for height in (1080, 720, 480):
        v = pick_video(fmts, height, duration)
        if not v:
            continue
        size = fmt_size_mb(v, duration)
        if v.get("acodec") in (None, "none"):
            a = pick_audio(fmts, duration)
            if a:
                size += fmt_size_mb(a, duration)
        if not size:
            size = head_size_mb(v.get("url"))
        if not size:
            size = (BITRATE_KBPS[height] / 8.0) * max(duration, 60) / 1024.0
        out.append({"id": "mp4-%dp" % height, "type": "mp4",
                    "label": "MP4 \u00b7 %dp" % height, "quality": "%dp" % height,
                    "size": round(size, 1)})
    if duration:
        mp3_size = (192 / 8.0) * duration / 1024.0
    else:
        a = pick_audio(fmts, 0) or pick_video(fmts, 9999, 0) or {}
        mp3_size = head_size_mb(a.get("url")) * 0.15 or 2.0
    out.append({"id": "mp3", "type": "mp3", "label": "MP3 \u00b7 audio",
                "quality": "192k", "size": round(mp3_size, 1)})
    return out


def selector_for(fmt_id, height):
    if FFMPEG:
        return "bestvideo[height<=%d]+bestaudio/best[height<=%d]/best" % (height, height)
    return ("best[height<=%d][vcodec!=none][acodec!=none]/best[height<=%d]/best"
            % (height, height))


def cleanup():
    now = time.time()
    with LOCK:
        dead = [jid for jid, j in JOBS.items() if now - j.get("created", now) > JOB_TTL]
        for jid in dead:
            j = JOBS.pop(jid)
            shutil.rmtree(j.get("dir") or "", ignore_errors=True)


def run_download(job, url, fmt_id):
    try:
        height = 1080
        m = re.search(r"mp4-(\d+)p", fmt_id or "")
        if m:
            height = int(m.group(1))

        opts = {
            "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
            "socket_timeout": 30, "retries": 2, "extractor_retries": 3, "logger": _QuietLogger(),
            "outtmpl": os.path.join(job["dir"], "%(title).120s [%(id)s].%(ext)s"),
        }
        opts.update(cookie_opts())

        def hook(d):
            if job.get("cancel"):
                raise JobCancelled()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                job["mb"] = done / MB
                if total:
                    job["total"] = total / MB
                    job["pct"] = min(99.0, done * 100.0 / total)
            elif d.get("status") == "finished":
                job["pct"] = 99.0

        opts["progress_hooks"] = [hook]

        if fmt_id == "mp3":
            if not FFMPEG:
                raise ApiError("download", "FFmpeg is required for MP3 conversion. Install ffmpeg and retry.")
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            opts["format"] = selector_for(fmt_id, height)
            if FFMPEG:
                opts["merge_output_format"] = "mp4"

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)

        files = [os.path.join(job["dir"], f) for f in os.listdir(job["dir"])]
        files = [f for f in files if os.path.isfile(f)]
        if fmt_id == "mp3":
            mp3s = [f for f in files if f.lower().endswith(".mp3")]
            if mp3s:
                files = mp3s
        if not files:
            raise ApiError("download", "Download interrupted.")
        best = max(files, key=os.path.getsize)
        job["path"] = best
        job["name"] = os.path.basename(best)
        job["pct"] = 100.0
        job["mb"] = os.path.getsize(best) / MB
        job["total"] = job["mb"]
        job["state"] = "done"
    except JobCancelled:
        job["state"] = "cancelled"
    except ApiError as e:
        job["state"] = "error"
        job["code"] = e.code
        job["error"] = e.message
    except Exception as e:  # yt_dlp.utils.DownloadError & friends
        err = map_error(e)
        job["state"] = "error"
        job["code"] = err.code
        job["error"] = err.message
    finally:
        job["finished"] = time.time()


@app.get("/")
def index():
    return Response(HTML, mimetype="text/html")


@app.post("/api/analyze")
def api_analyze():
    try:
        body = request.get_json(silent=True) or {}
        url, source = validate_url(body.get("url", ""))
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
                "skip_download": True, "socket_timeout": 30, "extractor_retries": 3, "logger": _QuietLogger()}
        opts.update(cookie_opts())
        info, last_exc = None, None
        t0 = time.time()
        for attempt in range(3):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                break
            except Exception as e:
                last_exc = e
                # keep the request short (hosting proxies cut off long requests)
                if attempt < 2 and is_transient(e) and (time.time() - t0) < 18:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        if info is None:
            raise last_exc
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise ApiError("analysis", "We couldn\u2019t read that video. It may be private or removed.")
            info = entries[0]
        duration = int(info.get("duration") or 0)
        hid = stable_hash(url)
        return jsonify(
            url=url,
            source=source,
            id=format(hid, "x"),
            title=(info.get("title") or "Untitled video"),
            hue=hid % 360,
            duration="%d:%02d" % (duration // 60, duration % 60),
            thumb=info.get("thumbnail"),
            formats=build_formats(info, duration),
        )
    except ApiError as e:
        return jsonify(error=e.message, code=e.code), 400
    except Exception as e:
        err = map_error(e)
        return jsonify(error=err.message, code=err.code), 400


@app.post("/api/download")
def api_download():
    try:
        cleanup()
        body = request.get_json(silent=True) or {}
        url, _ = validate_url(body.get("url", ""))
        fmt_id = body.get("fmt") or "mp4-1080p"
        if fmt_id not in VALID_FMTS:
            raise ApiError("download", "Unknown format.")
        job = {
            "id": uuid.uuid4().hex, "state": "running",
            "pct": 0.0, "mb": 0.0, "total": 0.0,
            "error": None, "code": None,
            "dir": tempfile.mkdtemp(prefix="videodown-"),
            "path": None, "name": None,
            "cancel": False, "created": time.time(),
        }
        with LOCK:
            JOBS[job["id"]] = job
        threading.Thread(target=run_download, args=(job, url, fmt_id), daemon=True).start()
        return jsonify(job=job["id"])
    except ApiError as e:
        return jsonify(error=e.message, code=e.code), 400


@app.get("/api/progress/<job_id>")
def api_progress(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify(error="Unknown job.", code="download"), 404
    return jsonify(
        state=job["state"], pct=round(job["pct"], 1),
        mb=round(job["mb"], 1), total=round(job["total"], 1),
        error=job["error"], code=job["code"],
    )


@app.post("/api/cancel/<job_id>")
def api_cancel(job_id):
    job = JOBS.get(job_id)
    if job:
        job["cancel"] = True
        if job["state"] == "running":
            job["state"] = "cancelled"
    return jsonify(ok=True)


@app.get("/api/file/<job_id>")
def api_file(job_id):
    job = JOBS.get(job_id)
    if not job or not job.get("path") or not os.path.isfile(job["path"]):
        return jsonify(error="File not found.", code="download"), 404
    return send_file(job["path"], as_attachment=True,
                     download_name=job.get("name") or "video.mp4")


@app.get("/api/settings")
def api_settings():
    mode, browser = cookies_state()
    return jsonify(cookies=mode, browser=browser)


@app.post("/api/cookies")
def api_cookies():
    body = request.get_json(silent=True) or {}
    if body.get("clear"):
        try:
            os.remove(COOKIE_FILE)
        except OSError:
            pass
        save_config({"browser": "none"})
        return jsonify(ok=True, cookies="none", browser=None)
    if "text" in body:
        text = (body.get("text") or "").strip()
        if not text:
            return jsonify(ok=False, error="Cookie text is empty."), 400
        try:
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError as e:
            return jsonify(ok=False, error="Could not save cookies: %s" % e), 500
        return jsonify(ok=True, cookies="file", browser=None)
    if "browser" in body:
        b = (body.get("browser") or "none").lower()
        if b != "none" and b not in BROWSERS:
            return jsonify(ok=False, error="Unknown browser."), 400
        save_config({"browser": b})
        mode, browser = cookies_state()
        return jsonify(ok=True, cookies=mode, browser=browser)
    return jsonify(ok=False, error="Nothing to do."), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print("VideoDown  \u2192  http://localhost:%d" % port)
    if not FFMPEG:
        print("WARNING: ffmpeg not found \u2014 MP3 conversion and HD stream merging are disabled.")
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        print("TIP: pip install curl-cffi  (improves TikTok / Instagram / Facebook reliability).")
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
