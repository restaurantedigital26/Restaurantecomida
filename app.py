from flask import Flask, render_template, request, jsonify, send_from_directory, abort
import openai  # type: ignore
from pymongo import MongoClient
import requests, os
from bson.objectid import ObjectId
from flask import session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
import datetime
from datetime import datetime, timezone
import sys
import mimetypes
from urllib.parse import unquote, quote

# =========================
# CONFIGURACIÓN GENERAL
# =========================
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "clave_super_secreta_123")

# Configurar carpeta de uploads PERSISTENTE
UPLOAD_FOLDER = "static/uploads"
print(f"📁 UPLOAD_FOLDER configurado como: {UPLOAD_FOLDER}")

# ===== NUEVO: Crear subcarpetas necesarias =====
os.makedirs(os.path.join(UPLOAD_FOLDER, "restaurantes"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, "publicidad"), exist_ok=True)

print(f"✅ Carpeta de uploads lista: {UPLOAD_FOLDER}")
print(f"✅ Subcarpeta restaurantes: {os.path.join(UPLOAD_FOLDER, 'restaurantes')}")

# =========================
# API KEYS
# =========================
GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

if not GOOGLE_API_KEY:
    print("⚠️ ADVERTENCIA: GOOGLE_PLACES_API_KEY no configurada. El mapa podría no funcionar.")

# =========================
# OPENAI (VERSIÓN LEGACY - FUNCIONAL)
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print("="*60)
print("🔍 CONFIGURANDO OPENAI (API LEGACY)")
print("="*60)

if not OPENAI_API_KEY:
    print("❌ ERROR: OPENAI_API_KEY no configurada")
    client = None
else:
    try:
        openai.api_key = OPENAI_API_KEY
        # En la versión legacy, el cliente es la biblioteca misma
        client = openai
        print("✅ OpenAI configurado correctamente (versión legacy)")
        
        # Probar la conexión
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            print("✅ Conexión con OpenAI verificada")
        except Exception as e:
            print(f"⚠️ OpenAI configurado pero falló la prueba: {e}")
            
    except ImportError as e:
        print(f"❌ Error importando openai: {e}")
        print("   Verifica que openai esté instalado: pip install openai==0.28.0")
        client = None
    except Exception as e:
        print(f"❌ Error configurando OpenAI: {e}")
        client = None

print("="*60)

# =========================
# CLOUDINARY CONFIGURATION
# =========================
import cloudinary
import cloudinary.uploader
import cloudinary.api

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

print("="*50)
print("🔍 VERIFICANDO VARIABLES DE CLOUDINARY")
print("="*50)
print(f"CLOUDINARY_CLOUD_NAME: {'✅ Configurada' if CLOUDINARY_CLOUD_NAME else '❌ No configurada'}")
print(f"CLOUDINARY_API_KEY: {'✅ Configurada' if CLOUDINARY_API_KEY else '❌ No configurada'}")
print(f"CLOUDINARY_API_SECRET: {'✅ Configurada' if CLOUDINARY_API_SECRET else '❌ No configurada'}")

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    try:
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True
        )
        print("✅ Cloudinary configurado correctamente")
    except Exception as e:
        print(f"❌ Error configurando Cloudinary: {e}")
else:
    print("⚠️ Cloudinary no configurado - usando almacenamiento local")
print("="*50)

# =========================
# FUNCIÓN PARA SUBIR A CLOUDINARY
# =========================
def subir_a_cloudinary(archivo, carpeta):
    """
    Sube una imagen a Cloudinary y devuelve la URL segura y el public_id
    - archivo: archivo de imagen (request.files)
    - carpeta: 'restaurantes', 'publicidad', 'platillos'
    """
    if not archivo or not archivo.filename:
        return None
    
    # Si Cloudinary no está configurado, retornar None
    if not CLOUDINARY_CLOUD_NAME:
        print("⚠️ Cloudinary no configurado")
        return None
    
    try:
        print(f"📸 Subiendo a Cloudinary: {archivo.filename}")
        
        resultado = cloudinary.uploader.upload(
            archivo,
            folder=f"comida_iguala/{carpeta}",
            resource_type="image",
            overwrite=True
        )
        
        url_imagen = resultado['secure_url']
        public_id = resultado['public_id']
        
        print(f"✅ Imagen subida: {url_imagen}")
        print(f"📌 Public ID: {public_id}")
        
        return {
            'url': url_imagen,
            'public_id': public_id
        }
        
    except Exception as e:
        print(f"❌ Error en Cloudinary: {e}")
        return None

# =========================
# MONGODB ATLAS (USANDO VARIABLE DE ENTORNO)
# =========================
MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    print("❌ ERROR: MONGODB_URI no está configurada")
    print("Debes configurar la variable de entorno MONGODB_URI")
    sys.exit(1)

try:
    mongo = MongoClient(MONGODB_URI)
    # Verificar conexión
    mongo.admin.command('ping')
    print("✅ Conectado a MongoDB Atlas")
    
    # Obtener base de datos
    db = mongo["comida_iguala"]
    
    # Colecciones
    lugares = db["lugares"]
    reviews = db["reviews"]
    usuarios = db["usuarios"]
    restaurantes = db["restaurantes"]
    comentarios = db["comentarios"]
    chats = db["chats"]
    platillo_chats = db["platillo_chats"] 
    administradores = db["administradores"]
    calificaciones = db["calificaciones"]
    publicidad = db["publicidad"] 
    ia_conocimiento = db["ia_conocimiento"]
    
    print("✅ Colecciones listas")
    
except Exception as e:
    print(f"❌ Error conectando a MongoDB: {e}")
    sys.exit(1)

# Crear administrador por defecto si no existe
try:
    if not administradores.find_one({"username": "admin"}):
        administradores.insert_one({
            "username": "admin",
            "password": generate_password_hash("admin123"),
            "nombre": "Administrador",
            "email": "admin@gmail.com"
        })
        print("✅ Administrador por defecto creado (admin/admin123)")
except Exception as e:
    print(f"⚠️ Error al crear administrador: {e}")

# =========================
# FLASK-MAIL CONFIGURATION
# =========================
from flask_mail import Mail, Message

# --- DIAGNÓSTICO ---
print("="*50)
print("🔍 VERIFICANDO VARIABLES DE ENTORNO")
mail_user = os.environ.get('MAIL_USERNAME')
mail_pass = os.environ.get('MAIL_PASSWORD')
print(f"MAIL_USERNAME: '{mail_user}'")
print(f"MAIL_PASSWORD: {'✅ Configurada' if mail_pass else '❌ No configurada'} (longitud: {len(mail_pass or '')})")
print("="*50)
# --- FIN DIAGNÓSTICO ---

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587  # Primero prueba con 587/TLS
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = mail_user
app.config['MAIL_PASSWORD'] = mail_pass
app.config['MAIL_DEFAULT_SENDER'] = mail_user  # ← CORREGIDO: solo el email
app.config['MAIL_MAX_EMAILS'] = None
app.config['MAIL_ASCII_ATTACHMENTS'] = False

mail = Mail(app)

# =========================
# FUNCIONES DE CORREO
# =========================
def enviar_correo_bienvenida(email, nombre):
    """Envía correo de bienvenida a nuevos usuarios"""
    try:
        msg = Message(
            subject="🎉 ¡Bienvenido a Sabores de Iguala!",
            sender=app.config['MAIL_USERNAME'],  # ← ¡ESTA ES LA LÍNEA CLAVE!
            recipients=[email],
            html=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        background: linear-gradient(135deg, #fff8e7, #fff);
                    }}
                    .header {{
                        background: linear-gradient(135deg, #8B4513, #654321);
                        color: white;
                        padding: 30px;
                        text-align: center;
                        border-radius: 10px 10px 0 0;
                    }}
                    .content {{
                        padding: 30px;
                        background: white;
                    }}
                    .button {{
                        display: inline-block;
                        padding: 12px 24px;
                        background: #8B4513;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 0;
                    }}
                    .footer {{
                        text-align: center;
                        padding: 20px;
                        color: #666;
                        font-size: 0.9rem;
                        border-top: 1px solid #e0d5c6;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎊 ¡Bienvenido, {nombre}!</h1>
                    </div>
                    <div class="content">
                        <h2>Gracias por unirte a Sabores de Iguala</h2>
                        <p>Estamos emocionados de tenerte en nuestra comunidad gastronómica. Ahora puedes:</p>
                        <ul>
                            <li>🍽️ Explorar los mejores restaurantes de Iguala</li>
                            <li>⭐ Calificar y comentar tus experiencias</li>
                            <li>💬 Chatear directamente con los restaurantes</li>
                            <li>🎁 Descubrir promociones exclusivas</li>
                        </ul>
                        <p>¿Listo para comenzar tu aventura culinaria?</p>
                        <a href="http://127.0.0.1:5000/dashboard-cliente" class="button">Explorar Restaurantes</a>
                    </div>
                    <div class="footer">
                        <p>© 2024 Sabores de Iguala - Todos los derechos reservados</p>
                        <p style="font-size: 0.8rem;">Este correo fue enviado a {email}</p>
                    </div>
                </div>
            </body>
            </html>
            """
        )
        mail.send(msg)
        print(f"✅ Correo de bienvenida enviado a {email}")
        return True
    except Exception as e:
        print(f"❌ Error enviando correo de bienvenida: {e}")
        return False

def enviar_correo_recuperacion(email, token):
    """Envía correo para recuperación de contraseña"""
    try:
        msg = Message(
            subject="🔐 Recuperación de contraseña - Sabores de Iguala",
            recipients=[email],
            html=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        background: linear-gradient(135deg, #8B4513, #654321);
                        color: white;
                        padding: 30px;
                        text-align: center;
                        border-radius: 10px 10px 0 0;
                    }}
                    .content {{
                        padding: 30px;
                        background: #fff8e7;
                    }}
                    .token-box {{
                        background: white;
                        border: 2px solid #8B4513;
                        border-radius: 5px;
                        padding: 15px;
                        text-align: center;
                        font-size: 1.2rem;
                        font-weight: bold;
                        margin: 20px 0;
                    }}
                    .footer {{
                        text-align: center;
                        padding: 20px;
                        color: #666;
                        font-size: 0.9rem;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔐 Recuperación de Contraseña</h1>
                    </div>
                    <div class="content">
                        <p>Hemos recibido una solicitud para restablecer tu contraseña.</p>
                        <p>Tu código de recuperación es:</p>
                        <div class="token-box">
                            {token}
                        </div>
                        <p>Este código expirará en 1 hora por seguridad.</p>
                        <p>Si no solicitaste este cambio, ignora este correo.</p>
                    </div>
                    <div class="footer">
                        <p>© 2024 Sabores de Iguala</p>
                    </div>
                </div>
            </body>
            </html>
            """
        )
        mail.send(msg)
        print(f"✅ Correo de recuperación enviado a {email}")
        return True
    except Exception as e:
        print(f"❌ Error enviando correo de recuperación: {e}")
        return False

# =========================
# INICIALIZAR CAMPOS DE CALIFICACIÓN PARA RESTAURANTES EXISTENTES
# =========================
def inicializar_calificaciones():
    """Agrega los campos de calificación a todos los restaurantes que no los tengan"""
    for restaurante in restaurantes.find():
        update_data = {}
        if 'promedio_general' not in restaurante:
            update_data['promedio_general'] = 0.0
        if 'promedio_comida' not in restaurante:
            update_data['promedio_comida'] = 0.0
        if 'promedio_servicio' not in restaurante:
            update_data['promedio_servicio'] = 0.0
        if 'total_calificaciones' not in restaurante:
            update_data['total_calificaciones'] = 0
            
        if update_data:
            restaurantes.update_one(
                {"_id": restaurante["_id"]},
                {"$set": update_data}
            )
    print("✅ Campos de calificación inicializados para todos los restaurantes")    

# =========================
# PLATILLOS TRADICIONALES
# =========================
PLATILLOS = {
    "pozole": "Pozole (blanco y verde)",
    "elopozole": "Elopozole",
    "cochinita": "Cochinita estilo Iguala",
    "tamales": "Tamales de nejo",
    "barbacoa": "Barbacoa",
    "tacos": "Tacos",
    "picadas": "Picadas de papa"
}

# =========================
# DETECTAR PLATILLO
# =========================
def detectar_platillo(texto):
    texto = texto.lower()
    for clave in PLATILLOS:
        if clave in texto:
            return clave
    return None

# =========================
# DETECTAR SI PIDEN RESEÑAS
# =========================
def pide_resenas(texto):
    texto = texto.lower()
    palabras = ["reseña", "reseñas", "opinión", "opiniones", "comentarios"]
    return any(p in texto for p in palabras)

# =========================
# GOOGLE PLACES → MONGO
# =========================
def cargar_google_places(query, platillo):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": query,
        "key": GOOGLE_API_KEY
    }

    response = requests.get(url, params=params).json()
    resultados = response.get("results", [])

    print(f"🔍 {query} → {len(resultados)} resultados")

    for lugar in resultados:
        lugares.update_one(
            {"place_id": lugar["place_id"]},
            {"$set": {
                "nombre": lugar["name"],
                "direccion": lugar.get("formatted_address"),
                "rating": lugar.get("rating", 0),
                "total_reviews": lugar.get("user_ratings_total", 0),
                "ubicacion": lugar["geometry"]["location"],
                "platillo": platillo,
                "fuente": "Google Places"
            }},
            upsert=True
        )

# =========================
# RUTAS
# =========================
@app.route("/")
def landing():
    return render_template("landing.html", user=session.get("nombre"))

@app.route("/chat-ui")
def chat_ui():
    return render_template("index.html")

@app.route("/logout")
def logout():
    session.clear()  
    return redirect(url_for("landing"))

# =========================
# SERVIDOR DE IMÁGENES DESDE UPLOAD_FOLDER (RESPALDO)
# =========================
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Sirve archivos desde UPLOAD_FOLDER con diagnóstico detallado"""
    import os
    
    # Construir ruta completa
    ruta_completa = os.path.join(UPLOAD_FOLDER, filename)
    
    print(f"🔍 Solicitando: {filename}")
    print(f"📁 Buscando en: {ruta_completa}")
    print(f"📁 ¿Existe? {os.path.exists(ruta_completa)}")
    
    if not os.path.exists(ruta_completa):
        # Listar archivos en la carpeta para diagnóstico
        carpeta = os.path.dirname(ruta_completa)
        if os.path.exists(carpeta):
            archivos = os.listdir(carpeta)
            print(f"📁 Archivos en {carpeta}: {archivos[:5]}")  # Primeros 5 archivos
        else:
            print(f"❌ La carpeta {carpeta} no existe")
        return "Imagen no encontrada", 404
    
    try:
        return send_from_directory(UPLOAD_FOLDER, filename)
    except Exception as e:
        print(f"❌ Error sirviendo: {e}")
        return "Error al servir imagen", 500

# =========================
# FUNCIÓN PARA OBTENER URL DE IMAGEN
# =========================
def get_image_url(imagen_ruta, tipo="general"):
    """
    Devuelve la URL correcta para una imagen
    """
    if not imagen_ruta:
        return url_for('static', filename='img/default.jpg')
    
    # Si es solo nombre de archivo (guardado en uploads)
    if tipo == "restaurante":
        return url_for('static', filename=f'uploads/restaurantes/{imagen_ruta}')
    elif tipo == "publicidad":
        return url_for('static', filename=f'uploads/publicidad/{imagen_ruta}')
    else:  # general o platillo
        return url_for('static', filename=f'uploads/{imagen_ruta}')

# Hacer disponible la función get_image_url en todos los templates
@app.context_processor
def utility_processor():
    return dict(get_image_url=get_image_url)

# =========================
# CARGAR PLATILLOS
# =========================
@app.route("/cargar-platillos")
def cargar_platillos_tradicionales():
    cargar_google_places("pozole tradicional en Iguala Guerrero", "pozole")
    cargar_google_places("elopozole tradicional en Iguala Guerrero", "elopozole")
    cargar_google_places("cochinita tradicional en Iguala Guerrero", "cochinita")
    cargar_google_places("tamales de nejo en Iguala Guerrero", "tamales")
    cargar_google_places("barbacoa tradicional en Iguala Guerrero", "barbacoa")
    cargar_google_places("antojitos mexicanos en Iguala Guerrero", "tacos")

    total = lugares.count_documents({})
    return jsonify({
        "msg": "✔️ Platillos tradicionales cargados correctamente",
        "total_lugares": total
    })

# =========================
# MAPA - SOLO RESTAURANTES REGISTRADOS
# =========================
@app.route("/mapa")
def mapa():
    platillo = request.args.get("platillo")
    resultados = []
    
    # Buscar SOLO en restaurantes registrados (NO en Google Places)
    if platillo:
        # Buscar restaurantes que tengan este platillo en su menú
        for r in restaurantes.find():
            if r.get("menu"):
                for p in r["menu"]:
                    if platillo.lower() in p.get("nombre", "").lower():
                        if r.get("ubicacion") and r["ubicacion"].get("lat") and r["ubicacion"].get("lng"):
                            resultados.append({
                                "nombre": r["nombre"],
                                "direccion": r.get("direccion", "Dirección no disponible"),
                                "ubicacion": r["ubicacion"],
                                "rating": r.get("promedio_general", 0),
                                "total_reviews": r.get("total_calificaciones", 0),
                                "tipo": "restaurante_registrado",
                                "platillo": platillo
                            })
                        break
    else:
        # Si no hay filtro de platillo, mostrar TODOS los restaurantes con ubicación
        for r in restaurantes.find({"ubicacion": {"$exists": True, "$ne": None}}):
            # Obtener los platillos de este restaurante para el tooltip
            platillos_nombres = []
            if r.get("menu"):
                for p in r["menu"]:
                    platillos_nombres.append(p.get("nombre", ""))
            
            resultados.append({
                "nombre": r["nombre"],
                "direccion": r.get("direccion", "Dirección no disponible"),
                "ubicacion": r["ubicacion"],
                "rating": r.get("promedio_general", 0),
                "total_reviews": r.get("total_calificaciones", 0),
                "tipo": "restaurante_registrado",
                "platillos": platillos_nombres[:3]  # Solo 3 platillos para no saturar
            })

    print(f"📍 Mapa: {len(resultados)} restaurantes registrados encontrados")
    return jsonify(resultados)

# =========================
# PROCESAR CONSULTA DE PLATILLO
# =========================
def procesar_consulta_platillo(platillo_key, mensaje):
    """Procesa consultas sobre un platillo específico"""
    try:
        nombre_platillo = PLATILLOS.get(platillo_key, platillo_key)
        print(f"🍽️ Procesando consulta sobre: {nombre_platillo}")

        # Buscar restaurantes que ofrecen este platillo
        restaurantes_con_platillo = []
        for rest in restaurantes.find():
            if rest.get("menu"):
                for platillo in rest["menu"]:
                    if platillo_key in platillo.get("nombre", "").lower():
                        restaurantes_con_platillo.append(rest)
                        break

        respuesta = f"🍽️ **{nombre_platillo}**\n\n"
        
        if restaurantes_con_platillo:
            respuesta += "🏆 **RESTAURANTES QUE LO OFRECEN**\n"
            respuesta += "═══════════════════════════\n\n"
            for i, r in enumerate(restaurantes_con_platillo[:5], start=1):
                respuesta += f"**{i}. {r['nombre']}**\n"
                respuesta += f"   📍 {r.get('direccion', 'Ubicación no disponible')}\n"
                respuesta += f"   📞 {r.get('telefono', 'Sin teléfono')}\n"
                if r.get('promedio_general'):
                    estrellas = "⭐" * int(r['promedio_general'])
                    respuesta += f"   {estrellas} {r['promedio_general']}/5\n"
                respuesta += "\n"
        else:
            respuesta += "❌ No hay restaurantes registrados para este platillo.\n\n"
        
        # Opiniones (solo si el usuario las pidió)
        if pide_resenas(mensaje):
            respuesta += "💬 **OPINIONES DE CLIENTES**\n"
            respuesta += "═══════════════════════════\n\n"
            
            opiniones_encontradas = False
            for rest in restaurantes_con_platillo[:2]:
                comentarios_rest = list(comentarios.find(
                    {"restaurante_id": rest["_id"]}
                ).sort("fecha", -1).limit(2))
                
                if comentarios_rest:
                    opiniones_encontradas = True
                    respuesta += f"📌 **{rest['nombre']}**\n"
                    for c in comentarios_rest:
                        respuesta += f"   \"{c['comentario']}\"\n"
                        respuesta += f"   — {c['cliente_nombre']}\n\n"
            
            if not opiniones_encontradas:
                respuesta += "   Aún no hay opiniones para este platillo.\n"
                respuesta += "   ¡Sé el primero en calificar!\n\n"
        
        # Promociones
        promociones = []
        for rest in restaurantes_con_platillo[:3]:
            promos = list(publicidad.find({
                "restaurante_id": rest["_id"],
                "activa": True
            }).limit(2))
            for p in promos:
                promociones.append({
                    "restaurante": rest["nombre"],
                    "titulo": p["titulo"],
                    "descuento": p.get("descuento", "")
                })
        
        if promociones:
            respuesta += "🎁 **PROMOCIONES ACTIVAS**\n"
            respuesta += "═══════════════════════════\n\n"
            for p in promociones[:3]:
                respuesta += f"**{p['restaurante']}**\n"
                respuesta += f"   ✨ {p['titulo']}\n"
                if p['descuento']:
                    respuesta += f"   🔖 {p['descuento']}\n"
                respuesta += "\n"
        
        respuesta += "───────────────────────────\n"
        respuesta += "¿Necesitas más información? Solo pregúntame."

        return jsonify({
            "reply": respuesta,
            "platillo": platillo_key
        })
        
    except Exception as e:
        print(f"❌ Error en procesar_consulta_platillo: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "reply": f"Lo siento, no pude obtener información sobre {platillo_key}."
        })

# =========================
# CHAT IA MEJORADO (VERSIÓN LEGACY)
# =========================
@app.route("/chat", methods=["POST"])
def chat():
    try:
        mensaje = request.json.get("message", "")
        
        # DIAGNÓSTICO: Verificar cliente OpenAI
        if not client:
            print("❌ ERROR: Cliente OpenAI no inicializado")
            print(f"   OPENAI_API_KEY presente: {'✅' if OPENAI_API_KEY else '❌'}")
            return jsonify({
                "reply": "🤖 El asistente IA no está disponible en este momento.\n\n"
                        "Posibles causas:\n"
                        "• API key de OpenAI no configurada\n"
                        "• Error de conexión con OpenAI\n\n"
                        "Por favor, contacta al administrador."
            })
        
        print(f"📨 Mensaje recibido: '{mensaje}'")
        mensaje_lower = mensaje.lower()
        
        # ===== DETECTAR PREGUNTAS SOBRE RESTAURANTES EN GENERAL =====
        palabras_restaurantes = ["qué restaurantes", "que restaurantes", "cuántos restaurantes", "cuantos restaurantes", 
                                 "lista de restaurantes", "todos los restaurantes", "restaurantes hay", 
                                 "restaurantes disponibles", "qué lugares", "que lugares"]
        
        if any(pregunta in mensaje_lower for pregunta in palabras_restaurantes):
            print("🔍 Detectada consulta: lista de restaurantes")
            # Obtener todos los restaurantes
            todos_restaurantes = list(restaurantes.find().sort("nombre", 1))
            
            if not todos_restaurantes:
                return jsonify({
                    "reply": "📭 No hay restaurantes registrados en el sistema aún."
                })
            
            respuesta = f"🏪 **RESTAURANTES DISPONIBLES**\n"
            respuesta += f"═══════════════════════════\n\n"
            respuesta += f"📊 **Total:** {len(todos_restaurantes)} restaurantes\n\n"
            
            for i, r in enumerate(todos_restaurantes[:10], start=1):
                respuesta += f"**{i}. {r['nombre']}**\n"
                respuesta += f"   📍 {r.get('direccion', 'Dirección no disponible')}\n"
                respuesta += f"   📞 {r.get('telefono', 'Teléfono no disponible')}\n"
                
                if r.get('promedio_general'):
                    estrellas = "⭐" * int(r['promedio_general'])
                    respuesta += f"   {estrellas} {r['promedio_general']}/5 ({r.get('total_calificaciones', 0)} opiniones)\n"
                else:
                    respuesta += f"   ⭐ Nuevo (sin calificaciones)\n"
                
                num_platillos = len(r.get('menu', []))
                respuesta += f"   🍽️ {num_platillos} platillo{'s' if num_platillos != 1 else ''}\n"
                
                promos_activas = publicidad.count_documents({
                    "restaurante_id": r["_id"],
                    "activa": True
                })
                if promos_activas > 0:
                    respuesta += f"   🎁 {promos_activas} promoción{'es' if promos_activas != 1 else ''} activa{'s' if promos_activas != 1 else ''}\n"
                
                respuesta += "\n"
            
            if len(todos_restaurantes) > 10:
                respuesta += f"... y {len(todos_restaurantes) - 10} restaurantes más.\n\n"
            
            respuesta += "───────────────────────────\n"
            respuesta += "¿Quieres información de algún restaurante en específico? Solo dime su nombre."
            
            return jsonify({"reply": respuesta})
        
        # ===== DETECTAR PREGUNTAS SOBRE UN RESTAURANTE ESPECÍFICO =====
        restaurante_mencionado = None
        for r in restaurantes.find():
            if r["nombre"].lower() in mensaje_lower:
                restaurante_mencionado = r
                break
        
        if restaurante_mencionado:
            print(f"🔍 Detectado restaurante: {restaurante_mencionado['nombre']}")
            r = restaurante_mencionado
            respuesta = f"🏪 **{r['nombre']}**\n"
            respuesta += "═══════════════════════════\n\n"
            respuesta += f"📝 **Descripción:** {r.get('descripcion', 'Sin descripción')}\n\n"
            respuesta += f"📍 **Dirección:** {r.get('direccion', 'No disponible')}\n"
            respuesta += f"📞 **Teléfono:** {r.get('telefono', 'No disponible')}\n"
            
            if r.get('promedio_general'):
                estrellas = "⭐" * int(r['promedio_general'])
                respuesta += f"⭐ **Calificación:** {estrellas} {r['promedio_general']}/5 ({r.get('total_calificaciones', 0)} opiniones)\n"
            
            if r.get('menu'):
                respuesta += f"\n🍽️ **Platillos destacados:**\n"
                for i, p in enumerate(r['menu'][:3], start=1):
                    respuesta += f"   {i}. **{p['nombre']}** - ${p['precio']}\n"
                if len(r['menu']) > 3:
                    respuesta += f"   ... y {len(r['menu']) - 3} platillos más\n"
            
            promos = list(publicidad.find({
                "restaurante_id": r["_id"],
                "activa": True
            }).limit(2))
            
            if promos:
                respuesta += f"\n🎁 **Promociones activas:**\n"
                for p in promos:
                    respuesta += f"   ✨ {p['titulo']}\n"
                    if p.get('descuento'):
                        respuesta += f"   🔖 {p['descuento']}\n"
            
            respuesta += "\n───────────────────────────\n"
            respuesta += f"¿Quieres conocer más sobre algún platillo en específico?"
            
            return jsonify({"reply": respuesta})
        
        # Saludos
        saludos = ["hola", "buenos días", "buenas tardes", "buenas noches", "qué tal", "que tal", "saludos"]
        if any(saludo in mensaje_lower for saludo in saludos):
            print("🔍 Detectado: saludo")
            return jsonify({
                "reply": "¡Hola! Soy el asistente gastronómico de Iguala. ¿En qué puedo ayudarte?\n\n"
                        "Puedes preguntarme sobre:\n"
                        "🍲 **Platillos típicos** (pozole, cochinita, tamales, etc.)\n"
                        "🏪 **Restaurantes** (lista de restaurantes, información específica)\n"
                        "⭐ **Opiniones de clientes**\n"
                        "📅 **Promociones y eventos**"
            })
        
        # Ayuda
        if "ayuda" in mensaje_lower or "qué puedes hacer" in mensaje_lower or "que puedes hacer" in mensaje_lower:
            print("🔍 Detectado: solicitud de ayuda")
            return jsonify({
                "reply": "🤖 **¿Qué puedo hacer por ti?**\n\n"
                        "✅ Mostrarte **todos los restaurantes** disponibles\n"
                        "✅ Darte **información detallada** de un restaurante específico\n"
                        "✅ Recomendarte los mejores **platillos típicos** de Iguala\n"
                        "✅ Mostrarte dónde puedes encontrarlos\n"
                        "✅ Compartir **opiniones y calificaciones** de clientes\n"
                        "✅ Informarte sobre **promociones y eventos** especiales\n\n"
                        "**Ejemplos de preguntas:**\n"
                        "• '¿Qué restaurantes hay?'\n"
                        "• 'Dime información de Doña Mari'\n"
                        "• '¿Dónde hay buen pozole?'\n"
                        "• 'Recomiéndame un lugar para comer cochinita'\n"
                        "• 'Promociones en tamales'"
            })
        
        # Detectar platillo
        platillo_key = detectar_platillo(mensaje)
        
        if platillo_key:
            print(f"🔍 Detectado platillo: {platillo_key}")
            return procesar_consulta_platillo(platillo_key, mensaje)
        
        # Si no detecta nada específico
        print("🔍 No se detectó ninguna consulta específica")
        return jsonify({
            "reply": "🤔 No entendí bien tu pregunta.\n\n"
                    "Puedes preguntarme sobre:\n"
                    "- **Restaurantes:** '¿Qué restaurantes hay?', 'Información de Doña Mari'\n"
                    "- **Platillos:** 'pozole', 'cochinita', 'tamales', 'barbacoa', 'elopozole'\n"
                    "- **Opiniones:** '¿Qué opinan de Doña Mari?', 'reseñas de pozole'\n\n"
                    "o escribe **'ayuda'** para más información."
        })
        
    except Exception as e:
        print(f"❌ ERROR CRÍTICO en chat(): {type(e).__name__}")
        print(f"❌ Detalle: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "reply": "Lo siento, ocurrió un error interno. Por favor intenta de nuevo más tarde."
        }), 500

# =========================
# REGISTRO
# =========================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.form
        nombre = data.get("nombre")
        email = data.get("email")
        password = generate_password_hash(data.get("password"))
        
        # Forzar tipo a "cliente" - los restaurantes solo los crea el admin
        tipo = "cliente"

        if not nombre or not email or not password:
            return "⚠️ Todos los campos son obligatorios"

        if usuarios.find_one({"email": email}):
            return "⚠️ El usuario ya existe"

        usuario = {
            "nombre": nombre,
            "email": email,
            "password": password,
            "tipo": tipo,
            "fecha_registro": datetime.now(timezone.utc)
        }

        usuarios.insert_one(usuario)
        
        # ===== NUEVO: Enviar correo de bienvenida =====
        enviar_correo_bienvenida(email, nombre)
        
        return redirect(url_for("login"))

    return render_template("register.html")
# =========================
# LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return render_template("login.html", error="Por favor ingresa email y contraseña")

        # 1. Verificar si es administrador (buscar por username o email)
        admin = administradores.find_one({
            "$or": [
                {"username": email},
                {"email": email}
            ]
        })
        
        if admin:
            if check_password_hash(admin["password"], password):
                session["user_id"] = str(admin["_id"])
                session["nombre"] = admin["nombre"]
                session["tipo"] = "admin"
                session["username"] = admin["username"]
                print(f"✅ Admin logueado: {admin['username']}")  # Debug
                return redirect(url_for("dashboard_admin"))
            else:
                print(f"❌ Contraseña incorrecta para admin: {email}")  # Debug
                return render_template("login.html", error="Contraseña incorrecta")

        # 2. Verificar si es usuario normal (cliente o restaurante)
        usuario = usuarios.find_one({"email": email})
        if usuario:
            if check_password_hash(usuario["password"], password):
                session["user_id"] = str(usuario["_id"])
                session["nombre"] = usuario["nombre"]
                session["tipo"] = usuario["tipo"]
                session["email"] = usuario["email"]
                
                print(f"✅ Usuario logueado: {usuario['email']} - Tipo: {usuario['tipo']}")  # Debug
                
                if usuario["tipo"] == "cliente":
                    return redirect(url_for("dashboard_cliente"))
                elif usuario["tipo"] == "restaurante":
                    return redirect(url_for("dashboard_restaurante"))
                else:
                    return render_template("login.html", error="Tipo de usuario no válido")
            else:
                print(f"❌ Contraseña incorrecta para usuario: {email}")  # Debug
                return render_template("login.html", error="Contraseña incorrecta")

        # Si llegamos aquí, el usuario no existe
        print(f"❌ Usuario no encontrado: {email}")  # Debug
        return render_template("login.html", error="Usuario no encontrado")

    return render_template("login.html")

# =========================
# ADMIN - CREAR RESTAURANTE (CON CLOUDINARY)
# =========================
@app.route("/admin/crear-restaurante", methods=["GET", "POST"])
def admin_crear_restaurante():
    if session.get("tipo") != "admin":
        return redirect(url_for("login"))

    if request.method == "POST":
        print("="*50)
        print("📝 CREANDO NUEVO RESTAURANTE")
        
        nombre = request.form.get("nombre")
        email = request.form.get("email")
        password = generate_password_hash(request.form.get("password"))
        telefono = request.form.get("telefono")
        direccion = request.form.get("direccion")
        descripcion = request.form.get("descripcion")
        sitio_web = request.form.get("sitio_web")
        latitud = request.form.get("latitud")
        longitud = request.form.get("longitud")
        
        # ===== PROCESAR IMAGEN CON CLOUDINARY =====
        imagen_restaurante = request.files.get("imagen_restaurante")
        imagen_url = None
        imagen_public_id = None

        if imagen_restaurante and imagen_restaurante.filename != "":
            print(f"📸 Subiendo imagen a Cloudinary: {imagen_restaurante.filename}")
            
            resultado = subir_a_cloudinary(imagen_restaurante, "restaurantes")
            
            if resultado:
                imagen_url = resultado['url']
                imagen_public_id = resultado['public_id']
                print(f"✅ Imagen subida a Cloudinary correctamente")
            else:
                print(f"⚠️ Falló la subida a Cloudinary")
        else:
            print("📸 No se recibió imagen")

        if not nombre or not email or not password:
            return "⚠️ Todos los campos obligatorios"

        # Verificar si ya existe
        if usuarios.find_one({"email": email}):
            return "⚠️ Ya existe un usuario con ese email"

        # Procesar redes sociales
        redes_sociales = {}
        i = 0
        while True:
            tipo = request.form.get(f"red_social_tipo_{i}")
            url = request.form.get(f"red_social_url_{i}")
            if tipo and url:
                redes_sociales[tipo] = url
                i += 1
            else:
                break

        # Crear usuario restaurante
        usuario = {
            "nombre": nombre,
            "email": email,
            "password": password,
            "tipo": "restaurante",
            "fecha_registro": datetime.datetime.now(datetime.UTC),
            "creado_por": session.get("user_id")
        }
        result = usuarios.insert_one(usuario)
        print(f"✅ Usuario creado con ID: {result.inserted_id}")

        # Crear objeto de ubicación
        ubicacion = None
        if latitud and longitud:
            try:
                ubicacion = {
                    "lat": float(latitud),
                    "lng": float(longitud)
                }
            except:
                ubicacion = None

        # Crear perfil de restaurante
        restaurante_data = {
            "nombre": nombre,
            "email": email,
            "telefono": telefono,
            "direccion": direccion,
            "descripcion": descripcion,
            "sitio_web": sitio_web,
            "redes_sociales": redes_sociales,
            "ubicacion": ubicacion,
            "imagen_restaurante": None,  # Ya no usamos nombre local
            "imagen_url": imagen_url,
            "imagen_public_id": imagen_public_id,
            "menu": [],
            "usuario_id": result.inserted_id,
            "fecha_creacion": datetime.datetime.now(datetime.UTC)
        }
        
        result_rest = restaurantes.insert_one(restaurante_data)
        print(f"✅ Restaurante creado con ID: {result_rest.inserted_id}")
        print(f"🖼️ Imagen URL guardada: {imagen_url}")
        print("="*50)
        
        return redirect(url_for("dashboard_admin"))

    return render_template("admin_crear_restaurante.html", google_maps_key=GOOGLE_API_KEY)

# =========================
# ADMIN - EDITAR RESTAURANTE (CON CLOUDINARY)
# =========================
@app.route("/admin/editar-restaurante/<restaurante_id>", methods=["GET", "POST"])
def admin_editar_restaurante(restaurante_id):
    if session.get("tipo") != "admin":
        return redirect(url_for("login"))

    restaurante = restaurantes.find_one({"_id": ObjectId(restaurante_id)})
    if not restaurante:
        return "Restaurante no encontrado"

    if request.method == "POST":
        print("="*50)
        print(f"📝 EDITANDO RESTAURANTE: {restaurante_id}")
        
        nombre = request.form.get("nombre")
        email = request.form.get("email")
        telefono = request.form.get("telefono")
        direccion = request.form.get("direccion")
        descripcion = request.form.get("descripcion")
        sitio_web = request.form.get("sitio_web")
        latitud = request.form.get("latitud")
        longitud = request.form.get("longitud")
        
        # ===== PROCESAR IMAGEN CON CLOUDINARY =====
        imagen_restaurante = request.files.get("imagen_restaurante")
        imagen_url = restaurante.get("imagen_url")  # Mantener la actual
        imagen_public_id = restaurante.get("imagen_public_id")

        if imagen_restaurante and imagen_restaurante.filename != "":
            print(f"📸 Subiendo nueva imagen a Cloudinary: {imagen_restaurante.filename}")
            
            resultado = subir_a_cloudinary(imagen_restaurante, "restaurantes")
            
            if resultado:
                imagen_url = resultado['url']
                imagen_public_id = resultado['public_id']
                
                # Eliminar imagen anterior de Cloudinary
                if restaurante.get("imagen_public_id"):
                    try:
                        cloudinary.uploader.destroy(restaurante["imagen_public_id"])
                        print(f"🗑️ Imagen anterior eliminada de Cloudinary")
                    except Exception as e:
                        print(f"⚠️ No se pudo eliminar imagen anterior: {e}")
        else:
            print("📸 No se recibió imagen nueva, se mantiene la actual")

        # Procesar ubicación
        ubicacion = None
        if latitud and longitud:
            try:
                ubicacion = {
                    "lat": float(latitud),
                    "lng": float(longitud)
                }
            except:
                ubicacion = None

        # Procesar redes sociales
        redes_sociales = {}
        i = 0
        while True:
            tipo = request.form.get(f"red_social_tipo_{i}")
            url = request.form.get(f"red_social_url_{i}")
            if tipo and url:
                redes_sociales[tipo] = url
                i += 1
            else:
                break

        # Actualizar restaurante
        restaurantes.update_one(
            {"_id": ObjectId(restaurante_id)},
            {"$set": {
                "nombre": nombre,
                "email": email,
                "telefono": telefono,
                "direccion": direccion,
                "descripcion": descripcion,
                "sitio_web": sitio_web,
                "redes_sociales": redes_sociales,
                "ubicacion": ubicacion,
                "imagen_restaurante": None,
                "imagen_url": imagen_url,
                "imagen_public_id": imagen_public_id
            }}
        )
        
        print(f"✅ Restaurante actualizado")
        print(f"🖼️ Imagen URL final: {imagen_url}")
        print("="*50)

        # Actualizar también en usuarios
        usuarios.update_one(
            {"email": restaurante["email"]},
            {"$set": {
                "nombre": nombre,
                "email": email
            }}
        )

        return redirect(url_for("dashboard_admin"))

    return render_template("admin_editar_restaurante.html", restaurante=restaurante, google_maps_key=GOOGLE_API_KEY)

# =========================
# ADMIN - ELIMINAR RESTAURANTE
# =========================
@app.route("/admin/eliminar-restaurante/<restaurante_id>", methods=["POST"])
def admin_eliminar_restaurante(restaurante_id):
    if session.get("tipo") != "admin":
        return redirect(url_for("login"))

    restaurante = restaurantes.find_one({"_id": ObjectId(restaurante_id)})
    if not restaurante:
        return "Restaurante no encontrado"

    # Eliminar imagen de Cloudinary si existe
    if restaurante.get("imagen_public_id"):
        try:
            cloudinary.uploader.destroy(restaurante["imagen_public_id"])
            print(f"🗑️ Imagen eliminada de Cloudinary")
        except Exception as e:
            print(f"⚠️ Error al eliminar imagen de Cloudinary: {e}")

    # Eliminar comentarios asociados
    comentarios.delete_many({"restaurante_id": ObjectId(restaurante_id)})
    
    # Eliminar chats asociados
    chats.delete_many({"restaurante_id": ObjectId(restaurante_id)})
    
    # Eliminar usuario asociado
    usuarios.delete_one({"email": restaurante["email"]})
    
    # Eliminar restaurante
    restaurantes.delete_one({"_id": ObjectId(restaurante_id)})

    return redirect(url_for("dashboard_admin"))

# =========================
# DASHBOARD ADMIN (CORREGIDO)
# =========================
@app.route("/dashboard-admin")
def dashboard_admin():
    if session.get("tipo") != "admin":
        return redirect(url_for("login"))

    # Estadísticas
    total_restaurantes = restaurantes.count_documents({})
    total_clientes = usuarios.count_documents({"tipo": "cliente"})
    total_comentarios = comentarios.count_documents({})
    total_chats = chats.count_documents({})

    # Lista de restaurantes
    lista_restaurantes = list(restaurantes.find().sort("fecha_creacion", -1))
    
    # Lista de clientes con información adicional
    clientes_lista = []
    for cliente in usuarios.find({"tipo": "cliente"}).sort("fecha_registro", -1):
        # Contar comentarios del cliente
        num_comentarios = comentarios.count_documents({"cliente_id": cliente["_id"]})
        # Contar chats del cliente
        num_chats = chats.count_documents({"cliente_id": cliente["_id"]})
        
        cliente_data = {
            "_id": cliente["_id"],
            "nombre": cliente["nombre"],
            "email": cliente["email"],
            "fecha_registro": cliente.get("fecha_registro"),
            "total_comentarios": num_comentarios,
            "total_chats": num_chats
        }
        clientes_lista.append(cliente_data)

    # ===== TODOS LOS COMENTARIOS (CORREGIDO) =====
    todos_comentarios = []
    try:
        cursor = comentarios.find().sort("fecha", -1).limit(50)
        for comentario in cursor:
            # Buscar nombre del restaurante
            restaurante = restaurantes.find_one({"_id": comentario["restaurante_id"]})
            comentario_data = {
                "_id": str(comentario["_id"]),
                "cliente_nombre": comentario.get("cliente_nombre", "Cliente"),
                "comentario": comentario["comentario"],
                "fecha": comentario.get("fecha"),
                "restaurante_nombre": restaurante["nombre"] if restaurante else "Restaurante no disponible"
            }
            todos_comentarios.append(comentario_data)
        
        print(f"✅ Comentarios cargados: {len(todos_comentarios)}")
        
    except Exception as e:
        print(f"❌ Error al cargar comentarios: {e}")
        todos_comentarios = []

    # Lista de chats
    chats_lista = []
    for chat in chats.find().sort("fecha", -1).limit(50):
        restaurante = restaurantes.find_one({"_id": chat["restaurante_id"]})
        cliente = usuarios.find_one({"_id": chat["cliente_id"]})
        
        ultimo_mensaje = chat["mensajes"][-1] if chat.get("mensajes") else None
        
        chats_lista.append({
            "_id": chat["_id"],
            "restaurante_nombre": restaurante["nombre"] if restaurante else "N/A",
            "cliente_nombre": cliente["nombre"] if cliente else "N/A",
            "total_mensajes": len(chat.get("mensajes", [])),
            "ultimo_mensaje": ultimo_mensaje.get("fecha") if ultimo_mensaje else None
        })

    return render_template(
        "dashboard_admin.html",
        nombre=session.get("nombre"),
        total_restaurantes=total_restaurantes,
        total_clientes=total_clientes,
        total_comentarios=total_comentarios,
        total_chats=total_chats,
        restaurantes=lista_restaurantes[:10], 
        clientes=clientes_lista[:20],  
        todos_comentarios=todos_comentarios,
        chats_lista=chats_lista,
        restaurantes_lista=lista_restaurantes[:10], 
    )

# =========================
# ADMIN - ELIMINAR CLIENTE
# =========================
@app.route("/admin/eliminar-cliente/<cliente_id>", methods=["POST"])
def admin_eliminar_cliente(cliente_id):
    if session.get("tipo") != "admin":
        return redirect(url_for("login"))

    try:
        # Buscar el cliente
        cliente = usuarios.find_one({"_id": ObjectId(cliente_id), "tipo": "cliente"})
        if not cliente:
            return "Cliente no encontrado"

        # 1. Eliminar todos los comentarios del cliente
        comentarios_eliminados = comentarios.delete_many({"cliente_id": ObjectId(cliente_id)})
        
        # 2. Eliminar todos los chats del cliente
        chats_eliminados = chats.delete_many({"cliente_id": ObjectId(cliente_id)})
        
        # 3. Eliminar todos los chats de platillos del cliente
        platillo_chats_eliminados = platillo_chats.delete_many({"cliente_id": ObjectId(cliente_id)})
        
        # 4. Eliminar todas las calificaciones del cliente
        calificaciones_eliminadas = calificaciones.delete_many({"cliente_id": ObjectId(cliente_id)})
        
        # 5. Finalmente, eliminar el cliente
        resultado = usuarios.delete_one({"_id": ObjectId(cliente_id)})

        if resultado.deleted_count > 0:
            print(f"✅ Cliente eliminado: {cliente['nombre']} ({cliente['email']})")
            print(f"   - Comentarios eliminados: {comentarios_eliminados.deleted_count}")
            print(f"   - Chats eliminados: {chats_eliminados.deleted_count}")
            print(f"   - Chats de platillos eliminados: {platillo_chats_eliminados.deleted_count}")
            print(f"   - Calificaciones eliminadas: {calificaciones_eliminadas.deleted_count}")
            
            return redirect(url_for("dashboard_admin", mensaje="Cliente eliminado correctamente"))
        else:
            return "Error al eliminar el cliente"

    except Exception as e:
        print(f"❌ Error al eliminar cliente: {e}")
        return "Error interno del servidor"

# =========================
# VISTA PÚBLICA DE RESTAURANTES (SIN LOGIN)
# =========================
@app.route("/restaurantes/publico")
def ver_restaurantes_publico():
    # No requiere login - cualquiera puede ver
    lista_restaurantes = list(restaurantes.find({}).limit(20))
    return render_template("restaurantes_publico.html", restaurantes=lista_restaurantes)

@app.route("/restaurante/publico/<id>")
def detalle_restaurante_publico(id):
    try:
        restaurante = restaurantes.find_one({"_id": ObjectId(id)})
    except:
        return "ID inválido"
    
    if not restaurante:
        return "Restaurante no encontrado"
    
    return render_template("detalle_restaurante_publico.html", restaurante=restaurante)

# =========================
# ADMIN - ELIMINAR COMENTARIO
# =========================
@app.route("/admin/eliminar-comentario/<comentario_id>", methods=["POST"])
def admin_eliminar_comentario(comentario_id):
    if session.get("tipo") != "admin":
        return redirect(url_for("login"))

    try:
        # Buscar el comentario
        comentario = comentarios.find_one({"_id": ObjectId(comentario_id)})
        if not comentario:
            return "Comentario no encontrado"

        # Eliminar el comentario
        resultado = comentarios.delete_one({"_id": ObjectId(comentario_id)})

        if resultado.deleted_count > 0:
            print(f"✅ Comentario eliminado: {comentario['comentario'][:50]}...")
            return redirect(url_for("dashboard_admin", mensaje="Comentario eliminado correctamente"))
        else:
            return "Error al eliminar el comentario"

    except Exception as e:
        print(f"❌ Error al eliminar comentario: {e}")
        return "Error interno del servidor"

# =========================
# DASHBOARD CLIENTE
# =========================
@app.route("/dashboard-cliente")
def dashboard_cliente():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    if session.get("tipo") != "cliente":
        return redirect(url_for("landing"))

    # Obtener publicidad activa de todos los restaurantes
    ahora = datetime.datetime.now(datetime.UTC)
    
    # Crear fecha de inicio del día (00:00:00) y fin del día (23:59:59)
    inicio_dia = datetime.datetime(ahora.year, ahora.month, ahora.day, 0, 0, 0, tzinfo=datetime.UTC)
    fin_dia = datetime.datetime(ahora.year, ahora.month, ahora.day, 23, 59, 59, tzinfo=datetime.UTC)
    
    print("="*50)
    print("🔍 DEBUG PUBLICIDAD - INICIO")
    print(f"Fecha actual: {ahora}")
    print(f"Inicio del día: {inicio_dia}")
    print(f"Fin del día: {fin_dia}")
    
    publicidad_activa = list(db.publicidad.find({
        "activa": True,
        "$or": [
            {"fecha_fin": {"$exists": False}},  # Sin fecha de fin
            {"fecha_fin": None},                 # Fecha fin null
            {"fecha_fin": {"$gte": inicio_dia}}  # Fecha fin >= hoy a las 00:00
        ]
    }).sort("fecha_creacion", -1))

    print(f"📊 Publicaciones encontradas en BD: {len(publicidad_activa)}")
    
    for i, pub in enumerate(publicidad_activa):
        print(f"\n  Publicación {i+1}:")
        print(f"    ID: {pub['_id']}")
        print(f"    Título: {pub.get('titulo')}")
        print(f"    Fecha fin: {pub.get('fecha_fin')}")

    # Enriquecer con información del restaurante
    publicidad_con_restaurante = []
    for pub in publicidad_activa:
        restaurante = restaurantes.find_one({"_id": pub["restaurante_id"]})
        if restaurante:
            pub_dict = dict(pub)
            pub_dict["restaurante_nombre"] = restaurante.get("nombre", "Restaurante")
            pub_dict["restaurante_direccion"] = restaurante.get("direccion", "")
            pub_dict["restaurante_telefono"] = restaurante.get("telefono", "")
            pub_dict["restaurante_id"] = str(restaurante["_id"])
            publicidad_con_restaurante.append(pub_dict)
            print(f"\n  ✅ Enriquecida: {pub_dict['titulo']} de {pub_dict['restaurante_nombre']}")
        else:
            print(f"\n  ❌ Restaurante no encontrado para publicación {pub.get('titulo')}")

    print(f"\n📊 Total publicaciones para template: {len(publicidad_con_restaurante)}")
    print("="*50)

    return render_template(
        "dashboard_cliente.html", 
        nombre=session.get("nombre"),
        publicidad=publicidad_con_restaurante
    )


#==========================
# DEBUG
#==========================
@app.route("/debug/publicidad")
def debug_publicidad():
    if session.get("tipo") != "admin":
        return redirect(url_for("login"))
    
    # Ver todas las publicaciones
    todas = list(db.publicidad.find({}))
    
    # Ver publicaciones activas
    ahora = datetime.datetime.now(datetime.UTC)
    activas = list(db.publicidad.find({
        "activa": True,
        "$or": [
            {"fecha_fin": {"$exists": False}},
            {"fecha_fin": None},
            {"fecha_fin": {"$gte": ahora}}
        ]
    }))
    
    resultado = {
        "total_publicaciones": len(todas),
        "publicaciones_activas": len(activas),
        "detalle_publicaciones": []
    }
    
    for pub in todas:
        restaurante = restaurantes.find_one({"_id": pub["restaurante_id"]})
        resultado["detalle_publicaciones"].append({
            "id": str(pub["_id"]),
            "restaurante": restaurante["nombre"] if restaurante else "Desconocido",
            "titulo": pub["titulo"],
            "activa": pub.get("activa", False),
            "fecha_inicio": str(pub.get("fecha_inicio")) if pub.get("fecha_inicio") else None,
            "fecha_fin": str(pub.get("fecha_fin")) if pub.get("fecha_fin") else None,
            "imagen": pub.get("imagen")
        })
    
    return resultado

@app.route("/debug/ver-publicidad")
def debug_ver_publicidad():
    if session.get("tipo") != "admin":
        return redirect(url_for("login"))
    
    from bson import ObjectId
    import datetime
    
    ahora = datetime.datetime.now(datetime.UTC)
    
    # 1. Ver todas las publicaciones
    todas = list(db.publicidad.find({}))
    
    # 2. Ver publicaciones activas (las que deberían mostrarse)
    activas = list(db.publicidad.find({
        "activa": True,
        "$or": [
            {"fecha_fin": {"$exists": False}},
            {"fecha_fin": None},
            {"fecha_fin": {"$gte": ahora}}
        ]
    }))
    
    resultado = {
        "fecha_actual": str(ahora),
        "total_publicaciones": len(todas),
        "publicaciones_activas": len(activas),
        "detalle": []
    }
    
    for pub in activas:
        restaurante = restaurantes.find_one({"_id": pub["restaurante_id"]})
        resultado["detalle"].append({
            "id": str(pub["_id"]),
            "restaurante": restaurante["nombre"] if restaurante else "Desconocido",
            "titulo": pub["titulo"],
            "tipo": pub.get("tipo"),
            "activa": pub.get("activa"),
            "fecha_inicio": str(pub.get("fecha_inicio")) if pub.get("fecha_inicio") else None,
            "fecha_fin": str(pub.get("fecha_fin")) if pub.get("fecha_fin") else None,
            "descuento": pub.get("descuento")
        })
    
    return resultado

# =========================
# DEBUG - VER IMÁGENES
# =========================
@app.route("/debug/imagenes")
def debug_imagenes():
    if session.get("tipo") != "admin":
        return redirect(url_for("login"))
    
    import os
    from pathlib import Path
    
    carpeta = os.path.join(UPLOAD_FOLDER, "restaurantes")
    resultado = {
        "carpeta": carpeta,
        "existe": os.path.exists(carpeta),
        "archivos": []
    }
    
    if os.path.exists(carpeta):
        for archivo in os.listdir(carpeta):
            ruta_completa = os.path.join(carpeta, archivo)
            resultado["archivos"].append({
                "nombre": archivo,
                "tamaño": os.path.getsize(ruta_completa),
                "modificado": datetime.datetime.fromtimestamp(os.path.getmtime(ruta_completa)).strftime('%Y-%m-%d %H:%M:%S')
            })
    
    return resultado

# =========================
# DASHBOARD RESTAURANTE
# =========================
@app.route("/dashboard-restaurante")
def dashboard_restaurante():
    if session.get("user_id") is None:
        return redirect(url_for("login"))
    if session.get("tipo") != "restaurante":
        return redirect(url_for("landing"))

    usuario = usuarios.find_one({"_id": ObjectId(session["user_id"])})
    restaurante = restaurantes.find_one({"email": usuario["email"]})

    if not restaurante:
        return redirect(url_for("login"))

    # ===== 1. OBTENER CHATS DE PLATILLOS =====
    chats_platillos = list(platillo_chats.find({"restaurante_id": restaurante["_id"]}).sort("fecha_inicio", -1))

    # ===== 2. OBTENER CHATS GENERALES =====
    chats_generales = list(chats.find({"restaurante_id": restaurante["_id"]}).sort("fecha", -1))

    # Procesar la información de clientes para el panel lateral
    clientes_chat = {}

    # 2.1 Procesar chats generales
    for chat in chats_generales:
        cliente_id = str(chat["cliente_id"])
        if cliente_id not in clientes_chat:
            cliente = usuarios.find_one({"_id": chat["cliente_id"]})
            clientes_chat[cliente_id] = {
                "cliente_id": cliente_id,
                "cliente_nombre": cliente.get("nombre", "Cliente") if cliente else "Cliente",
                "chats_por_platillo": []
            }
        
        # Agregar chat general como si fuera un "platillo" especial
        ultimo_mensaje = chat["mensajes"][-1] if chat.get("mensajes") else None
        clientes_chat[cliente_id]["chats_por_platillo"].append({
            "chat_id": str(chat["_id"]),
            "platillo_nombre": "💬 Chat General",
            "platillo_index": -1,  # -1 indica que es chat general
            "ultimo_mensaje": ultimo_mensaje.get("texto")[:50] + "..." if ultimo_mensaje and len(ultimo_mensaje.get("texto", "")) > 50 else (ultimo_mensaje.get("texto") if ultimo_mensaje else "Sin mensajes"),
            "ultimo_mensaje_fecha": ultimo_mensaje.get("fecha") if ultimo_mensaje else None,
            "ultimo_mensaje_tipo": ultimo_mensaje.get("tipo") if ultimo_mensaje else None,
            "total_mensajes": len(chat.get("mensajes", []))
        })

    # 2.2 Procesar chats de platillos
    for chat in chats_platillos:
        cliente_id = str(chat["cliente_id"])
        if cliente_id not in clientes_chat:
            cliente = usuarios.find_one({"_id": chat["cliente_id"]})
            clientes_chat[cliente_id] = {
                "cliente_id": cliente_id,
                "cliente_nombre": chat.get("cliente_nombre", cliente.get("nombre", "Cliente") if cliente else "Cliente"),
                "chats_por_platillo": []
            }
        
        ultimo_mensaje = chat["mensajes"][-1] if chat.get("mensajes") else None
        clientes_chat[cliente_id]["chats_por_platillo"].append({
            "chat_id": str(chat["_id"]),
            "platillo_nombre": f"🍽️ {chat['platillo_nombre']}",
            "platillo_index": chat["platillo_index"],
            "ultimo_mensaje": ultimo_mensaje.get("texto")[:50] + "..." if ultimo_mensaje and len(ultimo_mensaje.get("texto", "")) > 50 else (ultimo_mensaje.get("texto") if ultimo_mensaje else "Sin mensajes"),
            "ultimo_mensaje_fecha": ultimo_mensaje.get("fecha") if ultimo_mensaje else None,
            "ultimo_mensaje_tipo": ultimo_mensaje.get("tipo") if ultimo_mensaje else None,
            "total_mensajes": len(chat.get("mensajes", []))
        })

    # Ordenar chats por fecha del último mensaje (más reciente primero)
    for cliente in clientes_chat.values():
        cliente["chats_por_platillo"].sort(
            key=lambda x: x["ultimo_mensaje_fecha"] if x["ultimo_mensaje_fecha"] else datetime.datetime.min,
            reverse=True
        )

    # Convertir a lista para el template
    clientes_chat_lista = list(clientes_chat.values())
    # Ordenar clientes por el chat más reciente
    clientes_chat_lista.sort(
        key=lambda x: x["chats_por_platillo"][0]["ultimo_mensaje_fecha"] if x["chats_por_platillo"] and x["chats_por_platillo"][0]["ultimo_mensaje_fecha"] else datetime.datetime.min,
        reverse=True
    )

    # Ver si hay un chat seleccionado (puede ser general o de platillo)
    chat_seleccionado_id = request.args.get("chat_id")
    chat_selected = None

    if chat_seleccionado_id:
        try:
            # Buscar primero en chats de platillos
            chat_platillo = platillo_chats.find_one({"_id": ObjectId(chat_seleccionado_id)})
            if chat_platillo:
                cliente = usuarios.find_one({"_id": chat_platillo["cliente_id"]})
                chat_selected = {
                    "chat_id": chat_seleccionado_id,
                    "tipo": "platillo",
                    "cliente_id": str(chat_platillo["cliente_id"]),
                    "cliente_nombre": chat_platillo.get("cliente_nombre", cliente.get("nombre", "Cliente") if cliente else "Cliente"),
                    "platillo_nombre": chat_platillo["platillo_nombre"],
                    "platillo_index": chat_platillo["platillo_index"],
                    "mensajes": chat_platillo.get("mensajes", [])
                }
            else:
                # Buscar en chats generales
                chat_general = chats.find_one({"_id": ObjectId(chat_seleccionado_id)})
                if chat_general:
                    cliente = usuarios.find_one({"_id": chat_general["cliente_id"]})
                    chat_selected = {
                        "chat_id": chat_seleccionado_id,
                        "tipo": "general",
                        "cliente_id": str(chat_general["cliente_id"]),
                        "cliente_nombre": cliente.get("nombre", "Cliente") if cliente else "Cliente",
                        "platillo_nombre": "Chat General",
                        "mensajes": chat_general.get("mensajes", [])
                    }
        except Exception as e:
            print(f"Error al obtener chat: {e}")

    # Traer comentarios
    comentarios = list(db.comentarios.find({"restaurante_id": restaurante["_id"]}).sort("fecha", -1))

    return render_template(
        "dashboard_restaurante.html",
        nombre=session.get("nombre"),
        restaurante=restaurante,
        menu=restaurante.get("menu", []) if restaurante else [],
        chat={"clientes": clientes_chat_lista},
        comentarios=comentarios,
        chat_selected=chat_selected,
        google_maps_key=GOOGLE_API_KEY
    )


@app.route("/restaurantes")
def ver_restaurantes():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    if session.get("tipo") != "cliente":
        return redirect(url_for("landing"))

    lista_restaurantes = list(restaurantes.find({}))

    return render_template(
        "restaurantes.html",
        restaurantes=lista_restaurantes
    )

# =========================
# DETALLE DE PLATILLO PARA RESTAURANTES (VER INFORMACIÓN)
# =========================
@app.route("/dashboard-restaurante/platillo/<int:platillo_index>")
def detalle_platillo_restaurante(platillo_index):
    if session.get("user_id") is None or session.get("tipo") != "restaurante":
        return redirect(url_for("login"))

    usuario = usuarios.find_one({"_id": ObjectId(session["user_id"])})
    restaurante = restaurantes.find_one({"email": usuario["email"]})

    if not restaurante:
        return redirect(url_for("login"))

    menu = restaurante.get("menu", [])
    if platillo_index >= len(menu):
        return "Platillo no encontrado"

    platillo = menu[platillo_index]

    return render_template(
        "detalle_platillo_restaurante.html",
        restaurante=restaurante,
        platillo=platillo,
        platillo_index=platillo_index
    )

# =========================
# DETALLE RESTAURANTE PARA CLIENTES
# =========================
@app.route("/restaurante/<id>")
def detalle_restaurante(id):
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    try:
        restaurante = restaurantes.find_one({"_id": ObjectId(id)})
    except:
        return "ID inválido"

    if not restaurante:
        return "Restaurante no encontrado"

    # Asegurar campos de calificación
    campos_calificacion = ['promedio_general', 'promedio_comida', 'promedio_servicio', 'total_calificaciones']
    for campo in campos_calificacion:
        if campo not in restaurante:
            restaurante[campo] = 0.0 if 'promedio' in campo else 0

    # Obtener publicidad activa de ESTE restaurante
    ahora = datetime.datetime.now(datetime.UTC)
    print(f"🔍 Buscando publicidad para restaurante {id}")  # Debug
    
    publicidad_activa = list(db.publicidad.find({
        "restaurante_id": ObjectId(id),
        "activa": True,
        "$or": [
            {"fecha_fin": {"$exists": False}},
            {"fecha_fin": None},
            {"fecha_fin": {"$gte": ahora}}
        ]
    }).sort("fecha_creacion", -1))
    
    print(f"📊 Publicaciones encontradas para este restaurante: {len(publicidad_activa)}")  # Debug
    restaurante['publicidad_activa'] = publicidad_activa

    # Traer TODOS los comentarios del restaurante
    todos_comentarios = list(db.comentarios.find({"restaurante_id": ObjectId(id)}).sort("fecha", -1))

    # Traer SOLO el chat de este cliente con el restaurante
    chat_cliente = db.chats.find_one({
        "restaurante_id": ObjectId(id),
        "cliente_id": ObjectId(session["user_id"])
    })

    return render_template(
        "detalle_restaurante.html",
        restaurante=restaurante,
        comentarios=todos_comentarios,
        chat=chat_cliente,
        session=session,
        google_maps_key=GOOGLE_API_KEY
    )

# =========================
# DETALLE RESTAURANTE DESDE PUBLICIDAD (CON CONTADOR DE VISTAS)
# =========================
@app.route("/publicidad/<pub_id>/restaurante/<rest_id>")
def detalle_restaurante_desde_publicidad(pub_id, rest_id):
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    # Incrementar contador de vistas
    try:
        publicidad.update_one(
            {"_id": ObjectId(pub_id)},
            {"$inc": {"vistas": 1}}
        )
        print(f"✅ Vista registrada para publicación {pub_id}")
    except Exception as e:
        print(f"❌ Error al registrar vista: {e}")

    # Redirigir al detalle normal del restaurante
    return redirect(url_for("detalle_restaurante", id=rest_id))


# =========================
# RUTA PARA ENVIAR MENSAJE DESDE EL RESTAURANTE
# =========================
@app.route("/dashboard-restaurante/chat/<id>", methods=["POST"])
def enviar_chat_restaurante(id):
    if session.get("user_id") is None or session.get("tipo") != "restaurante":
        return redirect(url_for("login"))

    mensaje = request.form.get("mensaje")
    cliente_id = request.args.get("cliente")
    
    if not mensaje:
        return "⚠️ Debes escribir un mensaje"
    
    if not cliente_id:
        return "⚠️ No se especificó el cliente"

    try:
        # Buscar si ya existe un chat con este cliente
        chat = db.chats.find_one({
            "restaurante_id": ObjectId(id),
            "cliente_id": ObjectId(cliente_id)
        })

        nuevo_mensaje = {
            "tipo": "Restaurante",
            "texto": mensaje,
            "fecha": datetime.datetime.utcnow()
        }

        if chat:
            # Actualizar chat existente
            db.chats.update_one(
                {"_id": chat["_id"]},
                {"$push": {"mensajes": nuevo_mensaje}}
            )
        else:
            # Crear nuevo chat
            db.chats.insert_one({
                "restaurante_id": ObjectId(id),
                "cliente_id": ObjectId(cliente_id),
                "mensajes": [nuevo_mensaje]
            })

    except Exception as e:
        print(f"Error al enviar mensaje: {e}")
        return "⚠️ Error al enviar el mensaje"

    return redirect(url_for("dashboard_restaurante", cliente=cliente_id))

# =========================
# RESTAURANTE - RESPONDER CHAT DE PLATILLO
# =========================
@app.route("/dashboard-restaurante/responder-chat-platillo/<chat_id>", methods=["POST"])
def responder_chat_platillo(chat_id):
    if session.get("user_id") is None or session.get("tipo") != "restaurante":
        return redirect(url_for("login"))

    mensaje = request.form.get("mensaje")
    
    if not mensaje:
        return "⚠️ Debes escribir un mensaje"

    try:
        # Buscar el chat de platillo
        chat = platillo_chats.find_one({"_id": ObjectId(chat_id)})
        if not chat:
            return "Chat no encontrado"

        nuevo_mensaje = {
            "tipo": "Restaurante",
            "texto": mensaje,
            "fecha": datetime.datetime.utcnow()
        }

        # Actualizar el chat
        platillo_chats.update_one(
            {"_id": ObjectId(chat_id)},
            {"$push": {"mensajes": nuevo_mensaje}}
        )

    except Exception as e:
        print(f"Error al enviar mensaje: {e}")
        return "⚠️ Error al enviar el mensaje"

    return redirect(url_for("dashboard_restaurante", chat_id=chat_id))

# =========================
# RESTAURANTE - RESPONDER CHAT GENERAL
# =========================
@app.route("/dashboard-restaurante/responder-chat-general/<chat_id>", methods=["POST"])
def responder_chat_general(chat_id):
    if session.get("user_id") is None or session.get("tipo") != "restaurante":
        return redirect(url_for("login"))

    mensaje = request.form.get("mensaje")
    
    if not mensaje:
        return "⚠️ Debes escribir un mensaje"

    try:
        # Buscar el chat general
        chat = db.chats.find_one({"_id": ObjectId(chat_id)})
        if not chat:
            return "Chat no encontrado"

        nuevo_mensaje = {
            "tipo": "Restaurante",
            "texto": mensaje,
            "fecha": datetime.datetime.utcnow()
        }

        # Actualizar el chat
        db.chats.update_one(
            {"_id": ObjectId(chat_id)},
            {"$push": {"mensajes": nuevo_mensaje}}
        )

    except Exception as e:
        print(f"Error al enviar mensaje: {e}")
        return "⚠️ Error al enviar el mensaje"

    return redirect(url_for("dashboard_restaurante", chat_id=chat_id))

# =========================
# MENU RESTAURANTE
# =========================
@app.route("/subir_menu", methods=["GET", "POST"])
def subir_menu():
    if "user_id" not in session or session["tipo"] != "restaurante":
        return redirect(url_for("login"))

    usuario = usuarios.find_one({"_id": ObjectId(session["user_id"])})
    restaurante = restaurantes.find_one({"email": usuario["email"]})

    if request.method == "POST":

        # =========================
        # DATOS GENERALES DEL LOCAL (solo si no existen)
        # =========================
        if not restaurante.get("descripcion"):
            descripcion_local = request.form.get("descripcion_local")
            ubicacion = request.form.get("ubicacion")
            telefono = request.form.get("telefono")
            redes_sociales = request.form.get("redes_sociales")

            restaurantes.update_one(
                {"_id": restaurante["_id"]},
                {"$set": {
                    "descripcion": descripcion_local,
                    "direccion": ubicacion,
                    "telefono": telefono,
                    "redes_sociales": redes_sociales
                }}
            )

        # =========================
        # DATOS DEL PLATILLO CON CLOUDINARY
        # =========================
        nombre_platillo = request.form.get("nombre_platillo")
        precio = request.form.get("precio")
        descripcion_platillo = request.form.get("descripcion_platillo")

        foto = request.files.get("foto")
        foto_url = None
        foto_public_id = None

        if foto and foto.filename != "":
            print(f"📸 Subiendo foto de platillo a Cloudinary")
            
            resultado = subir_a_cloudinary(foto, "platillos")
            
            if resultado:
                foto_url = resultado['url']
                foto_public_id = resultado['public_id']

        if nombre_platillo and precio:
            restaurantes.update_one(
                {"_id": restaurante["_id"]},
                {"$push": {
                    "menu": {
                        "nombre": nombre_platillo,
                        "precio": precio,
                        "descripcion": descripcion_platillo,
                        "foto": None,
                        "foto_url": foto_url,
                        "foto_public_id": foto_public_id
                    }
                }}
            )

        return redirect(url_for("dashboard_restaurante"))

    return render_template("subir_menu.html", restaurante=restaurante)

# =========================
# ELIMINAR PLATILLO
# =========================
@app.route("/restaurante/<restaurante_id>/eliminar/<int:platillo_index>", methods=["POST"])
def eliminar_platillo(restaurante_id, platillo_index):
    restaurante = restaurantes.find_one({"_id": ObjectId(restaurante_id)})
    if not restaurante:
        return "Restaurante no encontrado"

    menu = restaurante.get("menu", [])
    if platillo_index < len(menu):
        # Eliminar imagen de Cloudinary si existe
        platillo = menu[platillo_index]
        if platillo.get("foto_public_id"):
            try:
                cloudinary.uploader.destroy(platillo["foto_public_id"])
                print(f"🗑️ Imagen de platillo eliminada de Cloudinary")
            except Exception as e:
                print(f"⚠️ Error al eliminar imagen: {e}")
        
        menu.pop(platillo_index)
        restaurantes.update_one({"_id": restaurante["_id"]}, {"$set": {"menu": menu}})

    return redirect(url_for("dashboard_restaurante"))

# =========================
# EDITAR PLATILLO (CON CLOUDINARY)
# =========================
@app.route("/restaurante/<restaurante_id>/editar/<int:platillo_index>", methods=["GET", "POST"])
def editar_platillo(restaurante_id, platillo_index):
    restaurante = restaurantes.find_one({"_id": ObjectId(restaurante_id)})
    if not restaurante:
        return "Restaurante no encontrado"

    menu = restaurante.get("menu", [])

    if platillo_index >= len(menu):
        return "Platillo no encontrado"

    platillo = menu[platillo_index]

    if request.method == "POST":
        nombre = request.form.get("nombre_platillo")
        precio = request.form.get("precio")
        descripcion = request.form.get("descripcion_platillo")

        # ===== PROCESAR FOTO DEL PLATILLO CON CLOUDINARY =====
        foto = request.files.get("foto")
        foto_url = platillo.get("foto_url")  # Mantener la actual
        foto_public_id = platillo.get("foto_public_id")

        if foto and foto.filename != "":
            print(f"📸 Subiendo nueva foto a Cloudinary")
            
            resultado = subir_a_cloudinary(foto, "platillos")
            
            if resultado:
                foto_url = resultado['url']
                foto_public_id = resultado['public_id']
                
                # Eliminar imagen anterior de Cloudinary
                if platillo.get("foto_public_id"):
                    try:
                        cloudinary.uploader.destroy(platillo["foto_public_id"])
                        print(f"🗑️ Imagen anterior eliminada de Cloudinary")
                    except Exception as e:
                        print(f"⚠️ No se pudo eliminar imagen anterior: {e}")

        # Actualizar platillo
        platillo["nombre"] = nombre
        platillo["precio"] = precio
        platillo["descripcion"] = descripcion
        platillo["foto"] = None
        platillo["foto_url"] = foto_url
        platillo["foto_public_id"] = foto_public_id

        # Guardar de nuevo en Mongo
        menu[platillo_index] = platillo
        restaurantes.update_one({"_id": restaurante["_id"]}, {"$set": {"menu": menu}})

        return redirect(url_for("dashboard_restaurante"))

    return render_template("editar_platillo.html", platillo=platillo, restaurante_id=restaurante_id)

# =========================
# DETALLE DE PLATILLO PARA CLIENTES
# =========================
@app.route("/restaurante/<restaurante_id>/platillo/<int:platillo_index>")
def detalle_platillo_cliente(restaurante_id, platillo_index):
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    try:
        restaurante = restaurantes.find_one({"_id": ObjectId(restaurante_id)})
    except:
        return "ID inválido"

    if not restaurante:
        return "Restaurante no encontrado"

    menu = restaurante.get("menu", [])
    if platillo_index >= len(menu):
        return "Platillo no encontrado"

    platillo = menu[platillo_index]
    
    # Obtener el chat ESPECÍFICO de este cliente para ESTE platillo
    chat_key = f"{restaurante_id}_{platillo_index}_{session['user_id']}"
    
    chat_platillo = platillo_chats.find_one({
        "chat_key": chat_key
    })

    return render_template(
        "detalle_platillo_cliente.html",
        restaurante=restaurante,
        platillo=platillo,
        platillo_index=platillo_index,
        chat=chat_platillo 
    )

# =========================
# COMENTARIOS-CLIENTES CON CALIFICACIÓN
# =========================
@app.route("/restaurante/<id>/comentario", methods=["POST"])
def agregar_comentario_con_calificacion(id):
    if session.get("user_id") is None or session.get("tipo") != "cliente":
        return redirect(url_for("login"))

    mensaje = request.form.get("mensaje")
    calificacion_comida = request.form.get("calificacion_comida")
    calificacion_servicio = request.form.get("calificacion_servicio")
    
    if not mensaje:
        return "⚠️ Debes escribir un comentario"
    
    if not calificacion_comida or not calificacion_servicio:
        return "⚠️ Debes calificar la comida y el servicio"

    # Guardar comentario
    comentario = {
        "restaurante_id": ObjectId(id),
        "cliente_id": ObjectId(session["user_id"]),
        "cliente_nombre": session.get("nombre"),
        "comentario": mensaje,
        "fecha": datetime.datetime.utcnow()
    }
    db.comentarios.insert_one(comentario)

    # Guardar calificación
    calificacion = {
        "restaurante_id": ObjectId(id),
        "cliente_id": ObjectId(session["user_id"]),
        "cliente_nombre": session.get("nombre"),
        "comida": int(calificacion_comida),
        "servicio": int(calificacion_servicio),
        "fecha": datetime.datetime.utcnow()
    }
    db.calificaciones.insert_one(calificacion)

    # Actualizar promedio del restaurante
    actualizar_promedio_restaurante(id)

    return redirect(url_for("detalle_restaurante", id=id))

def actualizar_promedio_restaurante(restaurante_id):
    """Calcula y actualiza el promedio de calificaciones del restaurante"""
    todas_calif = list(db.calificaciones.find({"restaurante_id": ObjectId(restaurante_id)}))
    
    if todas_calif:
        suma_comida = sum(c["comida"] for c in todas_calif)
        suma_servicio = sum(c["servicio"] for c in todas_calif)
        total = len(todas_calif)
        
        promedio_comida = suma_comida / total
        promedio_servicio = suma_servicio / total
        promedio_general = (promedio_comida + promedio_servicio) / 2
        
        restaurantes.update_one(
            {"_id": ObjectId(restaurante_id)},
            {"$set": {
                "promedio_comida": round(promedio_comida, 1),
                "promedio_servicio": round(promedio_servicio, 1),
                "promedio_general": round(promedio_general, 1),
                "total_calificaciones": total
            }}
        )

# =========================
# PUBLICIDAD Y OFERTAS DEL RESTAURANTE (CON CLOUDINARY)
# =========================
@app.route("/dashboard-restaurante/publicidad", methods=["GET", "POST"])
def gestionar_publicidad():
    if session.get("user_id") is None or session.get("tipo") != "restaurante":
        return redirect(url_for("login"))

    usuario = usuarios.find_one({"_id": ObjectId(session["user_id"])})
    restaurante = restaurantes.find_one({"email": usuario["email"]})

    if request.method == "POST":
        titulo = request.form.get("titulo")
        descripcion = request.form.get("descripcion")
        tipo = request.form.get("tipo")
        fecha_inicio = request.form.get("fecha_inicio")
        fecha_fin = request.form.get("fecha_fin")
        descuento = request.form.get("descuento")
        
        # ===== PROCESAR IMAGEN DE PUBLICIDAD CON CLOUDINARY =====
        imagen = request.files.get("imagen")
        imagen_url = None
        imagen_public_id = None
        
        if imagen and imagen.filename != "":
            print(f"📸 Subiendo imagen de publicidad a Cloudinary")
            
            resultado = subir_a_cloudinary(imagen, "publicidad")
            
            if resultado:
                imagen_url = resultado['url']
                imagen_public_id = resultado['public_id']

        publicacion = {
            "restaurante_id": restaurante["_id"],
            "restaurante_nombre": restaurante["nombre"],
            "titulo": titulo,
            "descripcion": descripcion,
            "tipo": tipo,
            "fecha_inicio": datetime.datetime.strptime(fecha_inicio, "%Y-%m-%d") if fecha_inicio else None,
            "fecha_fin": datetime.datetime.strptime(fecha_fin, "%Y-%m-%d") if fecha_fin else None,
            "descuento": descuento,
            "imagen": None,  # Ya no usamos nombre local
            "imagen_url": imagen_url,
            "imagen_public_id": imagen_public_id,
            "activa": True,
            "fecha_creacion": datetime.datetime.now(datetime.UTC),
            "vistas": 0
        }
        
        result = publicidad.insert_one(publicacion)
        print(f"✅ Publicación creada con ID: {result.inserted_id}")
        print(f"🖼️ Imagen URL guardada: {imagen_url}")
        
        return redirect(url_for("gestionar_publicidad"))

    # Obtener publicaciones
    mis_publicaciones = list(publicidad.find({
        "restaurante_id": restaurante["_id"]
    }).sort("fecha_creacion", -1))

    return render_template(
        "publicidad_restaurante.html",
        restaurante=restaurante,
        publicaciones=mis_publicaciones
    )

# =========================
# DESACTIVAR PUBLICIDAD (CON ELIMINACIÓN DE CLOUDINARY)
# =========================
@app.route("/dashboard-restaurante/publicidad/desactivar/<publicidad_id>")
def desactivar_publicidad(publicidad_id):
    if session.get("user_id") is None or session.get("tipo") != "restaurante":
        return redirect(url_for("login"))
    
    try:
        publicacion = publicidad.find_one({"_id": ObjectId(publicidad_id)})
        if publicacion and publicacion.get("imagen_public_id"):
            # Eliminar de Cloudinary
            cloudinary.uploader.destroy(publicacion["imagen_public_id"])
            print(f"🗑️ Imagen eliminada de Cloudinary")
        
        # Desactivar en BD
        publicidad.update_one(
            {"_id": ObjectId(publicidad_id)},
            {"$set": {"activa": False}}
        )
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return redirect(url_for("gestionar_publicidad"))

# =========================
# CHATS-CLIENTE-REST
# =========================
@app.route("/restaurante/<id>/chats", methods=["POST"])
def enviar_chat(id):
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    mensaje = request.form.get("mensaje")
    
    if not mensaje:
        return "⚠️ Debes escribir un mensaje"

    try:
        # Buscar si ya existe un chat entre este cliente y el restaurante
        chat = db.chats.find_one({
            "restaurante_id": ObjectId(id),
            "cliente_id": ObjectId(session["user_id"])
        })

        nuevo_mensaje = {
            "tipo": "Cliente",
            "texto": mensaje,
            "fecha": datetime.datetime.utcnow()
        }

        if chat:
            db.chats.update_one(
                {"_id": chat["_id"]},
                {"$push": {"mensajes": nuevo_mensaje}}
            )
        else:
            db.chats.insert_one({
                "restaurante_id": ObjectId(id),
                "cliente_id": ObjectId(session["user_id"]),
                "mensajes": [nuevo_mensaje]
            })

    except Exception as e:
        print(f"Error al enviar mensaje: {e}")
        return "⚠️ Error al enviar el mensaje"

    # Redirigir a la página anterior (detalle del platillo o restaurante)
    referer = request.referrer
    if referer:
        return redirect(referer)
    return redirect(url_for("detalle_restaurante", id=id))

# =========================
# CONFIGURACIÓN IA POR PLATILLO
# =========================
@app.route("/restaurante/<restaurante_id>/platillo/<int:platillo_index>/configurar-ia", methods=["GET", "POST"])
def configurar_ia_platillo(restaurante_id, platillo_index):
    if session.get("user_id") is None or session.get("tipo") != "restaurante":
        return redirect(url_for("login"))

    # Verificar que el restaurante existe y pertenece al usuario
    usuario = usuarios.find_one({"_id": ObjectId(session["user_id"])})
    restaurante = restaurantes.find_one({"email": usuario["email"]})
    
    if str(restaurante["_id"]) != restaurante_id:
        return "No autorizado"

    # Obtener el platillo
    menu = restaurante.get("menu", [])
    if platillo_index >= len(menu):
        return "Platillo no encontrado"
    
    platillo = menu[platillo_index]

    if request.method == "POST":
        # Procesar ingredientes (separar por líneas)
        ingredientes_text = request.form.get("ingredientes", "")
        ingredientes = [i.strip() for i in ingredientes_text.split("\n") if i.strip()]
        
        # Procesar alérgenos (separar por comas)
        alergenos_text = request.form.get("alergenos", "")
        alergenos = [a.strip() for a in alergenos_text.split(",") if a.strip()]
        
        # Procesar personalizaciones
        personalizaciones_text = request.form.get("personalizaciones", "")
        personalizaciones = [p.strip() for p in personalizaciones_text.split("\n") if p.strip()]
        
        # Procesar FAQs (formato: pregunta|respuesta)
        faqs_text = request.form.get("faqs", "")
        faqs = []
        for linea in faqs_text.split("\n"):
            if "|" in linea:
                pregunta, respuesta = linea.split("|", 1)
                faqs.append({
                    "pregunta": pregunta.strip(),
                    "respuesta": respuesta.strip()
                })
        
        # Guardar configuración
        config = {
            "restaurante_id": ObjectId(restaurante_id),
            "restaurante_nombre": restaurante["nombre"],
            "platillo_index": platillo_index,
            "platillo_nombre": platillo["nombre"],
            "ingredientes": ingredientes,
            "alergenos": alergenos,
            "personalizaciones": personalizaciones,
            "faqs": faqs,
            "actualizado": datetime.datetime.now(datetime.UTC)
        }
        
        ia_conocimiento.update_one(
            {
                "restaurante_id": ObjectId(restaurante_id),
                "platillo_index": platillo_index
            },
            {"$set": config},
            upsert=True
        )
        
        return redirect(url_for("detalle_platillo_restaurante", 
                                restaurante_id=restaurante_id, 
                                platillo_index=platillo_index))

    # GET - Mostrar formulario con datos existentes
    config_existente = ia_conocimiento.find_one({
        "restaurante_id": ObjectId(restaurante_id),
        "platillo_index": platillo_index
    })

    return render_template(
        "configurar_ia_platillo.html",
        restaurante=restaurante,
        platillo=platillo,
        platillo_index=platillo_index,
        config=config_existente
    )

# =========================
# CHAT IA POR PLATILLO (VERSIÓN LEGACY)
# =========================
@app.route("/api/chat-ia-platillo", methods=["POST"])
def chat_ia_platillo():
    if session.get("user_id") is None:
        return jsonify({"error": "No autorizado"}), 401

    data = request.json
    restaurante_id = data.get("restaurante_id")
    platillo_index = data.get("platillo_index")
    mensaje = data.get("mensaje")
    historial = data.get("historial", [])  # Historial de la conversación

    if not all([restaurante_id, platillo_index is not None, mensaje]):
        return jsonify({"error": "Faltan datos"}), 400

    try:
        # 1. Obtener información del restaurante y platillo
        restaurante = restaurantes.find_one({"_id": ObjectId(restaurante_id)})
        if not restaurante:
            return jsonify({"error": "Restaurante no encontrado"}), 404
        
        menu = restaurante.get("menu", [])
        if platillo_index >= len(menu):
            return jsonify({"error": "Platillo no encontrado"}), 404
        
        platillo = menu[platillo_index]
        
        # 2. Obtener configuración IA del platillo
        config_ia = ia_conocimiento.find_one({
            "restaurante_id": ObjectId(restaurante_id),
            "platillo_index": platillo_index
        })
        
        # 3. Construir el contexto para la IA
        contexto = f"""Eres un asistente virtual experto en gastronomía para el restaurante "{restaurante['nombre']}".

INFORMACIÓN DEL RESTAURANTE:
- Nombre: {restaurante['nombre']}
- Dirección: {restaurante.get('direccion', 'No especificada')}
- Teléfono: {restaurante.get('telefono', 'No especificado')}

INFORMACIÓN DEL PLATILLO "{platillo['nombre']}":
- Descripción: {platillo.get('descripcion', 'No disponible')}
- Precio: ${platillo.get('precio', 'No disponible')}

"""

        if config_ia:
            if config_ia.get("ingredientes"):
                contexto += f"\nINGREDIENTES:\n- " + "\n- ".join(config_ia["ingredientes"]) + "\n"
            
            if config_ia.get("alergenos"):
                contexto += f"\nALÉRGENOS A CONSIDERAR:\n- " + "\n- ".join(config_ia["alergenos"]) + "\n"
            
            if config_ia.get("personalizaciones"):
                contexto += f"\nPERSONALIZACIONES DISPONIBLES:\n- " + "\n- ".join(config_ia["personalizaciones"]) + "\n"
            
            if config_ia.get("faqs"):
                contexto += f"\nPREGUNTAS FRECUENTES:\n"
                for faq in config_ia["faqs"]:
                    contexto += f"P: {faq['pregunta']}\nR: {faq['respuesta']}\n"
        else:
            contexto += "\n(No hay configuración adicional. Responde con la información básica del platillo.)\n"

        contexto += """
INSTRUCCIONES IMPORTANTES:
- Responde SIEMPRE basándote en la información proporcionada arriba
- NO inventes información que no esté en el contexto
- Sé amable, profesional y servicial
- Si no sabes algo, sugiere que contacten directamente al restaurante
- Mantén las respuestas concisas pero completas
- Si te preguntan por información que no está disponible, dilo honestamente
"""

        # 4. Construir el historial de conversación
        mensajes_api = [
            {"role": "system", "content": contexto}
        ]
        
        # Agregar historial si existe
        for msg in historial[-5:]:  # Últimos 5 mensajes para contexto
            mensajes_api.append({"role": msg["role"], "content": msg["content"]})
        
        # Agregar mensaje actual
        mensajes_api.append({"role": "user", "content": mensaje})

        # 5. Llamar a OpenAI (versión legacy)
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=mensajes_api,
            temperature=0.7,
            max_tokens=300
        )

        respuesta_ia = response.choices[0].message.content

        return jsonify({
            "respuesta": respuesta_ia,
            "platillo": platillo["nombre"],
            "restaurante": restaurante["nombre"]
        })

    except Exception as e:
        print(f"Error en chat IA: {e}")
        return jsonify({"error": "Error procesando la consulta"}), 500

# =========================
# EJECUCIÓN
# =========================
if __name__ == "__main__":
    print("="*50)
    print("🍽️  COMIDA IGUALA - SISTEMA DE RESTAURANTES")
    print("="*50)
    print(f"📁 Uploads: {UPLOAD_FOLDER}")
    print(f"🔑 OpenAI: {'✅' if OPENAI_API_KEY else '❌'}")
    print(f"🗺️ Google Maps: {'✅' if GOOGLE_API_KEY else '❌'}")
    print(f"📊 MongoDB Atlas: ✅ Conectado")
    print(f"☁️ Cloudinary: {'✅' if CLOUDINARY_CLOUD_NAME else '❌'}")
    print("="*50)
    print("🌐 Servidor iniciado en: http://127.0.0.1:5000")
    print("="*50)
    
    # En producción, debug=False
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)