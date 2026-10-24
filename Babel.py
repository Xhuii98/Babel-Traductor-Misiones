import os
import re
import base64
import sys
import json
import time
import tempfile
import queue
import random
import threading
import shutil
import hashlib
import subprocess
import zipfile
import bisect
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    import requests
    from deep_translator import GoogleTranslator
except ImportError as e:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Error de Librería", f"El programa detectó este error:\n\n{e}\n\nEscribe en tu consola (cmd):\npython -m pip install deep-translator")
    sys.exit()

try:
    import customtkinter as ctk
except ImportError as e:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Falta una librería", f"{e}\n\nEscribe en tu consola (cmd):\npython -m pip install customtkinter")
    sys.exit()

VERSION = "1.6.1"
NOMBRE_APP = "Babel"
RUTA_SALIDA_FIJA = os.path.join(os.path.expanduser("~"), "Documents", NOMBRE_APP)
_RUTA_ANTIGUA = os.path.join(os.path.expanduser("~"), "Documents", "FTB_Translator")
if not os.path.exists(RUTA_SALIDA_FIJA) and os.path.isdir(_RUTA_ANTIGUA):
    try:
        os.rename(_RUTA_ANTIGUA, RUTA_SALIDA_FIJA)
    except OSError:
        RUTA_SALIDA_FIJA = _RUTA_ANTIGUA
os.makedirs(RUTA_SALIDA_FIJA, exist_ok=True)
ARCHIVO_MEMORIA = os.path.join(RUTA_SALIDA_FIJA, "memoria_traducciones.json")

IGNORAR_ARCHIVOS = {"data.snbt"}
IGNORAR_CARPETAS = {"reward_tables", "recovery"}
PODAR_INSTANCIA = {"saves", "logs", "crash-reports", "backups", "backup", ".git", "libraries", "versions",
                   "mods", "_traducido", "screenshots", "shaderpacks", "__pycache__"}
RE_REFERENCIA_CLAVE = re.compile(r'"\{([A-Za-z0-9_.\-]+)\}"')
CLAVES_OK = {"title:", "subtitle:", "text:", "description:"}
RE_REFERENCIA = re.compile(r'"\{[A-Za-z0-9_.\-]+\}"')
RE_ID = re.compile(r'^[0-9A-Fa-f]{8,}$')
RE_CLAVE_ANTES = re.compile(r'([A-Za-z0-9_]+)\s*:\s*$')
RE_CADENA = re.compile(r'([a-zA-Z0-9_]+:\s*)?"([^"\\]*(?:\\.[^"\\]*)*)"')
REGEX_PROTEGIDO = None
REGEX_JSON = None
ULTIMO_GUARDADO = [0.0]

DESCANSO_LIMITE = 30 * 60
DESCANSO_ERROR = 5 * 60
GUARDAR_CADA = 25

SECRETOS = []

_IDIOMAS = [
    ("Español (México)", "es-419", "es", "ES-419", "es-ES", "es_mx"),
    ("Español (España)", "es", "es", "ES", "es-ES", "es_es"),
    ("Español (Latinoamérica: todos los países)", "es-419", "es", "ES-419", "es-ES", "es_mx"),
    ("English", "en", "en", "EN-US", "en-GB", "en_us"),
    ("Português (Brasil)", "pt-BR", "pt", "PT-BR", "pt-BR", "pt_br"),
    ("Português (Portugal)", "pt-PT", "pt", "PT-PT", "pt-PT", "pt_pt"),
    ("Français", "fr", "fr", "FR", "fr-FR", "fr_fr"),
    ("Deutsch", "de", "de", "DE", "de-DE", "de_de"),
    ("Italiano", "it", "it", "IT", "it-IT", "it_it"),
    ("Русский", "ru", "ru", "RU", "ru-RU", "ru_ru"),
    ("Polski", "pl", "pl", "PL", "pl-PL", "pl_pl"),
    ("Nederlands", "nl", "nl", "NL", "nl-NL", "nl_nl"),
    ("Türkçe", "tr", "tr", "TR", "tr-TR", "tr_tr"),
    ("Українська", "uk", "uk", "UK", "uk-UA", "uk_ua"),
    ("Čeština", "cs", "cs", "CS", "cs-CZ", "cs_cz"),
    ("Svenska", "sv", "sv", "SV", "sv-SE", "sv_se"),
    ("Dansk", "da", "da", "DA", "da-DK", "da_dk"),
    ("Suomi", "fi", "fi", "FI", "fi-FI", "fi_fi"),
    ("Norsk", "no", "no", "NB", "nb-NO", "nb_no"),
    ("Română", "ro", "ro", "RO", "ro-RO", "ro_ro"),
    ("Magyar", "hu", "hu", "HU", "hu-HU", "hu_hu"),
    ("Ελληνικά", "el", "el", "EL", "el-GR", "el_gr"),
    ("Bahasa Indonesia", "id", "id", "ID", "id-ID", "id_id"),
    ("العربية", "ar", "ar", "AR", "ar-SA", "ar_sa"),
    ("日本語", "ja", "ja", "JA", "ja-JP", "ja_jp"),
    ("한국어", "ko", "ko", "KO", "ko-KR", "ko_kr"),
    ("中文 (简体)", "zh-CN", "zh-CN", "ZH-HANS", "zh-CN", "zh_cn"),
    ("中文 (繁體)", "zh-TW", "zh-TW", "ZH-HANT", "zh-TW", "zh_tw"),
]
IDIOMAS = {n: {"nombre": n, "id": i, "google": g, "deepl": d, "mm": m, "mc": c} for n, i, g, d, m, c in _IDIOMAS}
IDIOMAS["Español (Latinoamérica: todos los países)"]["variantes"] = ["es_ar", "es_cl", "es_uy", "es_ve"]

COLA = queue.Queue()
DETENER = threading.Event()


def log(msg):
    for secreto in SECRETOS:
        if secreto:
            msg = msg.replace(secreto, "***")
    COLA.put(("log", msg))


def progreso(valor):
    COLA.put(("prog", valor))


def aviso(tipo, titulo, msg):
    COLA.put((tipo, titulo, msg))


class TodosBloqueados(Exception):
    pass


class Detenido(Exception):
    pass


LOCK_MEM = threading.Lock()


def cargar_memoria():
    if not os.path.exists(ARCHIVO_MEMORIA):
        return {}
    try:
        with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except Exception:
        try:
            os.replace(ARCHIVO_MEMORIA, ARCHIVO_MEMORIA + ".corrupto")
        except OSError:
            pass
        return {}
    migrado = {}
    for k, v in datos.items():
        if es_respuesta_invalida(v):
            continue
        migrado[k if re.match(r"^[a-z]{2}(-[A-Za-z0-9]{2,4})?\|", k) else f"es|{k}"] = v
    return migrado


MARCAS_ERROR = ("mymemory warning", "invalid source language", "invalid target language",
                "langpair=", "rfc3066", "please select two distinct languages",
                "query length limit exceeded", "almost all languages supported",
                "no query specified", "too many requests")


def es_respuesta_invalida(v):
    if not isinstance(v, str) or not v.strip():
        return True
    bajo = v.lower()
    return any(m in bajo for m in MARCAS_ERROR)


def guardar_memoria():
    with LOCK_MEM:
        tmp = ARCHIVO_MEMORIA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(MEMORIA_GLOBAL, f, ensure_ascii=False)
        os.replace(tmp, ARCHIVO_MEMORIA)


def guardar_seguro():
    try:
        guardar_memoria()
    except Exception as e:
        log(f"⚠️ No pude guardar la memoria: {e}")


MEMORIA_GLOBAL = cargar_memoria()


GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
GOOGLE_CABECERAS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0 Safari/537.36",
    "Accept": "*/*",
}
GOOGLE_CLIENTES = ["dict-chrome-ex", "at", "gtx"]
GOOGLE_LOTE_CARACTERES = 3500
GOOGLE_INTERVALO = 1.2
_google_lock = threading.Lock()
_google_ultimo = [0.0]


def _google_peticion(texto, destino):
    with _google_lock:
        espera = GOOGLE_INTERVALO - (time.time() - _google_ultimo[0])
        if espera > 0:
            time.sleep(espera)
        _google_ultimo[0] = time.time()
    ultimo = None
    for _ in range(len(GOOGLE_CLIENTES)):
        cliente = GOOGLE_CLIENTES[0]
        r = requests.post(GOOGLE_URL, params={"client": cliente, "sl": "auto", "tl": destino, "dt": "t"},
                          data={"q": texto}, headers=GOOGLE_CABECERAS, timeout=30)
        if r.status_code == 200:
            break
        ultimo = r.status_code
        with _google_lock:
            if GOOGLE_CLIENTES[0] == cliente:
                GOOGLE_CLIENTES.append(GOOGLE_CLIENTES.pop(0))
    else:
        if ultimo == 429:
            raise RuntimeError("429 Google: TooManyRequests")
        raise RuntimeError(f"Google HTTP {ultimo}")
    datos = r.json()
    return "".join(seg[0] for seg in (datos[0] or []) if seg and isinstance(seg[0], str))


def _google_viejo(textos, destino):
    return [GoogleTranslator(source="auto", target=destino).translate(t) for t in textos]


def traducir_google_lote(textos, destino):
    salida = [None] * len(textos)
    grupo, chars = [], 0

    def enviar(idx):
        if not idx:
            return
        try:
            if len(idx) == 1:
                salida[idx[0]] = _google_peticion(textos[idx[0]], destino)
                return
            partes = _google_peticion("\n".join(textos[i] for i in idx), destino).split("\n")
            if len(partes) == len(idx):
                for i, t in zip(idx, partes):
                    salida[i] = t.strip()
                return
            for i in idx:
                salida[i] = _google_peticion(textos[i], destino)
        except (ValueError, KeyError, IndexError, TypeError):
            for i, t in zip(idx, _google_viejo([textos[i] for i in idx], destino)):
                salida[i] = t

    for i, t in enumerate(textos):
        if "\n" in t:
            enviar([i])
            continue
        if grupo and chars + len(t) > GOOGLE_LOTE_CARACTERES:
            enviar(grupo)
            grupo, chars = [], 0
        grupo.append(i)
        chars += len(t) + 1
    enviar(grupo)
    return salida


MS_URL = "https://edge.microsoft.com/translate/translatetext"
MS_CODIGOS = {"pt-PT": "pt-pt", "zh-CN": "zh-Hans", "zh-TW": "zh-Hant", "no": "nb"}
MS_LOTE_TEXTOS = 50
MS_LOTE_CARACTERES = 5000
MS_INTERVALO = 0.6
_ms_lock = threading.Lock()
_ms_ultimo = [0.0]


def codigo_microsoft(lang):
    return MS_CODIGOS.get(lang["id"]) or lang["google"].split("-")[0]


def _ms_texto(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        if isinstance(item.get("translations"), list) and item["translations"]:
            return item["translations"][0].get("text")
        return item.get("text")
    return None


def _ms_peticion(textos, destino):
    with _ms_lock:
        espera = MS_INTERVALO - (time.time() - _ms_ultimo[0])
        if espera > 0:
            time.sleep(espera)
        _ms_ultimo[0] = time.time()
    params = {"to": destino, "isEnterpriseClient": "false"}
    if destino != "en":
        params["from"] = "en"
    r = requests.post(MS_URL, params=params, json=list(textos), headers=GOOGLE_CABECERAS, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("429 Microsoft: TooManyRequests")
    if r.status_code != 200:
        raise RuntimeError(f"Microsoft HTTP {r.status_code}")
    datos = r.json()
    if not isinstance(datos, list) or len(datos) != len(textos):
        raise RuntimeError("Microsoft: respuesta inesperada")
    return [_ms_texto(x) for x in datos]


def traducir_microsoft_lote(textos, destino):
    salida, grupo, chars = [None] * len(textos), [], 0

    def enviar(idx):
        if idx:
            for i, t in zip(idx, _ms_peticion([textos[i] for i in idx], destino)):
                salida[i] = t

    for i, t in enumerate(textos):
        if grupo and (len(grupo) >= MS_LOTE_TEXTOS or chars + len(t) > MS_LOTE_CARACTERES):
            enviar(grupo)
            grupo, chars = [], 0
        grupo.append(i)
        chars += len(t)
    enviar(grupo)
    return salida


def clasificar(exc):
    nombre = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "toomanyrequests" in nombre or "429" in msg or "too many" in msg or "blocked" in msg:
        return "limite"
    if "456" in msg or "quota" in msg:
        return "cuota"
    if "auth" in nombre or "apikey" in nombre or "api key" in msg or "401" in msg or "403" in msg:
        return "auth"
    if "notsupported" in nombre:
        return "config"
    if "notfound" in nombre or "notvalid" in nombre or "http 400" in msg:
        return "texto"
    return "otro"


class Motor:
    def __init__(self, nombre, fn, pausa, max_fallos=3):
        self.nombre = nombre
        self.fn = fn
        self.pausa = pausa
        self.max_fallos = max_fallos
        self.fallos = 0
        self.bloqueado_hasta = 0
        self.desactivado = False
        self.motivo = ""

    def disponible(self):
        return not self.desactivado and time.time() >= self.bloqueado_hasta

    def registrar_fallo(self, exc):
        tipo = clasificar(exc)
        if tipo == "texto":
            return
        COLA.put(("motor", self.nombre, False))
        if tipo in ("auth", "cuota", "config"):
            self.desactivado = True
            self.motivo = {"auth": "clave rechazada", "cuota": "cuota agotada",
                           "config": f"no compatible ({type(exc).__name__})"}[tipo]
            log(f"🔑 {self.nombre}: {self.motivo}. Desactivado en esta sesión.")
        elif tipo == "limite":
            self.bloqueado_hasta = time.time() + DESCANSO_LIMITE
            log(f"⛔ {self.nombre}: límite de peticiones/bloqueo. Descanso de {DESCANSO_LIMITE // 60} min.")
        else:
            self.fallos += 1
            if self.fallos >= self.max_fallos:
                self.fallos = 0
                self.bloqueado_hasta = time.time() + DESCANSO_ERROR
                log(f"⚠️ {self.nombre}: {self.max_fallos} errores seguidos ({type(exc).__name__}). Descanso de {DESCANSO_ERROR // 60} min.")

    def estado(self):
        if self.desactivado:
            return f"{self.nombre}: desactivado ({self.motivo})"
        falta = int(self.bloqueado_hasta - time.time())
        if falta > 0:
            return f"{self.nombre}: en descanso ~{falta // 60 + 1} min más"
        return f"{self.nombre}: disponible"


DEEPL_ALTERNO = {"ES-419": "ES"}
_DEEPL_USAR_ALTERNO = set()


def _deepl_post(textos, api_key, codigo, timeout):
    host = "api-free.deepl.com" if api_key.endswith(":fx") else "api.deepl.com"
    if codigo in _DEEPL_USAR_ALTERNO:
        codigo = DEEPL_ALTERNO[codigo]
    r = requests.post(
        f"https://{host}/v2/translate",
        headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
        json={"text": list(textos), "target_lang": codigo},
        timeout=timeout)
    if r.status_code == 400 and "target_lang" in r.text.lower() and codigo in DEEPL_ALTERNO:
        _DEEPL_USAR_ALTERNO.add(codigo)
        log("⚠️ Tu cuenta de DeepL no admite español latino; uso español de España para esta traducción.")
        return _deepl_post(textos, api_key, codigo, timeout)
    if r.status_code != 200:
        raise RuntimeError(f"DeepL HTTP {r.status_code}: {r.text[:100]}")
    return [t["text"] for t in r.json()["translations"]]


def traducir_deepl(texto, api_key, codigo):
    return _deepl_post([texto], api_key, codigo, 20)[0]


def traducir_deepl_lote(textos, api_key, codigo):
    return _deepl_post(textos, api_key, codigo, 60)


def uso_deepl(api_key):
    try:
        host = "api-free.deepl.com" if api_key.endswith(":fx") else "api.deepl.com"
        r = requests.get(f"https://{host}/v2/usage",
                         headers={"Authorization": f"DeepL-Auth-Key {api_key}"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return int(d["character_count"]), int(d["character_limit"])
    except Exception:
        pass
    return None


LIBRE_POR_DEFECTO = "http://localhost:5000"
URL_LIBRE = "https://github.com/LibreTranslate/LibreTranslate"
LIBRE_EXTRA = {"pt-BR": ["pb", "pt-BR", "pt"], "pt-PT": ["pt"], "zh-CN": ["zh-Hans", "zh"],
               "zh-TW": ["zh-Hant", "zh"], "es-419": ["es"], "no": ["nb", "no"]}


def _libre_base(url):
    url = (url or LIBRE_POR_DEFECTO).strip().rstrip("/")
    if not url.startswith("http"):
        url = "http://" + url
    return url


def codigo_libre(lang, disponibles):
    candidatos = LIBRE_EXTRA.get(lang["id"], []) + LIBRE_EXTRA.get(lang["google"], [])
    candidatos += [lang["id"], lang["google"], lang["google"].split("-")[0]]
    for c in candidatos:
        if c in disponibles:
            return c
    return None


def idiomas_libre(base):
    try:
        r = requests.get(base + "/languages", timeout=5)
    except Exception as exc:
        raise ConnectionError(f"no está abierto en {base}") from exc
    if r.status_code != 200:
        raise RuntimeError(f"LibreTranslate HTTP {r.status_code}")
    return {d.get("code") for d in r.json() if isinstance(d, dict)}


def traducir_libre_lote(textos, base, codigo, fuente):
    r = requests.post(base + "/translate", json={"q": list(textos), "source": fuente, "target": codigo,
                                                 "format": "text"}, timeout=180)
    if r.status_code == 429:
        raise RuntimeError("429 LibreTranslate: demasiadas peticiones")
    if r.status_code in (400, 403) and "api" in r.text.lower() and "key" in r.text.lower():
        raise RuntimeError("401 LibreTranslate pide api key")
    if r.status_code != 200:
        raise RuntimeError(f"LibreTranslate HTTP {r.status_code}: {r.text[:100]}")
    trs = r.json().get("translatedText")
    if isinstance(trs, str):
        trs = [trs]
    if not isinstance(trs, list) or len(trs) != len(textos):
        raise RuntimeError("LibreTranslate devolvió una respuesta incompleta")
    return trs


class Traductor:
    def __init__(self, lang, api_deepl="", libre_url=""):
        self.idioma = lang["id"]
        self.lang = lang
        self.motores = []
        self.libre_base = _libre_base(libre_url)
        self.libre_codigo = None
        self.libre_fuente = "auto" if lang["id"].startswith("en") else "en"
        self.tiempos = {}
        self.avisado_lento = set()
        self.motores.append(Motor("LibreTranslate", lambda t: self._libre([t])[0], 0.0))
        if api_deepl:
            self.motores.append(Motor("DeepL", lambda t: traducir_deepl(t, api_deepl, lang["deepl"]), 0.1))
        ms = codigo_microsoft(lang)
        self.motores.append(Motor("Microsoft", lambda t: traducir_microsoft_lote([t], ms)[0], 0.0))
        self.lote_microsoft = lambda ts: traducir_microsoft_lote(ts, ms)
        self.motores.append(Motor("Google", lambda t: traducir_google_lote([t], lang["google"])[0], 0.0))
        self.lote_google = lambda ts: traducir_google_lote(ts, lang["google"])
        self.lote_deepl = (lambda ts: traducir_deepl_lote(ts, api_deepl, lang["deepl"])) if api_deepl else None

    def _libre(self, textos):
        if not self.libre_codigo:
            raise ConnectionError("LibreTranslate sin configurar")
        return traducir_libre_lote(textos, self.libre_base, self.libre_codigo, self.libre_fuente)

    def motor(self, nombre):
        return next((m for m in self.motores if m.nombre == nombre), None)

    def resumen(self):
        return "\n".join(m.estado() for m in self.motores)

    def _preparar_libre(self):
        m = self.motor("LibreTranslate")
        try:
            codigo = codigo_libre(self.lang, idiomas_libre(self.libre_base))
        except Exception as exc:
            m.desactivado, m.motivo = True, "no está abierto"
            log(f"➖ LibreTranslate (local, opcional): {exc}")
            return False
        if not codigo:
            m.desactivado, m.motivo = True, "no tiene este idioma"
            log(f"➖ LibreTranslate: no tiene instalado el idioma {self.lang['nombre']}. Descárgalo en LibreTranslate.")
            return False
        self.libre_codigo = codigo
        return True

    def probar(self):
        muestra = "Hello world" if self.idioma != "en" else "Hola mundo"
        ok = False
        for m in self.motores:
            if m.nombre == "LibreTranslate" and not self._preparar_libre():
                continue
            try:
                r = m.fn(muestra)
                if r and r.strip():
                    log(f"✅ {m.nombre}: funciona")
                    COLA.put(("motor", m.nombre, True))
                    ok = True
                else:
                    log(f"⚠️ {m.nombre}: respuesta vacía")
            except Exception as exc:
                log(f"⛔ {m.nombre}: {type(exc).__name__}: {str(exc)[:100]}")
                m.registrar_fallo(exc)
            time.sleep(0.3)
        return ok

    def traducir_lote(self, textos):
        if DETENER.is_set():
            raise Detenido()
        resultados = [(None, None)] * len(textos)
        deepl = self.motor("DeepL")
        if deepl and self.lote_deepl and deepl.disponible():
            try:
                trs = self.lote_deepl(textos)
                if len(trs) == len(textos):
                    resultados = [(t, "DeepL") if t and t.strip() else (None, None) for t in trs]
                    deepl.fallos = 0
                    time.sleep(deepl.pausa)
            except Exception as exc:
                deepl.registrar_fallo(exc)
        faltan = [i for i, r in enumerate(resultados) if r[0] is None]
        if faltan:
            self._repartir(textos, resultados, faltan)
        if DETENER.is_set():
            raise Detenido()
        if any(r[0] is None for r in resultados) and not any(m.disponible() for m in self.motores):
            raise TodosBloqueados(self.resumen())
        return resultados

    def _velocidad(self, nombre):
        total, n = self.tiempos.get(nombre, (0.0, 0))
        return total / n if n >= 3 else None

    def _es_lento(self, m, activos):
        mia = self._velocidad(m.nombre)
        if mia is None:
            return False
        for otro in activos:
            if otro is m or not otro.disponible():
                continue
            suya = self._velocidad(otro.nombre)
            if suya is not None and suya * 8 < mia:
                if m.nombre not in self.avisado_lento:
                    self.avisado_lento.add(m.nombre)
                    log(f"🐢 {m.nombre} va mucho más lento que {otro.nombre}: dejo que {otro.nombre} haga el trabajo.")
                return True
        return False

    def _repartir(self, textos, resultados, indices):
        plan = []
        fns = {"LibreTranslate": self._libre, "Microsoft": self.lote_microsoft, "Google": self.lote_google}
        for nombre, tam in (("LibreTranslate", 20), ("Microsoft", 50), ("Google", 30)):
            m = self.motor(nombre)
            if m and m.disponible():
                fn = fns[nombre]
                plan.append((m, tam, fn))
        if not plan:
            return
        activos = [m for m, _, _ in plan]
        lock = threading.Lock()
        cola = list(indices)
        probados = {i: set() for i in indices}
        ocupados = {}

        def tomar(m, tam, solo_rechazados):
            with lock:
                elegidos = [i for i in cola if m.nombre not in probados[i] and (probados[i] or not solo_rechazados)][:tam]
                for i in elegidos:
                    cola.remove(i)
                ocupados[m.nombre] = bool(elegidos)
                if elegidos:
                    return elegidos, False
                otros = any(v for k, v in ocupados.items() if k != m.nombre)
                return [], otros

        def devolver(m, idx):
            with lock:
                for i in idx:
                    probados[i].add(m.nombre)
                    cola.append(i)

        def trabajador(m, tam, fn):
            try:
                while not DETENER.is_set() and m.disponible():
                    idx, esperar = tomar(m, tam, self._es_lento(m, activos))
                    if not idx:
                        if esperar:
                            time.sleep(0.1)
                            continue
                        break
                    inicio = time.time()
                    try:
                        trs = fn([textos[i] for i in idx])
                    except Exception as exc:
                        m.registrar_fallo(exc)
                        devolver(m, idx)
                        continue
                    finally:
                        with lock:
                            ocupados[m.nombre] = False
                    total, n = self.tiempos.get(m.nombre, (0.0, 0))
                    self.tiempos[m.nombre] = (total + time.time() - inicio, n + len(idx))
                    malos = []
                    for i, tr in zip(idx, trs):
                        if tr and tr.strip():
                            resultados[i] = (tr, m.nombre)
                        else:
                            malos.append(i)
                    if malos:
                        devolver(m, malos)
                    m.fallos = 0
                    if m.pausa:
                        time.sleep(m.pausa + random.random() * 0.2)
            except Exception as exc:
                log(f"⚠️ {m.nombre}: error inesperado en el trabajo en paralelo: {type(exc).__name__}: {exc}")
            finally:
                with lock:
                    ocupados[m.nombre] = False

        hilos = [threading.Thread(target=trabajador, args=p, daemon=True) for p in plan]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()


def crear_regex_proteccion(lista_mods, json_mode=False):
    patron_base = r'([&§][0-9a-fA-Fk-oK-OrR])|({[^}]+})|(\((?:quest|item|image|http|https):[^)]+\))|(<[^>]+>)|(\[[a-zA-Z]+=[^\]]+\])'
    if not json_mode:
        patron_base += r'|((?:\\n|\ue000.)+)'
    if json_mode:
        patron_base += r'|(%(?:\d+\$)?[-+0#]*\d*(?:\.\d+)?[sdfxXeEgGcb%])|(\n)'
    if not lista_mods:
        return re.compile(patron_base, re.IGNORECASE)
    lista_mods.sort(key=len, reverse=True)
    patron_mods = "|".join([re.escape(m) for m in lista_mods])
    regex_mods = r'\b(?:' + patron_mods + r')\b'
    return re.compile(patron_base + r'|(' + regex_mods + r')', re.IGNORECASE)


def es_texto_traducible(texto):
    if not texto or len(texto) < 2:
        return False
    if " " not in texto and ":" in texto:
        return False
    if "/" in texto and " " not in texto:
        return False
    if texto.startswith("{") or texto.startswith("#"):
        return False
    if RE_ID.match(texto.strip()) or not tiene_letras(texto):
        return False
    return True


def limpiar_seguridad(texto):
    if texto is None:
        return ""
    return str(texto).replace('"', "'").replace("\n", " ").strip()


def separar_protegidos(texto, regex=None):
    regex = regex or REGEX_PROTEGIDO
    partes = re.split(regex, texto)
    resultado = []
    for p in partes:
        if p is None or p == "":
            continue
        if regex.fullmatch(p) or not p.strip():
            resultado.append((True, p))
        elif ":" in p and " " not in p and len(p) > 5 and not p.startswith("http"):
            resultado.append((True, p))
        else:
            resultado.append((False, p))
    return resultado


def reconstruir(mapa, estructura):
    final = ""
    for es_prot, cont in estructura:
        if es_prot:
            final += cont
        else:
            inicio = cont[:len(cont) - len(cont.lstrip())]
            fin = cont[len(cont.rstrip()):]
            final += inicio + limpiar_seguridad(mapa.get(cont, cont)) + fin
    return final


def tiene_letras(t):
    return bool(re.search(r"[^\W\d_]", t))


def valor_json_traducible(v):
    if not isinstance(v, str) or len(v.strip()) < 2 or not tiene_letras(v):
        return False
    if " " not in v.strip() and (":" in v or "/" in v):
        return False
    return True


def extraer_textos_json(datos):
    textos = set()
    for v in datos.values():
        if valor_json_traducible(v):
            for es_prot, seg in separar_protegidos(v, REGEX_JSON):
                if not es_prot and tiene_letras(seg):
                    textos.add(seg)
    return textos


def reconstruir_json(mapa, estructura):
    salida = []
    for es_prot, cont in estructura:
        if es_prot or not tiene_letras(cont):
            salida.append(cont)
            continue
        inicio = cont[:len(cont) - len(cont.lstrip())]
        fin = cont[len(cont.rstrip()):]
        salida.append(inicio + mapa.get(cont, cont).strip() + fin)
    return "".join(salida)


def campo_traducible(clave):
    return (not clave) or clave.strip().lower() in CLAVES_OK


def contexto_listas(contenido):
    permitidos, pila, en_cadena, escape = {}, [], False, False
    for i, c in enumerate(contenido):
        if en_cadena:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                en_cadena = False
            continue
        if c == '"':
            en_cadena = True
            permitidos[i] = bool(pila) and pila[-1]
        elif c == "[":
            m = RE_CLAVE_ANTES.search(contenido[max(0, i - 80):i])
            if m:
                pila.append((m.group(1).lower() + ":") in CLAVES_OK)
            else:
                pila.append(bool(pila) and pila[-1])
        elif c == "]" and pila:
            pila.pop()
    return permitidos


def cadena_permitida(m, contexto, modo_lang):
    if modo_lang:
        return True
    clave = m.group(1)
    if clave:
        return clave.strip().lower() in CLAVES_OK
    return contexto.get(m.start(), False)


ESTADO = {"nuevas": 0, "cache": 0, "fallidas": 0, "motores": {}}
LOTE_TEXTOS = 40
LOTE_CARACTERES = 12000


ESCAPES_SNBT = set('\\"\'')


MARCA_ESCAPE = "\ue000"


def desescapar_snbt(v):
    v = re.sub(r'(?<!\\)((?:\\\\)*)\\u([0-9a-fA-F]{4})', lambda m: m.group(1) + chr(int(m.group(2), 16)), v)
    return re.sub(r'\\(.)', lambda m: m.group(1) if m.group(1) in ESCAPES_SNBT else MARCA_ESCAPE + m.group(1), v)


def escapar_snbt(v):
    return v.replace("\\", "\\\\").replace('"', '\\"').replace(MARCA_ESCAPE, "\\")


def reconstruir_snbt(mapa, estructura):
    final = ""
    for es_prot, cont in estructura:
        if es_prot:
            final += cont
        else:
            inicio = cont[:len(cont) - len(cont.lstrip())]
            fin = cont[len(cont.rstrip()):]
            nuevo = mapa.get(cont)
            nuevo = str(nuevo).replace("\n", " ").replace("\\", "").replace(MARCA_ESCAPE, "").strip() if nuevo else cont.strip()
            final += inicio + nuevo + fin
    return escapar_snbt(final)


def validar_snbt(texto):
    pila, i, n = [], 0, len(texto)
    pares = {"}": "{", "]": "["}
    while i < n:
        c = texto[i]
        if c in "\"'":
            i += 1
            while i < n and texto[i] != c:
                if texto[i] == "\\":
                    if i + 1 >= n or texto[i + 1] not in "\\\"'ntrbfu":
                        return False
                    if texto[i + 1] == "u" and not re.fullmatch(r"[0-9a-fA-F]{4}", texto[i + 2:i + 6]):
                        return False
                    i += 1
                elif texto[i] == "\n":
                    return False
                i += 1
            if i >= n:
                return False
        elif c in "{[":
            pila.append(c)
        elif c in "}]":
            if not pila or pila.pop() != pares[c]:
                return False
        i += 1
    return not pila


def extraer_textos(contenido, modo_lang=False):
    textos = set()
    contexto = {} if modo_lang else contexto_listas(contenido)
    for m in RE_CADENA.finditer(contenido):
        if not cadena_permitida(m, contexto, modo_lang):
            continue
        valor = desescapar_snbt(m.group(2))
        if es_texto_traducible(valor):
            for es_prot, txt in separar_protegidos(valor):
                if not es_prot:
                    textos.add(txt)
    return textos


GLOSARIO_FIJO = r"(?i:mobs?|spawners?|respawns?|spawns?|crafting|stacks?|bosses|boss|xp|buffs?|debuffs?|nerfs?)"
GLOSARIO_NOMBRES = (r"Ender Dragon|Endermen|Enderman|Overworld|Netherite|Nether|Redstone|Elytra|Wither|Warden|"
                    r"Creepers?|Piglins?|Blazes?|Ghasts?|Shulkers?")
GLOSARIO_ES = {"chest": "cofre", "chests": "cofres"}
RE_GLOSARIO = re.compile(r"\b(?:" + GLOSARIO_FIJO + "|" + GLOSARIO_NOMBRES + r")\b|(?<![.!?:]\s)(?<!^)\bEnd\b")
RE_GLOSARIO_ES = re.compile(r"\b(?i:chests?)\b")
RE_FICHA = re.compile(r"QX(\d+)Z", re.IGNORECASE)


def regex_glosario(idioma):
    if idioma.startswith("es"):
        return re.compile(RE_GLOSARIO.pattern + "|" + RE_GLOSARIO_ES.pattern)
    return RE_GLOSARIO


def forma_glosario(termino, idioma):
    fija = GLOSARIO_ES.get(termino.lower()) if idioma.startswith("es") else None
    if not fija:
        return termino
    return fija[0].upper() + fija[1:] if termino[0].isupper() else fija


def enmascarar(txt, idioma):
    terminos = []

    def ficha(m):
        terminos.append(forma_glosario(m.group(0), idioma))
        return f"QX{len(terminos) - 1}Z"

    return regex_glosario(idioma).sub(ficha, txt), terminos


def desenmascarar(tr, terminos):
    if not terminos:
        return tr
    vistas = [int(n) for n in RE_FICHA.findall(tr)]
    if sorted(vistas) != list(range(len(terminos))):
        return None
    return RE_FICHA.sub(lambda m: terminos[int(m.group(1))], tr)


def cache_respeta_glosario(txt, tr, idioma):
    for m in regex_glosario(idioma).finditer(txt):
        if forma_glosario(m.group(0), idioma).lower() not in tr.lower():
            return False
    return True


def rearmar_por_piezas(txt, traductor, idioma):
    rx = regex_glosario(idioma)
    piezas, pos = [], 0
    for m in rx.finditer(txt):
        piezas.append((False, txt[pos:m.start()]))
        piezas.append((True, forma_glosario(m.group(0), idioma)))
        pos = m.end()
    piezas.append((False, txt[pos:]))
    a_traducir = [p.strip() for es_term, p in piezas if not es_term and tiene_letras(p)]
    if not a_traducir:
        return "".join(p for _, p in piezas)
    resultados = traductor.traducir_lote(a_traducir)
    tr = {orig: r for orig, (r, _) in zip(a_traducir, resultados)}
    if any(not tr.get(t) for t in a_traducir):
        return None
    salida = ""
    for es_term, p in piezas:
        if es_term or not tiene_letras(p):
            salida += p
        else:
            salida += p[:len(p) - len(p.lstrip())] + tr[p.strip()] + p[len(p.rstrip()):]
    return salida


def dividir_en_lotes(textos):
    lotes, actual, chars = [], [], 0
    for t in textos:
        if actual and (len(actual) >= LOTE_TEXTOS or chars + len(t) > LOTE_CARACTERES):
            lotes.append(actual)
            actual, chars = [], 0
        actual.append(t)
        chars += len(t)
    if actual:
        lotes.append(actual)
    return lotes


def resolver_textos(textos, traductor, idioma, nombre, indice, total):
    mapa, pendientes = {}, []
    for txt in textos:
        previa = MEMORIA_GLOBAL.get(f"{idioma}|{txt}")
        if previa and cache_respeta_glosario(txt, previa, idioma):
            mapa[txt] = previa
            ESTADO["cache"] += 1
        else:
            pendientes.append(txt)

    log(f"📄 {nombre}: {len(pendientes)} por traducir, {len(textos) - len(pendientes)} ya en memoria")
    COLA.put(("estado", f"Traduciendo {nombre}  ({indice + 1} de {total})"))
    fallidas, hechos = 0, 0
    lotes = dividir_en_lotes(pendientes)
    for n, lote in enumerate(lotes, 1):
        mascaras = [enmascarar(t, idioma) for t in lote]
        resultados = traductor.traducir_lote([m for m, _ in mascaras])
        for txt, (_, terminos), (tr, motor) in zip(lote, mascaras, resultados):
            if tr and es_respuesta_invalida(tr) and not es_respuesta_invalida(txt):
                tr = None
            if tr and terminos:
                tr = desenmascarar(tr, terminos)
                if tr is None:
                    try:
                        tr = rearmar_por_piezas(txt, traductor, idioma)
                    except TodosBloqueados:
                        raise
                    except Exception:
                        tr = None
            if tr:
                mapa[txt] = tr
                MEMORIA_GLOBAL[f"{idioma}|{txt}"] = tr
                ESTADO["nuevas"] += 1
                ESTADO["motores"][motor] = ESTADO["motores"].get(motor, 0) + 1
            else:
                fallidas += 1
                ESTADO["fallidas"] += 1
        hechos += len(lote)
        if time.time() - ULTIMO_GUARDADO[0] > 15 or n == len(lotes):
            guardar_seguro()
            ULTIMO_GUARDADO[0] = time.time()
        progreso(((indice + hechos / len(pendientes)) / total) * 100)
        if len(lotes) > 1 and (n % 10 == 0 or n == len(lotes)):
            log(f"   ... {hechos}/{len(pendientes)}")
    return mapa, fallidas


def _fin_cadena(t, i):
    q, i, n = t[i], i + 1, len(t)
    while i < n and t[i] != q:
        i += 2 if t[i] == "\\" else 1
    return i + 1


def _fin_lista(t, i):
    prof, n = 0, len(t)
    while i < n:
        c = t[i]
        if c in "\"'":
            i = _fin_cadena(t, i)
            continue
        if c in "[{":
            prof += 1
        elif c in "]}":
            prof -= 1
            if prof == 0:
                return i + 1
        i += 1
    return n


def entradas_lang(texto):
    i = texto.find("{")
    if i < 0:
        return None
    entradas, i, n = [], i + 1, len(texto)
    while i < n:
        while i < n and texto[i] in " \t\r\n,":
            i += 1
        if i >= n or texto[i] == "}":
            return entradas
        if texto[i] == '"':
            j = _fin_cadena(texto, i)
            clave = desescapar_snbt(texto[i + 1:j - 1])
        else:
            j = i
            while j < n and texto[j] not in ":\n{}[]":
                j += 1
            clave = texto[i:j].strip()
        i = j
        while i < n and texto[i] in " \t":
            i += 1
        if i >= n or texto[i] != ":" or not clave:
            return None
        i += 1
        while i < n and texto[i] in " \t\r\n":
            i += 1
        if i >= n:
            return None
        ini = i
        if texto[i] in "\"'":
            i = _fin_cadena(texto, i)
        elif texto[i] in "[{":
            i = _fin_lista(texto, i)
        else:
            while i < n and texto[i] not in ",\n}":
                i += 1
        entradas.append((clave, ini, i))
    return entradas


def _norm_valor(v):
    return re.sub(r"\s+", " ", v).strip()


_CACHE_EXISTENTES = {}


def decode_lgq1_content(content: str) -> str:
    """Reemplaza LGQ1:<base64> por el texto plano decodificado y escapado para SNBT."""
    pattern = r'LGQ1:([A-Za-z0-9+/=]+)'

    def replacer(match):
        try:
            decoded = base64.b64decode(match.group(1)).decode('utf-8')
            # Escapar para que no rompa el SNBT
            decoded = decoded.replace('\\', '\\\\').replace('"', '\\"')
            decoded = decoded.replace('\n', '\\n')
            return decoded
        except Exception:
            return match.group(0)

    return re.sub(pattern, replacer, content)


def _leer_con_lgq1(ruta):
    """Lee un archivo y decodifica LGQ1 en memoria si está presente."""
    try:
        with open(ruta, 'r', encoding='utf-8') as fh:
            contenido = fh.read()
    except Exception:
        return None
    if 'LGQ1:' not in contenido:
        return contenido
    return decode_lgq1_content(contenido)


def _familia(codigo):
    return codigo.lower().split("_")[0]


def _instalados_por_babel():
    return {os.path.normcase(os.path.abspath(p)) for p in cargar_manifiesto()}


def _archivos_idioma(raiz, extensiones, destino_mc):
    fam = _familia(destino_mc)
    elegidos = []
    try:
        nombres = sorted(os.listdir(raiz))
    except OSError:
        return elegidos
    for nombre in nombres:
        base = nombre.split(".")[0].lower()
        if base == "en_us" or _familia(base) != fam or "_" not in base:
            continue
        ruta = os.path.join(raiz, nombre)
        prioridad = 0 if base == destino_mc.lower() else 1
        if os.path.isdir(ruta):
            for r, _, archivos in os.walk(ruta):
                for f in sorted(archivos):
                    if f.lower().endswith(extensiones):
                        elegidos.append((prioridad, os.path.join(r, f)))
        elif nombre.lower().endswith(extensiones):
            elegidos.append((prioridad, ruta))
    return [r for _, r in sorted(elegidos, key=lambda x: x[0])]


def traducciones_existentes_snbt(ruta_ref, destino_mc):
    partes = os.path.abspath(ruta_ref).split(os.sep)
    if "lang" not in [p.lower() for p in partes]:
        return {}
    idx = max(i for i, p in enumerate(partes) if p.lower() == "lang")
    raiz = os.sep.join(partes[:idx + 1])
    clave_cache = (raiz, destino_mc)
    if clave_cache in _CACHE_EXISTENTES:
        return _CACHE_EXISTENTES[clave_cache]
    babel = _instalados_por_babel()
    mapa = {}
    for ruta in _archivos_idioma(raiz, (".snbt", ".snbt_merged"), destino_mc):
        normal = os.path.normcase(os.path.abspath(ruta))
        if normal in babel or (normal.endswith("_merged") and normal[:-len("_merged")] in babel):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                texto = f.read()
        except Exception:
            continue
        for clave, ini, fin in entradas_lang(texto) or []:
            mapa.setdefault(clave, texto[ini:fin])
    _CACHE_EXISTENTES[clave_cache] = mapa
    return mapa


def traducciones_existentes_json(ruta_ref, destino_mc):
    raiz = os.path.dirname(os.path.abspath(ruta_ref))
    clave_cache = (raiz, destino_mc, "json")
    if clave_cache in _CACHE_EXISTENTES:
        return _CACHE_EXISTENTES[clave_cache]
    babel = _instalados_por_babel()
    mapa = {}
    for ruta in _archivos_idioma(raiz, (".json",), destino_mc):
        if os.path.normcase(os.path.abspath(ruta)) in babel or os.path.dirname(ruta) != raiz:
            continue
        try:
            with open(ruta, "r", encoding="utf-8-sig") as f:
                datos = json.load(f)
        except Exception:
            continue
        if isinstance(datos, dict):
            for k, v in datos.items():
                mapa.setdefault(k, v)
    _CACHE_EXISTENTES[clave_cache] = mapa
    return mapa


def procesar_archivo(ruta, destino, traductor, idioma, indice=0, total=1, modo_lang=False,
                     existentes=None):
    with open(ruta, "r", encoding="utf-8") as f:
        contenido = f.read()

    entradas = entradas_lang(contenido) if modo_lang and existentes else None
    reuso = {}
    for clave, ini, fin in entradas or []:
        previo = existentes.get(clave)
        original = contenido[ini:fin]
        if (previo and previo[:1] == original[:1] and _norm_valor(previo) != _norm_valor(original)
                and tiene_letras(desescapar_snbt(previo)) and validar_snbt("{a: " + previo + "}")):
            reuso[(ini, fin)] = previo
    if reuso:
        log(f"♻️ {os.path.basename(ruta)}: reutilizo {len(reuso)} traducciones que ya traía el modpack; "
            f"traduzco solo {len(entradas) - len(reuso)} de {len(entradas)}")
        pendiente = "\n".join(contenido[ini:fin] for _, ini, fin in entradas if (ini, fin) not in reuso)
    else:
        pendiente = contenido

    mapa, fallidas = resolver_textos(extraer_textos(pendiente, modo_lang), traductor, idioma,
                                     os.path.basename(ruta), indice, total)

    contexto = {} if modo_lang else contexto_listas(contenido)

    def replacer(match):
        clave, todo = match.group(1), match.group(0)
        valor_orig = desescapar_snbt(match.group(2))
        if not cadena_permitida(match, contexto, modo_lang) or not es_texto_traducible(valor_orig):
            return todo
        nuevo = reconstruir_snbt(mapa, separar_protegidos(valor_orig))
        return f'{clave if clave else ""}"{nuevo}"'

    if reuso:
        partes_salida, previo_fin = [], 0
        for _, ini, fin in entradas:
            partes_salida.append(contenido[previo_fin:ini])
            partes_salida.append(reuso.get((ini, fin)) or RE_CADENA.sub(replacer, contenido[ini:fin]))
            previo_fin = fin
        partes_salida.append(contenido[previo_fin:])
        nuevo_contenido = "".join(partes_salida)
    else:
        nuevo_contenido = RE_CADENA.sub(replacer, contenido)
    if not validar_snbt(nuevo_contenido) and validar_snbt(contenido):
        log(f"⚠️ {os.path.basename(ruta)}: la traducción no pasó la revisión de formato; dejé este archivo en su idioma original para no romper el modpack.")
        nuevo_contenido = contenido
        fallidas = max(fallidas, 1)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        f.write(nuevo_contenido)
    return fallidas


def procesar_json(ruta, destino, traductor, idioma, indice=0, total=1, existentes=None):
    with open(ruta, "r", encoding="utf-8-sig") as f:
        datos = json.load(f)
    if not isinstance(datos, dict):
        raise ValueError("no parece un archivo de idioma (se esperaba un objeto JSON)")

    existentes = existentes or {}
    reuso = {k: existentes[k] for k, v in datos.items()
             if isinstance(v, str) and isinstance(existentes.get(k), str)
             and _norm_valor(existentes[k]) != _norm_valor(v) and tiene_letras(existentes[k])}
    if reuso:
        log(f"♻️ {os.path.basename(ruta)}: reutilizo {len(reuso)} traducciones que ya traía el modpack; "
            f"traduzco solo {len(datos) - len(reuso)} de {len(datos)}")
    pendientes = {k: v for k, v in datos.items() if k not in reuso}
    mapa, fallidas = resolver_textos(extraer_textos_json(pendientes), traductor, idioma,
                                     os.path.basename(ruta), indice, total)
    salida = {}
    for clave, valor in datos.items():
        if clave in reuso:
            salida[clave] = reuso[clave]
        elif valor_json_traducible(valor):
            salida[clave] = reconstruir_json(mapa, separar_protegidos(valor, REGEX_JSON))
        else:
            salida[clave] = valor
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    return fallidas


RE_CLAVE_TRADUCCION = re.compile(r"^[\w\-]+(\.[\w\-]+)+$")
NOMBRES_SISTEMA = {"bq": "Better Questing", "heracles": "Heracles / Odyssey Quests"}


def tipo_estructurado(ruta):
    partes = ruta.replace("\\", "/").lower().split("/")
    if not partes[-1].endswith(".json"):
        return None
    if "betterquesting" in partes[:-1] and (partes[-1] == "defaultquests.json" or "defaultquests" in partes[:-1]):
        return "bq"
    for i, p in enumerate(partes[:-2]):
        if p == "heracles" and partes[i + 1] == "quests":
            return "heracles"
    return None


def texto_estructurado(v):
    if not isinstance(v, str):
        return False
    limpio = re.sub(r"<[^>]+>", " ", v)
    return valor_json_traducible(limpio) and not RE_CLAVE_TRADUCCION.match(limpio.strip())


def _puntos_componente(padre, clave, puntos):
    v = padre[clave]
    if isinstance(v, str):
        if texto_estructurado(v):
            puntos.append((padre, clave))
    elif isinstance(v, dict):
        if "translate" not in v and isinstance(v.get("text"), str) and texto_estructurado(v["text"]):
            puntos.append((v, "text"))
        extra = v.get("extra")
        if isinstance(extra, list):
            for i in range(len(extra)):
                _puntos_componente(extra, i, puntos)
    elif isinstance(v, list):
        for i in range(len(v)):
            _puntos_componente(v, i, puntos)


def puntos_traducibles(datos, tipo):
    puntos = []
    if tipo == "bq":
        pila = [datos]
        while pila:
            nodo = pila.pop()
            if isinstance(nodo, dict):
                bq = nodo.get("betterquesting:10")
                if isinstance(bq, dict):
                    for k in ("name:8", "desc:8"):
                        if isinstance(bq.get(k), str) and texto_estructurado(bq[k]):
                            puntos.append((bq, k))
                pila.extend(v for k, v in nodo.items() if k != "betterquesting:10")
            elif isinstance(nodo, list):
                pila.extend(nodo)
    elif tipo == "heracles" and isinstance(datos, dict):
        disp = datos.get("display")
        if isinstance(disp, dict):
            for k in ("title", "subtitle"):
                if k in disp:
                    _puntos_componente(disp, k, puntos)
            desc = disp.get("description")
            if isinstance(desc, list):
                for i, linea in enumerate(desc):
                    if isinstance(linea, str) and texto_estructurado(linea):
                        puntos.append((desc, i))
            elif isinstance(desc, str) and texto_estructurado(desc):
                puntos.append((disp, "description"))
    return puntos


def leer_json(ruta):
    with open(ruta, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def textos_de_puntos(puntos):
    textos = set()
    for cont, k in puntos:
        for es_prot, seg in separar_protegidos(cont[k], REGEX_JSON):
            if not es_prot and tiene_letras(seg):
                textos.add(seg)
    return textos


def procesar_estructurado(ruta, destino, traductor, idioma, tipo, indice=0, total=1):
    datos = leer_json(ruta)
    puntos = puntos_traducibles(datos, tipo)
    mapa, fallidas = resolver_textos(textos_de_puntos(puntos), traductor, idioma,
                                     os.path.basename(ruta), indice, total)
    for cont, k in puntos:
        cont[k] = reconstruir_json(mapa, separar_protegidos(cont[k], REGEX_JSON))
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    return fallidas


def buscar_estructurados(ruta_entrada):
    encontrados = {}
    for r, files in recorrer(ruta_entrada, PODAR_INSTANCIA):
        for f in files:
            ruta = os.path.join(r, f)
            tipo = tipo_estructurado(ruta)
            if not tipo:
                continue
            try:
                if puntos_traducibles(leer_json(ruta), tipo):
                    encontrados[ruta] = tipo
            except Exception:
                pass
    return encontrados


def textos_de_archivo(ruta, tipo=None):
    if tipo:
        return textos_de_puntos(puntos_traducibles(leer_json(ruta), tipo))
    if ruta.lower().endswith(".json"):
        with open(ruta, "r", encoding="utf-8-sig") as f:
            datos = json.load(f)
        return extraer_textos_json(datos) if isinstance(datos, dict) else set()
    with open(ruta, "r", encoding="utf-8") as f:
        return extraer_textos(f.read(), es_lang_snbt(ruta))


def es_lang_snbt(ruta):
    partes = ruta.replace("\\", "/").lower().split("/")
    return "lang" in partes[:-1] and (partes[-1] == "en_us.snbt" or "en_us" in partes[:-1])


def carpeta_misiones(ruta):
    """Devuelve una lista de todas las rutas posibles donde pueden estar misiones."""
    rutas = []
    # Rutas estándar de FTB Quests / Better Questing
    cand = os.path.join(ruta, "config", "ftbquests", "quests")
    if os.path.isdir(cand):
        rutas.append(cand)
    # Rutas alternativas (kubejs/data/...)
    for sub in [
        os.path.join(ruta, "kubejs", "data", "ftbquests", "quests"),
        os.path.join(ruta, "kubejs", "data", "minecraft", "quests"),
        os.path.join(ruta, "kubejs", "data", "betterquests", "DefaultQuests"),
    ]:
        if os.path.isdir(sub):
            rutas.append(sub)
    # Si no encontró nada específico, usa la raíz
    if not rutas:
        rutas.append(ruta)
    return rutas


def recorrer(raiz, podar):
    for r, dirs, files in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in podar and not d.lower().startswith("quests-backup")]
        yield r, files


PAQUETE = "FTB_Translator_Misiones"
RE_LANG_EMPACADO = re.compile(r'^assets/([^/]+)/lang/en_us\.json$', re.IGNORECASE)


def raiz_instancia(ruta):
    actual = os.path.abspath(ruta)
    for _ in range(6):
        if os.path.isdir(os.path.join(actual, "mods")) or os.path.isfile(os.path.join(actual, "options.txt")):
            return actual
        padre = os.path.dirname(actual)
        if padre == actual:
            break
        actual = padre
    return os.path.abspath(ruta)


def buscar_en_empaquetados(raiz, faltan):
    hallados = []
    contenedores = []
    for carpeta, ext in (("mods", ".jar"), ("resourcepacks", ".zip")):
        d = os.path.join(raiz, carpeta)
        if os.path.isdir(d):
            contenedores += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.lower().endswith(ext)]
    for cont in contenedores:
        if not faltan:
            break
        try:
            with zipfile.ZipFile(cont) as z:
                for nombre in z.namelist():
                    m = RE_LANG_EMPACADO.match(nombre)
                    if not m:
                        continue
                    try:
                        datos = json.loads(z.read(nombre).decode("utf-8-sig"))
                    except Exception:
                        continue
                    if not isinstance(datos, dict):
                        continue
                    utiles = {k: v for k, v in datos.items() if k in faltan}
                    if not utiles:
                        continue
                    ns = m.group(1)
                    extraido = os.path.join(RUTA_SALIDA_FIJA, "_extraido", os.path.basename(raiz),
                                            os.path.basename(cont), "assets", ns, "lang", "en_us.json")
                    os.makedirs(os.path.dirname(extraido), exist_ok=True)
                    with open(extraido, "w", encoding="utf-8") as fh:
                        json.dump(utiles, fh, ensure_ascii=False, indent=2)
                    faltan -= set(utiles)
                    hallados.append({"ruta": extraido, "tipo": "json", "relevante": True, "empacado": True,
                                     "ns": ns, "tam": os.path.getsize(extraido),
                                     "motivo": f"estaba dentro de {os.path.basename(cont)} ({len(utiles)} textos de misiones)"})
        except (zipfile.BadZipFile, OSError):
            continue
    return hallados


RE_PROTEGIDO = re.compile(r"^\s*[A-Z0-9]{2,8}:[A-Za-z0-9+/=\r\n]{16,}")
CONFIG_EXTRACTOR = os.path.join("config", "translations_extractor-client.toml")


def archivo_protegido(ruta):
    try:
        with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
            return bool(RE_PROTEGIDO.match(f.read(300)))
    except OSError:
        return False


def buscar_extractor(raiz):
    hallados = []
    rp = os.path.join(raiz, "resourcepacks")
    try:
        paquetes = sorted(d for d in os.listdir(rp)
                          if d.lower().startswith("extractedtranslations") and os.path.isdir(os.path.join(rp, d)))
    except OSError:
        return hallados
    for paquete in paquetes:
        assets = os.path.join(rp, paquete, "assets")
        if not os.path.isdir(assets):
            continue
        for ns in sorted(os.listdir(assets)):
            carpeta_lang = os.path.join(assets, ns, "lang")
            if not os.path.isdir(carpeta_lang):
                continue
            for nombre in sorted(os.listdir(carpeta_lang)):
                if not nombre.lower().endswith(".json"):
                    continue
                try:
                    with open(os.path.join(carpeta_lang, nombre), "r", encoding="utf-8-sig") as fh:
                        datos = json.load(fh)
                except Exception:
                    continue
                utiles = {k: v for k, v in datos.items() if isinstance(v, str) and tiene_letras(v)} \
                    if isinstance(datos, dict) else {}
                if not utiles:
                    continue
                extraido = os.path.join(RUTA_SALIDA_FIJA, "_extraido", os.path.basename(raiz), paquete,
                                        "assets", ns, "lang", "en_us.json")
                os.makedirs(os.path.dirname(extraido), exist_ok=True)
                with open(extraido, "w", encoding="utf-8") as fh:
                    json.dump(utiles, fh, ensure_ascii=False, indent=2)
                de_misiones = ns.lower() in ("ftbquests", "ftbquestlocalizer") or \
                    any(k.lower().startswith("ftbquests") for k in utiles)
                hallados.append({"ruta": extraido, "tipo": "json", "relevante": de_misiones, "empacado": True,
                                 "ns": ns, "tam": os.path.getsize(extraido), "extractor": nombre[:-5].lower(),
                                 "motivo": (f"misiones sacadas por Translations Extractor ({len(utiles)} textos)"
                                            if de_misiones else f"textos de otros mods ({len(utiles)})")})
    return hallados


def ajustar_extractor(raiz, codigo):
    ruta = os.path.join(raiz, CONFIG_EXTRACTOR)
    if not os.path.isfile(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as fh:
            texto = fh.read()
        m = re.search(r'(?m)^(\s*targetLanguage\s*=\s*)"([^"]*)"', texto)
        if not m or m.group(2).lower() == codigo.lower():
            return False
        if not os.path.exists(ruta + ".respaldo"):
            shutil.copy2(ruta, ruta + ".respaldo")
        with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto[:m.start(2)] + codigo + texto[m.end(2):])
        return True
    except Exception:
        return None


def formato_paquete(raiz):
    version = ""
    try:
        with open(os.path.join(raiz, "minecraftinstance.json"), "r", encoding="utf-8-sig") as fh:
            version = str(json.load(fh).get("gameVersion", ""))
    except Exception:
        pass
    tabla = [("1.21.4", 46), ("1.21.2", 42), ("1.21", 34), ("1.20.5", 32), ("1.20.3", 22), ("1.20.2", 18),
             ("1.20", 15), ("1.19.4", 13), ("1.19.3", 12), ("1.19", 9), ("1.18", 8), ("1.17", 7), ("1.16.2", 6),
             ("1.16", 5), ("1.15", 5), ("1.13", 4), ("1.12", 3)]

    def tupla(v):
        return tuple(int(x) for x in re.findall(r"\d+", v)[:3])

    if version:
        for base, fmt in tabla:
            if tupla(version) >= tupla(base):
                return fmt, version
    return 15, version or "desconocida"


def preparar_paquete(raiz, nombre_idioma):
    carpeta = os.path.join(raiz, "resourcepacks", PAQUETE)
    os.makedirs(carpeta, exist_ok=True)
    fmt, version = formato_paquete(raiz)
    meta = {"pack": {"pack_format": fmt, "supported_formats": [1, 999],
                     "description": f"Misiones en {nombre_idioma} ({NOMBRE_APP})"}}
    with open(os.path.join(carpeta, "pack.mcmeta"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    activado = False
    opciones = os.path.join(raiz, "options.txt")
    if os.path.isfile(opciones):
        try:
            with open(opciones, "r", encoding="utf-8") as fh:
                lineas = fh.read().split("\n")
            entrada = f"file/{PAQUETE}"
            for i, linea in enumerate(lineas):
                if linea.startswith("resourcePacks:"):
                    lista = json.loads(linea[len("resourcePacks:"):])
                    if entrada not in lista:
                        if not os.path.exists(opciones + ".respaldo"):
                            shutil.copy2(opciones, opciones + ".respaldo")
                        lista.append(entrada)
                        lineas[i] = "resourcePacks:" + json.dumps(lista)
                        with open(opciones, "w", encoding="utf-8", newline="\n") as fh:
                            fh.write("\n".join(lineas))
                    activado = True
                    break
        except Exception as exc:
            log(f"⚠️ No pude activar el paquete en options.txt: {exc}")
    return activado, fmt, version


def descubrir(ruta_entrada, incluir_todo=False):
    misiones, candidatos, protegidos = [], set(), []
    raiz_qs = carpeta_misiones(ruta_entrada)
    for raiz_q in raiz_qs:
        for r, files in recorrer(raiz_q, IGNORAR_CARPETAS | PODAR_INSTANCIA):
            for f in files:
                ruta = os.path.join(r, f)
                en_lang = "lang" in ruta.replace("\\", "/").lower().split("/")[:-1]
                if f.endswith(".snbt") and f not in IGNORAR_ARCHIVOS and not en_lang:
                    if archivo_protegido(ruta):
                        protegidos.append(ruta)
                        continue
                    misiones.append(ruta)
                    nombre = f.replace(".snbt", "").replace("_", " ").title()
                    if "Ae2" in nombre:
                        nombre = "AE2"
                    if "Rftools" in nombre:
                        nombre = "RFTools"
                    candidatos.add(nombre)
                    if nombre.endswith("s"):
                        candidatos.add(nombre[:-1])

    # Decodificar LGQ1 si está presente (solo en archivos .snbt de misiones)
    for a in list(misiones):
        try:
            with open(a, "r", encoding="utf-8") as fh:
                contenido = fh.read()
        except Exception:
            continue
        if "LGQ1:" not in contenido:
            continue
        decoded = decode_lgq1_content(contenido)
        backup_path = a + ".backup_lgq1"
        shutil.copy2(a, backup_path)
        with open(a, "w", encoding="utf-8") as fh:
            fh.write(decoded)

    estructurados = buscar_estructurados(ruta_entrada)
    manifiesto, origenes = cargar_manifiesto(), {}
    for a in misiones + list(estructurados):
        try:
            if os.path.exists(a + ".respaldo") and manifiesto.get(a) == _sha(a):
                origenes[a] = a + ".respaldo"
        except OSError:
            pass

    referencias, n_refs = set(), 0
    for a in misiones:
        try:
            contenido = _leer_con_lgq1(origenes.get(a, a))
            if contenido is not None:
                encontradas = RE_REFERENCIA_CLAVE.findall(contenido)
                n_refs += len(encontradas)
                referencias.update(encontradas)
        except Exception:
            pass

    idiomas, cubiertas = [], set()
    for r, files in recorrer(ruta_entrada, PODAR_INSTANCIA):
        for f in files:
            ruta = os.path.join(r, f)
            fl = f.lower()
            try:
                tam = os.path.getsize(ruta)
            except OSError:
                continue
            if fl == "en_us.json" and tam < 30_000_000:
                relevante, motivo = False, "no parece de misiones"
                try:
                    with open(ruta, "r", encoding="utf-8-sig") as fh:
                        datos = json.load(fh)
                    claves = list(datos.keys()) if isinstance(datos, dict) else []
                    if referencias and any(k in referencias for k in claves):
                        relevante, motivo = True, "tiene el texto que usan las misiones"
                        cubiertas.update(k for k in claves if k in referencias)
                    elif any(k.lower().startswith("ftbquests") for k in claves):
                        relevante, motivo = True, "claves de FTB Quests"
                except Exception:
                    motivo = "no se pudo leer"
                idiomas.append({"ruta": ruta, "tipo": "json", "relevante": relevante, "motivo": motivo, "tam": tam})
            elif (fl.endswith(".snbt") or fl.endswith(".snbt_merged")) and es_lang_snbt(ruta):
                rel = "ftbquests" in ruta.lower()
                idiomas.append({"ruta": ruta, "tipo": "snbt", "relevante": rel, "tam": tam,
                                "motivo": "idioma nativo de FTB Quests" if rel else "no parece de misiones"})
    hay_snbt_lang = any(l["tipo"] == "snbt" and l["relevante"] for l in idiomas)
    faltan = referencias - cubiertas
    if faltan and not hay_snbt_lang:
        idiomas += buscar_en_empaquetados(raiz_instancia(ruta_entrada), set(faltan))
    idiomas += buscar_extractor(raiz_instancia(ruta_entrada))
    return {"misiones": misiones, "candidatos": candidatos, "lang": idiomas, "n_refs": n_refs, "origenes": origenes,
            "estructurados": estructurados, "protegidos": protegidos}


def mapear_ruta(ruta, lang, es_lang):
    carpeta, nombre = os.path.split(ruta)
    if es_lang and nombre.lower().endswith(".snbt_merged"):
        nombre = nombre[:-len("_merged")]
    if nombre.lower() in ("en_us.json", "en_us.snbt"):
        nombre = lang["mc"] + os.path.splitext(nombre)[1]
    if carpeta and es_lang:
        carpeta = os.sep.join(lang["mc"] if p.lower() == "en_us" else p for p in carpeta.split(os.sep))
    return os.path.join(carpeta, nombre)


ARCHIVO_MANIFIESTO = os.path.join(RUTA_SALIDA_FIJA, "instalados.json")


def _sha(ruta):
    h = hashlib.sha1()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def cargar_manifiesto():
    try:
        with open(ARCHIVO_MANIFIESTO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_manifiesto(m):
    try:
        with open(ARCHIVO_MANIFIESTO, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
    except Exception as exc:
        log(f"⚠️ No pude guardar el registro de instalaciones: {exc}")


def instalar_archivo(generado, objetivo, manifiesto):
    os.makedirs(os.path.dirname(objetivo), exist_ok=True)
    if os.path.exists(objetivo) and manifiesto.get(objetivo) != _sha(objetivo):
        respaldo = objetivo + ".respaldo"
        if os.path.exists(respaldo):
            os.replace(respaldo, f"{respaldo}-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(objetivo, respaldo)
    shutil.copy2(generado, objetivo)
    manifiesto[objetivo] = _sha(objetivo)


def iniciar_proceso(ruta_entrada, lang, api_deepl, instalar=False, incluir_todo=False, libre_url=""):
    global REGEX_PROTEGIDO, REGEX_JSON
    idioma, nombre_idioma = lang["id"], lang["nombre"]
    _CACHE_EXISTENTES.clear()
    try:
        log("🔎 Buscando misiones e idiomas en el modpack...")
        info = descubrir(ruta_entrada, incluir_todo)
        candidatos, origenes = info["candidatos"], info["origenes"]
        manifiesto = cargar_manifiesto()
        estructurados = info["estructurados"]
        if (not incluir_todo and not info["misiones"] and not estructurados and info["lang"] and len(info["lang"]) <= 3
                and not any(l["relevante"] for l in info["lang"])):
            incluir_todo = True
            log("ℹ️ Elegiste una carpeta con archivos de idioma: los traduzco aunque no vea claves de misiones.")
        elegidos = [l for l in info["lang"] if l["relevante"] or incluir_todo]
        omitidos = [l for l in info["lang"] if l not in elegidos]
        archivos = list(info["misiones"]) + list(estructurados) + [l["ruta"] for l in elegidos]
        total = len(archivos)
        protegidos = info["protegidos"]
        if protegidos:
            log(f"🔒 {len(protegidos)} archivos de misiones están protegidos por el autor del modpack. "
                "Babel no los lee ni los modifica.")
            ajuste = ajustar_extractor(raiz_instancia(ruta_entrada), lang["mc"])
            if ajuste:
                log(f"🔧 Ajusté Translations Extractor para que saque los textos en {lang['mc']}. "
                    "Vuelve a ejecutar /extract translations lang en el juego.")
            if not any(l.get("extractor") for l in elegidos):
                log("ℹ️ Para traducirlo: agrega los mods «Translations Extractor» y «FTB Quest Localizer», "
                    "entra a un mundo, escribe /extract translations lang y vuelve a usar Babel.")
        for l in elegidos:
            if l.get("extractor") and l["extractor"] != lang["mc"].lower():
                log(f"ℹ️ El extractor sacó textos pensados para {l['extractor']}; Babel los traduce a {nombre_idioma}.")
                break
        if total == 0 and protegidos:
            aviso("error", "Este modpack protege sus misiones",
                  "El autor del modpack protegió los archivos de misiones, así que Babel no puede leerlos "
                  "(y no va a modificarlos).\n\n"
                  "Para traducirlo de forma segura:\n"
                  "1. Agrega al modpack los mods «Translations Extractor» y «FTB Quest Localizer».\n"
                  "2. Abre el juego una vez y ciérralo.\n"
                  "3. Abre Babel y pulsa Traducir: ajustará el extractor a tu idioma.\n"
                  "4. Abre el juego, entra a un mundo y escribe: /extract translations lang\n"
                  "5. Cierra el juego y vuelve a pulsar Traducir en Babel. Traducirá esos textos y "
                  "activará un paquete de recursos con la traducción.")
            return
        if total == 0:
            aviso("error", "No encontré nada que traducir",
                  "No encontré misiones de FTB Quests, Better Questing ni Heracles/Odyssey Quests, "
                  "ni archivos de idioma de misiones.\n\n"
                  "Elige la carpeta del modpack (la que contiene config, mods, kubejs...).")
            return

        log(f"📚 Misiones (.snbt): {len(info['misiones'])} | archivos de idioma a traducir: {len(elegidos)}")
        for sistema in sorted(set(estructurados.values())):
            n = sum(1 for t in estructurados.values() if t == sistema)
            log(f"📚 Misiones de {NOMBRES_SISTEMA[sistema]}: {n} archivo(s)")
        for l in elegidos:
            nombre_l = (f"assets/{l['ns']}/lang/en_us.json" if l.get("empacado")
                        else os.path.relpath(l['ruta'], ruta_entrada))
            log(f"   🌐 {nombre_l}  ({max(1, l['tam'] // 1024)} KB) - {l['motivo']}")
        if omitidos:
            log(f"   ⏭ Omití {len(omitidos)} archivos de idioma que no parecen de misiones (otros mods). "
                "Activa «Incluir textos de otros mods» si los quieres.")
        if info["n_refs"]:
            log(f"📎 Hay {info['n_refs']} referencias tipo {{clave}} en los .snbt: su texto real está en un archivo de idioma.")
            if not elegidos:
                log("⚠️ No encontré ese archivo de idioma. Puede estar dentro de un .jar/.zip (ábrelo con 7-Zip y "
                    "saca el en_us.json a una carpeta normal) o en una carpeta que no elegiste.")

        GENERICOS = [
            "Getting Started", "Bosses", "Challenges", "Magic", "Tech", "Exploration",
            "Welcome", "Tips", "Information", "Basic", "Storage", "Farming", "Mining",
            "Dimensions", "Tools", "Weapons", "Armors", "Introduction", "Finale", "Quest",
            "Chapter Groups"
        ]
        protegidos = [n for n in candidatos if not any(g.lower() in n.lower() for g in GENERICOS)]
        REGEX_PROTEGIDO = crear_regex_proteccion(protegidos)
        REGEX_JSON = crear_regex_proteccion(protegidos, json_mode=True)

        SECRETOS[:] = [api_deepl] if api_deepl else []
        log(f"🌍 Traduciendo al: {nombre_idioma.upper()}")
        log(f"💾 Traducciones en memoria: {len(MEMORIA_GLOBAL)}")
        log("🔎 Probando motores...")
        traductor = Traductor(lang, api_deepl, libre_url)
        if not traductor.probar():
            aviso("error", "Ningún motor responde",
                  "Ningún motor de traducción funciona ahora mismo.\n\n" + traductor.resumen() +
                  "\n\nSi Google te bloqueó, espera unas horas, usa una clave gratis de DeepL "
                  "o abre LibreTranslate en tu computadora.")
            return

        pendientes_total, caracteres = set(), 0
        for a in archivos:
            try:
                contenido = _leer_con_lgq1(origenes.get(a, a))
                if contenido is not None:
                    for t in textos_de_archivo(contenido, estructurados.get(a)):
                        if f"{idioma}|{t}" not in MEMORIA_GLOBAL and t not in pendientes_total:
                            pendientes_total.add(t)
                            caracteres += len(t)
            except Exception as exc:
                log(f"⚠️ No pude leer {os.path.basename(a)}: {type(exc).__name__}: {exc}")
        log(f"📊 Por traducir: {len(pendientes_total)} textos (~{caracteres:,} caracteres)")
        if api_deepl:
            uso = uso_deepl(api_deepl)
            if uso:
                usados, limite = uso
                log(f"📈 DeepL: {usados:,} de {limite:,} caracteres usados este mes")
                if caracteres > limite - usados:
                    log("⚠️ Puede que no alcance la cuota de DeepL; el resto pasará a Microsoft/Google/LibreTranslate.")

        ruta_salida = os.path.join(RUTA_SALIDA_FIJA, "_traducido")
        raiz = raiz_instancia(ruta_entrada)
        empacados = {l["ruta"]: l for l in elegidos if l.get("empacado")}
        rel_de, base_de = {}, {}
        for a in archivos:
            if a in empacados:
                rel = os.path.join("resourcepacks", PAQUETE, "assets", empacados[a]["ns"], "lang", "en_us.json")
                rel_de[a], base_de[a] = rel, os.path.join(raiz, rel)
            else:
                rel_de[a], base_de[a] = os.path.relpath(a, ruta_entrada), a
        hubo_lang = False
        hubo_paquete = False
        n_instalados = 0
        temporales_lgq1 = []
        for i, a in enumerate(archivos):
            if DETENER.is_set():
                raise Detenido()
            tipo = estructurados.get(a)
            es_json = not tipo and a.lower().endswith(".json")
            es_lang = es_json or (not tipo and es_lang_snbt(a))
            hubo_lang = hubo_lang or es_lang
            dest = os.path.join(ruta_salida, mapear_ruta(rel_de[a], lang, es_lang))
            src = origenes.get(a, a)
            if src != a:
                log(f"↩ {os.path.basename(a)}: traduzco desde el original guardado (.respaldo)")
            # Si el archivo fuente tiene LGQ1 (ej. respaldo con LGQ1), decodificar en temporal
            src_limpio = None
            if os.path.exists(src):
                try:
                    with open(src, 'r', encoding='utf-8') as fh:
                        contenido_src = fh.read()
                    if 'LGQ1:' in contenido_src:
                        tmp = tempfile.NamedTemporaryFile(mode='w', suffix=os.path.splitext(src)[1],
                                                           delete=False, encoding='utf-8')
                        tmp.write(decode_lgq1_content(contenido_src))
                        tmp.close()
                        src_limpio = tmp.name
                        temporales_lgq1.append(tmp.name)
                except Exception:
                    pass
            try:
                if tipo:
                    sin_traducir = procesar_estructurado(src_limpio or src, dest, traductor, idioma, tipo, i, total)
                elif es_json:
                    sin_traducir = procesar_json(src_limpio or src, dest, traductor, idioma, i, total,
                                                 existentes=traducciones_existentes_json(a, lang["mc"]))
                else:
                    en_lang = es_lang_snbt(a)
                    sin_traducir = procesar_archivo(
                        src_limpio or src, dest, traductor, idioma, i, total, modo_lang=en_lang,
                        existentes=traducciones_existentes_snbt(a, lang["mc"]) if en_lang else None)
                if sin_traducir:
                    log(f"⚠️ {os.path.basename(a)}: {sin_traducir} textos sin traducir")
                else:
                    log(f"✅ {os.path.basename(a)}" + (f"  →  {os.path.basename(dest)}" if es_lang else ""))
                if instalar:
                    if es_json or not sin_traducir:
                        objetivo = mapear_ruta(base_de[a], lang, es_lang)
                        instalar_archivo(dest, objetivo, manifiesto)
                        hubo_paquete = hubo_paquete or a in empacados
                        guardar_manifiesto(manifiesto)
                        n_instalados += 1
                        log(f"   📥 Instalado: {objetivo}")
                    else:
                        log("   ⏸ No lo instalé porque quedaron textos sin traducir. Vuelve a ejecutar para completarlo.")
                elif es_lang:
                    log(f"   📁 Guardado en: {dest}")
                if es_lang and lang.get("variantes"):
                    for v in lang["variantes"]:
                        lang_v = dict(lang, mc=v)
                        dest_v = os.path.join(ruta_salida, mapear_ruta(rel_de[a], lang_v, es_lang))
                        os.makedirs(os.path.dirname(dest_v), exist_ok=True)
                        shutil.copy2(dest, dest_v)
                        if instalar and (es_json or not sin_traducir):
                            instalar_archivo(dest_v, mapear_ruta(base_de[a], lang_v, es_lang), manifiesto)
                    if instalar:
                        guardar_manifiesto(manifiesto)
                    log(f"   📥 Copias también para: {', '.join(lang['variantes'])}")
            except (TodosBloqueados, Detenido):
                raise
            except Exception as e:
                log(f"❌ {os.path.basename(a)}: {type(e).__name__}: {e}")
            progreso(((i + 1) / total) * 100)
            # Limpiar archivos temporales LGQ1 creados en este bucle
            for tmp in temporales_lgq1:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
            temporales_lgq1.clear()

        guardar_seguro()
        if instalar and "bq" in estructurados.values():
            extra_bq = ("\n\nBetter Questing: las misiones traducidas se cargan en mundos nuevos. "
                        "En un mundo ya creado, con trucos activados escribe /bq_admin default load.")
        else:
            extra_bq = ""
        aviso_paquete = ""
        if hubo_paquete:
            activado, fmt, version = preparar_paquete(raiz, nombre_idioma)
            log(f"📦 Paquete de recursos creado: resourcepacks/{PAQUETE} (Minecraft {version}, formato {fmt})")
            if activado:
                aviso_paquete = ("\n\nCreé el paquete de recursos «" + PAQUETE + "» y lo activé. "
                                 "Si el juego estaba abierto, ciérralo y vuelve a abrirlo; si no aparece, "
                                 "actívalo en Opciones > Paquetes de recursos.")
            else:
                aviso_paquete = ("\n\nCreé el paquete de recursos «" + PAQUETE + "». Actívalo en el juego: "
                                 "Opciones > Paquetes de recursos.")
        elif empacados and not instalar:
            aviso_paquete = ("\n\nParte del texto venía dentro de un mod: quedó en _traducido/resourcepacks/" + PAQUETE +
                             ". Cópiala a la carpeta resourcepacks del modpack y actívala en el juego.")
        if ESTADO["nuevas"] == 0 and ESTADO["cache"] > 0:
            log("ℹ️ Todo ya estaba en la memoria: no se pidió nada nuevo. Los archivos se regeneraron desde la memoria.")
        desglose = ", ".join(f"{k}: {v}" for k, v in ESTADO["motores"].items()) or "ninguno"
        log(f"🧮 Traducido por motor -> {desglose}")
        if api_deepl:
            uso = uso_deepl(api_deepl)
            if uso:
                log(f"📈 DeepL: {uso[0]:,} de {uso[1]:,} caracteres usados este mes")
        extra = ""
        if ESTADO["fallidas"]:
            extra = (f"\n\n⚠️ {ESTADO['fallidas']} textos quedaron sin traducir. Vuelve a ejecutar: "
                     "solo reintentará los pendientes.")
        if instalar and n_instalados:
            if hubo_lang and lang.get("variantes"):
                aviso_juego = ("\nQuedó para estos idiomas del juego: " + ", ".join([lang["mc"]] + lang["variantes"]) +
                               ". Elige el tuyo y recarga con F3+T.")
            elif hubo_lang:
                aviso_juego = f"\nEn el juego elige el idioma «{nombre_idioma}» ({lang['mc']}) y recarga con F3+T."
            else:
                aviso_juego = ""
            extra += (f"\n\nInstalé {n_instalados} archivo(s) directamente en el modpack (lo que reemplazó quedó como .respaldo)."
                      + aviso_juego)
        elif hubo_lang:
            extra += (f"\n\nPara usar el idioma: copia {lang['mc']}.json (o .snbt) junto al en_us original "
                      f"y elige «{nombre_idioma}» en el juego (recarga con F3+T).")
        aviso("info", "Listo",
              f"Traducción finalizada.\nNuevas: {ESTADO['nuevas']} | De memoria: {ESTADO['cache']}"
              f"\nCarpeta: Documentos/{os.path.basename(RUTA_SALIDA_FIJA)}{extra}{aviso_paquete}{extra_bq}")

    except TodosBloqueados as e:
        guardar_seguro()
        log("🛑 Todos los motores están bloqueados o en descanso. Progreso guardado.")
        aviso("error", "Motores bloqueados",
              f"Se detuvo para no perder tiempo.\n\n{e}\n\nTu progreso está guardado: "
              "vuelve a ejecutar más tarde y continuará donde quedó.")
    except Detenido:
        guardar_seguro()
        log("⏹️ Detenido por ti. Progreso guardado.")
    except Exception as e:
        guardar_seguro()
        log(f"💥 Error inesperado: {type(e).__name__}: {e}")
        aviso("error", "Error inesperado", f"{type(e).__name__}: {e}\n\nEl progreso se guardó.")
    finally:
        COLA.put(("fin",))


# Paleta neón: negro violeta, morado y cian
C = {
    "fondo": "#07060D", "lateral": "#0B0916", "tarjeta": "#110E1E", "campo": "#0A0814",
    "borde": "#251E3E", "borde_hover": "#3B2F66", "boton": "#1A1530", "boton_hover": "#272048",
    "nav_hover": "#14102A", "nav_activo": "#1C1538",
    "morado": "#A855F7", "cian": "#22D3EE", "aviso": "#FFC857",
    "texto": "#F4F3FF", "suave": "#9C97BD", "tenue": "#5E5880",
    "peligro": "#FF4D6D", "peligro_fondo": "#3A1224",
    "consola": "#05040A", "consola_txt": "#C4BFEA", "ok": "#2EF2A0", "ok_fondo": "#0E2E24", "mal": "#FF4D6D",
}
DISPLAY = "Bahnschrift SemiBold"
INTERRUPTOR = dict(progress_color=C["morado"], fg_color=C["borde"], button_color=C["texto"], button_hover_color="#FFFFFF")
ARCHIVO_CONFIG = os.path.join(RUTA_SALIDA_FIJA, "config.json")
URL_DEEPL = "https://www.deepl.com/pro-api"


def cargar_config():
    try:
        with open(ARCHIVO_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_config(datos):
    try:
        with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        log(f"⚠️ No pude guardar la configuración: {exc}")


def abrir_carpeta(ruta):
    try:
        os.makedirs(ruta, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(ruta)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", ruta])
    except Exception as exc:
        messagebox.showerror("No pude abrir la carpeta", str(exc))


# Animación: en cada cuadro lo mostrado se acerca al objetivo (suavizado = ease-out, y se interrumpe solo)
OBJETIVO = {"prog": 0.0, "nuevas": 0, "cache": 0, "fallidas": 0, "alfa": 100, "desliz": 0, "indicador": 0}
MOSTRADO = {"prog": 0.0, "nuevas": 0, "cache": 0, "fallidas": 0, "alfa": 0, "desliz": 0, "indicador": 0}
FUNDIDOS = {}
TRADUCIENDO = [False]
CUADRO = [0]
PAGINA = [None, None]  # página visible y su botón de la barra lateral
ESTILOS_LOG = {"ok": "✅🎉", "aviso": "⚠🐢⏳", "error": "⛔❌💥🛑", "tenue": "➖ℹ"}


def mezclar(a, b, t):
    a, b = int(a[1:], 16), int(b[1:], 16)
    return "#" + "".join(f"{round((a >> s & 255) * (1 - t) + (b >> s & 255) * t):02X}" for s in (16, 8, 0))


def fundir(widget, prop, desde, hasta, ms=700):
    FUNDIDOS[(widget, prop)] = (time.time(), ms / 1000, desde, hasta)


def dibujar(clave, v):
    if clave == "prog":
        barra.set(v / 100)
        mini_barra.set(v / 100)
        texto = f"{v:.0f}%"
        lbl_pct.poner(texto=texto)
        if lbl_mini_pct.cget("text") != texto:
            lbl_mini_pct.configure(text=texto)
    elif clave == "alfa":
        app.attributes("-alpha", v / 100)
    elif clave == "desliz":
        PAGINA[0].place(x=v, y=0, relwidth=1, relheight=1)
    elif clave == "indicador":
        indicador.place(x=0, y=v)
    else:
        n = round(v)
        stats[clave].configure(text=f"{n:,}".replace(",", " "), text_color=C["mal"] if clave == "fallidas" and n else C["texto"])


def animar():
    try:
        CUADRO[0] += 1
        for clave, meta in OBJETIVO.items():
            lento = clave in stats  # los contadores a ~10 cuadros/s: redibujar etiquetas en cada cuadro es caro
            if lento and CUADRO[0] % 6:
                continue
            v = MOSTRADO[clave]
            if v != meta:
                v = meta if abs(meta - v) < 0.4 else v + (meta - v) * (0.5 if lento else 0.18)
                MOSTRADO[clave] = v
                dibujar(clave, v)
        ahora = time.time()
        for (w, prop), (t0, dur, desde, hasta) in list(FUNDIDOS.items()):
            t = min(1.0, (ahora - t0) / dur)
            w.configure(**{prop: mezclar(desde, hasta, 1 - (1 - t) ** 3)})
            if t == 1.0:
                del FUNDIDOS[(w, prop)]
        if PAGINA[1]:
            b = PAGINA[1]
            OBJETIVO["indicador"] = b.winfo_y() + (b.winfo_height() - indicador.winfo_reqheight()) / 2
        if TRADUCIENDO[0] and btn_inicio.winfo_ismapped():
            btn_inicio.brillar(0.3 + 0.7 * abs(ahora % 2 - 1))
            puntos = int(ahora * 2.5) % 4
            texto = "TRADUCIENDO" + "." * puntos + " " * (3 - puntos)
            if btn_inicio.texto != texto:
                btn_inicio.poner(texto=texto)
    finally:
        app.after(16, animar)


def estilo_log(linea):
    return next((tag for tag, iniciales in ESTILOS_LOG.items() if linea and linea[0] in iniciales), "")


def bombear():
    hay_log = False
    try:
        while True:
            item = COLA.get_nowait()
            tipo = item[0]
            if tipo == "log":
                txt.insert("end", item[1] + "\n", estilo_log(item[1]))
                hay_log = True
            elif tipo == "prog":
                OBJETIVO["prog"] = max(0.0, min(100.0, item[1]))
            elif tipo == "estado":
                lbl_estado.configure(text=item[1])
            elif tipo == "motor":
                if item[1] in chips:
                    pintar_motor(item[1], item[2])
            elif tipo == "info":
                messagebox.showinfo(item[1], item[2])
            elif tipo == "error":
                messagebox.showerror(item[1], item[2])
            elif tipo == "fin":
                TRADUCIENDO[0] = False
                btn_inicio.poner(activo=True, texto="▶  TRADUCIR")
                btn_inicio.brillar(0.55)
                btn_stop.configure(state="disabled", border_color=C["borde"])
                if OBJETIVO["prog"] >= 99.5 and not DETENER.is_set():
                    lbl_estado.configure(text="¡Traducción terminada!", text_color=C["ok"])
                    lbl_mini.configure(text="●  Terminado", text_color=C["ok"])
                    lbl_pct.poner(color=C["ok"])
                    barra.colores = (C["ok"], C["cian"])
                    barra.pintar()
                else:
                    lbl_estado.configure(text="Listo para empezar")
                    lbl_mini.configure(text="●  En espera", text_color=C["suave"])
    except queue.Empty:
        pass
    if hay_log:
        txt.see("end")  # una vez por tanda: cada see() redibuja la barra de scroll
    for clave in stats:
        OBJETIVO[clave] = ESTADO[clave]
    app.after(100, bombear)


def validar_ruta(_=None):
    ruta = entrada_ruta.get().strip()
    if not ruta:
        texto, color = "", C["suave"]
    elif not os.path.isdir(ruta):
        texto, color = "✗  Esa carpeta no existe", C["mal"]
    else:
        raiz = raiz_instancia(ruta)
        if os.path.isdir(os.path.join(raiz, "mods")) or os.path.isfile(os.path.join(raiz, "options.txt")):
            texto, color = f"✓  Modpack: {os.path.basename(raiz)}", C["ok"]
        else:
            texto, color = "Existe, pero no parece la carpeta de un modpack", C["aviso"]
    lbl_ruta.configure(text=texto, text_color=color)


def alternar_clave():
    ver = btn_ojo.cget("text_color") != C["cian"]
    entrada_api.configure(show="" if ver else "•")
    btn_ojo.configure(text_color=C["cian"] if ver else C["texto"])


def navegar(clave):
    pagina, boton = PAGINAS[clave]
    if PAGINA[0] is pagina:
        return
    for otra, b in PAGINAS.values():
        b.marcar(False)
        otra.place_forget()
    boton.marcar(True)
    PAGINA[:] = [pagina, boton]
    MOSTRADO["desliz"] = 28  # la página entra deslizándose desde la derecha
    dibujar("desliz", 28)
    indicador.place(x=0, y=MOSTRADO["indicador"])


def copiar_registro():
    app.clipboard_clear()
    app.clipboard_append(txt.get("1.0", "end-1c"))
    btn_copiar.configure(text="✓  Copiado", text_color=C["ok"])
    app.after(1500, lambda: btn_copiar.configure(text="Copiar", text_color=C["suave"]))


def elegir_carpeta():
    ruta = filedialog.askdirectory(title="Carpeta de misiones (.snbt)")
    if ruta:
        entrada_ruta.delete(0, "end")
        entrada_ruta.insert(0, ruta)
        validar_ruta()


def boton_iniciar():
    ruta = entrada_ruta.get().strip()
    if not ruta or not os.path.isdir(ruta):
        messagebox.showerror("Falta la carpeta", "Elige la carpeta de tu modpack (la que contiene config, mods, kubejs...).")
        return
    lang = IDIOMAS.get(combo_idioma.get())
    if not lang:
        messagebox.showerror("Idioma", "Elige un idioma de destino.")
        return
    api = entrada_api.get().strip()
    libre = entrada_libre.get().strip()
    guardar_config({
        "carpeta": ruta, "idioma": combo_idioma.get(), "libre_url": libre,
        "deepl_key": api if var_recordar.get() else "",
        "instalar": bool(var_instalar.get()), "incluir_todo": bool(var_todo.get()),
    })
    DETENER.clear()
    ESTADO.update({"nuevas": 0, "cache": 0, "fallidas": 0, "motores": {}})
    txt.delete("1.0", "end")
    OBJETIVO["prog"] = 0.0
    barra.colores = (C["morado"], C["cian"])
    barra.pintar()
    lbl_pct.poner(color=C["cian"])
    lbl_estado.configure(text_color=C["suave"])
    for nombre in chips:
        pintar_motor(nombre)
    TRADUCIENDO[0] = True
    btn_inicio.poner(activo=False)
    btn_stop.configure(state="normal", border_color=C["peligro"])
    lbl_estado.configure(text="Probando motores de traducción...")
    lbl_mini.configure(text="●  Traduciendo", text_color=C["cian"])
    threading.Thread(target=iniciar_proceso, args=(ruta, lang, api, bool(var_instalar.get()), bool(var_todo.get()), libre),
                     daemon=True).start()


def boton_detener():
    DETENER.set()
    log("⏳ Deteniendo...")


def tarjeta(padre, **pack):
    marco = ctk.CTkFrame(padre, fg_color=C["tarjeta"], corner_radius=16, border_width=1, border_color=C["borde"])
    marco.pack(**{"fill": "x", "pady": (0, 16), **pack})
    cuerpo = ctk.CTkFrame(marco, fg_color="transparent")
    cuerpo.pack(fill="both", expand=True, padx=22, pady=20)
    return cuerpo


def encabezado(pagina, titulo, subtitulo):
    fila = ctk.CTkFrame(pagina, fg_color="transparent")
    fila.pack(fill="x")
    ctk.CTkLabel(fila, text=titulo, text_color=C["texto"], height=38,
                 font=ctk.CTkFont(family=DISPLAY, size=30)).pack(side="left")
    ctk.CTkLabel(pagina, text=subtitulo, text_color=C["suave"], anchor="w", justify="left", wraplength=760,
                 font=ctk.CTkFont(size=13)).pack(fill="x", pady=(2, 12))
    linea = BarraNeon(pagina, 3, C["fondo"], pista="")
    linea.configure(width=px(72))
    linea.pack(anchor="w", pady=(0, px(22)))
    linea.set(1)
    return fila


def etiqueta(padre, texto, pady=(0, 8)):
    ctk.CTkLabel(padre, text=texto, text_color=C["suave"], height=16,
                 font=ctk.CTkFont(family=DISPLAY, size=12)).pack(anchor="w", pady=pady)


def boton_suave(padre, texto, comando, **kw):
    return ctk.CTkButton(padre, text=texto, command=comando, fg_color=C["boton"], hover_color=C["boton_hover"],
                         text_color=C["texto"], corner_radius=10, **kw)


def campo(padre, **kw):
    e = ctk.CTkEntry(padre, height=40, corner_radius=10, fg_color=C["campo"], border_color=C["borde"],
                     text_color=C["texto"], placeholder_text_color=C["tenue"], **kw)
    e.bind("<FocusIn>", lambda _: e.configure(border_color=C["cian"]))
    e.bind("<FocusOut>", lambda _: e.configure(border_color=C["borde"]))
    return e


def opcion(padre, texto, var):
    ctk.CTkSwitch(padre, text=texto, variable=var, text_color=C["suave"], font=ctk.CTkFont(size=12),
                  **INTERRUPTOR).pack(anchor="w", pady=(12, 0))


def opcion_grande(padre, titulo, descripcion, var):
    fila = ctk.CTkFrame(padre, fg_color="transparent")
    fila.pack(fill="x")
    ctk.CTkSwitch(fila, text="", variable=var, width=46, **INTERRUPTOR).pack(side="right")
    col = ctk.CTkFrame(fila, fg_color="transparent")
    col.pack(side="left", fill="x", expand=True)
    ctk.CTkLabel(col, text=titulo, text_color=C["texto"], anchor="w", height=22,
                 font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x")
    ctk.CTkLabel(col, text=descripcion, text_color=C["suave"], anchor="w", justify="left", wraplength=600,
                 font=ctk.CTkFont(size=12)).pack(fill="x")


def tarjeta_motor(padre, nombre, descripcion, **pack):
    c = tarjeta(padre, **pack)
    fila = ctk.CTkFrame(c, fg_color="transparent")
    fila.pack(fill="x")
    ctk.CTkLabel(fila, text=nombre, text_color=C["texto"], font=ctk.CTkFont(family=DISPLAY, size=18)).pack(side="left")
    estados[nombre] = ctk.CTkLabel(fila, text="", height=26, corner_radius=13, font=ctk.CTkFont(size=12))
    estados[nombre].pack(side="right")
    chips[nombre].append(estados[nombre])
    ctk.CTkLabel(c, text=descripcion, text_color=C["suave"], anchor="w", justify="left", wraplength=640,
                 font=ctk.CTkFont(size=12)).pack(fill="x", pady=(2, 12))
    return c


def pintar_motor(nombre, ok=None):
    for chip in chips[nombre]:
        pintar_chip(chip, ok)
    estados[nombre].configure(text="●  " + {None: "Sin probar", True: "Funciona", False: "Con fallos"}[ok])


def pintar_chip(chip, ok=None):
    color, fondo = (C["suave"], C["campo"]) if ok is None else (C["ok"], C["ok_fondo"]) if ok else (C["mal"], C["peligro_fondo"])
    chip.configure(text_color=color)
    if ok is None:
        FUNDIDOS.pop((chip, "fg_color"), None)
        chip.configure(fg_color=fondo)
    else:
        fundir(chip, "fg_color", mezclar(fondo, color, 0.5), fondo)  # destello al cambiar de estado


def barra_titulo():
    # Windows 11: pinta la barra de título con la paleta (en Windows 10 la llamada no hace nada)
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(app.winfo_id())
        for atributo, hexa in ((35, C["fondo"]), (36, C["texto"])):
            color = ctypes.c_int(int(hexa[5:7] + hexa[3:5] + hexa[1:3], 16))  # COLORREF va en BGR
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(color), 4)
    except Exception:
        pass


# Tk no trae degradados, brillos ni esquinas redondas en el Canvas: se dibujan a mano
ESCALA = [1.0]


def px(n):
    return round(n * ESCALA[0])


def rect_redondo(c, x0, y0, x1, y1, r, **kw):
    # polígono suavizado con los puntos de las esquinas duplicados para que los lados queden rectos
    p = (x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y0 + r, x1, y1 - r, x1, y1 - r,
         x1, y1, x1 - r, y1, x1 - r, y1, x0 + r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y1 - r, x0, y0 + r,
         x0, y0 + r, x0, y0)
    return c.create_polygon(p, smooth=True, **kw)


def degradado(c, x0, y0, x1, y1, colores, r):
    # columnas de color recortadas en las esquinas: de 1 px en las curvas y de 6 px en el tramo recto,
    # porque cada columna es un objeto que Tk vuelve a pintar. Devuelve [(x, id)] de izquierda a derecha.
    columnas, x = [], x0
    while x < x1:
        d = max(x0 + r - x, x - (x1 - r), 0)
        paso = 1 if d > 0 else min(6, max(1, x1 - r - x))
        hueco = r - max(r * r - d * d, 0) ** 0.5
        if y1 - y0 > 2 * hueco:
            color = mezclar(colores[0], colores[1], min((x - x0) / (x1 - x0), 1))
            # rectángulos y no líneas: el centro de una línea de 1 px cae en medio píxel y dejaba huecos
            columnas.append((x, c.create_rectangle(x, y0 + hueco, x + paso, y1 - hueco, fill=color, outline="")))
        x += paso
    return columnas


class BarraNeon(tk.Canvas):
    # El degradado se dibuja una vez por tamaño; set() solo muestra u oculta las columnas que cambian
    # y mueve la punta redonda. Redibujar la barra entera en cada cuadro congelaba la ventana.
    def __init__(self, padre, alto, fondo, pista=None):
        super().__init__(padre, height=px(alto), bg=fondo, highlightthickness=0, bd=0)
        self.valor, self.colores, self.columnas, self.visibles = 0.0, (C["morado"], C["cian"]), [], 0
        self.pista = C["campo"] if pista is None else pista
        self.bind("<Configure>", lambda _: self.pintar())

    def pintar(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2:
            return
        if self.pista:
            rect_redondo(self, 0, 0, w, h, h / 2, fill=self.pista, outline="")
        self.columnas = degradado(self, 0, 0, w, h, self.colores, h / 2)
        self.xs = [x for x, _ in self.columnas]
        self.visibles = len(self.columnas)
        self.create_oval(0, 0, 0, 0, outline="", state="hidden", tags="cabeza")  # punta redonda del relleno
        self.set(self.valor)

    def set(self, v):
        self.valor = v
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or not self.pista:
            return
        lleno = w * max(0.0, min(1.0, v))
        limite = lleno - h / 2 if lleno > h else -1
        n = bisect.bisect_left(self.xs, limite)
        for _, item in self.columnas[min(n, self.visibles):max(n, self.visibles)]:
            self.itemconfigure(item, state="normal" if n > self.visibles else "hidden")
        self.visibles = n
        if lleno > h:
            self.coords("cabeza", lleno - h, 0, lleno, h)
            self.itemconfigure("cabeza", state="normal", fill=mezclar(self.colores[0], self.colores[1], limite / w))
        else:
            self.itemconfigure("cabeza", state="hidden")


class BotonNeon(tk.Canvas):
    def __init__(self, padre, texto, comando, fondo, alto=52):
        self.m = px(10)  # margen para el brillo alrededor del botón
        super().__init__(padre, height=px(alto) + 2 * self.m, bg=fondo, highlightthickness=0, bd=0, cursor="hand2")
        self.texto, self.comando, self.fondo, self.activo, self.nivel = texto, comando, fondo, True, 0.55
        self.bind("<Configure>", lambda _: self.dibujar())
        self.bind("<Enter>", self._entrar)
        self.bind("<Leave>", self._salir)
        self.bind("<ButtonRelease-1>", self._soltar)

    def dibujar(self):
        self.delete("all")
        w, h, m, r = self.winfo_width(), self.winfo_height(), self.m, px(14)
        if w < 4 * m:
            return
        for k in (5, 4, 3, 2, 1):  # capas del brillo, de la más ancha a la más pegada
            e = k * m / 5
            rect_redondo(self, m - e, m - e, w - m + e, h - m + e, r + e, outline="", tags=f"brillo{k}")
        colores = (C["morado"], C["cian"])
        if not self.activo:
            colores = tuple(mezclar(col, self.fondo, 0.55) for col in colores)
        degradado(self, m, m, w - m, h - m, colores, r)
        self.create_text(w / 2, h / 2, text=self.texto, fill=C["texto"], font=(DISPLAY, -px(18)), tags="texto")
        self._pintar_brillo()

    def brillar(self, nivel):
        nivel = round(nivel * 20) / 20  # en escalones: cada cambio redibuja el botón entero
        if nivel != self.nivel:
            self.nivel = nivel
            self._pintar_brillo()

    def _pintar_brillo(self):
        for k, fuerza in ((5, 0.06), (4, 0.12), (3, 0.2), (2, 0.3), (1, 0.45)):
            self.itemconfigure(f"brillo{k}", fill=mezclar(self.fondo, C["morado"], fuerza * self.nivel))

    def poner(self, activo=None, texto=None):
        if texto is not None:
            self.texto = texto
            self.itemconfigure("texto", text=texto)
        if activo is not None and activo != self.activo:
            self.activo = activo
            self.configure(cursor="hand2" if activo else "arrow")
            self.dibujar()

    def _entrar(self, _):
        if self.activo:
            self.brillar(1.0)

    def _salir(self, _):
        if self.activo:
            self.brillar(0.55)

    def _soltar(self, e):
        if self.activo and 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self.comando()


class TextoNeon(tk.Canvas):
    def __init__(self, padre, texto, tam, color, fondo, ancho, alto):
        super().__init__(padre, width=px(ancho), height=px(alto), bg=fondo, highlightthickness=0, bd=0)
        self.fondo, self.texto = fondo, texto
        fuente, x, y = (DISPLAY, -px(tam)), px(6), px(alto) / 2
        for r in (3, 2, 1):  # halo: copias desplazadas y apagadas del texto
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                self.create_text(x + dx * px(r), y + dy * px(r), text=texto, font=fuente, anchor="w", tags=("t", f"halo{r}"))
        self.create_text(x, y, text=texto, font=fuente, anchor="w", tags=("t", "nucleo"))
        self.poner(color=color)

    def poner(self, texto=None, color=None):
        if texto is not None and texto != self.texto:  # 25 copias del texto: solo si cambió
            self.texto = texto
            self.itemconfigure("t", text=texto)
        if color is not None:
            for r, fuerza in ((3, 0.07), (2, 0.14), (1, 0.28)):
                self.itemconfigure(f"halo{r}", fill=mezclar(self.fondo, color, fuerza))
            self.itemconfigure("nucleo", fill=color)


class ItemNav(ctk.CTkFrame):
    # botón de la barra lateral con el icono en su propia columna, para que los textos queden alineados
    def __init__(self, padre, icono, texto, comando):
        super().__init__(padre, fg_color="transparent", corner_radius=10, height=44, cursor="hand2")
        self.pack_propagate(False)
        self.activo = False
        self.icono = ctk.CTkLabel(self, text=icono, width=22, font=ctk.CTkFont(size=14))
        self.icono.pack(side="left", padx=(14, 10))
        self.texto = ctk.CTkLabel(self, text=texto, anchor="w", font=ctk.CTkFont(size=14))
        self.texto.pack(side="left", fill="x", expand=True)
        for w in (self, self.icono, self.texto):
            w.bind("<Button-1>", lambda _: comando())
            w.bind("<Enter>", lambda _: self._pintar(True))
            w.bind("<Leave>", self._salir)
        self.marcar(False)

    def _salir(self, e):
        # al pasar del marco a una de sus etiquetas también llega <Leave>: solo cuenta si el ratón salió del todo
        w = self.winfo_containing(e.x_root, e.y_root)
        if not (w and str(w).startswith(str(self))):
            self._pintar(False)

    def _pintar(self, encima):
        self.configure(fg_color=C["nav_activo"] if self.activo else C["nav_hover"] if encima else "transparent")
        color = C["texto"] if self.activo or encima else C["suave"]
        self.texto.configure(text_color=color)
        self.icono.configure(text_color=C["cian"] if self.activo else color)

    def marcar(self, activo):
        self.activo = activo
        self._pintar(False)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = ctk.CTk(fg_color=C["fondo"])
    app.attributes("-alpha", 0.0)  # entra con un fundido (ver animar)
    app.title(f"{NOMBRE_APP} {VERSION}")
    base_recursos = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    icono = os.path.join(base_recursos, "icono.ico")
    if os.path.isfile(icono) and sys.platform == "win32":
        try:
            app.iconbitmap(icono)
            app.after(300, lambda: app.iconbitmap(icono))
        except Exception:
            pass
    if sys.platform == "win32":
        app.after(300, barra_titulo)
    ESCALA[0] = ctk.ScalingTracker.get_widget_scaling(app)
    app.geometry("1180x780")
    app.minsize(1040, 720)

    cfg = cargar_config()

    # ── Barra lateral ──
    lateral = ctk.CTkFrame(app, fg_color=C["lateral"], corner_radius=0, width=240)
    lateral.pack(side="left", fill="y")
    lateral.pack_propagate(False)
    tk.Frame(app, width=1, bg=C["borde"]).pack(side="left", fill="y")

    marca = ctk.CTkFrame(lateral, fg_color="transparent")
    marca.pack(fill="x", padx=20, pady=(26, 0))
    logo_png = os.path.join(base_recursos, "icono.png")
    if os.path.isfile(logo_png):
        try:
            app.logo_img = tk.PhotoImage(file=logo_png)
            tk.Label(marca, image=app.logo_img, bg=C["lateral"], bd=0).pack(side="left", padx=(0, 10))
        except Exception:
            pass
    TextoNeon(marca, NOMBRE_APP.upper(), 34, C["cian"], C["lateral"], 130, 50).pack(side="left")
    ctk.CTkLabel(lateral, text="Traductor de misiones", text_color=C["suave"], height=16,
                 font=ctk.CTkFont(size=12)).pack(anchor="w", padx=26)

    nav = ctk.CTkFrame(lateral, fg_color="transparent")
    nav.pack(fill="x", pady=(30, 0))
    indicador = tk.Frame(nav, bg=C["cian"], width=px(3), height=px(22))
    contenido = ctk.CTkFrame(app, fg_color="transparent")
    contenido.pack(side="left", fill="both", expand=True, padx=36, pady=28)
    PAGINAS = {}
    for clave, icono, texto in (("traducir", "▶", "Traducir"), ("motores", "◆", "Motores"),
                                ("registro", "☰", "Registro"), ("ajustes", "⚙", "Ajustes")):
        boton = ItemNav(nav, icono, texto, lambda c=clave: navegar(c))
        boton.pack(fill="x", padx=14, pady=2)
        PAGINAS[clave] = (ctk.CTkFrame(contenido, fg_color="transparent"), boton)

    ctk.CTkLabel(lateral, text=f"v{VERSION}", text_color=C["tenue"], height=14,
                 font=ctk.CTkFont(size=11)).pack(side="bottom", anchor="w", padx=26, pady=(0, 18))
    mini = ctk.CTkFrame(lateral, fg_color=C["tarjeta"], corner_radius=12, border_width=1, border_color=C["borde"])
    mini.pack(side="bottom", fill="x", padx=14, pady=(0, 10))
    fila_mini = ctk.CTkFrame(mini, fg_color="transparent")
    fila_mini.pack(fill="x", padx=14, pady=(12, 8))
    lbl_mini = ctk.CTkLabel(fila_mini, text="●  En espera", text_color=C["suave"], height=18, font=ctk.CTkFont(size=12))
    lbl_mini.pack(side="left")
    lbl_mini_pct = ctk.CTkLabel(fila_mini, text="0%", text_color=C["texto"], height=18,
                                font=ctk.CTkFont(family=DISPLAY, size=13))
    lbl_mini_pct.pack(side="right")
    mini_barra = BarraNeon(mini, 4, C["tarjeta"])
    mini_barra.pack(fill="x", padx=px(14), pady=(0, px(14)))

    # ── Página: Traducir ──
    p = PAGINAS["traducir"][0]
    encabezado(p, "Traducir modpack", "Elige tu modpack y el idioma. Babel protege los códigos y los nombres de los mods.")
    c = tarjeta(p)
    etiqueta(c, "CARPETA DEL MODPACK")
    fila_ruta = ctk.CTkFrame(c, fg_color="transparent")
    fila_ruta.pack(fill="x")
    entrada_ruta = campo(fila_ruta, placeholder_text="C:/.../Instances/Mi Modpack")
    entrada_ruta.pack(side="left", fill="x", expand=True)
    entrada_ruta.bind("<KeyRelease>", validar_ruta)
    boton_suave(fila_ruta, "Examinar", elegir_carpeta, width=100, height=40).pack(side="left", padx=(8, 0))
    lbl_ruta = ctk.CTkLabel(c, text="", height=18, anchor="w", font=ctk.CTkFont(size=12))
    lbl_ruta.pack(fill="x", pady=(6, 0))
    etiqueta(c, "IDIOMA DE DESTINO", pady=(14, 8))
    combo_idioma = ctk.CTkComboBox(c, values=list(IDIOMAS.keys()), state="readonly", height=40, corner_radius=10,
                                   fg_color=C["campo"], border_color=C["borde"], button_color=C["boton"],
                                   button_hover_color=C["boton_hover"], text_color=C["texto"],
                                   dropdown_fg_color=C["tarjeta"], dropdown_hover_color=C["boton_hover"],
                                   dropdown_text_color=C["texto"])
    combo_idioma.pack(fill="x")
    combo_idioma.set(cfg.get("idioma") if cfg.get("idioma") in IDIOMAS else "Español (México)")

    h = tarjeta(p)
    arriba = ctk.CTkFrame(h, fg_color="transparent")
    arriba.pack(fill="x")
    lbl_pct = TextoNeon(arriba, "0%", 64, C["cian"], C["tarjeta"], 230, 84)
    lbl_pct.pack(side="left")
    info = ctk.CTkFrame(arriba, fg_color="transparent")
    info.pack(side="left", fill="x", expand=True, padx=(12, 0))
    etiqueta(info, "PROGRESO", pady=(0, 4))
    lbl_estado = ctk.CTkLabel(info, text="Listo para empezar", text_color=C["suave"], anchor="w", justify="left",
                              wraplength=480, font=ctk.CTkFont(size=13))
    lbl_estado.pack(fill="x")
    fila_chips = ctk.CTkFrame(info, fg_color="transparent")
    fila_chips.pack(fill="x", pady=(8, 0))
    chips = {}
    for nombre in ("DeepL", "LibreTranslate", "Microsoft", "Google"):
        chips[nombre] = [ctk.CTkLabel(fila_chips, text=f"●  {nombre}", height=26, corner_radius=13, font=ctk.CTkFont(size=12))]
        chips[nombre][0].pack(side="left", padx=(0, 8))
    barra = BarraNeon(h, 10, C["tarjeta"])
    barra.pack(fill="x", pady=(px(14), px(18)))
    fila_stats = ctk.CTkFrame(h, fg_color="transparent")
    fila_stats.pack(fill="x")
    stats = {}
    for i, (clave, nombre, color) in enumerate((("nuevas", "NUEVAS", C["cian"]), ("cache", "DE MEMORIA", C["morado"]),
                                                 ("fallidas", "SIN TRADUCIR", C["mal"]))):
        fila_stats.grid_columnconfigure(i, weight=1, uniform="stats")
        caja = ctk.CTkFrame(fila_stats, fg_color=C["campo"], corner_radius=12, border_width=1, border_color=C["borde"])
        caja.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 12, 0))
        tk.Frame(caja, bg=color, height=px(3), width=px(28)).pack(anchor="w", padx=px(16), pady=(px(14), 0))
        stats[clave] = ctk.CTkLabel(caja, text="0", text_color=C["texto"], height=34, font=ctk.CTkFont(family=DISPLAY, size=28))
        stats[clave].pack(anchor="w", padx=16, pady=(6, 0))
        ctk.CTkLabel(caja, text=nombre, text_color=C["suave"], height=16,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(0, 14))
    # la fila de botones va en el borde de la tarjeta para que el brillo quepa sin descuadrar el botón
    acciones = ctk.CTkFrame(h.master, fg_color="transparent")
    acciones.pack(fill="x", padx=12, pady=(0, 10))
    btn_inicio = BotonNeon(acciones, "▶  TRADUCIR", boton_iniciar, C["tarjeta"])
    btn_inicio.pack(side="left", fill="x", expand=True)
    btn_stop = ctk.CTkButton(acciones, text="■  Detener", height=52, width=140, corner_radius=14, state="disabled",
                             command=boton_detener, fg_color="transparent", border_width=1,
                             border_color=C["borde"], text_color=C["peligro"], hover_color=C["peligro_fondo"],
                             text_color_disabled=C["tenue"], font=ctk.CTkFont(size=14))
    btn_stop.pack(side="left", padx=(2, 10))

    # ── Página: Motores ──
    p = PAGINAS["motores"][0]
    encabezado(p, "Motores de traducción", "Babel reparte el trabajo entre varios motores. Si uno falla o se bloquea, "
                                           "sigue con los demás.")
    estados = {}
    c = tarjeta_motor(p, "DeepL", "La mejor calidad. Gratis: 500 000 caracteres al mes con tu clave.")
    fila_api = ctk.CTkFrame(c, fg_color="transparent")
    fila_api.pack(fill="x")
    entrada_api = campo(fila_api, show="•", placeholder_text="Pega tu clave (termina en :fx)")
    entrada_api.pack(side="left", fill="x", expand=True)
    btn_ojo = boton_suave(fila_api, "👁", alternar_clave, width=40, height=40)
    btn_ojo.pack(side="left", padx=(8, 0))
    boton_suave(fila_api, "Conseguir clave", lambda: webbrowser.open(URL_DEEPL), width=130, height=40).pack(side="left", padx=(8, 0))
    var_recordar = tk.BooleanVar(value=bool(cfg.get("deepl_key")))
    opcion(c, "Recordar mi clave en este equipo", var_recordar)
    c = tarjeta_motor(p, "LibreTranslate", "Traductor local en tu PC: gratis, rápido y sin límites. Opcional.")
    fila_libre = ctk.CTkFrame(c, fg_color="transparent")
    fila_libre.pack(fill="x")
    entrada_libre = campo(fila_libre, placeholder_text=LIBRE_POR_DEFECTO)
    entrada_libre.pack(side="left", fill="x", expand=True)
    boton_suave(fila_libre, "Cómo instalarlo", lambda: webbrowser.open(URL_LIBRE), width=130, height=40).pack(side="left", padx=(8, 0))
    entrada_libre.insert(0, cfg.get("libre_url") or LIBRE_POR_DEFECTO)
    fila = ctk.CTkFrame(p, fg_color="transparent")
    fila.pack(fill="x")
    tarjeta_motor(fila, "Microsoft", "Gratis y sin clave.", side="left", fill="both", expand=True, padx=(0, 8), pady=0)
    tarjeta_motor(fila, "Google", "Gratis y sin clave.", side="left", fill="both", expand=True, padx=(8, 0), pady=0)
    for nombre in chips:
        pintar_motor(nombre)

    # ── Página: Registro ──
    p = PAGINAS["registro"][0]
    fila = encabezado(p, "Registro", "Todo lo que hace Babel, paso a paso.")
    btn_copiar = ctk.CTkButton(fila, text="Copiar", width=100, height=34, corner_radius=10, command=copiar_registro,
                               fg_color=C["boton"], hover_color=C["boton_hover"], text_color=C["suave"],
                               font=ctk.CTkFont(size=12))
    btn_copiar.pack(side="right")
    txt = ctk.CTkTextbox(p, fg_color=C["consola"], text_color=C["consola_txt"], corner_radius=14, border_width=1,
                         border_color=C["borde"], border_spacing=14, scrollbar_button_color=C["borde"],
                         scrollbar_button_hover_color=C["borde_hover"],
                         font=ctk.CTkFont(family="Consolas", size=13), wrap="word")
    txt.pack(fill="both", expand=True)
    for tag, color in (("ok", C["ok"]), ("aviso", C["aviso"]), ("error", C["mal"]), ("tenue", C["tenue"])):
        txt.tag_config(tag, foreground=color)
    txt.insert("end", "Elige tu modpack y pulsa Traducir. Aquí verás todo lo que va pasando.\n", "tenue")

    # ── Página: Ajustes ──
    p = PAGINAS["ajustes"][0]
    encabezado(p, "Ajustes", "Cómo se instala la traducción y qué textos se incluyen.")
    c = tarjeta(p)
    var_instalar = tk.BooleanVar(value=cfg.get("instalar", True))
    opcion_grande(c, "Instalar en el modpack", "Copia la traducción dentro del modpack y guarda una copia de seguridad "
                                               "de los archivos originales.", var_instalar)
    tk.Frame(c, height=1, bg=C["borde"]).pack(fill="x", pady=px(16))
    var_todo = tk.BooleanVar(value=cfg.get("incluir_todo", False))
    opcion_grande(c, "Incluir textos de otros mods", "Además de las misiones, traduce textos de otros mods. "
                                                     "Usa más cuota de los traductores.", var_todo)
    c = tarjeta(p)
    etiqueta(c, "CARPETA DE RESULTADOS")
    fila = ctk.CTkFrame(c, fg_color="transparent")
    fila.pack(fill="x")
    ruta_resultados = os.path.join(RUTA_SALIDA_FIJA, "_traducido")
    ctk.CTkLabel(fila, text=ruta_resultados, text_color=C["texto"], anchor="w",
                 font=ctk.CTkFont(family="Consolas", size=12)).pack(side="left", fill="x", expand=True)
    boton_suave(fila, "📂  Abrir", lambda: abrir_carpeta(ruta_resultados), width=110, height=36).pack(side="right")

    if cfg.get("carpeta"):
        entrada_ruta.insert(0, cfg["carpeta"])
        validar_ruta()
    if cfg.get("deepl_key"):
        entrada_api.insert(0, cfg["deepl_key"])

    navegar("traducir")
    bombear()
    animar()
    app.mainloop()