"""Prueft fuer jede konfigurierte Plattform, ob die hinterlegten Zugangsdaten
gueltig sind - OHNE zu posten. Nuetzlich bei der Ersteinrichtung und zum Debuggen
abgelaufener Tokens (z.B. LinkedIn nach ~60 Tagen).

Prueft nur Plattformen, deren Env-Variablen gesetzt sind; ueberspringt den Rest.

Verwendung:
    python check_setup.py
"""
import os
import sys

from publishers import meta, linkedin, twitter, tiktok

CHECKS = [
    ("Meta (Instagram/Facebook)", "META_PAGE_ACCESS_TOKEN", meta.whoami),
    ("LinkedIn", "LINKEDIN_ACCESS_TOKEN", linkedin.whoami),
    ("X (Twitter)", "X_API_KEY", twitter.whoami),
    ("TikTok", "TIKTOK_ACCESS_TOKEN", tiktok.whoami),
]


def main() -> int:
    any_checked = False
    any_failed = False
    for label, env_var, whoami in CHECKS:
        if not os.environ.get(env_var):
            print(f"⏭  {label}: uebersprungen ({env_var} nicht gesetzt)")
            continue
        any_checked = True
        try:
            result = whoami()
            print(f"✅ {label}: OK ({result})")
        except Exception as exc:
            any_failed = True
            print(f"🚨 {label}: FEHLER - {exc}")

    if not any_checked:
        print("\nKeine Plattform-Credentials gesetzt - nichts zu pruefen.")
        return 0
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
