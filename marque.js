/* ---------------------------------------------------------------
   Marque du centre — kit Accompagna.
   Lit window.LMS_CONFIG.CENTRE (nom, logo, couleur) écrit par
   l'installateur et l'applique aux pages : nom à la place
   d'« Accompagna », logo devant le nom, couleur principale déclinée
   en nuances, icône de l'onglet. Sans CENTRE, rien ne change.
   --------------------------------------------------------------- */
(function () {
  var C = (window.LMS_CONFIG || {}).CENTRE || {};
  if (!C.nom) return;

  function hexVersRvb(h) {
    h = String(h || '').replace('#', '');
    if (h.length === 3) h = h.replace(/(.)/g, '$1$1');
    if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  function melange(rvb, vers, part) {
    return '#' + rvb.map(function (c, i) {
      var v = Math.round(c + (vers[i] - c) * part);
      return ('0' + v.toString(16)).slice(-2);
    }).join('');
  }
  var rvb = hexVersRvb(C.couleur);
  if (rvb) {
    var r = document.documentElement.style;
    r.setProperty('--prune', C.couleur);
    r.setProperty('--prune-fonce', melange(rvb, [0, 0, 0], 0.4));
    r.setProperty('--prune-clair', melange(rvb, [255, 255, 255], 0.88));
    r.setProperty('--rose', melange(rvb, [255, 255, 255], 0.45));
  }

  function remplace(t) { return String(t).replace(/Accompagna/g, C.nom); }

  function appliquer() {
    var mots = document.querySelectorAll('.logo .mot, #menu-titre');
    for (var i = 0; i < mots.length; i++) {
      if (mots[i].textContent.indexOf('Accompagna') >= 0) mots[i].textContent = remplace(mots[i].textContent);
    }
    if (document.title.indexOf('Accompagna') >= 0) document.title = remplace(document.title);
    if (C.logo) {
      var logos = document.querySelectorAll('.logo');
      for (var j = 0; j < logos.length; j++) {
        if (logos[j].querySelector('img.logo-centre')) continue;
        var img = document.createElement('img');
        img.src = C.logo; img.alt = ''; img.className = 'logo-centre';
        img.style.cssText = 'height:1.9em;width:auto;max-width:6em;object-fit:contain;vertical-align:middle';
        logos[j].insertBefore(img, logos[j].firstChild);
      }
      var ico = document.querySelector('link[rel="icon"]');
      if (ico && ico.getAttribute('href') !== C.logo) ico.setAttribute('href', C.logo);
    }
  }

  var enCours = false;
  function surveiller() {
    if (enCours) return;
    enCours = true;
    try { appliquer(); } finally { enCours = false; }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', surveiller);
  else surveiller();
  new MutationObserver(surveiller).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
})();
