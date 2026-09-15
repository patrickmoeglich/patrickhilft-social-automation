"""Tests fuer das Tool-Radar-Gedaechtnis und den Telegram-Versand.

Aufruf aus dem Repo-Wurzelverzeichnis:
    python -m pytest scripts/test_tool_radar.py -v
"""
import json
import re
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tool_radar as tr


class FakeBot:
    """Zeichnet Aufrufe auf, statt Telegram zu kontaktieren."""

    def __init__(self):
        self.aufrufe = []

    def send_message(self, text, reply_markup=None, parse_mode="HTML"):
        self.aufrufe.append({"text": text, "parse_mode": parse_mode})
        return 100 + len(self.aufrufe)


@pytest.fixture
def leeres_gedaechtnis():
    return {"version": 1, "letzter_lauf": None, "eintraege": []}


# --- Schluessel -------------------------------------------------------------

def test_schluessel_ignoriert_grossschreibung_und_leerzeichen():
    # Arrange / Act
    a = tr.schluessel("  Sevdesk-MCP ", "GitHub")
    b = tr.schluessel("sevdesk-mcp", "github")

    # Assert
    assert a == b


def test_schluessel_trennt_gleichen_namen_aus_verschiedenen_quellen():
    assert tr.schluessel("radar", "GitHub") != tr.schluessel("radar", "Smithery")


# --- Laden und Speichern ----------------------------------------------------

def test_laden_gibt_leeres_geruest_wenn_datei_fehlt(tmp_path):
    # Arrange
    pfad = tmp_path / "gibt-es-nicht.json"

    # Act
    daten = tr.laden(pfad)

    # Assert
    assert daten["eintraege"] == []
    assert daten["letzter_lauf"] is None


def test_speichern_und_laden_erhaelt_umlaute(tmp_path):
    # Arrange
    pfad = tmp_path / "gesehen.json"
    daten = tr.merke({"eintraege": []}, "Pflege-Tool", "GitHub", notiz="Für Tagespflege")

    # Act
    tr.speichern(daten, pfad)
    wieder = tr.laden(pfad)

    # Assert
    assert wieder["eintraege"][0]["notiz"] == "Für Tagespflege"
    assert wieder["letzter_lauf"] == tr.heute()
    assert "\\u" not in pfad.read_text(encoding="utf-8")


def test_laden_ergaenzt_fehlende_felder_in_altem_schema(tmp_path):
    # Arrange - Datei aus einer aelteren Version ohne "letzter_lauf"
    pfad = tmp_path / "gesehen.json"
    pfad.write_text(json.dumps({"eintraege": []}), encoding="utf-8")

    # Act
    daten = tr.laden(pfad)

    # Assert
    assert daten["version"] == tr.SCHEMA_VERSION
    assert daten["letzter_lauf"] is None


# --- Dedupe-Logik -----------------------------------------------------------

def test_pruefe_meldet_unbekanntes_tool_als_neu(leeres_gedaechtnis):
    assert tr.pruefe(leeres_gedaechtnis, "neues-tool", "MCP-Registry") == tr.NEU


def test_pruefe_meldet_gemeldetes_tool_ohne_neuen_stand_als_bekannt(leeres_gedaechtnis):
    # Arrange
    daten = tr.merke(leeres_gedaechtnis, "alt-tool", "GitHub", stand="2026-07-14")

    # Act / Assert
    assert tr.pruefe(daten, "alt-tool", "GitHub", stand="2026-07-14") == tr.BEKANNT


def test_pruefe_meldet_neueren_release_als_update(leeres_gedaechtnis):
    # Arrange
    daten = tr.merke(leeres_gedaechtnis, "alt-tool", "GitHub", stand="2026-07-14")

    # Act / Assert
    assert tr.pruefe(daten, "alt-tool", "GitHub", stand="2026-08-20") == tr.UPDATE


def test_pruefe_ignoriert_aelteren_stand_als_gespeichert(leeres_gedaechtnis):
    # Ein zurueckdatierter Stand darf keine Neumeldung ausloesen.
    daten = tr.merke(leeres_gedaechtnis, "alt-tool", "GitHub", stand="2026-07-14")
    assert tr.pruefe(daten, "alt-tool", "GitHub", stand="2026-01-01") == tr.BEKANNT


def test_pruefe_ohne_stand_bleibt_bekannt(leeres_gedaechtnis):
    # Quelle liefert kein Datum -> keine kuenstliche Neumeldung.
    daten = tr.merke(leeres_gedaechtnis, "alt-tool", "GitHub", stand="2026-07-14")
    assert tr.pruefe(daten, "alt-tool", "GitHub", stand=None) == tr.BEKANNT


def test_pruefe_bewertet_zu_schwaches_tool_bei_neuem_stand_erneut(leeres_gedaechtnis):
    # Arrange - war unter der Meldeschwelle, hat jetzt ein neues Release
    daten = tr.merke(
        leeres_gedaechtnis, "schwach", "Smithery",
        stand="2026-02-01", bewertung=3, status=tr.STATUS_ZU_SCHWACH,
    )

    # Act / Assert - NEU, nicht UPDATE: es wurde nie gemeldet
    assert tr.pruefe(daten, "schwach", "Smithery", stand="2026-08-01") == tr.NEU


def test_pruefe_meldet_dauergesperrtes_tool_auch_bei_neuem_release_nicht(leeres_gedaechtnis):
    # Arrange - bewusst und endgueltig abgelehnt (z. B. elster-mcp-server)
    daten = tr.merke(
        leeres_gedaechtnis, "elster-mcp-server", "GitHub",
        stand="2026-07-13", status=tr.STATUS_AUSGESCHLOSSEN, dauersperre=True,
    )

    # Act / Assert - neues Release aendert nichts, die Sperre haelt
    assert tr.pruefe(daten, "elster-mcp-server", "GitHub", stand="2027-01-01") == tr.BEKANNT


def test_pruefe_ohne_dauersperre_bewertet_ausgeschlossenes_tool_neu(leeres_gedaechtnis):
    # Gegenprobe: eine Ausschlussentscheidung ohne Sperre bleibt revidierbar,
    # etwa wenn ein aufgegebenes Repo wieder gepflegt wird.
    daten = tr.merke(
        leeres_gedaechtnis, "altes-repo", "GitHub",
        stand="2025-12-19", status=tr.STATUS_AUSGESCHLOSSEN,
    )
    assert tr.pruefe(daten, "altes-repo", "GitHub", stand="2026-08-01") == tr.NEU


def test_merke_ueberschreibt_statt_zu_duplizieren(leeres_gedaechtnis):
    # Arrange
    daten = tr.merke(leeres_gedaechtnis, "tool", "GitHub", bewertung=5)

    # Act
    daten = tr.merke(daten, "TOOL", "github", bewertung=8)

    # Assert
    assert len(daten["eintraege"]) == 1
    assert daten["eintraege"][0]["bewertung"] == 8


# --- Nachrichten-Teilung ----------------------------------------------------

def test_teile_laesst_kurzen_text_ungeteilt():
    assert tr.teile("Diese Woche nichts.") == ["Diese Woche nichts."]


def test_teile_gibt_leere_liste_bei_leerem_text():
    assert tr.teile("   \n  ") == []


def test_teile_trennt_bevorzugt_am_absatz():
    # Arrange - zwei Absaetze, zusammen ueber der Grenze
    absatz_a = "A" * 60
    absatz_b = "B" * 60

    # Act
    stuecke = tr.teile(f"{absatz_a}\n\n{absatz_b}", grenze=100)

    # Assert - sauber getrennt, kein Buchstabe vermischt
    assert stuecke == [absatz_a, absatz_b]


def test_teile_schneidet_ueberlangen_absatz_hart():
    # Arrange - ein einzelner Absatz ohne jede Umbruchstelle
    text = "X" * 250

    # Act
    stuecke = tr.teile(text, grenze=100)

    # Assert
    assert [len(s) for s in stuecke] == [100, 100, 50]
    assert "".join(stuecke) == text


def test_teile_haelt_jedes_stueck_unter_der_grenze():
    # Arrange - realistischer Report mit vielen Absaetzen
    text = "\n\n".join(f"Treffer {i}: " + "Text " * 40 for i in range(30))

    # Act
    stuecke = tr.teile(text, grenze=tr.TELEGRAM_MAX_ZEICHEN)

    # Assert
    assert len(stuecke) > 1
    assert all(len(s) <= tr.TELEGRAM_MAX_ZEICHEN for s in stuecke)


# --- Skill-Synchronitaet ----------------------------------------------------

SKILL_IM_REPO = Path(__file__).resolve().parent.parent / "skills" / "tool-radar" / "SKILL.md"
SKILL_AKTIV = Path.home() / ".claude" / "skills" / "tool-radar" / "SKILL.md"


def test_skill_liegt_versioniert_im_repo():
    # Die versionierte Fassung ist die Quelle der Wahrheit - ohne sie waere die
    # Filterlogik bei einem Rechnerwechsel verloren.
    assert SKILL_IM_REPO.exists(), f"Fehlt: {SKILL_IM_REPO}"


def test_skill_frontmatter_ist_intakt():
    # Arrange
    zeilen = SKILL_IM_REPO.read_text(encoding="utf-8").splitlines()

    # Assert - Claude Code laedt den Skill nur bei sauberem Frontmatter
    assert zeilen[0] == "---"
    assert zeilen[1].startswith("name: ")
    assert zeilen[2].startswith("description: ")
    assert zeilen[3] == "---"


def test_skill_im_repo_und_im_home_sind_synchron():
    # Kopie statt Symlink, weil OneDrive Links beim Sync zerlegt. Dieser Test
    # ist der Ersatz fuer die fehlende Verlinkung: er schlaegt an, sobald eine
    # der beiden Fassungen ohne die andere geaendert wird.
    if not SKILL_AKTIV.exists():
        pytest.skip("Keine aktive Skill-Installation unter ~/.claude (anderer Rechner)")

    repo = SKILL_IM_REPO.read_text(encoding="utf-8")
    aktiv = SKILL_AKTIV.read_text(encoding="utf-8")
    assert repo == aktiv, (
        "Skill-Fassungen sind auseinandergelaufen. Abgleichen mit:\n"
        f"  copy /Y \"{SKILL_IM_REPO}\" \"{SKILL_AKTIV}\""
    )


# --- Domain-Freigaben -------------------------------------------------------

WRAPPER = Path(__file__).resolve().parent / "tool_radar_montagslauf.cmd"


def _domains_aus_skill() -> set:
    """Liest den maschinenlesbaren Block zwischen den domains-Markern."""
    text = SKILL_IM_REPO.read_text(encoding="utf-8")
    block = re.search(r"<!--\s*domains:start\s*-->(.*?)<!--\s*domains:end\s*-->", text, re.S)
    assert block, "Domain-Block in SKILL.md fehlt oder Marker sind beschaedigt"
    return {z.strip() for z in block.group(1).splitlines() if z.strip()}


def _domains_aus_wrapper() -> set:
    text = WRAPPER.read_text(encoding="utf-8")
    return set(re.findall(r"WebFetch\(domain:([^)]+)\)", text))


def test_domains_in_skill_und_wrapper_sind_synchron():
    # Der Montagslauf ist headless: eine nicht freigegebene Domain wird still
    # abgelehnt und erscheint im Report als "nicht erreichbar". Genau so sind am
    # 21.08.2026 vier von sechs Quellen ausgefallen. Dieser Test ist die
    # Absicherung dagegen, dass eine neue Quelle im SKILL.md landet, die
    # Freigabe im Wrapper aber vergessen wird.
    im_skill = _domains_aus_skill()
    im_wrapper = _domains_aus_wrapper()

    fehlt_im_wrapper = im_skill - im_wrapper
    ueberzaehlig = im_wrapper - im_skill

    assert not fehlt_im_wrapper, (
        f"Domains stehen in SKILL.md, aber nicht im Wrapper: {sorted(fehlt_im_wrapper)}. "
        f"In {WRAPPER.name} als WebFetch(domain:...) ergaenzen."
    )
    assert not ueberzaehlig, (
        f"Domains stehen im Wrapper, aber nicht in SKILL.md: {sorted(ueberzaehlig)}. "
        "Entweder in den domains-Block aufnehmen oder die Freigabe entfernen."
    )


def test_wrapper_uebergibt_das_headless_argument():
    # Ohne das Argument fragt der Lauf nach Freigabe und endet ergebnislos.
    text = WRAPPER.read_text(encoding="utf-8")
    assert '/tool-radar headless' in text


# --- .env nachladen ---------------------------------------------------------

def test_lade_env_traegt_fehlende_werte_nach(tmp_path, monkeypatch):
    # Arrange
    pfad = tmp_path / ".env"
    pfad.write_text('TR_TOKEN="abc123"\n# Kommentar\n\nTR_CHAT=42\n', encoding="utf-8")
    monkeypatch.delenv("TR_TOKEN", raising=False)
    monkeypatch.delenv("TR_CHAT", raising=False)

    # Act
    anzahl = tr.lade_env(pfad)

    # Assert - Anfuehrungszeichen entfernt, Kommentar und Leerzeile ignoriert
    assert anzahl == 2
    assert os.environ["TR_TOKEN"] == "abc123"
    assert os.environ["TR_CHAT"] == "42"


def test_lade_env_ueberschreibt_gesetzte_variable_nicht(tmp_path, monkeypatch):
    # Arrange - echte Umgebungsvariable muss Vorrang vor der Datei haben
    pfad = tmp_path / ".env"
    pfad.write_text("TR_TOKEN=aus_datei\n", encoding="utf-8")
    monkeypatch.setenv("TR_TOKEN", "aus_umgebung")

    # Act
    anzahl = tr.lade_env(pfad)

    # Assert
    assert anzahl == 0
    assert os.environ["TR_TOKEN"] == "aus_umgebung"


def test_lade_env_ohne_datei_ist_kein_fehler(tmp_path):
    assert tr.lade_env(tmp_path / "gibt-es-nicht") == 0


def test_lade_env_ignoriert_zeilen_ohne_gleichheitszeichen(tmp_path, monkeypatch):
    # Arrange
    pfad = tmp_path / ".env"
    pfad.write_text("nur_text_ohne_wert\nTR_OK=ja\n", encoding="utf-8")
    monkeypatch.delenv("TR_OK", raising=False)

    # Act / Assert
    assert tr.lade_env(pfad) == 1


# --- Zugangsdaten-Waechter --------------------------------------------------

BEISPIEL_TOKEN = "123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
BEISPIEL_CHAT = "123456789"
ECHTER_TOKEN = "8012345678:AAF9-dummy_Wert_nur_fuer_Tests_xyz12"


@pytest.fixture
def beispieldatei(tmp_path):
    """Synthetische .env.example, damit die Tests nicht vom Repo-Stand abhaengen."""
    pfad = tmp_path / ".env.example"
    pfad.write_text(
        f"# Beispielwerte\nTELEGRAM_BOT_TOKEN={BEISPIEL_TOKEN}\n"
        f"TELEGRAM_CHAT_ID={BEISPIEL_CHAT}\n",
        encoding="utf-8",
    )
    return pfad


def _setze(monkeypatch, token, chat_id):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", chat_id)


def test_zugangsdaten_fehlt_wird_als_fehlend_gemeldet(monkeypatch, beispieldatei):
    # Arrange
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    # Act
    problem = tr.pruefe_zugangsdaten(beispieldatei)

    # Assert
    assert problem is not None
    assert "fehlen" in problem and "TELEGRAM_BOT_TOKEN" in problem


def test_zugangsdaten_beispielwert_wird_als_beispielwert_gemeldet(monkeypatch, beispieldatei):
    # Arrange
    _setze(monkeypatch, BEISPIEL_TOKEN, BEISPIEL_CHAT)

    # Act
    problem = tr.pruefe_zugangsdaten(beispieldatei)

    # Assert - klar als Beispielwert benannt, nicht als Formatfehler
    assert problem is not None
    assert "Beispielwert" in problem
    assert "Format" not in problem


def test_zugangsdaten_ohne_doppelpunkt_nennt_den_strukturfehler(monkeypatch, beispieldatei):
    # Arrange
    _setze(monkeypatch, "abcdefghijklmnopqrstuvwxyz", "42")

    # Act
    problem = tr.pruefe_zugangsdaten(beispieldatei)

    # Assert
    assert problem is not None
    assert "kein Doppelpunkt" in problem


def test_zugangsdaten_nichtnumerische_bot_id_nennt_den_strukturfehler(monkeypatch, beispieldatei):
    # Arrange
    _setze(monkeypatch, "meinbot:AAF9dummyWertNurFuerTestsxyz12345", "42")

    # Act
    problem = tr.pruefe_zugangsdaten(beispieldatei)

    # Assert
    assert problem is not None
    assert "nicht rein numerisch" in problem


def test_zugangsdaten_zu_kurzes_geheimnis_nennt_die_laenge(monkeypatch, beispieldatei):
    # Arrange
    _setze(monkeypatch, "123456789:zukurz", "42")

    # Act
    problem = tr.pruefe_zugangsdaten(beispieldatei)

    # Assert
    assert problem is not None
    assert "6 Zeichen lang" in problem


def test_zugangsdaten_geben_den_wert_niemals_aus(monkeypatch, beispieldatei):
    # Arrange - die Meldung landet im Log, dort darf kein Token stehen
    geheim = "meinbot:AAF9SUPERGEHEIMER_WERT_1234567890"
    _setze(monkeypatch, geheim, "42")

    # Act
    problem = tr.pruefe_zugangsdaten(beispieldatei)

    # Assert
    assert problem is not None
    assert geheim not in problem
    assert "SUPERGEHEIMER" not in problem


def test_zugangsdaten_token_mit_zweitem_doppelpunkt_ist_gueltig(monkeypatch, beispieldatei):
    # Regression: die erste Fassung verlangte exakt 35 Zeichen ohne Doppelpunkt
    # und haette diesen echten Token faelschlich als Platzhalter abgewiesen.
    _setze(monkeypatch, "8012345678:AAF9-dummy:mit:doppelpunkten_xyz12", "42")

    assert tr.pruefe_zugangsdaten(beispieldatei) is None


def test_zugangsdaten_negative_chat_id_ist_gueltig(monkeypatch, beispieldatei):
    # Gruppen-Chats haben negative IDs.
    _setze(monkeypatch, ECHTER_TOKEN, "-1001234567890")

    assert tr.pruefe_zugangsdaten(beispieldatei) is None


def test_zugangsdaten_nichtnumerische_chat_id_wird_gemeldet(monkeypatch, beispieldatei):
    # Arrange
    _setze(monkeypatch, ECHTER_TOKEN, "meinchat")

    # Act
    problem = tr.pruefe_zugangsdaten(beispieldatei)

    # Assert
    assert problem is not None and "TELEGRAM_CHAT_ID" in problem


def test_zugangsdaten_laesst_gueltige_werte_durch(monkeypatch, beispieldatei):
    _setze(monkeypatch, ECHTER_TOKEN, "987654321")

    assert tr.pruefe_zugangsdaten(beispieldatei) is None


def test_sende_bricht_mit_klarer_meldung_ab_statt_mit_stacktrace(monkeypatch):
    # Arrange - kein bot uebergeben, also echter Pfad mit Zugangsdatenpruefung
    monkeypatch.setattr(tr, "lade_env", lambda *a, **k: 0)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    # Act / Assert
    with pytest.raises(RuntimeError, match="Telegram-Versand nicht moeglich"):
        tr.sende("Testreport")


# --- Versand ----------------------------------------------------------------

def test_sende_schickt_reinen_text_ohne_parse_mode():
    # Arrange - URL mit "&" wuerde als HTML von Telegram abgelehnt
    bot = FakeBot()

    # Act
    tr.sende("Treffer: https://example.invalid/x?a=1&b=2", bot=bot)

    # Assert
    assert bot.aufrufe[0]["parse_mode"] is None


def test_sende_nummeriert_mehrteilige_reports():
    # Arrange
    bot = FakeBot()
    text = "\n\n".join("Absatz " + "y" * 200 for _ in range(40))

    # Act
    ids = tr.sende(text, bot=bot)

    # Assert
    assert len(ids) == len(bot.aufrufe) > 1
    assert bot.aufrufe[0]["text"].startswith(f"(1/{len(ids)})\n")


def test_sende_haengt_bei_einteiligem_report_keinen_zaehler_an():
    # Arrange
    bot = FakeBot()

    # Act
    tr.sende("Diese Woche nichts.", bot=bot)

    # Assert
    assert bot.aufrufe[0]["text"] == "Diese Woche nichts."
