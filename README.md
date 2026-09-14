# Tady Vary — kalendář s časy promítání

Festivalový kalendář cyklu "Tady Vary" obsahuje jen data promítání, ne
konkrétní časy. Ty postupně zveřejňuje program kina35.ifp.cz. Tento repozitář
jednou týdně (a na vyžádání) stáhne oba zdroje, dohledá u nadcházejících
promítání jejich konkrétní čas a vygeneruje obohacený `.ics` soubor.

## Odběr kalendáře

Přidej si do kalendářové aplikace tuto adresu (po zapnutí GitHub Pages):

```
webcal://wwwenca.github.io/tadyvary-kalendar/tadyvary.ics
```

## Ruční spuštění aktualizace

V záložce **Actions** na GitHubu spusť workflow "Update Tady Vary calendar"
tlačítkem "Run workflow".

## Lokální spuštění

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/update_calendar.py
```

Výstup se zapíše do `docs/tadyvary.ics`.
