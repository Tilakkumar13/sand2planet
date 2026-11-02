"""Shared look for the landing page and the results page.

Apple-style product page: system San Francisco on a Mac (Inter elsewhere), alternating
black and light full-bleed sections, big tight headlines, generous space, pill buttons
and frosted navigation.
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">')

BASE_CSS = r"""
:root {
  --black: #000000;
  --ink: #1d1d1f;          /* text on light */
  --ink-2: #6e6e73;        /* secondary on light */
  --ink-3: #86868b;
  --light: #f5f5f7;        /* light section */
  --white: #ffffff;
  --on-dark: #f5f5f7;
  --on-dark-2: #a1a1a6;
  --line: #d2d2d7;
  --line-dark: #424245;
  --blue: #0071e3;         /* action */
  --blue-hover: #0077ed;
  --link-dark: #2997ff;    /* links on black */
  --sand: #e3c193;
  --earth: #5aa469;
  --sea: #3b8fd9;
  --grad: linear-gradient(100deg, #f1d3a6 0%, #d8a86f 28%, #7fb069 62%, #4c9be0 100%);
  --sans: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", Inter, "Helvetica Neue", Arial, sans-serif;
  --r-l: 28px;
  --r-m: 18px;
  --nav-h: 48px;
  --ease: cubic-bezier(.28, .11, .32, 1);
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; scroll-behavior: smooth; scroll-padding-top: var(--nav-h); }
body { margin: 0; background: var(--white); color: var(--ink); font: 400 17px/1.47 var(--sans);
       letter-spacing: -0.022em; -webkit-font-smoothing: antialiased; }
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }
:focus-visible { outline: 2px solid var(--blue); outline-offset: 3px; border-radius: 6px; }
.num { font-variant-numeric: tabular-nums; }
img { display: block; }

/* frosted global nav */
.gnav { position: fixed; inset: 0 0 auto 0; z-index: 50; height: var(--nav-h);
        background: rgba(22, 22, 23, .72); backdrop-filter: saturate(180%) blur(20px);
        -webkit-backdrop-filter: saturate(180%) blur(20px); color: var(--on-dark); }
.gnav .in { max-width: 1024px; margin: 0 auto; height: 100%; padding: 0 22px; display: flex; align-items: center; gap: 28px; }
.gnav .brand { display: flex; align-items: center; gap: 9px; color: var(--on-dark); font-weight: 600; font-size: 16px; letter-spacing: -0.01em; margin-right: auto; }
.gnav .brand:hover { text-decoration: none; }
.gnav .brand svg { width: 26px; height: 17px; }
.gnav .links { display: flex; align-items: center; }
.gnav .links a { white-space: nowrap; color: rgba(245, 245, 247, .82); font-size: 13px; margin-left: 24px; letter-spacing: -0.01em; }
.gnav .links a:hover { color: #fff; text-decoration: none; }

.pill { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 0; cursor: pointer;
        background: var(--blue); color: #fff; font: 500 17px/1 var(--sans); letter-spacing: -0.02em;
        padding: 12px 22px; border-radius: 980px; transition: background .2s var(--ease), transform .2s var(--ease); }
.pill:hover { background: var(--blue-hover); text-decoration: none; }
.pill:active { transform: scale(.98); }
.pill.small { font-size: 12px; padding: 5px 12px; }
.pill.ghost { background: transparent; color: var(--blue); box-shadow: inset 0 0 0 1px var(--blue); }
.pill.ghost:hover { background: var(--blue); color: #fff; }
.pill:disabled { opacity: .35; cursor: default; }
.more { font-size: 17px; }
.more::after { content: " \203A"; }
.dark .more, .dark a:not(.pill) { color: var(--link-dark); }
.dark .pill { color: #fff; }
.dark .pill.ghost { color: var(--link-dark); box-shadow: inset 0 0 0 1px var(--link-dark); }
.dark .pill.ghost:hover { background: var(--link-dark); color: #000; }

.dark { background: var(--black); color: var(--on-dark); }
.light { background: var(--light); }
.wrap { max-width: 980px; margin: 0 auto; padding: 0 22px; }
.wide { max-width: 1200px; margin: 0 auto; padding: 0 22px; }

.headline { font-size: clamp(40px, 6.2vw, 80px); line-height: 1.05; font-weight: 700; letter-spacing: -0.015em; margin: 0; }
.section-title { font-size: clamp(32px, 4.4vw, 56px); line-height: 1.07; font-weight: 700; letter-spacing: -0.005em; margin: 0; }
.lede { font-size: clamp(19px, 1.9vw, 24px); line-height: 1.38; font-weight: 500; letter-spacing: 0.002em; color: var(--ink-2); }
.dark .lede { color: var(--on-dark-2); }
.grad { background: var(--grad); -webkit-background-clip: text; background-clip: text; color: transparent; }

/* scroll reveal (one shared, gentle movement) */
.reveal { opacity: 0; transform: translateY(28px); transition: opacity 1s var(--ease), transform 1s var(--ease); }
.reveal.in { opacity: 1; transform: none; }

.foot { background: var(--light); color: var(--ink-3); font-size: 12px; line-height: 1.33; letter-spacing: -0.01em; }
.foot .wrap { padding-top: 18px; padding-bottom: 22px; }
.foot p { margin: 0 0 8px; }
.foot .rule { border-top: 1px solid var(--line); margin: 12px 0; }

@media (max-width: 734px) {
  .gnav .links a:not(.pill) { display: none; }
  .gnav .links a.pill { margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  .reveal { opacity: 1; transform: none; transition: none; }
  * { animation: none !important; }
}
"""

MARK_SVG = ('<svg viewBox="0 0 34 22" aria-hidden="true" fill="none" stroke="currentColor" stroke-linecap="round">'
            '<path d="M2 19c5-1 7-9 15-11s11 6 15 5" stroke-width="2.2"/>'
            '<path d="M8 19c3-1 5-6 9-7s7 3 10 3" stroke-width="1.2" opacity=".55"/>'
            '<path d="M13 19c2 0 3-3 5-3s3 2 5 2" stroke-width="1" opacity=".35"/></svg>')

IMPORTMAP = ('<script type="importmap">{"imports": {"three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",'
             '"three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>')

REVEAL_JS = r"""
<script>
(() => {
  const els = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window) || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    els.forEach(e => e.classList.add("in")); return;
  }
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { rootMargin: "0px 0px -12% 0px" });
  els.forEach(e => io.observe(e));
})();
</script>
"""
