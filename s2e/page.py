"""The landing / upload page served by app.py."""
import html as _html
import os
import re

from .style import FONTS, BASE_CSS, MARK_SVG, IMPORTMAP, REVEAL_JS

_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sand to Earth</title>
<meta name="description" content="Shape a landscape with your hands, take one photo, and find where it already exists on Earth.">
<meta name="theme-color" content="#000000">
<meta property="og:type" content="website">
<meta property="og:title" content="Sand to Earth">
<meta property="og:description" content="Shape a landscape with your hands, take one photo, and find where it already exists on Earth.">
<meta property="og:image" content="https://tilakkumar13.github.io/sand2earth/og.png">
<meta property="og:url" content="https://tilakkumar13.github.io/sand2earth/">
<meta name="twitter:card" content="summary_large_image">
%%FONTS%%
<style>
%%CSS%%
/* ---------------- hero: sticky, scroll-scrubbed 3D ---------------- */
.hero { position: relative; height: 320vh; background: #000; }
.hero .stick { position: sticky; top: 0; height: 100vh; height: 100svh; overflow: hidden; }
#terrain { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.hero .glow { position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(60% 45% at 50% 62%, rgba(227, 193, 147, .16), transparent 70%); transition: opacity .6s; }
.hero.no-gl .glow { background: radial-gradient(50% 40% at 50% 60%, rgba(227,193,147,.35), rgba(90,164,105,.18) 45%, transparent 75%); }
.hero .copy { position: absolute; inset: 0; display: grid; place-items: start center; text-align: center;
  padding-top: calc(var(--nav-h) + 9vh); pointer-events: none; }
.hero .layer { grid-area: 1 / 1; will-change: opacity, transform; }
.hero h1 { font-size: clamp(56px, 10vw, 128px); line-height: 1; font-weight: 700; letter-spacing: -0.03em; margin: 0; }
.hero .sub { margin: 18px auto 0; max-width: 20em; font-size: clamp(21px, 2.4vw, 28px); line-height: 1.25; font-weight: 600;
  letter-spacing: -0.01em; color: var(--on-dark); }
.hero .beat { font-size: clamp(44px, 7.4vw, 96px); line-height: 1.02; font-weight: 700; letter-spacing: -0.03em; color: #fff; margin: 0; }
.hero .beat small { display: block; margin-top: 16px; font-size: clamp(17px, 1.7vw, 21px); line-height: 1.4; font-weight: 500;
  letter-spacing: -0.01em; color: var(--on-dark-2); max-width: 26em; margin-inline: auto; }
.hero .cta { display: flex; justify-content: center; gap: 14px; margin-top: 30px; pointer-events: auto; }
.hero .cue { position: absolute; left: 50%; bottom: 2.2vh; transform: translateX(-50%); color: var(--on-dark-2); font-size: 12px;
  letter-spacing: 0; transition: opacity .3s; }
.hero .cue::after { content: ""; display: block; width: 1px; height: 22px; margin: 6px auto 0; background: linear-gradient(var(--on-dark-2), transparent);
  animation: cue 1.8s var(--ease) infinite; }
@keyframes cue { 0% { transform: scaleY(0); transform-origin: top; } 50% { transform: scaleY(1); transform-origin: top; }
  51% { transform-origin: bottom; } 100% { transform: scaleY(0); transform-origin: bottom; } }
.legend { position: absolute; right: 22px; bottom: 2.2vh; display: flex; gap: 8px; align-items: center; font-size: 12px; color: var(--on-dark-2); }
.legend i { width: 64px; height: 4px; border-radius: 2px; background: #333; overflow: hidden; position: relative; }
.legend i b { position: absolute; inset: 0; transform-origin: left; transform: scaleX(0); background: var(--grad); }

/* ---------------- intro statement ---------------- */
.statement { padding: 150px 0 140px; }
.statement p { font-size: clamp(28px, 3.6vw, 48px); line-height: 1.14; font-weight: 700; letter-spacing: -0.01em; margin: 0;
  color: var(--ink-3); max-width: 20em; }
.statement p strong { color: var(--ink); font-weight: 700; }

/* ---------------- how it works ---------------- */
.how { padding: 120px 0 130px; }
.how .head { text-align: center; margin-bottom: 64px; }
.how .head .lede { margin: 16px auto 0; max-width: 30em; }
.steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; list-style: none; padding: 0; margin: 0; counter-reset: s; }
.steps li { background: var(--white); border-radius: var(--r-l); padding: 40px 34px 44px; min-height: 400px; display: flex; flex-direction: column; }
.steps .art { height: 150px; display: grid; place-items: center; margin-bottom: 26px; }
.steps .art svg { width: 150px; height: 120px; }
.steps .n { font-size: 15px; font-weight: 600; color: var(--ink-3); margin: 0 0 6px; }
.steps h3 { font-size: 32px; line-height: 1.12; letter-spacing: 0.004em; font-weight: 700; margin: 0 0 12px; }
.steps p { margin: 0; color: var(--ink-2); font-size: 17px; }

/* ---------------- numbers ---------------- */
.stats { padding: 140px 0 130px; }
.stats .head { text-align: center; margin-bottom: 80px; }
.stats .head .lede { margin: 18px auto 0; max-width: 28em; }
.grid4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 46px 30px; }
.stat .big { display: block; font-size: clamp(56px, 6.4vw, 84px); line-height: 1; font-weight: 700; letter-spacing: -0.02em; }
.stat p { margin: 14px 0 0; color: var(--on-dark-2); font-size: 17px; line-height: 1.4; max-width: 15em; }
.stats .note { margin: 70px auto 0; text-align: center; color: #6e6e73; font-size: 14px; max-width: 46em; }

/* ---------------- try it ---------------- */
.try { padding: 130px 0 140px; }
.try .head { text-align: center; margin-bottom: 50px; }
.try .head .lede { margin: 14px auto 0; }
.card { max-width: 720px; margin: 0 auto; background: var(--white); border-radius: var(--r-l); padding: 34px;
  box-shadow: 0 30px 80px -40px rgba(0,0,0,.25); }
#drop { position: relative; border-radius: var(--r-m); background: var(--light); min-height: 300px; display: grid; place-items: center;
  text-align: center; padding: 26px; cursor: pointer; transition: background .25s var(--ease), box-shadow .25s var(--ease); }
#drop:hover { background: #ededf0; }
#drop.over { background: #e8f1fc; box-shadow: inset 0 0 0 2px var(--blue); }
#drop .icon { width: 64px; height: 64px; margin: 0 auto 16px; color: var(--ink-3); }
#drop .t { font-size: 21px; font-weight: 600; letter-spacing: 0.01em; margin: 0; }
#drop .s { color: var(--ink-2); margin: 6px 0 20px; }
#drop .pick { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
#preview { display: none; width: 100%; }
#preview .ph { position: relative; width: min(100%, 340px); aspect-ratio: 1; margin: 0 auto; border-radius: var(--r-m); overflow: hidden;
  box-shadow: 0 20px 50px -25px rgba(0,0,0,.45); }
#preview img { width: 100%; height: 100%; object-fit: cover; }
#preview .meta { display: flex; justify-content: center; gap: 14px; align-items: baseline; margin-top: 16px; color: var(--ink-2); font-size: 15px; }
#preview .meta span { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.linkish { background: none; border: 0; font: inherit; color: var(--blue); cursor: pointer; padding: 0; }
.linkish:hover { text-decoration: underline; }
input[type=file] { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.opts { margin: 26px 0 28px; border-top: 1px solid var(--line); }
.opt { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding: 16px 2px; border-bottom: 1px solid var(--line); cursor: pointer; }
.opt span b { display: block; font-weight: 500; }
.opt span small { display: block; color: var(--ink-2); font-size: 14px; margin-top: 2px; }
.switch { appearance: none; -webkit-appearance: none; flex: none; width: 51px; height: 31px; border-radius: 31px; background: #e9e9eb;
  position: relative; cursor: pointer; transition: background .25s var(--ease); margin: 0; }
.switch::after { content: ""; position: absolute; top: 2px; left: 2px; width: 27px; height: 27px; border-radius: 50%; background: #fff;
  box-shadow: 0 3px 8px rgba(0,0,0,.15), 0 1px 1px rgba(0,0,0,.16); transition: transform .25s var(--ease); }
.switch:checked { background: #34c759; }
.switch:checked::after { transform: translateX(20px); }
#go { width: 100%; padding: 17px; font-size: 17px; }
#progress { display: none; list-style: none; margin: 22px 0 0; padding: 0; }
#progress li { display: flex; gap: 12px; align-items: center; padding: 7px 0; color: var(--ink-3); transition: color .3s; }
#progress li i { position: relative; width: 18px; height: 18px; border-radius: 50%; border: 2px solid #d2d2d7; flex: none; }
#progress li.on { color: var(--ink); }
#progress li.on i { border-color: var(--blue); border-right-color: transparent; animation: spin .8s linear infinite; }
#progress li.done { color: var(--ink-2); }
#progress li.done i { border-color: #34c759; background: #34c759; }
#progress li.done i::after { content: ""; position: absolute; left: 5px; top: 2px; width: 4px; height: 8px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
@keyframes spin { to { transform: rotate(360deg); } }
#error { display: none; margin: 16px 0 0; color: #d70015; text-align: center; }
.tips { display: flex; justify-content: center; gap: 28px; flex-wrap: wrap; margin: 30px auto 0; color: var(--ink-2); font-size: 14px; }
.tips span::before { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--ink-3); margin-right: 8px; vertical-align: 2px; }

/* ---------------- about ---------------- */
.about { padding: 130px 0 120px; }
.about .head { margin-bottom: 50px; }
.about .head .lede { margin: 14px 0 0; max-width: 32em; }
.tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.tile { background: var(--light); border-radius: var(--r-l); padding: 40px 40px 36px; }
.tile.span { grid-column: 1 / -1; }
.tile h3 { font-size: 28px; line-height: 1.14; font-weight: 700; letter-spacing: 0.007em; margin: 0 0 14px; }
.tile p { margin: 0 0 12px; color: var(--ink-2); }
.tile p strong { color: var(--ink); font-weight: 600; }
.tile ul { margin: 0; padding: 0; list-style: none; columns: 2; column-gap: 40px; }
.tile li { break-inside: avoid; padding: 10px 0; border-top: 1px solid var(--line); color: var(--ink-2); font-size: 15px; }
.tile li b { display: block; color: var(--ink); font-weight: 600; font-size: 16px; }
/*maker*/
.maker { display: flex; align-items: center; gap: 28px; max-width: 760px; margin: 64px auto 0; padding: 30px 36px;
  background: var(--light); border-radius: var(--r-l); }
.maker img { width: 104px; height: 104px; border-radius: 50%; object-fit: cover; flex: none; }
.maker p { margin: 0; }
.maker .by { color: var(--ink-3); font-size: 15px; }
.maker .nm { font-size: 30px; line-height: 1.15; font-weight: 700; letter-spacing: -0.01em; color: var(--ink); }
.maker .rl { color: var(--ink-2); font-size: 16px; margin-top: 4px; }
.maker .lk { display: flex; gap: 22px; flex-wrap: wrap; margin-top: 10px; font-size: 16px; }
@media (max-width: 734px) { .maker { flex-direction: column; text-align: center; padding: 28px 22px; } .maker .lk { justify-content: center; } }
/*/maker*/

@media (max-width: 1068px) { .grid4 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 734px) {
  .statement { padding: 90px 0; }
  .how, .stats, .try, .about { padding: 90px 0; }
  .steps { grid-template-columns: 1fr; }
  .steps li { min-height: 0; }
  .grid4 { grid-template-columns: 1fr 1fr; gap: 36px 18px; }
  .card { padding: 20px; border-radius: 22px; }
  .tiles { grid-template-columns: 1fr; }
  .tile { padding: 30px 24px; }
  .tile ul { columns: 1; }
  .legend { display: none; }
}
</style></head>
<body>
<nav class="gnav" aria-label="Sand to Earth">
  <div class="in">
    <a class="brand" href="#top">%%MARK%%Sand to Earth</a>
    <div class="links">
      <a href="#how">How it works</a><a href="#numbers">Accuracy</a><a href="#about">About</a>
      %%OTHERPLANET%%<a class="pill small" href="#try">Try it</a>
    </div>
  </div>
</nav>

<section class="hero dark" id="top" aria-label="Introduction">
  <div class="stick">
    <canvas id="terrain" aria-hidden="true"></canvas>
    <div class="glow"></div>
    <div class="copy">
      <div class="layer" data-in="0" data-out=".16">
        <h1 class="grad">Sand to Earth.</h1>
        <p class="sub">Shape a landscape with your hands. Find where it already exists.</p>
        <div class="cta"><a class="pill" href="#try">Try it with a photo</a><a class="pill ghost" href="#how">How it works</a></div>
      </div>
      <div class="layer" data-in=".2" data-out=".42"><p class="beat">Sculpt it.<small>Press ridges, valleys and peaks into sand or clay.</small></p></div>
      <div class="layer" data-in=".46" data-out=".66"><p class="beat">Photograph it.<small>One photo from above becomes a height map, right on your Mac.</small></p></div>
      <div class="layer" data-in=".7" data-out="1.1"><p class="beat">Find it on Earth.<small>%%HEROCAP%%</small></p></div>
    </div>
    <div class="cue" aria-hidden="true">Scroll</div>
    <div class="legend" aria-hidden="true">Sand <i><b id="mixbar"></b></i> Earth</div>
  </div>
</section>

<section class="statement">
  <div class="wrap">
    <p class="reveal">Landforms repeat. The same uplift, erosion and rivers carve the same shapes on every continent.
      <strong>So the ridge you press into clay on a café table very likely exists somewhere, at full size.</strong></p>
  </div>
</section>

<section class="how light" id="how">
  <div class="wide">
    <div class="head reveal">
      <h2 class="section-title">How it works.</h2>
      <p class="lede">Three steps from a handful of sand to a real place on the map.</p>
    </div>
    <ol class="steps">
      <li class="reveal">
        <div class="art"><svg viewBox="0 0 150 120" fill="none" stroke-linecap="round" aria-hidden="true">
          <ellipse cx="75" cy="92" rx="66" ry="18" fill="#efe4d3"/>
          <path d="M14 92c14-2 18-30 38-34s24 16 36 12 18-26 32-22 14 30 18 44" fill="#e3c193"/>
          <path d="M30 88c8-2 12-18 24-20s14 8 22 6" stroke="#c9a473" stroke-width="2"/>
          <path d="M82 84c6-2 10-14 20-14s10 8 16 8" stroke="#c9a473" stroke-width="2"/></svg></div>
        <p class="n">Step 1</p><h3>Sculpt.</h3>
        <p>Press hills, ridges and valleys into sand or modelling clay. Big, clear shapes work best.</p>
      </li>
      <li class="reveal">
        <div class="art"><svg viewBox="0 0 150 120" fill="none" stroke-linecap="round" aria-hidden="true">
          <rect x="45" y="6" width="60" height="104" rx="12" fill="#1d1d1f"/>
          <rect x="50" y="18" width="50" height="80" rx="4" fill="#3a3a3c"/>
          <path d="M52 86c8-2 10-18 22-20s14 10 24 6v24H52z" fill="#e3c193"/>
          <circle cx="75" cy="12" r="2.2" fill="#3a3a3c"/>
          <path d="M60 52l15 10 15-10" stroke="#2997ff" stroke-width="2.4"/></svg></div>
        <p class="n">Step 2</p><h3>Photograph.</h3>
        <p>Take one photo from straight above. A depth model turns it into a height map on your Mac.</p>
      </li>
      <li class="reveal">
        <div class="art"><svg viewBox="0 0 150 120" fill="none" aria-hidden="true">
          <defs><radialGradient id="gl" cx="38%" cy="32%"><stop offset="0" stop-color="#7fc4ff"/><stop offset="1" stop-color="#0b4a8f"/></radialGradient></defs>
          <circle cx="75" cy="60" r="50" fill="url(#gl)"/>
          <path d="M42 40c10-6 22 2 26 10s-4 14-12 16-16 10-20 0-4-20 6-26zM84 30c10-4 26 4 30 16s-6 18-14 16-8 10-16 6-12-16-8-24 2-12 8-14z" fill="#6aa86f"/>
          <path d="M70 84c8-2 16 2 18 8s-8 10-16 8-10-14-2-16z" fill="#c9a473"/>
          <circle cx="98" cy="48" r="7" fill="none" stroke="#fff" stroke-width="2.4"/><circle cx="98" cy="48" r="2" fill="#fff"/></svg></div>
        <p class="n">Step 3</p><h3>Found.</h3>
        <p>Your shape is compared with %%COUNT%% real places, turned through every angle, and shown on satellite imagery and in 3D.</p>
      </li>
    </ol>
  </div>
</section>

<section class="stats dark" id="numbers">
  <div class="wide">
    <div class="head reveal">
      <h2 class="section-title">Tested, not just pretty.</h2>
      <p class="lede">We take real places, bend them into rough, rotated, blurry copies like a hand-made sculpture, and check whether the search traces each one back.</p>
    </div>
    <div class="grid4">
      <div class="stat reveal"><span class="big grad num">%%TOP1%%</span><p>of distorted copies traced back to the right place on the first try.</p></div>
      <div class="stat reveal"><span class="big grad num">%%COUNTBIG%%</span><p>stretches of real terrain, %%SIZES%% across.</p></div>
      <div class="stat reveal"><span class="big grad num">%%ROT%%</span><p>typical error in which way your sandbox faces.</p></div>
      <div class="stat reveal"><span class="big grad num">%%MS%%</span><p>per search, on a laptop.</p></div>
    </div>
    <p class="note reveal">%%STATNOTE%%</p>
  </div>
</section>

<section class="try light" id="try">
  <div class="wrap">
    <div class="head reveal">
      <h2 class="section-title">Try it.</h2>
      <p class="lede">Your photo stays on this computer.</p>
    </div>
    %%PLANETS%%<div class="card reveal">
      <div id="drop" tabindex="0" role="button" aria-label="Add a photo of your sculpture">
        <div id="empty">
          <svg class="icon" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="6" y="14" width="52" height="40" rx="8"/><path d="M6 46l14-12 10 8 10-12 18 16"/><circle cx="44" cy="26" r="4"/></svg>
          <p class="t">Drop a photo of your sculpture</p>
          <p class="s">JPG, PNG or HEIC, taken from straight above.</p>
          <div class="pick">
            <label class="pill">Choose photo<input id="pick" type="file" accept="image/*"></label>
            <label class="pill ghost">Use camera<input id="snap" type="file" accept="image/*" capture="environment"></label>
          </div>
        </div>
        <div id="preview">
          <div class="ph"><img id="pimg" alt="Your photo, cropped to the square that will be searched"></div>
          <div class="meta"><span id="pname"></span><button class="linkish" id="change" type="button">Change</button></div>
        </div>
      </div>
      <div class="opts">
        <label class="opt"><span><b>Swap hills and valleys</b><small>Turn this on if a result shows your peaks as pits.</small></span>
          <input class="switch" type="checkbox" id="invert"></label>
        <label class="opt"><span><b>Also check the mirror image</b><small>Helps when the camera flips the picture.</small></span>
          <input class="switch" type="checkbox" id="flip"></label>
      </div>
      <button class="pill" id="go" disabled>Find my place</button>
      <ol id="progress" aria-live="polite">
        <li><i></i>Reading depth from your photo</li>
        <li><i></i>Comparing it with <span id="nplaces">%%COUNT%%</span> places</li>
        <li><i></i>Turning the best ones to line them up</li>
      </ol>
      <p id="error" role="alert"></p>
      <p id="srv" aria-live="polite"></p>
    </div>
    <div class="tips reveal"><span>Soft, even light</span><span>Fill the frame</span><span>Matte clay beats wet sand</span></div>%%RUNLOCAL%%
  </div>
</section>

%%MARSTEASER%%<section class="about" id="about">
  <div class="wide">
    <div class="head reveal">
      <h2 class="section-title">About the project.</h2>
      <p class="lede">An experiment where GIS, computer vision and remote sensing meet: a physical sculpture goes in, a real place on the planet comes out.</p>
    </div>
    <div class="tiles">
      <div class="tile reveal">
        <h3>Why it exists.</h3>
        <p>Projected sandboxes can draw contour lines on sand, and tangible GIS tools can rebuild a known place in sand.
          None of them asks the reverse question: <strong>given a shape made by hand, where on Earth is it?</strong></p>
      </div>
      <div class="tile reveal">
        <h3>What's inside.</h3>
        <p>Depth Anything V2 reads the photo as a height map. %%MATCHER%% Every candidate is then turned through all
          angles and compared exactly, which also tells you which way your sandbox would face on the map.</p>
      </div>
      <div class="tile reveal">
        <h3>A fair map of the planet.</h3>
        <p>Web Mercator stretches the poles, so pixel-sized windows make Greenland win far too often. Here every window is
          measured in <strong>kilometres</strong>, giving every latitude the same chance.</p>
      </div>
      <div class="tile reveal">
        <h3>Where the data comes from.</h3>
        <p>Elevation from the open <a href="https://registry.opendata.aws/terrain-tiles/">AWS Terrain Tiles</a> (SRTM, ETOPO1 and
          national surveys). Imagery from <a href="https://s2maps.eu">Sentinel-2 cloudless</a> by EOX. Place names from OpenStreetMap.</p>
      </div>
      <div class="tile span reveal">
        <h3>Standing on the shoulders of.</h3>
        <ul>
          <li><b>Augmented Reality Sandbox</b>Kreylos, UC Davis. Depth camera and projected contours.</li>
          <li><b>Tangible Landscape</b>NC State. Sculpt sand to match a known place.</li>
          <li><b>Content-based landscape retrieval</b>Jasiewicz, Netzel and Stepinski, 2013.</li>
          <li><b>LSE Wisconsin</b>Haffner et al., 2023. Neural landscape search, regional.</li>
          <li><b>GEAR</b>2026. Siamese retrieval of terrain analogues.</li>
          <li><b>terravector</b>DEM patch similarity search.</li>
        </ul>
      </div>
    </div>
    <!--maker-->
    <div class="maker reveal">
      <img src="data:image/jpeg;base64,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" alt="Tilak Kumar" width="104" height="104">
      <div>
        <p class="by">Made by</p>
        <p class="nm">Tilak Kumar</p>
        <p class="rl">MSc Geospatial Technologies, Institute for Geoinformatics, University of Münster</p>
        <p class="lk"><a class="more" href="https://tilakkumar13.github.io/">Portfolio</a><a class="more" href="https://www.linkedin.com/in/tilak-kumar-726201262/">LinkedIn</a><a class="more" href="https://github.com/Tilakkumar13">GitHub</a></p>
      </div>
    </div>
    <!--/maker-->
  </div>
</section>

<footer class="foot"><div class="wrap">
  <p>Elevation: AWS Terrain Tiles (Mapzen / Tilezen). Imagery: Sentinel-2 cloudless 2016 by EOX IT Services GmbH, contains modified
    Copernicus Sentinel data, CC BY 4.0. Depth: Depth Anything V2. 3D: three.js.</p>
  <div class="rule"></div>
  <p>Sand to Earth, 2026. <a href="https://github.com/Tilakkumar13/sand2earth">Open source on GitHub</a>. Made by <a href="https://tilakkumar13.github.io/">Tilak Kumar</a>.</p>
</div></footer>

<script type="application/json" id="herodata">%%HERODATA%%</script>
%%IMPORTMAP%%
<script>
/* hero text + legend follow scroll; runs even without WebGL */
(() => {
  const hero = document.querySelector(".hero"), layers = [...hero.querySelectorAll(".layer")];
  const cue = hero.querySelector(".cue"), bar = document.getElementById("mixbar");
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  window.__heroP = 0;
  function frame() {
    const r = hero.getBoundingClientRect();
    const p = clamp(-r.top / (r.height - innerHeight), 0, 1);
    window.__heroP = p;
    for (const l of layers) {
      const a = +l.dataset.in, b = +l.dataset.out, fade = .07;
      let o = a === 0 ? 1 - clamp((p - (b - fade)) / fade, 0, 1)
                      : Math.min(clamp((p - a) / fade, 0, 1), 1 - clamp((p - (b - fade)) / fade, 0, 1));
      l.style.opacity = o;
      l.style.transform = `translateY(${(1 - o) * (p < a ? 24 : -24)}px) scale(${.97 + .03 * o})`;
      l.style.visibility = o < .02 ? "hidden" : "visible";
    }
    cue.style.opacity = clamp(1 - p / .05, 0, 1);
    bar.style.transform = `scaleX(${clamp((p - .3) / .5, 0, 1)})`;
  }
  addEventListener("scroll", () => requestAnimationFrame(frame), { passive: true });
  addEventListener("resize", frame); frame();
  setTimeout(() => { if (!window.__terrainReady) hero.classList.add("no-gl"); }, 5000);
})();
</script>
<script type="module">
/* A sand sculpture that turns into real-looking mountains as you scroll. */
import * as THREE from "three";
const canvas = document.getElementById("terrain");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
let renderer;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" }); }
catch (e) { document.querySelector(".hero").classList.add("no-gl"); throw e; }
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
const scene = new THREE.Scene();
const cam = new THREE.PerspectiveCamera(30, 1, .1, 50);
scene.add(new THREE.HemisphereLight(0xfff4e6, 0x20242a, 1.1));
const key = new THREE.DirectionalLight(0xffffff, 2.6); key.position.set(-2.5, 3, -1.5); scene.add(key);
const rim = new THREE.DirectionalLight(0x8fb8ff, .8); rim.position.set(2.5, 1.2, 2.5); scene.add(rim);

// ---------- height field (deterministic) ----------
const HERO = JSON.parse(document.getElementById("herodata").textContent);
const PLANET = %%PLANET%%;
const marsRamp = ["#3a1a12", "#6e2f1c", "#a84a26", "#cf7a45", "#e9b07c", "#f6dcc0"].map(c => new THREE.Color(c));
const N = HERO ? HERO.n : 170, R = 1;
function hash(x, y) { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s); }
function vnoise(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
function ridged(x, y, oct) { let s = 0, amp = .5, f = 1; for (let i = 0; i < oct; i++) { s += amp * (1 - Math.abs(2 * vnoise(x * f, y * f) - 1)) ** 2; amp *= .5; f *= 2.03; } return s; }
const bumps = [[-.35, -.2, .55, .34], [.3, .25, .5, .28], [.05, -.5, .3, .2], [-.45, .45, .2, .22], [.55, -.35, .22, .2], [-.05, .1, .18, -.14]];
const g = new THREE.PlaneGeometry(2 * R, 2 * R, N - 1, N - 1); g.rotateX(-Math.PI / 2);
const pos = g.attributes.position, n = pos.count;
const hs = new Float32Array(n), he = new Float32Array(n), cs = new Float32Array(n * 3), ce = new Float32Array(n * 3);
const sand = [new THREE.Color("#b88d5f"), new THREE.Color("#d9b384"), new THREE.Color("#efd9b6")];
const earth = [new THREE.Color("#2f5a33"), new THREE.Color("#5f7f3e"), new THREE.Color("#8a7350"), new THREE.Color("#8d8a86"), new THREE.Color("#f4f6f8")];
function ramp(stops, t) { t = Math.min(.999, Math.max(0, t)) * (stops.length - 1); const i = Math.floor(t); return stops[i].clone().lerp(stops[i + 1], t - i); }
let lo = 1e9, hi = -1e9;
// Real place: the earth state is the true elevation, the sand state is the same place smoothed,
// which is what a hand-made sculpture of it would look like. Vertex i is row-major from the north edge.
let rLo = 1e9, rHi = -1e9;
if (HERO) for (const v of HERO.real) { rLo = Math.min(rLo, v); rHi = Math.max(rHi, v); }
const metresColor = [[0, "#3c6a3b"], [1200, "#6c8a45"], [2600, "#8a7350"], [4200, "#8f8b86"], [5200, "#e9edf0"], [6500, "#ffffff"]].map(([m, c]) => [m, new THREE.Color(c)]);
function colorAtMetres(m) {
  for (let k = 1; k < metresColor.length; k++) if (m <= metresColor[k][0]) {
    const [m0, c0] = metresColor[k - 1], [m1, c1] = metresColor[k];
    return c0.clone().lerp(c1, Math.max(0, (m - m0) / (m1 - m0)));
  }
  return metresColor[metresColor.length - 1][1].clone();
}
for (let i = 0; i < n; i++) {
  const x = pos.getX(i), z = pos.getZ(i), r = Math.hypot(x, z);
  const edge = Math.max(0, 1 - Math.max(0, r - .78) / .22);
  if (HERO) {
    const grain = .006 * (vnoise(x * 70, z * 70) - .5) + .01 * (vnoise(x * 18 + 3, z * 18) - .5);
    he[i] = (HERO.real[i] - rLo) / (rHi - rLo) * .46 * edge;
    hs[i] = ((HERO.sand[i] - rLo) / (rHi - rLo) * .42 + grain) * edge;
    lo = Math.min(lo, he[i]); hi = Math.max(hi, he[i]);
    continue;
  }
  let h = 0; for (const [bx, bz, s, a] of bumps) h += a * Math.exp(-((x - bx) ** 2 + (z - bz) ** 2) / (2 * s * s * .35));
  h += .05 * Math.sin(x * 3.1 + z * 1.7);
  const grain = .007 * (vnoise(x * 70, z * 70) - .5) + .012 * (vnoise(x * 18 + 3, z * 18) - .5);   // hand-pressed sand
  hs[i] = (h + grain) * edge;
  he[i] = (h + .26 * (ridged(x * 2.6 + 4, z * 2.6 + 9, 6) - .35) * (.35 + h)) * edge;
  lo = Math.min(lo, he[i]); hi = Math.max(hi, he[i]);
}
for (let i = 0; i < n; i++) {
  const t = (he[i] - lo) / (hi - lo);
  const sc = ramp(sand, (hs[i] - lo) / (hi - lo) * .9 + .05), j = .94 + .1 * hash(i * .37, i * .11);
  sc.multiplyScalar(j).toArray(cs, i * 3);
  (PLANET === "mars" ? ramp(marsRamp, HERO ? (HERO.real[i] - rLo) / (rHi - rLo) : t)
    : HERO ? colorAtMetres(HERO.real[i]) : ramp(earth, t * t * .9 + t * .1)).toArray(ce, i * 3);
}
g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
const am = document.createElement("canvas"); am.width = am.height = 256;
const ac = am.getContext("2d"); ac.fillStyle = "#000"; ac.fillRect(0, 0, 256, 256); ac.fillStyle = "#fff";
ac.beginPath(); ac.arc(128, 128, 127, 0, Math.PI * 2); ac.fill();
const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .92, metalness: 0, alphaMap: new THREE.CanvasTexture(am), alphaTest: .5 });
const land = new THREE.Mesh(g, mat); scene.add(land);
const base = new THREE.Mesh(new THREE.CylinderGeometry(R, R * .985, .12, 160, 1, true),
  new THREE.MeshStandardMaterial({ color: 0x1c1c1e, roughness: .6, metalness: .2, side: THREE.DoubleSide }));
base.position.y = -.06; scene.add(base);
const shadow = new THREE.Mesh(new THREE.CircleGeometry(1.35, 64), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: .55 }));
shadow.rotation.x = -Math.PI / 2; shadow.position.y = -.13; scene.add(shadow);
const S0 = .5, S1 = .78;
let lastMix = -1;
function morph(m) {
  if (Math.abs(m - lastMix) < .002) return; lastMix = m;
  const col = g.attributes.color.array;
  const k = m * m * (3 - 2 * m);
  for (let i = 0; i < n; i++) {
    pos.setY(i, (hs[i] + (he[i] - hs[i]) * k) * (S0 + (S1 - S0) * k));
    col[i * 3] = cs[i * 3] + (ce[i * 3] - cs[i * 3]) * k;
    col[i * 3 + 1] = cs[i * 3 + 1] + (ce[i * 3 + 1] - cs[i * 3 + 1]) * k;
    col[i * 3 + 2] = cs[i * 3 + 2] + (ce[i * 3 + 2] - cs[i * 3 + 2]) * k;
  }
  pos.needsUpdate = true; g.attributes.color.needsUpdate = true; g.computeVertexNormals();
}
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix();
}
addEventListener("resize", resize); resize();
let visible = true;
new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(canvas);
let sp = 0;
const t0 = performance.now();
renderer.setAnimationLoop(() => {
  if (!visible) return;
  const p = window.__heroP || 0;
  sp += (p - sp) * .12;                                     // smooth the scroll a little
  morph(Math.min(1, Math.max(0, (sp - .3) / .5)));
  const t = reduce ? 0 : (performance.now() - t0) / 1000;
  const az = -.6 + sp * 1.6 + t * .04;
  const pol = .27 + .14 * Math.min(1, sp * 1.4);            // from high above to a low, cinematic angle
  const narrow = cam.aspect < .8;
  const dist = (narrow ? 9.8 : 5.8) - sp * .6;
  cam.position.set(Math.sin(az) * Math.sin(pol * Math.PI) * dist, Math.cos(pol * Math.PI) * dist, Math.cos(az) * Math.sin(pol * Math.PI) * dist);
  cam.lookAt(0, narrow ? .75 : .62, 0);                   // aim above the model so it sits low, under the words
  renderer.render(scene, cam);
});
window.__terrainReady = true;
</script>

<script>
/* ---------- upload ---------- */
(() => {
  const $ = id => document.getElementById(id);
  if (!$("drop")) return;                                  // static showcase: no upload box
  const ENGINE = %%ENGINE%%;                               // "" = the local app does the search; else the in-browser engine folder
  const PLANETS = %%PLANET_DATA%%;                         // planet -> folder with its index (in-browser search)
  let planet = %%PLANET%%;
  const engines = {}, warms = {};
  const drop = $("drop"), go = $("go"), err = $("error"), prog = $("progress"), srv = $("srv");
  let file = null, timers = [], eng = null, rep = null, warming = null;
  document.querySelectorAll("[data-planet]").forEach(b => b.addEventListener("click", () => {
    planet = b.dataset.planet;
    document.querySelectorAll("[data-planet]").forEach(x => x.setAttribute("aria-pressed", x === b ? "true" : "false"));
    document.documentElement.dataset.planet = planet;
    eng = engines[planet] || null; warming = warms[planet] || null; srv.textContent = "";
    if (file) warm();
  }));
  function showError(msg) { err.textContent = msg; err.style.display = msg ? "block" : "none"; }

  // In-browser search: fetch the engine, the terrain index and the depth model once (cached afterwards).
  function warm() {
    if (!ENGINE) return Promise.resolve();
    if (warming) return warming;
    srv.textContent = "Getting the search ready…";
    warming = (async () => {
      const [E, R] = await Promise.all([import(ENGINE + "engine.js"), import(ENGINE + "report.js")]);
      rep = R; eng = engines[planet] = new E.Engine(PLANETS[planet] || ENGINE);
      let got = 0; const depthFiles = new Map();
      const show = () => {
        const total = (eng.info ? eng.info.bytes : 45e6) + Math.max([...depthFiles.values()].reduce((a, b) => a + b, 0), 27e6);
        srv.textContent = `Downloading the search data, only the first time: ${Math.min(99, Math.round(got / total * 100))}%`;
      };
      await Promise.all([
        eng.load((kind, n) => { got += n; show(); }),
        eng.loadDepth((kind, n, total, name) => { got += n; depthFiles.set(name, total); show(); }),
      ]);
      $("nplaces").textContent = eng.info.count.toLocaleString("en");
      srv.textContent = planet === "mars" ? "Ready to search Mars. Expect less accuracy than on Earth: the matcher learned on Earth terrain and finds the right Mars place first in about half of tests."
                                          : "Ready. The search runs on this device; your photo is never uploaded.";
    })();
    warms[planet] = warming;
    warming.catch(e => { warming = null; warms[planet] = null; srv.textContent = ""; showError("The search couldn't load (" + e.message + "). Check your connection and try again."); });
    return warming;
  }
  async function browserSearch() {
    let bmp;
    try { bmp = await createImageBitmap(file, { imageOrientation: "from-image" }); }
    catch (e) { throw new Error("This browser can't read that photo. Try a JPG or PNG (iPhone: Settings › Camera › Formats › Most Compatible)."); }
    const s = Math.min(bmp.width, bmp.height), side = Math.min(s, 1024);
    const sq = document.createElement("canvas"); sq.width = sq.height = side;
    sq.getContext("2d").drawImage(bmp, (bmp.width - s) / 2, (bmp.height - s) / 2, s, s, 0, 0, side, side);
    await warm();
    stage(0);
    const dc = document.createElement("canvas"); dc.width = dc.height = 518;
    const g = dc.getContext("2d"); g.imageSmoothingQuality = "high"; g.drawImage(sq, 0, 0, 518, 518);
    const h = await eng.heightFromCanvas(dc, $("invert").checked);
    stage(1);
    const { query, results } = await eng.search(h, { allowFlip: $("flip").checked, onStage: stage });
    const parts = await (await fetch(ENGINE + "report.json")).json();
    const html = await rep.buildReport(eng, parts, { query, results, photo: sq, home: location.href.split("#")[0] });
    stage(3);
    showReport(html);
  }
  // The results page opens over this one (works in every browser, including in-app ones); Back closes it.
  function showReport(html) {
    const f = document.createElement("iframe");
    f.id = "report"; f.title = "Your result";
    f.srcdoc = html.replace("<head>", '<head><base target="_top">');
    document.body.appendChild(f); document.documentElement.classList.add("has-report");
    history.pushState({ report: 1 }, "", "#result");
    go.textContent = "Find my place"; go.disabled = false; prog.style.display = "none";
  }
  function closeReport() {
    const f = document.getElementById("report");
    if (f) { f.remove(); document.documentElement.classList.remove("has-report"); }
  }
  addEventListener("popstate", () => { if (location.hash !== "#result") closeReport(); });
  addEventListener("hashchange", () => { if (location.hash !== "#result") closeReport(); });

  // "Use camera": phones open their own camera app; computers get a live preview here.
  const phone = /Android|iPhone|iPad|iPod|Mobi/i.test(navigator.userAgent) || (navigator.maxTouchPoints > 1 && /Mac/.test(navigator.userAgent));
  if (!phone && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    $("snap").closest("label").addEventListener("click", e => { e.preventDefault(); openCamera(); });
  }
  async function openCamera() {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
    } catch (e) {
      return showError(e.name === "NotAllowedError" ? "Camera access was blocked. Allow it in the address bar, or choose a photo instead."
                                                    : "No camera found. Choose a photo instead.");
    }
    showError("");
    const ov = document.createElement("div"); ov.className = "cam"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-label", "Camera");
    ov.innerHTML = '<div class="cambox"><div class="camview"><video playsinline autoplay muted></video><i></i></div>' +
      '<p>Hold the camera straight above your sculpture and fill the square.</p>' +
      '<div class="camctl"><button class="pill ghost" type="button" data-x>Cancel</button><button class="pill" type="button" data-shot>Take photo</button></div></div>';
    document.body.appendChild(ov);
    const v = ov.querySelector("video"); v.srcObject = stream;
    const close = () => { stream.getTracks().forEach(t => t.stop()); ov.remove(); removeEventListener("keydown", esc); };
    const esc = e => { if (e.key === "Escape") close(); };
    addEventListener("keydown", esc);
    ov.querySelector("[data-x]").onclick = close;
    ov.addEventListener("click", e => { if (e.target === ov) close(); });
    ov.querySelector("[data-shot]").onclick = () => {
      if (!v.videoWidth) return;
      const s = Math.min(v.videoWidth, v.videoHeight), c = document.createElement("canvas");
      c.width = c.height = s;                                  // the square you saw is the square that is searched
      c.getContext("2d").drawImage(v, (v.videoWidth - s) / 2, (v.videoHeight - s) / 2, s, s, 0, 0, s, s);
      c.toBlob(b => { close(); setFile(new File([b], "camera.jpg", { type: "image/jpeg" })); }, "image/jpeg", 0.92);
    };
    ov.querySelector("[data-shot]").focus();
  }

  function setFile(f) {
    if (!f) return;
    if (!f.type.startsWith("image/") && !/\.hei[cf]$/i.test(f.name)) return showError("That file isn't an image. Choose a JPG, PNG or HEIC photo.");
    file = f; showError("");
    $("pimg").src = URL.createObjectURL(f); $("pname").textContent = f.name;
    $("empty").style.display = "none"; $("preview").style.display = "block"; go.disabled = false;
    warm();
  }
  $("pick").onchange = e => setFile(e.target.files[0]);
  $("snap").onchange = e => setFile(e.target.files[0]);
  $("change").onclick = e => { e.stopPropagation(); $("pick").click(); };
  drop.addEventListener("click", e => { if (!file && e.target === drop) $("pick").click(); });
  drop.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("pick").click(); } });
  ["dragenter", "dragover"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => setFile(e.dataTransfer.files[0]));
  function stage(k) { [...prog.children].forEach((li, i) => { li.className = i < k ? "done" : i === k ? "on" : ""; }); }
  go.onclick = async () => {
    if (!file) return;
    go.disabled = true; go.textContent = "Searching"; showError(""); prog.style.display = "block";
    try {
      if (ENGINE) {
        if (!warming || srv.textContent.startsWith("Downloading")) stage(-1);
        await browserSearch();
        return;
      }
      stage(0);
      timers = [setTimeout(() => stage(1), 1800), setTimeout(() => stage(2), 3200)];
      const q = new URLSearchParams({ invert: +$("invert").checked, flip: +$("flip").checked });
      const r = await fetch("/search?" + q, { method: "POST", body: file, headers: { "Content-Type": "application/octet-stream" } });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || "The search stopped unexpectedly. Check the terminal for details.");
      timers.forEach(clearTimeout); stage(3);
      location.href = j.report;
    } catch (e) {
      timers.forEach(clearTimeout); prog.style.display = "none"; go.textContent = "Find my place";
      const lost = !ENGINE && (e instanceof TypeError || e.message === "Failed to fetch");
      showError(lost ? "Can't reach the app. Is app.py still running in the terminal?" : e.message);
      go.disabled = false;
    }
  };
  addEventListener("pageshow", () => { go.textContent = "Find my place"; go.disabled = !file; prog.style.display = "none"; });
})();
</script>
%%REVEAL%%
</body></html>
"""


def _join(km):
    parts = [f"{k:,.0f}" for k in km]
    if len(parts) == 1:
        return parts[0] + " km"
    return parts[0] + " to " + parts[-1] + " km"


def read_mars_results(path="docs/results.md"):
    """The 'placed anywhere' row of the Mars table in docs/results.md."""
    if not os.path.exists(path):
        return None
    text = open(path).read()
    if "## Mars" not in text:
        return None
    for line in text.split("## Mars", 1)[1].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[1] == "placed anywhere":
            n = re.search(r"(\d+) crude-sculpture queries", text.split("## Mars", 1)[1])
            return dict(top1=cells[2], rot=cells[4], ms=cells[5], where="placed anywhere", n=n.group(1) if n else "100")
    return None


def read_results(path="docs/results.md", matcher="handcrafted"):
    """Pick the row matching the active matcher from evaluate.py's table (held-out row preferred)."""
    if not os.path.exists(path):
        return None
    rows = {}
    for line in open(path):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0] in ("handcrafted", "learned"):
            rows[(cells[0], cells[1])] = cells
    for key in ((matcher, "placed anywhere"), (matcher, "lined up"), (matcher, "held-out regions"), (matcher, "anywhere")):
        if key in rows:
            m, where, top1, top5, rot, ms = rows[key]
            text = open(path).read()
            n = re.search(r"(\d+) crude-sculpture queries", text)
            big = re.search(r"\((\d+) for the learned \"placed anywhere\" row\)", text)
            n = big.group(1) if big and m == "learned" and where == "placed anywhere" else (n.group(1) if n else "100")
            return dict(top1=top1, rot=rot, ms=ms, where=where, n=n)
    return None


HERO_PLACE = dict(lon=86.925, lat=27.988, km=300, name="the Himalaya around Mount Everest")


def hero_data(index, place=HERO_PLACE, n=128):
    """Real elevation for the landing-page hero, plus a smoothed 'sand sculpture' of the same place."""
    try:
        import cv2
        import numpy as np
        from .tiles import lonlat_to_px, meters_per_px
        if index.h.get("synthetic"):
            return None
        z = index.h["zoom"]
        x, y = lonlat_to_px(place["lon"], place["lat"], z)
        x, y = x - index.h["px0"], y - index.h["py0"]
        w = int(round(place["km"] * 1000 / index.mpp(place["lat"])))
        H, W = index.mosaic.shape
        x0, y0 = int(round(x - w / 2)), int(round(y - w / 2))
        if w < 16 or x0 < 0 or y0 < 0 or x0 + w > W or y0 + w > H:
            return None
        real = cv2.resize(np.asarray(index.mosaic[y0:y0 + w, x0:x0 + w], np.float32), (n, n), interpolation=cv2.INTER_CUBIC)
        sand = cv2.GaussianBlur(real, (0, 0), n / 26)
        return dict(n=n, real=np.round(real).astype(int).ravel().tolist(), sand=np.round(sand).astype(int).ravel().tolist(),
                    name=place["name"], km=place["km"])
    except Exception:
        return None


STATIC_CSS = """
.examples { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; margin: 0 0 40px; }
.ex { display: block; background: var(--white); border-radius: var(--r-l); overflow: hidden; color: var(--ink);
  transition: transform .35s var(--ease), box-shadow .35s var(--ease); }
.ex:hover { text-decoration: none; transform: scale(1.015); box-shadow: 0 20px 40px -24px rgba(0,0,0,.35); }
.ex .pics { display: grid; grid-template-columns: 1fr 1fr; }
.ex img { width: 100%; aspect-ratio: 1; object-fit: cover; }
.ex div.t { padding: 16px 20px 20px; }
.ex b { display: block; font-size: 19px; font-weight: 600; }
.ex span { color: var(--ink-2); font-size: 14px; }
.run h3 { font-size: 24px; font-weight: 700; margin: 0 0 6px; }
.run p { color: var(--ink-2); margin: 0 0 18px; }
.run pre { margin: 0; background: var(--light); border-radius: var(--r-m); padding: 18px 20px; overflow-x: auto;
  font: 14px/1.7 ui-monospace, "SF Mono", Menlo, monospace; letter-spacing: 0; color: var(--ink); }
.run .gh { margin-top: 22px; text-align: center; }
"""


PLANET_CSS = """
.gnav .otherp { color: #ff9b6b; }
.gnav .otherp.earth { color: #8fd0ff; }
.marsteaser { padding: 140px 0; text-align: center; background: radial-gradient(70% 80% at 50% 100%, #8c2a17 0%, #2a0f08 55%, #000 100%); }
.marsteaser .kick { color: #ff9b6b; font-weight: 600; font-size: 17px; margin: 0 0 8px; }
.marsteaser .section-title { background: linear-gradient(100deg, #f6dcc0, #e9a86f 40%, #c9562a); -webkit-background-clip: text; background-clip: text; color: transparent; }
.marsteaser .lede { color: #d7c2b6; max-width: 32em; margin: 12px auto 30px; }
.marsteaser .pill { background: #c1440e; }
"""

MARS_TEASER = """<section class="marsteaser dark">
  <div class="wrap reveal">
    <p class="kick">New</p>
    <h2 class="section-title">Now on Mars.</h2>
    <p class="lede">Same sand, another planet. Find where your landscape exists among Olympus Mons, Valles Marineris and
      thousands of craters, mapped by NASA's Mars Global Surveyor.</p>
    <a class="pill" href="mars/">Try Sand to Mars</a>
  </div>
</section>
"""

MARS_CSS = """
:root { --grad: linear-gradient(100deg, #f6dcc0 0%, #e9a86f 30%, #c9562a 66%, #8c2a17 100%); --blue: #c9562a; }
.pill:not(.ghost) { background: #c1440e; }
.pill:not(.ghost):hover { background: #a63a0c; }
.pill.ghost { color: #ff9b6b; border-color: rgba(255,155,107,.5); }
.light .pill.ghost, #drop .pill.ghost { color: #c1440e; border-color: rgba(193,68,14,.4); }
.hero .glow { background: radial-gradient(60% 50% at 50% 60%, rgba(193,68,14,.28), transparent 70%); }
.stats.dark { background: radial-gradient(80% 60% at 50% 0%, #2a120a 0%, #000 70%); }
#progress li.on i { border-color: #c1440e; border-right-color: transparent; }
"""

# Sand to Mars: the same page, with Mars words, data and colours.
MARS_TEXT = [
    ("<title>Sand to Earth</title>", "<title>Sand to Mars</title>"),
    ('content="Sand to Earth"', 'content="Sand to Mars"'),
    ("find where it already exists on Earth.", "find where it exists on Mars."),
    ("https://tilakkumar13.github.io/sand2earth/\">", "https://tilakkumar13.github.io/sand2earth/mars/\">"),
    ('aria-label="Sand to Earth"', 'aria-label="Sand to Mars"'),
    ('%%MARK%%Sand to Earth</a>', '%%MARK%%Sand to Mars</a>'),
    ('<h1 class="grad">Sand to Earth.</h1>', '<h1 class="grad">Sand to Mars.</h1>'),
    ("Shape a landscape with your hands. Find where it already exists.", "Shape a landscape with your hands. Find where it exists on Mars."),
    ('<p class="beat">Find it on Earth.', '<p class="beat">Find it on Mars.'),
    ('Sand <i><b id="mixbar"></b></i> Earth', 'Sand <i><b id="mixbar"></b></i> Mars'),
    ("Landforms repeat. The same uplift, erosion and rivers carve the same shapes on every continent.\n      <strong>So the ridge you press into clay on a café table very likely exists somewhere, at full size.</strong>",
     "Mars has a volcano almost three times the height of Everest, a canyon as long as the United States and craters\n"
     "      everywhere. <strong>Press a shape into sand, and find the place on Mars that looks like it.</strong>"),
    ('stop-color="#7fc4ff"', 'stop-color="#f0a070"'), ('stop-color="#0b4a8f"', 'stop-color="#7a2a14"'),
    ('fill="#6aa86f"', 'fill="#b5552b"'),
    ("Three steps from a handful of sand to a real place on the map.", "Three steps from a handful of sand to a real place on Mars."),
    ("compared with", "compared with"),
    ("We take real places, bend them into rough, rotated, blurry copies like a hand-made sculpture, and check whether the search traces each one back.",
     "We take real places on Mars, bend them into rough, rotated, blurry copies like a hand-made sculpture, and check whether the search traces each one back."),
    ("An experiment where GIS, computer vision and remote sensing meet: a physical sculpture goes in, a real place on the planet comes out.",
     "An experiment where GIS, computer vision and planetary remote sensing meet: a physical sculpture goes in, a real place on Mars comes out."),
    ("given a shape made by hand, where on Earth is it?", "given a shape made by hand, where on Mars is it?"),
    ("make Greenland win far too often", "make the polar regions win far too often"),
    ('<p>Elevation from the open <a href="https://registry.opendata.aws/terrain-tiles/">AWS Terrain Tiles</a> (SRTM, ETOPO1 and\n          national surveys). Imagery from <a href="https://s2maps.eu">Sentinel-2 cloudless</a> by EOX. Place names from OpenStreetMap.</p>',
     '<p>Elevation from the <a href="https://pds-geosciences.wustl.edu/missions/mgs/megdr.html">MGS MOLA laser altimeter</a>\n'
     '          (NASA, 1.85 km grid). Imagery from Viking and MOLA via <a href="https://trek.nasa.gov/mars/">NASA Mars Trek</a>.\n'
     '          Place names from the <a href="https://planetarynames.wr.usgs.gov/">IAU Gazetteer of Planetary Nomenclature</a>.</p>'),
    ("<p>Sand to Earth, 2026.", "<p>Sand to Mars, part of Sand to Earth, 2026."),
    ('<meta name="theme-color" content="#000000">', '<meta name="theme-color" content="#1a0a05">'),
]

LIVE_CSS = """
#srv { margin: 14px 0 0; text-align: center; color: var(--ink-2); font-size: 14px; min-height: 1.4em; }
.planet { display: flex; justify-content: center; gap: 4px; margin: 0 auto 22px; padding: 4px; width: max-content;
  background: rgba(0,0,0,.06); border-radius: 999px; }
.planet button { border: 0; background: none; font: inherit; font-size: 15px; font-weight: 600; padding: 9px 22px; border-radius: 999px;
  color: var(--ink-2); cursor: pointer; }
.planet button[aria-pressed="true"] { background: #fff; color: var(--ink); box-shadow: 0 1px 4px rgba(0,0,0,.12); }
html[data-planet="mars"] .planet button[aria-pressed="true"] { background: #c1440e; color: #fff; }
#report { position: fixed; inset: 0; width: 100%; height: 100%; border: 0; z-index: 1000; background: #000; }
html.has-report, html.has-report body { overflow: hidden; }
.cam { position: fixed; inset: 0; z-index: 1001; background: rgba(0,0,0,.86); display: flex; align-items: center; justify-content: center; padding: 20px; }
.cambox { width: min(560px, 100%); text-align: center; color: #f5f5f7; }
.camview { position: relative; aspect-ratio: 1; border-radius: 22px; overflow: hidden; background: #111; }
.camview video { width: 100%; height: 100%; object-fit: cover; display: block; }
.camview i { position: absolute; inset: 5%; border: 2px solid rgba(255,255,255,.7); border-radius: 14px; pointer-events: none; }
.cambox p { margin: 16px 0; color: #a1a1a6; font-size: 15px; }
.camctl { display: flex; gap: 12px; justify-content: center; }
.runlocal { text-align: center; color: var(--ink-2); font-size: 14px; margin: 18px 0 0; }
"""

RUN_LOCAL = ('<p class="runlocal reveal">The first search downloads about 70 MB (the depth model and a compact copy of '
             'the planet\'s terrain); after that it is cached. Prefer Python? '
             '<a href="https://github.com/Tilakkumar13/sand2earth#quick-start-macos-apple-silicon">Run it from the command line</a>.</p>')


def _static_try(examples):
    cards = "".join(
        f'<a class="ex reveal" href="{_html.escape(e["href"])}"><div class="pics">'
        f'<img src="{_html.escape(e["photo"])}" alt="Sculpture photo"><img src="{_html.escape(e["match"])}" alt="Matching terrain"></div>'
        f'<div class="t"><b>{_html.escape(e["title"])}</b><span>{_html.escape(e["sub"])}</span></div></a>'
        for e in (examples or []))
    ex_html = f'<div class="examples">{cards}</div>' if cards else ""
    return f"""<section class="try light" id="try">
  <div class="wrap">
    <div class="head reveal">
      <h2 class="section-title">Try it.</h2>
      <p class="lede">{"Open a real search below, or run" if cards else "Run"} it on your own Mac. Your photos never leave your computer.</p>
    </div>
    {ex_html}
    <div class="card run reveal">
      <h3>Run it yourself.</h3>
      <p>About five minutes on a Mac with Python 3.10 or newer.</p>
      <pre>git clone https://github.com/Tilakkumar13/sand2earth
cd sand2earth
python3 -m venv .venv &amp;&amp; source .venv/bin/activate
pip install -r requirements.txt
python build_index.py --zoom 6 --name world_z6
python app.py --index data/world_z6</pre>
      <div class="gh"><a class="pill" href="https://github.com/Tilakkumar13/sand2earth">View on GitHub</a></div>
    </div>
  </div>
</section>"""


def render_page(count, sizes_km=(156, 313, 626), matcher="handcrafted", results=None, hero=None,
                static=False, examples=None, public=False, engine=None, mars=None, planet="earth", data=None):
    """planet="mars" renders Sand to Mars: same page, Mars words, colours, data and results.
    engine: folder with the browser code; data: folder with this planet's index (default: engine)."""
    text = ("A neural network trained on thousands of real landscapes picks the candidates."
            if matcher == "learned" else
            "A rotation-proof terrain fingerprint picks the candidates.")
    r = results or read_results(matcher=matcher)
    if r:
        ms = r["ms"].replace(" ms", "")
        ms_txt = f"{float(ms) / 1000:.1f} s" if ms.replace(".", "").isdigit() else r["ms"]
        top1, rot = r["top1"], r["rot"]
        note = (f"From {r['n']} simulated sculptures of real places on Mars, placed anywhere and at any size, with random "
                "rotation, depth distortion, blur and noise. The matcher learned on Earth terrain only, so every Mars place was "
                "new to it; that is why the number is lower than on Earth. Real photos of real sand are the next test.") \
            if planet == "mars" else \
               (f"From {r['n']} simulated sculptures in regions held out of training, "
                + ("placed anywhere and at any size, " if r['where'] == 'placed anywhere' else "")
                + "with random rotation, depth distortion, blur and noise. The test starts from a height map, so it "
                  "does not include reading depth from a photo: real photos of real sand are the next test.")
    else:
        top1, rot, ms_txt = "77%", "2°", "0.6 s"
        note = "Run evaluate.py to measure accuracy on your own index."
    import json as _json
    cap = (f"These mountains are real: {hero['name']}, {hero['km']} km across. "
           f"The sand above was the same place, smoothed like a hand-made copy.") if hero else \
          f"Searched against {count:,} stretches of real terrain."
    page = _PAGE
    browser = static and bool(engine)
    if public:
        page = (page.replace("<p class=\"lede\">Your photo stays on this computer.</p>",
                             "<p class=\"lede\">Your photo is searched on a small server, deleted after 30 minutes and never published.</p>")
                    .replace("becomes a height map, right on your Mac.", "becomes a height map in seconds.")
                    .replace("turns it into a height map on your Mac.", "turns it into a height map."))
    if browser:
        page = (page.replace("<p class=\"lede\">Your photo stays on this computer.</p>",
                             "<p class=\"lede\">Everything runs right here in your browser. Your photo never leaves your device.</p>")
                    .replace("becomes a height map, right on your Mac.", "becomes a height map, right in your browser.")
                    .replace("turns it into a height map on your Mac.", "turns it into a height map, right in your browser."))
    page = page.replace("</style></head>", LIVE_CSS + PLANET_CSS + (MARS_CSS if planet == "mars" else "") + "</style></head>", 1)
    page = page.replace("%%ENGINE%%", _json.dumps(engine if browser else ""))
    planets = {planet: data or engine} if browser else {}
    if browser and mars and planet == "earth" and False:   # (the switch moved to its own page: Sand to Mars)
        planets["mars"] = mars
    page = page.replace("%%PLANET_DATA%%", _json.dumps(planets)).replace("%%PLANET%%", _json.dumps(planet))
    page = page.replace("%%OTHERPLANET%%", ('<a class="otherp" href="mars/">Sand to Mars</a>' if mars else "") if planet == "earth"
                        else '<a class="otherp earth" href="../">Sand to Earth</a>')
    page = page.replace("%%MARSTEASER%%", MARS_TEASER if (planet == "earth" and mars) else "")
    if planet == "mars":
        for x, y in MARS_TEXT:
            page = page.replace(x, y)
    page = page.replace("%%PLANETS%%", ('<div class="planet reveal" role="group" aria-label="Search on">'
                                        '<button type="button" data-planet="earth" aria-pressed="true">Earth</button>'
                                        '<button type="button" data-planet="mars" aria-pressed="false">Mars</button></div>\n    ')
                        if False else "")                       # Earth and Mars now have their own pages
    page = page.replace("%%RUNLOCAL%%", RUN_LOCAL if browser else "")
    if static and not browser:
        a = page.index('<section class="try light" id="try">')
        b = page.index("</section>", a) + len("</section>")
        page = page[:a] + _static_try(examples) + page[b:]
        page = page.replace("</style></head>", STATIC_CSS + "</style></head>", 1)
        page = page.replace("<p class=\"lede\">Your photo stays on this computer.</p>", "")
        page = page.replace("becomes a height map, right on your Mac.", "becomes a height map.")
        page = page.replace('<a class="pill small" href="#try">Try it</a>', '<a class="pill small" href="#try">Try it</a>')
    return (page.replace("%%HERODATA%%", _json.dumps(hero) if hero else "null").replace("%%HEROCAP%%", _html.escape(cap))
            .replace("%%FONTS%%", FONTS).replace("%%CSS%%", BASE_CSS).replace("%%MARK%%", MARK_SVG)
            .replace("%%IMPORTMAP%%", IMPORTMAP).replace("%%REVEAL%%", _reveal())
            .replace("%%COUNTBIG%%", f"{count:,}" if count < 100000 else f"{round(count / 1000)}K")
            .replace("%%COUNT%%", f"{count:,}").replace("%%SIZES%%", _join(sizes_km))
            .replace("%%MATCHER%%", text).replace("%%TOP1%%", _html.escape(top1.replace(" ", "")))
            .replace("%%ROT%%", _html.escape(rot)).replace("%%MS%%", _html.escape(ms_txt))
            .replace("%%STATNOTE%%", _html.escape(note)))


def _reveal():
    from .style import REVEAL_JS
    return REVEAL_JS
