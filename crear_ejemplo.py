"""Regenera un EXAMEN DEMOSTRATIVO totalmente genérico, sin datos empresariales.

El programa solo lee la pestaña Preguntas; LEEME permite enseñar el formato
sin que el personal tenga que conocer Python. No reemplaza un XLSX existente.
"""
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent
OUT = BASE / 'ejemplos' / 'Plantilla_20_preguntas.xlsx'
# Ejercicios sencillos y atemporales, útiles para cualquier institución.
QUESTIONS = [
 ('Matemáticas','¿Cuánto es 7 + 5?',('10','11','12','13'),'C'),
 ('Matemáticas','¿Cuántos lados tiene un triángulo?',('2','3','4','5'),'B'),
 ('Matemáticas','¿Cuál es la mitad de 80?',('20','30','40','50'),'C'),
 ('Matemáticas','¿Cuál de los siguientes números es par?',('17','21','26','33'),'C'),
 ('Matemáticas','¿Cuánto es 3 × 4?',('7','9','12','14'),'C'),
 ('Lenguaje','¿Cuál de estas palabras es un sustantivo?',('Correr','Azul','Libro','Rápido'),'C'),
 ('Lenguaje','¿Cuál oración usa signos de interrogación?',('Buenos días.','¿Cómo estás?','Hasta luego.','Hola.'),'B'),
 ('Lenguaje','¿Cuál es el plural de «flor»?',('Floritos','Flores','Floras','Florales'),'B'),
 ('Lenguaje','¿Qué signo indica una pausa breve en una oración?',('Punto final','Coma','Comillas','Dos puntos'),'B'),
 ('Lenguaje','¿Qué palabra es un verbo?',('Escribir','Mesa','Nube','Camino de tierra'),'A'),
 ('Ciencias','¿Cuál es el estado sólido del agua?',('Vapor','Lluvia','Hielo','Niebla'),'C'),
 ('Ciencias','¿Qué astro ilumina la Tierra durante el día?',('La Luna','El Sol','Marte','Venus'),'B'),
 ('Ciencias','¿Qué instrumento mide la temperatura?',('Regla','Brújula','Termómetro','Balanza'),'C'),
 ('Ciencias','¿Cuál es el planeta donde vivimos?',('Marte','Venus','Tierra','Júpiter'),'C'),
 ('Ciencias','¿Qué órgano se utiliza principalmente para ver?',('Oído','Ojo','Nariz','Lengua'),'B'),
 ('Pensamiento lógico','Si hoy es lunes, ¿qué día sigue?',('Domingo','Martes','Viernes','Sábado'),'B'),
 ('Pensamiento lógico','Completa la secuencia: 2, 4, 6, ...',('7','8','9','10'),'B'),
 ('Pensamiento lógico','¿Cuál no pertenece al grupo?',('Círculo','Triángulo','Cuadrado','Manzana'),'D'),
 ('Pensamiento lógico','Si dos cajas tienen 3 libros cada una, ¿cuántos libros hay?',('3','4','6','9'),'C'),
 ('Pensamiento lógico','Según la imagen, ¿qué forma aparece a la derecha?',('Círculo','Cuadrado','Triángulo','Estrella'),'B'),
]


def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if OUT.exists():
        print('El ejemplo ya existe y no se reemplaza:',OUT)
        return
    book=Workbook();sheet=book.active;sheet.title='Preguntas'
    sheet.append(['Tema','Pregunta','A','B','C','D','Correcta','Imagen'])
    for n,(tema,pregunta,options,correcta) in enumerate(QUESTIONS):
        sheet.append([tema,pregunta,*options,correcta,'figuras_ejemplo.png' if n==19 else ''])
    sheet.freeze_panes='C2';sheet.auto_filter.ref=f'A1:H{sheet.max_row}'
    for col,width in {'A':24,'B':73,'C':36,'D':36,'E':36,'F':36,'G':13,'H':27}.items():
        sheet.column_dimensions[col].width=width
    for cell in sheet[1]:
        cell.font=Font(bold=True,color='FFFFFF')
        cell.fill=PatternFill('solid',fgColor='204D67')
        cell.alignment=Alignment(wrap_text=True)
    for row in sheet.iter_rows(min_row=2):
        sheet.row_dimensions[row[0].row].height=44
        for cell in row:cell.alignment=Alignment(wrap_text=True,vertical='top')
    choices=DataValidation(type='list',formula1='"A,B,C,D"',allow_blank=False)
    sheet.add_data_validation(choices);choices.add(f'G2:G{sheet.max_row}')
    guide=book.create_sheet('LEEME')
    for line in ('EXAMEN DEMOSTRATIVO - CULTURA GENERAL',
        'Es un ejemplo educativo. No contiene datos ni procesos de ninguna empresa.',
        'El programa solo lee la pestaña Preguntas.',
        'Las columnas son Tema, Pregunta, A, B, C, D, Correcta, Imagen.',
        'En Correcta escribe la letra A/B/C/D, no el texto.',
        'La imagen opcional debe estar en la subcarpeta imagenes junto al Excel.',
        'No se permiten macros, fórmulas ni filas en blanco intercaladas.'):
        guide.append([line])
    guide.column_dimensions['A'].width=105
    book.save(OUT)
    image_dir=OUT.parent/'imagenes';image_dir.mkdir(exist_ok=True)
    shape=Image.new('RGB',(720,220),'white');draw=ImageDraw.Draw(shape)
    draw.ellipse((35,52,179,196),outline='#26728A',width=7)
    draw.polygon([(270,195),(346,53),(423,195)],outline='#26728A',width=7)
    draw.rectangle((515,53,668,195),outline='#26728A',width=7)
    shape.save(image_dir/'figuras_ejemplo.png')
    print('Plantilla genérica creada:',OUT)


if __name__=='__main__':
    main()
