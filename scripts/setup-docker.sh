#!/usr/bin/env bash
# Disposable native release runners only; never an installation-host setup tool.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
printf 'Native runner UID: %s\n' "$(id -u)"
test "$(. /etc/os-release; echo "$ID/$VERSION_CODENAME")" = ubuntu/noble

sudo apt-get -o Acquire::Retries=3 update
sudo apt-get install --no-install-recommends -y ca-certificates curl gnupg
if ! grep -Rqs 'download.docker.com/linux/ubuntu' /etc/apt/sources.list.d; then
  sudo install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
    sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/bundle-docker.gpg
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/bundle-docker.gpg] https://download.docker.com/linux/ubuntu noble stable\n' "$(dpkg --print-architecture)" |
    sudo tee /etc/apt/sources.list.d/bundle-docker.list >/dev/null
fi
sudo apt-get -o Acquire::Retries=3 update
docker_version=$(apt-cache madison docker-ce | awk '$3 ~ /^5:29\.5\.3-/ {print $3; exit}')
test -n "$docker_version"
sudo apt-get install --no-install-recommends -y --allow-downgrades \
  docker-ce="$docker_version" docker-ce-cli="$docker_version" containerd.io
sudo python3 - <<'PY'
import json
from pathlib import Path
path = Path('/etc/docker/daemon.json')
config = json.loads(path.read_text()) if path.exists() else {}
config.setdefault('features', {})['containerd-snapshotter'] = True
# Classic-store driver options do not apply to containerd's snapshotter.
config.pop('storage-driver', None)
config.pop('storage-opts', None)
path.write_text(json.dumps(config) + '\n')
PY
sudo systemctl restart containerd
sudo systemctl reset-failed docker
if ! sudo systemctl restart docker; then
  sudo journalctl -u docker --no-pager -n 30
  exit 1
fi
probe_user=$(getent passwd 1000 | cut -d: -f1 || true)
if test -z "$probe_user"; then
  sudo useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin bundle-probe
  probe_user=bundle-probe
fi
sudo usermod -a -G docker "$probe_user"
python3 scripts/stock.py docker-preflight
