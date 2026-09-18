#!/usr/bin/env python3
"""Génère core/data/common_passwords.txt (liste de refus embarquée, ~1 250 entrées).

Mots de passe les plus courants + suites clavier + années + variantes françaises.
Relancer :  python scripts/make_passwords.py
"""
from __future__ import annotations

import itertools
import string
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "core" / "data" / "common_passwords.txt"

BASE = """
password 123456 123456789 12345678 12345 1234567 1234567890 123123 111111 1234 12345678910
qwerty qwerty123 qwertyuiop azerty azerty123 qwerty1 qwerty12 abc123 abc1234 abcdef abcdefg
admin administrator root user guest test demo pass passwd password1 password123 password1234
passw0rd pass123 pass1234 iloveyou letmein welcome welcome1 monkey dragon master sunshine
princess starwars football baseball basketball hockey tennis golf fishing hunter killer
batman superman spiderman pokemon pikachu naruto naruto123 naruto1 minecraft fortnite
google facebook youtube instagram tiktok twitter snapchat netflix amazon apple microsoft
windows linux ubuntu debian android iphone samsung huawei xiaomi nokia motorola
motdepasse motdepasse1 motdepasse123 mdp mdp123 bonjour bonjour123 salut coucou coucou123
soleil soleil123 lune etoile amour amour123 famille famille123 copain copine copine123
chocolat chocolat123 chocolatine croissant baguette fromage pizza burger frites kebab
lycee lycee123 college ecole eleve eleve123 prof prof123 cours devoir devoir123
mdl mdl123 mdl2024 mdl2025 mdl2026 maison maison123 chambre cuisine salon jardin
chat chien cheval lapin poisson oiseau dauphin licorne licorne123 panda tigre lion loup
juin juillet aout septembre octobre novembre decembre janvier fevrier mars avril mai
lundi mardi mercredi jeudi vendredi samedi dimanche lundi123 vendredi123
azertyuiop azertyui qsdfgh jklm wxcvbn qsdqsd azerty1234 azertyuiop123
123qwe qwe123 qweasd qweasdzxc asdfgh asdfghjkl asdf1234 zxcvbn zxcvbnm 1q2w3e 1q2w3e4r
1qaz2wsx 1qazxsw2 zaq12wsx 1q1q1q 2w3e4r q1w2e3 q1w2e3r4 q1w2e3r4t5 1234qwer qwer1234
000000 00000 0000 1111 2222 3333 4444 5555 6666 7777 8888 9999 121212 131313 232323
696969 8675309 55555 555555 666666 7777777 888888 999999 999999999 101010 112233
123321 654321 987654321 147258369 159357 753951 456789 456123 789456 789456123
147258 258456 321654 369258147 963852741 741852963 852456 963852 159753 753159
1111111 11111111 111111111 222222222 333333333 555555555 77777777 888888888
superman1 batman1 trustno1 freedom whatever whatever1 whatever123 secret secret123
charlie charlie123 thomas thomas123 robert robert123 michael michael1 jordan jordan23
jennifer jennifer1 jessica jessica1 joshua joshua1 matthew matthew1 andrew daniel
anthony harley rangerbuster george computer internet internet1 server network
changeme changeme123 default temp temporary newpass newpassword reset reset123
temp123 demo123 user123 admin123 test123 test1234 sample example example123
password! p@ssw0rd p@ssword p@ss123 pass@123 password01 password00 password2024
passw0rd! password. password1! admin@123 admin1234 root123 root1234 toor user1234
love love123 loveyou loveme loverboy sex sexy sexy123 money money123 cash cash123
lucky lucky123 lucky7 lucky1234 hello hello123 hello1 hellokitty goodbye bye
merde putain connard salope encule salope123 pute nique
""".split()

KEYBOARD_ROWS = [
    "azertyuiop", "qsdfghjklm", "wxcvbn", "qwertyuiop", "asdfghjkl", "zxcvbnm",
    "1234567890", "&é\"'(-è_çà", "0987654321",
]

WORDS_FR = """
association bureau tresorier president secretaire membre eleve lycee maison salle
permanence babyfoot billard jeux caisse banque coffre bilan compte ecriture recette
depense cotisation subvention evenement animation communication documentation
deplacement restauration fournitures menage nettoyage tache preuve planning
campagne disponibilite creneau gerant interne externe semaine semestre trimestre
rentrée rentree toussaint noel vacances fermetures charte reglement mentions rgpd
invitation motdepasse notification message diffusion accuse lecture relance
""".split()

NAMES = """
marie julie lucas emma louis gabriel lea hugo chloe nathan theo camille manon
lucas1 julie123 emma123 louis123 nathan123 sarah alexandre nicolas anthony
kevin julien maximequentin thibault valentin bastien florent clement
""".split()


def main() -> None:
    items: list[str] = []
    items.extend(BASE)
    items.extend(WORDS_FR)
    items.extend(NAMES)
    # Suites clavier et sous-chaînes
    for row in KEYBOARD_ROWS:
        for size in range(4, 9):
            for start in range(0, len(row) - size + 1):
                items.append(row[start : start + size])
                items.append(row[start : start + size][::-1])
    # Années seules et années suffixées
    for year in range(1900, 2101):
        items.append(str(year))
        items.append("mdp%s" % year)
        items.append("azerty%s" % year)
        items.append("motdepasse%s" % year)
        items.append("mdl%s" % year)
    # Suites numériques et alphabétiques
    for size in range(4, 11):
        items.append("".join(str(i % 10) for i in range(1, size + 1)))
        items.append(string.ascii_lowercase[:size])
        items.append(string.ascii_lowercase[:size].upper())
    # Combinaisons mot + chiffres courts
    for word in ("azerty", "motdepasse", "bonjour", "soleil", "amour", "lycee", "mdl", "admin", "eleve"):
        for suffix in ("1", "12", "123", "1234", "!", "01", "007"):
            items.append(word + suffix)
    # Paires de mots fréquents
    for a, b in itertools.product(("mot", "motde", "mon", "le", "la"), ("passe", "mdp", "lycee", "soleil")):
        items.append(a + b)

    cleaned = []
    seen = set()
    for item in items:
        low = item.strip().lower()
        if len(low) >= 3 and low not in seen:
            seen.add(low)
            cleaned.append(low)
    cleaned.sort()
    header = (
        "# Liste de refus embarquée — mots de passe trop courants.\n"
        "# Générée par scripts/make_passwords.py : mots connus, suites clavier, années, variantes FR.\n"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(header + "\n".join(cleaned) + "\n", encoding="utf-8")
    print("%d entrées écrites dans %s" % (len(cleaned), OUT))


if __name__ == "__main__":
    main()
