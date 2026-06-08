# autenticação com o ML via OAuth
# gera e renova o token automaticamente
# o bot usa esse token pra buscar nome, foto e preço de qualquer produto

import json
import logging
import os
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ML_CLIENT_ID     = os.getenv("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET")
TOKEN_FILE       = Path("ml_token.json")

log = logging.getLogger(__name__)
_cache = {"token": None, "expires": datetime.min}


def _salvar_token(data: dict):
    TOKEN_FILE.write_text(json.dumps(data))


def _carregar_token() -> dict:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return {}


def get_token() -> str | None:
    # retorna do cache se ainda válido
    if _cache["token"] and datetime.now() < _cache["expires"]:
        return _cache["token"]

    saved = _carregar_token()

    # tenta renovar via refresh_token se tiver
    if saved.get("refresh_token"):
        try:
            r = requests.post(
                "https://api.mercadolibre.com/oauth/token",
                data={
                    "grant_type":    "refresh_token",
                    "client_id":     ML_CLIENT_ID,
                    "client_secret": ML_CLIENT_SECRET,
                    "refresh_token": saved["refresh_token"],
                },
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                _salvar_token(data)
                _cache["token"]   = data["access_token"]
                _cache["expires"] = datetime.now() + timedelta(seconds=data.get("expires_in", 21600) - 60)
                log.info("Token ML renovado via refresh.")
                return _cache["token"]
        except Exception as e:
            log.warning("Falha ao renovar token: %s", e)

    # fallback: client_credentials (acesso básico)
    try:
        r = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            data={
                "grant_type":    "client_credentials",
                "client_id":     ML_CLIENT_ID,
                "client_secret": ML_CLIENT_SECRET,
            },
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            _salvar_token(data)
            _cache["token"]   = data["access_token"]
            _cache["expires"] = datetime.now() + timedelta(seconds=data.get("expires_in", 21600) - 60)
            log.info("Token ML via client_credentials.")
            return _cache["token"]
        else:
            log.error("Erro token ML: %d %s", r.status_code, r.text[:100])
    except Exception as e:
        log.error("Erro token ML: %s", e)

    return None


def buscar_produto_api(mlb_id: str) -> dict:
    token = get_token()
    if not token:
        return {}

    try:
        r = requests.get(
            f"https://api.mercadolibre.com/items/{mlb_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code == 200:
            data  = r.json()
            preco = data.get("price", 0)
            thumb = ""
            pics  = data.get("pictures", [])
            if pics:
                thumb = pics[0].get("url", "").replace("http://", "https://")
                import re
                thumb = re.sub(r"-[A-Z]\.jpg", "-O.jpg", thumb)
            return {
                "titulo": data.get("title", ""),
                "preco":  preco,
                "imagem": thumb,
                "ok":     True,
            }
    except Exception as e:
        log.warning("Busca API ML falhou: %s", e)

    return {"ok": False}
