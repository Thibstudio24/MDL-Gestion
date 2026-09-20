#!/usr/bin/env bash
# --------------------------------------------------------------------------- #
# Déploie une AUTRE instance MDL Gestion depuis le dépôt GitHub de votre choix,
# crée son compte super-administrateur, puis imprime le bloc d'informations à
# transmettre à la centrale pour la raccorder.
#
# Usage :
#   ./scripts/nouvelle_instance.sh <dépôt-github> <dossier-cible> \
#       [--email admin@asso.fr] [--hub https://centrale.exemple.fr] [--branche main]
#
# Exemple :
#   ./scripts/nouvelle_instance.sh Thibstudio24/MDL-Gestion ~/mdl-lycee2 \
#       --email bureau@lycee2.fr --hub https://mdl-centrale.alwaysdata.net
#
# Sur alwaysdata : lancez-le depuis le compte qui hébergera l'instance ; le
# Python à utiliser peut être forcé avec PYTHON=python (panneau → Environnement).
# --------------------------------------------------------------------------- #
set -euo pipefail

REPO="${1:?dépôt GitHub requis (ex. Thibstudio24/MDL-Gestion)}"
CIBLE="${2:?dossier cible requis (ex. ~/mdl-lycee2)}"
shift 2 || true

EMAIL=""
HUB=""
BRANCHE="main"
PYTHON="${PYTHON:-python3}"

while [ $# -gt 0 ]; do
  case "$1" in
    --email) EMAIL="$2"; shift 2 ;;
    --hub) HUB="$2"; shift 2 ;;
    --branche) BRANCHE="$2"; shift 2 ;;
    *) echo "option inconnue : $1" >&2; exit 2 ;;
  esac
done
EMAIL="${EMAIL:-admin@$(hostname)}"

echo "==> 1/5 Clone de $REPO (branche $BRANCHE) vers $CIBLE"
if [ -d "$CIBLE/.git" ]; then
  echo "    dossier déjà cloné : mise à jour (git pull)"
  git -C "$CIBLE" pull --ff-only || true
else
  git clone --branch "$BRANCHE" "https://github.com/$REPO.git" "$CIBLE"
fi
cd "$CIBLE"

echo "==> 2/5 Environnement Python + dépendances"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

echo "==> 3/5 Base de données + statiques"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput

echo "==> 4/5 Compte super-administrateur ($EMAIL)"
CREATION=$(.venv/bin/python manage.py mdl_admin --email "$EMAIL" | tail -1)
echo "    $CREATION"

if [ -n "$HUB" ]; then
  echo "==> Pointage du hub vers $HUB"
  .venv/bin/python - "$HUB" << 'PYEOF'
import json, pathlib, sys
fichier = pathlib.Path("config/instance.json")
config = json.loads(fichier.read_text()) if fichier.exists() else {}
config.setdefault("hub", {})["url"] = sys.argv[1]
fichier.write_text(json.dumps(config, indent=2, ensure_ascii=False))
print("    hub.url =", sys.argv[1])
PYEOF
fi

echo "==> 5/5 Informations de raccordement pour la centrale"
INFOS=$(.venv/bin/python manage.py mdl_hub_infos)
INSTALL_ID=$(echo "$INFOS" | sed -n 's/^INSTALL_ID=//p')
SECRET=$(echo "$INFOS" | sed -n 's/^SECRET=//p')

cat << BLOC

=====================================================================
  À TRANSMETTRE À LA CENTRALE (super-admin de la centrale)
---------------------------------------------------------------------
  Instance      : $CIBLE (dépôt $REPO)
  Connexion     : $EMAIL  (mot de passe ci-dessus : ligne COMPTE_CREE)
  install_id    : $INSTALL_ID
  secret        : $SECRET
---------------------------------------------------------------------
  Rien à transmettre : l'instance s'enrôle TOUTE SEULE auprès de la
  centrale MDL au premier heartbeat (URL intégrée par défaut, ou
  --hub ci-dessus). Elle apparaîtra « en ligne » côté centrale
  dès son premier contact.
  Il ne reste qu'à planifier le cron alwaysdata de l'instance :
  */15 * * * *  $CIBLE/.venv/bin/python $CIBLE/manage.py mdl_cron
=====================================================================
BLOC
