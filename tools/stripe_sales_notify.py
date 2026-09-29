# -*- coding: utf-8 -*-
"""
Notifications de vente L'Univers de la Mariée → Telegram.

Surveille les paiements Stripe (Payment Intents) et envoie un message Telegram
pour chaque nouvelle commande payée. Conçu pour tourner via le Planificateur de
tâches Windows (aucun agent, aucun coût) — état dans tools/.sales_state.json.

Secrets lus dans %LOCALAPPDATA%\\hermes\\.env :
  STRIPE_LUM_KEY      (clé restreinte — doit avoir « Payment Intents : Lecture »)
  TELEGRAM_BOT_TOKEN  (bot Hermes)
  TELEGRAM_HOME_CHANNEL (chat de l'utilisateur)
"""
import io, os, re, json, sys, urllib.request, urllib.parse, urllib.error, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        return json.load(io.open(ETAT, encoding="utf-8"))
    return {"vus": [], "depuis": None, "alerte_permission_envoyee": False}

def ecrire_etat(e):
    io.open(ETAT, "w", encoding="utf-8", newline="\n").write(json.dumps(e, ensure_ascii=False, indent=2))

def main():
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
            telegram(token, chat, "%s \u26a0\ufe0f Surveillance des ventes : la cl\u00e9 Stripe n'a pas encore la permission "
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
        texte = ("%s \U0001F4B0 <b>Nouvelle commande pay\u00e9e</b>\n"
                 "\u2022 Montant : <b>%.2f \u20ac</b>\n"
                 "\u2022 Pi\u00e8ce : %s\n"
                 "\u2022 Client : %s (%s)\n"
                 "\u2022 Paiement : https://dashboard.stripe.com/payments/%s\n"
                 "\u2022 Pense \u00e0 confirmer l'envoi \u00e0 la cliente.") % (PREFIX, montant, ref or "voir Stripe", nom, email, pi.get("id"))
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
