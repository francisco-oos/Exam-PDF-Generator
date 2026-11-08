"""Crear XLSX demostrativo con series ficticias; no hace falta para usar la herramienta."""
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

questions = [
 ('INOVA y SERCEL','¿Qué variante SERCEL utiliza geófono obligatorio?', ['AFU','DFU','Ambas','Ninguna'],'A'),
 ('INOVA y SERCEL','¿Qué ocurre con INOVA digital Q009845 al plantarse en tierra?', ['Se instala con arnés.','Requiere dos geófonos.','Se planta sin complementos.','Se convierte a AFU.'],'C'),
 ('INOVA y SERCEL','INOVA analógico Q009921 cambia de tierra a pantano. ¿Qué se reporta si solo agregan geófono?', ['Rotación del INOVA.','Tendido del geófono por conversión.','Levantamiento del nodo.','Baja de serie.'],'B'),
 ('INOVA y SERCEL','Se registran 20 AFU 7001423 y 19 arneses. ¿Qué se hace con los arneses?', ['Se agregan 20.','Se eliminan.','Se cambia todo a DFU.','Se conservan 19; son opcionales.'],'D'),
 ('INOVA y SERCEL','DFU 8002134 funciona como repetidora junto a DFU 8002451 productivo. ¿Cómo se cuentan?', ['Dos físicos; uno productivo.','Dos productivos.','Solo uno físico.','Un solo equipo con dos series.'],'A'),
 ('Maniobras','Salen 10 AFU para rotación y entran 9 de misma tecnología. ¿Qué resultado real hubo?', ['10 rotaciones.','9 rotaciones y un levantamiento.','9 tendidos sin levantados.','10 equipos perdidos.'],'B'),
 ('Maniobras','Sale INOVA Q009114 y entra DFU 8001746. ¿Qué se registra?', ['Rotación programada.','Solo un cambio de serie.','Levantamiento INOVA y tendido DFU.','Baja oficial de INOVA.'],'C'),
 ('Maniobras','Un checador reemplaza AFU 7003342 por AFU 7003343 por falla. ¿Qué se reporta?', ['Tendido de dos AFU.','Robo de AFU.','Rotación programada siempre.','Cambio por falla con ambas series.'],'D'),
 ('Maniobras','Se retira solo el geófono de INOVA analógico. ¿Se levantó el nodo?', ['No; solo se levantó geófono.','Sí, el nodo completo.','Sí, es rotación.','Se convierte a DFU.'],'A'),
 ('Maniobras','La maniobra fue para retirar material antes de quema de caña. ¿Qué motivo se anota?', ['Incautación.','Zafra.','TX desconectado.','Mantenimiento.'],'B'),
 ('Documentación','¿Qué hacer cuando un reporte no indica la cantidad de arneses?', ['Poner cero.','Igualar a los AFU.','Indicar no informado y aclarar.','Adivinar por estaca.'],'C'),
 ('Documentación','Se encuentra un nodo quemado sin serie ni ubicación conocida. ¿Qué se hace?', ['No registrarlo.','Inventar una serie.','Contar como recuperado automáticamente.','Folio provisional y evidencia real.'],'D'),
 ('Documentación','TX informó desconectado el 12 y Control de Material extraviado el 17. ¿Cómo se documenta?', ['Con ambas fechas y fuentes.','Solo con el 17.','Solo con el 12.','Fecha promedio.'],'A'),
 ('Documentación','¿Qué debe acompañar una incidencia de robo, extravío o incautación de campo?', ['Solo una llamada.','Formato múltiple y mención diaria.','Una orden de compra.','Una captura sin evidencia.'],'B'),
 ('Documentación','Si un equipo se reemplaza en estaca donde se extravió otro, ¿qué pasa con el perdido?', ['Se recupera automáticamente.','Cambia su serie a la nueva.','Conserva seguimiento de extravío.','Se elimina del catálogo.'],'C'),
 ('Revisión y control','Se corrige después un tramo del Excel diario ya entregado. ¿Qué procedimiento corresponde?', ['Sobrescribir el archivo anterior.','No hacer nada.','Cambiar solo el PDF de examen.','Generar una versión rectificada preservando la original.'],'D'),
 ('Revisión y control','Mantenimiento tiene 14 nodos físicamente y TX reportó entregar 15. ¿Qué registrar?', ['15 esperados, 14 confirmados.','15 confirmados.','14 confirmados y ninguna diferencia.','Todos reparados.'],'A'),
 ('Revisión y control','¿Quién puede aprobar una baja o descuento oficial del inventario general?', ['TX automáticamente.','Control de Material.','Cualquier checador.','La hoja de Excel.'],'B'),
 ('Revisión y control','¿Quién puede cotejar reportes localmente en campamento según la propuesta?', ['Solo personal nuevo.','Solo TX.','Taller designado o Cabo A.','Solo Control de Inventarios central.'],'C'),
 ('Revisión y control','¿Qué implica tener una serie extraviada con expediente al cerrar proyecto?', ['Que regresó físicamente.','Que fue reparada.','Que se borró.','Que está justificada como no recuperada.'],'D'),
]

out=Path(__file__).parent/'ejemplos'/'Plantilla_20_preguntas.xlsx'
out.parent.mkdir(parents=True,exist_ok=True)
wb=Workbook();ws=wb.active;ws.title='Preguntas'
ws.append(['Tema','Pregunta','A','B','C','D','Correcta','Imagen'])
for n,(section,prompt,opts,letter) in enumerate(questions):
    ws.append([section,prompt,*opts,letter,'conector_ejemplo.png' if n==4 else ''])
ws.freeze_panes='C2'
ws.auto_filter.ref=f'A1:H{len(questions)+1}'
for col,width in {'A':21,'B':78,'C':42,'D':42,'E':42,'F':42,'G':13,'H':28}.items():ws.column_dimensions[col].width=width
for cell in ws[1]:
    cell.font=Font(bold=True,color='FFFFFF')
    cell.fill=PatternFill('solid',fgColor='204D67')
    cell.alignment=Alignment(wrap_text=True)
for row in ws.iter_rows(min_row=2):
    for cell in row:cell.alignment=Alignment(wrap_text=True,vertical='top')
    ws.row_dimensions[row[0].row].height=50
v=DataValidation(type='list',formula1='"A,B,C,D"',allow_blank=False)
ws.add_data_validation(v);v.add(f'G2:G{len(questions)+1}')
info=wb.create_sheet('LEEME')
for line in ['PLANTILLA V1 — EXAMEN DE OPCIÓN MÚLTIPLE','El generador solo lee la hoja Preguntas.',
             'Columnas A–H, Imagen es opcional. Una fila = una pregunta.',
             'Correcta es la letra de la opción A, B, C o D, no el texto.',
             'Las series son FICTICIAS y no se deben usar en registros de material.',
             'No uses fórmulas o macros. Para Imagen, coloca solo un nombre PNG/JPG en ejemplos/imagenes.',
             'No cambies el encabezado ni insertes filas vacías intermedias.',
             'Se generan PDFs de cuadernillo, hoja para responder y acetato superponible.']:
    info.append([line])
info.column_dimensions['A'].width=100
wb.save(out)
print(out)

# Recurso de demostración original y genérico; no representa marca ni equipo real.
from PIL import Image, ImageDraw
folder=out.parent/'imagenes';folder.mkdir(exist_ok=True)
pic=Image.new('RGB',(720,260),'white');dr=ImageDraw.Draw(pic)
dr.rounded_rectangle((24,30,696,225),radius=22,outline='#155973',width=5)
dr.ellipse((102,95,183,176),fill='#d1edef',outline='#155973',width=5)
dr.line((183,134,435,134),fill='#155973',width=13)
dr.rounded_rectangle((432,103,560,165),radius=9,outline='#155973',fill='#eef5f7',width=5)
dr.text((50,200),'Esquema ilustrativo ficticio para la pregunta.',fill='#4a6876')
pic.save(folder/'conector_ejemplo.png')
logo=Image.new('RGB',(360,150),'white');dc=ImageDraw.Draw(logo)
dc.rounded_rectangle((10,10,350,140),radius=20,fill='#173c51')
dc.ellipse((24,35,105,115),outline='#62d1d4',width=7)
dc.text((125,50),'EMPRESA DEMO',fill='white')
logo.save(folder/'logo_ejemplo.png')
print('Recursos de demostración en:',folder)
