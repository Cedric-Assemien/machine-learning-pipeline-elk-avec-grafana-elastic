# Optimisation de la Cantine Scolaire (ML + ELK + Grafana)

Ce projet combine un pipeline de Machine Learning (scikit-learn) et une stack ELK (Elasticsearch, Logstash, Kibana) + Grafana orchestrés via Docker Compose pour analyser le dataset `data/cantine.csv`.

## Structure

- `data/cantine.csv` — dataset fourni
- `src/train_model.py` — script ML: split, pipeline, entraînement, métriques, importances
- `requirements.txt` — dépendances Python
- `docker-compose.yml` — ELK + Grafana
- `docker/logstash/pipeline/cantine.conf` — pipeline Logstash d’ingestion CSV
- `docker/logstash/config/logstash.yml` — config de base Logstash
- `docker/elasticsearch/cantine_index_mapping.json` — mapping d’index Elasticsearch `cantine_data`
- `artifacts/` — artefacts générés (modèle, métriques)
- `kibana/export/cantine_data_view.ndjson` — Data View Kibana exportable
- `docker/grafana/provisioning/*` — provisioning automatique (datasource + dashboards)
- `docker/grafana/dashboards/cantine_dashboard.json` — dashboard d’exemple

## Démarrage rapide (Windows PowerShell)

1. Démarrer la stack ELK + Grafana

```powershell
docker compose up -d
```

2. Créer l’index et le mapping

```powershell
Invoke-WebRequest -Uri http://localhost:9200/cantine_data -Method Put -ContentType 'application/json' -InFile '.\docker\elasticsearch\cantine_index_mapping.json'
```

3. (Optionnel) Importer la Data View Kibana

- Kibana > Stack Management > Saved Objects > Import
- Fichier: `kibana/export/cantine_data_view.ndjson`

4. Vérifier l’ingestion

- Ouvrir Kibana > Dev Tools et exécuter:
  ```json
  GET cantine_data/_count
  ```
- Le `count` doit être > 0 après démarrage de Logstash.

5. Ouvrir les interfaces

- Elasticsearch: http://localhost:9200
- Kibana: http://localhost:5601
- Grafana: http://localhost:3000 (admin / admin par défaut)
- Dashboard Grafana direct: http://localhost:3000/d/cantine-main

## Partie A – Machine Learning (scikit-learn)

### Préparation (split 70/30)

- Fait dans `src/train_model.py` via `train_test_split(..., test_size=0.3, stratify=y, random_state=42)`.
- Pourquoi c’est important: séparer train/test permet d’estimer la performance généralisable du modèle et de limiter le sur-apprentissage. Sans set de test, on risque d’optimiser les hyperparamètres ou la structure pour s’adapter au bruit du jeu d’entraînement et d’avoir une performance trompeuse en production.

### Modélisation prédictive

- Pipeline:
  - Prétraitement: `ColumnTransformer` avec `OneHotEncoder(handle_unknown='ignore')` sur `classe`, `type_repas` et passage direct des variables numériques `age, calories, cout_repas, freq_consommation, satisfaction`.
  - Modèle: `RandomForestClassifier(n_estimators=300, class_weight='balanced', random_state=42)`.
- Évaluation: `accuracy`, `recall`, `f1-score` + `classification_report` sur le set de test.

Exécution locale (Windows PowerShell):

```powershell
# (Optionnel) créer un venv
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\src\train_model.py
```

Les artefacts sont sauvegardés dans `artifacts/`.

### Interprétation

- Les importances de caractéristiques du modèle (Random Forest) sont extraites et les deux plus fortes sont listées dans la console et écrites dans `artifacts/feature_importances_top2.json`.
- Utilisation possible par l’école:
  - Si `type_repas` et `satisfaction`/`calories` sont dominants, adapter l’offre (ex: augmenter la disponibilité des options les plus appréciées) et veiller à l’équilibre nutritionnel.
  - Si `cout_repas` est important, étudier une tarification sociale ou des remises ciblées.
  - Si `classe` (niveau) pèse, personnaliser les menus par niveau (primaire vs lycée) et la communication.

## Partie B – Analyse avec ELK

### 1) Lancer la stack

```powershell
# Démarrer Elasticsearch, Kibana, Logstash, Grafana
# (Docker Desktop doit être démarré)
docker compose up -d
```

- Elasticsearch: http://localhost:9200
- Kibana: http://localhost:5601
- Grafana: http://localhost:3000 (user: admin / pass: admin par défaut, à changer)

### 2) Créer l’index et le mapping

```powershell
# Créer l’index cantine_data avec mapping adapté
Invoke-WebRequest -Uri http://localhost:9200/cantine_data -Method Put -ContentType 'application/json' -InFile '.\docker\elasticsearch\cantine_index_mapping.json'
```

Champs clés du mapping:

- `age: integer`, `classe: keyword`, `type_repas: keyword`, `calories: float`, `cout_repas: float`, `freq_consommation: integer`, `satisfaction: integer`, `recommande: boolean`.

### 3) Ingestion CSV via Logstash

Le pipeline ( `docker/logstash/pipeline/cantine.conf` ) lit `data/cantine.csv`, parse les colonnes, cast les types, et indexe dans `cantine_data`.

Pour forcer la réingestion (si besoin):

- Arrêter logstash: `docker compose stop logstash`
- Supprimer l’index: `Invoke-WebRequest -Uri http://localhost:9200/cantine_data -Method Delete`
- Recréer l’index (voir étape 2)
- Supprimer le fichier sincedb dans le conteneur (optionnel):
  ```powershell
  docker compose run --rm logstash bash -lc "rm -f /usr/share/logstash/data/.sincedb_cantine"
  ```
- Redémarrer: `docker compose up -d logstash`

#### Relance guidée de Logstash après modification du pipeline

```powershell
docker compose stop logstash
# (re)créer l'index si besoin
Invoke-WebRequest -Uri http://localhost:9200/cantine_data -Method Delete -ErrorAction SilentlyContinue
Invoke-WebRequest -Uri http://localhost:9200/cantine_data -Method Put -ContentType 'application/json' -InFile '.\docker\elasticsearch\cantine_index_mapping.json'
# purger sincedb pour relire le CSV
docker compose run --rm logstash bash -lc "rm -f /usr/share/logstash/data/.sincedb_cantine"
docker compose up -d logstash
```

### 4) Agrégations DSL (exemples prêts à coller)

- Moyenne de satisfaction par `type_repas`:

```json
POST cantine_data/_search
{
  "size": 0,
  "aggs": {
    "satisfaction_par_type": {
      "terms": { "field": "type_repas" },
      "aggs": {
        "satisfaction_moy": { "avg": { "field": "satisfaction" } }
      }
    }
  }
}
```

- Distribution des coûts moyens par `classe`:

```json
POST cantine_data/_search
{
  "size": 0,
  "aggs": {
    "cout_par_classe": {
      "terms": { "field": "classe" },
      "aggs": {
        "cout_moy": { "avg": { "field": "cout_repas" } }
      }
    }
  }
}
```

Interprétation rapide:

- Si `végétarien` > `standard` en satisfaction moyenne, renforcer l’offre végétarienne.
- Si certaines classes ont un coût moyen plus élevé, ajuster le budget/menus pour l’équité.

### 5) Visualisations Kibana

- Pie chart: Index `cantine_data`, champ `recommande` (booléen) en aggregation « Terms » pour la proportion Oui/Non.
- Scatter plot: `X = calories`, `Y = satisfaction`. Optionnel: color par `type_repas`.

### Import Data View Kibana (facultatif)

Vous pouvez importer la Data View prête à l’emploi:

1. Kibana > Stack Management > Saved Objects > Import
2. Sélectionner `kibana/export/cantine_data_view.ndjson`
3. La Data View `cantine_data` sera disponible (time field `@timestamp`). Si vous n’avez pas (encore) de `@timestamp`, vous pouvez choisir « No time field » lors de la création manuelle d’une Data View.

### Importer un bundle de visualisations Kibana (facultatif)

Un export NDJSON prêt à l’emploi est disponible avec:

- un pie « recommande »
- un scatter « calories vs satisfaction » (Vega)
- une barre « satisfaction moyenne par type_repas »

Procédure:

1. Kibana > Stack Management > Saved Objects > Import
2. Fichier: `kibana/export/cantine_bundle.ndjson`
3. Ouvrez le dashboard « Cantine - Starter »

## Grafana (optionnel)

- Provisioning automatique: au démarrage de Grafana, une datasource `Elasticsearch-Cantine` (uid: `es-cantine`) et un dashboard `Cantine - Vue d'ensemble` sont créés. Accédez à http://localhost:3000.
- Lien direct du dashboard: http://localhost:3000/d/cantine-main
- Si le dashboard ne s’affiche pas, vérifiez dans Configuration > Data sources que `Elasticsearch-Cantine` pointe bien vers `http://elasticsearch:9200` et l’index `cantine_data`.

Note: Le datasource/dashboards s’appuient sur un champ `@timestamp`. Vous pouvez l’ajouter dans Logstash, par exemple:

```conf
filter {
  # ... votre filtre csv/mutate existant ...
  if !["@timestamp"] {
    mutate { add_field => { "@timestamp" => "%{+YYYY-MM-dd'T'HH:mm:ss.SSSX}" } }
  }
}
```

ou utiliser le `date` filter si vous avez une colonne de date.

## Partie C – Discussion critique

- Complémentarité:
  - scikit-learn offre la prédiction (ex: qui est susceptible de recommander la cantine), et l’explicabilité via importances.
  - ELK offre l’exploration interactive, les agrégations rapides et des visualisations ad-hoc pour les décideurs.
  - Ensemble: on identifie les leviers (ELK) et on cible les actions (ML) en priorisant selon l’impact prédictif.
- Extension de dataset:
  - Ajouter « allergies », « préférences détaillées », « indicateurs nutritionnels (protéines, lipides, fibres) », « heure/ligne de service », « files d’attente », « origine des ingrédients ».
  - Impact: meilleure personnalisation des menus, détection de segments spécifiques (allergiques/gluten), corrélations fines entre nutrition et satisfaction, et optimisation opérationnelle des pics d’affluence.

## Dépannage

- Assurez-vous que Docker Desktop est démarré et que `9200`, `5601`, `3000` sont libres.
- Si l’ingestion ne commence pas: vérifier le chemin du CSV monté, recréer l’index, supprimer `sincedb` comme montré.
- Version ELK: 7.17.x cohérente entre services.
