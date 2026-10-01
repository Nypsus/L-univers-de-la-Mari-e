# -*- coding: utf-8 -*-
"""
Notifications de vente L'Univers de la Mariée → Telegram + livraison e-mail.

Surveille les paiements Stripe (Payment Intents). Pour chaque nouvelle commande payée :
  1. envoie à l'acheteuse son e-mail de livraison (lien de téléchargement) si le produit
     est connu dans tools/livraison.json — via tools/livraison_email.py ;
  2. notifie l'utilisateur sur Telegram.
Conçu pour tourner via le Planificateur de tâches Windows (aucun agent, aucun coût) —
état dans tools/.sales_state.json.

Secrets lus dans %LOCALAPPDATA%\\hermes\\.env :
  STRIPE_LUM_KEY      (clé restreinte — doit avoir « Payment Intents : Lecture »)
  TELEGRAM_BOT_TOKEN  (bot Hermes)
  TELEGRAM_HOME_CHANNEL (chat de l'utilisateur)
Le mot de passe e-mail vient du coffre HSB (voir tools/livraison_email.py).

Test de la livraison seule :
  python tools/stripe_sales_notify.py --test adresse@exemple.fr
"""
import io, os, re, json, sys, urllib.request, urllib.parse, urllib.error, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import livraison_email  # noqa: E402

ETAT = os.path.join(ROOT, "tools", ".sales_state.json")
LOG = os.path.join(ROOT, "tools", ".sales_notify.log")
PREFIX = "\U0001F381 L'UNIVERS DE LA MARI\u00c9E \u2014"


def env():
    p = os.path.expandvars(r"%LOCALAPPDATA%\hermes\.env")
    d = {}
    for ligne in io.open(p, encoding="utf-8", errors="replace"):
        m = re.match(r"^([A-Z_]+)=(.*)$", ligne.strip())
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def log(msg):
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


def telegram(token, chat, texte):
    data = urllib.parse.urlencode({"chat_id": chat, "text": texte, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=data)
    return json.load(urllib.request.urlopen(req, timeout=30))


def stripe_get(key, chemin):
    req = urllib.request.Request("https://api.stripe.com/v1/" + chemin, headers={"Authorization": "Bearer " + key})
    return json.load(urllib.request.urlopen(req, timeout=30))


def lire_etat():
    if os.path.exists(ETAT):
        e = json.load(io.open(ETAT, encoding="utf-8"))
        e.setdefault("emails", {})
        return e
    return {"vus": [], "depuis": None, "alerte_permission_envoyee": False, "emails": {}}


def ecrire_etat(e):
    io.open(ETAT, "w", encoding="utf-8", newline="\n").write(json.dumps(e, ensure_ascii=False, indent=2))


def main():
    # Test de livraison seule (ne touche pas à Stripe) : --test adresse[@domaine] [ref]
    if "--test" in sys.argv:
        i = sys.argv.index("--test")
        adresse = sys.argv[i + 1] if len(sys.argv) > i + 1 else ""
        ref = sys.argv[i + 2] if len(sys.argv) > i + 2 else "guide-robe-de-mariee"
        ok, det = livraison_email.envoyer_livraison(adresse, "Test", ref)
        print(("OK " if ok else "ECHEC ") + det + " -> " + adresse)
        return 0

    e = env()
    key, token, chat = e.get("STRIPE_LUM_KEY"), e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_HOME_CHANNEL")
    if not (key and token and chat):
        log("secrets manquants"); return 1
    etat = lire_etat()
    depuis = etat.get("depuis") or int((datetime.datetime.now() - datetime.timedelta(days=1)).timestamp())
    try:
        r = stripe_get(key, "payment_intents?limit=100&created[gte]=%d" % depuis)
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode("utf-8", "replace")[:200]
        if ex.code == 403 and not etat.get("alerte_permission_envoyee"):
            telegram(token, chat, "%s \u26a0\ufe0f Surveillance des ventes : la cl\u00e9 Stripe n'a pas la permission "
                                  "\u00ab Payment Intents : Lecture \u00bb. Ajoute-la (Stripe \u2192 D\u00e9veloppeurs \u2192 Cl\u00e9s API \u2192 modifier la cl\u00e9) "
                                  "et les notifications de commande partiront ici automatiquement." % PREFIX)
            etat["alerte_permission_envoyee"] = True
            ecrire_etat(etat)
        log("erreur API %s %s" % (ex.code, detail))
        return 1
    nouvelles = 0
    max_ts = depuis
    for pi in r.get("data", []):
        max_ts = max(max_ts, pi.get("created", depuis))
        if pi.get("id") in etat["vus"] or pi.get("status") != "succeeded":
            continue
        montant = (pi.get("amount_received") or pi.get("amount") or 0) / 100.0
        ref = (pi.get("metadata") or {}).get("ref", "")
        email = pi.get("receipt_email") or ((pi.get("charges", {}).get("data") or [{}])[0].get("billing_details", {}) or {}).get("email") or "?"
        nom = ((pi.get("charges", {}).get("data") or [{}])[0].get("billing_details", {}) or {}).get("name") or "?"

        # 1) Livraison e-mail à l'acheteuse (une seule fois par paiement, seulement si OK)
        livraison_txt = ""
        if email and email != "?" and ref:
            emails = etat.setdefault("emails", {})
            deja = emails.get(pi.get("id")) or {}
            if deja.get("ok"):
                livraison_txt = "\n\u2022 Livraison e-mail : d\u00e9j\u00e0 envoy\u00e9e \u2714"
            else:
                ok, det = livraison_email.envoyer_livraison(email, nom, ref)
                emails[pi.get("id")] = {"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "to": email, "ok": ok, "detail": det}
                ecrire_etat(etat)
                log("email %s -> %s (%s)" % ("OK" if ok else "ECHEC", email, det))
                livraison_txt = "\n\u2022 Livraison e-mail : %s" % ("envoy\u00e9e \u00e0 l'acheteuse \u2714" if ok else "\u26a0 " + det)
        elif ref:
            livraison_txt = "\n\u2022 Livraison e-mail : adresse de l'acheteuse absente \u2014 \u00e0 envoyer \u00e0 la main"

        # 2) Notification Telegram à l'utilisateur
        texte = ("%s \U0001F4B0 <b>Nouvelle commande pay\u00e9e</b>\n"
                 "\u2022 Montant : <b>%.2f \u20ac</b>\n"
                 "\u2022 Pi\u00e8ce : %s\n"
                 "\u2022 Client : %s (%s)\n"
                 "\u2022 Paiement : https://dashboard.stripe.com/payments/%s"
                 "%s") % (PREFIX, montant, ref or "voir Stripe", nom, email, pi.get("id"), livraison_txt)
        try:
            telegram(token, chat, texte)
            etat["vus"].append(pi.get("id"))
            nouvelles += 1
            log("notifi\u00e9 %s %.2f\u20ac" % (pi.get("id"), montant))
        except Exception as ex:
            log("erreur telegram %s" % ex)
    etat["depuis"] = max_ts
    etat["vus"] = etat["vus"][-200:]
    ecrire_etat(etat)
    if not nouvelles:
        log("rien de neuf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
