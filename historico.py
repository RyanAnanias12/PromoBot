# guarda histórico de posts em JSON simples
# evita repostar a mesma oferta e permite consultar o que já foi postado

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

HISTORICO_FILE = Path("historico.json")
log = logging.getLogger(__name__)


def _carregar() -> list:
    if HISTORICO_FILE.exists():
        return json.loads(HISTORICO_FILE.read_text())
    return []


def _salvar(data: list):
    HISTORICO_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def registrar(oferta: dict):
    data = _carregar()
    data.insert(0, {
        "id":        oferta.get("id", ""),
        "titulo":    oferta.get("titulo", ""),
        "preco_de":  oferta.get("preco_de", ""),
        "preco_por": oferta.get("preco_por", ""),
        "cupom":     oferta.get("cupom", ""),
        "url":       oferta.get("url", ""),
        "postado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    # mantém só os últimos 200 posts
    _salvar(data[:200])
    log.info("Registrado no histórico: %s", oferta.get("titulo","")[:50])


def ja_postou(url: str, horas: int = 24) -> bool:
    import hashlib
    key = hashlib.md5(url.encode()).hexdigest()[:10]
    data = _carregar()
    for item in data:
        item_key = hashlib.md5(item.get("url","").encode()).hexdigest()[:10]
        if item_key == key:
            try:
                postado = datetime.strptime(item["postado_em"], "%d/%m/%Y %H:%M")
                if datetime.now() - postado < timedelta(hours=horas):
                    return True
            except Exception:
                pass
    return False


def listar(limite: int = 20) -> list:
    return _carregar()[:limite]
