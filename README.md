# Youtube ad skipper (FR)

Surveille l'écran et clique sur le bouton **Ignorer** de YouTube dès qu'une
publicité devient ignorable.

```bash
python skipper.py
```

Un lanceur permet aussi de démarrer sans terminal : double-cliquez sur
`run.exe`. Il n'est pas fourni dans le dépôt ; construisez-le une fois avec
`python build_exe.py`.

Arrêt avec Ctrl+C. Un guide pas à pas est disponible dans
[GUIDE.md](GUIDE.md) ; cette page explique surtout **comment ça marche**.
*An English version of this page is available in [README.en.md](README.en.md).*

## Le principe

L'outil **lit l'écran**. `rapidocr-onnxruntime` (un modèle OCR installable via
pip, sans binaire externe) repère du texte n'importe où et renvoie son cadre :
le mot « Ignorer » est donc trouvé quelle que soit sa taille.

Tous les écrans sont balayés en entier, donc le lecteur peut se trouver
n'importe où. Les écrans sont énumérés au démarrage : en brancher un troisième
fonctionne sans rien changer.

## Pourquoi la v0 ne marchait pas

Deux bugs distincts, chacun suffisant à tout casser.

**1. La mise à l'échelle de l'affichage.** L'écran principal est à 125 %. `mss`
capture les vrais pixels (1920x1080) alors que pyautogui travaille dans l'espace
réduit que Windows annonce aux processus non « DPI aware » (1536x864). Le bouton
était donc localisé dans un repère et cliqué dans un autre : chaque clic
atterrissait environ 1,25 fois trop à droite et trop bas. `winput.make_dpi_aware()`
règle ce point avant toute mesure de l'écran, et les clics passent désormais
directement par `user32` plutôt que par pyautogui.

**2. La comparaison d'images.** Les fichiers `ignore_button_fr_screen_*.png`
étaient des captures du bouton à une taille précise. Ce type de comparaison ne
reconnaît que cette taille-là : changer d'écran, passer en plein écran ou en mode
cinéma, ou une refonte de YouTube, et plus rien ne correspondait. La v0 essayait
environ 400 copies redimensionnées par image, ce qui était lent et ratait quand
même le bouton.

## Ce qui est reconnu comme le bouton

L'OCR renvoie une ligne entière de texte à la fois, ce qui a d'abord conduit
l'outil à cliquer n'importe où. Quatre règles l'en empêchent.

- **Le mot doit commencer le texte.** « gitignore » sur le formulaire de dépôt
  GitHub, ou toute phrase mentionnant le mot, le contiennent au milieu : c'est
  précisément ce qui les distingue d'un vrai bouton.
- **La lecture doit être proche.** `Ignorer` et `Ignore` passent, `Ignor` non
  (`--min-similarity`, 0.90 par défaut). Les accents sont retirés et les
  confusions courantes de l'OCR corrigées au préalable : `lgnorer`, `1gnorer` et
  `|gnorer` correspondent donc encore, car rater un vrai bouton est l'échec le
  plus gênant.
- **Le texte doit être court.** Un libellé de bouton fait quelques mots ; une
  ligne de 60 caractères contenant le mot est de la prose.
- **« Ignorer dans 5 » est rejeté** : c'est le décompte *avant* que la publicité
  devienne ignorable, et cliquer dessus ne fait rien.

Le clic vise le **mot reconnu**, pas le centre du cadre OCR. Sur « Ignorer les
annonces » lu comme un seul bloc, le centre tombe sur « annonces » — c'est ce qui
faisait atterrir les clics à côté du mot.

Si un libellé est toujours affiché après avoir été cliqué, ce n'était pas un
bouton d'ignorance (un vrai disparaît) : il est alors ignoré au lieu d'être
cliqué à chaque passage.

## Vitesse

Balayer des écrans entiers coûte naïvement environ 12 s par écran, ce qui serait
inutilisable. Répartition réelle de ce temps, sur un écran 1080p affichant une
page YouTube chargée (240 blocs de texte) :

| étape | coût | ce qui est fait |
| --- | --- | --- |
| détection des blocs de texte | ~0,3 s | peu coûteux et à peu près constant : toujours exécuté |
| découpe des blocs | ~2,8 s | RapidOCR applique une transformation de perspective sur l'image entière pour chaque bloc. Le texte à l'écran étant aligné sur les axes, une simple découpe de tableau la remplace |
| reconnaissance du texte | ~11 s | le vrai coût, proportionnel au nombre de blocs |

La reconnaissance est donc **évitée** plutôt qu'optimisée :

- **Les blocs qui ne peuvent pas être un libellé sont écartés** avant toute
  découpe : trop hauts, trop larges, mauvaises proportions.
- **Les résultats sont mis en cache selon le contenu du bloc.** Une boucle de
  surveillance regarde un écran presque immobile : presque chaque bloc a déjà
  été lu.
- **Seuls les blocs immobiles depuis l'image précédente sont lus.** Une vidéo en
  mouvement invente des formes ressemblant à du texte, différentes à chaque
  image, qui ne seraient jamais dans le cache ; un bouton, lui, est une
  incrustation immobile. Ce qui bouge encore est lu quelques blocs par passage,
  à tour de rôle : rien n'est écarté définitivement, cela prend simplement un
  passage ou deux de plus.

Résultat mesuré sur deux écrans en pleine résolution :

| | coût |
| --- | --- |
| premier passage (cache froid) | ~2 s |
| régime établi | **~0,8 s pour les deux écrans** (~0,4 s chacun) |

Le programme affiche sa cadence réelle une fois stabilisé. Si un passage dure
plus longtemps que `--tick`, c'est la durée du passage qui fait la cadence.

## Options

| Option | Défaut | Rôle |
| --- | --- | --- |
| `--monitor` | `all` | `all` (autant d'écrans que branchés), ou un numéro d'écran (à partir de 1). |
| `--region` | `full` | Restreint le balayage à `br`, `bottom` ou `right` pour réduire le coût du démarrage. Rarement utile. |
| `--tick` | `1` | Délai minimal entre deux passages. Un passage plus long impose sa propre cadence. |
| `--hours` | `6` | Durée d'exécution. |
| `--cooldown` | `4` | Pause après un clic, pour ne pas cliquer un même bouton en rafale. |
| `--keyword` | `ignorer` | Texte recherché. Répétable : `--keyword ignorer --keyword skip`. |
| `--min-similarity` | `0.90` | Proximité exigée avec le mot. À baisser si un bouton est raté. |
| `--min-confidence` | `0.55` | Rejette les lectures OCR moins sûres que ce seuil. |
| `--dry-run` | inactif | Signale les détections sans cliquer. |
| `--debug` | inactif | Écrit les captures annotées dans `debug/`. |
| `--keep-mouse` | inactif | Laisse le curseur sur le bouton au lieu de le remettre en place. |

Le curseur est replacé là où vous l'aviez laissé après chaque clic.

## Tests

```bash
python -m pytest test_matching.py -q
```

couvre les règles d'acceptation et de rejet sur des sorties OCR réalistes, y
compris les erreurs observées en conditions réelles (`gitignore`, lignes de
prose mentionnant le mot).

```bash
python selftest.py
```

vérifie de bout en bout la capture, la mise à l'échelle DPI et le décalage entre
écrans : le script lit un texte déjà affiché, calcule ses coordonnées globales,
recapture exactement à ces coordonnées et confirme que le même texte s'y trouve.
Il dessine aussi un faux bouton « Ignorer les annonces » et vérifie que le point
de clic tombe sur le mot « Ignorer » plutôt qu'au milieu du libellé. Aucune
publicité n'est nécessaire.

## Prérequis

```bash
pip install -r requirements.txt
```

Windows uniquement (`winput.py` utilise l'API Win32). Le dossier `legacy/`
conserve les fichiers de la v0 à titre de référence ; aucun code ne les importe.
