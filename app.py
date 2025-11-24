import streamlit as st
from PIL import Image
import pytesseract
import re

st.title("Registro con lectura de documento de identidad")

st.write("Sube una imagen del documento y trataremos de extraer el nombre y el número.")

# Si lo ejecutas local en Windows y Tesseract no está en el PATH,
# descomenta y ajusta la ruta:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

uploaded_file = st.file_uploader(
    "Sube el documento (imagen JPG/PNG)", 
    type=["jpg", "jpeg", "png"]
)

nombre_detectado = ""
doc_detectado = ""

def extraer_datos_ocr(img: Image.Image):
    """
    Aplica OCR y trata de extraer:
    - Número de documento tipo 99999999-9 (DUI)
    - Nombre completo (heurística sencilla)
    """
    texto = pytesseract.image_to_string(img, lang="spa")  # OCR en español
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]

    # 1. Buscar número de documento con patrón tipo DUI SV (8 dígitos, guión, 1 dígito)
    num_doc = None
    patron_dui = re.compile(r"\b\d{8}-\d\b")
    for linea in lineas:
        m = patron_dui.search(linea)
        if m:
            num_doc = m.group(0)
            break

    # 2. Heurística simple para nombre:
    #    - línea con muchas letras en mayúsculas
    #    - sin dígitos
    #    - al menos dos palabras
    posible_nombre = None
    mejor_puntaje = 0

    for linea in lineas:
        if any(ch.isdigit() for ch in linea):
            continue

        palabras = linea.split()
        if len(palabras) < 2:
            continue

        # puntuamos por proporción de mayúsculas
        mayus = sum(1 for ch in linea if ch.isalpha() and ch.isupper())
        letras = sum(1 for ch in linea if ch.isalpha())
        if letras == 0:
            continue
        score = mayus / letras

        if score > mejor_puntaje and score > 0.6:  # umbral ajustable
            mejor_puntaje = score
            posible_nombre = linea

    return posible_nombre, num_doc, texto

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Documento subido", use_column_width=True)

    if st.button("Leer datos del documento"):
        nombre_detectado, doc_detectado, texto_completo = extraer_datos_ocr(image)

        st.subheader("Texto detectado (OCR)")
        st.text(texto_completo)

# Campos del formulario (permiten corrección)
st.subheader("Datos de la persona")

nombre = st.text_input(
    "Nombre completo (como en el documento)", 
    value=nombre_detectado or ""
)
numero_doc = st.text_input(
    "Número de documento", 
    value=doc_detectado or ""
)

email = st.text_input("Correo electrónico (opcional)")
telefono = st.text_input("Teléfono (opcional)")

if st.button("Guardar registro"):
    # Aquí puedes guardar a CSV, base de datos, etc.
    # Ejemplo simple: mostramos un resumen
    st.success("Registro guardado (ejemplo).")
    st.write({
        "nombre": nombre,
        "numero_doc": numero_doc,
        "email": email,
        "telefono": telefono,
        "nombre_archivo": uploaded_file.name if uploaded_file else None,
    })
    st.info("En una versión real, aquí escribirías estos datos a una base de datos o archivo.")
