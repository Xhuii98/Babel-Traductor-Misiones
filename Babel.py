import os
import re
import sys
import json
import time
import queue
import random
import threading
import shutil
import hashlib
import subprocess
import zipfile
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

VERSION = "1.1.0"
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
        self.motores.append(Motor(
            "Google",
            lambda t: GoogleTranslator(source="auto", target=lang["google"]).translate(t),
            0.5))
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
        for nombre, tam in (("LibreTranslate", 20), ("Google", 1)):
            m = self.motor(nombre)
            if m and m.disponible():
                fn = self._libre if nombre == "LibreTranslate" else (lambda ts, m=m: [m.fn(ts[0])])
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


def extraer_textos(contenido, modo_lang=False):
    textos = set()
    contexto = {} if modo_lang else contexto_listas(contenido)
    for m in RE_CADENA.finditer(contenido):
        if not cadena_permitida(m, contexto, modo_lang):
            continue
        valor = m.group(2)
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


def procesar_archivo(ruta, destino, traductor, idioma, indice=0, total=1, modo_lang=False):
    with open(ruta, "r", encoding="utf-8") as f:
        contenido = f.read()

    mapa, fallidas = resolver_textos(extraer_textos(contenido, modo_lang), traductor, idioma,
                                     os.path.basename(ruta), indice, total)

    contexto = {} if modo_lang else contexto_listas(contenido)

    def replacer(match):
        clave, valor_orig, todo = match.group(1), match.group(2), match.group(0)
        if not cadena_permitida(match, contexto, modo_lang) or not es_texto_traducible(valor_orig):
            return todo
        nuevo = reconstruir(mapa, separar_protegidos(valor_orig))
        return f'{clave if clave else ""}"{nuevo}"'

    nuevo_contenido = RE_CADENA.sub(replacer, contenido)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        f.write(nuevo_contenido)
    return fallidas


def procesar_json(ruta, destino, traductor, idioma, indice=0, total=1):
    with open(ruta, "r", encoding="utf-8-sig") as f:
        datos = json.load(f)
    if not isinstance(datos, dict):
        raise ValueError("no parece un archivo de idioma (se esperaba un objeto JSON)")

    mapa, fallidas = resolver_textos(extraer_textos_json(datos), traductor, idioma,
                                     os.path.basename(ruta), indice, total)
    salida = {}
    for clave, valor in datos.items():
        if valor_json_traducible(valor):
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
    cand = os.path.join(ruta, "config", "ftbquests", "quests")
    return cand if os.path.isdir(cand) else ruta


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
    misiones, candidatos = [], set()
    raiz_q = carpeta_misiones(ruta_entrada)
    for r, files in recorrer(raiz_q, IGNORAR_CARPETAS | PODAR_INSTANCIA):
        for f in files:
            ruta = os.path.join(r, f)
            en_lang = "lang" in ruta.replace("\\", "/").lower().split("/")[:-1]
            if f.endswith(".snbt") and f not in IGNORAR_ARCHIVOS and not en_lang:
                misiones.append(ruta)
                nombre = f.replace(".snbt", "").replace("_", " ").title()
                if "Ae2" in nombre:
                    nombre = "AE2"
                if "Rftools" in nombre:
                    nombre = "RFTools"
                candidatos.add(nombre)
                if nombre.endswith("s"):
                    candidatos.add(nombre[:-1])

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
            with open(origenes.get(a, a), "r", encoding="utf-8") as fh:
                encontradas = RE_REFERENCIA_CLAVE.findall(fh.read())
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
            elif fl.endswith(".snbt") and es_lang_snbt(ruta):
                rel = "ftbquests" in ruta.lower()
                idiomas.append({"ruta": ruta, "tipo": "snbt", "relevante": rel, "tam": tam,
                                "motivo": "idioma nativo de FTB Quests" if rel else "no parece de misiones"})
    hay_snbt_lang = any(l["tipo"] == "snbt" and l["relevante"] for l in idiomas)
    faltan = referencias - cubiertas
    if faltan and not hay_snbt_lang:
        idiomas += buscar_en_empaquetados(raiz_instancia(ruta_entrada), set(faltan))
    return {"misiones": misiones, "candidatos": candidatos, "lang": idiomas, "n_refs": n_refs, "origenes": origenes,
            "estructurados": estructurados}


def mapear_ruta(ruta, lang, es_lang):
    carpeta, nombre = os.path.split(ruta)
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
                for t in textos_de_archivo(origenes.get(a, a), estructurados.get(a)):
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
                    log("⚠️ Puede que no alcance la cuota de DeepL; el resto pasará a LibreTranslate/Google.")

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
            try:
                if tipo:
                    sin_traducir = procesar_estructurado(src, dest, traductor, idioma, tipo, i, total)
                elif es_json:
                    sin_traducir = procesar_json(src, dest, traductor, idioma, i, total)
                else:
                    sin_traducir = procesar_archivo(src, dest, traductor, idioma, i, total, modo_lang=es_lang_snbt(a))
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


C = {
    "fondo": "#0F1216", "tarjeta": "#1A1F27", "borde": "#2A313C", "borde_hover": "#38414F",
    "acento": "#4ADE80", "acento_hover": "#22C55E", "texto_acento": "#08210F",
    "texto": "#E6EAF0", "suave": "#9AA4B2",
    "peligro": "#EF4444", "peligro_fondo": "#3A1D1D",
    "consola": "#0B0E12", "consola_txt": "#9BF0B5", "ok": "#4ADE80", "mal": "#F87171",
}
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


def bombear():
    try:
        while True:
            item = COLA.get_nowait()
            tipo = item[0]
            if tipo == "log":
                txt.insert("end", item[1] + "\n")
                txt.see("end")
            elif tipo == "prog":
                barra.set(max(0.0, min(1.0, item[1] / 100)))
                lbl_pct.configure(text=f"{item[1]:.0f}%")
            elif tipo == "estado":
                lbl_estado.configure(text=item[1])
            elif tipo == "motor":
                if item[1] in chips:
                    chips[item[1]].configure(text_color=C["ok"] if item[2] else C["mal"])
            elif tipo == "info":
                messagebox.showinfo(item[1], item[2])
            elif tipo == "error":
                messagebox.showerror(item[1], item[2])
            elif tipo == "fin":
                btn_inicio.configure(state="normal")
                btn_stop.configure(state="disabled")
                lbl_estado.configure(text="Listo para empezar")
    except queue.Empty:
        pass
    app.after(100, bombear)


def elegir_carpeta():
    ruta = filedialog.askdirectory(title="Carpeta de misiones (.snbt)")
    if ruta:
        entrada_ruta.delete(0, "end")
        entrada_ruta.insert(0, ruta)


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
    barra.set(0)
    lbl_pct.configure(text="0%")
    for chip in chips.values():
        chip.configure(text_color=C["suave"])
    btn_inicio.configure(state="disabled")
    btn_stop.configure(state="normal")
    lbl_estado.configure(text="Probando motores de traducción...")
    threading.Thread(target=iniciar_proceso, args=(ruta, lang, api, bool(var_instalar.get()), bool(var_todo.get()), libre),
                     daemon=True).start()


def boton_detener():
    DETENER.set()
    log("⏳ Deteniendo...")


def tarjeta(padre, numero, titulo, subtitulo):
    marco = ctk.CTkFrame(padre, fg_color=C["tarjeta"], corner_radius=14, border_width=1, border_color=C["borde"])
    marco.pack(fill="x", pady=(0, 12))
    cab = ctk.CTkFrame(marco, fg_color="transparent")
    cab.pack(fill="x", padx=16, pady=(14, 8))
    ctk.CTkLabel(cab, text=str(numero), width=28, height=28, corner_radius=14, fg_color=C["acento"],
                 text_color=C["texto_acento"], font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
    col = ctk.CTkFrame(cab, fg_color="transparent")
    col.pack(side="left", padx=10)
    ctk.CTkLabel(col, text=titulo, text_color=C["texto"], anchor="w",
                 font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w")
    ctk.CTkLabel(col, text=subtitulo, text_color=C["suave"], anchor="w",
                 font=ctk.CTkFont(size=12)).pack(anchor="w")
    cuerpo = ctk.CTkFrame(marco, fg_color="transparent")
    cuerpo.pack(fill="x", padx=16, pady=(0, 14))
    return cuerpo


def boton_suave(padre, texto, comando, **kw):
    return ctk.CTkButton(padre, text=texto, command=comando, fg_color=C["borde"], hover_color=C["borde_hover"],
                         text_color=C["texto"], corner_radius=10, **kw)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = ctk.CTk(fg_color=C["fondo"])
    app.title(f"{NOMBRE_APP} {VERSION}")
    base_recursos = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    icono = os.path.join(base_recursos, "icono.ico")
    if os.path.isfile(icono) and sys.platform == "win32":
        try:
            app.iconbitmap(icono)
            app.after(300, lambda: app.iconbitmap(icono))
        except Exception:
            pass
    app.geometry("1080x700")
    app.minsize(980, 640)

    cfg = cargar_config()

    cab = ctk.CTkFrame(app, fg_color="transparent")
    cab.pack(fill="x", padx=24, pady=(18, 12))
    fila_titulo = ctk.CTkFrame(cab, fg_color="transparent")
    fila_titulo.pack(anchor="w")
    logo_png = os.path.join(base_recursos, "icono.png")
    if os.path.isfile(logo_png):
        try:
            app.logo_img = tk.PhotoImage(file=logo_png)
            tk.Label(fila_titulo, image=app.logo_img, bg=C["fondo"], bd=0).pack(side="left", padx=(0, 12))
        except Exception:
            pass
    ctk.CTkLabel(fila_titulo, text=NOMBRE_APP, text_color=C["texto"],
                 font=ctk.CTkFont(size=30, weight="bold")).pack(side="left")
    ctk.CTkLabel(cab, text="Todas las misiones, todos los idiomas. Traduce los libros de misiones de tus modpacks "
                           "protegiendo códigos y nombres de mods.",
                 text_color=C["suave"], font=ctk.CTkFont(size=13)).pack(anchor="w", pady=(4, 0))

    cuerpo = ctk.CTkFrame(app, fg_color="transparent")
    cuerpo.pack(fill="both", expand=True, padx=24, pady=(0, 20))
    cuerpo.grid_columnconfigure(0, weight=0, minsize=440)
    cuerpo.grid_columnconfigure(1, weight=1)
    cuerpo.grid_rowconfigure(0, weight=1)

    izq = ctk.CTkScrollableFrame(cuerpo, fg_color="transparent", width=420)
    izq.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
    der = ctk.CTkFrame(cuerpo, fg_color=C["tarjeta"], corner_radius=14, border_width=1, border_color=C["borde"])
    der.grid(row=0, column=1, sticky="nsew")

    c1 = tarjeta(izq, 1, "Carpeta del modpack", "La de la instancia: donde están config, mods, kubejs...")
    entrada_ruta = ctk.CTkEntry(c1, height=38, placeholder_text="C:/.../Instances/Mi Modpack",
                                fg_color=C["fondo"], border_color=C["borde"])
    entrada_ruta.pack(side="left", fill="x", expand=True)
    boton_suave(c1, "Examinar", elegir_carpeta, width=92, height=38).pack(side="left", padx=(8, 0))

    c2 = tarjeta(izq, 2, "Idioma de destino", "Elige a qué idioma quieres traducir")
    combo_idioma = ctk.CTkComboBox(c2, values=list(IDIOMAS.keys()), state="readonly", height=38,
                                   fg_color=C["fondo"], border_color=C["borde"], button_color=C["borde"],
                                   button_hover_color=C["borde_hover"], dropdown_fg_color=C["tarjeta"],
                                   dropdown_hover_color=C["borde"])
    combo_idioma.pack(fill="x")
    combo_idioma.set(cfg.get("idioma") if cfg.get("idioma") in IDIOMAS else "Español (México)")
    var_instalar = tk.BooleanVar(value=cfg.get("instalar", True))
    ctk.CTkCheckBox(c2, text="Instalar en el modpack (con copia de seguridad)", variable=var_instalar,
                    text_color=C["suave"], fg_color=C["acento"], hover_color=C["acento_hover"],
                    checkmark_color=C["texto_acento"], font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(12, 0))
    var_todo = tk.BooleanVar(value=cfg.get("incluir_todo", False))
    ctk.CTkCheckBox(c2, text="Incluir textos de otros mods (usa más cuota)", variable=var_todo,
                    text_color=C["suave"], fg_color=C["acento"], hover_color=C["acento_hover"],
                    checkmark_color=C["texto_acento"], font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(8, 0))

    c3 = tarjeta(izq, 3, "Clave de DeepL (recomendada)", "Gratis: 500 000 caracteres al mes. Sin clave usa LibreTranslate/Google")
    fila_api = ctk.CTkFrame(c3, fg_color="transparent")
    fila_api.pack(fill="x")
    entrada_api = ctk.CTkEntry(fila_api, height=38, show="•", placeholder_text="Pega tu clave (termina en :fx)",
                               fg_color=C["fondo"], border_color=C["borde"])
    entrada_api.pack(side="left", fill="x", expand=True)
    boton_suave(fila_api, "Conseguir clave", lambda: webbrowser.open(URL_DEEPL), width=120, height=38).pack(side="left", padx=(8, 0))
    var_recordar = tk.BooleanVar(value=bool(cfg.get("deepl_key")))
    ctk.CTkCheckBox(c3, text="Recordar mi clave en este equipo", variable=var_recordar, text_color=C["suave"],
                    fg_color=C["acento"], hover_color=C["acento_hover"], checkmark_color=C["texto_acento"],
                    font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(10, 0))

    c4 = tarjeta(izq, 4, "Traductor local (opcional)", "LibreTranslate en tu PC: gratis, rápido y sin límites")
    fila_libre = ctk.CTkFrame(c4, fg_color="transparent")
    fila_libre.pack(fill="x")
    entrada_libre = ctk.CTkEntry(fila_libre, height=38, placeholder_text=LIBRE_POR_DEFECTO,
                                 fg_color=C["fondo"], border_color=C["borde"])
    entrada_libre.pack(side="left", fill="x", expand=True)
    boton_suave(fila_libre, "Cómo instalarlo", lambda: webbrowser.open(URL_LIBRE), width=120, height=38).pack(side="left", padx=(8, 0))
    entrada_libre.insert(0, cfg.get("libre_url") or LIBRE_POR_DEFECTO)

    if cfg.get("carpeta"):
        entrada_ruta.insert(0, cfg["carpeta"])
    if cfg.get("deepl_key"):
        entrada_api.insert(0, cfg["deepl_key"])

    fila = ctk.CTkFrame(izq, fg_color="transparent")
    fila.pack(fill="x", pady=(4, 0))
    btn_inicio = ctk.CTkButton(fila, text="▶  Traducir", height=48, corner_radius=12, command=boton_iniciar,
                               font=ctk.CTkFont(size=16, weight="bold"), fg_color=C["acento"],
                               hover_color=C["acento_hover"], text_color=C["texto_acento"])
    btn_inicio.pack(side="left", fill="x", expand=True)
    btn_stop = ctk.CTkButton(fila, text="■  Detener", height=48, width=120, corner_radius=12, state="disabled",
                             command=boton_detener, fg_color="transparent", border_width=2,
                             border_color=C["peligro"], text_color=C["peligro"], hover_color=C["peligro_fondo"])
    btn_stop.pack(side="left", padx=(10, 0))
    ctk.CTkButton(izq, text="📂  Abrir carpeta de resultados", height=38, corner_radius=10,
                  command=lambda: abrir_carpeta(os.path.join(RUTA_SALIDA_FIJA, "_traducido")),
                  fg_color="transparent", border_width=1, border_color=C["borde"], text_color=C["suave"],
                  hover_color=C["borde"]).pack(fill="x", pady=(10, 0))

    ctk.CTkLabel(der, text="Progreso", text_color=C["texto"],
                 font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=18, pady=(16, 2))
    lbl_estado = ctk.CTkLabel(der, text="Listo para empezar", text_color=C["suave"], anchor="w")
    lbl_estado.pack(fill="x", padx=18)
    fila_barra = ctk.CTkFrame(der, fg_color="transparent")
    fila_barra.pack(fill="x", padx=18, pady=(10, 4))
    barra = ctk.CTkProgressBar(fila_barra, height=14, corner_radius=7, progress_color=C["acento"], fg_color=C["fondo"])
    barra.set(0)
    barra.pack(side="left", fill="x", expand=True)
    lbl_pct = ctk.CTkLabel(fila_barra, text="0%", width=48, text_color=C["texto"], font=ctk.CTkFont(size=13, weight="bold"))
    lbl_pct.pack(side="left", padx=(10, 0))

    fila_chips = ctk.CTkFrame(der, fg_color="transparent")
    fila_chips.pack(fill="x", padx=18, pady=(4, 8))
    ctk.CTkLabel(fila_chips, text="Motores:", text_color=C["suave"], font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
    chips = {}
    for nombre in ("DeepL", "LibreTranslate", "Google"):
        chips[nombre] = ctk.CTkLabel(fila_chips, text=f"● {nombre}", text_color=C["suave"], font=ctk.CTkFont(size=12))
        chips[nombre].pack(side="left", padx=(0, 12))

    ctk.CTkLabel(der, text="Registro", text_color=C["texto"],
                 font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=18, pady=(4, 4))
    txt = ctk.CTkTextbox(der, fg_color=C["consola"], text_color=C["consola_txt"], corner_radius=10,
                         font=ctk.CTkFont(family="Consolas", size=12), wrap="word")
    txt.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    bombear()
    app.mainloop()
