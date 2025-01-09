import argparse

from .phonetizer import CoquiTTSPhonetizer, PraatPhonetizer
from .synthese import Synthetiseur
from .gui import SynthetiseurGUI

parser = argparse.ArgumentParser(
    prog="./synthese",
    description="Moteur Text-to-Speech à partir de ma voix."
)

parser.add_argument('text', help="Texte à synthétiser")
parser.add_argument(
    '-o', '--output', default="output.wav",
    help="Nom du fichier audio final.")
parser.add_argument(
    '-p', '--never-use-phonemes',
    default=True, action="store_false",
    help="Evite que le programme utilise des phonemes quand des diphones sont indisponibles."
)
parser.add_argument(
    '-l', '--legacy-phonetizer',
    default=False, action="store_true",
    help="Utiliser l'ancien phonetiseur basé sur Espeak. Utilise la synthèse neuronale sinon."
)
parser.add_argument(
    '-g', '--gui',
    default=False, action="store_true",
    help="Lancer le mode graphique du programme"
)

args = parser.parse_args()


if args.gui:
    gui = SynthetiseurGUI()
    gui.run()
else:
    synthese = Synthetiseur(
        ("./diphones/logatomes.wav", "./diphones/logatomes.TextGrid"),
        use_phonemes=args.never_use_phonemes,
        phonetizer=PraatPhonetizer() if args.legacy_phonetizer else CoquiTTSPhonetizer()
    )
    output = synthese.speak(args.text)
    synthese.save(output, args.output)
