/* timing_weather_motion.js — PROOF OF CONCEPT (additive presentation layer)
 *
 * Vanilla Motion micro-animations layered on top of the v3 dashboard, using the
 * self-hosted UMD global `window.Motion` (assets/js/vendor/motion.js). No build
 * step, no React — same runtime model as the rest of the dashboard.
 *
 * STRICTLY ADDITIVE per LOCKED.md. This file:
 *   • never touches live data, the moon engine, ring values, or Currents voice
 *   • only animates opacity / transform — presentation, not content
 *   • degrades to a fully-visible, un-animated page if Motion fails to load
 *     (we only ever set opacity:0 from inside the Motion-loaded path, so a
 *      missing library or a thrown error can never hide content)
 *   • honors prefers-reduced-motion — zero motion when the user asks for none
 *
 * Animated entry points: hero label rise-in · per-lens card stagger-in ·
 * lens-nav hover lift · barely-there ambient sun-bloom pulse.
 */
(function () {
  const M = window.Motion;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Fail safe: no library, or the user prefers reduced motion → leave DOM as-is.
  if (!M || reduce) return;

  const { animate, hover, stagger } = M;
  const RISE = ['translateY(14px)', 'none'];
  const seen = new WeakSet(); // each card is revealed at most once

  // Reveal every not-yet-seen card inside a slide, gently staggered. Called for
  // the active lens on load and again whenever a lens becomes active, so cards
  // in hidden slides are never pre-hidden (no JS failure can strand content).
  function revealSlide(slide) {
    const cards = Array.from(slide.querySelectorAll('.card')).filter((c) => !seen.has(c));
    if (!cards.length) return;
    cards.forEach((c) => { seen.add(c); c.style.opacity = '0'; });
    animate(cards, { opacity: [0, 1], transform: RISE },
            { duration: 0.5, ease: 'easeOut', delay: stagger(0.05) });
  }

  function run() {
    // 1 — Hero label rises in once on load.
    const label = document.querySelector('.solar .label');
    if (label) {
      animate(label, { opacity: [0, 1], transform: RISE },
              { duration: 0.6, ease: 'easeOut' });
    }

    // 2 — Cards in the active lens stagger in; other lenses reveal on switch.
    const active = document.querySelector('.slide.on') || document.querySelector('.slide');
    if (active) revealSlide(active);
    document.querySelectorAll('.lensnav button').forEach((btn) => {
      btn.addEventListener('click', () => {
        const slide = document.querySelector(`.slide[data-lens="${btn.dataset.lens}"]`);
        if (slide) revealSlide(slide);
      });
    });

    // 3 — Lens-nav buttons get a tactile lift on hover (pointer devices only).
    if (typeof hover === 'function') {
      document.querySelectorAll('.lensnav button').forEach((btn) => {
        hover(btn, () => {
          animate(btn, { transform: 'translateY(-2px)' }, { duration: 0.18, ease: 'easeOut' });
          return () => animate(btn, { transform: 'none' }, { duration: 0.18, ease: 'easeOut' });
        });
      });
    }

    // 4 — Ambient sun bloom: a barely-there breathing pulse so the hero reads as
    //     "alive". Low amplitude on a purely decorative layer — never the moon.
    const sun = document.querySelector('.solar .sun');
    if (sun) {
      animate(sun, { opacity: [0.92, 1, 0.92] },
              { duration: 6, repeat: Infinity, ease: 'easeInOut' });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
