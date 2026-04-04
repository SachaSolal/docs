# config — Configuration & State Management

Fichiers de configuration, variables d'environnement et base SQLite
pour le suivi de l'état du pipeline.

## Fichiers

```
/config/
  .env.example      ← template des variables d'environnement
  pipeline.db       ← base SQLite (état du pipeline, ignorée par git)
  ma_voix.wav       ← sample vocal pour le clonage TTS (ignoré par git)
  hook_templates.json ← templates de hooks pré-écrits
```

## Base SQLite — Schéma

```sql
CREATE TABLE subjects (
    slug            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    -- pending | research | scripting | review | assets | editing | uploading | done | rejected
    confidence_score INTEGER,
    llm_source      TEXT,  -- 'gemini' ou 'ollama' (ollama = review manuelle conseillée)
    fact_check_verdict TEXT,  -- PUBLIER | REVISION | REJETER
    youtube_url     TEXT,
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pipeline_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT REFERENCES subjects(slug),
    stage           TEXT,
    duration_sec    REAL,
    success         BOOLEAN,
    error           TEXT,
    ran_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Hook Templates

```json
[
  "Elle a {ACTION}. [PAUSE_1S] Vous n avez jamais entendu son nom.",
  "En {ANNEE}, une femme a {CHANGEMENT}. L histoire a retenu le nom de son collègue.",
  "On lui a volé {CHOSE}. Elle a quand même {REUSSITE}.",
  "Tout le monde connaît {NOM_CELEBRE}. [PAUSE_1S] Personne ne sait que c est {SUJET} qui a tout rendu possible.",
  "Elle avait {AGE} ans quand {EVENEMENT}. [PAUSE_1S] On ne lui a jamais pardonné."
]
```
