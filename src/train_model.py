import json
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_dir, 'data', 'cantine.csv')
    out_dir = os.path.join(base_dir, 'artifacts')
    os.makedirs(out_dir, exist_ok=True)
    cache_dir = os.path.join(out_dir, 'sk_cache')
    os.makedirs(cache_dir, exist_ok=True)

    df = pd.read_csv(data_path)

    # Expected columns
    expected = [
        'age', 'classe', 'type_repas', 'calories', 'cout_repas',
        'freq_consommation', 'satisfaction', 'recommande'
    ]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans le CSV: {missing}")

    # Features/target
    target = 'recommande'
    X = df.drop(columns=[target])
    y = df[target].astype(int)

    # Train/test split (70/30)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    # Justification de l'étape (écrite dans README mais loggée ici aussi)
    print("Séparation train/test: essentielle pour estimer la performance généralisable et éviter le surapprentissage.")

    # Identify numeric and categorical features
    numeric_features = ['age', 'calories', 'cout_repas', 'freq_consommation', 'satisfaction']
    categorical_features = ['classe', 'type_repas']

    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features),
            ('num', 'passthrough', numeric_features),
        ]
    )

    clf = RandomForestClassifier(
        n_estimators=300,
        random_state=42,
        class_weight='balanced',
        min_samples_leaf=1,
        max_features='sqrt',
    )

    pipe = Pipeline(
        steps=[('preprocess', preprocessor), ('model', clf)],
        memory=joblib.Memory(cache_dir, verbose=0),
    )
    pipe.fit(X_train, y_train)

    # Evaluation
    y_pred = pipe.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    print("\nMétriques sur le test:")
    print(f"Accuracy: {acc:.3f}")
    print(f"Recall:   {rec:.3f}")
    print(f"F1-score: {f1:.3f}")
    print("\nRapport de classification:\n")
    print(classification_report(y_test, y_pred, digits=3))

    # Feature importances: on récupère les noms des features encodées
    ohe: OneHotEncoder = pipe.named_steps['preprocess'].named_transformers_['cat']
    ohe_features = ohe.get_feature_names_out(categorical_features)
    feature_names = list(ohe_features) + numeric_features

    importances = pipe.named_steps['model'].feature_importances_
    # Top 2 features
    top2_idx = np.argsort(importances)[-2:][::-1]
    top2 = [(feature_names[i], float(importances[i])) for i in top2_idx]

    print("\nTop 2 variables les plus importantes:")
    for name, imp in top2:
        print(f"- {name}: importance={imp:.4f}")

    # Save artifacts
    joblib.dump(pipe, os.path.join(out_dir, 'model.joblib'))
    with open(os.path.join(out_dir, 'metrics.json'), 'w', encoding='utf-8') as f:
        json.dump({'accuracy': acc, 'recall': rec, 'f1': f1}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, 'feature_importances_top2.json'), 'w', encoding='utf-8') as f:
        json.dump({'top2': top2}, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
