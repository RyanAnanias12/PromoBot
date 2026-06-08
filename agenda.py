# agendador simples via arquivo agenda.txt
# formato de cada linha:
#   HH:MM | LINK | CUPOM | PRECO_DE/PRECO_POR | descrição opcional
#
# exemplo agenda.txt:
#   12:00 | https://meli.la/xxx | CUPOMXYZ | 129/94,90 | Kit Cuecas Boxer Lupo
#   18:00 | https://meli.la/yyy | | 58,90 | Garrafa Térmica 1L
#   21:00 | https://meli.la/zzz | MLPRACASA | 429/284

import logging
from pathlib import Path
from datetime import datetime

AGENDA_FILE = Path("agenda.txt")
log = logging.getLogger(__name__)


def ler_agenda() -> list[dict]:
    if not AGENDA_FILE.exists():
        return []

    ofertas = []
    for linha in AGENDA_FILE.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue

        partes = [p.strip() for p in linha.split("|")]
        if len(partes) < 2:
            continue

        horario = partes[0]
        url     = partes[1] if len(partes) > 1 else ""
        cupom   = partes[2] if len(partes) > 2 else ""
        preco   = partes[3] if len(partes) > 3 else ""
        desc    = partes[4] if len(partes) > 4 else ""

        preco_de  = ""
        preco_por = ""
        if "/" in preco:
            ps        = preco.split("/")
            preco_de  = ps[0].strip()
            preco_por = ps[1].strip()
        else:
            preco_por = preco.strip()

        ofertas.append({
            "horario":  horario,
            "url":      url,
            "cupom":    cupom,
            "preco_de": preco_de,
            "preco_por": preco_por,
            "descricao": desc,
        })

    return ofertas


def ofertas_do_momento() -> list[dict]:
    agora   = datetime.now().strftime("%H:%M")
    agenda  = ler_agenda()
    return [o for o in agenda if o["horario"] == agora]


def criar_agenda_exemplo():
    if not AGENDA_FILE.exists():
        AGENDA_FILE.write_text(
            "# Agenda de posts — edite esse arquivo todo dia de manhã\n"
            "# Formato: HH:MM | LINK | CUPOM | PRECO_DE/PRECO_POR | descrição\n"
            "# Cupom e descrição são opcionais — deixe vazio mas mantenha o |\n\n"
            "# 12:00 | https://meli.la/xxx | CUPOMXYZ | 129/94,90 | Kit Cuecas Boxer Lupo\n"
            "# 18:00 | https://meli.la/yyy | | 58,90 | Garrafa Térmica 1L\n"
            "# 21:00 | https://meli.la/zzz | MLPRACASA | 429/284 |\n",
            encoding="utf-8"
        )
        log.info("agenda.txt criado com exemplos.")
