/* MDL Gestion — JS vanilla (aucune dépendance hormis Chart.js chargé à la demande). */
(function () {
  'use strict';

  var root = document.documentElement;
  var body = document.body;

  function csrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  /* ---------------------------------------------------------------- toasts */
  function toast(message, kind) {
    var box = document.getElementById('toasts');
    if (!box) { return; }
    var el = document.createElement('div');
    el.className = 'toast' + (kind ? ' toast-' + kind : '');
    el.textContent = message;
    box.appendChild(el);
    setTimeout(function () { el.remove(); }, 5200);
  }
  window.mdlToast = toast;

  /* ------------------------------------------------- messages Django → toasts */
  var messages = document.getElementById('django-messages');
  if (messages) {
    Array.prototype.forEach.call(messages.children, function (node) {
      var kind = (node.className.match(/message-(\w+)/) || [])[1];
      toast(node.textContent.trim(), kind === 'error' ? 'error' : kind);
    });
    setTimeout(function () { messages.hidden = true; }, 400);
  }
  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-dismiss]')) {
      var node = event.target.closest('.message');
      if (node) { node.remove(); }
    }
  });

  /* --------------------------------------------------------------- sidebar */
  var collapsed = localStorage.getItem('mdl.sidebar') === 'collapsed';
  if (collapsed) { body.classList.add('sidebar-collapsed'); }
  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-sidebar-toggle]')) {
      body.classList.toggle('sidebar-collapsed');
      localStorage.setItem('mdl.sidebar', body.classList.contains('sidebar-collapsed') ? 'collapsed' : 'open');
    }
    if (event.target.closest('[data-sidebar-open]')) { body.classList.add('sidebar-open'); }
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') { body.classList.remove('sidebar-open'); }
  });

  /* ------------------------------------------------------------------ thème */
  function applyMode(mode) {
    root.setAttribute('data-mode', mode);
    localStorage.setItem('mdl.mode', mode);
  }
  var savedMode = localStorage.getItem('mdl.mode');
  if (savedMode && !root.getAttribute('data-locked')) { applyMode(savedMode); }
  var savedDensity = localStorage.getItem('mdl.density');
  if (savedDensity) { root.setAttribute('data-density', savedDensity); }

  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-mode-toggle]')) {
      var order = ['light', 'dark', 'auto'];
      var current = root.getAttribute('data-mode') || 'light';
      var next = order[(order.indexOf(current) + 1) % order.length];
      applyMode(next);
      persistPrefs({ mode: next });
      toast('Apparence : ' + (next === 'light' ? 'clair' : next === 'dark' ? 'sombre' : 'automatique'));
      redrawCharts();
    }
    if (event.target.closest('[data-density-toggle]')) {
      var density = root.getAttribute('data-density') === 'compacte' ? 'confort' : 'compacte';
      root.setAttribute('data-density', density);
      localStorage.setItem('mdl.density', density);
      persistPrefs({ density: density });
      toast('Densité : ' + density);
    }
    if (event.target.closest('[data-print]')) { window.print(); }
  });

  function persistPrefs(prefs) {
    if (!document.body.classList.contains('with-sidebar')) { return; }
    fetch('/parametres/prefs/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), 'X-Requested-With': 'fetch' },
      body: JSON.stringify(prefs)
    }).catch(function () { /* hors ligne : réglage conservé localement */ });
  }
  window.mdlPrefs = persistPrefs;

  /* ---------------------------------------------------------------- hors ligne */
  function setOffline(state) {
    localStorage.setItem('offline', state ? '1' : '0');
    var existing = document.querySelector('.offline-banner');
    if (state && !existing) {
      var banner = document.createElement('div');
      banner.className = 'offline-banner';
      banner.setAttribute('role', 'alert');
      banner.textContent = 'Vous êtes hors ligne — saisies suspendues. Les pages déjà ouvertes restent consultables.';
      document.body.appendChild(banner);
    } else if (!state && existing) {
      existing.remove();
    }
    Array.prototype.forEach.call(document.querySelectorAll('form button[type=submit], form input[type=submit]'), function (button) {
      button.disabled = state;
      button.title = state ? 'Vous êtes hors ligne : les saisies reprendront à la reconnexion.' : '';
    });
  }
  window.addEventListener('online', function () { setOffline(false); toast('Connexion rétablie', 'success'); });
  window.addEventListener('offline', function () { setOffline(true); });
  if (!navigator.onLine) { setOffline(true); }

  /* ------------------------------------------------------- service worker + PWA */
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/service-worker.js', { scope: '/' }).then(function (registration) {
        registration.addEventListener('updatefound', function () {
          var worker = registration.installing;
          if (!worker) { return; }
          worker.addEventListener('statechange', function () {
            if (worker.state === 'installed' && navigator.serviceWorker.controller) {
              toast('Nouvelle version disponible, rechargez la page.');
              var button = document.createElement('button');
              button.className = 'btn btn-sm btn-primary';
              button.textContent = 'Recharger';
              button.style.marginLeft = '10px';
              button.addEventListener('click', function () {
                worker.postMessage('skip-waiting');
                window.location.reload();
              });
              var last = document.querySelector('#toasts .toast:last-child');
              if (last) { last.appendChild(button); }
            }
          });
        });
      }).catch(function () { /* PWA inactive en HTTP simple */ });
    });
  }

  var deferredPrompt = null;
  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferredPrompt = event;
    var banner = document.getElementById('install-banner');
    if (banner && localStorage.getItem('mdl.install-dismissed') !== '1') { banner.hidden = false; }
  });
  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-install-accept]') && deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function () {
        deferredPrompt = null;
        var banner = document.getElementById('install-banner');
        if (banner) { banner.hidden = true; }
      });
    }
    if (event.target.closest('[data-install-dismiss]')) {
      localStorage.setItem('mdl.install-dismissed', '1');
      var banner = document.getElementById('install-banner');
      if (banner) { banner.hidden = true; }
    }
    if (event.target.closest('[data-clear-cache]')) {
      if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage('clear-cache');
      }
      if (window.caches) {
        caches.keys().then(function (keys) { keys.forEach(function (key) { caches.delete(key); }); });
      }
      toast('Cache vidé', 'success');
    }
  });

  /* ------------------------------------------------------------- formulaires */
  document.addEventListener('submit', function (event) {
    var form = event.target;
    var confirmText = form.getAttribute('data-confirm');
    if (confirmText && !window.confirm(confirmText)) { event.preventDefault(); return; }
    if (!form.hasAttribute('data-ajax')) { return; }
    event.preventDefault();
    var button = form.querySelector('button[type=submit]');
    if (button) { button.disabled = true; }
    fetch(form.action, {
      method: form.method || 'POST',
      body: new FormData(form),
      headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'fetch' }
    }).then(function (response) {
      return response.json().catch(function () { return { ok: response.ok }; });
    }).then(function (data) {
      if (data.message) { toast(data.message, data.ok === false ? 'error' : 'success'); }
      if (data.reload) { window.location.reload(); return; }
      if (data.redirect) { window.location = data.redirect; return; }
      if (data.html && data.target) {
        var target = document.querySelector(data.target);
        if (target) { target.innerHTML = data.html; }
      }
    }).catch(function () { toast('Envoi impossible : vérifiez la connexion.', 'error'); })
      .finally(function () { if (button) { button.disabled = false; } });
  });

  document.addEventListener('change', function (event) {
    if (event.target.matches('[data-autosubmit]')) {
      var form = event.target.closest('form');
      if (form) { form.submit(); }
    }
  });

  /* ------------------------------------------------- robustesse du mot de passe */
  var COMMON = ['motdepasse', 'azerty', 'bonjour', '123456', 'soleil', 'admin', 'mdl', 'password'];
  function scorePassword(value) {
    if (!value) { return 0; }
    var low = value.toLowerCase();
    if (COMMON.some(function (word) { return low.indexOf(word) >= 0; })) { return 0; }
    var score = 0;
    if (value.length >= 10) { score += 1; }
    if (value.length >= 14) { score += 1; }
    var kinds = 0;
    if (/[a-z]/.test(value)) { kinds += 1; }
    if (/[A-Z]/.test(value)) { kinds += 1; }
    if (/[0-9]/.test(value)) { kinds += 1; }
    if (/[^A-Za-z0-9]/.test(value)) { kinds += 1; }
    if (kinds >= 3) { score += 1; }
    if (kinds === 4 && value.length >= 16) { score += 1; }
    return Math.min(score, 4);
  }
  var LABELS = ['Trop faible', 'Faible', 'Correct', 'Bon', 'Excellent'];
  document.addEventListener('input', function (event) {
    var input = event.target;
    if (!input.matches('[data-strength]')) { return; }
    var meter = document.querySelector('[data-strength-meter]');
    var label = document.querySelector('[data-strength-label]');
    if (!meter) { return; }
    var score = scorePassword(input.value);
    Array.prototype.forEach.call(meter.children, function (bar, index) {
      bar.className = index < score ? 'on-' + score : '';
    });
    if (label) { label.textContent = input.value ? LABELS[score] : ''; }
  });

  /* ---------------------------------------------------------------- graphiques */
  function chartColors() {
    var style = getComputedStyle(root);
    var colors = [];
    for (var i = 1; i <= 8; i += 1) {
      var value = style.getPropertyValue('--chart-' + i).trim();
      if (value) { colors.push(value); }
    }
    if (!colors.length) { colors = ['#33556e', '#a76a43', '#2c6f52', '#96700f', '#3a6d94', '#7a4f6d', '#5c7f99', '#c2a878']; }
    return colors;
  }
  function semanticColor(name, fallback) {
    return getComputedStyle(root).getPropertyValue('--' + name).trim() || fallback;
  }
  var charts = [];
  function drawCharts() {
    if (typeof window.Chart === 'undefined') { return; }
    var palette = chartColors();
    Array.prototype.forEach.call(document.querySelectorAll('canvas[data-chart]'), function (canvas) {
      if (canvas.dataset.drawn === '1') { return; }
      canvas.dataset.drawn = '1';
      var spec;
      try { spec = JSON.parse(canvas.getAttribute('data-chart')); } catch (e) { return; }
      var text = semanticColor('text', '#1d2732');
      var border = semanticColor('border', '#d3dbe3');
      var datasets = (spec.series || []).map(function (serie, index) {
        var color = serie.css ? semanticColor(serie.css, palette[index % palette.length]) : palette[index % palette.length];
        return {
          label: serie.label || '',
          data: serie.data || [],
          backgroundColor: spec.type === 'line' ? color + '33' : color,
          borderColor: color,
          borderWidth: spec.type === 'line' ? 2 : 1,
          fill: spec.type === 'line',
          tension: 0.25
        };
      });
      charts.push(new window.Chart(canvas.getContext('2d'), {
        type: spec.type || 'bar',
        data: { labels: spec.labels || [], datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { display: (spec.series || []).length > 1 && spec.type !== 'doughnut', position: 'bottom',
                      labels: { color: text, boxWidth: 10, font: { size: 10 } } },
            tooltip: { enabled: true }
          },
          scales: spec.type === 'doughnut' ? {} : {
            x: { ticks: { color: text, font: { size: 9 } }, grid: { color: border } },
            y: { ticks: { color: text, font: { size: 9 } }, grid: { color: border }, beginAtZero: true }
          }
        }
      }));
    });
  }
  function redrawCharts() {
    charts.forEach(function (chart) { chart.destroy(); });
    charts = [];
    Array.prototype.forEach.call(document.querySelectorAll('canvas[data-chart]'), function (canvas) {
      canvas.dataset.drawn = '0';
    });
    drawCharts();
  }
  if (typeof window.Chart !== 'undefined') { drawCharts(); }
  else {
    window.addEventListener('load', function () { setTimeout(drawCharts, 60); });
  }

  /* ------------------------------------------------------------ divers clics */
  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-confirm-click]');
    if (button && !window.confirm(button.getAttribute('data-confirm-click'))) {
      event.preventDefault();
      event.stopPropagation();
    }
    var copy = event.target.closest('[data-copy]');
    if (copy) {
      var value = copy.getAttribute('data-copy');
      if (navigator.clipboard) {
        navigator.clipboard.writeText(value).then(function () { toast('Copié dans le presse-papiers', 'success'); });
      }
    }
  });
})();

/* ---------------------------------------------------- modales et push (greffon) */
(function () {
  'use strict';
  document.addEventListener('click', function (event) {
    var opener = event.target.closest('[data-open-modal]');
    if (opener) {
      var dialog = document.getElementById(opener.getAttribute('data-open-modal'));
      if (dialog && dialog.showModal) { dialog.showModal(); }
    }
    var closer = event.target.closest('[data-close-modal]');
    if (closer) {
      var open = closer.closest('dialog');
      if (open && open.close) { open.close(); }
    }
    if (event.target.closest('[data-request-push]')) {
      if (!('Notification' in window)) { window.mdlToast('Ce navigateur ne gère pas les notifications.', 'error'); return; }
      Notification.requestPermission().then(function (state) {
        if (state !== 'granted') { window.mdlToast('Notifications refusées : vous garderez le badge et l\'e-mail.', 'error'); return; }
        if (!('serviceWorker' in navigator) || !window.PushManager) { window.mdlToast('Push indisponible sur ce navigateur.', 'error'); return; }
        navigator.serviceWorker.ready.then(function (registration) {
          return fetch('/notifications/vapid/').then(function (r) { return r.json(); }).then(function (data) {
            return registration.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: data.key
            });
          });
        }).then(function (subscription) {
          return fetch('/notifications/push/abonner/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content, 'X-Requested-With': 'fetch' },
            body: JSON.stringify(subscription.toJSON())
          });
        }).then(function () { window.mdlToast('Notifications activées sur cet appareil', 'success'); })
          .catch(function () { window.mdlToast('Abonnement impossible (clés VAPID absentes ?).', 'error'); });
      });
    }
    if (event.target.closest('[data-keep-offline]')) {
      var url = event.target.closest('[data-keep-offline]').getAttribute('data-keep-offline');
      if (window.caches) {
        caches.open('mdl-offline').then(function (cache) {
          return cache.add(url);
        }).then(function () { window.mdlToast('Document conservé hors ligne', 'success'); })
          .catch(function () { window.mdlToast('Impossible de conserver ce document.', 'error'); });
      }
    }
  });
})();

/* ---------------------------------------------------------------- glisser-déposer */
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    var form = document.querySelector('form[data-dropzone]');
    var zone = document.querySelector('[data-dropzone-target]');
    if (!form || !zone) { return; }
    var input = form.querySelector('input[type=file]');
    ['dragenter', 'dragover'].forEach(function (name) {
      zone.addEventListener(name, function (event) { event.preventDefault(); zone.classList.add('is-over'); });
    });
    ['dragleave', 'drop'].forEach(function (name) {
      zone.addEventListener(name, function (event) { event.preventDefault(); zone.classList.remove('is-over'); });
    });
    zone.addEventListener('drop', function (event) {
      if (!input || !event.dataTransfer) { return; }
      input.files = event.dataTransfer.files;
      var label = zone.querySelector('p');
      if (label) { label.textContent = event.dataTransfer.files.length + ' fichier(s) prêt(s) à être déposé(s).'; }
    });
  });
})();
