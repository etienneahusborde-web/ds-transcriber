# DS2 Transcriber — application web sur Render

Application web **prototype**, accessible depuis un navigateur, pour convertir les fichiers Olympus `.ds2` / `.dss` en WAV et produire une transcription française en TXT et SRT.

## Déploiement (aucune compilation sur votre PC)

1. Créer un dépôt GitHub contenant **les fichiers de ce dossier à la racine** (ne pas déposer seulement le ZIP).
2. Dans Render, choisir **New → Blueprint** puis connecter le dépôt GitHub.
3. Valider la création du service défini dans `render.yaml` (plan **Free**).
4. À la fin du build Docker, ouvrir l'adresse `https://<nom-du-service>.onrender.com` attribuée par Render.

Le déploiement compile automatiquement le décodeur [hirparak/dss-codec](https://github.com/hirparak/dss-codec), [whisper.cpp](https://github.com/ggml-org/whisper.cpp) et télécharge le modèle **Tiny multilingue** (~75 Mio) dans l'image Docker.

## Réserves importantes

- Render **Free** n'offre que **512 Mo de RAM** et un CPU très limité. L'exécution de Whisper Tiny **peut dépasser** la mémoire disponible ou durer très longtemps. **Le déploiement et la transcription ne sont pas garantis**, faute de validation sur une instance Render réelle.
- Le service gratuit s'endort après une période d'inactivité, peut redémarrer et ne convient pas à un service public de production.
- Un seul traitement à la fois ; demandes supplémentaires refusées temporairement.
- Limites initiales : fichier de 12 Mio maximum, audio de 10 minutes maximum.
- Les fichiers traités restent disponibles temporairement, et sont supprimés opportunément environ 30 min après la fin du traitement. **Un redémarrage détruit les fichiers.** Ce mécanisme n'offre pas de garantie d'effacement immédiat.
- L'accès aux téléchargements repose sur un identifiant aléatoire difficile à deviner. **N'utilisez pas le prototype pour des documents confidentiels** ; pour un site public, ajouter un vrai système de suppression automatique, du contrôle d'accès, une protection anti-abus et un hébergement dimensionné.
- Les barres d'état correspondent aux *étapes* du travail et non à un pourcentage de calcul.
- Pour de meilleures transcriptions, il faudra un hébergement plus puissant pour utiliser `small` ou `medium`.

## Essai local (Docker uniquement)

```bash
docker build -t ds2-transcriber .
docker run --rm -p 10000:10000 -e PORT=10000 ds2-transcriber
```

Puis ouvrir `http://localhost:10000`.

## Technologies

Python Flask + Gunicorn, `dss-decode` (Rust), ffmpeg, `whisper.cpp` (Tiny français/multilingue), Docker.

Code d'intégration fourni tel quel, sans garantie de fonctionnement sur l'offre gratuite.
