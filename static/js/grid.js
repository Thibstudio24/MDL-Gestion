/* grid.js — grilles de disponibilités (clic, glisser, tout cocher, copie Q1→Q2). */
(function () {
  'use strict';

  function table() { return document.querySelector('[data-grid]'); }
  function saveUrl() { var node = table(); return node ? node.getAttribute('data-grid') : null; }

  function csrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function cellKey(cell) {
    return {
      week: cell.getAttribute('data-week'),
      weekday: cell.getAttribute('data-weekday'),
      slot: cell.getAttribute('data-slot'),
      evening: cell.getAttribute('data-evening') === '1'
    };
  }

  function setCell(cell, on) {
    if (cell.classList.contains('disabled')) { return false; }
    cell.setAttribute('aria-pressed', on ? 'true' : 'false');
    cell.classList.toggle('is-on', !!on);
    cell.textContent = on ? (cell.getAttribute('data-label') || '✓') : '';
    return true;
  }

  function collect() {
    var out = [];
    Array.prototype.forEach.call(document.querySelectorAll('[data-grid] td.slot[aria-pressed="true"]'), function (cell) {
      out.push(cellKey(cell));
    });
    return out;
  }

  var painting = false;
  var paintValue = true;

  document.addEventListener('mousedown', function (event) {
    var cell = event.target.closest('[data-grid] td.slot');
    if (!cell) { return; }
    painting = true;
    paintValue = cell.getAttribute('aria-pressed') !== 'true';
    setCell(cell, paintValue);
    event.preventDefault();
  });
  document.addEventListener('mouseover', function (event) {
    if (!painting) { return; }
    var cell = event.target.closest('[data-grid] td.slot');
    if (cell) { setCell(cell, paintValue); }
  });
  document.addEventListener('mouseup', function () {
    if (!painting) { return; }
    painting = false;
    autosave();
  });
  document.addEventListener('keydown', function (event) {
    var cell = event.target.closest && event.target.closest('[data-grid] td.slot');
    if (!cell) { return; }
    if (event.key === ' ' || event.key === 'Enter') {
      setCell(cell, cell.getAttribute('aria-pressed') !== 'true');
      autosave();
      event.preventDefault();
    }
  });

  document.addEventListener('click', function (event) {
    var all = event.target.closest('[data-grid-day-all]');
    if (all) {
      var weekday = all.getAttribute('data-grid-day-all');
      Array.prototype.forEach.call(document.querySelectorAll('[data-grid] td.slot[data-weekday="' + weekday + '"]'), function (cell) {
        if (!cell.classList.contains('disabled')) { setCell(cell, true); }
      });
      autosave();
    }
    var none = event.target.closest('[data-grid-day-none]');
    if (none) {
      var day = none.getAttribute('data-grid-day-none');
      Array.prototype.forEach.call(document.querySelectorAll('[data-grid] td.slot[data-weekday="' + day + '"]'), function (cell) {
        setCell(cell, false);
      });
      autosave();
    }
    var copy = event.target.closest('[data-grid-copy]');
    if (copy) {
      var from = copy.getAttribute('data-grid-copy');
      var to = from === 'Q1' ? 'Q2' : 'Q1';
      var map = {};
      Array.prototype.forEach.call(document.querySelectorAll('[data-grid] td.slot[data-week="' + from + '"][aria-pressed="true"]'), function (cell) {
        map[cell.getAttribute('data-weekday') + '|' + cell.getAttribute('data-slot') + '|' + cell.getAttribute('data-evening')] = true;
      });
      Array.prototype.forEach.call(document.querySelectorAll('[data-grid] td.slot[data-week="' + to + '"]'), function (cell) {
        var key = cell.getAttribute('data-weekday') + '|' + cell.getAttribute('data-slot') + '|' + cell.getAttribute('data-evening');
        setCell(cell, !!map[key]);
      });
      autosave();
      if (window.mdlToast) { window.mdlToast('Semaine ' + to + ' alignée sur la semaine ' + from, 'success'); }
    }
    if (event.target.closest('[data-grid-save]')) { save(true); }
  });

  var timer = null;
  function autosave() {
    updateCounter();
    if (!saveUrl()) { return; }
    clearTimeout(timer);
    timer = setTimeout(function () { save(false); }, 700);
  }

  function updateCounter() {
    var counter = document.querySelector('[data-grid-count]');
    if (counter) { counter.textContent = collect().length; }
  }

  function save(explicit) {
    var url = saveUrl();
    if (!url) { return; }
    var button = document.querySelector('[data-grid-save]');
    if (button) { button.disabled = true; }
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), 'X-Requested-With': 'fetch' },
      body: JSON.stringify({ slots: collect() })
    }).then(function (response) { return response.json(); }).then(function (data) {
      if (data.ok === false) {
        if (window.mdlToast) { window.mdlToast(data.message || 'Enregistrement refusé', 'error'); }
      } else if (explicit && window.mdlToast) {
        window.mdlToast('Disponibilités enregistrées', 'success');
      }
    }).catch(function () {
      if (window.mdlToast) { window.mdlToast('Hors ligne : enregistrement reporté', 'error'); }
    }).finally(function () { if (button) { button.disabled = false; } });
  }

  document.addEventListener('DOMContentLoaded', updateCounter);
})();
