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
