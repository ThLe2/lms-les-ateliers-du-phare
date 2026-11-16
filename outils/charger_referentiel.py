#!/usr/bin/env python3
"""Charge les référentiels RNCP et RS de France compétences dans la base d'un centre.

Source : export quotidien publié par France compétences sur data.gouv.fr
(jeu « Répertoire national des certifications professionnelles et répertoire spécifique »,
fichiers XML v4.1). Licence Ouverte / Etalab 2.0.

Le script :
  1. lit la liste des fichiers du jeu de données et prend les derniers exports RNCP et RS v4.1 ;
  2. les télécharge et lit chaque fiche (lecture en flux : le fichier RNCP fait près de 500 Mo) ;
  3. écrit dans la base, par lots, les tables referentiel_fiches et referentiel_blocs
     (fiches actives complètes ; fiches inactives réduites à leur identité et à leurs remplaçantes) ;
  4. inscrit le chargement dans referentiel_chargements.

Il n'écrit que dans ces trois tables. Il a besoin de la clé de service du centre, qu'il lit dans la
variable d'environnement SUPABASE_SERVICE_ROLE_KEY (jamais en argument, jamais affichée).

Utilisation :
  python3 charger_referentiel.py --url https://xxxx.supabase.co            (chargement réel)
  python3 charger_referentiel.py --essai --dossier /tmp/rncp                (lecture seule : compte et contrôle)
"""
import argparse, io, json, os, re, sys, tempfile, time, urllib.request, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

JEU = "https://www.data.gouv.fr/api/1/datasets/5eebbc067a14b6fecc9c9976/"
LOT = 200
VOIES = (("SI_JURY_FI", "formation initiale"), ("SI_JURY_CA", "apprentissage"), ("SI_JURY_FC", "formation continue"),
         ("SI_JURY_CQ", "contrat de professionnalisation"), ("SI_JURY_CL", "candidature individuelle"), ("SI_JURY_VAE", "VAE"))


def telecharger(url, dest):
    for essai in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "accompagna-referentiel/1.0"}), timeout=600) as r, open(dest, "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        return dest
                    f.write(b)
        except Exception as e:  # coupure réseau : on réessaie
            if essai == 2:
                raise
            print(f"  nouvelle tentative ({e})", file=sys.stderr)
            time.sleep(10)


def derniers_exports():
    with urllib.request.urlopen(JEU, timeout=60) as r:
        jeu = json.load(r)
    res = {}
    for x in sorted(jeu["resources"], key=lambda x: x.get("last_modified") or "", reverse=True):
        t = x.get("title") or ""
        for rep in ("rncp", "rs"):
            if rep not in res and re.match(rf"export-fiches-{rep}-v4-1-\d{{4}}-\d{{2}}-\d{{2}}\.zip$", t):
                res[rep] = (t, x["url"], t[-14:-4])
    if set(res) != {"rncp", "rs"}:
        raise SystemExit(f"Exports v4.1 introuvables dans le jeu data.gouv.fr : {sorted(res)}")
    return res


def texte(el, tag):
    v = el.findtext(tag)
    if v is None:
        return None
    v = re.sub(r"[ \t ]{3,}", "\n", v.replace("\r", "")).strip()   # les retours à la ligne de l'export sont devenus des suites d'espaces
    return v or None


def date(el, tag):
    v = el.findtext(tag)
    try:
        return datetime.strptime(v.strip(), "%d/%m/%Y").date().isoformat() if v else None
    except ValueError:
        return None


def paires(el, conteneur, item):
    c = el.find(conteneur)
    return [] if c is None else [{"code": (i.findtext("CODE") or "").strip(), "libelle": (i.findtext("LIBELLE") or "").strip()} for i in c.findall(item)]


def lire(chemin_xml, repertoire, export_du):
    for _, el in ET.iterparse(chemin_xml, events=("end",)):
        if el.tag != "FICHE":
            continue
        numero = (el.findtext("NUMERO_FICHE") or "").strip()
        actif = (el.findtext("ACTIF") or "").strip() == "Oui"
        f = {
            "numero": numero, "repertoire": repertoire, "intitule": (el.findtext("INTITULE") or "").strip() or numero,
            "abrege_code": (el.findtext("ABREGE/CODE") or "").strip() or None,
            "abrege_libelle": (el.findtext("ABREGE/LIBELLE") or "").strip() or None,
            "niveau": (el.findtext("NOMENCLATURE_EUROPE/NIVEAU") or "").strip() or None,
            "actif": actif, "etat_fiche": texte(el, "ETAT_FICHE"), "type_enregistrement": texte(el, "TYPE_ENREGISTREMENT"),
            "date_effet": date(el, "DATE_EFFET"), "date_fin_enregistrement": date(el, "DATE_FIN_ENREGISTREMENT"),
            "date_limite_delivrance": date(el, "DATE_LIMITE_DELIVRANCE"), "date_publication": date(el, "DATE_DE_PUBLICATION"),
            "certificateurs": [{"nom": (c.findtext("NOM_CERTIFICATEUR") or "").strip(), "siret": (c.findtext("SIRET_CERTIFICATEUR") or "").strip() or None}
                               for c in el.findall("CERTIFICATEURS/CERTIFICATEUR")],
            "anciennes": [x.text.strip() for x in el.findall("ANCIENNES_CERTIFICATIONS/ANCIENNE_CERTIFICATION/ID_FICHE_ANCIENNE_CERTIFICATION") if x.text],
            "nouvelles": [x.text.strip() for x in el.findall("NOUVELLES_CERTIFICATIONS/NOUVELLE_CERTIFICATION/ID_FICHE_NOUVELLE_CERTIFICATION") if x.text],
            "export_du": export_du,
        }
        blocs = []
        # PostgREST exige les mêmes clés pour toutes les lignes d'un lot : valeurs vides par défaut.
        f.update({"nsf": [], "rome": [], "formacodes": [], "voies_acces": [], "activites_visees": None, "capacites_attestees": None,
                  "objectifs_contexte": None, "secteurs_activite": None, "types_emploi": None, "reglementations": None,
                  "prerequis_entree": None, "prerequis_validation": None})
        if actif:
            f.update({
                "nsf": paires(el, "CODES_NSF", "NSF"), "rome": paires(el, "CODES_ROME", "ROME"), "formacodes": paires(el, "FORMACODES", "FORMACODE"),
                "voies_acces": [lib for t, lib in VOIES if (el.findtext(f"{t}/ACTIF") or "").strip() == "Oui"],
                "activites_visees": texte(el, "ACTIVITES_VISEES"), "capacites_attestees": texte(el, "CAPACITES_ATTESTEES"),
                "objectifs_contexte": texte(el, "OBJECTIFS_CONTEXTE"), "secteurs_activite": texte(el, "SECTEURS_ACTIVITE"),
                "types_emploi": texte(el, "TYPE_EMPLOI_ACCESSIBLES"), "reglementations": texte(el, "REGLEMENTATIONS_ACTIVITES"),
                "prerequis_entree": texte(el, "PREREQUIS_ENTREE_FORMATION"), "prerequis_validation": texte(el, "PREREQUIS_VALIDATION_CERTIFICATION"),
            })
            for i, b in enumerate(el.findall("BLOCS_COMPETENCES/BLOC_COMPETENCES")):
                code = (b.findtext("CODE") or "").strip()
                if code:
                    blocs.append({"code": code, "numero": numero, "ordre": i + 1, "libelle": (b.findtext("LIBELLE") or "").strip() or code,
                                  "liste_competences": texte(b, "LISTE_COMPETENCES"), "modalites_evaluation": texte(b, "MODALITES_EVALUATION")})
        el.clear()
        if numero:
            yield f, blocs


class Base:
    def __init__(self, url, cle):
        self.url, self.cle = url.rstrip("/"), cle

    def appel(self, methode, chemin, corps=None, prefer=None):
        h = {"apikey": self.cle, "Authorization": f"Bearer {self.cle}", "Content-Type": "application/json"}
        if prefer:
            h["Prefer"] = prefer
        data = None if corps is None else json.dumps(corps, ensure_ascii=False).encode()
        for essai in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(f"{self.url}/rest/v1/{chemin}", data=data, headers=h, method=methode), timeout=300) as r:
                    t = r.read().decode()
                    return json.loads(t) if t else None
            except urllib.error.HTTPError as e:
                msg = e.read().decode()[:500]
                if e.code < 500 or essai == 2:
                    raise SystemExit(f"Base : {methode} {chemin.split('?')[0]} → HTTP {e.code} {msg}")
            except Exception:
                if essai == 2:
                    raise
            time.sleep(5)


def principal():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--url", help="URL Supabase du centre (https://xxxx.supabase.co)")
    p.add_argument("--essai", action="store_true", help="lecture seule : télécharge, lit et compte, sans rien écrire")
    p.add_argument("--dossier", help="dossier de travail (sinon dossier temporaire)")
    a = p.parse_args()
    base = None
    if not a.essai:
        cle = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not a.url or not cle:
            raise SystemExit("Chargement réel : --url et la variable SUPABASE_SERVICE_ROLE_KEY sont obligatoires (ou --essai).")
        base = Base(a.url, cle)

    dossier = a.dossier or tempfile.mkdtemp(prefix="referentiel-")
    os.makedirs(dossier, exist_ok=True)
    exports = derniers_exports()
    export_du = max(v[2] for v in exports.values())
    print(f"Exports retenus : {', '.join(v[0] for v in exports.values())}")
    chargement = None
    if base:
        chargement = base.appel("POST", "referentiel_chargements", {"fichiers": [v[0] for v in exports.values()], "export_du": export_du}, "return=representation")[0]["id"]

    totaux = {"fiches": 0, "actives": 0, "blocs": 0}
    try:
        for rep in ("rncp", "rs"):
            titre, url, jour = exports[rep]
            z = os.path.join(dossier, titre)
            if not os.path.exists(z):
                print(f"Téléchargement {titre}…")
                telecharger(url, z)
            with zipfile.ZipFile(z) as zz:
                nom = [n for n in zz.namelist() if n.lower().endswith(".xml")][0]
                xml = os.path.join(dossier, nom)
                if not os.path.exists(xml):
                    zz.extract(nom, dossier)
            lot_f, lot_b = [], []

            def vider():
                if base and lot_f:
                    base.appel("POST", "referentiel_fiches?on_conflict=numero", lot_f, "resolution=merge-duplicates,return=minimal")
                    # les blocs des fiches du lot sont remplacés en entier (une fiche devenue inactive n'en garde aucun)
                    base.appel("DELETE", "referentiel_blocs?numero=in.(" + ",".join(f["numero"] for f in lot_f) + ")")
                    if lot_b:
                        base.appel("POST", "referentiel_blocs?on_conflict=code", lot_b, "resolution=merge-duplicates,return=minimal")
                lot_f.clear(); lot_b.clear()

            for f, blocs in lire(xml, rep.upper(), jour):
                lot_f.append(f); lot_b.extend(blocs)
                totaux["fiches"] += 1; totaux["actives"] += f["actif"]; totaux["blocs"] += len(blocs)
                if len(lot_f) >= LOT:
                    vider()
            vider()
            print(f"{rep.upper()} : lu jusqu'à {totaux}")
            if not a.dossier:
                os.remove(xml)
        if base:
            base.appel("PATCH", f"referentiel_chargements?id=eq.{chargement}",
                       {"fin": datetime.now(timezone.utc).isoformat(), "statut": "terminé", "nb_fiches": totaux["fiches"], "nb_actives": totaux["actives"], "nb_blocs": totaux["blocs"]})
    except BaseException as e:
        if base and chargement:
            base.appel("PATCH", f"referentiel_chargements?id=eq.{chargement}",
                       {"fin": datetime.now(timezone.utc).isoformat(), "statut": "erreur", "message": str(e)[:1000]})
        raise
    print(f"Terminé : {totaux['fiches']} fiches dont {totaux['actives']} actives, {totaux['blocs']} blocs de compétences (export du {export_du}).")


if __name__ == "__main__":
    principal()
