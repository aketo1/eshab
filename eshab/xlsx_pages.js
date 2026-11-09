/* Excel's printed pages, inside Edge.

   xlsx_layout.py writes each sheet as a model: column widths, rows (a height,
   or none for rows Excel fits to their text), cells with their formatted text,
   the lines between cells, objects on their anchors and the page setup. Here
   the rows that fit to their text are measured, numbers too wide for their
   column become #### as in Excel, and the sheet is cut into pages: across and
   down within the printable area, at Excel's scale or fitted to pages, with
   title rows and columns repeated, page breaks kept, centring, gridlines and
   headers and footers. Everything is laid out four times larger than print
   (the PDF is shrunk afterwards), so lengths are points times K. */
(function () {
  "use strict";

  var PX = 96 / 72;
  var book = JSON.parse(document.getElementById("eshab-book").textContent);
  var K = book.k;
  var pages = [];
  var pageSizes = [];

  function px(points) { return points * K * PX; }

  function make(tag, className, parent) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (parent) parent.appendChild(el);
    return el;
  }

  /* -- the sheet's geometry ---------------------------------------------------- */

  function measureRows(sheet) {
    var heights = sheet.rows.slice();
    var box = make("div", "measure", document.body);
    var probes = [];
    sheet.cells.forEach(function (cell) {
      if (cell.rs !== 1 || heights[cell.r] !== null || !cell.t) return;
      var width = 0;
      for (var c = cell.c; c < cell.c + cell.cs; c++) width += sheet.cols[c];
      var probe = make("div", cell.k + (cell.w ? " cell wrap" : " cell"), box);
      probe.style.position = "relative";
      probe.style.width = px(Math.max(1, width - 2 * sheet.pad)) + "px";
      var inner = make("div", "v", probe);
      inner.style.position = "relative";
      inner.style.setProperty("--lh", px(cell.lh) + "px");
      inner.innerHTML = cell.t;
      probes.push({cell: cell, el: inner});
    });
    var needed = {};
    probes.forEach(function (probe) {
      var cell = probe.cell, height = cell.lh;
      if (cell.w) height = Math.max(cell.lh, probe.el.getBoundingClientRect().height / (K * PX));
      needed[cell.r] = Math.max(needed[cell.r] || 0, height);
    });
    box.remove();
    for (var r = 0; r < heights.length; r++) {
      if (heights[r] === null) heights[r] = Math.max(sheet.defaultRow, needed[r] || 0);
    }
    return heights;
  }

  /* Numbers that do not fit their column show as #### (General ones first
     give up decimals), as Excel shows them. */
  function fitNumbers(sheet) {
    var box = make("div", "measure", document.body), probes = [];
    sheet.cells.forEach(function (cell) {
      if (!cell.n || cell.w || !cell.t) return;
      var probe = make("span", cell.k, box);
      probe.style.whiteSpace = "pre";
      probe.innerHTML = cell.t;
      probes.push({cell: cell, el: probe});
    });
    var hash = make("span", "", box);
    probes.forEach(function (probe) {
      var cell = probe.cell, room = 0;
      for (var c = cell.c; c < cell.c + cell.cs; c++) room += sheet.cols[c];
      room = px(room - 2 * sheet.pad);
      if (probe.el.getBoundingClientRect().width <= room + 0.5) return;
      if (cell.g && cell.v !== null && cell.v !== undefined && isFinite(cell.v)) {
        for (var digits = 10; digits >= 1; digits--) {
          var text = shortGeneral(cell.v, digits);
          probe.el.textContent = text;
          if (probe.el.getBoundingClientRect().width <= room + 0.5) { cell.t = text; return; }
        }
      }
      hash.className = cell.k;
      hash.style.whiteSpace = "pre";
      hash.textContent = "#";
      var one = hash.getBoundingClientRect().width || 1;
      cell.t = new Array(Math.max(1, Math.floor(room / one)) + 1).join("#");
    });
    box.remove();
  }

  function shortGeneral(value, digits) {
    var text = Number(value).toPrecision(digits);
    if (text.indexOf("e") >= 0) {
      var parts = text.split("e"), mantissa = parts[0].replace(/\.?0+$/, ""), exponent = Number(parts[1]);
      return mantissa + "E" + (exponent < 0 ? "-" : "+") + (Math.abs(exponent) < 10 ? "0" : "") + Math.abs(exponent);
    }
    if (text.indexOf(".") >= 0) text = text.replace(/\.?0+$/, "");
    return text;
  }

  function positions(sizes) {
    var out = [0];
    for (var i = 0; i < sizes.length; i++) out.push(out[i] + sizes[i]);
    return out;
  }

  /* -- cutting into pages ---------------------------------------------------- */

  function indexRange(ids, span) {
    if (!span) return null;
    var first = -1, last = -1;
    for (var i = 0; i < ids.length; i++) {
      if (ids[i] >= span[0] && ids[i] <= span[1]) {
        if (first < 0) first = i;
        last = i;
      }
    }
    return first < 0 ? null : [first, last];
  }

  function runs(sizes, room, breaks, ids, titles) {
    var out = [], start = 0, used = 0;
    for (var i = 0; i < sizes.length; i++) {
      var forced = i > start && breaks.indexOf(ids[i - 1]) >= 0;
      var band = titles && start > titles[1] ? titles[2] : 0;
      if (i > start && (forced || used + sizes[i] > room - band + 0.01)) {
        out.push([start, i - 1]);
        start = i;
        used = 0;
      }
      used += sizes[i];
    }
    out.push([start, sizes.length - 1]);
    return out;
  }

  function sum(sizes, from, to) {
    var total = 0;
    for (var i = from; i <= to; i++) total += sizes[i];
    return total;
  }

  /* -- drawing a part of the sheet -------------------------------------------- */

  function slice(sheet, geo, rows, cols, rtl) {
    var x0 = geo.x[cols[0]], y0 = geo.y[rows[0]];
    var width = geo.x[cols[1] + 1] - x0, height = geo.y[rows[1] + 1] - y0;
    var el = make("div", "slice");
    el.style.width = px(width) + "px";
    el.style.height = px(height) + "px";
    function left(x, w) { return rtl ? width - (x - x0) - w : x - x0; }

    if (sheet.setup.grid) {
      for (var r = rows[0]; r <= rows[1] + 1; r++) line(el, "h", 0, geo.y[r] - y0, width, 0.5, "solid", "808080");
      for (var c = cols[0]; c <= cols[1] + 1; c++) line(el, "v", left(geo.x[c], 0), 0, height, 0.5, "solid", "808080");
    }
    sheet.cells.forEach(function (cell) {
      if (cell.r > rows[1] || cell.r + cell.rs - 1 < rows[0] || cell.c > cols[1] || cell.c + cell.cs - 1 < cols[0]) return;
      var x = geo.x[cell.c], w = geo.x[cell.c + cell.cs] - x;
      var y = geo.y[cell.r], h = geo.y[cell.r + cell.rs] - y;
      var box = make("div", cell.k + " cell" + (cell.w ? " wrap" : ""), el);
      box.style.left = px(left(x, w)) + "px";
      box.style.top = px(y - y0) + "px";
      box.style.width = px(w) + "px";
      box.style.height = px(h) + "px";
      if (!cell.t) return;
      if (cell.w) box.style.overflow = "hidden";
      var text = make("div", "v", box);
      text.innerHTML = cell.t;
      text.style.setProperty("--lh", px(cell.lh) + "px");
      placeText(sheet, geo, cell, text, w, rtl);
    });
    sheet.edges.forEach(function (edge) {
      if (edge.o === "h") {
        if (edge.r < rows[0] || edge.r > rows[1] + 1 || edge.c < cols[0] || edge.c > cols[1]) return;
        var w = geo.x[edge.c + 1] - geo.x[edge.c];
        line(el, "h", left(geo.x[edge.c], w), geo.y[edge.r] - y0, w, edge.w, edge.s, edge.k);
      } else {
        if (edge.c < cols[0] || edge.c > cols[1] + 1 || edge.r < rows[0] || edge.r > rows[1]) return;
        var h = geo.y[edge.r + 1] - geo.y[edge.r];
        line(el, "v", left(geo.x[edge.c], 0), geo.y[edge.r] - y0, h, edge.w, edge.s, edge.k);
      }
    });
    sheet.objects.forEach(function (object) {
      var spot = objectBox(sheet, geo, object);
      if (!spot) return;
      if (spot.x > geo.x[cols[1] + 1] || spot.x + spot.w < x0 || spot.y > geo.y[rows[1] + 1] || spot.y + spot.h < y0) return;
      var holder = make("div", "obj", el);
      holder.style.left = px(left(spot.x, spot.w)) + "px";
      holder.style.top = px(spot.y - y0) + "px";
      holder.style.width = px(spot.w) + "px";
      holder.style.height = px(spot.h) + "px";
      var inner = make("div", "inner", holder);
      inner.style.width = px(object.w) + "px";
      inner.style.height = px(object.h) + "px";
      if (Math.abs(spot.w - object.w) > 0.05 || Math.abs(spot.h - object.h) > 0.05) {
        inner.style.transform = "scale(" + (spot.w / object.w) + "," + (spot.h / object.h) + ")";
      }
      inner.innerHTML = object.html;
    });
    return {el: el, width: width, height: height};
  }

  function line(parent, orientation, x, y, length, width, style, color) {
    var el = make("div", "edge", parent);
    var thickness = Math.max(width, 0.25);
    if (orientation === "h") {
      el.style.left = px(x - (thickness > 1 ? thickness / 2 : 0)) + "px";
      el.style.top = px(y - thickness / 2) + "px";
      el.style.width = px(length + (thickness > 1 ? thickness : 0)) + "px";
      el.style.borderTop = px(thickness) + "px " + style + " #" + color;
    } else {
      el.style.left = px(x - thickness / 2) + "px";
      el.style.top = px(y - (thickness > 1 ? thickness / 2 : 0)) + "px";
      el.style.height = px(length + (thickness > 1 ? thickness : 0)) + "px";
      el.style.borderLeft = px(thickness) + "px " + style + " #" + color;
    }
  }

  function placeText(sheet, geo, cell, text, w, rtl) {
    var pad = sheet.pad, indent = cell.ind || 0;
    var spillLeft = 0, spillRight = 0;
    for (var i = 1; i <= cell.sl; i++) spillLeft += geo.w[cell.c - i] || 0;
    for (var j = 1; j <= cell.sr; j++) spillRight += geo.w[cell.c + cell.cs - 1 + j] || 0;
    if (rtl) { var swap = spillLeft; spillLeft = spillRight; spillRight = swap; }
    var vertical = cell.va;
    if (cell.rot) {
      text.style.left = "50%";
      text.style.top = "50%";
      var turn = cell.rot === 255 ? 0 : (cell.rot <= 90 ? -cell.rot : cell.rot - 90);
      if (cell.rot === 255) {
        text.style.writingMode = "vertical-rl";
        text.style.textOrientation = "upright";
      }
      text.style.transform = "translate(-50%,-50%) rotate(" + turn + "deg)";
      return;
    }
    if (cell.w) {
      text.style.left = px(pad + (cell.ha === "left" ? indent : 0)) + "px";
      text.style.right = px(pad + (cell.ha === "right" ? indent : 0)) + "px";
      text.style.textAlign = {center: "center", right: "right", justify: "justify", distributed: "justify"}[cell.ha] || "left";
    } else if (cell.ha === "right") {
      text.style.right = px(pad + indent) + "px";
      text.style.maxWidth = px(w + spillLeft - 2 * pad - indent) + "px";
      text.style.overflow = "hidden";
      text.style.textAlign = "right";
      text.style.direction = "ltr";
    } else if (cell.ha === "center" || cell.ha === "centerContinuous" || cell.ha === "fill") {
      var reach = Math.min(spillLeft, spillRight);
      text.style.left = px(-reach + pad) + "px";
      text.style.width = px(w + 2 * reach - 2 * pad) + "px";
      text.style.textAlign = "center";
      text.style.overflow = "hidden";
    } else {
      text.style.left = px(pad + indent) + "px";
      text.style.maxWidth = px(w + spillRight - 2 * pad - indent) + "px";
      text.style.overflow = "hidden";
    }
    if (vertical === "top") text.style.top = "0";
    else if (vertical === "center" || vertical === "justify" || vertical === "distributed") {
      text.style.top = "50%";
      text.style.transform = (text.style.transform || "") + " translateY(-50%)";
    } else text.style.bottom = "0";
  }

  function columnAt(sheet, geo, id, offset) {
    var index = sheet.colIds.indexOf(id);
    if (index < 0) {
      for (var i = 0; i < sheet.colIds.length; i++) if (sheet.colIds[i] > id) return geo.x[i];
      return geo.x[geo.x.length - 1];
    }
    return geo.x[index] + Math.min(offset, geo.w[index]);
  }

  function rowAt(sheet, geo, id, offset) {
    var index = sheet.rowIds.indexOf(id);
    if (index < 0) {
      for (var i = 0; i < sheet.rowIds.length; i++) if (sheet.rowIds[i] > id) return geo.y[i];
      return geo.y[geo.y.length - 1];
    }
    return geo.y[index] + Math.min(offset, geo.h[index]);
  }

  function objectBox(sheet, geo, object) {
    if (object.abs) return {x: object.abs[0], y: object.abs[1], w: object.w, h: object.h};
    var from = object.from;
    var x = columnAt(sheet, geo, from[0], from[1]), y = rowAt(sheet, geo, from[2], from[3]);
    if (object.to) {
      var to = object.to;
      var x2 = columnAt(sheet, geo, to[0], to[1]), y2 = rowAt(sheet, geo, to[2], to[3]);
      return {x: x, y: y, w: Math.max(1, x2 - x), h: Math.max(1, y2 - y)};
    }
    return {x: x, y: y, w: object.w, h: object.h};
  }

  /* -- a sheet's pages ---------------------------------------------------------- */

  function layoutSheet(sheet, sheetIndex) {
    var setup = sheet.setup;
    var heights = measureRows(sheet);
    fitNumbers(sheet);
    var geo = {w: sheet.cols, h: heights, x: positions(sheet.cols), y: positions(heights)};
    var paper = setup.paper, m = setup.m;
    var availW = paper[0] - m.l - m.r, availH = paper[1] - m.t - m.b;
    var titleRows = indexRange(sheet.rowIds, setup.titleRows), titleCols = indexRange(sheet.colIds, setup.titleCols);
    var titleH = titleRows ? sum(heights, titleRows[0], titleRows[1]) : 0;
    var titleW = titleCols ? sum(sheet.cols, titleCols[0], titleCols[1]) : 0;
    var totalW = geo.x[geo.x.length - 1], totalH = geo.y[geo.y.length - 1];
    var scale = (setup.scale || 100) / 100;
    if (setup.fit) {
      var sx = setup.fit[0] > 0 ? setup.fit[0] * availW / totalW : Infinity;
      var sy = setup.fit[1] > 0 ? setup.fit[1] * availH / totalH : Infinity;
      scale = Math.min(1, sx, sy);
      scale = Math.max(0.1, Math.floor(scale * 100 + 1e-6) / 100);
    }
    var capW = availW / scale, capH = availH / scale;
    var colRuns = runs(sheet.cols, capW, setup.colBreaks, sheet.colIds, titleCols ? [titleCols[0], titleCols[1], titleW] : null);
    var rowRuns = runs(heights, capH, setup.rowBreaks, sheet.rowIds, titleRows ? [titleRows[0], titleRows[1], titleH] : null);
    var order = [];
    if (setup.order === "over") rowRuns.forEach(function (rr) { colRuns.forEach(function (cr) { order.push([rr, cr]); }); });
    else colRuns.forEach(function (cr) { rowRuns.forEach(function (rr) { order.push([rr, cr]); }); });
    var rtl = setup.rtl;
    order.forEach(function (pair, index) {
      var rr = pair[0], cr = pair[1];
      var page = make("div", "page", document.body);
      page.style.width = px(paper[0]) + "px";
      page.style.height = px(paper[1] - 0.5) + "px";
      page.dataset.sheet = sheetIndex;
      var withRows = titleRows && rr[0] > titleRows[1], withCols = titleCols && cr[0] > titleCols[1];
      var blockW = sum(sheet.cols, cr[0], cr[1]) + (withCols ? titleW : 0);
      var blockH = sum(heights, rr[0], rr[1]) + (withRows ? titleH : 0);
      var area = make("div", "area", page);
      var offsetX = setup.center[0] ? Math.max(0, (availW - blockW * scale) / 2) : 0;
      var offsetY = setup.center[1] ? Math.max(0, (availH - blockH * scale) / 2) : 0;
      area.style.top = px(m.t + offsetY) + "px";
      if (rtl) area.style.right = px(m.r + offsetX) + "px";
      else area.style.left = px(m.l + offsetX) + "px";
      area.style.width = px(blockW) + "px";
      area.style.height = px(blockH) + "px";
      area.style.transformOrigin = rtl ? "top right" : "top left";
      if (scale !== 1) area.style.transform = "scale(" + scale + ")";
      var bodyX = withCols ? titleW : 0, bodyY = withRows ? titleH : 0;
      function put(part, x, y) {
        part.el.style.top = px(y) + "px";
        if (rtl) part.el.style.right = px(x) + "px";
        else part.el.style.left = px(x) + "px";
        area.appendChild(part.el);
      }
      if (withRows && withCols) put(slice(sheet, geo, titleRows, titleCols, rtl), 0, 0);
      if (withRows) put(slice(sheet, geo, titleRows, cr, rtl), bodyX, 0);
      if (withCols) put(slice(sheet, geo, rr, titleCols, rtl), 0, bodyY);
      put(slice(sheet, geo, rr, cr, rtl), bodyX, bodyY);
      pages.push({el: page, sheet: sheet, index: index, setup: setup});
      pageSizes.push(paper);
    });
  }

  /* -- headers and footers, and page numbers ------------------------------------- */

  function headersAndFooters() {
    var total = pages.length;
    var counters = {};
    pages.forEach(function (page, at) {
      var sheet = page.sheet, setup = page.setup, hf = sheet.hf || {};
      var number = at + 1;
      if (setup.first !== null && setup.first !== undefined) {
        counters[sheet.name] = (counters[sheet.name] === undefined ? setup.first : counters[sheet.name] + 1);
        number = counters[sheet.name];
      }
      var head = hf.head, foot = hf.foot;
      if (hf.differentFirst && page.index === 0) { head = hf.firstHead; foot = hf.firstFoot; }
      else if (hf.differentOddEven && number % 2 === 0) { head = hf.evenHead || head; foot = hf.evenFoot || foot; }
      [[head, "top", setup.m.h], [foot, "bottom", setup.m.f]].forEach(function (item) {
        if (!item[0]) return;
        var bar = make("div", "hf", page.el);
        bar.style[item[1]] = px(item[2]) + "px";
        bar.style.left = px(setup.m.l) + "px";
        bar.style.right = px(setup.m.r) + "px";
        bar.style.fontFamily = "Calibri, Arial";
        bar.style.fontSize = px(11) + "px";
        ["left", "center", "right"].forEach(function (side) {
          var part = make("div", "", bar);
          part.style.textAlign = side;
          part.innerHTML = item[0][side] || "";
        });
        Array.prototype.forEach.call(bar.querySelectorAll(".hf-page"), function (el) { el.textContent = String(number); });
        Array.prototype.forEach.call(bar.querySelectorAll(".hf-pages"), function (el) { el.textContent = String(total); });
      });
    });
  }

  function pageRules() {
    var first = pageSizes[0], rules = "";
    pageSizes.forEach(function (size, index) {
      if (size[0] === first[0] && size[1] === first[1]) return;
      var name = "x" + index;
      rules += "@page " + name + " { size: " + (size[0] * K) + "pt " + (size[1] * K) + "pt; margin: 0; }";
      pages[index].el.style.page = name;
    });
    if (rules) {
      var style = document.createElement("style");
      style.textContent = rules;
      document.head.appendChild(style);
    }
  }

  try {
    book.sheets.forEach(layoutSheet);
    headersAndFooters();
    pageRules();
  } catch (error) {
    if (window.console) console.error("Eshab sheets:", error);
    document.body.textContent = "";
    var note = make("pre", "", document.body);
    note.textContent = "Eshab could not lay out this workbook: " + error;
  }
}());
