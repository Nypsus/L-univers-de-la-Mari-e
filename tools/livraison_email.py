# -*- coding: utf-8 -*-
"""Livraison par e-mail des produits digitaux — L'Univers de la Mariée.

Envoie à l'acheteuse le lien de téléchargement de son produit après paiement.
Expéditeur : la boîte nypsus.business@gmail.com. Le mot de passe d'application
vient du COFFRE (HSB) et n'est jamais écrit dans ce dépôt public ni journalisé ;
un cache LOCAL hors dépôt (%LOCALAPPDATA%/hermes/lum_mail_secret.json) évite de
relire le coffre à chaque envoi (supprimer ce fichier si le mot de passe change).

Test direct :
    python tools/livraison_email.py --test adresse@exemple.fr
"""
import ast
import io
import json
import os
import smtplib
import subprocess
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVRAISON_PATH = os.path.join(ROOT, "tools", "livraison.json")
CACHE_PW = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                        "hermes", "lum_mail_secret.json")

HSB_VENV_PY = "C:/Users/orio/repos/hermes-secret-broker/.venv/Scripts/python.exe"
HSB_CRED_IMAP = "7122c0b3a80841a595a2e3206368875e"  # « Nypsus.business — IMAP (avis) » (niveau 2)
HSB_PURPOSE = "Livraison e-mail du guide (commande boutique LUM)"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
EXPEDITEUR_ADDR = "nypsus.business@gmail.com"
EXPEDITEUR_NOM = "L'Univers de la Mariée"


def _run_hsb(args):
    """Appelle le client HSB (canal Hermes). Aucune valeur secrète n'est imprimée ici."""
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000  # pas de fenêtre
    proc = subprocess.run(
        [HSB_VENV_PY, "-m", "hsb.client", "--compact"] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=90, **kw,
    )
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("ATTENTION"):
            continue
        try:
            return json.loads(line)
        except Exception:
            try:
                return ast.literal_eval(line)
            except Exception:
                continue
    raise RuntimeError("HSB injoignable (rc=%s)" % proc.returncode)


def _mail_password():
    """Mot de passe d'application Gmail : cache local hors dépôt, sinon coffre HSB."""
    try:
        cache = json.load(io.open(CACHE_PW, encoding="utf-8"))
    except Exception:
        cache = {}
    if cache.get("password"):
        return str(cache["password"])
    env = _run_hsb(["request", "--credential", HSB_CRED_IMAP, "--field", "password",
                    "--purpose", HSB_PURPOSE])
    if not env.get("ok"):
        raise RuntimeError("HSB_" + str((env.get("error") or {}).get("code")))
    res = env.get("result") or {}
    pwd = None
    if res.get("status") == "released" and res.get("value"):
        pwd = str(res["value"])
    elif res.get("confirmation_id"):  # niveau 3 : attente de validation humaine
        conf_id = res["confirmation_id"]
        for _ in range(100):
            c = _run_hsb(["confirmation", "--id", conf_id])
            cc = (c.get("result") or {}) if c.get("ok") else {}
            if cc.get("status") == "granted" and cc.get("value"):
                pwd = str(cc["value"])
                break
            if cc.get("status") in ("denied", "expired"):
                raise RuntimeError("HSB_CONFIRM_" + str(cc.get("status")))
            time.sleep(3)
    if not pwd:
        raise RuntimeError("HSB_PASSWORD_INDISPONIBLE")
    os.makedirs(os.path.dirname(CACHE_PW), exist_ok=True)
    io.open(CACHE_PW, "w", encoding="utf-8").write(json.dumps({"password": pwd}))
    return pwd


def produits():
    return json.load(io.open(LIVRAISON_PATH, encoding="utf-8"))


def _salut(nom_client):
    return ("Bonjour %s," % nom_client) if nom_client and nom_client != "?" else "Bonjour,"


def _corps_texte(nom_client, p):
    return (_salut(nom_client) +
            "\n\nMerci pour votre commande.\n\nVotre exemplaire : " + p["nom"] +
            "\nLien de téléchargement : " + p["url"] +
            "\n\nÀ conserver : si vous perdez cet e-mail, répondez simplement à ce message — "
            "nous vous renverrons votre guide." +
            "\n\nBelle préparation,\nMaryse — L'Univers de la Mariée")


def _corps_html(nom_client, p):
    url = p["url"]
    return """<div style="font-family:Georgia,'Times New Roman',serif;max-width:560px;margin:0 auto;color:#4a4a4a;line-height:1.6;">
  <p style="font-size:26px;color:#b8860b;margin:0 0 18px;">L'Univers de la Mari&eacute;e</p>
  <p>%s</p>
  <p>Merci pour votre commande. Voici votre exemplaire de <b>%s</b> :</p>
  <p style="text-align:center;margin:30px 0;">
    <a href="%s" style="background:#d4af37;color:#141210;padding:14px 30px;text-decoration:none;font-weight:bold;font-family:Georgia,serif;">Recevoir le guide</a>
  </p>
  <p style="font-size:13px;">Ou copiez ce lien : <a href="%s">%s</a></p>
  <p style="font-size:13px;background:#faf7ef;border:1px solid #eadfc2;padding:12px 14px;"><b>&Agrave; conserver :</b> ce lien est le v&ocirc;tre. Si vous perdez cet e-mail, r&eacute;pondez simplement &agrave; ce message &mdash; nous vous renverrons votre guide.</p>
  <p>Belle pr&eacute;paration,<br>Maryse &mdash; L'Univers de la Mari&eacute;e</p>
  <p style="font-size:11px;color:#999;border-top:1px solid #eee;padding-top:10px;">L'Univers de la Mari&eacute;e &middot; atelier de couture &middot; Moulle (62)<br>WhatsApp : +33 6 13 34 29 00 &middot; luniversdelamariee.com</p>
</div>""" % (_salut(nom_client), p["nom"], url, url, url)


def envoyer_livraison(to_email, nom_client, ref):
    """Envoie l'e-mail de livraison du produit `ref`. Retourne (ok: bool, detail: str)."""
    p = produits().get(ref)
    if not p:
        return False, "REF_INCONNUE (%s)" % ref
    if not to_email or "@" not in str(to_email):
        return False, "DESTINATAIRE_INVALIDE"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Votre commande : " + p["nom"]
    msg["From"] = formataddr((EXPEDITEUR_NOM, EXPEDITEUR_ADDR))
    msg["To"] = to_email
    msg["Reply-To"] = formataddr((EXPEDITEUR_NOM, EXPEDITEUR_ADDR))
    msg.attach(MIMEText(_corps_texte(nom_client, p), "plain", "utf-8"))
    msg.attach(MIMEText(_corps_html(nom_client, p), "html", "utf-8"))
    try:
        pwd = _mail_password()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=60) as S:
            S.login(EXPEDITEUR_ADDR, pwd)
            S.send_message(msg)
    except Exception as e:  # noqa: BLE001
        return False, "SMTP:" + type(e).__name__ + ":" + str(e)[:120]
    return True, "ENVOYE"


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Livraison e-mail — L'Univers de la Mariée")
    ap.add_argument("--test", metavar="ADRESSE", help="envoie l'e-mail de livraison à cette adresse")
    ap.add_argument("--ref", default="guide-robe-de-mariee")
    a = ap.parse_args()
    if a.test:
        ok, det = envoyer_livraison(a.test, "Test", a.ref)
        print(("OK " if ok else "ECHEC ") + det + " -> " + a.test)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
