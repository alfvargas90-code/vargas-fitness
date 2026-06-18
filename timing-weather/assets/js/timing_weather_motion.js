/* timing_weather_motion.js — additive entrance animations.
 *
 * Uses the NATIVE Web Animations API (element.animate) + IntersectionObserver —
 * no external library, so there is nothing for GitHub Pages' Jekyll build to
 * strip and nothing extra to download. Same static runtime as the dashboard.
 *
 * STRICTLY ADDITIVE per LOCKED.md. This file:
 *   • only animates opacity / transform — presentation, never content
 *   • never touches live data, the moon engine, ring values, or Currents voice
 *   • is fail-safe: it never sets inline opacity itself, so if the API is
 *     missing or a call throws, every element keeps its normal (visible) CSS
 *   • honors prefers-reduced-motion — zero motion when the user asks for none
 *
 * Effects: hero label rise-in · per-lens card reveal (above-fold staggers in,
 * below-fold reveals on scroll) · subtle ambient sun-bloom pulse.
 */
(function () {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  // Fail safe: reduced-motion, or a browser without WAAPI → leave the DOM as-is.
  if (reduce || typeof Element.prototype.animate !== 'function') return;

  const RISE = [
    { opacity: 0, transform: 'translateY(18px)' },
    { opacity: 1, transform: 'translateY(0)' },
  ];
  const TIMING = { duration: 560, easing: 'cubic-bezier(.2,.7,.2,1)', fill: 'both' };
  const seen = new WeakSet(); // each card animates at most once

  function rise(el, delay) {
    try { el.animate(RISE, Object.assign({}, TIMING, { delay: delay || 0 })); }
    catch (e) { /* never block the page on a presentation effect */ }
  }

  // Reveal a slide's not-yet-seen cards: above-the-fold cards stagger in now,
  // below-the-fold cards reveal on scroll as they enter — so the effect lands
  // where the eye is. Cards are never pre-hidden, so a miss can't strand them.
  function revealSlide(slide) {
    const cards = Array.from(slide.querySelectorAll('.card')).filter((c) => !seen.has(c));
    if (!cards.length) return;
    const fold = (window.innerHeight || 800) * 0.92;
    let stagger = 0;
    cards.forEach((c) => {
      seen.add(c);
      if (io && c.getBoundingClientRect().top >= fold) {
        io.observe(c);                 // below the fold → reveal on scroll
      } else {
        rise(c, stagger);              // visible now → stagger in
        stagger += 70;
      }
    });
  }

  const io = ('IntersectionObserver' in window)
    ? new IntersectionObserver((entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) { rise(e.target, 0); io.unobserve(e.target); }
        });
      }, { threshold: 0.12 })
    : null;

  function run() {
    // 1 — Hero label rises in once on load.
    const label = document.querySelector('.solar .label');
    if (label) rise(label, 0);

    // 2 — Cards in the active lens stagger in; other lenses reveal on switch.
    const active = document.querySelector('.slide.on') || document.querySelector('.slide');
    if (active) revealSlide(active);
    document.querySelectorAll('.lensnav button').forEach((btn) => {
      btn.addEventListener('click', () => {
        const slide = document.querySelector(`.slide[data-lens="${btn.dataset.lens}"]`);
        // Defer a frame: the existing handler flips display first, so we measure
        // the slide's real layout after the switch, not before.
        if (slide) requestAnimationFrame(() => revealSlide(slide));
      });
    });

    // 3 — Ambient sun bloom: a barely-there breathing pulse over the decorative
    //     sun glow so the hero reads as "alive". Never the moon.
    const sun = document.querySelector('.solar .sun');
    if (sun) {
      try {
        sun.animate([{ opacity: 0.9 }, { opacity: 1 }, { opacity: 0.9 }],
                    { duration: 6000, iterations: Infinity, easing: 'ease-in-out' });
      } catch (e) { /* decorative only */ }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
