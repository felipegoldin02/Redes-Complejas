import pandas as pd
from SPARQLWrapper import SPARQLWrapper, JSON
import time
import json

print("INICIANDO EXTRACCIÓN DIVIDE Y VENCERÁS v2 (Bloques blindados de 25 años)...")

sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
sparql.agent = "GrafoMedievalDivide/6.0 (Contacto: investigador@ejemplo.com)"
sparql.setReturnFormat(JSON)

nodos = {}

# ==========================================
# FASE 1: DESCARGAR PERSONAJES BASE
# ==========================================
print("\nFASE 1: Descargando personajes base (ultra rápido)...")
# Achicamos los bloques a 25 años para evitar que Wikidata corte el archivo a la mitad
for anio_inicio in range(500, 1550, 25):
    anio_fin = anio_inicio + 24
    print(f"-> Escaneando nacidos entre {anio_inicio} - {anio_fin}...")
    
    query_base = f"""
    SELECT ?persona ?personaLabel ?casaLabel ?nacimiento ?lugar_nacLabel
    WHERE {{
      ?persona wdt:P31 wd:Q5 ;
               wdt:P569 ?nacimiento ;
               (wdt:P53|wdt:P97) ?casa .
      FILTER(YEAR(?nacimiento) >= {anio_inicio} && YEAR(?nacimiento) <= {anio_fin})
      OPTIONAL {{ ?persona wdt:P19 ?lugar_nac . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
    }} LIMIT 15000
    """
    sparql.setQuery(query_base)
    
    exito = False
    intentos = 0
    
    # Sistema de reintentos automático
    while not exito and intentos < 3:
        try:
            res_cruda = sparql.query().response.read().decode('utf-8')
            data = json.loads(res_cruda, strict=False)
            
            for item in data["results"]["bindings"]:
                p_id = item["persona"]["value"].split("/")[-1]
                p_nombre = item.get("personaLabel", {}).get("value", "Desconocido")
                p_casa = item.get("casaLabel", {}).get("value", "Desconocida")
                
                f_nac = item.get("nacimiento", {}).get("value", "")
                anio = f_nac.split("-")[0].replace("+", "") if f_nac else "Desconocido"
                
                l_nac = item.get("lugar_nacLabel", {}).get("value", "")
                lugar = l_nac if (l_nac and not l_nac.startswith("http")) else "Desconocido"
                
                nodos[p_id] = {
                    "Id": p_id, "Label": p_nombre, "casa": p_casa, 
                    "epoca": anio, "ubicacion": lugar
                }
            exito = True
            time.sleep(1) # Pausa mínima
            
        except Exception as e:
            intentos += 1
            print(f"   X Error detectado: {e}. Reintentando en 5 segundos (Intento {intentos}/3)...")
            time.sleep(5)

ids_base = list(nodos.keys())
print(f"✓ Fase 1 completada: {len(ids_base)} nobles ancla encontrados.")

# ==========================================
# FASE 2: DESCARGAR FAMILIARES EXACTOS
# ==========================================
print("\nFASE 2: Trazando relaciones genealógicas y hermanos...")
relaciones = []
lotes = [ids_base[i:i + 200] for i in range(0, len(ids_base), 200)]

for idx, lote in enumerate(lotes):
    print(f"-> Procesando árbol familiar: lote {idx + 1}/{len(lotes)}...")
    valores = " ".join([f"wd:{q}" for q in lote])
    
    query_fam = f"""
    SELECT ?persona ?padre ?padreLabel ?madre ?madreLabel ?conyuge ?conyugeLabel ?hermano ?hermanoLabel
    WHERE {{
      VALUES ?persona {{ {valores} }}
      OPTIONAL {{ ?persona wdt:P22 ?padre . }}
      OPTIONAL {{ ?persona wdt:P25 ?madre . }}
      OPTIONAL {{ ?persona wdt:P26 ?conyuge . }}
      OPTIONAL {{ ?persona wdt:P3373 ?hermano . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
    }}
    """
    sparql.setQuery(query_fam)
    
    exito_fase2 = False
    intentos_fase2 = 0
    
    while not exito_fase2 and intentos_fase2 < 3:
        try:
            res_cruda = sparql.query().response.read().decode('utf-8')
            data = json.loads(res_cruda, strict=False)
            
            for item in data["results"]["bindings"]:
                p_id = item["persona"]["value"].split("/")[-1]
                
                def procesar_fam(rol_var, rel_nombre):
                    if rol_var in item:
                        f_id = item[rol_var]["value"].split("/")[-1]
                        f_nom = item.get(f"{rol_var}Label", {}).get("value", "Desconocido")
                        
                        if f_id not in nodos:
                            nodos[f_id] = {
                                "Id": f_id, "Label": f_nom, "casa": "Desconocida", 
                                "epoca": "Desconocido", "ubicacion": "Desconocido"
                            }
                        
                        if rel_nombre in ["conyuge", "hermano"]:
                            relaciones.append({"Source": p_id, "Target": f_id, "Label": rel_nombre})
                            relaciones.append({"Source": f_id, "Target": p_id, "Label": rel_nombre})
                        else:
                            relaciones.append({"Source": p_id, "Target": f_id, "Label": rel_nombre})

                procesar_fam("padre", "padre")
                procesar_fam("madre", "madre")
                procesar_fam("conyuge", "conyuge")
                procesar_fam("hermano", "hermano")
                
            exito_fase2 = True
            time.sleep(1.5)
        except Exception as e:
            intentos_fase2 += 1
            print(f"   X Error en lote {idx + 1}: {e}. Reintentando...")
            time.sleep(5)

# ==========================================
# FASE 3: HERENCIA INTELIGENTE
# ==========================================
print("\nFASE 3: Aplicando lógicas de herencia de datos...")

rel_conyuges = [r for r in relaciones if r['Label'] == 'conyuge']
for r in rel_conyuges:
    p1, p2 = r['Source'], r['Target']
    if p1 in nodos and p2 in nodos:
        e1, e2 = nodos[p1]['epoca'], nodos[p2]['epoca']
        if e1 != 'Desconocido' and e2 == 'Desconocido':
            nodos[p2]['epoca'] = f"{e1.replace('*', '')}*"
        elif e2 != 'Desconocido' and e1 == 'Desconocido':
            nodos[p1]['epoca'] = f"{e2.replace('*', '')}*"

rel_padres = [r for r in relaciones if r['Label'] == 'padre']
for generacion in range(1, 3):
    cambios = 0
    estado_actual = {k: v['ubicacion'] for k, v in nodos.items()}
    
    for r in rel_padres:
        hijo_id, padre_id = r['Source'], r['Target']
        if hijo_id in nodos and padre_id in nodos:
            ubi_padre = estado_actual[padre_id]
            ubi_hijo = nodos[hijo_id]['ubicacion']
            
            if ubi_padre != 'Desconocido' and ubi_hijo == 'Desconocido':
                nodos[hijo_id]['ubicacion'] = f"{ubi_padre.replace('*', '')}*"
                cambios += 1
                
    print(f"   -> Generación {generacion} procesada: {cambios} ubicaciones heredadas.")
    if cambios == 0:
        break

df_nodos = pd.DataFrame(list(nodos.values())).astype(str)
df_relaciones = pd.DataFrame(relaciones).drop_duplicates()

df_nodos.to_csv("nodos_gephi_final.csv", index=False, encoding="utf-8")
df_relaciones.to_csv("relaciones_gephi_final.csv", index=False, encoding="utf-8")

print(f"\n¡Éxito total! Generados {len(df_nodos)} nodos y {len(df_relaciones)} relaciones.")

from google.colab import files
files.download("nodos_gephi_final.csv")
files.download("relaciones_gephi_final.csv")