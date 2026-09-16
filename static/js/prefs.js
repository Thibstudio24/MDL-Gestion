/* prefs.js — applique palette / mode / densité avant le premier rendu (anti-flash).
   Utilisé sur les écrans sans session (connexion, invitation) et par l'installeur. */
(function () {
  'use strict';
  var root = document.documentElement;
  var stored = {
    palette: localStorage.getItem('mdl.palette'),
    mode: localStorage.getItem('mdl.mode'),
    density: localStorage.getItem('mdl.density')
  };
  if (stored.palette && !root.getAttribute('data-palette-locked')) { root.setAttribute('data-palette', stored.palette); }
  if (stored.mode && !root.getAttribute('data-mode-locked')) { root.setAttribute('data-mode', stored.mode); }
  if (stored.density) { root.setAttribute('data-density', stored.density); }

  function bindPreview() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-palette-choice]'), function (choice) {
      choice.addEventListener('click', function () {
        var name = choice.getAttribute('data-palette-choice');
        root.setAttribute('data-palette', name);
        localStorage.setItem('mdl.palette', name);
        Array.prototype.forEach.call(document.querySelectorAll('[data-palette-choice]'), function (other) {
          other.classList.toggle('is-active', other === choice);
        });
        var input = document.querySelector('input[name="palette"]');
        if (input) { input.value = name; }
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-mode-choice]'), function (choice) {
      choice.addEventListener('click', function () {
        var mode = choice.getAttribute('data-mode-choice');
        root.setAttribute('data-mode', mode);
        localStorage.setItem('mdl.mode', mode);
        Array.prototype.forEach.call(document.querySelectorAll('[data-mode-choice]'), function (other) {
          other.classList.toggle('is-active', other === choice);
        });
      });
    });
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', bindPreview); }
  else { bindPreview(); }
})();
