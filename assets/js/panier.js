/* Panier de la boutique — L'Univers de la Mariée
   - mémorise le panier dans le navigateur (localStorage)
   - affiche un panier latéral + un bouton flottant
   - « Passer commande » appelle la fonction Netlify /api/create-checkout (paiement groupé Stripe)
   - si la fonction n'est pas encore activée, on retombe sur les liens « Acheter maintenant » de chaque fiche */
(function () {
  var CLE = 'lum_panier';

  function articles() {
    try { return (typeof ARTICLES !== 'undefined' && ARTICLES) ? ARTICLES : {}; } catch (e) { return {}; }
  }
  function panier() {
    try { return JSON.parse(localStorage.getItem(CLE) || '[]'); } catch (e) { return []; }
  }
  function sauver(p) { localStorage.setItem(CLE, JSON.stringify(p)); maj(); }
  function euros(a) { var v = parseFloat(String(a.prix).replace(',', '.')); return isNaN(v) ? 0 : v; }

  function creerInterface() {
    if (document.getElementById('panier')) return;
    var b = document.createElement('button');
    b.id = 'btn-panier';
    b.className = 'btn-luxe fixed bottom-6 right-6 z-40 rounded-full px-6 py-4 shadow-xl uppercase tracking-widest font-bold text-xs';
    b.style.display = 'none';
    b.onclick = ouvrir;
    b.innerHTML = 'Panier (<span id="nb-panier">0</span>)';
    document.body.appendChild(b);

    var voile = document.createElement('div');
    voile.id = 'panier-voile';
    voile.style.display = 'none';
    voile.className = 'fixed inset-0 bg-black/50 z-[90]';
    voile.onclick = fermer;
    document.body.appendChild(voile);

    var p = document.createElement('aside');
    p.id = 'panier';
    p.className = 'fixed top-0 right-0 h-full w-full max-w-md bg-[#faf9f6] z-[100] shadow-2xl p-8 flex flex-col translate-x-full transition-transform duration-500';
    p.innerHTML =
      '<button onclick="LumPanier.fermer()" class="self-end text-3xl text-[#d4af37]">&times;</button>' +
      '<h3 class="font-amour text-3xl gold-static mb-6">Votre panier</h3>' +
      '<div id="panier-lignes" class="flex-1 overflow-auto text-sm"></div>' +
      '<div class="border-t border-[#e8e3d8] pt-4 mt-4">' +
      '<p class="flex justify-between font-luxe mb-4"><span>Total</span><span id="panier-total">0 €</span></p>' +
      '<button onclick="LumPanier.commander()" class="btn-luxe block w-full text-center py-4 uppercase tracking-widest font-bold text-sm">Passer commande</button>' +
      '<p id="panier-erreur" style="display:none" class="text-xs text-red-500 mt-3"></p>' +
      '<p class="text-[10px] text-gray-400 uppercase tracking-widest mt-3 text-center">Paiement sécurisé par Stripe &middot; Livraison offerte en France</p>' +
      '</div>';
    document.body.appendChild(p);
  }

  function maj() {
    creerInterface();
    var p = panier(), A = articles(), total = 0;
    var nb = document.getElementById('nb-panier');
    if (nb) nb.textContent = p.length;
    var bouton = document.getElementById('btn-panier');
    if (bouton) bouton.style.display = p.length ? '' : 'none';
    var lignes = document.getElementById('panier-lignes');
    if (lignes) {
      lignes.innerHTML = p.map(function (id, i) {
        var a = A[id];
        if (!a) return '';
        total += euros(a);
        return '<div class="flex items-center gap-3 py-3 border-b border-[#eee]">' +
          '<img src="' + a.photo + '" alt="" class="w-14 h-14 object-cover rounded">' +
          '<div class="flex-1"><p class="font-amour text-lg">' + a.nom + '</p><p class="text-gray-500 text-xs">' + a.prix + '</p></div>' +
          '<button onclick="LumPanier.retirer(' + i + ')" class="text-[#d4af37] text-xl">&times;</button></div>';
      }).join('') || '<p class="text-gray-400">Votre panier est vide.</p>';
    }
    var t = document.getElementById('panier-total');
    if (t) t.textContent = total.toFixed(0) + ' €';
  }

  function ouvrir() { creerInterface(); maj(); document.getElementById('panier').classList.remove('translate-x-full'); document.getElementById('panier-voile').style.display = ''; }
  function fermer() { document.getElementById('panier').classList.add('translate-x-full'); document.getElementById('panier-voile').style.display = 'none'; }
  function ajouter(id) { if (!articles()[id]) return; var p = panier(); p.push(id); sauver(p); ouvrir(); }
  function retirer(i) { var p = panier(); p.splice(i, 1); sauver(p); }

  function commander() {
    var err = document.getElementById('panier-erreur');
    var p = panier();
    if (!p.length) return;
    err.style.display = 'none';
    fetch('/api/create-checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: p })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.url) { window.location.href = d.url; return; }
      throw new Error((d && d.error) || 'réponse inattendue');
    }).catch(function (e) {
      err.textContent = "Le paiement groupé n'est pas encore activé — utilisez « Acheter maintenant » sous chaque pièce. (" + e.message + ")";
      err.style.display = '';
    });
  }

  window.LumPanier = { ouvrir: ouvrir, fermer: fermer, ajouter: ajouter, retirer: retirer, commander: commander, maj: maj };

  document.addEventListener('DOMContentLoaded', function () {
    maj();
    if (location.search.indexOf('commande=ok') >= 0) {
      localStorage.setItem(CLE, '[]'); maj();
      setTimeout(function () { alert("Merci ! Votre commande est confirmée — Maryse vous contacte pour l'envoi."); }, 400);
    }
    if (location.search.indexOf('commande=annulee') >= 0) {
      setTimeout(function () { alert('Paiement annulé — votre panier est conservé.'); }, 400);
    }
  });
})();
