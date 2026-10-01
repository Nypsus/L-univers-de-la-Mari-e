# -*- coding: utf-8 -*-
"""
Boutique L'Univers de la Mariée — crée les produits, tarifs et liens de paiement Stripe
et les injecte dans boutique.html.

Usage :
  1. Remplir boutique-articles.json (liste d'articles) :
       [{ "id": "collier-rosace", "nom": "Collier « Rosace »", "cat": "Collier",
          "prix_eur": 45, "photo": "assets/img/boutique/collier-rosace.webp",
          "description": "Dentelle de Calais, fermoir doré." }, ...]
  2. python tools/stripe_links.py
  3. git add -A && git commit && git push   (déploie la boutique)

Le script :
  - réutilise un produit Stripe déjà créé (metadata ref = id) au lieu d'en recréer un ;
  - crée produit + tarif + lien de paiement (mode live du profil LUM) ;
  - réécrit "lien" dans boutique-articles.json et l'objet ARTICLES de boutique.html.
La clé est lue dans %LOCALAPPDATA%\\hermes\\.env (STRIPE_LUM_KEY) et n'est jamais affichée.
"""
import io, os, re, json, urllib.request, urllib.parse, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

def cle():
    env = io.open(os.path.expandvars(r"%LOCALAPPDATA%\hermes\.env"), encoding="utf-8", errors="replace").read()
    return re.search(r"^STRIPE_LUM_KEY=(.+)$", env, re.M).group(1).strip()

KEY = cle()

def api(methode, chemin, params=None):
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request("https://api.stripe.com/v1/" + chemin, data=data,
                                 headers={"Authorization": "Bearer " + KEY,
                                          "Content-Type": "application/x-www-form-urlencoded"},
                                 method=methode)
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        print("ERREUR", chemin, e.code, e.read().decode("utf-8", "replace")[:300])
        raise

def _completion(a):
    """Parametres after_completion selon article physique ou digital."""
    if a.get("digital"):
        return {
            "after_completion[type]": "redirect",
            "after_completion[redirect][url]": a.get("apres_paiement", ""),
            "custom_text[submit][message]": "Après paiement, vous êtes redirigé vers votre guide (imprimable en PDF).",
        }
    return {
        "after_completion[type]": "hosted_confirmation",
        "after_completion[hosted_confirmation][custom_message]": "Merci ! Maryse vous contacte pour confirmer votre pièce et son envoi.",
        "custom_text[submit][message]": "Livraison offerte en France métropolitaine. Pièce faite main à l'atelier.",
    }


def produits_existants():
    r = api("GET", "products?limit=100&active=true")
    return {p.get("metadata", {}).get("ref"): p for p in r.get("data", []) if p.get("metadata", {}).get("ref")}

def main():
    with io.open("boutique-articles.json", encoding="utf-8") as f:
        articles = json.load(f)

    connus = produits_existants()
    for a in articles:
        ref = a["id"]
        if a.get("lien"):
            print("%-24s lien déjà présent : %s" % (ref, a["lien"]))
            continue
        if ref in connus:
            prod = connus[ref]
            print("%-24s produit Stripe existant : %s" % (ref, prod["id"]))
        else:
            prod = api("POST", "products", {
                "name": a["nom"],
                "description": a.get("description", ""),
                "metadata[ref]": ref,
                "metadata[type]": "boutique",
            })
            print("%-24s produit créé : %s" % (ref, prod["id"]))
        prix = api("POST", "prices", {"product": prod["id"], "unit_amount": int(round(a["prix_eur"] * 100)), "currency": "eur"})
        pl = api("POST", "payment_links", {
            "line_items[0][price]": prix["id"],
            "line_items[0][quantity]": 1,
            **_completion(a),
            "metadata[ref]": ref,
            # le ref est aussi posé sur le PAIEMENT lui-même : la livraison
            # e-mail (tools/livraison_email.py) le relit dans payment_intent.metadata.ref
            "payment_intent_data[metadata][ref]": ref,
            "payment_intent_data[metadata][produit]": a["nom"],
        })
        a["lien"] = pl["url"]
        print("%-24s LIEN : %s" % (ref, pl["url"]))

    with io.open("boutique-articles.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    # injection dans boutique.html
    obj = {}
    for a in articles:
        if a.get("lien"):
            obj[a["id"]] = {
                "nom": a["nom"], "cat": a.get("cat", ""),
                "prix": ("%g \u20ac" % a["prix_eur"]).replace(".", ","),
                "photo": a.get("photo", ""), "lien": a["lien"], **({"sans_panier": True} if a.get("sans_panier") else {}),
            }
    h = io.open("boutique.html", encoding="utf-8").read()
    h = re.sub(r"const ARTICLES = \{.*?\};",
               "const ARTICLES = %s;" % json.dumps(obj, ensure_ascii=False, indent=8), h, count=1, flags=re.S)
    io.open("boutique.html", "w", encoding="utf-8", newline="\n").write(h)
    print("\n%d article(s) injecté(s) dans boutique.html — penser à git push." % len(obj))

if __name__ == "__main__":
    main()
