#!/usr/bin/env python3
"""
Monitor Legislativo Uruguay — Script de actualización automática.
Consulta parlamento.gub.uy, detecta novedades, actualiza data/legislative_data.json
y regenera index.html con los datos embebidos.

Diseñado para correr en GitHub Actions (cron diario) o manualmente.
"""

import json
import re
import sys
import os
import urllib.request
import urllib.error
from html.parser import HTMLParser
from datetime import datetime

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "legislative_data.json")
HTML_FILE = os.path.join(os.path.dirname(__file__), "..", "index.html")

# ============================================================
# 1. SCRAPER — Obtener leyes promulgadas de parlamento.gub.uy
# ============================================================

class LeyesTableParser(HTMLParser):
    """Parsea la tabla de leyes promulgadas del parlamento."""
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.current_cell = ""
        self.rows = []
        self.cell_index = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            self.in_table = True
        elif tag == "tbody" and self.in_table:
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_row = True
            self.current_row = []
            self.cell_index = 0
        elif tag == "td" and self.in_row:
            self.in_cell = True
            self.current_cell = ""
            self.cell_index += 1

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.in_cell = False
            self.current_row.append(self.current_cell.strip())
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "table":
            self.in_table = False

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


def fetch_page(url):
    """Descarga una página web."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; MonitorLegislativoUY/1.0)"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        print(f"  Error al acceder a {url}: {e}")
        return None


def parse_leyes_page(html_content):
    """Extrae leyes de la tabla HTML del parlamento."""
    parser = LeyesTableParser()
    parser.feed(html_content)

    leyes = []
    for row in parser.rows:
        if len(row) < 5:
            continue
        # Columnas: Número | Promulgación | Texto Original | Texto Actualizado | Título | Asunto | ...
        numero_raw = row[0].strip()
        fecha = row[1].strip()
        titulo = row[4].strip() if len(row) > 4 else ""
        asunto = row[5].strip() if len(row) > 5 else ""

        if not numero_raw or not numero_raw.isdigit():
            continue

        leyes.append({
            "numero_ley": int(numero_raw),
            "numero": f"Ley {numero_raw}",
            "fecha": fecha,
            "titulo": titulo,
            "asunto": asunto,
            "tipo": "Ley Promulgada",
            "tramite": "Promulgada",
            "fuente": "Parlamento"
        })

    return leyes


def scrape_leyes_promulgadas():
    """Obtiene todas las leyes promulgadas del parlamento (todas las páginas)."""
    all_leyes = []
    page = 0

    while True:
        url = f"https://parlamento.gub.uy/documentosyleyes/leyes?page={page}"
        print(f"  Consultando {url}...")
        html = fetch_page(url)
        if not html:
            break

        leyes = parse_leyes_page(html)
        if not leyes:
            break

        all_leyes.extend(leyes)
        print(f"  Página {page}: {len(leyes)} leyes encontradas")

        # Verificar si hay más páginas
        if f"page={page + 1}" in html:
            page += 1
        else:
            break

    print(f"  Total leyes del parlamento: {len(all_leyes)}")
    return all_leyes


# ============================================================
# 2. CLASIFICACIÓN Y RESUMEN
# ============================================================

# Categorías con palabras clave
CATEGORY_RULES = [
    (["presupuesto", "rendición de cuentas", "ejecución presupuestal"], "Presupuesto", True),
    (["impuesto", "tributar", "imposición", "fiscal", "evasión", "irae", "iva"], "Tributario", True),
    (["comercio", "mercosur", "libre comercio", "arancel", "exporta"], "Comercio Internacional", True),
    (["trabajo", "empleo", "desempleo", "subsidio por desempleo", "laboral", "trabajador"], "Trabajo y Empleo", True),
    (["banco", "financier", "crédito", "fondo de garantía", "hipotecario", "consumidor"], "Sector Financiero", True),
    (["inversión", "inversiones", "fogade", "comap", "incentivo"], "Inversiones", True),
    (["energía", "combustible", "fronteriza", "zona franca"], "Energía", True),
    (["transporte", "radar", "vial", "tránsito"], "Transporte", True),
    (["salud", "médic", "nutricional", "vitamina", "bioética", "alimentación", "gluten"], "Salud", False),
    (["pensión graciable"], "General", False),
    (["jubilación", "pensión", "retiro", "cjppu", "previsional"], "Seguridad Social", False),
    (["defensa", "militar", "ejército", "armada", "buque rou", "operación", "ingreso al país", "salida pais", "antark"], "Defensa", False),
    (["discapacidad", "protección social", "violencia"], "Derechos y Protección Social", False),
    (["matrimonio", "racismo", "discriminación", "derechos civil"], "Derechos Civiles", False),
    (["extradición", "convención", "convenio", "naciones unidas", "tratado"], "Relaciones Internacionales", False),
    (["denominación", "liceo", "escuela", "designa"], "Denominaciones y Homenajes", False),
    (["conmemoración", "feriado", "aniversario", "día nacional", "día de", "capital nacional"], "Conmemoraciones", False),
    (["audiovisual", "cultura", "patrimonio"], "Cultura e Industria", False),
    (["inmueble", "transferencia", "construcción", "cesantía"], "Construcción e Inmuebles", False),
    (["tecnología", "digital", "inteligencia artificial", "ciber"], "Tecnología", True),
    (["plataforma", "lavado de activos", "criptoactivo"], "Seguridad Financiera", True),
]


def classify_item(titulo):
    """Clasifica un item legislativo por categoría e impacto económico."""
    titulo_lower = titulo.lower()
    for keywords, category, economic in CATEGORY_RULES:
        for kw in keywords:
            if kw in titulo_lower:
                return category, economic
    return "General", False


def generate_resumen(item):
    """Genera un resumen breve basado en el título y tipo."""
    titulo = item.get("titulo", "")
    tipo = item.get("tipo", "")
    categoria = item.get("categoria", "")
    t = titulo.lower()

    # Resúmenes específicos para items conocidos
    if "presupuesto nacional" in t and "2025" in t:
        return "Presupuesto quinquenal del gobierno 2025-2029. Establece las asignaciones presupuestales para todo el período de gobierno."
    if "rendición de cuentas" in t:
        return "Rendición de cuentas del ejercicio fiscal anterior. Incluye disposiciones sobre resultado fiscal y partidas extraordinarias."
    if "mercosur" in t and ("comercio" in t or "unión europea" in t or "ue" in t):
        return "Aprobación de acuerdo comercial en el marco del Mercosur. Impacta el comercio exterior del país."
    if "subsidio por desempleo" in t or "seguro desempleo" in t:
        empresa = re.search(r'(?:empresa\s+)?([A-Z][A-Z\s\.]+S\.A\.)', titulo)
        if empresa:
            return f"Extensión del subsidio por desempleo para los trabajadores de {empresa.group(1).strip()}. Medida de protección laboral."
        return "Extensión del subsidio por desempleo para trabajadores de una empresa en dificultades."
    if "pensión graciable" in t:
        return "Otorgamiento de pensión graciable por servicios eminentes prestados al país."
    if "denominación" in t or "denominacion" in t or "designa" in t.split(".")[0].lower():
        return f"Designación oficial de un bien público o espacio en homenaje. {titulo[:150]}."
    if "feriado" in t or "conmemoración" in t or "día nacional" in t or "día de" in t.split(".")[0].lower():
        return f"Declaración conmemorativa o establecimiento de efeméride. {titulo[:150]}."
    if "autorización" in t and ("ingreso" in t or "salida" in t) and ("buque" in t or "militar" in t or "ejército" in t or "armada" in t):
        return "Autorización de ingreso o salida de personal/equipamiento militar, en el marco de cooperación internacional o ejercicios conjuntos."
    if "doble imposición" in t or "evasión fiscal" in t:
        return f"Convenio internacional para evitar doble imposición y prevenir evasión fiscal. {titulo[:120]}."
    if "transferencia" in t and "inmueble" in t:
        return "Transferencia de inmuebles del patrimonio del Estado a gobiernos departamentales o instituciones públicas."

    # Genérico basado en categoría
    if len(titulo) < 120:
        return titulo + "."
    return titulo[:200] + "..."


def generate_url(item):
    """Genera la URL correcta para un item legislativo."""
    numero = item.get("numero", "")
    tipo = item.get("tipo", "")
    asunto = item.get("asunto", "")

    # Leyes promulgadas
    ley_match = re.search(r"Ley\s*(\d+)", numero)
    if ley_match:
        return f"https://parlamento.gub.uy/documentosyleyes/leyes/ley/{ley_match.group(1)}"

    # Decretos
    decreto_match = re.search(r"(\d+)/(\d+)", numero)
    if "decreto" in tipo.lower() and decreto_match:
        return f"https://www.impo.com.uy/bases/decretos/{decreto_match.group(1)}-{decreto_match.group(2)}"

    # Fichas de asunto
    if asunto and asunto.isdigit():
        return f"https://parlamento.gub.uy/documentosyleyes/ficha-asunto/{asunto}"

    asunto_match = re.search(r"Asunto\s*(\d+)", numero)
    if asunto_match:
        return f"https://parlamento.gub.uy/documentosyleyes/ficha-asunto/{asunto_match.group(1)}"

    # Carpetas
    carpeta_match = re.search(r"Carpeta\s*(\d+)", numero)
    if carpeta_match:
        return f"https://parlamento.gub.uy/documentosyleyes/ficha-asunto/{carpeta_match.group(1)}"

    return "https://parlamento.gub.uy/documentosyleyes"


# ============================================================
# 3. MERGE Y ACTUALIZACIÓN
# ============================================================

def load_current_data():
    """Carga los datos actuales del JSON."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_data(data):
    """Guarda los datos actualizados."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def merge_new_leyes(current_data, scraped_leyes):
    """Identifica y agrega leyes nuevas que no están en el dataset actual."""
    # Build set of existing law numbers
    existing_nums = set()
    for item in current_data:
        num = item.get("numero", "")
        # Extract just the number for comparison
        m = re.search(r"(\d{5})", num)
        if m:
            existing_nums.add(m.group(1))

    new_items = []
    for ley in scraped_leyes:
        ley_num = str(ley["numero_ley"])
        if ley_num not in existing_nums:
            categoria, economico = classify_item(ley["titulo"])
            item = {
                "tipo": ley["tipo"],
                "numero": ley["numero"],
                "fecha": ley["fecha"],
                "titulo": ley["titulo"],
                "categoria": categoria,
                "economico": economico,
                "tramite": ley["tramite"],
                "fuente": ley["fuente"],
                "asunto": ley.get("asunto", "")
            }
            item["resumen"] = generate_resumen(item)
            item["url"] = generate_url(item)
            new_items.append(item)

    return new_items


# ============================================================
# 4. REBUILD HTML
# ============================================================

def rebuild_html(data):
    """Actualiza el const DATA en index.html con los datos actuales."""
    if not os.path.exists(HTML_FILE):
        print(f"  ERROR: No se encontró {HTML_FILE}")
        return False

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Reemplazar const DATA
    data_json = json.dumps(data, ensure_ascii=False)
    match = re.search(r"^const DATA = \[.*\];$", html, re.MULTILINE)
    if not match:
        print("  ERROR: No se encontró 'const DATA' en index.html")
        return False

    html = html.replace(match.group(0), f"const DATA = {data_json};")

    # Actualizar conteo de items en el subtítulo
    html = re.sub(
        r"Universo completo de actividad normativa — \d+ items legislativos",
        f"Universo completo de actividad normativa — {len(data)} items legislativos",
        html
    )

    # Actualizar fecha
    now = datetime.now()
    meses = ["enero","febrero","marzo","abril","mayo","junio",
             "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    fecha_str = f"{now.day} de {meses[now.month-1]} de {now.year}"
    html = re.sub(r"Actualizado al \d+ de \w+ de \d+", f"Actualizado al {fecha_str}", html)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    return True


# ============================================================
# 5. MAIN
# ============================================================

def main():
    print("=" * 60)
    print("Monitor Legislativo Uruguay — Actualización")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. Cargar datos actuales
    print("\n1. Cargando datos actuales...")
    current_data = load_current_data()
    print(f"   Items actuales: {len(current_data)}")

    # 2. Scraping del parlamento
    print("\n2. Consultando parlamento.gub.uy...")
    scraped_leyes = scrape_leyes_promulgadas()

    if not scraped_leyes:
        print("   No se pudieron obtener datos del parlamento. Abortando.")
        sys.exit(1)

    # 3. Detectar novedades
    print("\n3. Buscando novedades...")
    new_items = merge_new_leyes(current_data, scraped_leyes)

    if not new_items:
        print("   No hay leyes nuevas. Sin cambios.")
        sys.exit(0)

    print(f"   ¡{len(new_items)} ley(es) nueva(s) encontrada(s)!")
    for item in new_items:
        print(f"     - {item['numero']}: {item['titulo'][:70]}...")

    # 4. Agregar nuevas al inicio del dataset
    updated_data = new_items + current_data
    save_data(updated_data)
    print(f"\n4. Datos guardados: {len(updated_data)} items totales")

    # 5. Rebuild HTML
    print("\n5. Actualizando index.html...")
    if rebuild_html(updated_data):
        print("   index.html actualizado correctamente.")
    else:
        print("   ERROR al actualizar index.html")
        sys.exit(1)

    # 6. Output para GitHub Actions
    # Crear summary para el commit message
    resumen = ", ".join([item["numero"] for item in new_items])
    print(f"\n✓ Actualización completada: +{len(new_items)} items ({resumen})")

    # Set output for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_changes=true\n")
            f.write(f"new_count={len(new_items)}\n")
            f.write(f"total_count={len(updated_data)}\n")
            f.write(f"summary=+{len(new_items)} leyes: {resumen}\n")


if __name__ == "__main__":
    main()
