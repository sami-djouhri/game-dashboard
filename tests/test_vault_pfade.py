"""Welten-Downloads: Pfade duerfen das Snapshot-Verzeichnis nie verlassen.

Der Endpunkt gibt eine Datei heraus, deren Name aus der URL kommt. Das ist die
klassische Stelle fuer Pfad-Traversal: mit `../` in der Welt-ID stuende sonst der
ganze Container offen, samt `data/game-dashboard.sqlite` mit allen Passwort-Hashes.
Geprueft wird beides, die Funktion `vault.world_path` und der Weg ueber HTTP.
"""
from __future__ import annotations

import pytest

from app import vault
from app.config import settings

BOESE_WELTEN = [
    "../../etc/passwd",
    "../game-dashboard",
    "..",
    "....//....//etc/passwd",
    "/etc/passwd",
    "welt/../../../root",
    "welt\x00.tar.gz",
    "%2e%2e%2fetc%2fpasswd",
]


@pytest.fixture
def welten(tmp_path):
    """Ein Snapshot-Verzeichnis, wie der Spiegel-Timer es anlegt."""
    wurzel = tmp_path / "worlds"
    (wurzel / "terraria").mkdir(parents=True)
    (wurzel / "valheim.tar.gz").write_bytes(b"valheim-stand")
    (wurzel / "terraria" / "greenleaf.tar.gz").write_bytes(b"terraria-greenleaf")
    settings.worlds_dir = str(wurzel)
    return wurzel


# ── vault.world_path ──────────────────────────────────────────────────
def test_gueltige_pfade_werden_gefunden(welten):
    assert vault.world_path("valheim") == (welten / "valheim.tar.gz").resolve()
    assert vault.world_path("terraria", "greenleaf") == (welten / "terraria" / "greenleaf.tar.gz").resolve()


@pytest.mark.parametrize("welt", BOESE_WELTEN)
def test_welt_verlaesst_das_verzeichnis_nicht(welten, welt):
    assert vault.world_path("terraria", welt) is None, f"„{welt}" + "“ kam durch"


@pytest.mark.parametrize("spiel", ["../app", "/etc", "unbekanntes-spiel", "", "valheim/../valheim"])
def test_nur_bekannte_spiele(welten, spiel):
    """Der Spiel-Schluessel wird gegen die Guide-Liste geprueft, nicht gegen ein
    Muster. Eine Allowlist kann man nicht mit Sonderzeichen ueberreden."""
    assert vault.world_path(spiel) is None


def test_fehlende_datei_gibt_nichts(welten):
    assert vault.world_path("dayz") is None
    assert vault.world_path("terraria", "nie-angelegt") is None


def test_symlink_nach_draussen_wird_abgewiesen(welten, tmp_path):
    """Ein Verweis innerhalb des Verzeichnisses darf nicht aus ihm herausfuehren.
    `resolve()` loest ihn auf, danach muss der Pfad immer noch unterhalb der
    Wurzel liegen - genau diese zweite Pruefung faengt den Fall."""
    geheim = tmp_path / "geheim.tar.gz"
    geheim.write_bytes(b"nichts fuer die Oeffentlichkeit")
    (welten / "dayz.tar.gz").symlink_to(geheim)
    assert vault.world_path("dayz") is None


def test_verzeichnis_statt_datei(welten):
    """`terraria` ist ein Verzeichnis. Ohne die is_file-Pruefung wuerde der
    Endpunkt versuchen, ein Verzeichnis auszuliefern."""
    assert vault.world_path("terraria") is None


def test_liste_zeigt_nur_kuratierte_und_saubere_namen(welten):
    """Manuelle Sicherungen (`zomboid-vor-mods-2026.tar.gz`) und Fremddateien
    bleiben unsichtbar - die Liste ist eine Auswahl, kein Verzeichnislisting."""
    (welten / "zomboid").mkdir()
    (welten / "zomboid" / "vor-mods-2026-01-01.tar.gz").write_bytes(b"x")
    (welten / "zomboid" / "Grossbuchstaben.tar.gz").write_bytes(b"x")
    (welten / "geheim.txt").write_text("kein Spiel")
    (welten / "unbekanntes-spiel.tar.gz").write_bytes(b"x")

    gruppen = {g["key"]: g for g in vault.list_world_groups()}
    assert set(gruppen) == {"valheim", "terraria", "zomboid"}
    zomboid_welten = {w["world"] for w in gruppen["zomboid"]["worlds"]}
    assert zomboid_welten == {"vor-mods-2026-01-01"}, "ein Name ausserhalb des Musters kam durch"
    assert gruppen["valheim"]["worlds"][0]["per_world"] is False
    assert gruppen["terraria"]["worlds"][0]["per_world"] is True


def test_liste_ohne_verzeichnis_ist_leer(tmp_path):
    settings.worlds_dir = str(tmp_path / "gibt-es-nicht")
    assert vault.list_world_groups() == []


# ── Der Weg ueber HTTP ────────────────────────────────────────────────
@pytest.mark.parametrize("welt", BOESE_WELTEN)
def test_download_weist_traversal_ab(verifiziert, welten, welt):
    antwort = verifiziert.get("/api/worlds/terraria/download", params={"world": welt})
    assert antwort.status_code == 404, f"„{welt}" + "“ lieferte eine Datei aus"


def test_download_liefert_die_richtige_datei(verifiziert, welten):
    antwort = verifiziert.get("/api/worlds/terraria/download", params={"world": "greenleaf"})
    assert antwort.status_code == 200
    assert antwort.content == b"terraria-greenleaf"
    assert "greenleaf-terraria-greenleaf.tar.gz" in antwort.headers["content-disposition"]


def test_download_unbekanntes_spiel(verifiziert, welten):
    assert verifiziert.get("/api/worlds/unbekannt/download").status_code == 404


# ── Snapshot-Dateinamen (Restore/Loeschen ueber die Bridge) ───────────
BOESE_DATEIEN = [
    "../../../etc/passwd.tar.gz",
    "/etc/shadow.tar.gz",
    "..\\windows.tar.gz",
    "welt.tar.gz; rm -rf /",
    "welt.sh",
    "welt.tar.gz\nzweite.tar.gz",
    "",
    "Grossbuchstabe.tar.gz",
]


@pytest.mark.parametrize("datei", BOESE_DATEIEN)
def test_restore_weist_unsaubere_dateinamen_ab(admin, bruecke, datei):
    antwort = admin.post("/api/games/valheim/restore", json={"file": datei})
    assert antwort.status_code == 400, f"„{datei}" + "“ wurde zum Zurueckspielen angenommen"
    assert not bruecke.kam_an("restore_snapshot")


@pytest.mark.parametrize("datei", BOESE_DATEIEN)
def test_loeschen_weist_unsaubere_dateinamen_ab(admin, bruecke, datei):
    antwort = admin.post("/api/games/valheim/snapshots/delete", json={"file": datei})
    assert antwort.status_code == 400
    assert not bruecke.kam_an("delete_snapshot")


def test_sauberer_snapshot_name_kommt_durch(admin, bruecke):
    antwort = admin.post("/api/games/valheim/restore",
                         json={"file": "nightly/valheim-2026-09-17.tar.gz"})
    assert antwort.status_code == 200
    assert bruecke.zuletzt() == ("restore_snapshot", "valheim", "nightly/valheim-2026-09-17.tar.gz")


def test_restore_ohne_json_body(admin):
    antwort = admin.roh_post("/api/games/valheim/restore", data={},
                             headers={"X-CSRF-Token": admin.csrf})
    assert antwort.status_code == 400
