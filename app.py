# app.py - TrueEye Sistema Completo (Flow + API)
import os
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import re

import aiohttp
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

# ===========================
# CONFIGURACIÓN Y LOGGING
# ===========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validar API Key de Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    logger.warning("⚠️ ANTHROPIC_API_KEY no está configurada - el servicio iniciará pero fallará al analizar")
else:
    logger.info("✅ ANTHROPIC_API_KEY configurada")

# Inicializar cliente Anthropic de forma segura
client = None
try:
    import anthropic
    if ANTHROPIC_API_KEY:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        logger.info("✅ Cliente Anthropic inicializado correctamente")
except Exception as e:
    logger.error(f"❌ Error inicializando cliente Anthropic: {e}")
    client = None

# [RESTO DEL CÓDIGO CONTINÚA IGUAL...]

# ===========================
# PROMPTS DEL FLOW ORIGINAL
# ===========================
PROMPT_SESGO_MATICES = """IMPORTANTISIMO: LA FECHA ACTUAL ES 2025.
No incluyas reflexiones internas, procesos de pensamiento o marcadores HTML/Markdown en tu respuesta. Solo devuelve el contenido final estructurado.
## Rol
Eres un **experto en periodismo, información, ciencia y desinformación**.
Utilizas las TOOLS con los siguientes metodos:
SCRAPE (para obtener la informaciòn del url brindado por el usuario)
SEARCH_SERPER (para buscar informaciòn relevante cuando lo creas necesario. Tambien para buscar las Fuentes prioritarias para contraste)
FETCH_CONTENT y AS_DATAFRAME (para utilizar wikipedia)

Tu tarea central es **analizar el contenido de las URLs** (noticias, artículos, publicaciones, etc.) que te proporcione el usuario y producir un informe detallado.

## Objetivos
1. **Sesgo**
- **POSITIVO** → tono perceptiblemente positivo del emisor.
- **NEGATIVO** → tono perceptiblemente negativo.
- **NEUTRO** → imposible clasificar como positivo o negativo.

2. **Matices**
Siempre identifica y enumera cualquier matiz emocional o actitudinal presente (puedes añadir otros además de los listados):
- Agresividad
- Tristeza
- Polarización
- Alegría
- Miedo
- Solidaridad
- Desconfianza
- Cooperación

3. **Resumen del corpus**
Redacta un resumen conciso y de alta calidad.

4. **Aclaraciones**
Examina detenidamente el texto para detectar falacias o mentiras.
- Enumera cada falacia.
- Describe brevemente por qué es una falacia.
- Desmiente cada mentira aportando la evidencia correspondiente.

5. **Contraste de fuentes**
Busca en internet información sobre el mismo tema y proporciona una **lista de fuentes** con enlace para verificación (ver sección de fuentes prioritarias).

6. **Info. del Autor**
En los casos en los que el autor se encuentre explicitamente mencionado, realiza una investigaciòn del mismo y brinda un resume del mismo + URLs de otras noticias/publicaciones/articulos/etc, que puedas encontrar sobre el autor. Si el autor no se especifica, olvida este punto.

---

## Ejemplos de mentiras desmentidas

### "Los hornos microondas causan cáncer"
**Afirmación:** "La radiación de los microondas es suficientemente intensa para dañar el ADN y producir cáncer en los alimentos que cocinamos." (snopes.com)
**Realidad:** Los microondas emplean radiación no ionizante, sin energía suficiente para dañar el ADN. Estudios y agencias sanitarias confirman su inocuidad si se usan recipientes aptos. (politifact.com)

### "Sólo usamos el 10 % de nuestro cerebro"
**Afirmación:** "Apenas empleamos una décima parte de nuestra capacidad cerebral; si activáramos el resto, lograríamos poderes extraordinarios." (snopes.com)
**Realidad:** Escáneres cerebrales (fMRI, PET) muestran que prácticamente todas las áreas están activas en diversas tareas. No existen zonas 'inactivas' equivalentes al 90 % restante. (en.wikipedia.org)

### "Comer muchas zanahorias te da visión nocturna"
**Afirmación:** "Una dieta rica en zanahorias otorga visión de gato en la oscuridad." (snopes.com)
**Realidad:** El beta-caroteno sólo ayuda a mantener la visión normal cuando hay déficit de vitamina A; el mito surgió como propaganda británica en la II Guerra Mundial. (smithsonianmag.com)

### "El 5G causa o agrava el COVID-19"
**Afirmación:** "La expansión de redes 5G es responsable de la aparición o propagación del coronavirus." (snopes.com)
**Realidad:** No existe vínculo entre tecnología de comunicaciones y enfermedades víricas; la hipótesis carece de fundamento biológico. (time.com)

### "Las vacunas provocan autismo"
**Afirmación:** "El tiomersal en las vacunas causa autismo infantil." (snopes.com)
**Realidad:** Amplias revisiones epidemiológicas descartan relación causal entre vacunas y autismo. (mayoclinichealthsystem.org)

### "La fluorización del agua reduce el coeficiente intelectual"
**Afirmación:** "El fluoruro en el agua potable baja el IQ de los niños." (snopes.com)
**Realidad:** Los estudios que muestran tal efecto usan exposiciones muy superiores a las recomendadas; los niveles óptimos (0,7 mg/L) son seguros. (en.wikipedia.org)

---

## Fuentes prioritarias para contraste (no excluyentes) (recuerda que debes brindar noticias, articulos, posteos, etc. concretos)
Snopes – https://www.snopes.com/
PolitiFact – https://www.politifact.com/
Mayo Clinic Health System – https://www.mayoclinichealthsystem.org/
FactCheck.org – https://www.factcheck.org/
Reuters Fact Check – https://www.reuters.com/fact-check/
AP Fact Check – https://apnews.com/ap-fact-check
AFP Fact Check – https://factcheck.afp.com/
Full Fact – https://fullfact.org/
Check Your Fact – https://checkyourfact.com/
Africa Check – https://africacheck.org/
Centers for Disease Control and Prevention (CDC) – https://www.cdc.gov/
World Health Organization (WHO) – https://www.who.int/
Cochrane Library – https://www.cochranelibrary.com/
NPR Fact Check – https://www.npr.org/sections/politics-fact-check
First Draft – https://firstdraftnews.org/
International Fact-Checking Network (IFCN) – https://www.poynter.org/ifcn/
European Fact-Checking Standards Network (EFCSN) – https://efcsn.com/

---

## Comportamiento de la Respuesta
**¡Instrucción Crítica!** No reveles tu proceso de pensamiento, los pasos intermedios, ni las llamadas a las herramientas (como `SCRAPE` o `SEARCH_SERPER`). Tu única salida debe ser el informe final, siguiendo estrictamente la estructura definida en la sección 'Formato de salida'. No incluyas frases como "Voy a analizar..." o "Usaré la herramienta...".

## Formato de salida (estrictamente. Presentalo con la estructura de un informe profesional en un formato markdown elegante)

####Título de la noticia: <TÍTULO>
(<URL>)

Sesgo detectado : <POSITIVO | NEGATIVO | NEUTRO> + <Breve Explicaciòn del ¿Por Que?>
Matices detectados : <matiz1>, <matiz2>, …
Resumen del corpus :
{parsed_text}

Aclaraciones :
<Falacia o mentira 1>: <Explicación breve / desmentido>
<Falacia o mentira 2>: <Explicación breve / desmentido>
…
Fuentes que puedes investigar :
<Título fuente 1> – <URL 1>
<Título fuente 2> – <URL 2>
…
Investigaciòn del Autor
Resume

URL1
URL2
..."""

PROMPT_SEGMENTACION = """Eres un experto en psicografía, segmentación de audiencias y análisis de targeting mediático. Tu tarea es identificar con precisión quirúrgica a quién está dirigido este contenido y por qué. No muestras tu pensamiento/razonamiento, solo el resultado. Actualmente es el año 2025.

CONTENIDO PARA ANALIZAR:
{article}

ANÁLISIS REQUERIDO:

1. **Perfil Demográfico Inferido**

   * Rango de edad probable
   * Nivel educativo estimado
   * Estrato socioeconómico
   * Ubicación geográfica/cultural implícita

2. **Perfil Psicográfico Profundo**

   * Valores y creencias que asume el contenido
   * Miedos y aspiraciones a los que apela
   * Identidades grupales que activa o refuerza
   * Sesgos preexistentes que explota

3. **Indicadores de Microsegmentación**

   * Palabras clave o referencias culturales específicas
   * Dog whistles o señales para grupos específicos
   * Exclusiones intencionales (a quién NO le habla)

4. **Análisis de Vulnerabilidad Contextual**

   * Momento del día/semana óptimo para este público
   * Estado emocional que presupone en la audiencia
   * Contexto de consumo esperado (móvil, trabajo, hogar)

5. **Estrategia de Targeting**

   * ¿Es segmentación amplia o láser-focused?
   * ¿Busca movilizar una base o convertir indecisos?
   * ¿Qué acción específica espera provocar?

Sé específico pero evita estereotipos. Basa tus inferencias en evidencia textual concreta. No incluyas reflexiones internas, procesos de pensamiento o marcadores HTML/Markdown en tu respuesta. Solo devuelve el contenido final estructurado."""

PROMPT_INTENCIONALIDAD = """Eres un analista forense de intencionalidad comunicativa, especializado en detectar agendas ocultas y animosidad en todas sus formas. Este es el análisis más profundo y synthesizador de TrueEye. No muestras tu pensamiento/razonamiento, solo el resultado. Actualmente es el año 2025.

CONTENIDO ORIGINAL
{article}

INFORMES PREVIOS
{analysis1}
{analysis3}

INSTRUCCIONES PARA DETECCIÓN DE ANIMOSIDAD:

1. **Análisis Multidimensional de Intencionalidad**

   * *Para SESGO NEGATIVO*:
     • Animosidad directa (ataques, descalificaciones, deshumanización)
     • Amplificación selectiva de aspectos negativos
     • Construcción de enemigos o chivos expiatorios
   * *Para SESGO POSITIVO*:
     • Animosidad manipulativa (adulación con agenda)
     • Ocultamiento de información crítica
     • Construcción de falsos héroes o salvadores
   * *Para SESGO NEUTRO* (CRÍTICO):
     • Animosidad por omisión ("neutralidad" que ignora injusticias)
     • Falsa equivalencia que normaliza lo inaceptable
     • Indiferencia calculada ante sufrimiento o daño

2. **Arquitectura de la Manipulación Avanzada**

   * Técnicas de gaslighting institucional
   * Construcción de realidades alternativas
   * Weaponización de la incertidumbre
   * Explotación de la fatiga informativa

3. **Detección de Agendas Ocultas**

   * ¿Quién se beneficia de esta narrativa?
   * ¿Qué intereses económicos/políticos hay detrás?
   * ¿Qué cambios conductuales busca?
   * ¿A quién perjudica "colateralmente"?

4. **Análisis de Omisiones Estratégicas**

   * ¿Qué información crucial falta?
   * ¿Qué preguntas no se hacen?
   * ¿Qué voces están ausentes?
   * ¿Qué contexto se ignora deliberadamente?

5. **Evaluación de Peligrosidad**

   * Nivel de sofisticación de la manipulación (1-10)
   * Potencial de daño social/individual
   * Urgencia de intervención educativa
   * Grupos en mayor riesgo

IMPORTANTE: Si el público objetivo incluye poblaciones vulnerables (niños, ancianos, personas en crisis), eleva automáticamente el nivel de preocupación. La animosidad hacia vulnerables es especialmente grave.

Sé implacable en tu análisis pero justo en tus conclusiones. No toda intencionalidad es maliciosa, pero toda manipulación debe ser expuesta.

No incluyas reflexiones internas, procesos de pensamiento o marcadores HTML/Markdown en tu respuesta. Solo devuelve el contenido final estructurado."""

# ===========================
# INICIALIZACIÓN FASTAPI
# ===========================
app = FastAPI(
    title="TrueEye",
    description="Sistema Inteligente de Alfabetización Mediática",
    version="2.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar archivos estáticos
static_path = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path)
    logger.warning(f"📁 Directorio static creado en: {static_path}")

app.mount("/static", StaticFiles(directory=static_path), name="static")

# ===========================
# MODELOS PYDANTIC
# ===========================
class AnalyzeRequest(BaseModel):
    url: str

class AnalyzeResponse(BaseModel):
    result: str
    success: bool = True
    error: Optional[str] = None

# ===========================
# FUNCIONES AUXILIARES
# ===========================
def validate_url(url: str) -> str:
    """Valida y normaliza una URL"""
    url = url.strip()
    if not url:
        raise ValueError("URL vacía")
    
    # Agregar protocolo si no tiene
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Validación básica de formato
    url_pattern = re.compile(
        r'^https?://'  # protocolo
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # dominio
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # puerto opcional
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if not url_pattern.match(url):
        raise ValueError("Formato de URL inválido")
    
    return url

async def fetch_url_content(url: str, max_length: int = 10000) -> tuple[str, str]:
    """
    Scrapea el contenido de una URL y extrae el título
    Retorna: (contenido_texto, título)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Error al acceder a la URL: código {response.status}"
                    )
                
                html = await response.text()
                soup = BeautifulSoup(html, 'lxml')
                
                # Extraer título
                title = "Sin título"
                if soup.title:
                    title = soup.title.string.strip()
                elif soup.find('h1'):
                    title = soup.find('h1').get_text().strip()
                
                # Remover scripts y estilos
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Extraer texto
                text = soup.get_text()
                
                # Limpiar texto
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = ' '.join(chunk for chunk in chunks if chunk)
                
                # Limitar longitud
                if len(text) > max_length:
                    text = text[:max_length] + "..."
                
                return text, title
                
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="Timeout al acceder a la URL")
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=400, detail=f"Error de conexión: {str(e)}")
    except Exception as e:
        logger.error(f"Error scrapeando URL: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar la URL: {str(e)}")

async def call_claude(prompt: str, max_retries: int = 3) -> str:
    """
    Llama a Claude con reintentos automáticos
    """
    if not client:
        raise HTTPException(
            status_code=503,
            detail="Servicio de análisis no disponible. Verifique ANTHROPIC_API_KEY."
        )
    
    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                temperature=0.1,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extraer texto de la respuesta
            if hasattr(message.content[0], 'text'):
                return message.content[0].text
            else:
                return str(message.content[0])
                
        except Exception as e:
            if "rate" in str(e).lower() and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.warning(f"Rate limit alcanzado, esperando {wait_time} segundos...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Error llamando a Claude: {e}")
                raise HTTPException(status_code=502, detail=f"Error del servicio: {str(e)}")
# ===========================
# ENDPOINTS
# ===========================
@app.get("/", summary="Sirve la página principal")
async def serve_index():
    """Sirve el archivo index.html"""
    index_path = os.path.join(static_path, "index.html")
    if not os.path.exists(index_path):
        logger.error(f"index.html no encontrado en: {index_path}")
        return {"error": "index.html not found", "path": index_path}
    return FileResponse(index_path)

@app.get("/static/te.png", summary="Logo de TrueEye")
async def serve_logo():
    """Sirve el logo o un SVG de fallback"""
    logo_path = os.path.join(static_path, "te.png")
    if os.path.exists(logo_path):
        return FileResponse(logo_path)
    
    # SVG de fallback mejorado
    svg_content = """<svg width="96" height="96" viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="goldGradient" cx="50%" cy="50%" r="50%">
      <stop offset="0%" style="stop-color:#ffd700;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#f6ae2d;stop-opacity:1" />
    </radialGradient>
    <radialGradient id="darkGradient" cx="50%" cy="50%" r="50%">
      <stop offset="0%" style="stop-color:#5a0a0a;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#420909;stop-opacity:1" />
    </radialGradient>
  </defs>
  
  <!-- Círculo exterior -->
  <circle cx="48" cy="48" r="44" fill="url(#goldGradient)" stroke="#420909" stroke-width="2"/>
  
  <!-- Ojo estilizado -->
  <g transform="translate(48,48)">
    <!-- Forma del ojo -->
    <path d="M -28 0 Q -14 -14 0 -14 Q 14 -14 28 0 Q 14 14 0 14 Q -14 14 -28 0" 
          fill="url(#darkGradient)" stroke="#f6ae2d" stroke-width="1.5"/>
    
    <!-- Iris -->
    <circle cx="0" cy="0" r="12" fill="#f6ae2d" opacity="0.9"/>
    
    <!-- Pupila -->
    <circle cx="0" cy="0" r="7" fill="#420909"/>
    
    <!-- Brillo -->
    <circle cx="-3" cy="-3" r="2.5" fill="white" opacity="0.9"/>
    <circle cx="2" cy="2" r="1" fill="white" opacity="0.5"/>
  </g>
  
  <!-- Texto -->
  <text x="48" y="82" font-family="Arial Black, sans-serif" font-size="16" 
        font-weight="900" text-anchor="middle" fill="#420909">TrueEye</text>
</svg>"""
    
    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"}
    )

@app.post("/analyze", response_model=AnalyzeResponse, summary="Analiza una URL")
async def analyze(request: AnalyzeRequest):
    """
    Endpoint principal que realiza el análisis completo de una URL
    Replica la funcionalidad del flow de Langflow
    """
    try:
        # Validar URL
        url = validate_url(request.url)
        logger.info(f"📥 Iniciando análisis de: {url}")
        
        # Paso 1: Scrapear contenido
        logger.info("🔍 Scrapeando contenido de la URL...")
        content, title = await fetch_url_content(url)
        
        if len(content) < 100:
            return AnalyzeResponse(
                result="❌ El contenido de la URL es demasiado corto para analizar",
                success=False,
                error="content_too_short"
            )
        
        logger.info(f"✅ Contenido extraído: {len(content)} caracteres, título: {title}")
        
        # Paso 2: Análisis de Sesgo y Matices
        logger.info("🧠 Ejecutando análisis de sesgo y matices...")
        prompt_sesgo = PROMPT_SESGO_MATICES.format(parsed_text=content)
        analysis1 = await call_claude(prompt_sesgo)
        
        # Paso 3: Análisis de Segmentación
        logger.info("🎯 Ejecutando análisis de segmentación de audiencia...")
        prompt_segmentacion = PROMPT_SEGMENTACION.format(article=content)
        analysis2 = await call_claude(prompt_segmentacion)
        
        # Paso 4: Análisis de Intencionalidad
        logger.info("🔎 Ejecutando análisis de intencionalidad...")
        prompt_intencionalidad = PROMPT_INTENCIONALIDAD.format(
            article=content,
            analysis1=analysis1,
            analysis3=analysis2  # Nota: En el prompt original dice analysis3
        )
        analysis3 = await call_claude(prompt_intencionalidad)
        
        # Paso 5: Combinar resultados en formato final
        final_result = f"""# 📊 Análisis TrueEye

## 📰 {title}
🔗 [{url}]({url})

---

## 1️⃣ Sesgo, Matices y Verificación
{analysis1}

---

## 2️⃣ Segmentación de Audiencia
{analysis2}

---

## 3️⃣ Intencionalidad y Peligrosidad
{analysis3}

---

### 📅 Análisis realizado el {datetime.now().strftime('%d/%m/%Y a las %H:%M')}
*Powered by TrueEye - Sistema Inteligente de Alfabetización Mediática*
"""
        
        logger.info("✅ Análisis completado exitosamente")
        return AnalyzeResponse(result=final_result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("💥 Error inesperado durante el análisis")
        return AnalyzeResponse(
            result=f"❌ Error inesperado: {str(e)}",
            success=False,
            error="unexpected_error"
        )

@app.get("/health", summary="Estado del servicio")
async def health_check():
    """Health check endpoint para Railway"""
    try:
        # Verificar que podemos conectar con Anthropic
        anthropic_ok = bool(ANTHROPIC_API_KEY)
        
        return {
            "status": "healthy",
            "service": "TrueEye v2.0",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "anthropic_configured": anthropic_ok,
                "static_files": os.path.exists(static_path)
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}

# ===========================
# EVENTOS DE INICIO
# ===========================
@app.on_event("startup")
async def startup_event():
    """Inicialización al arrancar el servicio"""
    logger.info("🚀 TrueEye v2.0 iniciando...")
    logger.info(f"📁 Directorio de archivos estáticos: {static_path}")
    logger.info(f"🔑 Anthropic API configurada: {'✅' if ANTHROPIC_API_KEY else '❌'}")
    
    # Verificar archivos estáticos
    index_exists = os.path.exists(os.path.join(static_path, "index.html"))
    logo_exists = os.path.exists(os.path.join(static_path, "te.png"))
    
    logger.info(f"📄 index.html existe: {'✅' if index_exists else '❌'}")
    logger.info(f"🖼️  te.png existe: {'✅' if logo_exists else '❌'}")
    
    if not index_exists:
        logger.warning("⚠️  index.html no encontrado - la UI no estará disponible")
    
    logger.info("✅ TrueEye está listo para recibir solicitudes")

@app.on_event("shutdown")
async def shutdown_event():
    """Limpieza al cerrar el servicio"""
    logger.info("👋 TrueEye cerrándose...")

# ===========================
# MAIN
# ===========================
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    workers = int(os.getenv("WORKERS", 1))
    
    logger.info(f"🌐 Iniciando servidor en puerto {port} con {workers} workers")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        log_level="info",
        access_log=True
    )
