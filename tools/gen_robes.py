# -*- coding: utf-8 -*-
"""
Génère une page SEO par robe (robes/<slug>.html) depuis l'objet `products` de vitrine.html,
patche vitrine.html (lien « fiche complète » dans la popup + petit lien sur les cartes),
et met à jour sitemap.xml.

Usage : python tools/gen_robes.py   (depuis la racine du repo)
"""
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
BASE = "https://luniversdelamariee.com"

def slugify(t):
    s = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "robe"

def lire(p):
    with open(p, encoding="utf-8") as f:
        return f.read()

def ecrire(p, s):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)

vitrine = lire("vitrine.html")

# --- 1. Extraire le bloc products et le parser ---
# (retrait des commentaires pleine ligne d'abord, puis scanner d'accolades qui respecte les chaînes)
sans_com = "\n".join(l for l in vitrine.split("\n") if not l.strip().startswith("//"))
i = sans_com.find("const products = {")
assert i > 0, "bloc products introuvable"
start = sans_com.find("{", i)
depth, instr, esc, end = 0, None, False, None
for pos in range(start, len(sans_com)):
    c = sans_com[pos]
    if instr:
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == instr:
            instr = None
    else:
        if c in "\"'":
            instr = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = pos + 1
                break
assert end, "fin du bloc products introuvable"
js = sans_com[start:end]
js = re.sub(r",(\s*[}\]])", r"\1", js)                       # virgules finales
js = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', js)  # clés entre guillemets
js = re.sub(r"'([A-Za-z0-9_]+)'(\s*:)", r'"\1"\2', js)                       # clés 'item1' -> "item1"
produits = json.loads(js)
# on ne garde que les fiches complètes (2 entrées bouchon sans description dans la vitrine : item3, n3)
produits = {k: p for k, p in produits.items() if p.get("title") and p.get("desc") and p.get("imgs")}
print("produits parsés :", len(produits))

# --- 2. Extraire style + footer réutilisables ---
sty = vitrine[vitrine.find("<style>"): vitrine.find("</style>") + len("</style>")]
foot = vitrine[vitrine.find("<footer"): vitrine.find("</footer>") + len("</footer>")]

# --- 3. Slugs uniques ---
slugs = {}
vus = set()
for k, p in produits.items():
    s = slugify(p["title"])
    n = 2
    while s in vus:
        s = slugify(p["title"]) + "-" + str(n)
        n += 1
    vus.add(s)
    slugs[k] = s
    p["_slug"] = s

# --- 4. Catégories depuis les cartes ---
cats = {}
for m in re.finditer(r'data-category="([^"]*)"\s+onclick="openModal\(\'([^\']+)\'\)"', vitrine):
    cats[m.group(2)] = m.group(1)
print("cartes trouvées :", len(cats))

# --- 5. Générer les pages ---
os.makedirs("robes", exist_ok=True)
prix_re = re.compile(r"([\d][\d\s\u202f]*)\s*€")

for k, p in produits.items():
    s = p["_slug"]
    titre = p["title"]
    sous = p.get("subtitle", "")
    desc = p.get("desc", "").strip()
    imgs = p.get("imgs", [])
    statut = p.get("status", "")
    dispo = "InStock" if statut.lower().startswith("dispo") else "SoldOut"
    marque = sous.split("•")[0].strip() if "•" in sous else ""
    m = prix_re.search(p.get("price", ""))
    prix = m.group(1).replace(" ", "").replace("\u202f", "") if m else ""
    prix_html = re.sub(r"\(Neuf\s*:", "<span class=\"text-gray-400 text-sm\">(Neuf :", p.get("price", "")) + ("</span>" if "(Neuf" in p.get("price", "") else "")
    img_abs = [BASE + "/" + im for im in imgs]
    desc_meta = re.sub(r"\s+", " ", desc)[:155].rsplit(" ", 1)[0] + "…"
    og_img = img_abs[0] if img_abs else BASE + "/assets/og/og-lunivers-de-la-mariee.jpg"

    offre = {
        "@type": "Offer",
        "url": "%s/robes/%s.html" % (BASE, s),
        "priceCurrency": "EUR",
        "availability": "https://schema.org/" + dispo,
        "itemCondition": "https://schema.org/UsedCondition",
        "seller": {
            "@type": "BridalShop",
            "name": "L'Univers de la Mariée",
            "address": {"@type": "PostalAddress", "streetAddress": "1 rue du Questage",
                        "addressLocality": "Moulle", "postalCode": "62910", "addressCountry": "FR"},
        },
    }
    if prix:
        offre["price"] = prix + ".00"
    prod_ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": titre,
        "image": img_abs,
        "description": re.sub(r"\s+", " ", desc),
        "sku": k,
        "category": "Robe de mariée",
        "material": p.get("fabric", ""),
        "offers": offre,
    }
    if marque:
        prod_ld["brand"] = {"@type": "Brand", "name": marque}

    wa_txt = ("Bonjour Maryse, je suis int\u00e9ress\u00e9e par la robe \u00ab %s \u00bb vue sur votre site." % titre)
    import urllib.parse
    wa = "https://wa.me/33613342900?text=" + urllib.parse.quote(wa_txt)

    imgs_html = "\n".join(
        '<div class="bg-white p-3 shadow-lg"><img src="../%s" class="w-full h-auto" alt="%s \u2014 robe de mari\u00e9e, %s" loading="lazy"></div>'
        % (im, titre.replace('"', ""), p.get("fabric", "")) for im in imgs
    )
    badge = ('<span class="badge-gold-prestige px-8 py-2.5 text-[12px] uppercase tracking-[0.3em] font-bold rounded-full shadow-lg">%s</span>' % (statut or "Pièce d'atelier"))

    page = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{titre} \u2014 robe de mari\u00e9e{sous_t} | L'Univers de la Mari\u00e9e, atelier (62)</title>
    <meta name="description" content="{desc_meta}">
    <link rel="canonical" href="{base}/robes/{slug}.html">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <meta name="theme-color" content="#141210">
    <meta property="og:type" content="product">
    <meta property="og:locale" content="fr_FR">
    <meta property="og:site_name" content="L'Univers de la Mari\u00e9e">
    <meta property="og:title" content="{titre} \u2014 {sous}">
    <meta property="og:description" content="{desc_meta}">
    <meta property="og:url" content="{base}/robes/{slug}.html">
    <meta property="og:image" content="{og_img}">
    <meta property="og:image:alt" content="{titre} \u2014 robe de mari\u00e9e">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{titre} \u2014 L'Univers de la Mari\u00e9e">
    <meta name="twitter:description" content="{desc_meta}">
    <meta name="twitter:image" content="{og_img}">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/feather-icons/dist/feather.min.js"></script>
    {sty}
    <script type="application/ld+json">
{ld}
    </script>
</head>
<body>

    <a href="../vitrine.html" class="nav-back-home">
        <i data-feather="arrow-left" style="width:16px;"></i> Galerie
    </a>

    <header class="pt-32 pb-10 text-center px-6">
        <p class="font-luxe text-gray-500 uppercase tracking-widest text-xs mb-4">{sous}</p>
        <h1 class="font-amour text-5xl md:text-7xl gold-static mb-6">{titre}</h1>
        {badge}
    </header>

    <main class="max-w-6xl mx-auto px-6 mb-24">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-10 items-start">
            <div class="space-y-6">
{imgs_html}
            </div>
            <div class="bg-[#faf9f6] md:sticky md:top-24">
                <p class="text-gray-600 leading-loose mb-10 font-light text-justify">{desc}</p>
                <div class="grid grid-cols-2 gap-6 mb-10">
                    <div><span class="block text-xs uppercase text-[#d4af37] font-bold tracking-widest mb-1">Mati\u00e8re</span><span class="font-luxe text-lg">{fabric}</span></div>
                    <div><span class="block text-xs uppercase text-[#d4af37] font-bold tracking-widest mb-1">Taille</span><span class="font-luxe text-lg">{taille}</span></div>
                    <div><span class="block text-xs uppercase text-[#d4af37] font-bold tracking-widest mb-1">\u00c9tat</span><span class="font-luxe text-lg">{etat}</span></div>
                    <div><span class="block text-xs uppercase text-[#d4af37] font-bold tracking-widest mb-1">Prix vitrine</span><span class="font-luxe text-lg">{prix}</span></div>
                </div>
                <a href="{wa}" target="_blank" rel="noopener"
                   class="block w-full text-center py-4 bg-[#1a1a1a] text-[#f6e27a] uppercase tracking-widest font-bold text-sm transition-all duration-300 hover:bg-[#d4af37] hover:text-[#1a1a1a]">
                    R\u00e9server un essayage
                </a>
                <p class="text-center text-[10px] text-gray-400 uppercase tracking-widest mt-3">Essayage priv\u00e9 sur rendez-vous uniquement \u00b7 Showroom \u00e0 Moulle (62910)</p>
                <a href="../vitrine.html" class="block w-full text-center py-3 mt-4 border border-[#d4af37] text-[#d4af37] uppercase tracking-widest font-bold text-xs hover:bg-[#d4af37] hover:text-[#1a1a1a] transition-colors">
                    \u2190 Retour \u00e0 la galerie
                </a>
            </div>
        </div>
    </main>

{foot}

    <script>feather.replace();</script>
</body>
</html>
""".format(
        titre=titre, sous=sous, sous_t=(" \u2014 " + marque if marque else ""), desc=desc, desc_meta=desc_meta,
        base=BASE, slug=s, og_img=og_img, sty=sty, ld=json.dumps(prod_ld, ensure_ascii=False, indent=2),
        badge=badge, imgs_html=imgs_html, fabric=p.get("fabric", ""), taille=p.get("size", ""),
        etat=p.get("condition", ""), prix=prix_html, wa=wa, foot=foot,
    )
    ecrire(os.path.join("robes", s + ".html"), page)

print("pages générées :", len(produits))

# --- 6. Patcher vitrine.html ---
v = vitrine

# 6a. CSS du lien « fiche complète »
if ".fiche-link" not in v:
    css = """
        .fiche-link { display:inline-block; margin-top:10px; font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#f6e27a; border-bottom:1px solid rgba(246,226,122,.55); padding-bottom:2px; }
        .fiche-link:hover { color:#fff; border-color:#fff; }
"""
    v = v.replace("</style>", css + "    </style>", 1)

# 6b. lien dans la modale + patch openModal
if "modal-full-link" not in v:
    v = v.replace(
        '                    <p class="text-center text-[10px] text-gray-400 uppercase tracking-widest">Essayage priv\u00e9 sur rendez-vous uniquement</p>',
        '                    <a id="modal-full-link" href="#" class="block w-full text-center py-3 mt-3 border border-[#d4af37] text-[#d4af37] uppercase tracking-widest font-bold text-xs hover:bg-[#d4af37] hover:text-[#1a1a1a] transition-colors">Voir la fiche compl\u00e8te</a>\n'
        '                    <p class="text-center text-[10px] text-gray-400 uppercase tracking-widest mt-3">Essayage priv\u00e9 sur rendez-vous uniquement</p>',
        1)

# table des slugs (robuste : ne dépend pas du format des entrées products)
table = "const ROBE_SLUGS = %s;\n" % json.dumps(slugs, ensure_ascii=False)
if "const ROBE_SLUGS = " in v:
    v = re.sub(r"const ROBE_SLUGS = \{[^\n]*\};\n", table, v, count=1)
else:
    v = v.replace("function openModal(id) {", table + "\nfunction openModal(id) {", 1)

# logique du lien : version data.slug (1re exécution) ou ROBE_SLUGS (reprises)
vieux = ("    const _fl = document.getElementById('modal-full-link');\n"
         "    if (_fl) { if (data.slug) { _fl.href = 'robes/' + data.slug + '.html'; _fl.style.display = ''; } else { _fl.style.display = 'none'; } }")
nouveau = ("    const _fl = document.getElementById('modal-full-link');\n"
           "    if (_fl) { const _s = ROBE_SLUGS[currentProductId]; if (_s) { _fl.href = 'robes/' + _s + '.html'; _fl.style.display = ''; } else { _fl.style.display = 'none'; } }")
if vieux in v:
    v = v.replace(vieux, nouveau, 1)
elif "modal-full-link" in v and "ROBE_SLUGS[currentProductId]" not in v:
    v = v.replace(
        "document.getElementById('modal-badge').innerText = data.status;",
        "document.getElementById('modal-badge').innerText = data.status;\n" + nouveau, 1)

# 6c. lien discret sur chaque carte (à la fin du contenu d'overlay-info)
def ajoute_lien_carte(m):
    key = m.group(1)
    if key not in slugs:
        return m.group(0)
    bloc_carte = m.group(0)
    if "fiche-link" in bloc_carte:
        return bloc_carte
    lien = '<a href="robes/%s.html" class="fiche-link" onclick="event.stopPropagation()">Fiche compl\u00e8te \u2192</a>' % slugs[key]
    return re.sub(r'(<div class="overlay-info">.*?)(</div>)',
                  lambda mm: mm.group(1) + lien + mm.group(2),
                  bloc_carte, count=1, flags=re.S)

v = re.sub(r'onclick="openModal\(\'([^\']+)\'\)"(.*?)<div class="overlay-info">(.*?)</div>', ajoute_lien_carte, v, flags=re.S)

# 6d. vérifier que la table des slugs est bien là (plus de patch par entrée : formats trop variés)
manquants = [k for k in slugs if ('"%s"' % slugs[k]) not in v]
if "ROBE_SLUGS" not in v:
    print("ATTENTION table ROBE_SLUGS absente")
elif manquants:
    print("ATTENTION slugs absents de la table :", manquants)
else:
    print("table ROBE_SLUGS : ok (%d robes)" % len(slugs))

ecrire("vitrine.html", v)

# --- 7. sitemap.xml ---
sm = lire("sitemap.xml")
nouvelles = ""
for k, p in produits.items():
    url = "%s/robes/%s.html" % (BASE, p["_slug"])
    if url not in sm:
        nouvelles += "  <url>\n    <loc>%s</loc>\n    <priority>0.8</priority>\n  </url>\n" % url
if nouvelles:
    sm = sm.replace("</urlset>", nouvelles + "</urlset>")
    ecrire("sitemap.xml", sm)
    print("sitemap : +%d robes" % len(produits))
else:
    print("sitemap : déjà à jour")

print("OK")
