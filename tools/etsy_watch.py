# -*- coding: utf-8 -*-
"""
Surveillance du blocage Etsy (DataDome) + relance AUTONOME de la connexion.

Deux rôles (toutes les 30 min, tâche planifiée) :
  1. Sonder Etsy avec un Chrome jetable (profil temp, aucun pilotage persistant) pour
     détecter le lever du blocage réseau — sans taper sur le navigateur du coffre.
  2. Au premier signe de déblocage : purger le profil du coffre, échauffer, puis lancer la
     connexion Etsy VIA LE COFFRE (transport hsb-v1 → perform goto/login — le mot de passe
     reste dans le coffre, frappe humaine lettre par lettre), vérifier la session (page
     compte), et notifier chaque étape sur Telegram.

Garde-fous : une tentative max toutes les 3 h ; ré-armement 6 h après un échec (sauf
captcha — action humaine requise) ; coffre verrouillé → tentative en attente (part dès le
déverrouillage). Arrêt définitif après une connexion confirmée.

Usage : python etsy_watch.py            → cycle normal (sonde + tentative si armée)
        python etsy_watch.py --retry    → force une tentative de connexion maintenant

Secrets lus dans %LOCALAPPDATA%\\hermes\\.env : TELEGRAM_BOT_TOKEN, TELEGRAM_HOME_CHANNEL.
État : tools/.etsy_watch.json  |  Journal : tools/.etsy_watch.log
"""
import html, io, os, re, json, sys, shutil, subprocess, tempfile, time
import urllib.request, urllib.parse, urllib.error, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ETAT = os.path.join(ROOT, "tools", ".etsy_watch.json")
LOG = os.path.join(ROOT, "tools", ".etsy_watch.log")
PREFIX = "\U0001F381 L'UNIVERS DE LA MARI\u00c9E \u2014"
URL = "https://www.etsy.com/fr/"
SIGNIN = "https://www.etsy.com/fr/signin"
COMPTE = "https://www.etsy.com/your/account"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
MARQUEURS = ("Acc\u00e8s temporairement restreint", "temporarily restricted", "captcha-delivery")
REPO_HSB = r"C:\Users\orio\repos\hermes-secret-broker"
CRED_ETSY = "fac5b59845b84a7497c5644e0a089332"
PROFIL_COFFRE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "HermesSecretBroker", "naveur-profile-chrome")
DELAI_MIN_TENTATIVE = 3 * 3600      # pas deux tentatives automatiques à moins de 3 h
DELAI_REARMEMENT = 6 * 3600         # nouvel essai auto 6 h après un échec non-captcha


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
    data = urllib.parse.urlencode({"chat_id": chat, "text": texte, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=data)
    return json.load(urllib.request.urlopen(req, timeout=30))


def notifier(token, chat, texte):
    if token and chat:
        try:
            telegram(token, chat, texte)
            return True
        except Exception as ex:
            log("erreur telegram : %s" % type(ex).__name__)
    else:
        log("canal telegram absent")
    return False


def lire_etat():
    defauts = {"blocked": None, "notified_at": None, "checks": 0, "pending_attempt": False,
               "last_attempt": 0, "last_attempt_detail": "", "locked_notified": False, "done": False}
    if os.path.exists(ETAT):
        try:
            defauts.update(json.load(io.open(ETAT, encoding="utf-8")))
        except Exception:
            pass
    return defauts


def ecrire_etat(e):
    io.open(ETAT, "w", encoding="utf-8", newline="\n").write(json.dumps(e, ensure_ascii=False, indent=2))


def probe():
    """Retourne (bloque, detail). bloque=None si indéterminé (erreur technique)."""
    import websocket  # websocket-client
    prof = tempfile.mkdtemp(prefix="etsy-probe-")
    p = None
    try:
        p = subprocess.Popen([CHROME, "--remote-debugging-port=0", "--user-data-dir=" + prof,
                              "--no-first-run", "--no-default-browser-check", "--remote-allow-origins=*",
                              "--disable-blink-features=AutomationControlled",
                              "--window-position=-2400,-2400", "--window-size=900,700", "about:blank"])
        portf = os.path.join(prof, "DevToolsActivePort")
        port = None
        deadline = time.time() + 25
        while time.time() < deadline and not port:
            if os.path.exists(portf):
                try:
                    port = open(portf).read().strip().splitlines()[0]
                except Exception:
                    pass
            time.sleep(0.3)
        if not port:
            return None, "port DevTools introuvable"
        time.sleep(0.8)
        pages = [t for t in json.loads(urllib.request.urlopen("http://127.0.0.1:%s/json" % port).read())
                 if t.get("type") == "page"]
        ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"], max_size=8 * 1024 * 1024)
        mid = [0]

        def call(method, **params):
            mid[0] += 1
            ws.send(json.dumps({"id": mid[0], "method": method, "params": params}))
            while True:
                r = json.loads(ws.recv())
                if r.get("id") == mid[0]:
                    return r.get("result", {})

        call("Page.navigate", url=URL)
        time.sleep(9)
        st = call("Runtime.evaluate", expression=(
            "(() => { const t=(document.body?document.body.innerText:'').slice(0,600);"
            " const cap=!!document.querySelector('iframe[src*=captcha]');"
            " return { url: location.href, title: document.title, ready: document.readyState, cap, txt: t };"
            " })()"), returnByValue=True)
        v = st.get("result", {}).get("value") or {}
        ws.close()
        url, title, txt, cap = v.get("url", ""), (v.get("title") or ""), (v.get("txt") or ""), bool(v.get("cap"))
        bloque = ("dd_referrer" in url) or cap or title.strip() == "etsy.com" or len(txt) < 40 \
            or any(m in txt for m in MARQUEURS)
        detail = "url=%s | titre=%s | texte=%d car | captcha=%s" % (url[:80], title[:60], len(txt), cap)
        return bloque, detail
    except Exception as ex:
        return None, "erreur probe %s %s" % (type(ex).__name__, str(ex)[:120])
    finally:
        if p is not None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        time.sleep(0.5)
        shutil.rmtree(prof, ignore_errors=True)


# ---------------------------------------------------------------- transport coffre

def _transport():
    if REPO_HSB not in sys.path:
        sys.path.insert(0, REPO_HSB)
    from hsb.client import transport
    return transport


def coffre_verrouille():
    try:
        r = _transport().call("hsb-admin-v1", "admin.status")
        res = r.get("result") or {}
        return not (r.get("ok") and not res.get("locked"))
    except Exception as ex:
        log("coffre : statut illisible (%s)" % type(ex).__name__)
        return True


def perform(params):
    return _transport().call("hsb-v1", "perform", params)


def tuer_chrome_profil():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                    "Where-Object { $_.CommandLine -like '*naveur-profile-chrome*' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                   capture_output=True, timeout=60)


def tenter_connexion():
    """Purge du profil + échauffement + connexion + vérification. -> (ok, detail)."""
    try:
        perform({"action": "naveur_stop"})
    except Exception:
        pass
    time.sleep(1)
    try:
        tuer_chrome_profil()
    except Exception:
        pass
    time.sleep(1)
    shutil.rmtree(PROFIL_COFFRE, ignore_errors=True)
    r = perform({"credential_id": CRED_ETSY, "action": "goto", "url": URL})
    if not r.get("ok"):
        return False, "goto refus\u00e9 : %s" % json.dumps(r.get("error"), ensure_ascii=False)[:160]
    time.sleep(8)
    r = perform({"credential_id": CRED_ETSY, "action": "login", "url": SIGNIN})
    if not r.get("ok"):
        return False, "login refus\u00e9 : %s" % json.dumps(r.get("error"), ensure_ascii=False)[:160]
    out = ((r.get("result") or {}).get("naveur")) or {}
    if out.get("captcha"):
        return False, "captcha \u00e0 valider \u00e0 la main dans la fen\u00eatre du coffre"
    if not out.get("logged_in"):
        return False, "connexion non aboutie (url=%s)" % str(out.get("url"))[:90]
    time.sleep(2)
    r = perform({"credential_id": CRED_ETSY, "action": "goto", "url": COMPTE})
    url_fin = ""
    if r.get("ok"):
        url_fin = str(((r.get("result") or {}).get("result") or {}).get("url") or "")
    if ("signin" in url_fin.lower()) or ("connexion" in url_fin.lower()):
        return False, "session non confirm\u00e9e (redirection %s)" % url_fin[:90]
    return True, "session confirm\u00e9e (%s)" % url_fin[:90]


def main():
    force = "--retry" in sys.argv
    e = env()
    token, chat = e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_HOME_CHANNEL")
    etat = lire_etat()
    if etat.get("done") and not force:
        return 0
    if not force:
        etat["checks"] = etat.get("checks", 0) + 1
        bloque, detail = probe()
        etat["last_detail"] = detail
        etat["last_check"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if bloque is None:
            log("probe indetermine : %s" % detail)
        elif bloque:
            etat["blocked"] = True
            log("encore bloque : %s" % detail)
        else:
            if etat.get("blocked") is not False:
                etat["pending_attempt"] = True
                etat["locked_notified"] = False
                log("debloque -> tentative armee : %s" % detail)
            else:
                log("debloque (deja vu) : %s" % detail)
            etat["blocked"] = False
        # ré-armement après échec (hors captcha)
        if (not etat.get("pending_attempt") and not etat.get("done")
                and etat.get("blocked") is False and etat.get("last_attempt")):
            det = str(etat.get("last_attempt_detail") or "")
            if "captcha" not in det and (time.time() - float(etat["last_attempt"])) > DELAI_REARMEMENT:
                etat["pending_attempt"] = True
                log("re-armement apres echec (%s)" % det[:80])
    if force:
        etat["pending_attempt"] = True
    if etat.get("pending_attempt") and etat.get("attempts_paused") and not force:
        log("tentative en pause (mot de passe a verifier dans le coffre)")
    if etat.get("pending_attempt") and (force or not etat.get("attempts_paused")):
        if coffre_verrouille():
            if not etat.get("locked_notified"):
                etat["locked_notified"] = True
                notifier(token, chat, "%s \U0001F513 <b>Etsy : le blocage est lev\u00e9, mais le coffre est verrouill\u00e9.</b>\n"
                                      "D\u00e9verrouille-le : la connexion partira automatiquement au prochain passage (30 min max)." % PREFIX)
            log("tentative en attente : coffre verrouille")
        elif (not force) and etat.get("last_attempt") and \
                (time.time() - float(etat["last_attempt"]) < DELAI_MIN_TENTATIVE):
            log("tentative en attente : moins de 3 h depuis la derniere")
        else:
            notifier(token, chat, "%s \U0001F680 <b>Etsy : je lance la connexion maintenant</b> (navigateur du coffre, frappe humaine)." % PREFIX)
            ok, det = tenter_connexion()
            etat["pending_attempt"] = False
            etat["last_attempt"] = time.time()
            etat["last_attempt_detail"] = det
            etat["locked_notified"] = False
            log("tentative : ok=%s | %s" % (ok, det))
            if ok:
                etat["done"] = True
                notifier(token, chat, "%s \u2705 <b>Etsy : connexion r\u00e9ussie — session confirm\u00e9e.</b>\n"
                                      "Le navigateur du coffre est connect\u00e9 \u00e0 ton compte. Prochaine \u00e9tape : pr\u00e9parer la boutique Etsy." % PREFIX)
            else:
                notifier(token, chat, "%s \u26A0\uFE0F <b>Etsy : la connexion n'a pas abouti.</b>\n"
                                      "Raison : %s\nLa surveillance continue." % (PREFIX, html.escape(det)))
    ecrire_etat(etat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
