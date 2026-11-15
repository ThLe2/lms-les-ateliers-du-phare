#!/usr/bin/env python3
"""Recoupe les valeurs datées de la base avec OpenFisca France (lecture seule).

- Lit les tables de valeurs datées et les historiques (PASS, SMIC) par l'API
  publique du centre.
- Télécharge les paramètres OpenFisca (dépôt GitHub openfisca/openfisca-france).
- Compare selon correspondances_openfisca.json et écrit un rapport :
  concordant, ÉCART, manquant en base, absent d'OpenFisca, OpenFisca périmé.
- N'écrit jamais en base.

Usage : python3 verifier_sources.py --url https://xxx.supabase.co --cle <clé anon>
        [--correspondances correspondances_openfisca.json] [--depuis 2015]
        [--json rapport.json] [--texte rapport.txt]
"""
import argparse, datetime as dt, json, os, sys, urllib.request
try:
    import yaml
except ImportError:
    sys.exit("Module manquant : pip install pyyaml")

OF = "https://raw.githubusercontent.com/openfisca/openfisca-france/master/openfisca_france/parameters/"
TABLES = ["parametres_sante", "parametres_prevoyance", "parametres_epargne", "parametres_tns", "parametres_parcours"]
_cache = {}

def lire_json(url, cle):
    req = urllib.request.Request(url, headers={"apikey": cle, "Authorization": "Bearer " + cle})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def openfisca(chemin):
    """{date: {valeur, texte, lien, jo}}, date de dernière vérification OpenFisca."""
    if chemin in _cache: return _cache[chemin]
    with urllib.request.urlopen(OF + chemin, timeout=30) as r:
        d = yaml.safe_load(r.read())
    md = d.get("metadata") or {}
    refs, jo = md.get("reference") or {}, md.get("official_journal_date") or {}
    def cle_date(k): return k if isinstance(k, dt.date) else dt.date.fromisoformat(str(k))
    refs = {cle_date(k): v for k, v in refs.items()}; jo = {cle_date(k): v for k, v in jo.items()}
    vals = {}
    for k, v in (d.get("values") or {}).items():
        k = cle_date(k); x = v.get("value") if isinstance(v, dict) else v
        r = refs.get(k) or {}
        if isinstance(r, list): r = r[0] if r else {}
        vals[k] = {"valeur": None if x is None else float(x), "texte": r.get("title"), "lien": r.get("href"),
                   "jo": str(jo[k]) if k in jo else None}
    res = (vals, str(md.get("last_value_still_valid_on")) if md.get("last_value_still_valid_on") else None)
    _cache[chemin] = res
    return res

def en_vigueur(vals, jour):
    ds = [d for d in vals if d <= jour]
    return (max(ds), vals[max(ds)]) if ds else (None, None)

def proche(a, b): return a is not None and b is not None and abs(a - b) < 1e-6 * max(1, abs(b)) + 0.005 * (abs(b) >= 1)

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--url", required=True); a.add_argument("--cle", required=True)
    a.add_argument("--correspondances", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "correspondances_openfisca.json"))
    a.add_argument("--depuis", type=int, default=2015); a.add_argument("--json"); a.add_argument("--texte")
    p = a.parse_args(); rest = p.url.rstrip("/") + "/rest/v1/"
    corr = json.load(open(p.correspondances, encoding="utf-8"))
    aujourd = dt.date.today()
    rapport = {"le": aujourd.isoformat(), "historiques": [], "valeurs": []}

    # 1. Historiques (une ligne par date)
    for h in corr["historiques"]:
        vals, der = openfisca(h["of"])
        if "colonne_annee" in h:
            base = {dt.date(int(r[h["colonne_annee"]]), 1, 1): float(r[h["colonne_valeur"]])
                    for r in lire_json(f'{rest}{h["table"]}?select={h["colonne_annee"]},{h["colonne_valeur"]}', p.cle)}
            vals = {d: v for d, v in vals.items() if d.month == 1 and d.day == 1}
        else:
            base = {dt.date.fromisoformat(r[h["colonne_date"]]): float(r[h["colonne_valeur"]])
                    for r in lire_json(f'{rest}{h["table"]}?select={h["colonne_date"]},{h["colonne_valeur"]}', p.cle)}
        lignes = []
        for d in sorted(set(base) | {k for k, v in vals.items() if v["valeur"] is not None}):
            if d.year < p.depuis: continue
            b, o = base.get(d), vals.get(d)
            ov = o and o["valeur"]
            if b is not None and ov is not None: etat = "concordant" if proche(b, ov) else "ÉCART"
            elif ov is not None: etat = "manquant en base"
            else: etat = "absent d'OpenFisca" + (f" (OpenFisca vérifié au {der})" if der and d.isoformat() > der else "")
            lignes.append({"date": d.isoformat(), "base": b, "openfisca": ov, "etat": etat,
                           "texte": o and o["texte"], "lien": o and o["lien"], "jo": o and o["jo"]})
        rapport["historiques"].append({"libelle": h["libelle"], "openfisca_verifie_au": der, "lignes": lignes})

    # 2. Valeurs datées (valeur en vigueur aujourd'hui)
    base = {}
    for t in TABLES:
        for r in lire_json(f"{rest}{t}?select=cle,valeur,unite,libelle", p.cle):
            base.setdefault(r["cle"], dict(r, table=t))
    for c in corr["valeurs"]:
        vals, der = openfisca(c["of"])
        jour = dt.date(aujourd.year, 1, 1) if c.get("date") == "janvier" else aujourd
        d, o = en_vigueur(vals, jour)
        b = base.get(c["cle"])
        ov = None if not o or o["valeur"] is None else o["valeur"] * c.get("facteur", 1)
        bv = None if not b or b["valeur"] is None else float(b["valeur"])
        if b is None: etat = "clé absente de la base"
        elif ov is None: etat = "absent d'OpenFisca"
        else: etat = "concordant" if proche(bv, ov) else "ÉCART"
        rapport["valeurs"].append({"cle": c["cle"], "libelle": b and b["libelle"], "base": bv, "openfisca": ov,
            "en_vigueur_depuis": d and d.isoformat(), "openfisca_verifie_au": der, "etat": etat,
            "texte": o and o["texte"], "lien": o and o["lien"], "jo": o and o["jo"], "parametre_openfisca": c["of"]})

    # 3. Rapport texte
    out = [f"Recoupement OpenFisca — {aujourd.strftime('%d/%m/%Y')} — lecture seule, rien n'est écrit en base"]
    for h in rapport["historiques"]:
        n = {}
        for l in h["lignes"]: n[l["etat"]] = n.get(l["etat"], 0) + 1
        out.append(f"\n{h['libelle']} (OpenFisca vérifié au {h['openfisca_verifie_au'] or '?'}) : " + ", ".join(f"{v} {k}" for k, v in n.items()))
        for l in h["lignes"]:
            if l["etat"] != "concordant":
                out.append(f"  - {l['date']} : base {l['base']} / OpenFisca {l['openfisca']} → {l['etat']}" + (f" — {l['texte']}" if l["texte"] else ""))
    n = {}
    for v in rapport["valeurs"]: n[v["etat"]] = n.get(v["etat"], 0) + 1
    out.append("\nValeurs datées en vigueur : " + ", ".join(f"{v} {k}" for k, v in n.items()))
    for v in rapport["valeurs"]:
        if v["etat"] != "concordant":
            out.append(f"  - {v['cle']} : base {v['base']} / OpenFisca {v['openfisca']} (en vigueur depuis {v['en_vigueur_depuis']}, "
                       f"OpenFisca vérifié au {v['openfisca_verifie_au']}) → {v['etat']}" + (f" — {v['texte']}" if v["texte"] else ""))
    out.append("\nRappel : OpenFisca est un projet public collaboratif, pas une publication officielle. Un écart se tranche sur le texte officiel (Légifrance), jamais sur OpenFisca seul.")
    texte = "\n".join(out); print(texte)
    if p.json: json.dump(rapport, open(p.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if p.texte: open(p.texte, "w", encoding="utf-8").write(texte)

if __name__ == "__main__":
    main()
