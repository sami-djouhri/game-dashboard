#!/usr/bin/env python3
"""f2b-ssh-sitzung: ignorecommand fuer fail2ban auf gamehost.

Exit 0 (= fail2ban ignoriert die Adresse), wenn von dieser Adresse gerade eine
ANGEMELDETE SSH-Sitzung besteht, sonst Exit 1.

Warum: Der Heimanschluss hat eine wechselnde Adresse, ein fester ignoreip-Eintrag
veraltet still. Von genau dieser Adresse haelt node1 aber dauerhaft den
Bridge-Tunnel (gamehost-bridge-tunnel.service). Am 2026-11-23 sperrte caddy-proben
den Heimanschluss fuer 18 h, weil eine Sicherheitsprobe aus dem Haus fuenf
Scanner-Pfade abfragte; die Blackbox-Messung von zu Hause war so lange blind, und
recidive zaehlte mit: drei solche Sperren an einem Tag haetten alle Ports
gesperrt, damit auch SSH und den Tunnel selbst.

Ein offener TCP-Connect auf Port 22 reicht NICHT. Sonst kaeme jeder Scanner an
  die Ausnahme, der vor seinem Durchlauf eine Verbindung zu sshd aufmacht. Gezaehlt
  wird nur ein sshd-session-Prozess, dessen Titel einen Benutzer ohne Klammerzusatz
  nennt (`root`, `root@notty`). Vor der Anmeldung steht dort `[net]`,
  `[accepted]` oder `[preauth]`, der Monitor heisst `<user> [priv]`.
Jeder Fehler endet mit Exit 1: im Zweifel wird gesperrt, nicht ausgenommen.
"""
from __future__ import annotations

import ipaddress
import re
import subprocess
import sys

SS_BEFEHL = ["ss", "-tnpH", "state", "established", "( sport = :22 )"]
_ANGEMELDET = re.compile(r"^sshd-session: [a-z_][a-z0-9_.-]*(@notty|@pts/\d+)?$")
_PIDS = re.compile(r"pid=(\d+)")


def normalisiere(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Adresse ohne Port und Klammern; IPv4 in IPv6 (::ffff:a.b.c.d) wird IPv4."""
    adr = ipaddress.ip_address(text.strip().strip("[]"))
    if isinstance(adr, ipaddress.IPv6Address) and adr.ipv4_mapped:
        return adr.ipv4_mapped
    return adr


def gegenstelle(feld: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """`1.2.3.4:5678` oder `[2001:db8::1]:5678` -> Adresse, sonst None."""
    host, _, port = feld.rpartition(":")
    if not host or not port.isdigit():
        return None
    try:
        return normalisiere(host)
    except ValueError:
        return None


def pids_der_adresse(ss_text: str, adr) -> set[int]:
    """PIDs aller Prozesse, die eine Verbindung zu `adr` halten (aus `ss -tnpH`)."""
    pids: set[int] = set()
    for zeile in ss_text.splitlines():
        teile = zeile.split()
        # state established filtert die State-Spalte weg:
        # Recv-Q Send-Q Lokal Gegenstelle Prozess
        if len(teile) < 5:
            continue
        if gegenstelle(teile[3]) != adr:
            continue
        pids.update(int(p) for p in _PIDS.findall(" ".join(teile[4:])))
    return pids


def ist_angemeldet(titel: str) -> bool:
    return bool(_ANGEMELDET.match(titel.strip()))


def entscheide(ip_text: str, ss_text: str, titel_von) -> bool:
    """True, wenn `ip_text` eine angemeldete SSH-Sitzung haelt. `titel_von(pid)` -> str."""
    try:
        adr = normalisiere(ip_text)
    except ValueError:
        return False
    for pid in sorted(pids_der_adresse(ss_text, adr)):
        try:
            if ist_angemeldet(titel_von(pid)):
                return True
        except OSError:
            continue
    return False


def _titel(pid: int) -> str:
    with open(f"/proc/{pid}/cmdline", "rb") as f:
        return f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return 1
    try:
        ss_text = subprocess.run(SS_BEFEHL, check=True, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return 1
    return 0 if entscheide(argv[1], ss_text, _titel) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
