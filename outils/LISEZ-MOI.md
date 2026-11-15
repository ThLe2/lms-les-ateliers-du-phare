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
