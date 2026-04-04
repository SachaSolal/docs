# 05-upload — Publication YouTube

Upload automatique via YouTube Data API v3 avec métadonnées
générées par Gemini. Anti-spam et validation thumbnail Telegram.

## Flux d'upload

```
[Input] /04-edit/exports/{slug}.mp4
        /02-scripts/approved/{slug}.json (métadonnées)
        /03-assets/raw-images/{slug}/thumbnail.png
    |
    v
[1] Validation thumbnail → envoi Telegram → attente /ok_{slug}
    |
    v
[2] Upload vidéo (status: private)
    → attente 45s (évite le double flaggage spam)
    |
    v
[3] Mise à jour métadonnées (titre, description, tags)
    → appel séparé de l'upload (réduit le risque de ban)
    |
    v
[4] Passage en public (heure variable 9h-11h selon config)
    |
    v
[5] Notification Telegram "✅ Vidéo publiée"
    → lien YouTube + stats initiales
```

## Anti-spam YouTube — Règles appliquées

```python
UPLOAD_RULES = {
    # Toujours uploader en private d'abord
    "initial_status": "private",

    # Attente entre upload et update métadonnées
    "metadata_delay_sec": 45,

    # Heure de publication variable (évite le pattern répétitif)
    "publish_hour_range": (9, 11),  # heure locale aléatoire dans cette plage

    # Longueur description minimum
    "min_description_chars": 300,

    # Tags : minimum 8, maximum 15
    "tags_count_range": (8, 15),
}
```

## Génération métadonnées Gemini

Les métadonnées sont extraites directement du script JSON (champ `youtube_metadata`).
Un second prompt Gemini génère les tags SEO depuis le script :

```python
TAGS_PROMPT = """
Génère 12 tags YouTube pour une vidéo biographique sur {nom} ({période}).

Règles :
- Mix : tags larges (histoire, femmes historiques) + tags précis (nom, époque, pays)
- Inclure des tags en anglais pour toucher l'audience internationale
- Éviter les tags trop génériques (histoire, femme)
- Format : liste Python de strings

Contexte : {résumé_biographique}
"""
```

## Quota YouTube Data API v3

| Opération | Coût (unités) | Quota/jour |
|---|---|---|
| Upload vidéo | 1600 | 10 000 |
| Update métadonnées | 50 | — |
| Update status (public) | 50 | — |
| **Total par vidéo** | **~1700** | max ~5 vidéos/jour |

Pour 1 vidéo/semaine : aucun risque de quota.

## Notification Telegram finale

```
✅ Vidéo publiée !

📹 Ada Lovelace — La programmatrice oubliée
🔗 youtube.com/watch?v=xxxxx
📊 Statut : Public
🕐 Publié à 10h34

Pipeline terminé en 47 minutes.
```
