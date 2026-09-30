/* ZEPHYRA — compteur de visites auto-hébergé (Hyperion, extension 15).
   Mesure RÉELLE du trafic des sites de l'écosystème. Aucun cookie, aucun identifiant,
   aucune donnée personnelle : l'adresse IP est hachée avec un sel quotidien côté serveur
   et n'est jamais conservée en clair.

   - une vue est enregistrée par page ;
   - tout élément portant data-zy-event="<nom>" envoie un ÉVÉNEMENT au clic
     (ex. data-zy-event="whatsapp", "reservation", "contact" → contacts qualifiés réels). */
(function () {
  var ENDPOINT = "https://151.115.77.106.sslip.io/t.gif";
  function siteKey() {
    var h = location.host, parts = location.pathname.split("/").filter(Boolean);
    if (/\.github\.io$/i.test(h) && parts.length) { return h + "/" + parts[0]; }
    return h;
  }
  function send(event) {
    try {
      var i = new Image();
      i.width = 1; i.height = 1; i.alt = "";
      i.referrerPolicy = "no-referrer-when-downgrade";
      i.src = ENDPOINT +
        "?s=" + encodeURIComponent(siteKey()) +
        "&p=" + encodeURIComponent(location.pathname) +
        "&r=" + encodeURIComponent(document.referrer || "") +
        "&e=" + encodeURIComponent(event || "view");
    } catch (e) { /* la mesure ne doit jamais casser la page */ }
  }
  send("view");
  document.addEventListener("click", function (ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest("[data-zy-event]") : null;
    if (el) { send(el.getAttribute("data-zy-event") || "clic"); }
  }, true);
})();
