// Netlify Function — crée une session Stripe Checkout pour le panier de la boutique.
// La clé secrète reste côté serveur (variable d'environnement Netlify STRIPE_SECRET_KEY).
// Entrée : { "items": ["collier-rosace", "ceinture-eclat"] }  (identifiants d'articles)
// Sortie  : { "url": "https://checkout.stripe.com/..." }

const ARTICLES = require('./articles.json');

exports.handler = async (event) => {
  const headers = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': 'https://luniversdelamariee.com',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
  if (event.httpMethod === 'OPTIONS') return { statusCode: 204, headers, body: '' };
  if (event.httpMethod !== 'POST') return { statusCode: 405, headers, body: JSON.stringify({ error: 'POST only' }) };

  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) {
    return { statusCode: 500, headers, body: JSON.stringify({ error: 'STRIPE_SECRET_KEY manquant dans les variables Netlify' }) };
  }

  let corps;
  try {
    corps = JSON.parse(event.body || '{}');
  } catch (e) {
    return { statusCode: 400, headers, body: JSON.stringify({ error: 'JSON invalide' }) };
  }
  const demandes = Array.isArray(corps.items) ? corps.items.slice(0, 20) : [];
  const lignes = demandes.map((id) => ARTICLES[id]).filter(Boolean);
  if (!lignes.length) return { statusCode: 400, headers, body: JSON.stringify({ error: 'Aucun article valide' }) };

  const params = new URLSearchParams();
  params.set('mode', 'payment');
  params.set('success_url', 'https://luniversdelamariee.com/boutique.html?commande=ok');
  params.set('cancel_url', 'https://luniversdelamariee.com/boutique.html?commande=annulee');
  params.set('locale', 'fr');
  params.set('shipping_address_collection[allowed_countries][0]', 'FR');
  params.set('shipping_address_collection[allowed_countries][1]', 'BE');
  params.set('shipping_address_collection[allowed_countries][2]', 'LU');
  params.set('shipping_address_collection[allowed_countries][3]', 'CH');
  params.set('custom_text[submit][message]', 'Livraison offerte en France métropolitaine. Pièce faite main à l\'atelier.');
  lignes.forEach((l, i) => {
    params.set(`line_items[${i}][price]`, l.price);
    params.set(`line_items[${i}][quantity]`, '1');
  });

  try {
    const r = await fetch('https://api.stripe.com/v1/checkout/sessions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/x-www-form-urlencoded' },
      body: params.toString(),
    });
    const data = await r.json();
    if (!r.ok) {
      return { statusCode: 502, headers, body: JSON.stringify({ error: (data.error && data.error.message) || 'Erreur Stripe' }) };
    }
    return { statusCode: 200, headers, body: JSON.stringify({ url: data.url }) };
  } catch (e) {
    return { statusCode: 500, headers, body: JSON.stringify({ error: String(e) }) };
  }
};
