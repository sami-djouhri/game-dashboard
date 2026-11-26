"""Ausnahme fuer fail2ban: nur eine ANGEMELDETE SSH-Sitzung nimmt eine Adresse aus."""
import importlib.util
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[1] / "gamehost" / "fail2ban" / "f2b-ssh-sitzung.py"
_spec = importlib.util.spec_from_file_location("f2b_ssh_sitzung", _PFAD)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

SS = (
    '0 0 192.0.2.10:22 198.51.100.7:45634 users:(("sshd-session",pid=11,fd=7),("sshd-session",pid=10,fd=7))\n'
    '0 0 192.0.2.10:22 203.0.113.9:50000 users:(("sshd-session",pid=20,fd=7))\n'
    '0 0 [::ffff:192.0.2.10]:22 [::ffff:192.0.2.5]:40000 users:(("sshd-session",pid=30,fd=7))\n'
    '0 0 [2001:db8::2]:22 [2001:db8::1]:40001 users:(("sshd-session",pid=40,fd=7))\n'
)
TITEL = {
    10: "sshd-session: root [priv]",
    11: "sshd-session: root",
    20: "sshd-session: [net]",          # Scanner: verbunden, nicht angemeldet
    30: "sshd-session: sami@notty",
    40: "sshd-session: root@pts/0",
}


def _t(pid):
    return TITEL[pid]


def test_angemeldete_sitzung_nimmt_aus():
    assert m.entscheide("198.51.100.7", SS, _t)


def test_offener_connect_ohne_anmeldung_reicht_nicht():
    assert not m.entscheide("203.0.113.9", SS, _t)


def test_fremde_adresse_wird_nicht_ausgenommen():
    assert not m.entscheide("198.51.100.8", SS, _t)


def test_ipv4_in_ipv6_und_ipv6():
    assert m.entscheide("192.0.2.5", SS, _t)
    assert m.entscheide("2001:db8::1", SS, _t)


def test_monitor_allein_zaehlt_nicht():
    ss = '0 0 192.0.2.10:22 198.51.100.7:1 users:(("sshd-session",pid=10,fd=7))\n'
    assert not m.entscheide("198.51.100.7", ss, _t)


def test_titel_varianten():
    for gut in ("sshd-session: root", "sshd-session: root@notty", "sshd-session: a_b-c@pts/3"):
        assert m.ist_angemeldet(gut), gut
    for schlecht in ("sshd-session: [accepted]", "sshd-session: root [priv]",
                     "sshd-session: unknown [preauth]", "sshd-session: root [net]",
                     "sshd: root@notty", ""):
        assert not m.ist_angemeldet(schlecht), schlecht


def test_unsinn_und_verschwundener_prozess_sperren():
    assert not m.entscheide("kein-ip", SS, _t)
    assert not m.entscheide("", SS, _t)

    def weg(pid):
        raise FileNotFoundError(pid)
    assert not m.entscheide("198.51.100.7", SS, weg)


def test_main_ohne_argument_sperrt():
    assert m.main(["f2b"]) == 1
