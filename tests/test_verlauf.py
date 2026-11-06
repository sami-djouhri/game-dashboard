"""Die Uebergangs-Erkennung: aus zwei Momentaufnahmen werden Ereignisse.

Geprueft wird `app/verlauf.py` direkt. Die Funktion ist rein, deshalb braucht
kein Test hier einen Arbiter, eine Datenbank oder eine Wartezeit.

Die Faelle sind nach dem gewaehlt, was im Betrieb vorkommt und was bisher
NICHT im Log stand: das Auto-Off des Arbiters und der Start aus Discord.
"""
from __future__ import annotations

from app import verlauf
from app.verlauf import Stand
from tests.conftest import anmelden, konto


def _aktionen(ereignisse) -> list[str]:
    return [e.action for e in ereignisse]


def test_erster_blick_meldet_geweckt():
    ereignisse, stand = verlauf.uebergaenge({}, {"valheim": 0}, jetzt=1000.0)

    assert _aktionen(ereignisse) == ["spiel.wach"]
    assert "valheim" in stand


def test_start_aus_discord_hat_keinen_namen():
    """Der Fall, den das Dashboard bisher gar nicht sah.

    `/game valheim start` geht direkt an die wake-bridge. Ohne bekannten
    Ausloeser bleibt die Zeile namenlos, statt jemanden zu erfinden: dieselbe
    Entscheidung wie bei `ausgeloest_von` in den Spielzeiten.
    """
    ereignisse, _ = verlauf.uebergaenge({}, {"valheim": 0}, jetzt=1000.0, starter={})

    assert ereignisse[0].detail == "geweckt"
    assert ereignisse[0].actor == "arbiter"


def test_start_ueber_die_seite_nennt_den_namen():
    ereignisse, _ = verlauf.uebergaenge({}, {"valheim": 0}, jetzt=1000.0,
                                        starter={"valheim": "sami"})

    assert ereignisse[0].detail == "geweckt von sami"
    assert ereignisse[0].actor == "sami"


def test_erster_spieler_und_neue_spitze():
    _, stand = verlauf.uebergaenge({}, {"valheim": 0}, jetzt=1000.0)
    ereignisse, stand = verlauf.uebergaenge(stand, {"valheim": 1}, jetzt=1060.0)
    assert [e.detail for e in ereignisse] == ["erster Spieler ist drin"]

    ereignisse, stand = verlauf.uebergaenge(stand, {"valheim": 3}, jetzt=1120.0)
    assert [e.detail for e in ereignisse] == ["3 im Spiel"]

    # Gleiche Zahl noch einmal: keine neue Zeile. Sonst stuende bei jedem
    # 60-Sekunden-Durchgang dieselbe Meldung im Verlauf.
    ereignisse, stand = verlauf.uebergaenge(stand, {"valheim": 3}, jetzt=1180.0)
    assert ereignisse == []

    # Rueckgang unter die Spitze ist auch keine Meldung wert.
    ereignisse, stand = verlauf.uebergaenge(stand, {"valheim": 2}, jetzt=1240.0)
    assert ereignisse == []


def test_leer_und_dann_aus():
    """Das Auto-Off des Arbiters, der haeufigste Fall ohne jede Zeile.

    Ein Server geht nach zwanzig Minuten Leerlauf von selbst aus. Bis hierhin
    endete die Geschichte im Log beim Start, und warum er jetzt aus ist, stand
    nirgends.
    """
    _, stand = verlauf.uebergaenge({}, {"valheim": 0}, jetzt=0.0)
    _, stand = verlauf.uebergaenge(stand, {"valheim": 3}, jetzt=60.0)

    ereignisse, stand = verlauf.uebergaenge(stand, {"valheim": 0}, jetzt=7000.0)
    assert [e.detail for e in ereignisse] == ["niemand mehr drin"]

    ereignisse, stand = verlauf.uebergaenge(stand, {}, jetzt=8400.0)
    assert _aktionen(ereignisse) == ["spiel.aus"]
    assert "2 h 20 min" in ereignisse[0].detail
    assert "3 Spieler" in ereignisse[0].detail
    assert stand == {}


def test_geweckt_und_nie_betreten_sagt_das():
    """Die Zeile, an der man sieht, dass sich das Wecken nicht gelohnt hat."""
    _, stand = verlauf.uebergaenge({}, {"factorio": 0}, jetzt=0.0)
    ereignisse, _ = verlauf.uebergaenge(stand, {}, jetzt=1200.0)

    assert "niemand war drin" in ereignisse[0].detail
    assert "20 min" in ereignisse[0].detail


def test_ausfall_der_messung_meldet_nicht_leer():
    """⚠️ Eine Spielerzahl von -1 heisst „nicht gemessen", nicht „niemand da".

    Der Test fuhr bis 2026-10-23 einen Server, der NIE Spieler hatte, und
    war damit wertlos: `max(0, -1)` ergibt 0, und bei dauerhaft leerem Server
    kommt mit und ohne die Unterscheidung dasselbe heraus. Eine Mutation, die
    `messbar` fest auf wahr setzte, blieb unbemerkt. Der aussagekraeftige Fall
    ist der Ausfall MITTEN in einer laufenden Runde: ohne die Unterscheidung
    stuende dann „niemand mehr drin", waehrend drei Leute weiterspielen.
    """
    _, stand = verlauf.uebergaenge({}, {"valheim": 0}, jetzt=0.0)
    _, stand = verlauf.uebergaenge(stand, {"valheim": 3}, jetzt=60.0)

    # Abfrageport antwortet nicht mehr, die Runde laeuft weiter.
    ereignisse, stand = verlauf.uebergaenge(stand, {"valheim": -1}, jetzt=120.0)
    assert ereignisse == [], "ein Messausfall ist keine Meldung ueber Spieler"
    assert stand["valheim"].spieler == 3, "der letzte gemessene Stand bleibt stehen"

    # Und wenn die Messung zurueckkommt, darf es keine Phantom-Zeile geben.
    ereignisse, stand = verlauf.uebergaenge(stand, {"valheim": 3}, jetzt=180.0)
    assert ereignisse == []


def test_server_ohne_abfrageport_bleibt_still():
    """Avorion und Minecraft haben keinen Abfrageport. Ueber ihre ganze
    Laufzeit darf keine einzige Spieler-Zeile entstehen."""
    _, stand = verlauf.uebergaenge({}, {"avorion": -1}, jetzt=0.0)
    for t in (60.0, 120.0, 180.0):
        ereignisse, stand = verlauf.uebergaenge(stand, {"avorion": -1}, jetzt=t)
        assert ereignisse == []

    ereignisse, _ = verlauf.uebergaenge(stand, {}, jetzt=240.0)
    assert _aktionen(ereignisse) == ["spiel.aus"]
    assert "niemand war drin" in ereignisse[0].detail


def test_zwei_spiele_stoeren_einander_nicht():
    """Seit dem Mehr-Spiel-Umbau laufen Server nebeneinander. Jeder fuehrt
    seine eigene Laufzeit und seine eigene Spitze."""
    _, stand = verlauf.uebergaenge({}, {"valheim": 2}, jetzt=0.0)
    ereignisse, stand = verlauf.uebergaenge(stand, {"valheim": 2, "zomboid": 0}, jetzt=600.0)

    assert [(e.game, e.action) for e in ereignisse] == [("zomboid", "spiel.wach")]

    ereignisse, stand = verlauf.uebergaenge(stand, {"zomboid": 0}, jetzt=1200.0)
    assert [(e.game, e.action) for e in ereignisse] == [("valheim", "spiel.aus")]
    assert "20 min" in ereignisse[0].detail, "valheims eigene Laufzeit, nicht zomboids"


def test_dauer_in_worten():
    assert verlauf._dauer(0) == "0 min"
    assert verlauf._dauer(60 * 45) == "45 min"
    assert verlauf._dauer(60 * 120) == "2 h"
    assert verlauf._dauer(60 * 135) == "2 h 15 min"


# ── Der Endpunkt ──────────────────────────────────────────────────────
def test_verlauf_endpunkt_trennt_die_terraria_instanzen():
    """Der Bestandsfehler, den die neue Spalte behebt.

    Bis zum 2026-10-23 wurde das Spiel mit `detail LIKE 'terraria%'` aus dem
    Fliesstext geraten. Das trifft seit dem 2026-10-11 alle drei Instanzen:
    wer GreenerForest weckte, stand danach auch im Verlauf von GreenForest.
    """
    from app import db
    s = anmelden(konto("verlaufleser"), "verlaufleser")
    db.log_event("tobi", "game.start", "terraria-wildwuchs welt=wildwuchs -> ok",
                 game="terraria-wildwuchs")

    fremd = s.get("/api/games/terraria/verlauf").json()["eintraege"]
    eigen = s.get("/api/games/terraria-wildwuchs/verlauf").json()["eintraege"]

    assert fremd == [], "GreenForest darf den Start von GreenerForest nicht zeigen"
    assert len(eigen) == 1


def test_alte_zeilen_ohne_spalte_werden_gefunden():
    """Zeilen aus der Zeit vor der Spalte tragen game=''. Der Rueckfall muss
    sie finden, und zwar OHNE die Verwechslung von oben wieder einzubauen."""
    from app import db
    s = anmelden(konto("altleser"), "altleser")
    db._exec("INSERT INTO events(ts,actor,action,detail,game) VALUES(?,?,?,?,'')",
             (db.now_iso(), "sami", "game.start", "terraria welt=greenleaf -> ok"))
    db._exec("INSERT INTO events(ts,actor,action,detail,game) VALUES(?,?,?,?,'')",
             (db.now_iso(), "tobi", "game.start", "terraria-calamity -> ok"))

    eigen = s.get("/api/games/terraria/verlauf").json()["eintraege"]

    assert len(eigen) == 1, "die Calamity-Zeile gehoert nicht zu terraria"
    assert eigen[0]["actor"] == "sami"


def test_verlauf_bleibt_ohne_bridge_lesbar(monkeypatch):
    """⚠️ Der Verlauf fragt die Bridge bewusst nicht.

    Ein Server, der nicht antwortet, ist der haeufigste Anlass nachzusehen, was
    zuletzt mit ihm war. Haenge der Endpunkt an `_validate_game`, waere er
    genau dann tot, wenn man ihn braucht.
    """
    import httpx
    from app import bridge

    async def kaputt():
        raise httpx.ConnectError("Bridge weg")

    monkeypatch.setattr(bridge, "get_status", kaputt)
    s = anmelden(konto("notleser"), "notleser")

    antwort = s.get("/api/games/valheim/verlauf")
    assert antwort.status_code == 200
