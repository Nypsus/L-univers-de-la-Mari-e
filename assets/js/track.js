/* L'Univers de la Mariée — mesure des conversions, sans cookie.
   Les clics importants (WhatsApp, téléphone, Instagram, Facebook, galerie,
   prise de rendez-vous) sont comptés ici. Les évènements partent vers l'outil
   d'analytics présent sur la page (Umami ou Plausible) et sont poussés dans
   window.dataLayer pour Google Analytics / GTM. Aucun cookie, aucune donnée
   personnelle : seuls des clics sont comptés. */
(function () {
  window.dataLayer = window.dataLayer || [];

  window.lumTrack = function (name, props) {
    props = props || {};
    try { window.dataLayer.push(Object.assign({ event: name, page: location.pathname }, props)); } catch (e) {}
    try { if (window.umami && typeof window.umami.track === 'function') window.umami.track(name, props); } catch (e) {}
    try { if (typeof window.plausible === 'function') window.plausible(name, { props: props }); } catch (e) {}
  };

  document.addEventListener('click', function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
    if (!a) return;
    var href = a.getAttribute('href') || '';
    var label = (a.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60);
    var evt = null;
    if (href.indexOf('wa.me') > -1) evt = 'clic_whatsapp';
    else if (href.indexOf('instagram.com') > -1) evt = 'clic_instagram';
    else if (href.indexOf('facebook.com') > -1) evt = 'clic_facebook';
    else if (href.indexOf('tel:') === 0) evt = 'clic_telephone';
    else if (href.indexOf('vitrine') > -1) evt = 'clic_galerie';
    else if (href.indexOf('#contact') > -1) evt = 'clic_prendre_rdv';
    if (evt) window.lumTrack(evt, { libelle: label, cible: href });
  }, true);
})();
