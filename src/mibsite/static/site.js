(function () {
  "use strict";
  var root = document.documentElement;
  var themeBtn = document.querySelector(".theme");
  if (themeBtn) themeBtn.addEventListener("click", function () {
    var dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch (e) {}
  });

  document.querySelectorAll("pre.cmd").forEach(function (pre) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "copy"; b.textContent = "Copy";
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(pre.querySelector("code").textContent).then(function () {
        b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1200);
      });
    });
    pre.appendChild(b);
  });

  var article = document.querySelector("article.mib");
  if (!article) return;
  var table = article.querySelector("table.tt");
  if (!table) return;

  // Rows are in pre-order with a depth (data-d); a branch's subtree is the run of following deeper rows.
  var rows = Array.prototype.slice.call(table.querySelectorAll("tr.r"));
  // Per-row lookups are cached in arrays once, so render() and the filter never query the DOM per row.
  // byId has no prototype, so a hash like #constructor or #toString is simply "not found"
  var depth = [], parent = [], collapsed = [], stack = [], byId = Object.create(null), toggles = [], details = [], names = [];
  var hl = []; // rows currently highlighted by the filter
  rows.forEach(function (r, i) {
    var d = +r.dataset.d;
    depth.push(d);
    if (d > 24) r.style.setProperty("--d", d); // style.css covers depths 1-24 (so no-JS pages are indented too)
    names.push(r.id.toLowerCase());
    var n = r.nextElementSibling;
    details.push(n && n.classList.contains("dr") ? n : null);
    while (stack.length && depth[stack[stack.length - 1]] >= d) stack.pop();
    parent.push(stack.length ? stack[stack.length - 1] : -1);
    stack.push(i);
    if (!(r.id in byId)) byId[r.id] = i; // a #hash opens the first row with that name
    var b = null;
    if (r.classList.contains("br")) { // toggles are added here to keep the static HTML small
      b = document.createElement("button");
      b.type = "button"; b.className = "tg"; b.setAttribute("aria-label", "Open or close " + r.id);
      r.firstElementChild.insertBefore(b, r.firstElementChild.firstChild);
    }
    toggles.push(b);
    collapsed.push(false); // the tree starts fully expanded
  });
  var matches = null; // filter result: array of booleans "visible", or null when no filter

  function render() {
    var skip = -1;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i], show;
      if (matches) show = matches[i];
      else if (skip !== -1 && depth[i] > skip) show = false;
      else { skip = -1; show = true; if (collapsed[i]) skip = depth[i]; }
      if (r.hidden === show) r.hidden = !show;
      var dr = details[i];
      if (dr) { var dHidden = !show || !r.classList.contains("open"); if (dr.hidden !== dHidden) dr.hidden = dHidden; }
      if (toggles[i]) toggles[i].setAttribute("aria-expanded", String(matches ? true : !collapsed[i]));
    }
  }
  function openDetail(i, open) {
    var dr = details[i];
    if (!dr) return;
    rows[i].classList.toggle("open", open);
  }

  function openTo(id) {
    var i = byId[id];
    if (i === undefined) return;
    if (matches) { matches = null; if (filter) filter.value = ""; clearHl(); }
    for (var p = parent[i]; p !== -1; p = parent[p]) collapsed[p] = false;
    openDetail(i, true);
    render();
    rows[i].scrollIntoView({ block: "center" });
  }

  table.addEventListener("click", function (ev) {
    var r = ev.target.closest("tr.r");
    if (!r || ev.target.closest("a")) return; // links navigate via hashchange
    var i = rows.indexOf(r); // by position, not id: ids can repeat on a page
    if (ev.target.closest(".tg")) { if (!matches) { collapsed[i] = !collapsed[i]; render(); } return; }
    if (getSelection().toString()) return; // let people select/copy OIDs
    openDetail(i, !r.classList.contains("open"));
    render();
  });

  article.querySelectorAll("[data-tree]").forEach(function (b) {
    b.addEventListener("click", function () {
      var close = b.dataset.tree === "close";
      rows.forEach(function (r, i) { collapsed[i] = close && r.classList.contains("br"); });
      render();
    });
  });

  var filter = article.querySelector(".tfilter"), timer;
  function clearHl() { hl.forEach(function (r) { r.classList.remove("hl"); }); hl = []; }
  if (filter) filter.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      var q = filter.value.trim().toLowerCase();
      clearHl();
      if (!q) { matches = null; render(); return; }
      matches = rows.map(function () { return false; });
      var until = -1;
      rows.forEach(function (r, i) {
        if (until !== -1 && depth[i] > until) { matches[i] = true; return; } // descendants of a match
        until = -1;
        if (names[i].indexOf(q) === -1) return;
        r.classList.add("hl"); hl.push(r);
        matches[i] = true; until = depth[i];
        for (var p = parent[i]; p !== -1 && !matches[p]; p = parent[p]) matches[p] = true;
      });
      render();
    }, 150);
  });

  render();
  if (location.hash) openTo(decodeURIComponent(location.hash.slice(1)));
  addEventListener("hashchange", function () { openTo(decodeURIComponent(location.hash.slice(1))); });
})();
