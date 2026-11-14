# Collecteur des clôtures (gratuit, tourne sur GitHub, PC éteint)

**Novig** et **SX Bet** (bourse : NBA, NFL, foot dont sélections nationales, esport) effacent leurs matchs réglés de
leur API publique. Ce collecteur tourne toutes les 15 min sur GitHub Actions (gratuit), relève la clôture de chaque
match juste après le coup d'envoi et l'écrit dans `novig_closes.json` et `sx_closes.json`. `hl_verif.py` lit ces
fichiers : un lancement par semaine suffit. Les fichiers ne contiennent que des prix publics (aucune donnée de compte).

## Installation (une fois, ~5 min)

1. Créer un compte sur https://github.com puis un **nouveau dépôt public** (ex. `clotures`), en cochant
   « Add a README file ».
2. Dans le dépôt : **Add file → Upload files**, glisser `novig_collect.py`, `sx_collect.py`, `novig_closes.json`,
   `sx_closes.json`, `sx_state.json`, puis **Commit changes**.
3. **Add file → Create new file**, nom : `.github/workflows/clotures.yml`, coller le contenu du fichier
   `.github/workflows/novig.yml` de ce dossier, puis **Commit** (le dossier `.github` est masqué sous Windows).
4. Onglet **Actions** : activer les workflows si GitHub le demande, ouvrir « clotures » → **Run workflow** pour un
   premier essai (coche verte = OK, ~2 min).
5. Dans `hl_verif.py`, renseigner l'adresse « raw » du dépôt :
   `COLLECTEUR_URL = "https://raw.githubusercontent.com/<compte>/<dépôt>/main/"`.

GitHub met en pause les tâches planifiées d'un dépôt public sans activité pendant 60 jours ; les commits du
collecteur comptent comme activité. Si l'onglet Actions affiche « disabled », cliquer « Enable workflow ».
