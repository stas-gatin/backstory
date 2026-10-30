// Gentle motion for every page: the headline comes in word by word, and blocks rise into place as they scroll into
// view. Nothing moves for people who ask their system for reduced motion.
(() => {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  document.querySelectorAll(".hero h1").forEach((h) => {
    let i = 0;
    const words = (node) => [...node.childNodes].forEach((n) => {
      if (n.nodeType === 3) {
        const frag = document.createDocumentFragment();
        n.textContent.split(/(\s+)/).forEach((w) => {
          if (!w.trim()) { frag.appendChild(document.createTextNode(w)); return; }
          const s = document.createElement("span");
          s.className = "word"; s.textContent = w; s.style.animationDelay = (0.06 + i++ * 0.07) + "s";
          frag.appendChild(s);
        });
        n.replaceWith(frag);
      } else if (n.nodeType === 1) words(n);
    });
    words(h);
  });
  const SEL = ".hero p, .promises li, .section-title, .card:not(.result):not(.input), .ps, .kpi, .rrow, .bar, .lessons li, .tests tbody tr, .motto, footer";
  const io = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
  const watch = (root) => root.querySelectorAll(SEL).forEach((el) => {
    if (el.classList.contains("sr")) return;
    el.classList.add("sr");
    io.observe(el);
  });
  watch(document);
  // Blocks added later (the track record's rows, a check's cards) get the same treatment.
  new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => { if (n.nodeType === 1) { if (n.matches?.(SEL)) { n.classList.add("sr"); io.observe(n); } watch(n); } })))
    .observe(document.body, { childList: true, subtree: true });
})();
