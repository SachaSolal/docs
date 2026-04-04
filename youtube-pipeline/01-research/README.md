# 01-research — Collecte & Fact-Checking

Ce module récupère toutes les sources brutes sur une femme historique
et les consolide dans la Knowledge Base.

## Rôle dans le pipeline

```
n8n CRON
  → Execute Command : python 01-research/scraper.py --slug "ada-lovelace"
  → Écrit : /knowledge_base/{slug}/01_wikipedia.json
  → Écrit : /knowledge_base/{slug}/02_academic.json
  → Écrit : /knowledge_base/{slug}/03_web_articles.json
  → Écrit : /knowledge_base/{slug}/04_sources.txt
  → Met à jour SQLite : status = 'research_done'
```

## Sources utilisées (toutes gratuites)

| Source | API | Usage |
|---|---|---|
| Wikipedia | `wikipedia-api` Python | Base biographique |
| Semantic Scholar | api.semanticscholar.org | Papiers académiques |
| CORE | core.ac.uk/api | Open access agrégé |
| Gallica BNF | gallica.bnf.fr/api | Sources françaises |
| Tavily | tavily.com (1000 req/mois gratuit) | Recherche web IA |
| Gemini Grounding | Gemini API (Google Search) | Synthèse multi-sources |

## Structure de la Knowledge Base

```
/knowledge_base/{slug}/
  01_wikipedia.json       ← données Wikipedia structurées
  02_academic.json        ← papiers Semantic Scholar + CORE
  03_web_articles.json    ← articles Tavily + Gemini Grounding
  04_sources.txt          ← toutes les URLs utilisées
  05_fact_check.json      ← résultat validation (généré par 02-scripts)
  06_script_final.json    ← script validé (cache — ne pas re-générer)
  notes_humaines.md       ← optionnel : ajout manuel de sources
```

## Prompt de consolidation Gemini

Après scraping, Gemini consolide les sources brutes :

```python
CONSOLIDATION_PROMPT = """
Tu reçois des données brutes de plusieurs sources sur : {nom}

Synthétise en JSON structuré :
{
  "faits_verifies": [  // présents dans 2+ sources
    {"fait": "...", "sources": ["url1", "url2"]}
  ],
  "faits_uniques": [   // 1 seule source, à traiter avec prudence
    {"fait": "...", "source": "url1"}
  ],
  "contradictions": [  // sources en désaccord
    {"sujet": "...", "version_a": "...", "version_b": "..."}
  ],
  "lacunes": [         // questions sans réponse dans les sources
    "Quelle était sa relation avec X ?"
  ]
}

Sources brutes :
{sources_brutes}
"""
```

## Déclenchement depuis n8n

Nœud "Execute Command" :
```bash
python /app/scripts/01_scraper.py --slug "{{$json.slug}}" --name "{{$json.name}}"
```
