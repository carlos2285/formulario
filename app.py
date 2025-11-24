import streamlit as st
from PIL import Image
import pytesseract
import re
from datetime import datetime

st.set_page_config(page_title="Formulario DUI + Datos de Pago", layout="centered")

st.title("Captura de datos desde DUI (El Salvador)")
st.write(
    "1) Sube las imágenes del **frente** y **reverso** del DUI (nuevo o antiguo).\n"
    "2) La aplicación intentará leer automáticamente los datos que vienen en el documento.\n"
    "3) Completa el resto de información manualmente."
)

# ---------------------------------------------------------
# Utilidades de preprocesamiento
# ---------------------------------------------------------
def preparar_imagen(img: Image.Image) -> Image.Image:
    # Rota si viene vertical y pasa a escala de grises
    if img.height > img.width:
        img = img.rotate(90, expand=True)
    img = img.convert("L")
    return img


def convertir_fecha_mrz(fecha6: str):
    # Convierte fecha YYMMDD de MRZ a dd/mm/yyyy (aprox).
    try:
        yy = int(fecha6[0:2])
        mm = int(fecha6[2:4])
        dd = int(fecha6[4:6])
        if yy >= 50:
            yyyy = 1900 + yy
        else:
            yyyy = 2000 + yy
        dt = datetime(yyyy, mm, dd)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return None


# ---------------------------------------------------------
# Lectura de MRZ (reverso)
# ---------------------------------------------------------
def parsear_mrz(texto: str) -> dict:
    # Parsear MRZ del reverso para extraer nombre, número, fechas, sexo
    datos = {
        "numero_doc": None,
        "fecha_nacimiento": None,
        "fecha_expiracion": None,
        "sexo": None,
        "apellidos": None,
        "nombres": None,
    }

    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    if len(lineas) < 2:
        return datos

    mrz = lineas[-3:]

    # Línea 1: IDSLV + número
    l1 = mrz[0]
    m_doc = re.search(r"ID[ A-Z]{2,3}([0-9A-Z<]{8,12})", l1)
    if m_doc:
        numero_doc = m_doc.group(1).replace("<", "")
        datos["numero_doc"] = numero_doc

    # Línea 2: fecha nacimiento, sexo, fecha expiración
    if len(mrz) >= 2:
        l2 = mrz[1].replace(" ", "")
        m_nac = re.search(r"(\d{6})[MF<]", l2)
        if m_nac:
            datos["fecha_nacimiento"] = convertir_fecha_mrz(m_nac.group(1))

        m_sexo = re.search(r"\d{6}([MF<])", l2)
        if m_sexo:
            s = m_sexo.group(1)
            if s in ("M", "F"):
                datos["sexo"] = s

        m_exp = re.search(r"\d{6}[MF<](\d{6})", l2)
        if m_exp:
            datos["fecha_expiracion"] = convertir_fecha_mrz(m_exp.group(1))

    # Línea 3: apellidos y nombres
    if len(mrz) >= 3:
        l3 = mrz[2]
        partes = l3.split("<<")
        if len(partes) >= 2:
            apellidos_raw = partes[0]
            nombres_raw = "<<".join(partes[1:])
            datos["apellidos"] = apellidos_raw.replace("<", " ").strip()
            datos["nombres"] = nombres_raw.replace("<", " ").strip()

    return datos


# ---------------------------------------------------------
# OCR reverso: dirección, residencia, etc.
# ---------------------------------------------------------
def extraer_desde_reverso(img: Image.Image) -> dict:
    datos = {}

    img_prep = preparar_imagen(img)
    texto_completo = pytesseract.image_to_string(img_prep, lang="spa+eng")
    datos["texto_reverso_raw"] = texto_completo

    # Recorte MRZ (parte inferior)
    w, h = img_prep.size
    mrz_region = img_prep.crop((0, int(h * 0.6), w, h))
    texto_mrz = pytesseract.image_to_string(mrz_region, lang="eng")
    datos_mrz = parsear_mrz(texto_mrz)
    datos.update(datos_mrz)

    direccion = None
    departamento = None
    distrito = None  # municipio/distrito según versión

    lineas = [l.strip() for l in texto_completo.splitlines() if l.strip()]

    for i, linea in enumerate(lineas):
        low = linea.lower()

        if "residencia" in low or "address" in low:
            partes = []
            if i + 1 < len(lineas):
                partes.append(lineas[i + 1])
            if i + 2 < len(lineas):
                partes.append(lineas[i + 2])
            if partes:
                direccion = " ".join(partes)

        if ("departamento" in low or "state" in low) and departamento is None:
            if ":" in linea:
                departamento = linea.split(":", 1)[1].strip()
            elif i + 1 < len(lineas):
                departamento = lineas[i + 1].strip()

        # Versión vieja: Municipio / City; nueva: Distrito
        if ("municipio" in low or "distrito" in low or "city" in low) and distrito is None:
            if ":" in linea:
                distrito = linea.split(":", 1)[1].strip()
            elif i + 1 < len(lineas):
                distrito = lineas[i + 1].strip()

    datos["direccion"] = direccion
    datos["departamento_residencia"] = departamento
    datos["distrito_residencia"] = distrito

    return datos


# ---------------------------------------------------------
# OCR frente: número DUI y nombres si son más legibles allí
# ---------------------------------------------------------
def extraer_desde_frente(img: Image.Image) -> dict:
    datos = {}

    img_prep = preparar_imagen(img)
    texto = pytesseract.image_to_string(img_prep, lang="spa+eng")
    datos["texto_frente_raw"] = texto

    lineas = [l.strip() for l in texto.splitlines() if l.strip()]

    apellidos = None
    nombres = None
    numero_doc = None

    for linea in lineas:
        m_dui = re.search(r"\b\d{8}-\d\b", linea)
        if m_dui:
            numero_doc = m_dui.group(0)
            break

    for i, linea in enumerate(lineas):
        low = linea.lower()

        if "apellidos" in low or "surname" in low:
            if i + 1 < len(lineas):
                apellidos = lineas[i + 1].strip()

        if "nombres" in low or "given names" in low:
            if i + 1 < len(lineas):
                nombres = lineas[i + 1].strip()

    datos["apellidos"] = apellidos
    datos["nombres"] = nombres
    if numero_doc:
        datos["numero_doc"] = numero_doc

    return datos


def combinar_datos(front: dict, back: dict) -> dict:
    # Combina datos de frente y reverso dando prioridad al MRZ
    datos = {}
    datos.update(front)
    for k, v in back.items():
        if k in ["numero_doc", "apellidos", "nombres"]:
            if v:
                datos[k] = v
        else:
            if v and not datos.get(k):
                datos[k] = v
    return datos


# ---------------------------------------------------------
# Carga de imágenes
# ---------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    frente_file = st.file_uploader("Frente del DUI", type=["jpg", "jpeg", "png"], key="frente")
with col2:
    reverso_file = st.file_uploader("Reverso del DUI", type=["jpg", "jpeg", "png"], key="reverso")

if frente_file:
    img_front = Image.open(frente_file)
    st.image(img_front, caption="Frente subido", use_column_width=True)

if reverso_file:
    img_back = Image.open(reverso_file)
    st.image(img_back, caption="Reverso subido", use_column_width=True)

datos_extraidos = {}

if st.button("Leer datos desde el DUI"):
    if not frente_file or not reverso_file:
        st.error("Por favor sube **ambos lados** del DUI.")
    else:
        front_data = extraer_desde_frente(img_front)
        back_data = extraer_desde_reverso(img_back)
        datos_extraidos = combinar_datos(front_data, back_data)
        st.success("Lectura completada. Verifica los datos en el formulario de abajo.")


# ---------------------------------------------------------
# FORMULARIO PRINCIPAL
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Información de DUI (para procesos administrativos / seguros)")


def valor_inicial(campo: str, por_defecto: str = "") -> str:
    if not datos_extraidos:
        return por_defecto
    return (datos_extraidos.get(campo) or por_defecto).strip()


# Construir Nombre Completo a partir de apellidos + nombres
nombre_completo_auto = ""
if datos_extraidos:
    ap = datos_extraidos.get("apellidos") or ""
    no = datos_extraidos.get("nombres") or ""
    nombre_completo_auto = (ap + " " + no).strip()

# Número de DUI sin guiones
numero_dui_raw = valor_inicial("numero_doc")
numero_dui_sin = numero_dui_raw.replace("-", "") if numero_dui_raw else ""

# Campos que vienen del DUI
nombre_completo = st.text_input("Nombre Completo", value=nombre_completo_auto)
numero_dui = st.text_input("Número de DUI (sin guiones)", value=numero_dui_sin)
direccion_completa = st.text_input("Dirección completa", value=valor_inicial("direccion"))
departamento = st.text_input("Departamento", value=valor_inicial("departamento_residencia"))
distrito = st.text_input("Distrito", value=valor_inicial("distrito_residencia"))

st.markdown("### Información de contacto (rellenada por la persona)")
telefono_contacto = st.text_input("Número telefónico de contacto")

st.markdown("### Información necesaria para procesos de pagos")
correo_facturacion = st.text_input("Correo electrónico para recibir facturación (DTE)")
banco = st.text_input("Banco")
cuenta_banco = st.text_input("Cuenta de Banco")
tipo_cuenta = st.text_input("Tipo de cuenta")

st.markdown("### Información necesaria para saldos / recargas")
celular_recarga = st.text_input("Número de Celular para recarga")
compania_tel = st.text_input("Compañía telefónica")

if st.button("Guardar registro (demo)"):
    registro = {
        "nombre_completo": nombre_completo,
        "numero_dui_sin_guiones": numero_dui,
        "direccion_completa": direccion_completa,
        "departamento": departamento,
        "distrito": distrito,
        "telefono_contacto": telefono_contacto,
        "correo_facturacion": correo_facturacion,
        "banco": banco,
        "cuenta_banco": cuenta_banco,
        "tipo_cuenta": tipo_cuenta,
        "celular_recarga": celular_recarga,
        "compania_telefonica": compania_tel,
    }

    st.success("Registro 'guardado' (solo demostración).")
    st.json(registro)
    st.info("En producción aquí se guardaría en una base de datos o archivo CSV/Excel.")
