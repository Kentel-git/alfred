"""Client minimo per obs-websocket v5 (OBS Studio ≥ 28)."""

import base64
import hashlib
import itertools
import json
import os

import websockets

_contatore = itertools.count()


class ObsNonRaggiungibile(Exception):
    pass


async def _richieste(config_obs: dict, richieste: list[tuple[str, dict | None]]) -> list[dict]:
    """Si collega, si identifica, esegue le richieste in ordine e chiude."""
    url = f"ws://{config_obs.get('host', '127.0.0.1')}:{config_obs.get('porta', 4455)}"
    try:
        ws = await websockets.connect(url, open_timeout=3)
    except (OSError, TimeoutError) as errore:
        raise ObsNonRaggiungibile(str(errore)) from errore

    async with ws:
        ciao = json.loads(await ws.recv())["d"]
        identificazione = {"rpcVersion": 1, "eventSubscriptions": 0}
        if "authentication" in ciao:
            password = os.environ.get("ALFRED_OBS_PASSWORD", "")
            sfida, sale = ciao["authentication"]["challenge"], ciao["authentication"]["salt"]
            segreto = base64.b64encode(hashlib.sha256((password + sale).encode()).digest()).decode()
            identificazione["authentication"] = base64.b64encode(
                hashlib.sha256((segreto + sfida).encode()).digest()
            ).decode()
        await ws.send(json.dumps({"op": 1, "d": identificazione}))
        risposta = json.loads(await ws.recv())
        if risposta["op"] != 2:
            raise ObsNonRaggiungibile("identificazione rifiutata (password in ALFRED_OBS_PASSWORD?)")

        risultati = []
        for tipo, dati in richieste:
            rid = f"alfred-{next(_contatore)}"
            await ws.send(json.dumps({"op": 6, "d": {"requestType": tipo, "requestId": rid, "requestData": dati or {}}}))
            while True:
                m = json.loads(await ws.recv())
                if m["op"] == 7 and m["d"]["requestId"] == rid:
                    risultati.append(m["d"].get("responseData") or {})
                    break
        return risultati


async def stato(config_obs: dict) -> dict:
    try:
        diretta, registrazione, scene, versione = await _richieste(
            config_obs,
            [("GetStreamStatus", None), ("GetRecordStatus", None), ("GetSceneList", None), ("GetVersion", None)],
        )
    except ObsNonRaggiungibile as errore:
        return {"aperto": False, "motivo": str(errore)}
    return {
        "aperto": True,
        "versione_obs": versione.get("obsVersion"),
        "diretta": {"attiva": diretta.get("outputActive", False), "durata": diretta.get("outputTimecode")},
        "registrazione": {
            "attiva": registrazione.get("outputActive", False),
            "in_pausa": registrazione.get("outputPaused", False),
            "durata": registrazione.get("outputTimecode"),
        },
        "scena_attuale": scene.get("currentProgramSceneName"),
        "scene": [s["sceneName"] for s in reversed(scene.get("scenes", []))],
    }
