/* Word's pages, inside Edge.

   docx_layout.py writes a Word file as one flow of paragraphs and tables,
   which prints acceptably on its own. This script then lays that flow out
   the way Word does: real page boxes carrying each section's own header and
   footer (any content, pushing the text down when they are tall), filled
   line by line under Word's rules, with footnotes at the bottom of the page
   that refers to them, columns, and pictures placed relative to the page.

   If anything goes wrong here the plain flow is printed instead. */
(function () {
  "use strict";

  var PX = 96 / 72;             // CSS pixels in a point
  var SLACK = 0.75;             // how far (px) a line may overhang and still fit
  var OVERFLOW = {};            // thrown when a balancing attempt runs out of columns
  var ATOMS = "img,.drawn,.crop,.marker,.at";
  var OUTSIDE = ".anchor,.leader,.floated";

  var setup, flows, flowStyle, noteStore, endnoteStore;
  var pages = [], page = null, band = null, column = null, flowing = null;
  var area = null;              // while a header or footer is placed: the width it measures from
  var fresh = false;            // this column began because the text ran over
  var noteBodies = {}, separator = null;
  var range = document.createRange();
  var trial = null;             // what a balancing attempt has added to the page

  function make(tag, className, parent) {
    var el = document.createElement(tag);
    el.className = className;
    if (parent) parent.appendChild(el);
    return el;
  }

  function pageTop() { return page.el.getBoundingClientRect().top; }

  /* -- pages and their columns ------------------------------------------- */

  function addPage(sect, first) {
    var number = first && sect.start !== null ? sect.start : (page ? page.number + 1 : 1);
    var el = make("div", "page", document.body);
    el.style.width = sect.w + "pt";
    el.style.height = (sect.h - 0.5) + "pt";
    page = {el: el, section: sect, number: number, top: sect.top * PX,
            bottom: (sect.h - sect.bottom) * PX, shared: null, bands: [], exclusions: []};
    pages.push(page);
    var kind = first && sect.titlePg ? "first" : setup.evenOdd && number % 2 === 0 ? "even" : "default";
    addPart(sect.hdr[kind], "hdr");
    addPart(sect.ftr[kind], "ftr");
    startBand(page.top, sect);
  }

  function addPart(id, className) {
    if (id === null || id === undefined) return;
    var sect = page.section;
    var box = make("div", className, page.el);
    box.style.left = sect.left + "pt";
    box.style.width = (sect.w - sect.left - sect.right) + "pt";
    if (className === "hdr") box.style.top = sect.header + "pt";
    else box.style.bottom = sect.footer + "pt";
    box.appendChild(document.getElementById("eshab-part-" + id).content.cloneNode(true));
    fixAllTabs(box);
    area = {left: sect.left * PX, width: (sect.w - sect.left - sect.right) * PX};
    placePartFloats(box);
    var rect = box.getBoundingClientRect(), top = pageTop();
    if (className === "hdr") {
      if (!sect.fixedTop) page.top = Math.max(page.top, rect.bottom - top);
    } else if (!sect.fixedBottom) {
      page.bottom = Math.min(page.bottom, rect.top - top);
    }
    placeAnchors(box);
    pinFloats(box);
    area = null;
  }

  /* Text wraps around what floats in a header or footer, but the page's own
     text does not: the part stays as tall as its lines. */
  function placePartFloats(box) {
    var floats = box.querySelectorAll(".p > .floated");
    if (!floats.length) return;
    Array.prototype.forEach.call(floats, function (float) { placeFloat(float, float.parentNode); });
    var top = box.getBoundingClientRect().top, bottom = top;
    Array.prototype.forEach.call(box.children, function (child) {
      bottom = Math.max(bottom, child.getBoundingClientRect().bottom + (parseFloat(getComputedStyle(child).marginBottom) || 0));
    });
    box.style.height = (bottom - top) + "px";
  }

  function startBand(top, sect) {
    var columns = [], x = 0;
    var inner = sect.w - sect.left - sect.right;
    sect.cols.forEach(function (col) {
      var left = sect.left + (sect.bidi ? inner - x - col.w : x);
      var el = make("div", "col", page.el);
      el.style.top = top + "px";
      el.style.left = left + "pt";
      el.style.width = col.w + "pt";
      columns.push({el: el, left: left * PX, width: col.w * PX, own: null});
      x += col.w + col.gap;
    });
    band = {top: top, columns: columns, index: 0, limit: null, carry: 0};
    page.bands.push(band);
    column = columns[0];
  }

  function nextColumn(natural) {
    fresh = natural;
    if (band.index + 1 < band.columns.length) {
      band.index += 1;
      column = band.columns[band.index];
      return;
    }
    if (trial) throw OVERFLOW;
    addPage(flowing, false);
  }

  function limit() {
    var bottom = page.bottom;
    if (page.shared) bottom -= page.shared.getBoundingClientRect().height;
    if (column.own) bottom -= column.own.getBoundingClientRect().height;
    if (band.limit !== null) bottom = Math.min(bottom, band.limit);
    return pageTop() + bottom;
  }

  /* -- footnotes ----------------------------------------------------------- */

  function newArea(left, width) {
    var el = make("div", "notes-area", page.el);
    el.style.left = left + "px";
    el.style.width = width + "px";
    el.style.bottom = ((page.section.h - 0.5) * PX - page.bottom) + "px";
    return el;
  }

  function noteArea() {
    if (band.columns.length === 1) {
      var sect = page.section;
      if (!page.shared) page.shared = newArea(sect.left * PX, (sect.w - sect.left - sect.right) * PX);
      return page.shared;
    }
    if (!column.own) column.own = newArea(column.left, column.width);
    return column.own;
  }

  function addNote(key) {
    if (!noteBodies[key]) return null;
    var area = noteArea();
    if (!area.firstChild && separator) area.appendChild(separator.cloneNode(true));
    var note = noteBodies[key].cloneNode(true);
    area.appendChild(note);
    fixAllTabs(note);
    if (trial) trial.push(note);
    return note;
  }

  function dropNote(note) {
    if (!note) return;
    var area = note.parentNode;
    note.remove();
    if (area.children.length === 1 && area.firstChild.classList.contains("note-sep")) area.firstChild.remove();
  }

  /* -- tab stops -----------------------------------------------------------

     Only here are real text widths known: each piece of a tabbed line goes
     to the stop Word would choose for it, measured from the paragraph's
     start edge (the right one in Arabic). */

  function fixTabs(el) {
    var info = JSON.parse(el.dataset.tabs);
    var rtl = getComputedStyle(el).direction === "rtl", box = el.getBoundingClientRect();
    function startOf(r) { return rtl ? box.right - r.right : r.left - box.left; }
    function endOf(r) { return rtl ? box.right - r.left : r.right - box.left; }
    function nextStop(x) {
      for (var i = 0; i < info.stops.length; i++) {
        if (info.stops[i][0] > x + 0.5) return info.stops[i];
      }
      return [(Math.floor((x + info.indent) / info.step) + 1) * info.step - info.indent, "start", null];
    }

    var marker = el.querySelector(":scope > .marker.tabbed"), cursor = null;
    if (marker) {
      marker.style.minWidth = "0";
      var rect = marker.getBoundingClientRect(), from = startOf(rect), stop = nextStop(endOf(rect));
      marker.style.minWidth = (stop[0] - from) + "px";
      cursor = stop[0];
    }

    // Tabs in running text (a centred or justified line, or one with line breaks).
    Array.prototype.forEach.call(el.querySelectorAll(":scope > .tab"), function (tab) {
      tab.style.width = "0";
      var x = startOf(tab.getBoundingClientRect());
      tab.style.width = Math.max(0, nextStop(x)[0] - x) + "px";
    });

    var tabs = el.querySelectorAll(":scope > .at");
    if (!tabs.length) return;
    Array.prototype.forEach.call(el.querySelectorAll(":scope > .leader"), function (old) { old.remove(); });
    range.setStart(el, 0);
    range.setEndBefore(tabs[0]);
    var list = range.getClientRects();
    for (var i = 0; i < list.length; i++) {
      if (list[i].width > 0) cursor = Math.max(cursor === null ? -Infinity : cursor, endOf(list[i]));
    }
    if (cursor === null) cursor = parseFloat(getComputedStyle(el).textIndent) || 0;

    Array.prototype.forEach.call(tabs, function (at) {
      at.style.transform = "";
      at.style.insetInlineStart = "0";
      var width = at.getBoundingClientRect().width, stop = nextStop(cursor);
      var shift = {end: 1, decimal: 1, center: 0.5}[stop[1]] || 0, begin = stop[0] - width * shift;
      at.style.insetInlineStart = begin + "px";
      if (stop[2] && begin > cursor) {
        var leader = document.createElement("span");
        leader.className = "leader";
        leader.style.insetInlineStart = cursor + "px";
        leader.style.width = (begin - cursor) + "px";
        leader.style.lineHeight = info.line;
        leader.textContent = stop[2].repeat(Math.ceil((begin - cursor) / 2) + 1);
        el.insertBefore(leader, at);
      }
      cursor = begin + width;
    });
  }

  function fixAllTabs(host) {
    if (host.dataset && host.dataset.tabs) fixTabs(host);
    Array.prototype.forEach.call(host.querySelectorAll("[data-tabs]"), fixTabs);
  }

  /* -- the lines of a paragraph -------------------------------------------- */

  function eachAtom(el, visit) {
    for (var node = el.firstChild; node; node = node.nextSibling) {
      if (node.nodeType === 3) {
        if (node.data) visit(node);
      } else if (node.nodeType === 1 && !node.matches(OUTSIDE)) {
        if (node.matches(ATOMS)) visit(node);
        else eachAtom(node, visit);
      }
    }
  }

  function linesOf(el) {
    var rects = [];
    eachAtom(el, function (node) {
      var list;
      if (node.nodeType === 3) {
        range.selectNodeContents(node);
        list = range.getClientRects();
      } else {
        list = [node.getBoundingClientRect()];
      }
      for (var i = 0; i < list.length; i++) {
        if (list[i].height > 0) rects.push({top: list[i].top, bottom: list[i].bottom});
      }
    });
    rects.sort(function (a, b) { return a.top - b.top; });
    var lines = [];
    rects.forEach(function (r) {
      var last = lines[lines.length - 1];
      if (last && r.top < last.bottom - 0.5 * Math.min(r.bottom - r.top, last.bottom - last.top)) {
        last.top = Math.min(last.top, r.top);
        last.bottom = Math.max(last.bottom, r.bottom);
      } else {
        lines.push({top: r.top, bottom: r.bottom});
      }
    });
    return lines;
  }

  function lineBottom(el, lines, index) {
    return index + 1 < lines.length ? (lines[index].bottom + lines[index + 1].top) / 2
                                    : el.getBoundingClientRect().bottom;
  }

  function refsByLine(el, lines) {
    var byLine = lines.map(function () { return []; });
    var refs = el.querySelectorAll(".note-ref");
    for (var i = 0; i < refs.length; i++) {
      var rect = refs[i].getBoundingClientRect(), middle = (rect.top + rect.bottom) / 2;
      var at = 0;
      while (at + 1 < lines.length && middle > lines[at].bottom) at += 1;
      if (byLine[at]) byLine[at].push(refs[i].dataset.note);
    }
    return byLine;
  }

  function charMiddle(node, index) {
    range.setStart(node, index);
    range.setEnd(node, index + 1);
    var list = range.getClientRects();
    if (!list.length) return null;
    return (list[0].top + list[0].bottom) / 2;
  }

  function findBreak(el, y) {
    var found = null;
    eachAtom(el, function (node) {
      if (found) return;
      if (node.nodeType === 3) {
        range.selectNodeContents(node);
        var list = range.getClientRects(), lowest = -Infinity;
        for (var i = 0; i < list.length; i++) lowest = Math.max(lowest, (list[i].top + list[i].bottom) / 2);
        if (lowest <= y) return;
        var lo = 0, hi = node.length;
        while (lo < hi) {
          var mid = (lo + hi) >> 1, middle = charMiddle(node, mid);
          if (middle === null || middle <= y) lo = mid + 1;
          else hi = mid;
        }
        if (lo < node.length) found = {node: node, offset: lo};
      } else {
        var rect = node.getBoundingClientRect();
        if ((rect.top + rect.bottom) / 2 > y) {
          found = {node: node.parentNode, offset: Array.prototype.indexOf.call(node.parentNode.childNodes, node)};
        }
      }
    });
    return found;
  }

  function splitTree(block, where) {
    var node = where.node, right;
    if (node.nodeType === 3) {
      right = where.offset === 0 ? node : node.splitText(where.offset);
      node = right.parentNode;
    } else {
      right = node.childNodes[where.offset] || null;
    }
    var carried = null;
    for (;;) {
      var clone = node.cloneNode(false);
      if (carried) clone.appendChild(carried);
      while (right) {
        var next = right.nextSibling;
        clone.appendChild(right);
        right = next;
      }
      if (node === block) return clone;
      carried = clone;
      right = node.nextSibling;
      node = node.parentNode;
    }
  }

  /* The lines after `head` go on in a paragraph of their own: the first part
     keeps its justified last line, the rest starts flush with no space. */
  function splitParagraph(el, lines, head) {
    var where = findBreak(el, (lines[head - 1].bottom + lines[head].top) / 2);
    if (!where) return null;
    var tail = splitTree(el, where);
    el.style.marginBottom = "0";
    if (el.style.textAlign === "justify") el.style.textAlignLast = "justify";
    tail.style.marginTop = "0";
    tail.style.textIndent = "";
    tail.style.minHeight = "";
    return tail;
  }

  /* -- placing blocks ------------------------------------------------------- */

  function settle(el) {
    placeAnchors(el);
    pinFloats(el);
  }

  /* Once its paragraph has its place, an object the text wraps round is set on the
     page itself: Edge's printing misplaces what sits inside a float in a
     right-to-left paragraph, and the page keeps it out of the lines' own shifts. */
  function pinFloats(host) {
    var origin = page.el.getBoundingClientRect();
    Array.prototype.forEach.call(host.querySelectorAll(".floated > .float-body"), function (body) {
      var rect = body.getBoundingClientRect();
      body.style.left = (rect.left - origin.left) + "px";
      body.style.top = (rect.top - origin.top) + "px";
      page.el.appendChild(body);
      if (trial) trial.push(body);
    });
  }

  function isKeepNext(el) { return el.style && el.style.breakAfter === "avoid"; }
  function isOnly(el) { return column.el.firstElementChild === el && column.el.lastElementChild === el; }

  function moveOn(el, queue) {
    dropExclusions(el);
    clearGaps(el);
    el.remove();
    nextColumn(true);
    queue.unshift(el);
  }

  function placeParagraph(el, queue) {
    clearGaps(el);
    if (placeFloats(el) && !isOnly(el)) { moveOn(el, queue); return; }
    applyExclusions(el);
    var lines = linesOf(el), total = lines.length;
    if (!total) {
      if (el.getBoundingClientRect().bottom <= limit() + SLACK || isOnly(el)) { settle(el); return; }
      moveOn(el, queue);
      return;
    }
    var refs = refsByLine(el, lines), added = [], count = 0;
    for (var i = 0; i < total; i++) {
      var here = refs[i].map(addNote);
      if (lineBottom(el, lines, i) <= limit() + SLACK) {
        added.push(here);
        count += 1;
      } else {
        here.forEach(dropNote);
        break;
      }
    }
    if (count === total) { settle(el); return; }

    var orphans = Number(el.style.orphans) || 2, widows = Number(el.style.widows) || 2;
    var whole = el.style.breakInside === "avoid" || el.querySelector(".at") !== null;
    var head = whole ? 0 : count;
    if (head && total - head < widows) head = total - widows;
    if (head < orphans) head = 0;
    if (!head && isOnly(el)) {
      // Too tall for any page: it must break somewhere, or overhang.
      if (whole || count < 1) { added.forEach(function (notes) { notes.forEach(dropNote); }); settle(el); return; }
      head = count;
    }
    for (var line = head; line < added.length; line++) added[line].forEach(dropNote);
    if (!head) { moveOn(el, queue); return; }
    var tail = splitParagraph(el, lines, head);
    settle(el);
    nextColumn(true);
    if (tail) queue.unshift(tail);
  }

  /* -- tables ---------------------------------------------------------------- */

  function splitCell(cell, y) {
    var tail = cell.cloneNode(false), moving = false;
    Array.prototype.slice.call(cell.children).forEach(function (child) {
      if (moving) { tail.appendChild(child); return; }
      if (child.getBoundingClientRect().bottom <= y + SLACK) return;
      moving = true;
      if (child.matches(".p")) {
        var lines = linesOf(child), count = 0;
        while (count < lines.length && lineBottom(child, lines, count) <= y + SLACK) count += 1;
        if (count > 0 && count < lines.length) {
          var rest = splitParagraph(child, lines, count);
          if (rest) { tail.appendChild(rest); return; }
        }
      }
      tail.appendChild(child);
    });
    return tail;
  }

  function firstLineFits(cell, y) {
    var first = cell.querySelector(".p");
    if (!first) return false;
    var lines = linesOf(first);
    return lines.length > 0 && lineBottom(first, lines, 0) <= y + SLACK;
  }

  /* A row may break across pages unless Word was told otherwise. */
  function splitRow(row) {
    var cells = Array.prototype.slice.call(row.cells), y = limit();
    if (row.style.breakInside === "avoid" || cells.some(function (cell) { return cell.rowSpan > 1; })) return null;
    if (!cells.some(function (cell) { return firstLineFits(cell, y); })) return null;
    var tail = row.cloneNode(false);
    tail.style.height = "";
    cells.forEach(function (cell) { tail.appendChild(splitCell(cell, y)); });
    return tail;
  }

  /* A cell merged down across the break goes on in the rows below it. */
  function carryMerges(rows, cut, first) {
    if (!first) return;
    rows.slice(0, cut).forEach(function (row, index) {
      Array.prototype.slice.call(row.cells).forEach(function (cell) {
        var kept = cut - index;
        if (cell.rowSpan <= kept) return;
        var rest = cell.cloneNode(false);
        rest.rowSpan = cell.rowSpan - kept;
        cell.rowSpan = kept;
        var at = Number(cell.dataset.col), before = null;
        Array.prototype.forEach.call(first.cells, function (other) {
          if (!before && Number(other.dataset.col) > at) before = other;
        });
        first.insertBefore(rest, before);
      });
    });
  }

  function placeTable(table, queue) {
    var body = table.tBodies[0];
    if (!body) { settle(table); return; }
    var rows = Array.prototype.slice.call(body.rows), fit = 0, added = [];
    for (var i = 0; i < rows.length; i++) {
      var refs = Array.prototype.map.call(rows[i].querySelectorAll(".note-ref"), function (r) { return r.dataset.note; });
      var here = refs.map(addNote);
      if (rows[i].getBoundingClientRect().bottom <= limit() + SLACK) {
        fit += 1;
        added.push(here);
      } else {
        here.forEach(dropNote);
        break;
      }
    }
    if (fit === rows.length) { settle(table); return; }

    var broken = splitRow(rows[fit]);
    if (fit === 0 && !broken) {
      if (!isOnly(table)) {
        table.remove();
        nextColumn(true);
        queue.unshift(table);
        return;
      }
      fit = 1;                  // taller than a page: it overhangs
    }
    var held = broken ? fit + 1 : fit;
    var tail = table.cloneNode(false);
    var columns = table.querySelector(":scope > colgroup");
    if (columns) tail.appendChild(columns.cloneNode(true));
    if (table.tHead) tail.appendChild(table.tHead.cloneNode(true));
    var nextBody = make("tbody", "", tail);
    if (broken) nextBody.appendChild(broken);
    rows.slice(held).forEach(function (row) { nextBody.appendChild(row); });
    if (!nextBody.rows.length) { settle(table); return; }
    carryMerges(rows, held, nextBody.rows[0]);
    settle(table);
    nextColumn(true);
    queue.unshift(tail);
  }

  /* -- the flow ---------------------------------------------------------------- */

  /* What a heading keeps with must start on the same page. */
  function chainFits(first, queue) {
    var chain = [first], at = 0;
    while (isKeepNext(chain[chain.length - 1]) && at < queue.length) {
      if (queue[at].classList.contains("page-break")) return true;
      chain.push(queue[at]);
      at += 1;
    }
    var copies = chain.map(function (el) { return column.el.appendChild(el.cloneNode(true)); });
    copies.forEach(fixAllTabs);
    var last = copies[copies.length - 1], bottom;
    if (last.tagName === "TABLE") {
      var row = last.tBodies[0] && last.tBodies[0].rows[0];
      bottom = (row || last).getBoundingClientRect().bottom;
    } else {
      var lines = linesOf(last);
      bottom = lines.length ? lineBottom(last, lines, Math.min(1, lines.length - 1)) : last.getBoundingClientRect().bottom;
    }
    var fits = bottom <= limit() + SLACK;
    copies.forEach(function (el) { el.remove(); });
    return fits;
  }

  function balanced(queue) {
    var probe = make("div", "col", page.el);
    probe.style.visibility = "hidden";
    probe.style.width = column.width + "px";
    queue.forEach(function (el) { probe.appendChild(el.cloneNode(true)); });
    var height = probe.getBoundingClientRect().height / band.columns.length;
    probe.remove();
    var room = page.bottom - band.top, step = setup.k * 6 * PX;
    if (height > room) return false;
    for (; height <= room + step; height += step) {
      trial = [];
      band.limit = band.top + height;
      try {
        flow(queue.map(function (el) { return el.cloneNode(true); }), false);
        trial = null;
        queue.length = 0;
        return true;
      } catch (error) {
        if (error !== OVERFLOW) throw error;
      }
      trial.forEach(function (el) { el.remove(); });
      trial = null;
      band.columns.forEach(function (col) { col.el.textContent = ""; });
      band.index = 0;
      column = band.columns[0];
      fresh = false;
    }
    band.limit = null;
    return false;
  }

  function flow(queue, balance) {
    while (queue.length) {
      if (balance && !trial && band.index === 0 && !column.el.firstChild && band.columns.length > 1 && balanced(queue)) return;
      var block = queue.shift();
      if (block.classList.contains("page-break")) {
        addPage(flowing, false);
        fresh = false;
        continue;
      }
      if (block.style.breakBefore === "page") {
        block.style.breakBefore = "";
        if (column.el.firstChild) addPage(flowing, false);
        fresh = false;
      }
      if (isKeepNext(block) && column.el.firstChild && !chainFits(block, queue)) nextColumn(true);
      if (!column.el.firstChild) {
        if (fresh && block.matches(".p")) block.style.marginTop = "0";
        else if (band.carry) block.style.marginTop = Math.max(0, (parseFloat(getComputedStyle(block).marginTop) || 0) - band.carry) + "px";
      }
      band.carry = 0;
      fresh = false;
      column.el.appendChild(block);
      fixAllTabs(block);
      if (block.tagName === "TABLE") placeTable(block, queue);
      else placeParagraph(block, queue);
    }
  }

  /* Where a continuous section's text begins: under everything above it. */
  function startContinuous() {
    var top = pageTop(), lowest = band.top, carry = 0;
    band.columns.forEach(function (col) {
      var last = col.el.lastElementChild;
      if (!last) return;
      var margin = parseFloat(getComputedStyle(last).marginBottom) || 0;
      var bottom = last.getBoundingClientRect().bottom - top;
      if (bottom > lowest) { lowest = bottom; carry = margin; }
    });
    // The space after the last paragraph comes first, so all the columns
    // start level; the next paragraph adds only what its own space exceeds.
    startBand(lowest + carry, flowing);
    band.carry = carry;
  }

  function sameSheet(a, b) { return a.w === b.w && a.h === b.h && a.left === b.left && a.right === b.right; }

  function clean(el) {
    var copy = el.cloneNode(true);
    if (copy.dataset.lift) copy.style.top = "";
    Array.prototype.forEach.call(copy.querySelectorAll("[data-lift]"), function (inner) { inner.style.top = ""; });
    return copy;
  }

  function run() {
    flows.forEach(function (source, index) {
      var sect = setup.sections[index], previous = setup.sections[index - 1];
      var queue = Array.prototype.map.call(source.children, clean);
      flowing = sect;
      fresh = false;
      if (!page) {
        addPage(sect, true);
      } else if (sect.type === "continuous" && sameSheet(sect, previous)) {
        startContinuous();
      } else if (sect.type === "nextColumn" && sameSheet(sect, previous) && band.index + 1 < band.columns.length) {
        nextColumn(false);
      } else {
        var number = sect.start !== null ? sect.start : page.number + 1;
        if ((sect.type === "oddPage" && number % 2 === 0) || (sect.type === "evenPage" && number % 2 === 1)) {
          addPage(previous, false);
        }
        addPage(sect, true);
      }
      var following = setup.sections[index + 1];
      flow(queue, sect.cols.length > 1 && following !== undefined && following.type === "continuous");
    });
    if (endnoteStore) {
      var parts = Array.prototype.map.call(endnoteStore.querySelectorAll(".p,table"), clean);
      flow(parts, false);
    }
  }

  /* -- page numbers and finishing ---------------------------------------------- */

  function letters(value) {
    return String.fromCharCode(97 + (value - 1) % 26).repeat(Math.floor((value - 1) / 26) + 1);
  }

  function roman(value) {
    var out = "";
    [[1000, "m"], [900, "cm"], [500, "d"], [400, "cd"], [100, "c"], [90, "xc"], [50, "l"], [40, "xl"],
     [10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"]].forEach(function (pair) {
      while (value >= pair[0]) { out += pair[1]; value -= pair[0]; }
    });
    return out;
  }

  function format(value, style, sectionFormat) {
    var kind = {roman: "lowerRoman", ROMAN: "upperRoman", alphabetic: "lowerLetter", ALPHABETIC: "upperLetter",
                ArabicDash: "numberInDash", Arabic: "decimal"}[style] || sectionFormat || "decimal";
    switch (kind) {
      case "lowerRoman": return roman(value);
      case "upperRoman": return roman(value).toUpperCase();
      case "lowerLetter": return letters(value);
      case "upperLetter": return letters(value).toUpperCase();
      case "numberInDash": return "- " + value + " -";
      case "hindiNumbers": return String(value).replace(/[0-9]/g, function (d) { return String.fromCharCode(0x0660 + Number(d)); });
      case "arabicAbjad": return "أبجدهوزحطيكلمنسعفصقرشتثخذضظغ".charAt((value - 1) % 28);
      case "arabicAlpha": return "أبتثجحخدذرزسشصضطظعغفقكلمنهوي".charAt((value - 1) % 28);
      default: return String(value);
    }
  }

  function fillFields() {
    var inSection = new Map();
    pages.forEach(function (p) { inSection.set(p.section, (inSection.get(p.section) || 0) + 1); });
    pages.forEach(function (p) {
      Array.prototype.forEach.call(p.el.querySelectorAll(".field"), function (field) {
        var kind = field.dataset.field;
        var value = kind === "PAGE" ? p.number : kind === "NUMPAGES" ? pages.length : inSection.get(p.section);
        var target = field;
        while (target.firstElementChild) target = target.firstElementChild;
        target.textContent = format(value, field.dataset.style, kind === "PAGE" ? p.section.fmt : null);
      });
    });
  }

  function drawColumnLines() {
    pages.forEach(function (p) {
      if (!p.section.sep) return;
      p.bands.forEach(function (b) {
        var top = p.el.getBoundingClientRect().top, lowest = b.top;
        b.columns.forEach(function (col) { lowest = Math.max(lowest, col.el.getBoundingClientRect().bottom - top); });
        b.columns.slice(1).forEach(function (col, index) {
          var before = b.columns[index], between = (col.left + col.width + before.left) / 2;
          if (col.left > before.left) between = (before.left + before.width + col.left) / 2;
          var line = make("div", "col-line", p.el);
          line.style.left = between + "px";
          line.style.top = b.top + "px";
          line.style.height = (lowest - b.top) + "px";
        });
      });
    });
  }

  function placeAnchors(host) {
    var anchors = host.querySelectorAll(".anchor");
    for (var i = 0; i < anchors.length; i++) {
      if (!anchors[i].closest(".drawn")) placeAnchor(anchors[i]);   // inside a shape it stays with the shape
    }
  }

  /* Where an anchored object goes, measured from the page's corner. */
  function spotOf(d, block) {
    var s = page.section, W = s.w * PX, H = s.h * PX, L = s.left * PX, R = s.right * PX;
    var T = s.top * PX, B = s.bottom * PX, top = pageTop(), col = area || column;
    var blockTop = block ? block.getBoundingClientRect().top - top : page.top;
    var across = {page: [0, W], margin: [L, W - L - R], leftMargin: [0, L], rightMargin: [W - R, R],
                  insideMargin: [0, L], outsideMargin: [W - R, R]}[d.hrel] || [col.left, col.width];
    var down = {page: [0, H], margin: [T, H - T - B], topMargin: [0, T], bottomMargin: [H - B, B],
                insideMargin: [0, T], outsideMargin: [H - B, B]}[d.vrel] || [blockTop, 0];
    function at(frame, align, offset, size) {
      if (align === "left" || align === "top" || align === "inside") return frame[0];
      if (align === "center") return frame[0] + (frame[1] - size) / 2;
      if (align === "right" || align === "bottom" || align === "outside") return frame[0] + frame[1] - size;
      return frame[0] + Number(offset || 0) * PX;
    }
    return {left: at(across, d.halign, d.hoff, Number(d.w) * PX), top: at(down, d.valign, d.voff, Number(d.h) * PX),
            blockTop: blockTop};
  }

  function placeAnchor(anchor) {
    var spot = spotOf(anchor.dataset, anchor.closest(".p"));
    anchor.style.left = spot.left + "px";
    anchor.style.top = spot.top + "px";
    page.el.appendChild(anchor);
    if (trial) trial.push(anchor);
  }

  /* -- text around objects -------------------------------------------------------

     Word sets each object where its anchor says and lets the text find the free
     parts of every line beside it. Here an object with top-and-bottom wrapping is
     a float from the column's edge, keeping text off its band; any other wrap
     makes a zero-size float that only holds the object until its paragraph is
     placed, and the page remembers what the object takes from the lines. Each
     paragraph then fills, line by line, the parts no object takes (see
     applyExclusions), so objects never push each other about. In a header or
     footer the object is a float from its nearer edge. */

  function polygonOf(d, left, top) {
    if (!d.poly) return null;
    return d.poly.split(" ").map(function (pair) {
      var xy = pair.split(",");
      return [left + Number(xy[0]) * PX, top + Number(xy[1]) * PX];
    });
  }

  /* Where an outline crosses the band from y0 to y1: its leftmost and rightmost x. */
  function spanOf(points, y0, y1) {
    var low = Infinity, high = -Infinity;
    for (var i = 0; i < points.length; i++) {
      var a = points[i], b = points[(i + 1) % points.length];
      if (Math.max(a[1], b[1]) < y0 || Math.min(a[1], b[1]) > y1) continue;
      var from = Math.max(y0, Math.min(a[1], b[1])), to = Math.min(y1, Math.max(a[1], b[1]));
      [from, to].forEach(function (y) {
        var x = a[1] === b[1] ? null : a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]);
        [x === null ? a[0] : x, x === null ? b[0] : x].forEach(function (v) {
          low = Math.min(low, v);
          high = Math.max(high, v);
        });
      });
    }
    return low <= high ? [low, high] : null;
  }

  function placeFloat(box, block) {
    var d = box.dataset;
    if (d.measure && box.firstElementChild) {            // a floating table: as tall as it lays out
      d.h = String(box.firstElementChild.getBoundingClientRect().height / PX);
      d.measure = "";
    }
    var spot = spotOf(d, block), gaps = d.gap.split(" ").map(function (g) { return Number(g) * PX; });
    var col = area || column, w = Number(d.w) * PX, h = Number(d.h) * PX, x = spot.left - col.left, y = spot.top - spot.blockTop;
    var rect = block.getBoundingClientRect(), css = getComputedStyle(block), origin = page.el.getBoundingClientRect();
    var all = d.wrap === "wrapTopAndBottom", side = d.side || "bothSides";
    if (all || area) {
      var roomLeft = x - gaps[3], roomRight = col.width - (x + w + gaps[1]);
      var onLeft = all || side === "right" || (side !== "left" && roomRight >= roomLeft);
      box.style.cssFloat = onLeft ? "left" : "right";
      box.style.height = Math.max(0, y + h + gaps[2]) + "px";
      box.style.shapeOutside = "inset(" + Math.max(0, y - gaps[0]) + "px 0 0 0) border-box";
      if (onLeft) {
        var edge = rect.left - origin.left + parseFloat(css.borderLeftWidth) + parseFloat(css.paddingLeft);
        box.style.width = (all ? col.width : Math.max(0, x + w + gaps[1])) + "px";
        box.style.marginLeft = (col.left - edge) + "px";
        box.style.marginRight = "0";
      } else {
        var far = rect.right - origin.left - parseFloat(css.borderRightWidth) - parseFloat(css.paddingRight);
        box.style.width = Math.max(0, col.width - x + gaps[3]) + "px";
        box.style.marginRight = (far - col.left - col.width) + "px";
        box.style.marginLeft = "0";
      }
    } else {
      box.style.cssFloat = "left";
      box.style.width = box.style.height = "0";
      box.style.marginLeft = box.style.marginRight = "0";
      box.style.shapeOutside = "none";
      var points = polygonOf(d, spot.left, spot.top), reach = points ? spanOf(points, spot.top, spot.top + h) : null;
      var left = reach ? reach[0] : spot.left, right = reach ? reach[1] : spot.left + w;
      if (side === "largest") side = col.left + col.width - right >= left - col.left ? "right" : "left";
      page.exclusions.push({owner: block, column: column, top: spot.top - gaps[0], bottom: spot.top + h + gaps[2],
                            left: left, right: right, points: points, gaps: gaps, side: side,
                            colLeft: col.left, colRight: col.left + col.width});
    }
    var inner = box.firstElementChild, at = box.getBoundingClientRect();
    inner.style.left = (origin.left + spot.left - at.left) + "px";
    inner.style.top = (origin.top + spot.top - at.top) + "px";
    var fixed = area || d.vrel === "page" || d.vrel === "margin" || d.vrel === "topMargin" || d.vrel === "bottomMargin";
    return !fixed && origin.top + spot.top + h > limit() + SLACK;
  }

  function dropExclusions(el) {
    if (page) page.exclusions = page.exclusions.filter(function (ex) { return ex.owner !== el; });
  }

  function clearGaps(el) {
    var gaps = el.querySelectorAll(".wrap-gap");
    if (!gaps.length) return;
    Array.prototype.forEach.call(gaps, function (gap) { gap.remove(); });
    el.normalize();
  }

  /* What an object takes from the band between top and bottom (page px), or null. */
  function takenBy(ex, top, bottom, o) {
    if (bottom <= o.top + ex.top + 0.5 || top >= o.top + ex.bottom - 0.5) return null;
    var left = ex.left, right = ex.right;
    if (ex.points) {
      var part = spanOf(ex.points, Math.max(top - o.top, ex.top + ex.gaps[0]), Math.min(bottom - o.top, ex.bottom - ex.gaps[2]));
      if (!part) return null;
      left = part[0];
      right = part[1];
    }
    left = o.left + left - ex.gaps[3];
    right = o.left + right + ex.gaps[1];
    if (ex.side === "left") return {from: left, to: o.left + ex.colRight + 1, bottom: o.top + ex.bottom};
    if (ex.side === "right") return {from: o.left + ex.colLeft - 1, to: right, bottom: o.top + ex.bottom};
    return {from: left, to: right, bottom: o.top + ex.bottom};
  }

  /* The parts of a line no object takes, in reading order. */
  function freeParts(taken, start, end, rtl) {
    taken.sort(function (a, b) { return a.from - b.from; });
    var parts = [], at = start;
    taken.forEach(function (t) {
      if (t.from > at) parts.push([at, Math.min(t.from, end)]);
      at = Math.max(at, t.to);
    });
    if (at < end) parts.push([at, end]);
    parts = parts.filter(function (p) { return p[1] - p[0] > 1; });
    return rtl ? parts.reverse() : parts;
  }

  /* The text and objects of a paragraph in order, with the gaps already put in. */
  function piecesOf(el) {
    var out = [];
    (function walk(node) {
      for (var child = node.firstChild; child; child = child.nextSibling) {
        if (child.nodeType === 3) { if (child.data) out.push(child); continue; }
        if (child.nodeType !== 1 || child.matches(OUTSIDE)) continue;
        if (child.classList.contains("wrap-gap") || child.matches(ATOMS)) { out.push(child); continue; }
        walk(child);
      }
    })(el);
    return out;
  }

  /* In one line, after the gap `after` (or from the line's start), where the text
     stops fitting before `limit`: the place after the last whole word that fits, or
     the first piece of the part when not even one word does. Null if it all fits. */
  function breakInLine(el, line, limit, rtl, after) {
    var first = null, space = null, started = !after;
    function fits(r) { return rtl ? r.left >= limit - 0.5 : r.right <= limit + 0.5; }
    function inLine(r) { var middle = (r.top + r.bottom) / 2; return middle >= line.top && middle <= line.bottom; }
    var pieces = piecesOf(el);
    for (var p = 0; p < pieces.length; p++) {
      var node = pieces[p];
      if (node.nodeType === 1 && node.classList.contains("wrap-gap")) {
        if (node === after) started = true;
        continue;
      }
      if (!started) continue;
      if (node.nodeType === 1) {
        var box = node.getBoundingClientRect();
        if (box.height <= 0 || !inLine(box)) continue;
        var at = Array.prototype.indexOf.call(node.parentNode.childNodes, node);
        if (!first) first = {node: node.parentNode, offset: at, x: rtl ? box.right : box.left};
        if (!fits(box)) return space || first;
        space = {node: node.parentNode, offset: at + 1, x: rtl ? box.left : box.right};
        continue;
      }
      range.selectNodeContents(node);
      var all = range.getClientRects(), near = false;
      for (var k = 0; k < all.length; k++) if (all[k].bottom >= line.top && all[k].top <= line.bottom) near = true;
      if (!near) continue;
      for (var i = 0; i < node.length; i++) {
        range.setStart(node, i);
        range.setEnd(node, i + 1);
        var rects = range.getClientRects(), r = null, blank = node.data[i] === " " || node.data[i] === "\u00a0";
        for (var j = 0; j < rects.length; j++) if (rects[j].width > 0 || blank) { r = rects[j]; break; }
        if (!r || !inLine(r)) continue;
        if (!first) first = {node: node, offset: i, x: rtl ? r.right : r.left};
        if (blank) { space = {node: node, offset: i + 1, x: rtl ? r.left : r.right}; continue; }
        if (!fits(r)) return space || first;
      }
    }
    return null;
  }

  function putGap(where, width, rtl) {
    var gap = document.createElement("span");
    gap.className = "wrap-gap";
    gap.style.width = Math.max(0, width - 0.5) + "px";
    if (where.node.nodeType === 3) {
      var rest = where.offset < where.node.length ? where.node.splitText(where.offset) : where.node.nextSibling;
      where.node.parentNode.insertBefore(gap, rest);
    } else {
      where.node.insertBefore(gap, where.node.childNodes[where.offset] || null);
    }
    return gap;
  }

  function putBreak(where) {
    var gap = document.createElement("br");
    gap.className = "wrap-gap";
    if (where.node.nodeType === 3) {
      var rest = where.offset < where.node.length ? where.node.splitText(where.offset) : where.node.nextSibling;
      where.node.parentNode.insertBefore(gap, rest);
    } else {
      where.node.insertBefore(gap, where.node.childNodes[where.offset] || null);
    }
  }

  /* Each line of the paragraph that meets an object: its words go into the free
     parts of the line in reading order, a gap jumping each object. A line with no
     free part at all is pushed below the object. */
  function applyExclusions(el) {
    var list = page.exclusions.filter(function (ex) { return ex.column === column; });
    if (!list.length) return;
    var o = page.el.getBoundingClientRect(), box = el.getBoundingClientRect();
    var lowest = Math.max.apply(null, list.map(function (ex) { return o.top + ex.bottom; }));
    if (lowest <= box.top) return;
    var css = getComputedStyle(el), rtl = css.direction === "rtl";
    var start = box.left + parseFloat(css.borderLeftWidth) + parseFloat(css.paddingLeft);
    var end = box.right - parseFloat(css.borderRightWidth) - parseFloat(css.paddingRight);
    for (var index = 0, guard = 0; guard < 400; guard++) {
      var lines = linesOf(el);
      if (index >= lines.length) break;
      var line = lines[index];
      if (line.top >= lowest) break;
      var taken = list.map(function (ex) { return takenBy(ex, line.top, line.bottom, o); }).filter(Boolean);
      if (!taken.length) { index += 1; continue; }
      var parts = freeParts(taken, start, end, rtl);
      var lead = breakInLine(el, line, rtl ? Infinity : -Infinity, rtl, null);
      if (!lead) { index += 1; continue; }
      var below = Math.min.apply(null, taken.map(function (t) { return t.bottom; }));
      if (!parts.length) { skipBelow(lead, line, below); continue; }    // no room beside the object
      // the line's first piece starts the first free part it reaches
      var k = 0, x = lead.x;
      while (k < parts.length && (rtl ? parts[k][0] >= x - 0.5 : parts[k][1] <= x + 0.5)) k += 1;
      if (k >= parts.length) { index += 1; continue; }
      var after = null, filled = false, pushed = null;
      var into = rtl ? x - parts[k][1] : parts[k][0] - x;
      if (into > 0.5) after = putGap(lead, into, rtl);
      for (var step = 0; step < 50; step++) {
        var where = breakInLine(el, line, rtl ? parts[k][0] : parts[k][1], rtl, after);
        if (!where) break;
        if (Math.abs(where.x - (rtl ? parts[k][1] : parts[k][0])) > 1.5) filled = true;
        if (k + 1 < parts.length) {
          after = putGap(where, rtl ? where.x - parts[k + 1][1] : parts[k + 1][0] - where.x, rtl);
          k += 1;
          continue;
        }
        if (!filled) pushed = where;           // not one word fits anywhere on this line
        else if (rtl ? parts[k][0] > start + 1 : parts[k][1] < end - 1) putBreak(where);
        break;
      }
      if (pushed) { skipBelow(pushed, line, below); continue; }
      index += 1;
    }
  }

  /* The rest of a line goes below the objects beside it: a gap as tall as what is
     left of them, then a break. The same line index then holds the moved text. */
  function skipBelow(where, line, below) {
    var skip = putGap(where, 0, false);
    skip.style.verticalAlign = "top";
    skip.style.height = Math.max(0, below - line.top) + "px";
    putBreak({node: skip.parentNode, offset: Array.prototype.indexOf.call(skip.parentNode.childNodes, skip) + 1});
  }

  function placeFloats(el) {
    var boxes = el.querySelectorAll(":scope > .floated"), over = false;
    for (var i = 0; i < boxes.length; i++) {
      if (placeFloat(boxes[i], el)) over = true;
    }
    return over;
  }

  function finish() {
    fillFields();
    drawColumnLines();
    Array.prototype.forEach.call(document.querySelectorAll(".page [data-lift]"), function (el) {
      el.style.top = el.dataset.lift;
    });
    var first = pages[0].section;
    var rules = "@page { size: " + first.w + "pt " + first.h + "pt; margin: 0; }";
    setup.sections.forEach(function (s, index) {
      rules += "@page s" + index + " { size: " + s.w + "pt " + s.h + "pt; margin: 0; }";
    });
    pages.forEach(function (p) {
      if (!sameSheetSize(p.section, first)) p.el.style.page = "s" + setup.sections.indexOf(p.section);
    });
    var style = document.createElement("style");
    style.textContent = rules;
    document.head.appendChild(style);
    if (flowStyle) flowStyle.remove();
    flows.forEach(function (el) { el.remove(); });
    if (noteStore) noteStore.remove();
    if (endnoteStore) endnoteStore.remove();
    Array.prototype.forEach.call(document.querySelectorAll("template"), function (el) { el.remove(); });
  }

  function sameSheetSize(a, b) { return a.w === b.w && a.h === b.h; }

  function start() {
    setup = JSON.parse(document.getElementById("eshab-pages").textContent);
    flows = Array.prototype.slice.call(document.querySelectorAll("body > .section"));
    flowStyle = document.getElementById("eshab-flow");
    noteStore = document.getElementById("eshab-notes");
    endnoteStore = document.getElementById("eshab-endnotes");
    if (noteStore) {
      separator = noteStore.querySelector(".note-sep");
      Array.prototype.forEach.call(noteStore.querySelectorAll(".note"), function (note) {
        noteBodies[note.dataset.note] = note;
      });
    }
    var hidden = flows.concat(noteStore || [], endnoteStore || []);
    hidden.forEach(function (el) { el.style.display = "none"; });
    try {
      run();
      finish();
    } catch (error) {
      pages.forEach(function (p) { p.el.remove(); });
      hidden.forEach(function (el) { el.style.display = ""; });
      if (window.console) console.error("Eshab pages:", error);
    }
  }

  start();
}());
