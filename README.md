# Synthèse vocale personnelle

_Vox mea_ est un programme de synthèse vocale par concaténation de diphones prenant appui sur ma propre voix. Projet réalisé dans le cadre du cours de Synthèse de la parole du Master Plurital (INALCO, Sorbonne Nouvelle, Paris Nanterre).

Développé sous python v3.11

## Installation

Installer les dépendances à l'aide de :

```bash
$ pip install -r requirements.txt
```

Ou bien :

```bash
$ pip install praat-parselmouth praat-textgrids requests TTS
```

## Utilisation

> Attention : ce programme nécessite une connexion internet

Pour lancer le programme, executer la commande suivante :

```bash
python -m synthese "C'est une affaire intéressante, qu'en pensez-vous ?"
```

Les paramètres disponibles sont :

* `-h`, `--help` : Montrer le message d'aide
* `-o OUTPUT`, `--output OUTPUT` : Spécifier le nom du fichier audio généré
* `-p`, `--never-use-phonemes` : Evite que le programme utilise des phonèmes quand des diphones sont indisponibles.
* `-l`, `--legacy-phonetizer` : Utiliser l'ancien phonetiseur basé sur Praat-Espeak (par défaut utilise la synthèse neuronale CoquiTTS).

## Exemples d'audios

Se trouve dans le dossier `./samples` 5 audios issus de la synthèse des phrases suivantes :

* _C'est une affaire intéressante, quand pensez vous ?_
* _Bonjour, je m'appelle César, j'habite à Paris et j'ai vingt-cinq ans_
* _J'ai conçu cette synthèse vocale à partir de ma propre voix_
* _Tu veux que je te prenne des trucs au franprix ?_
* _Du bristole et de la naphtaline de chez leroi merlin_


## Fonctionnement

### Phonétiseur (label SAMPA, durée, fréquence fondamentale)

Le programme propose deux phonétiseurs différents : `CoquiTTSPhonetizer` ou `PraatPhonetizer`.

Alors que le second est basé sur la méthode présentée en cours (synthétiseur espeak, lecture du textgrid, valeurs de f0/durée aux occurences des phonèmes etc.), le premier est plus complexe car il repose sur une synthèse neuronale préalable.

À partir d'une phrase en français, le processus de phonétisation se découpe en 4 étapes :

1. Nous chargeons le modèle [VITS](https://docs.coqui.ai/en/latest/models/vits.html) de CoquiTTS et nous lui demandons de générer un fichier WAV à partir de la phrase. Ce fichier WAV est placé dans un sous-dossier caché. Un fichier TXT contenant la phrase est aussi créé dans ce sous-dossier.
2. Nous envoyons le fichier WAV et le fichier TXT vers un webservice où est executé le programme [_Munich AUtomatic Segmentation System_](https://www.bas.uni-muenchen.de/Bas/BasMAUS.html). Ce programme prend le fichier WAV et le fichier TXT et renvoie un fichier TextGrid comprenant une segmentation en phonèmes de la phrase.
3. Ensuite, nous explorons les intervalles du TextGrid téléchargé et nous renvoyons, au fur et à mesure, les informations sur ces phonèmes (label SAMPA, durée, f0).
4. Nous supprimons le sous dossier caché qui ne nous sert plus.

L'instance permet de renvoyer une liste de dictionnaires, un dictionnaire par phonème. Chaque dictionnaire comprend trois informations :

* Le label SAMPA
* la durée du phonème
* Les f0

**Codes SAMPA**

Pour être sûr qu'il y a les mêmes codes SAMPA entre le phonetiseur et l'annotation des logatomes, le phonetiseur « nettoye » les codes SAMPA récupéré par la segmentation automatique de phonèmes. Ce nettoyage consiste à remplacer certains codes SAMPA vers d'autres très proches :

* `9~` en `e~`
* `2` et `Y` en `@`
* `A~`, `E~` et `O~` en `a~`, `e~` et `o~`

**Fréquences fondamentales**

Pour avoir une bonne représentation de l'évolution de la f0 de chaque phonème, le programme récupère quatre valeurs de f0 par phonème. Chacune est équidistante l'une de l'autre afin de couvrir tout le phonème.

### Synthétiseur

Une fois nos informations phonétiques récupérées, la seconde étape consiste, d'une part, à concaténer les diphones puis, d'autre part, à moduler leur durée et leur fréquence fondamentale.

**Concaténation des diphones**

Nous itérons dans nos informations phonétiques deux par deux. On appelle une méthode chargée de nous renvoyer les  annotations de logatomes correspondant à nos deux phonèmes. Cette méthode – appelée `_get_diphone_or_replacement()` — a deux stratégies :

* Si le diphone a été annoté, alors il retourne les temps de son annotation (_début_, _milieu 1_, _milieu 2_, _fin_). Dans ce cas précis, _milieu 1_ est égal à _milieu 2_.
* Si le diphone n'a pas été annoté, la méthode renvoie les temps d'annotation de deux phonèmes disjoints. Dans ce cas, _milieu 1_ et _milieu 2_ ne sont pas égaux. La méthode fait attention de sélectionner comme premier phonème un phonème annoté « à gauche » et comme second phonème un phonème annoté « à droite ».

S'en suit la récupération du segment audio du diphone (à la moitié de chaque phonème). Un seul segment est récupéré si le diphone était bien annoté, deux sont récupérés puis concaténés s'il s'agit de deux phonèmes disjoints. Ces segments commencent tous à zero. On ajoute à nos informations phonétiques le temps de début et de fin de chaque phonème traité.

Pour le premier phonème de la séquence, on prend dans le segment audio sa première moitié de premier phonème. Idem pour le dernier phonème, on prend la seconde moitié de son second phonème. Cela permet de garantir l'intégrité des phonèmes placés aux extrémités.

**Modulation de la prosodie**

À partir de nos informations phonétiques mises à jour et de notre audio de diphones concaténés, nous pouvons appliquer sur l'audio la prosodie mesurée sur notre audio de synthèse neuronale.

Pour la _fréquence fondamentale_, on reprend les quatre points de f0 de chaque phonème et on l'ajoute à notre audio final. Pour la _durée_, on multiplie la durée du segment du phonème par le ratio $\frac{durée\ théorique}{durée\ réelle}$.

Nous enregistrons le nouvel audio dans un fichier WAV.

## Bilan et améliorations

Le programme fonctionne bien pour les phrases choisis (on comprend les phrases et elles présentent une intonation plutôt naturelle). Il y a des artefacts, sans doute liées à des problèmes dans l'annotation des logatomes, mais aussi par la concaténation à certaines occasions de phonèmes et non de diphones : leur présence s'explique par la difficulté à prévoir à l'avance les phonèmes et codes SAMPA retournés par la segmentation automatique des phonèmes. Cela nous force à concaténer des phonèmes et cela réduit la qualité de l'audio final. De plus, notre enregistrment de logatomes est composé de deux parties concaténées (suite à un ajout effectué plus tard), cela s'entend un peu dans l'audio final.

À l'avenir, nous pourrions enregistrer et annoter bien plus de diphones. Il en faudrait plus de 800 pour couvrir une bonne partie des mots et liaisons de la langue française. Nous pourrions pré-traiter l'annotation d'un enregistrement grâce à notre programme d'annotation automatique de phonèmes. Enfin, dans sa programmation même, le programme gagnerait à ne pas recourir à un service en ligne afin de pouvoir s'exécuter en local, il faudrait pour ça compiler et exécuter _Munich AUtomatic Segmentation System_ en local (or le code source est introuvable).
