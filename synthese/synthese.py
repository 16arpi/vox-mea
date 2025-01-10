import math
import re
import random

from parselmouth import Sound, WindowShape, SoundFileFormat
from parselmouth.praat import call
from textgrids import TextGrid

from .phonetizer import CoquiTTSPhonetizer

SAMPA = re.compile(r'^([a-z]|[A-Z]|[0-9]|~|@)+$')
SAMPA_REPLACEMENTS = {
    "E": "e",
    "e": "E",
    "w": "o"
}

class Synthetiseur:
    """
    Politique de remplacement des diphones inconnus...
    On a un dictionnaire SAMPA_REPLACEMENTS qui indique
    quel label chercher quand l'un est indiponible
    => la raison et que certains phonèmes sont très proches
       (ex: e et E)

    Si rien n'y fait, qu'aucun diphone ne peut être trouvé,
    on renvoie deux phonèmes qui ne se suivent pas.
    """
    def _get_diphone_or_replacement(self, diphones, p1, p2):
        rep1 = SAMPA_REPLACEMENTS.get(p1)
        rep2 = SAMPA_REPLACEMENTS.get(p2)


        # On cherche des diphones basés sur les phonèmes
        # mentionnés (ou leur remplacement)
        if (p1, p2) in diphones:
            return diphones[(p1, p2)]

        if (rep1, p2) in diphones:
            return diphones[(rep1, p2)]

        if (p1, rep2) in diphones:
            return diphones[(p1, rep2)]

        if (rep1, rep2) in diphones:
            return diphones[(rep1, rep2)]

        # Si rien n'est trouvé, on cherche deux
        # phonèmes disjoints (en conservant leur place
        # gauche et droite)
        final_d1 = None
        final_d2 = None
        for ((d1, d2), (dstart, dmiddle1, dmiddle2, dend)) in diphones.items():
            if not final_d1 and p1 == d1:
                final_d1 = (dstart, dmiddle1)
            if not final_d2 and p2 == d2:
                final_d2 = (dmiddle2, dend)

        if not final_d1 or not final_d2:
            raise KeyError((p1, p2))

        (dstart, dmiddle1) = final_d1
        (dmiddle2, dend) = final_d2

        return (dstart, dmiddle1, dmiddle2, dend)

    """
    Imprime dans la console les diphones manquants
    dans l'annotation des logatomes. Des phonèmes
    seront utilisés à leur place
    """
    def _check_diphones(self, phonetic, diphones):
        needed = [(phonetic[i]["label"], phonetic[i+1]["label"]) for i in range(len(phonetic) - 1)]

        missing = [e for e in needed if e not in diphones.keys()]

        if self.use_phonemes:
            if len(missing) > 0:
                print("Les diphones suivants sont manquant, ils seront remplacés par des concaténations de phonèmes")
                for (a, b) in missing:
                    print(f'- {a}{b}')

    """
    Nettoie les codes SAMPA fourni par espeak
    et renvoie des codes SAMPA présents dans
    notre annotation de logatomes
    """
    def _clean_sampa(self, code: str):
        if '-' in code:
            code = code.replace('-', '')
        if code == '2' or code == 'Y':
            code = '@'
        if code == 'A~' or code == 'E~' or code == 'O~':
            code = code.lower()
        return code

    """
    Fonction qui retourne un dictionnaire
    avec tous nos diphones annotés
    """
    def _voicePhonemes(self, textgrid, textgrid_label="phonemes"):
        # return phonemes
        segms = textgrid[textgrid_label]
        grid_size = len(segms)
        result =  {}
        for i in range(1, grid_size - 1):
            d1 = segms[i]
            d2 = segms[i + 1]

            label_1 = d1.text
            label_2 = d2.text

            start = d1.xmin
            middle = d1.xmax
            end = d2.xmax

            result[(label_1, label_2)] = (start, middle, middle, end)

        return result

    """
    Générer la synthèse avec concatenation des diphones
    => Ce faisant, enregistrer le temps de fin + début des phonemes
    Retourner output, phonemes
    """
    def _synthesis(self, phonetic_data, voice_sound, diphones):
        # return output, phonemes enrichis par leur temps
        zeroes = call(self.voice_sound, "To PointProcess (zeroes)", 1, "yes", "no")
        blank = voice_sound.extract_part(0, 0.01, WindowShape.RECTANGULAR, 1, False)
        end = voice_sound.extract_part(0, 0.01, WindowShape.RECTANGULAR, 1, False)
        psize = len(phonetic_data)

        output_length = 0.05

        # Boucle à travers les diphones
        for i in range(psize - 1):
            phoneme1_label = phonetic_data[i]["label"]
            phoneme2_label = phonetic_data[i+1]["label"]

            (d_start, d_middle1, d_middle2, d_end) = self._get_diphone_or_replacement(
                diphones,
                phoneme1_label,
                phoneme2_label
            )

            middle1 = (d_start + d_middle1) / 2
            middle2 = (d_middle2 + d_end) / 2


            # On prend comme début de sample
            # Soit le milieu du premier phoneme
            # Soit le début SI c'est le premier diphone
            nearest_idx_1 = call(zeroes, "Get nearest index", d_start if i == 0 else middle1)
            zero_middle_1 = call(zeroes, "Get time from index", nearest_idx_1)

            # On prend comme fin de sample
            # Soit le milieu du second phoneme
            # Soit la fin SI c'est le dernier diphone
            nearest_idx_2 = call(zeroes, "Get nearest index", d_end if i == psize - 2 else middle2)
            zero_middle_2 = call(zeroes, "Get time from index", nearest_idx_2)

            # Si les deux milieux sont identifiques
            # Alors on a affaire à un vrai diphone
            # Sinon, ce sont deux phonemes indépendants
            if d_middle1 == d_middle2:
                sample = voice_sound.extract_part(zero_middle_1, zero_middle_2, WindowShape.RECTANGULAR, 1, False)
            elif self.use_phonemes:
                nearest_idx_center_1 = call(zeroes, "Get nearest index", d_middle1)
                zero_center_1 = call(zeroes, "Get time from index", nearest_idx_center_1)

                nearest_idx_center_2 = call(zeroes, "Get nearest index", d_middle2)
                zero_center_2 = call(zeroes, "Get time from index", nearest_idx_center_2)

                sample1 = voice_sound.extract_part(zero_middle_1, zero_center_1, WindowShape.RECTANGULAR, 1, False)
                sample2 = voice_sound.extract_part(zero_center_2, zero_middle_2, WindowShape.RECTANGULAR, 1, False)

                sample = sample1.concatenate([sample1, sample2])
            else:
                raise Exception(" ".join(["Diphone manquant :", phoneme1_label, phoneme2_label]))

            time_middle_sample = output_length + (d_middle1 - d_start)

            phonetic_data[i]["end"] = time_middle_sample
            phonetic_data[i+1]["start"] = time_middle_sample

            blank = blank.concatenate([blank, sample])

            output_length += (zero_middle_1 - d_start) + (d_end - zero_middle_2)

        phonetic_data[0]["start"] = 0.05
        phonetic_data[len(phonetic_data) - 1]["end"] = output_length

        blank = blank.concatenate([blank, end])

        return blank, phonetic_data

    """
    Sur une instance de manipulation audio Praat,
    applique la modification de durée et de f0 des
    phonèmes :
    - cinq nouveaux points de f0 par phonème
    - distorsion du coefficient de durée par phonème
    """
    def _postSynthesis(self, pre_output, phonemes):
        # Instance manipulation pre_output (pitch, )
        manipulation = call(pre_output, "To Manipulation", 0.01, 75, 600)

        # Tiers
        pitch_tier = call(manipulation, "Extract pitch tier")
        duration_tier = call(manipulation, "Extract duration tier")

        call(pitch_tier, "Remove points between", 0, pre_output.duration)


        # Pour tout phoneme
        for phoneme in phonemes:

            start = phoneme["start"]
            end = phoneme["end"]

            mid = (start + end) / 2

            length_hypothetic = phoneme["length"]
            length_real = end - start
            length_ratio = length_hypothetic / length_real * 0.50


            # Pitch modifier (4 points de f0 par phonème)
            f0_steps = list(map(lambda x: start + ((end - start) / 5) * x, range(1, 5)))
            for i in range(4):
                f0t = f0_steps[i]
                f0v =  phoneme["f0"][i]
                if not math.isnan(f0v):
                    call(pitch_tier, "Add point", f0t, f0v)

            # Duration modifier
            call(duration_tier, "Add point", start, 1)
            call(duration_tier, "Add point", mid, length_ratio)
            call(duration_tier, "Add point", end, 1)

        call([manipulation, duration_tier], "Replace duration tier")
        call([manipulation, pitch_tier], "Replace pitch tier")

        return call(manipulation, "Get resynthesis (overlap-add)")

    def save(self, sound, filename):
        print(f'Enregistrement de {filename}')
        sound.save(filename, SoundFileFormat.WAV)

    def __init__(
        self,
        voice=("./diphones/logatomes.wav", "./diphones/logatomes.TextGrid"),
        use_phonemes=False,
        phonetizer=CoquiTTSPhonetizer()):

        self.hash = '%032x' % (random.getrandbits(128))
        self.use_phonemes = use_phonemes
        (self.voice_sound, self.voice_textGrid) = (Sound(voice[0]), TextGrid(voice[1]))
        self.phonetizer = phonetizer
        self.diphones = self._voicePhonemes(self.voice_textGrid)

    def speak(self, sentence):
        # Pipeline phonetisation
        self.phonetic_data = list(self.phonetizer.phonetic(sentence))

        # Print la phrase phonetique
        print("".join([a["label"] for a in self.phonetic_data]))

        # Vérification de la disponibilité des diphones
        self._check_diphones(self.phonetic_data, self.diphones)

        self.pre_output, self.phonetic_data = self._synthesis(
            self.phonetic_data,
            self.voice_sound,
            self.diphones
        )

        return self._postSynthesis(self.pre_output, self.phonetic_data)



