# Guide d'utilisation

Guide pratique, de l'installation au dépannage. Pour comprendre le
fonctionnement interne, voir [README.md](README.md).

## 1. Installation

Il faut Python 3.10 ou plus récent, sous Windows.

```bash
pip install -r requirements.txt
```

Cela installe `mss` (capture d'écran), `numpy`, `opencv-python` et
`rapidocr-onnxruntime` (le moteur OCR). Aucun logiciel externe n'est à
installer : le modèle OCR arrive avec le paquet pip, il pèse une douzaine de
mégaoctets et fonctionne sur le processeur.

Vérifiez que tout est en place :

```bash
python selftest.py
```

Attendu : `PASS` sur chaque écran détecté. Ce test dessine un faux bouton et
vérifie que le clic tomberait au bon endroit — il ne clique jamais nulle part.

## 2. Lancement

### Avec le lanceur

Double-cliquez sur `run.exe`, dans le dossier du projet. La fenêtre s'ouvre,
l'outil démarre, et elle reste ouverte à la fin pour afficher le résultat.

Le lanceur n'est pas fourni dans le dépôt. Il se construit en une commande :

```bash
python build_exe.py
```

Il ne contient que le lanceur, pas le projet : il exécute `skipper.py` avec le
Python du système. Modifier le code ne demande donc pas de reconstruction. En
revanche il doit rester dans le dossier du projet, à côté de `skipper.py`.

Les options fonctionnent aussi :

```bash
run.exe --dry-run
```

### En ligne de commande

```bash
python skipper.py
```

Vous verrez :

```
Youtube ad skipper -- demarre ...
  watching monitor 1 (1920x1080 at 0,0), region 'full'
  watching monitor 2 (1920x1080 at 1920,0), region 'full'
  looking for ['ignorer'], every 1.0s, for 6.0h
  Ctrl+C to stop

18:31:52  first sweep of 2 monitor(s): 2.1s (building the text cache)
18:32:00  settled -- sweeping all 2 monitor(s) every 1.0s
```

Le premier passage est plus lent : il remplit le cache de texte. La ligne
`settled` indique la cadence réelle une fois stabilisé.

Quand une publicité est ignorée :

```
18:44:07  found 'Ignorer' on monitor 2 at (3188, 880)  [ocr 0.82, match 1.00]
18:44:07  clicked, cursor back at (2053, 442)
```

Arrêtez avec **Ctrl+C**.

## 3. Essayer sans risque

Pour observer ce que l'outil détecterait, sans qu'il touche à la souris :

```bash
python skipper.py --dry-run
```

Rien n'est cliqué, tout est affiché. C'est la bonne façon de vérifier le
comportement avant de le laisser tourner.

## 4. Usages courants

Ne surveiller qu'un seul écran (un peu plus rapide) :

```bash
python skipper.py --monitor 2
```

Le laisser tourner toute la journée :

```bash
python skipper.py --hours 8
```

Chercher aussi le bouton anglais :

```bash
python skipper.py --keyword ignorer --keyword skip
```

Garder le curseur sur le bouton au lieu de le remettre en place :

```bash
python skipper.py --keep-mouse
```

La liste complète des options se trouve dans le [README](README.md#options).

## 5. Ce que fait l'outil à votre souris

À chaque clic :

1. la position actuelle du curseur est mémorisée ;
2. le curseur va sur le bouton, marque une pause de 0,12 s (YouTube réagit au
   survol), puis clique ;
3. le curseur revient exactement où il était.

Si vous étiez en train de taper ou de viser quelque chose, l'interruption dure
environ un quart de seconde. `--keep-mouse` désactive le retour en place.

## 6. Dépannage

### Le bouton s'affiche mais rien ne se passe

Lancez le diagnostic :

```bash
python skipper.py --dry-run --debug
```

Le dossier `debug/` contient alors les captures annotées : chaque texte détecté
est encadré avec sa confiance OCR. Regardez l'image correspondant au moment où
le bouton était visible.

| Ce que montre l'image | Cause | Correction |
| --- | --- | --- |
| Le mot est encadré mais lu bizarrement (`lgn0rer`…) | lecture OCR imparfaite | `--min-similarity 0.85` |
| Le mot est encadré avec une confiance faible (< 0.55) | texte peu lisible | `--min-confidence 0.4` |
| Le mot n'est pas encadré du tout | le bouton bougeait encore, ou le texte est trop petit | attendez un passage de plus ; voir ci-dessous |
| Le libellé est différent d'« Ignorer » | variante de YouTube | ajoutez `--keyword <le texte vu>` |

### Il ne clique pas tout de suite

C'est normal et voulu. Un bouton qui vient d'apparaître par-dessus une vidéo en
mouvement n'est lu qu'une fois immobile, soit au passage suivant — environ une
seconde de plus. Le bouton d'ignorance reste affiché pendant toute la publicité,
donc cela ne le fait pas rater.

### Il clique sur autre chose

Cela ne devrait plus arriver : le mot doit **commencer** le texte lu, ce qui
écarte « gitignore » et les phrases contenant le mot. Si un cas subsiste,
augmentez l'exigence :

```bash
python skipper.py --min-similarity 0.95
```

et signalez le texte fautif — il mérite d'être ajouté à `test_matching.py`.

### Il a cliqué une fois puis s'arrête sur le même élément

Message attendu :

```
'xxx' is still there after being clicked, so it is not a skip button -- ignoring it
```

Un vrai bouton d'ignorance disparaît dès qu'on clique dessus. Un élément qui
reste affiché n'en est pas un : il est mis de côté jusqu'à ce qu'il disparaisse,
pour éviter les clics en rafale.

### Le premier passage est long

Environ 2 s : c'est le remplissage du cache. Les passages suivants tournent
autour de 0,4 s par écran. Pour réduire ce démarrage, limitez la zone :

```bash
python skipper.py --region br
```

`br` ne balaie que le quart inférieur droit. Attention : si le lecteur n'est pas
à cet endroit, le bouton ne sera pas vu. `full` (le défaut) est le choix sûr.

### Les clics tombent à côté

Ce symptôme venait de la mise à l'échelle de l'affichage et est corrigé.
Pour le vérifier sur votre configuration :

```bash
python selftest.py
```

`PASS` signifie que capture, DPI et décalage entre écrans concordent.

## 7. Limites connues

- **Windows uniquement.** `winput.py` s'appuie sur l'API Win32.
- **Une seule langue à la fois par défaut**, réglable avec `--keyword`.
- **Le lecteur doit être visible.** Une fenêtre par-dessus le bouton, ou un
  écran en veille, rend le bouton illisible : l'outil lit ce qui est affiché.
- **Publicités non ignorables.** Les publicités courtes sans bouton « Ignorer »
  ne peuvent pas être passées ; l'outil attend simplement.
