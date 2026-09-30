# -*- coding: utf-8 -*-
"""Pilote de l'onboarding Etsy via CDP réel sur le navigateur du coffre.

Les widgets React d'Etsy ignorent les clics JS (.click()) -> il faut des clics SOURIS
réels (Input.dispatchMouseEvent, isTrusted=true). Ce script fournit :
  python etsy_wizard.py etat            -> JSON de l'écran (boutons, champs, radios, erreurs)
  python etsy_wizard.py clic "<texte>"  -> clic souris réel sur le plus petit élément
                                           contenant ce texte (bouton, option, lien)
  python etsy_wizard.py goto <url>      -> navigue puis état

Aucun secret ici : la saisie des valeurs sensibles reste au coffre (naveur). Runtime.enable
n'est JAMAIS utilisé (vecteur de détection CDP — règle du projet).
"""
import json, os, sys, time, urllib.request

import websocket

PROF = os.path.join(os.environ["LOCALAPPDATA"], "HermesSecretBroker", "naveur-profile-chrome")


def cdp():
    port = open(os.path.join(PROF, "DevToolsActivePort")).read().strip().splitlines()[0]
    targets = json.loads(urllib.request.urlopen("http://127.0.0.1:%s/json/list" % port).read())
    pages = [x for x in targets if x.get("type") == "page"]
    page = None
    for pref in ("onboarding", "etsy.com/sell", "etsy.com/your", "etsy.com"):
        for x in pages:
            if pref in (x.get("url") or ""):
                page = x
                break
        if page:
            break
    if page is None and pages:
        page = pages[0]
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], max_size=8 * 1024 * 1024)
    mid = [0]

    def call(method, **params):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == mid[0]:
                return r.get("result", {})

    return ws, call


def evalv(call, expr):
    r = call("Runtime.evaluate", expression=expr, returnByValue=True)
    return r.get("result", {}).get("value")


def centre(call, texte):
    v = evalv(call, """
    (() => {
      const t = %s.toLowerCase();
      const all = [...document.querySelectorAll('*')];
      const hits = all.filter(e => (e.textContent || '').toLowerCase().includes(t) && (e.textContent || '').length < 300);
      hits.sort((a, b) => { const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
        return (ra.width * ra.height) - (rb.width * rb.height); });
      for (const h of hits) {
        const r = h.getBoundingClientRect();
        if (r.width > 30 && r.height > 8) return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2), tag: h.tagName, w: Math.round(r.width), h: Math.round(r.height)};
      }
      return null;
    })()
    """ % json.dumps(texte))
    return v


def clic_reel(call, x, y):
    # un onglet en arrière-plan (visibilityState=hidden) rejette les clics injectés :
    # bringToFront + émulation de focus AVANT chaque clic (leçon vécue).
    call("Page.bringToFront")
    call("Emulation.setFocusEmulationEnabled", enabled=True)
    call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", buttons=1, clickCount=1)
    call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", buttons=0, clickCount=1)


def etat(call):
    return evalv(call, """(() => {
      const vis = e => e.offsetParent !== null;
      const btns = [...document.querySelectorAll('button')].filter(vis);
      const suiv = btns.find(b => /suivant|continuer|enregistrer|suivante|valider|ouvrir|cr[eé]er|commencer|c'est parti/i.test(b.textContent || ''));
      const errs = [...document.querySelectorAll('*')].filter(e => e.children.length === 0 && vis(e) && /s[eé]lectionnez|obligatoire|requis|incorrect|erreur|introuvable/i.test(e.textContent || '')).map(e => e.textContent.trim().slice(0, 80)).slice(0, 4);
      const champs = [...document.querySelectorAll('input[type=text], input[type=email], input[type=search], input[type=tel], textarea')].filter(vis).map(i => ({name: i.name, id: i.id, ph: i.placeholder || '', val: (i.value || '').slice(0, 50)}));
      const radios = [...document.querySelectorAll('input[type=radio]')].map(i => i.checked);
      const checks = [...document.querySelectorAll('input[type=checkbox]')].map(i => ({id: i.id, name: i.name, checked: i.checked}));
      return {url: location.href, titre: document.title,
              boutons: btns.map(b => (b.textContent || '').trim().slice(0, 45)).filter(t => t).slice(0, 14),
              suivant: suiv ? {txt: (suiv.textContent || '').trim().slice(0, 35), disabled: suiv.disabled} : null,
              erreurs: errs, champs: champs, radios: radios, coches: checks,
              texte: (document.body ? document.body.innerText : '').slice(0, 1000)};
    })()""")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "etat"
    ws, call = cdp()
    try:
        if cmd == "etat":
            print(json.dumps(etat(call), ensure_ascii=False, indent=1)[:2600])
        elif cmd == "clic":
            c = centre(call, sys.argv[2])
            print("cible :", c)
            if c:
                clic_reel(call, c["x"], c["y"])
                time.sleep(float(sys.argv[3]) if len(sys.argv) > 3 else 1.8)
                print(json.dumps(etat(call), ensure_ascii=False)[:900])
        elif cmd == "goto":
            call("Page.navigate", url=sys.argv[2])
            time.sleep(5)
            print(json.dumps(etat(call), ensure_ascii=False)[:900])
        else:
            print("commande inconnue :", cmd)
    finally:
        ws.close()


if __name__ == "__main__":
    main()
