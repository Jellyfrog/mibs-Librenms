(function () {
  "use strict";
  var ROOT = typeof document !== "undefined" ? (document.documentElement.dataset.root || "") : "";
  var BASE = ROOT + "/data/search/";
  var MAX_SHARDS = 8, MAX_RESULTS = 200, LIVE_RESULTS = 8;

  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; } // plain code-point order, as the index is sorted

  // All shards that can hold names starting with q: the longest shard prefix of q, then every deeper shard,
  // shortest prefixes first (they hold the shortest, best-ranked names). Callers load at most MAX_SHARDS.
  function pickNameShards(prefixes, q) {
    var longest = null, below = [];
    prefixes.forEach(function (p) {
      if (q.indexOf(p) === 0 && (longest === null || p.length > longest.length)) longest = p;
      if (p.length > q.length && p.indexOf(q) === 0) below.push(p);
    });
    below.sort(function (a, b) { return (a.length - b.length) || cmp(a, b); });
    return (longest !== null ? [longest] : []).concat(below); // longest is never longer than q, below always is
  }

  function isArcPrefix(p, q) { return p === "" || q === p || q.indexOf(p + ".") === 0; }

  function pickOidShards(prefixes, q) {
    return prefixes.filter(function (p) { return isArcPrefix(p, q); })
      .sort(function (a, b) { return b.length - a.length; });
  }

  function oidLookup(rows, q) {
    var best = null, children = [];
    rows.forEach(function (r) {
      if (isArcPrefix(r[0], q)) { if (!best || r[0].length > best[0].length) best = r; }
      else if (r[0].indexOf(q + ".") === 0 && children.length < MAX_RESULTS) children.push(r);
    });
    return { best: best, instance: best && best[0] !== q ? q.slice(best[0].length + 1) : "", children: children };
  }

  // ---- index format v2 decoding (see search_index.py) ----
  function frontDecode(s) {
    var out = [], prev = "";
    if (!s) return out;
    s.split("\n").forEach(function (line) {
      var sp = line.indexOf(" ");
      prev = prev.slice(0, +line.slice(0, sp)) + line.slice(sp + 1);
      out.push(prev);
    });
    return out;
  }
  function lines(text, fn) {
    var out = [];
    text.split("\n").forEach(function (line) {
      if (!line) return;
      var f = line.split("\t");
      f[2].split(",").forEach(function (idx) { out.push(fn(f, +idx)); });
    });
    return out;
  }
  // name shard -> rows [name, oid|null, modIdx, isMib]; OID field "" = a MIB, "-" = an object with no known OID
  function parseNames(text) {
    return lines(text, function (f, i) { return [f[0], f[1] && f[1] !== "-" ? f[1] : null, i, f[1] === ""]; });
  }
  // OID shard -> rows [oid, name, modIdx]; OIDs are stored relative to the shard prefix
  function parseOids(prefix, text) {
    return lines(text, function (f, i) { return [f[0] ? (prefix ? prefix + "." + f[0] : f[0]) : prefix, f[1], i]; });
  }

  if (typeof window === "undefined") { // node (tests); browsers expose element ids such as id="module" as globals
    module.exports = { pickNameShards: pickNameShards, pickOidShards: pickOidShards, oidLookup: oidLookup,
      frontDecode: frontDecode, parseNames: parseNames, parseOids: parseOids };
    return;
  }

  // shared with site.js (loaded after this file on every page)
  window.MibSite = { ROOT: ROOT, esc: esc };

  // ---- query engine: returns {best?, items[], total} of plain result objects ----
  var manifest = null, loading = null;
  function getText(url) { return fetch(url).then(function (r) { return r.ok ? r.text() : ""; }).catch(function () { return ""; }); }
  function loadManifest() {
    if (!loading) loading = fetch(BASE + "manifest.json").then(function (r) { return r.json(); }).then(function (m) {
      manifest = { modules: m.modules, dirs: m.dirs, vendors: m.vendors, n: frontDecode(m.n), o: frontDecode(m.o) };
    });
    return loading;
  }
  function file(p) { return (p === "" ? "_" : p) + ".txt"; }
  // parsed rows are cached per shard, so typing more characters never re-parses a shard
  var parsed = {};
  function nameShard(p) {
    return parsed["n" + p] || (parsed["n" + p] = getText(BASE + "n/" + file(p)).then(function (t) {
      return parseNames(t).map(function (r) { r.push(r[0].toLowerCase()); return r; }); // r[4] = lowercased name
    }));
  }
  function oidShard(p) { return parsed["o" + p] || (parsed["o" + p] = getText(BASE + "o/" + file(p)).then(function (t) { return parseOids(p, t); })); }
  function result(modIdx, name, oid, opt) { // opt: {instance, isMib}
    opt = opt || {};
    var m = manifest.modules[modIdx], dir = manifest.dirs[m[1]];
    var url = "/mib/" + (dir === "_root" ? "" : dir + "/") + m[0] + "/"; // as Module.url
    return {
      name: name || m[0], oid: oid, instance: opt.instance || "", mib: m[0], vendor: manifest.vendors[m[2]], isMib: !!opt.isMib,
      href: ROOT + url + (name && name !== m[0] ? "#" + encodeURIComponent(name) : "")
    };
  }
  function isOid(q) { return /^\.?\d/.test(q); }

  function findName(q) {
    var lq = q.toLowerCase().replace(/^.*::/, "");
    var all = pickNameShards(manifest.n, lq), partial = all.length > MAX_SHARDS;
    return Promise.all(all.slice(0, MAX_SHARDS).map(nameShard))
      .then(function (shards) {
        var rows = [].concat.apply([], shards).filter(function (r) { return r[4].indexOf(lq) === 0; });
        rows.sort(function (a, b) {
          return (a[0].length - b[0].length) || ((a[3] ? 0 : 1) - (b[3] ? 0 : 1)) || cmp(a[0], b[0]);
        });
        return { best: null, total: rows.length, partial: partial,
          items: rows.slice(0, MAX_RESULTS).map(function (r) { return result(r[2], r[0], r[1], { isMib: r[3] }); }) };
      });
  }

  function findOid(q) {
    q = q.replace(/^\./, "").replace(/\.$/, "");
    var shards = pickOidShards(manifest.o, q), children = [];
    function tryShard(i) {
      if (i >= shards.length) return Promise.resolve({ best: null, instance: "", children: children });
      return oidShard(shards[i]).then(function (rows) {
        var res = oidLookup(rows, q);
        if (!children.length) children = res.children;
        return res.best ? { best: res.best, instance: res.instance, children: children } : tryShard(i + 1);
      });
    }
    return tryShard(0).then(function (res) {
      return {
        best: res.best ? result(res.best[2], res.best[1], res.best[0], { instance: res.instance }) : null,
        total: res.children.length,
        items: res.children.map(function (r) { return result(r[2], r[1], r[0]); }),
        below: q
      };
    });
  }

  function find(q) { return loadManifest().then(function () { return isOid(q) ? findOid(q) : findName(q); }); }

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function meta(r) {
    return (r.oid ? "<code>" + esc(r.oid) + (r.instance ? "." + esc(r.instance) : "") + "</code> " : r.isMib ? "<span class=\"tag\">MIB</span> " : "") +
      "<small>" + (r.isMib ? "" : esc(r.mib)) + (r.vendor ? (r.isMib ? "" : " · ") + esc(r.vendor) : "") + "</small>";
  }

  // ---- full results page (/search/) ----
  var input = document.getElementById("q"), out = document.getElementById("results");
  if (input && out) {
    var timer, seq = 0;
    var li = function (r) { return "<li><a href=\"" + esc(r.href) + "\"><b>" + esc(r.name) + "</b></a> " + meta(r) + "</li>"; };
    var run = function () {
      var q = input.value.trim(), my = ++seq;
      history.replaceState(null, "", q ? "?q=" + encodeURIComponent(q) : location.pathname);
      if (q.length < 2) { out.innerHTML = "<p class=\"hint\">Type 2 or more characters.</p>"; return; }
      find(q).then(function (res) {
        if (my !== seq) return;
        var html = "";
        if (res.best) html += "<h2>Best result</h2><ol>" + li(res.best) + "</ol>";
        if (res.items.length) html += (res.below ? "<h2>Objects below " + esc(res.below) + "</h2>" : "") +
          "<ol>" + res.items.map(li).join("") + "</ol>";
        if (res.partial || res.total > res.items.length) html += "<p class=\"hint\">There are more results than the page can show. Type more characters.</p>";
        out.innerHTML = html || "<p>No results.</p>";
      });
    };
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 150); });
    var initial = new URLSearchParams(location.search).get("q");
    if (initial) { input.value = initial; run(); }
  }

  // ---- live results under the header and home search boxes ----
  document.querySelectorAll("input[data-live]").forEach(function (box, n) {
    var form = box.form, list = document.createElement("ul"), seq = 0, timer, items = [], active = -1;
    list.className = "live-list"; list.id = "live-" + n; list.setAttribute("role", "listbox"); list.hidden = true;
    form.appendChild(list);
    box.setAttribute("role", "combobox"); box.setAttribute("aria-controls", list.id);
    box.setAttribute("aria-expanded", "false"); box.setAttribute("aria-autocomplete", "list");

    function close() { list.hidden = true; active = -1; box.setAttribute("aria-expanded", "false"); box.removeAttribute("aria-activedescendant"); }
    function mark(i) {
      var opts = list.querySelectorAll("[role=option]");
      if (!opts.length) return;
      active = (i + opts.length) % opts.length;
      opts.forEach(function (o, j) { o.setAttribute("aria-selected", String(j === active)); });
      box.setAttribute("aria-activedescendant", opts[active].id);
    }
    function show(q, res) {
      items = (res.best ? [res.best] : []).concat(res.items).slice(0, LIVE_RESULTS);
      var all = "<li class=\"live-all\"><a href=\"" + esc(form.action + "?q=" + encodeURIComponent(q)) + "\">See all results for <b>" + esc(q) + "</b></a></li>";
      list.innerHTML = (items.length ? items.map(function (r, i) {
        return "<li role=\"option\" id=\"" + list.id + "-" + i + "\" aria-selected=\"false\"><a href=\"" + esc(r.href) + "\"><b>" + esc(r.name) + "</b> " + meta(r) + "</a></li>";
      }).join("") : "<li class=\"live-none\">No results.</li>") + all;
      list.hidden = false; active = -1; box.setAttribute("aria-expanded", "true");
    }
    function run() {
      var q = box.value.trim(), my = ++seq;
      if (q.length < 2) { close(); return; }
      find(q).then(function (res) { if (my === seq && box.value.trim() === q) show(q, res); });
    }
    box.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 120); });
    box.addEventListener("focus", function () { loadManifest(); if (box.value.trim().length >= 2 && list.innerHTML) { list.hidden = false; box.setAttribute("aria-expanded", "true"); } });
    box.addEventListener("keydown", function (e) {
      if (list.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); mark(active + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); mark(active - 1); }
      else if (e.key === "Escape") { close(); }
      else if (e.key === "Enter" && active >= 0 && items[active]) { e.preventDefault(); location.href = items[active].href; }
    });
    document.addEventListener("click", function (e) { if (!form.contains(e.target)) close(); });
  });
})();
