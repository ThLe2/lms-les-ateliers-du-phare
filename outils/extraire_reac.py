#!/usr/bin/env python3
"""Détail des compétences des titres professionnels (REAC) — pour les référentiels chargés dans la base du centre.

Pour chaque fiche RNCP d'un titre professionnel du ministère du Travail encore active, et pour chaque fiche
retenue dans une sélection, le script :
  1. lit sur le site de France compétences le lien du « Référentiel d'activité, de compétences et d'évaluation »
     joint à la fiche (pour un titre professionnel : le REAC suivi du référentiel de certification) ;
  2. si le document a changé depuis le dernier passage (ou n'a jamais été lu), le télécharge et en extrait le texte
     (pdftotext, paquet poppler-utils) ;
  3. découpe chaque « FICHE COMPÉTENCE PROFESSIONNELLE » : intitulé, description, contexte de mise en œuvre,
     critères de performance, savoir-faire et savoirs ; rattache chaque compétence à son bloc RNCP par l'intitulé ;
  4. écrit dans referentiel_documents et referentiel_competences (et rien d'autre).

Un document qui ne suit pas la trame du REAC est noté « format non reconnu » : son lien reste disponible,
le détail se lit dans le PDF.

La clé de service est lue dans la variable SUPABASE_SERVICE_ROLE_KEY (jamais en argument, jamais affichée).

    python3 extraire_reac.py --url https://xxxx.supabase.co                 (passage complet)
    python3 extraire_reac.py --essai --pdf REAC.pdf                          (lecture seule : découpe un PDF local)
"""
import argparse, json, os, re, subprocess, sys, tempfile, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 accompagna/1.0",
      "Accept-Language": "fr-FR,fr;q=0.9"}
FC = "https://www.francecompetences.fr"


def http(url, timeout=120):
    for essai in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception:
            if essai == 2:
                raise
            time.sleep(5 * (essai + 1))


def norm(t):
    t = unicodedata.normalize("NFD", (t or "").replace("’", "'")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def lien_document(numero):
    rep, n = re.match(r"(RNCP|RS)(\d+)", numero).groups()
    html = http(f"{FC}/recherche/{rep.lower()}/{n}/").decode("utf-8", "replace")
    m = re.search(r'<a[^>]+href="(/wp-json/api/v1/activity/export/\d+/\d+)"[^>]*>([\s\S]*?)</a>', html)
    if not m:
        return None, None
    titre = re.sub(r"<[^>]+>|\s+", " ", m.group(2)).replace("&rsquo;", "’").replace("&#8217;", "’").strip()
    return FC + m.group(1), titre or "Référentiel"


def texte_pdf(chemin):
    return subprocess.run(["pdftotext", "-enc", "UTF-8", chemin, "-"], capture_output=True, check=True).stdout.decode("utf-8", "replace")


def nettoyer(t):
    t = t.replace("\f", "\n").replace(" ", " ")
    # cartouche de bas de page des documents du ministère (une valeur par ligne, ou sur une seule ligne)
    t = re.sub(r"(?m)^SIGLE\n(?:.*\n){0,24}?Page\n\d+/\d+\n", "", t)
    t = re.sub(r"(?m)^\s*SIGLE\s+Type de document.*\n(?:\s*\S+\s+REAC\s+TP-\d+.*\n)?", "", t)
    return t


def items(lignes):
    """Regroupe les lignes en éléments : une ligne qui commence par une minuscule prolonge la précédente."""
    out = []
    for l in lignes:
        l = l.strip()
        if not l:
            continue
        if out and (l[0].islower() or l[0] in "(«,;:" or out[-1].endswith(("-", ",", " de", " du", " des", " la", " le", " les", " et", " ou", " à", " au", " aux", " en", " d’", " l’"))):
            out[-1] = out[-1] + " " + l
        else:
            out.append(l)
    return [re.sub(r"\s+", " ", x).strip() for x in out]


def paragraphe(lignes):
    return re.sub(r"\s+", " ", " ".join(l.strip() for l in lignes if l.strip())).strip() or None


def decouper(texte):
    t = nettoyer(texte)
    entete = {}
    m = re.search(r"Millésime\n(\d+)\n\s*\nDate de Validation\n(\d{2}/\d{2}/\d{4})", texte)
    if m:
        entete = {"millesime": m.group(1), "date_validation": m.group(2)}
    m0 = re.search(r"(?m)^FICHE COMP[ÉE]TENCE PROFESSIONNELLE N°", t)
    if not m0:
        return entete, []
    debut = m0.start()
    fin = re.search(r"(?m)^FICHE DES COMP[ÉE]TENCES TRANSVERSALES|^Glossaire du REAC|^Glossaire technique|^R[ÉE]F[ÉE]RENTIEL DE CERTIFICATION", t[debut:])
    zone = t[debut: debut + fin.start()] if fin else t[debut:]
    morceaux = re.split(r"(?m)^FICHE COMP[ÉE]TENCE PROFESSIONNELLE N°\s*(\d+)\s*$", zone)
    comps = []
    for i in range(1, len(morceaux), 2):
        ordre, corps = int(morceaux[i]), morceaux[i + 1]
        lignes = corps.split("\n")
        # intitulé : premières lignes non vides avant « Description de la compétence »
        j = 0
        while j < len(lignes) and not lignes[j].strip():
            j += 1
        titre = []
        while j < len(lignes) and not re.match(r"Description de la comp[ée]tence", lignes[j]):
            if lignes[j].strip():
                titre.append(lignes[j].strip())
            j += 1
        sections, cle = {"description": [], "contexte": [], "criteres": [], "savoirs": []}, None
        for l in lignes[j:]:
            s = l.strip()
            if re.match(r"Description de la comp[ée]tence", s):
                cle = "description"; continue
            if s.startswith("Contexte(s) professionnel(s)") or s.startswith("Contexte professionnel"):
                cle = "contexte"; continue
            if re.match(r"Crit[èe]res de performance", s):
                cle = "criteres"; continue
            if s.startswith("Savoir-faire techniques") or s.startswith("Savoirs, savoir-faire"):
                cle = "savoirs"; continue
            if cle:
                sections[cle].append(l)
        comps.append({"ordre": ordre, "intitule": paragraphe(titre) or f"Compétence {ordre}",
                      "description": paragraphe(sections["description"]), "contexte": paragraphe(sections["contexte"]),
                      "criteres": items(sections["criteres"]), "savoirs": items(sections["savoirs"])})
    return entete, comps


def rattacher(comps, blocs):
    """Rattache chaque compétence au bloc RNCP dont la liste contient son intitulé."""
    index = []
    for b in blocs:
        for l in (b.get("liste_competences") or "").split("\n"):
            l = re.sub(r"^\s*[-•*–]\s*", "", l).strip()
            if l:
                index.append((norm(l), b["code"]))
    for c in comps:
        n = norm(c["intitule"])
        c["bloc_code"] = next((code for l, code in index if l == n or (len(n) > 15 and (n in l or l in n))), None)
    return comps


class Base:
    def __init__(self, url, cle):
        self.url, self.cle = url.rstrip("/"), cle

    def appel(self, methode, chemin, corps=None, prefer=None):
        h = {"apikey": self.cle, "Content-Type": "application/json"}
        if not self.cle.startswith("sb_"):
            h["Authorization"] = f"Bearer {self.cle}"
        if prefer:
            h["Prefer"] = prefer
        data = None if corps is None else json.dumps(corps, ensure_ascii=False).encode()
        for essai in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(f"{self.url}/rest/v1/{chemin}", data=data, headers=h, method=methode), timeout=120) as r:
                    t = r.read().decode()
                    return json.loads(t) if t else None
            except urllib.error.HTTPError as e:
                msg = e.read().decode()[:400]
                if e.code < 500 or essai == 2:
                    raise SystemExit(f"Base : {methode} {chemin.split('?')[0]} → HTTP {e.code} {msg}")
            except Exception:
                if essai == 2:
                    raise
            time.sleep(5)


def principal():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--url")
    p.add_argument("--essai", action="store_true", help="lecture seule")
    p.add_argument("--pdf", help="avec --essai : découper ce PDF local et afficher le résultat")
    p.add_argument("--numero", action="append", help="limiter à cette fiche (répétable)")
    p.add_argument("--forcer", action="store_true", help="relire les documents même s'ils n'ont pas changé")
    a = p.parse_args()

    if a.essai and a.pdf:
        entete, comps = decouper(texte_pdf(a.pdf))
        print(json.dumps({"entete": entete, "nb": len(comps), "competences": comps}, ensure_ascii=False, indent=1))
        return

    cle = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not a.url or not cle:
        raise SystemExit("--url et la variable SUPABASE_SERVICE_ROLE_KEY sont obligatoires (ou --essai --pdf).")
    base = Base(a.url, cle)

    if a.numero:
        cibles = sorted(set(n.upper() for n in a.numero))
    else:
        tp = base.appel("GET", "referentiel_fiches?select=numero&actif=is.true&repertoire=eq.RNCP"
                               "&certificateurs=cs." + urllib.parse.quote('[{"nom":"MINISTERE DU TRAVAIL DU PLEIN EMPLOI ET DE L\' INSERTION"}]'))
        sel = base.appel("GET", "referentiel_selections?select=numero")
        cibles = sorted({x["numero"] for x in (tp or []) + (sel or [])})
    connus = {d["numero"]: d for d in (base.appel("GET", "referentiel_documents?select=numero,url,statut") or [])}
    print(f"{len(cibles)} fiche(s) à examiner")
    bilan = {"extrait": 0, "inchangé": 0, "format non reconnu": 0, "sans document": 0, "erreur": 0}
    dossier = tempfile.mkdtemp(prefix="reac-")
    for numero in cibles:
        maintenant = datetime.now(timezone.utc).isoformat()
        try:
            url, titre = lien_document(numero)
            time.sleep(0.5)
            if not url:
                base.appel("POST", "referentiel_documents?on_conflict=numero", {"numero": numero, "url": None, "titre": None, "statut": "sans document",
                           "nb_competences": 0, "message": None, "verifie_le": maintenant}, "resolution=merge-duplicates,return=minimal")
                bilan["sans document"] += 1
                continue
            ancien = connus.get(numero)
            if ancien and ancien["url"] == url and ancien["statut"] in ("extrait", "format non reconnu") and not a.forcer:
                base.appel("PATCH", f"referentiel_documents?numero=eq.{numero}", {"verifie_le": maintenant})
                bilan["inchangé"] += 1
                continue
            chemin = os.path.join(dossier, numero + ".pdf")
            open(chemin, "wb").write(http(url))
            entete, comps = decouper(texte_pdf(chemin))
            blocs = base.appel("GET", f"referentiel_blocs?select=code,liste_competences&numero=eq.{numero}") or []
            comps = rattacher(comps, blocs)
            base.appel("DELETE", f"referentiel_competences?numero=eq.{numero}")
            if comps:
                base.appel("POST", "referentiel_competences", [dict(c, numero=numero) for c in comps], "return=minimal")
            statut = "extrait" if comps else "format non reconnu"
            base.appel("POST", "referentiel_documents?on_conflict=numero", {
                "numero": numero, "url": url, "titre": titre, "statut": statut, "nb_competences": len(comps),
                "millesime": entete.get("millesime"), "date_validation": entete.get("date_validation"),
                "message": None, "verifie_le": maintenant, "extrait_le": maintenant}, "resolution=merge-duplicates,return=minimal")
            bilan[statut] += 1
            print(f"  {numero} : {statut} ({len(comps)} compétences)")
            os.remove(chemin)
        except SystemExit:
            raise
        except Exception as e:
            bilan["erreur"] += 1
            print(f"  {numero} : erreur {e}", file=sys.stderr)
            base.appel("POST", "referentiel_documents?on_conflict=numero", {"numero": numero, "statut": "erreur", "message": str(e)[:500],
                       "verifie_le": maintenant}, "resolution=merge-duplicates,return=minimal")
    print("Bilan :", json.dumps(bilan, ensure_ascii=False))


if __name__ == "__main__":
    principal()
