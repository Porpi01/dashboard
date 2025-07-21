import streamlit as st
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime
from bson.objectid import ObjectId # Import ObjectId for MongoDB _id

# Configuración de la página de Streamlit
st.set_page_config(layout="wide")
load_dotenv()

# --- Conexión a MongoDB ---
@st.cache_resource
def init_connection():
    """Inicializa y cachea la conexión a MongoDB."""
    try:
        mongo_url = os.getenv("DATABASE_URL")
        if not mongo_url:
            st.warning("DATABASE_URL no encontrada en .env, usando la URL predeterminada.")
            # URL predeterminada - REEMPLAZA CON TU CADENA DE CONEXIÓN REAL DE MONGODB
            mongo_url = "mongodb+srv://usuario:contraseña@cluster.mongodb.net/?retryWrites=true&w=majority"
        
        client = MongoClient(mongo_url, server_api=ServerApi('1'))
        db = client["prueba"] # Se revirtió al nombre de base de datos original "prueba"
        
        # Haz un ping a la base de datos para confirmar la conexión
        client.admin.command('ping')
        st.success("✅ Conexión a MongoDB establecida con éxito!")
        return db
    except Exception as e:
        st.error(f"❌ Error al conectar a MongoDB: {e}")
        st.stop() # Detiene la aplicación si la conexión falla

db = init_connection()

# Definir colecciones
startups_collection = db["startup"] # Se revirtió al nombre de colección original "startup"
session_offers_collection = db["session_offers"]
session_requests_collection = db["session_requests"]
session_history_collection = db["session_history"] # Nueva colección para sesiones completadas

# Se eliminó el bloque para inicializar datos de startups de ejemplo

st.title("🚀 Panel de Control de Mentoría para Startups")

# --- Funciones Auxiliares ---
@st.cache_data(ttl=60) # Cachear datos por 60 segundos
def load_all_startups():
    """Carga todos los datos de las startups de la colección."""
    return list(startups_collection.find({}))

@st.cache_data(ttl=60)
def get_contacts():
    """Recupera la información de contacto de todas las startups."""
    cursor = startups_collection.find(
        {"contact": {"$ne": None, "$ne": ""}},
        {"company": 1, "contact": 1, "email": 1, "sector": 1, "_id": 0}
    )
    return pd.DataFrame(list(cursor))

# --- Secciones del Panel de Control ---

# Mostrar estadísticas clave (se puede expandir más tarde)
st.header("📊 Estadísticas Clave")
total_startups = startups_collection.count_documents({})
st.metric(label="Total de Startups Registradas", value=total_startups)

# Mostrar lista de contactos
st.header("📞 Contactos de Startups")
contacts_data = get_contacts()
if not contacts_data.empty:
    st.dataframe(contacts_data, use_container_width=True)
else:
    st.info("No hay contactos disponibles aún.")

# --- Conexiones Sugeridas ---
st.markdown("---")
st.header("🤝 Conexiones Sugeridas para Startups")

all_startups = load_all_startups()
startup_map = {s.get('company', 'Startup sin Nombre'): s for s in all_startups if 'company' in s}
startup_names = sorted(startup_map.keys())

selected_name = st.selectbox("Selecciona tu Startup:", options=startup_names, key="selected_startup_for_suggestions")

selected_startup_data = None
if selected_name:
    selected_startup_data = startup_map[selected_name]

    # --- INICIO DE LA LÓGICA DE INICIALIZACIÓN DE SESIONES ---
    # Asegurarse de que los campos de sesiones existan con valores predeterminados
    update_needed = False
    if 'sessions_allotted_to_receive' not in selected_startup_data:
        selected_startup_data['sessions_allotted_to_receive'] = 2 # Valor predeterminado de 2 sesiones
        update_needed = True
    if 'sessions_received' not in selected_startup_data:
        selected_startup_data['sessions_received'] = 0
        update_needed = True
    if 'sessions_lent' not in selected_startup_data:
        selected_startup_data['sessions_lent'] = 0
        update_needed = True

    if update_needed:
        try:
            startups_collection.update_one(
                {"_id": selected_startup_data['_id']},
                {"$set": {
                    "sessions_allotted_to_receive": selected_startup_data['sessions_allotted_to_receive'],
                    "sessions_received": selected_startup_data['sessions_received'],
                    "sessions_lent": selected_startup_data['sessions_lent']
                }}
            )
            st.success(f"Campos de sesión inicializados/actualizados para {selected_name}.")
            # Vuelve a cargar los datos para que el dashboard refleje los cambios inmediatamente
            st.rerun() # CAMBIO: st.experimental_rerun() a st.rerun()
        except Exception as e:
            st.error(f"Error al inicializar los campos de sesión para {selected_name}: {e}")
    # --- FIN DE LA LÓGICA DE INICIALIZACIÓN DE SESIONES ---

    sector = selected_startup_data.get('sector')
    stage = selected_startup_data.get('stage')

    st.subheader(f"Estado de tus Sesiones para {selected_name}:")
    col1, col2, col3 = st.columns(3)
    col1.metric("Sesiones Asignadas para Recibir", selected_startup_data.get('sessions_allotted_to_receive', 0))
    col2.metric("Sesiones Recibidas", selected_startup_data.get('sessions_received', 0))
    col3.metric("Sesiones Prestadas", selected_startup_data.get('sessions_lent', 0))


    suggestions = [s for s in all_startups if s.get('_id') != selected_startup_data.get('_id') and (
        s.get('sector') == sector or s.get('stage') == stage
    )]

    # Limitar a las 5 mejores sugerencias para brevedad
    top_5 = suggestions[:5]

    if top_5:
        st.subheader("Startups con Intereses Similares:")
        for s in top_5:
            with st.expander(f"**{s.get('company', 'Startup')}** - Sector: {s.get('sector', 'N/A')} | Etapa: {s.get('stage', 'N/A')}"):
                st.write(f"**Descripción:** {s.get('description', 'N/A')}")
                if s.get('website'):
                    web = s['website']
                    if not web.startswith(('http', 'https')):
                        web = 'https://' + web
                    st.markdown(f"**Sitio Web:** [{web}]({web})")
                st.write(f"**Correo Electrónico de Contacto:** {s.get('email', 'N/A')}")
    else:
        st.info("No se encontraron sugerencias para esta startup basadas en el sector o la etapa.")

# --- Mercado de Sesiones de Mentoría ---
st.markdown("---")
st.header("🤝 Mercado de Sesiones de Mentoría")

tabs = st.tabs(["📤 Ofrecer Sesión", "📥 Solicitar Sesión", "🔍 Ver y Emparejar Sesiones"])
startup_options_for_forms = {s.get('company'): str(s.get('_id')) for s in all_startups if 'company' in s}
startup_name_to_id = {s.get('company'): s.get('_id') for s in all_startups if 'company' in s}


# Pestaña: Ofrecer una Sesión
with tabs[0]:
    st.subheader("Ofrecer un Espacio de Sesión")
    st.info("Puedes ofrecer una de tus sesiones 'asignadas para recibir' a otra startup que lo necesite.")
    with st.form("form_offer"):
        offering_startup_name = st.selectbox(
            "Tu Startup:",
            options=list(startup_options_for_forms.keys()),
            key="offer_select"
        )
        offer_topic = st.text_input("Tema sobre el que puedes mentorizar (ej. 'Estrategias de Recaudación de Fondos', 'Ajuste Producto-Mercado'):")
        
        submit_offer = st.form_submit_button("Ofrecer Sesión")

        if submit_offer:
            offering_startup_id = startup_name_to_id.get(offering_startup_name)
            if not offering_startup_id:
                st.error("Startup seleccionada no encontrada.")
            else:
                # Recuperar datos actuales de la startup para verificar el recuento de sesiones
                current_startup_data = startups_collection.find_one({"_id": offering_startup_id})
                
                # Asegurarse de que los campos de sesión estén presentes en los datos recuperados
                # Esto es una doble verificación, ya que la lógica de inicialización superior ya debería haberlos establecido.
                sessions_allotted = current_startup_data.get('sessions_allotted_to_receive', 0)
                sessions_received = current_startup_data.get('sessions_received', 0)

                if sessions_allotted > sessions_received:
                    # Esto significa que tienen una sesión no recibida que pueden prestar
                    try:
                        session_offers_collection.insert_one({
                            "offering_startup_id": offering_startup_id,
                            "offering_startup_name": offering_startup_name,
                            "topic": offer_topic,
                            "status": "available", # 'available', 'claimed', 'used'
                            "timestamp": datetime.utcnow(),
                            "claimed_by_startup_id": None,
                            "claimed_by_startup_name": None
                        })
                        
                        # Actualizar el recuento de sesiones de la startup que ofrece
                        startups_collection.update_one(
                            {"_id": offering_startup_id},
                            {"$inc": {"sessions_lent": 1}} # Incrementar sesiones prestadas
                            # Nota: sessions_allotted_to_receive no se decrementa aquí, ya que están prestando una de sus sesiones *potenciales* a recibir.
                            # Se trata más de rastrear lo que han devuelto a la comunidad.
                        )
                        st.success(f"¡Sesión sobre '{offer_topic}' ofrecida por {offering_startup_name} con éxito!")
                        st.rerun() # CAMBIO: st.experimental_rerun() a st.rerun()
                    except Exception as e:
                        st.error(f"Error al ofrecer la sesión: {e}")
                else:
                    st.warning(f"{offering_startup_name} no tiene un espacio de sesión disponible para prestar (ya han recibido o prestado todas sus sesiones asignadas inicialmente).")

# Pestaña: Solicitar una Sesión
with tabs[1]:
    st.subheader("Solicitar una Sesión")
    st.info("Solicita una sesión sobre un tema específico. Puedes recibir hasta 2 sesiones, más cualquier sesión adicional prestada.")
    with st.form("form_request"):
        requesting_startup_name = st.selectbox(
            "Tu Startup:",
            options=list(startup_options_for_forms.keys()),
            key="req_select"
        )
        request_topic = st.text_input("Tema en el que necesitas ayuda (ej. 'Estrategia de Marketing', 'Asesoramiento Legal'):")
        
        submit_request = st.form_submit_button("Solicitar Sesión")

        if submit_request:
            requesting_startup_id = startup_name_to_id.get(requesting_startup_name)
            if not requesting_startup_id:
                st.error("Startup seleccionada no encontrada.")
            else:
                try:
                    session_requests_collection.insert_one({
                        "requesting_startup_id": requesting_startup_id,
                        "requesting_startup_name": requesting_startup_name,
                        "topic": request_topic,
                        "status": "pending", # 'pending', 'fulfilled', 'cancelled'
                        "timestamp": datetime.utcnow(),
                        "fulfilled_by_offer_id": None,
                        "fulfilled_by_startup_id": None,
                        "fulfilled_by_startup_name": None
                    })
                    st.success(f"¡Sesión sobre '{request_topic}' solicitada por {requesting_startup_name} con éxito!")
                    st.rerun() # CAMBIO: st.experimental_rerun() a st.rerun()
                except Exception as e:
                    st.error(f"Error al solicitar la sesión: {e}")


# Pestaña: Ver y Emparejar Sesiones
with tabs[2]:
    st.subheader("Ver Todas las Ofertas y Solicitudes de Sesiones")

    # Filtro para mostrar ofertas y solicitudes
    filter_startup_name = st.selectbox(
        "Filtrar por Tu Startup:",
        options=["Todas las Startups"] + list(startup_options_for_forms.keys()),
        key="filter_view_sessions"
    )
    
    filter_startup_id = None
    if filter_startup_name != "Todas las Startups":
        filter_startup_id = startup_name_to_id.get(filter_startup_name)

    st.subheader("Ofertas de Sesiones Disponibles")
    available_offers = list(session_offers_collection.find({"status": "available"}))
    
    filtered_offers = []
    if filter_startup_id:
        # Mostrar ofertas NO realizadas por la startup seleccionada, ya que no pueden reclamar las suyas propias
        filtered_offers = [
            offer for offer in available_offers 
            if offer.get('offering_startup_id') != filter_startup_id
        ]
    else:
        filtered_offers = available_offers

    if filtered_offers:
        st.dataframe(pd.DataFrame(filtered_offers)[["offering_startup_name", "topic", "timestamp"]], use_container_width=True)
        
        st.subheader("Reclamar una Sesión Disponible")
        # Crear un diccionario para una fácil búsqueda
        offer_display_options = {
            f"{offer['offering_startup_name']} - {offer['topic']} (Ofrecida el {offer['timestamp'].strftime('%Y-%m-%d %H:%M')})": str(offer['_id'])
            for offer in filtered_offers # Usar filtered_offers aquí
        }
        
        selected_offer_display = st.selectbox(
            "Selecciona una Oferta para Reclamar:",
            options=list(offer_display_options.keys()),
            key="claim_offer_select"
        )
        
        claiming_startup_name = st.selectbox(
            "Tu Startup (Reclamante):",
            options=list(startup_options_for_forms.keys()),
            key="claiming_startup_select"
        )

        if st.button("Reclamar Sesión Seleccionada"):
            if selected_offer_display and claiming_startup_name:
                selected_offer_id = ObjectId(offer_display_options[selected_offer_display])
                claiming_startup_id = startup_name_to_id.get(claiming_startup_name)

                if not claiming_startup_id:
                    st.error("Startup reclamante seleccionada no encontrada.")
                else:
                    # Evitar que una startup reclame su propia oferta
                    selected_offer_doc = session_offers_collection.find_one({"_id": selected_offer_id})
                    if selected_offer_doc and selected_offer_doc['offering_startup_id'] == claiming_startup_id:
                        st.warning("No puedes reclamar una sesión ofrecida por tu propia startup.")
                    else:
                        try:
                            # Actualizar el estado de la oferta de sesión
                            session_offers_collection.update_one(
                                {"_id": selected_offer_id},
                                {"$set": {
                                    "status": "claimed",
                                    "claimed_by_startup_id": claiming_startup_id,
                                    "claimed_by_startup_name": claiming_startup_name
                                }}
                            )

                            # Encontrar una solicitud pendiente coincidente de la startup reclamante, si la hay
                            # Priorizar el cumplimiento de una solicitud explícita si existe una para el tema
                            matching_request = session_requests_collection.find_one({
                                "requesting_startup_id": claiming_startup_id,
                                "topic": selected_offer_doc['topic'], # Coincidir por tema
                                "status": "pending"
                            })

                            if matching_request:
                                session_requests_collection.update_one(
                                    {"_id": matching_request['_id']},
                                    {"$set": {
                                        "status": "fulfilled",
                                        "fulfilled_by_offer_id": selected_offer_id,
                                        "fulfilled_by_startup_id": selected_offer_doc['offering_startup_id'],
                                        "fulfilled_by_startup_name": selected_offer_doc['offering_startup_name']
                                    }}
                                )
                            
                            # Actualizar el recuento de sesiones para ambas startups
                            # Incrementar sesiones_recibidas para la startup reclamante
                            startups_collection.update_one(
                                {"_id": claiming_startup_id},
                                {"$inc": {"sessions_received": 1}}
                            )

                            # Registrar la transacción en el historial de sesiones
                            session_history_collection.insert_one({
                                "type": "claimed_session",
                                "offer_id": selected_offer_id,
                                "offering_startup_id": selected_offer_doc['offering_startup_id'],
                                "offering_startup_name": selected_offer_doc['offering_startup_name'],
                                "claiming_startup_id": claiming_startup_id,
                                "claiming_startup_name": claiming_startup_name,
                                "topic": selected_offer_doc['topic'],
                                "timestamp": datetime.utcnow()
                            })

                            st.success(f"¡Sesión de {selected_offer_doc['offering_startup_name']} reclamada por {claiming_startup_name} con éxito!")
                            st.rerun() # CAMBIO: st.experimental_rerun() a st.rerun()
                        except Exception as e:
                            st.error(f"Error al reclamar la sesión: {e}")
            else:
                st.warning("Por favor, selecciona una oferta y tu startup para reclamar.")
    else:
        st.info("No hay ofertas de sesiones disponibles en este momento.")

    st.subheader("Solicitudes de Sesiones Pendientes")
    pending_requests = list(session_requests_collection.find({"status": "pending"}))
    
    filtered_requests = []
    if filter_startup_id:
        # Mostrar solicitudes realizadas por la startup seleccionada
        filtered_requests = [
            req for req in pending_requests 
            if req.get('requesting_startup_id') == filter_startup_id
        ]
    else:
        filtered_requests = pending_requests

    if filtered_requests:
        st.dataframe(pd.DataFrame(filtered_requests)[["requesting_startup_name", "topic", "timestamp"]], use_container_width=True)
    else:
        st.info("No hay solicitudes de sesiones pendientes en este momento.")

    st.subheader("Historial de Sesiones (Reclamaciones Completadas)")
    completed_sessions = list(session_history_collection.find({}))
    
    filtered_completed_sessions = []
    if filter_startup_id:
        # Mostrar sesiones completadas donde la startup seleccionada fue la que ofreció o la que reclamó
        filtered_completed_sessions = [
            sess for sess in completed_sessions
            if sess.get('offering_startup_id') == filter_startup_id or sess.get('claiming_startup_id') == filter_startup_id
        ]
    else:
        filtered_completed_sessions = completed_sessions

    if filtered_completed_sessions:
        history_df = pd.DataFrame(filtered_completed_sessions)
        st.dataframe(history_df[["offering_startup_name", "claiming_startup_name", "topic", "timestamp"]], use_container_width=True)
    else:
        st.info("No hay reclamaciones de sesiones completadas aún.")