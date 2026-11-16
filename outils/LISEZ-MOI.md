# Recoupement des valeurs datées avec OpenFisca

`verifier_sources.py` compare, en lecture seule, les valeurs datées de la base
(PASS, SMIC, prélèvements sociaux, fiscalité de l'assurance vie, taux des livrets…)
avec les paramètres publics d'OpenFisca France. Il n'écrit jamais en base.

    pip install pyyaml
    python3 outils/verifier_sources.py --url <URL Supabase> --cle <clé publique anon> --texte rapport.txt

La liste des valeurs contrôlées est dans `correspondances_openfisca.json` :
ajouter une ligne suffit à étendre le contrôle.

OpenFisca est un projet public collaboratif, pas une publication officielle :
un écart se tranche toujours sur le texte officiel (Légifrance).

# Liens valeurs datées ↔ articles de loi

`verifier_articles.py` relit, en lecture seule, chaque lien de la table
`valeurs_articles` : il interroge l'article en vigueur par la fonction
`veille-legifrance` (API Légifrance) et signale :

- **ARTICLE MODIFIÉ** : une nouvelle version de l'article est en vigueur depuis la vérification ;
- **ÉCRITURE ABSENTE** : la valeur attendue (« 152 500 », « 7,5 % »…) ne figure plus dans le texte.

    python3 outils/verifier_articles.py --url <URL Supabase> --cle <clé publique anon>

# Référentiels RNCP et RS (France compétences)

`charger_referentiel.py` charge dans la base du centre les fiches des répertoires RNCP et RS
publiées chaque nuit par France compétences sur data.gouv.fr (fichiers XML v4.1, Licence Ouverte) :
intitulé, niveau, certificateur, dates, activités visées, capacités attestées, prérequis, voies d'accès,
codes ROME, NSF et Formacode, et pour le RNCP les blocs de compétences (liste des compétences,
modalités d'évaluation). Les fiches inactives ne gardent que leur identité et la ou les fiches qui les remplacent.

Il n'écrit que dans `referentiel_fiches`, `referentiel_blocs` et `referentiel_chargements`.
La lecture se fait par `lms.referentiel_chercher`, `lms.referentiel_fiche` et `lms.referentiel_etat`
(équipe pédagogique uniquement).

Le chargement tourne chaque lundi à 5 h 17 (UTC) par l'action GitHub `.github/workflows/referentiel.yml`,
et peut être lancé à la main (onglet Actions > « Référentiels RNCP et RS » > Run workflow).
Il a besoin du secret GitHub `SUPABASE_SERVICE_ROLE_KEY`, créé par le responsable du centre.

    python3 outils/charger_referentiel.py --essai                 # lecture seule : télécharge et compte
    SUPABASE_SERVICE_ROLE_KEY=… python3 outils/charger_referentiel.py --url <URL Supabase>
