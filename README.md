# Radar — Narratifs & Tendances Crypto (100% automatisé)

Tableau de bord statique qui suit :
- la capitalisation de marché par **narratif crypto** (Bitcoin, Ethereum, DeFi, IA, Meme, RWA, GameFi, DePIN, Layer 2, Altcoins — configurable) via l'API **CoinGecko**
- l'intérêt de recherche **Google Trends** pour vos mots-clés (crypto, cryptomonnaie, bitcoin, btc, alt, altcoin, ethereum, eth — configurable)

Une **GitHub Action** tourne chaque jour toute seule, récupère les données, et les commit dans le dépôt. Le site (`index.html`, hébergé via GitHub Pages) les affiche automatiquement. **Aucune intervention manuelle nécessaire une fois configuré.**

## Pourquoi ça ne pouvait pas tourner dans le chat Claude

Un artifact Claude.ai s'exécute dans un navigateur sandboxé qui bloque tout appel réseau vers des API externes (CoinGecko, Google...). C'est pour ça que la version "artifact" plantait avec `Failed to fetch`. Ici, `index.html` est un vrai site web hébergé normalement, sans cette restriction — le fetch vers CoinGecko fonctionne nativement. Pour Google Trends, qui n'a pas d'API officielle, la collecte se fait côté serveur (GitHub Actions) via la librairie `pytrends`.

## Mise en place (10 minutes, une seule fois)

1. **Créer un dépôt GitHub** (public ou privé) et y pousser tous ces fichiers.
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<votre-user>/<votre-repo>.git
   git push -u origin main
   ```

2. **Activer GitHub Pages** : Settings → Pages → Source = `Deploy from a branch` → Branch = `main` / `root`. Votre dashboard sera disponible à `https://<votre-user>.github.io/<votre-repo>/`.

3. **Activer les Actions** : Settings → Actions → General → autoriser l'exécution des workflows. Le workflow `.github/workflows/daily-update.yml` est déjà configuré pour tourner tous les jours à 06:00 UTC.

4. **Autoriser le workflow à pousser des commits** : Settings → Actions → General → Workflow permissions → cocher `Read and write permissions`.

5. (Optionnel) Lancer une première exécution manuelle : onglet **Actions** → `Mise à jour quotidienne des données` → `Run workflow`, pour avoir un premier point de données tout de suite sans attendre le lendemain.

C'est tout. Chaque jour, le workflow met à jour `data/narratives_history.json` et `data/trends_history.json`, et le site les affiche automatiquement au prochain chargement.

## Personnaliser

Éditez `config.json` :
- `narratives` : liste des narratifs suivis, chacun avec des mots-clés utilisés pour matcher les catégories CoinGecko par nom.
- `trends_terms` : liste des mots-clés Google Trends suivis.
- `trends_geo` : code pays pour Google Trends (`"FR"`, `""` pour mondial, etc.)

Poussez le changement (`git push`) — il sera pris en compte à la prochaine exécution planifiée, ou immédiatement via `Run workflow`.

Vous pouvez aussi ajouter une **ligne manuelle** ponctuelle directement depuis l'interface (bouton « + Ligne manuelle ») — elle est stockée dans le navigateur (localStorage) et se superpose aux données automatiques, sans passer par GitHub.

## Limites connues

- **CoinGecko** : API publique gratuite, limite de requêtes raisonnable pour un usage quotidien — pas de souci ici (1 appel/jour).
- **Google Trends / pytrends** : librairie non-officielle, peut casser si Google modifie son site. Le workflow est configuré pour ne pas bloquer la mise à jour des narratifs si Google Trends échoue (`continue-on-error: true`). L'agrégation de plus de 5 termes utilise un rééchelonnage approximatif via un terme pivot commun — les valeurs restent indicatives, pas exactes à la décimale.
- Pas de backfill historique : l'historique démarre au jour de la première exécution du workflow.
