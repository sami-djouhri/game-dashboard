"""Was mit einem Server passiert ist, als Zeilen im Verlauf.

Der 60-Sekunden-Sampler beobachtet ohnehin den Arbiter-Status, um die
Spielzeiten zu fuehren. Dieses Modul leitet aus zwei aufeinanderfolgenden
Beobachtungen die Ereignisse ab, die dazwischen liegen.

Der Gewinn ist nicht die Bequemlichkeit, sondern die Abdeckung. Im Audit-Log
standen bisher nur Vorgaenge, die ueber die Weboberflaeche kamen. Zwei haeufige
Faelle fehlten vollstaendig:

  * Das Auto-Off des Arbiters. Ein Server, der nach zwanzig Minuten Leerlauf von
    selbst ausgeht, hinterliess keine Zeile. Im Verlauf endete die Geschichte
    beim Start, und warum der Server jetzt aus ist, stand nirgends.
  * Starts ueber Discord. `/game valheim start` geht direkt an die wake-bridge,
    am Dashboard vorbei. Die Kachel zeigte den Server als laufend, der Verlauf
    kannte den Start nicht.

Die Erkennung ist eine REINE Funktion ueber zwei Momentaufnahmen, kein Teil
der Schleife. Nur so laesst sie sich ohne laufenden Arbiter und ohne Wartezeit
pruefen; die Schleife drumherum reicht ihr nur Zustand und Uhr herein.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Stand:
    """Was wir beim letzten Blick ueber einen laufenden Server wussten."""
    spieler: int = 0
    spitze: int = 0
    seit: float = 0.0               # Zeitstempel in Sekunden (monoton oder Epoche)
    starter: str = ""               # wer ihn geweckt hat, sofern bekannt


@dataclass
class Ereignis:
    game: str
    action: str
    detail: str
    actor: str = "arbiter"
    stand: dict[str, Stand] = field(default_factory=dict, repr=False)


def _dauer(sekunden: float) -> str:
    """Laufzeit in Worten. Minuten bis 90, danach Stunden und Minuten.

    Eigene Formatierung und nicht die aus app.js: dort wird eine laufende
    Startdauer angezeigt (Sekunden zaehlen), hier eine abgeschlossene Laufzeit
    (Stunden zaehlen). „7140 min" waere richtig und unlesbar.
    """
    minuten = int(round(sekunden / 60))
    if minuten < 90:
        return f"{minuten} min"
    stunden, rest = divmod(minuten, 60)
    return f"{stunden} h" if rest == 0 else f"{stunden} h {rest} min"


def uebergaenge(vorher: dict[str, Stand], laufend: dict[str, int],
                jetzt: float, starter: dict[str, str] | None = None,
                ) -> tuple[list[Ereignis], dict[str, Stand]]:
    """Zwei Momentaufnahmen rein, die Ereignisse dazwischen raus.

    `laufend` ist {spiel: spielerzahl} aus der aktuellen Beobachtung, `vorher`
    derselbe Stand vom letzten Durchgang. Zurueck kommen die Ereignisse und der
    neue Stand, den der Aufrufer fuer das naechste Mal aufhebt.

    ⚠️ Eine Spielerzahl von -1 heisst „nicht fernpruefbar", nicht „niemand da".
    Solche Server (ohne Abfrageport) duerfen keine Spieler-Ereignisse
    ausloesen, sonst stuende im Verlauf jede Minute abwechselnd „erster
    Spieler" und „niemand mehr drin" fuer etwas, das nie gemessen wurde.
    """
    starter = starter or {}
    ereignisse: list[Ereignis] = []
    neu: dict[str, Stand] = {}

    for game, spieler in laufend.items():
        alt = vorher.get(game)
        messbar = spieler >= 0
        zahl = max(0, spieler)

        if alt is None:
            wer = starter.get(game, "")
            ereignisse.append(Ereignis(
                game, "spiel.wach",
                f"geweckt von {wer}" if wer else "geweckt",
                actor=wer or "arbiter"))
            alt = Stand(spieler=0, spitze=0, seit=jetzt, starter=wer)

        if messbar:
            if alt.spieler == 0 and zahl > 0:
                # Der eigentliche Beginn einer Runde. Bis hierhin lief nur ein
                # Server, ab hier spielt jemand -- das ist der Unterschied,
                # wegen dem auch die Discord-Meldung erst hier kommt.
                ereignisse.append(Ereignis(game, "spiel.spieler", "erster Spieler ist drin"))
            elif zahl > alt.spitze > 0:
                ereignisse.append(Ereignis(game, "spiel.spieler", f"{zahl} im Spiel"))
            elif zahl == 0 and alt.spieler > 0:
                ereignisse.append(Ereignis(game, "spiel.leer", "niemand mehr drin"))

        # ⚠️ `alt.seit` direkt uebernehmen, NICHT `alt.seit or jetzt`: ein
        # Zeitstempel von 0.0 ist falsy, und die Oder-Form setzte die Startzeit
        # dann bei jedem Durchgang neu. Die gemeldete Laufzeit waere immer der
        # Abstand zum vorletzten Blick gewesen, also rund eine Minute, egal wie
        # lange der Server wirklich lief. Gesetzt ist das Feld ohnehin immer:
        # ein neuer Server bekommt es oben beim Anlegen von `alt`.
        neu[game] = Stand(spieler=zahl if messbar else alt.spieler,
                          spitze=max(alt.spitze, zahl if messbar else 0),
                          seit=alt.seit, starter=alt.starter)

    for game, alt in vorher.items():
        if game in laufend:
            continue
        # Spitze und Laufzeit gehoeren in DIESE Zeile. Sie ist die einzige,
        # die jemand spaeter liest, um zu beurteilen, ob sich das Wecken
        # gelohnt hat; verteilt auf drei Zeilen muesste man sie zusammensuchen.
        teile = [f"ausgegangen nach {_dauer(max(0.0, jetzt - alt.seit))}"]
        if alt.spitze > 0:
            teile.append(f"{alt.spitze} Spieler" if alt.spitze > 1 else "1 Spieler")
        else:
            teile.append("niemand war drin")
        ereignisse.append(Ereignis(game, "spiel.aus", ", ".join(teile)))

    return ereignisse, neu
