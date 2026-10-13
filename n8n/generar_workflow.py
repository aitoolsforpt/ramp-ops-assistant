"""Genera n8n/workflow.json (importable en n8n con `n8n import:workflow`).

Flujo:
  POST /webhook/incidencia {id?, texto}
    -> Preparar petición (prompt + esquema JSON)
    -> Modelo local (Ollama) con reintento
    -> Validar + red de seguridad + registro   (nunca se pierde una incidencia)
    -> IF aprobación -> estado «pendiente de aprobación» | «registrada»
  GET /webhook/informe -> resumen por tipo, gravedad y estado
  GET /webhook/pendientes -> incidencias esperando aprobación, con enlaces aprobar/rechazar
  GET /webhook/decision?id=..&accion=aprobar|rechazar -> registra la decisión humana

El modelo y la URL de Ollama son las constantes MODELO y OLLAMA_URL de este fichero (n8n bloquea $env en nodos Code).
Sin claves ni datos reales.
"""
import json
import uuid
from pathlib import Path

# Cambia aquí el modelo o la URL de Ollama y vuelve a generar (n8n bloquea leer variables de entorno en los nodos Code).
MODELO = "qwen2.5:7b-instruct"
OLLAMA_URL = "http://127.0.0.1:11434"

SISTEMA = (
    "Eres un asistente de operaciones de rampa de un aeropuerto. Clasifica cada incidencia.\\n"
    "Tipos: equipaje, carga_balance, equipo_gse, seguridad_prl, personal, documentacion, otro.\\n"
    "Gravedad:\\n"
    "- critica: riesgo para personas o para la seguridad de la aeronave (fuego, derrame peligroso, zona de hélices, mercancía peligrosa sin documentación).\\n"
    "- alta: retraso notable (10 minutos o más), daño material relevante, lesión de una persona o incumplimiento de seguridad.\\n"
    "- media: incidencia gestionada sin retraso que afecta al proceso.\\n"
    "- baja: informativa o sin impacto.\\n"
    "aprobacion es true si la gravedad es alta o critica, y false en otro caso.\\n"
    "Responde solo con el JSON pedido."
)

PREPARAR = """const body = $input.first().json.body || {};
const texto = String(body.texto || '').trim();
const esquema = {
  type: 'object',
  properties: {
    tipo: { type: 'string', enum: ['equipaje','carga_balance','equipo_gse','seguridad_prl','personal','documentacion','otro'] },
    gravedad: { type: 'string', enum: ['baja','media','alta','critica'] },
    aprobacion: { type: 'boolean' },
  },
  required: ['tipo','gravedad','aprobacion'],
};
const modelo = '%s';
return [{ json: {
  id: body.id || ('INC-' + Date.now()),
  texto,
  ollamaBody: {
    model: modelo, stream: false, format: esquema, options: { temperature: 0 },
    messages: [ { role: 'system', content: '%s' }, { role: 'user', content: texto } ],
  },
} }];
""" % (MODELO, SISTEMA)

VALIDAR = r"""// Valida la salida del modelo, aplica la red de seguridad y registra SIEMPRE la incidencia.
const prep = $('Preparar peticion').first().json;
const entrada = $input.first().json;
const ORDEN = ['baja','media','alta','critica'];
const TIPOS = ['equipaje','carga_balance','equipo_gse','seguridad_prl','personal','documentacion','otro'];
let r = {}; let motivos = [];
try {
  if (entrada.error) throw new Error('fallo del modelo');
  r = JSON.parse(entrada.message.content);
} catch (e) {
  r = { tipo: null, gravedad: null, aprobacion: null };
  motivos.push('respuesta inválida o error del modelo');
}
const t = prep.texto;
const CRIT = /\b(fuego|humo|llamas?|incendio|combustible|derrame|fuga|peligros[ao]|h[eé]lices?|atrapad[oa]|herid[oa]s?|lesi[oó]n|quemadura|desmay\w*|colisi[oó]n|choque|explosi\w*)\b/i;
const ALTA = /(sin chaleco|sin formaci[oó]n|formaci[oó]n vigente|cable pelado|exceso de peso|desequilibr\w*|peso (distinto|inferior|superior)|resbal\w*|impact\w*|dolor de espalda|sin protectores|sin autorizaci[oó]n)/i;
const MIN = /(?:retras\w*[^.;]{0,60}?(\d+)\s*minutos|(\d+)\s*minutos\s*(?:de\s*)?(?:retraso|tarde))/i;
const m = MIN.exec(t);
const retraso = m ? parseInt(m[1] || m[2], 10) : 0;
let piso = null;
if (CRIT.test(t)) { piso = 'critica'; motivos.push('señal crítica en el texto'); }
else if (ALTA.test(t) || retraso >= 10) { piso = 'alta'; motivos.push('señal alta o retraso >= 10 min'); }
if (piso && (!ORDEN.includes(r.gravedad) || ORDEN.indexOf(r.gravedad) < ORDEN.indexOf(piso))) r.gravedad = piso;
if (['alta','critica'].includes(r.gravedad)) r.aprobacion = true;
if (!ORDEN.includes(r.gravedad) || !TIPOS.includes(r.tipo)) { r.aprobacion = true; if (!motivos.length) motivos.push('clasificación inválida'); }
const registro = { id: prep.id, texto: t, tipo: r.tipo, gravedad: r.gravedad, aprobacion: r.aprobacion, motivos_seguridad: motivos, fecha: new Date().toISOString(),
  estado: r.aprobacion ? 'pendiente_de_aprobacion' : 'registrada', decision: null, decidido_en: null };
const sd = $getWorkflowStaticData('global');
sd.registro = sd.registro || [];
sd.registro.push(registro);
return [{ json: registro }];
"""

INFORME = r"""const sd = $getWorkflowStaticData('global');
const reg = sd.registro || [];
const por = (k) => reg.reduce((a, x) => { const v = x[k] || 'sin_clasificar'; a[v] = (a[v] || 0) + 1; return a; }, {});
return [{ json: {
  total: reg.length,
  pendientes_de_aprobacion: reg.filter(x => x.estado === 'pendiente_de_aprobacion').length,
  por_estado: por('estado'),
  por_tipo: por('tipo'),
  por_gravedad: por('gravedad'),
  ultimas: reg.slice(-5),
} }];
"""

PENDIENTES = r"""const sd = $getWorkflowStaticData('global');
const base = 'http://localhost:5678'; // servidor local; cámbialo si se publica en otra URL
const pend = (sd.registro || []).filter(x => x.estado === 'pendiente_de_aprobacion');
return [{ json: {
  total_pendientes: pend.length,
  pendientes: pend.map(x => ({
    id: x.id, texto: x.texto, tipo: x.tipo, gravedad: x.gravedad, motivos_seguridad: x.motivos_seguridad,
    aprobar: base + '/webhook/decision?id=' + encodeURIComponent(x.id) + '&accion=aprobar',
    rechazar: base + '/webhook/decision?id=' + encodeURIComponent(x.id) + '&accion=rechazar',
  })),
} }];
"""

DECIDIR = r"""const q = $input.first().json.query || {};
const sd = $getWorkflowStaticData('global');
const reg = sd.registro || [];
const accion = String(q.accion || '');
if (!['aprobar', 'rechazar'].includes(accion)) return [{ json: { ok: false, error: 'accion debe ser aprobar o rechazar' } }];
const x = reg.find(r => r.id === q.id);
if (!x) return [{ json: { ok: false, error: 'incidencia no encontrada' } }];
if (x.estado !== 'pendiente_de_aprobacion') return [{ json: { ok: false, error: 'ya decidida: ' + x.estado, id: x.id } }];
x.decision = accion === 'aprobar' ? 'aprobada' : 'rechazada';
x.estado = x.decision;
x.decidido_en = new Date().toISOString();
return [{ json: { ok: true, id: x.id, estado: x.estado, decidido_en: x.decidido_en } }];
"""


def nodo(nombre, tipo, version, pos, params, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": nombre, "type": tipo, "typeVersion": version, "position": pos}
    n.update(extra)
    return n


def set_estado(nombre, pos, valor):
    return nodo(nombre, "n8n-nodes-base.set", 3.4, pos, {
        "assignments": {"assignments": [{"id": str(uuid.uuid4()), "name": "estado", "value": valor, "type": "string"}]},
        "includeOtherFields": True, "options": {},
    })


nodes = [
    nodo("Webhook incidencia", "n8n-nodes-base.webhook", 2, [0, 0],
         {"httpMethod": "POST", "path": "incidencia", "responseMode": "lastNode", "options": {}}, webhookId=str(uuid.uuid4())),
    nodo("Preparar peticion", "n8n-nodes-base.code", 2, [220, 0], {"jsCode": PREPARAR}),
    nodo("Modelo local (Ollama)", "n8n-nodes-base.httpRequest", 4.2, [440, 0], {
        "method": "POST", "url": OLLAMA_URL + "/api/chat",
        "sendBody": True, "specifyBody": "json", "jsonBody": "={{ $json.ollamaBody }}",
        "options": {"timeout": 300000},
    }, retryOnFail=True, maxTries=2, waitBetweenTries=2000, onError="continueRegularOutput"),
    nodo("Validar y registrar", "n8n-nodes-base.code", 2, [660, 0], {"jsCode": VALIDAR}),
    nodo("Requiere aprobacion?", "n8n-nodes-base.if", 2, [880, 0], {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.aprobacion }}", "rightValue": True,
                            "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
            "combinator": "and",
        }, "options": {},
    }),
    set_estado("Pendiente de aprobacion", [1100, -100], "pendiente_de_aprobacion_humana"),
    set_estado("Registrada", [1100, 100], "registrada"),
    nodo("Webhook informe", "n8n-nodes-base.webhook", 2, [0, 300],
         {"httpMethod": "GET", "path": "informe", "responseMode": "lastNode", "options": {}}, webhookId=str(uuid.uuid4())),
    nodo("Resumen", "n8n-nodes-base.code", 2, [220, 300], {"jsCode": INFORME}),
    nodo("Webhook pendientes", "n8n-nodes-base.webhook", 2, [0, 500],
         {"httpMethod": "GET", "path": "pendientes", "responseMode": "lastNode", "options": {}}, webhookId=str(uuid.uuid4())),
    nodo("Listar pendientes", "n8n-nodes-base.code", 2, [220, 500], {"jsCode": PENDIENTES}),
    nodo("Webhook decision", "n8n-nodes-base.webhook", 2, [0, 700],
         {"httpMethod": "GET", "path": "decision", "responseMode": "lastNode", "options": {}}, webhookId=str(uuid.uuid4())),
    nodo("Registrar decision", "n8n-nodes-base.code", 2, [220, 700], {"jsCode": DECIDIR}),
]

conexiones = {
    "Webhook incidencia": {"main": [[{"node": "Preparar peticion", "type": "main", "index": 0}]]},
    "Preparar peticion": {"main": [[{"node": "Modelo local (Ollama)", "type": "main", "index": 0}]]},
    "Modelo local (Ollama)": {"main": [[{"node": "Validar y registrar", "type": "main", "index": 0}]]},
    "Validar y registrar": {"main": [[{"node": "Requiere aprobacion?", "type": "main", "index": 0}]]},
    "Requiere aprobacion?": {"main": [
        [{"node": "Pendiente de aprobacion", "type": "main", "index": 0}],
        [{"node": "Registrada", "type": "main", "index": 0}],
    ]},
    "Webhook informe": {"main": [[{"node": "Resumen", "type": "main", "index": 0}]]},
    "Webhook pendientes": {"main": [[{"node": "Listar pendientes", "type": "main", "index": 0}]]},
    "Webhook decision": {"main": [[{"node": "Registrar decision", "type": "main", "index": 0}]]},
}

wf = {
    "id": "opsAsistenteRampa01",
    "name": "Asistente de operaciones de rampa",
    "nodes": nodes,
    "connections": conexiones,
    "settings": {"executionOrder": "v1"},
    "active": False,
}

destino = Path(__file__).parent / "workflow.json"
destino.write_text(json.dumps([wf], ensure_ascii=False, indent=2), encoding="utf-8")
print("workflow escrito en", destino)
