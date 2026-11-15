#!/usr/bin/env python3
"""Contrôle des liens « valeur datée ↔ article de loi » (lecture seule).

Pour chaque ligne de public.valeurs_articles :
- lit l'article en vigueur par la fonction veille-legifrance (API Légifrance) ;
- compare la version en vigueur à la version vérifiée (version_id) :
  si l'article a changé depuis la vérification, la valeur est « à revoir » ;
- vérifie que l'écriture attendue (« 152 500 », « 7,5 % »…) figure toujours dans le texte,
  y compris sous les écritures légales (« 35 p. 100 », « 35 pour cent »).
N'écrit jamais en base.

Usage : python3 verifier_articles.py --url https://xxx.supabase.co --cle <clé anon> [--texte rapport.txt]
"""
import argparse, datetime as dt, json, re, urllib.parse, urllib.request


def lire(url, cle):
    req = urllib.request.Request(url, headers={"apikey": cle, "Authorization": "Bearer " + cle})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def variantes(e):
    v = [e]
    m = re.match(r"^([\d,]+) ?%$", e)
    if m:
        v += [m.group(1) + " p. 100", m.group(1) + " pour cent", m.group(1) + "%", m.group(1) + " %"]
    return v


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--url", required=True); a.add_argument("--cle", required=True); a.add_argument("--texte")
    p = a.parse_args(); base = p.url.rstrip("/")
    liens = lire(f"{base}/rest/v1/valeurs_articles?select=*&order=code,article,cle", p.cle)
    articles, lignes = {}, []
    for l in liens:
        k = (l["code"], l["article"])
        if k not in articles:
            try:
                articles[k] = lire(f"{base}/functions/v1/veille-legifrance?code={l['code']}&article={urllib.parse.quote(l['article'])}", p.cle)
            except Exception as e:
                articles[k] = {"ok": False, "erreur": str(e)}
        d = articles[k]
        if not d.get("ok") or not d.get("trouve"):
            etat = "article introuvable ou API indisponible"
        else:
            texte = (d.get("texte") or "").replace(" ", " ").replace(" ", " ")
            modifie = l.get("version_id") and d.get("id") != l["version_id"]
            present = None if not l.get("ecriture") else any(v in texte for v in variantes(l["ecriture"]))
            if modifie:
                etat = f"ARTICLE MODIFIÉ : nouvelle version en vigueur depuis le {d.get('en_vigueur_du')} (vérifiée : version du {l.get('version_debut')})"
            elif present is False:
                etat = f"ÉCRITURE ABSENTE : « {l['ecriture']} » ne figure plus dans le texte"
            else:
                etat = "inchangé"
        lignes.append({**l, "etat": etat, "lien": d.get("lien"), "en_vigueur_du": d.get("en_vigueur_du")})

    jour = dt.date.today().strftime("%d/%m/%Y")
    alertes = [x for x in lignes if x["etat"] != "inchangé"]
    n = {s: sum(1 for x in lignes if x["statut"] == s) for s in ("valide", "a_valider", "a_revoir")}
    out = [f"Liens valeurs ↔ articles — {jour} — {len(lignes)} liens sur {len(articles)} articles "
           f"({n['valide']} validés, {n['a_valider']} à valider, {n['a_revoir']} à revoir) — {len(alertes)} alerte(s)"]
    for x in sorted(alertes, key=lambda x: (not x["etat"].startswith("ARTICLE"), x["cle"])):
        out.append(f"  - {x['cle']} — {x['code'].upper()} {x['article']} : {x['etat']}" + (f" — {x['lien']}" if x.get("lien") else ""))
    revoir = [x for x in lignes if x["statut"] == "a_revoir"]
    if revoir:
        out.append("  Liens à revoir par le service pédagogique :")
        out += [f"  - {x['cle']} — {x['code'].upper()} {x['article']} : {x.get('commentaire') or ''}" for x in revoir]
    out.append("Lecture seule : rien n'est écrit en base. Un lien ne devient « validé » qu'après relecture du service pédagogique.")
    texte = "\n".join(out); print(texte)
    if p.texte:
        open(p.texte, "w", encoding="utf-8").write(texte)


if __name__ == "__main__":
    main()
