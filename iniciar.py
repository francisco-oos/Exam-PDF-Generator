"""Diseñador de evaluaciones para Windows y Linux (Tkinter, sin servidor).

Los campos de identidad son libres; la vista previa se actualiza al escribir,
y únicamente el botón Generar escribe PDFs en disco.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import ImageTk

from src.evaluaciones.core import ExamError, generate, read_questions
from vista_previa import PreviewData, render_preview

BASE = Path(__file__).resolve().parent
NAVY = '#132d41'
SLATE = '#223f52'
TEAL = '#0b7988'
WHITE = '#ffffff'
BG = '#f3f6f8'
GRAY = '#617382'


def open_folder(path: Path):
    """Abrir una ruta local únicamente por acción explícita; no usar shell=True."""
    if sys.platform == 'win32':
        os.startfile(str(path))
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(path)])
    else:
        subprocess.Popen(['xdg-open', str(path)])


def build_ui():
    """Construir la ventana sin entrar al ciclo de eventos (permite smoke tests)."""
    root = tk.Tk()
    root.title('Generador de evaluaciones | Diseño empresarial')
    root.geometry('1340x818')
    root.minsize(1120, 720)
    root.configure(bg=BG)

    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('Modern.TEntry', padding=8, bordercolor='#ced8df', lightcolor='#ced8df',
                    fieldbackground=WHITE, font=('Segoe UI', 10))
    style.configure('Modern.TLabel', background=WHITE, foreground=NAVY,
                    font=('Segoe UI', 9))

    file_var = tk.StringVar(value=str(BASE / 'ejemplos' / 'Plantilla_20_preguntas.xlsx'))
    logo_var = tk.StringVar(value='')
    company_var = tk.StringVar(value='')
    group_var = tk.StringVar(value='')
    title_var = tk.StringVar(value='Evaluación de conocimientos')
    subtitle_var = tk.StringVar(value='')
    current_view = tk.StringVar(value='Cuadernillo')
    status = tk.StringVar(value='Listo para diseñar · Tus archivos originales no se modifican')
    last_output: list[Path | None] = [None]
    cache: dict = {'key': None, 'questions': (), 'error': None}
    scheduled: list[str | None] = [None]

    sidebar = tk.Frame(root, bg=NAVY, width=223)
    sidebar.pack(side='left', fill='y')
    sidebar.pack_propagate(False)
    tk.Label(sidebar, text='EVALUACIONES', bg=NAVY, fg='#66d6d7',
             font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=22, pady=(30, 4))
    tk.Label(sidebar, text='Diseña, imprime\ny evalúa.', bg=NAVY, fg=WHITE,
             font=('Segoe UI', 18, 'bold'), justify='left').pack(anchor='w', padx=22, pady=(4, 29))
    for no, heading, description in [
        ('01', 'IDENTIDAD', 'Empresa, área y título libres'),
        ('02', 'CONTENIDO', 'Preguntas desde Excel'),
        ('03', 'PREVISUALIZAR', 'Cuadernillo, hoja y acetato'),
    ]:
        panel=tk.Frame(sidebar,bg=SLATE,padx=10,pady=12)
        panel.pack(fill='x',padx=12,pady=5)
        tk.Label(panel,text=no,bg=SLATE,fg='#71d5d6',font=('Segoe UI',12,'bold')).pack(side='left',padx=(0,9))
        col=tk.Frame(panel,bg=SLATE);col.pack(side='left',fill='x',expand=True)
        tk.Label(col,text=heading,bg=SLATE,fg=WHITE,font=('Segoe UI',9,'bold')).pack(anchor='w')
        tk.Label(col,text=description,bg=SLATE,fg='#c3d4dd',font=('Segoe UI',8),
                 wraplength=149,justify='left').pack(anchor='w')
    tk.Label(sidebar,text='Datos locales y sin suscripción\nLicencia MIT · Uso empresarial',
             bg=NAVY,fg='#bbced7',font=('Segoe UI',9),justify='left').pack(
             side='bottom',anchor='w',padx=19,pady=23)

    mainarea=tk.Frame(root,bg=BG)
    mainarea.pack(side='left',fill='both',expand=True)
    tk.Label(mainarea,text='NUEVA EVALUACIÓN',bg=BG,fg=TEAL,
             font=('Segoe UI',10,'bold')).pack(anchor='w',padx=20,pady=(17,2))
    tk.Label(mainarea,text='Preparar documentos',bg=BG,fg=NAVY,
             font=('Segoe UI',21,'bold')).pack(anchor='w',padx=20)
    tk.Label(mainarea,text='Configura cualquier empresa, público o proyecto. Los documentos se generan en PDF A4.',
             bg=BG,fg=GRAY,font=('Segoe UI',9)).pack(anchor='w',padx=20,pady=(3,10))

    bottom=tk.Frame(mainarea,bg=BG)
    bottom.pack(side='bottom',fill='x',padx=19,pady=(7,16))
    tk.Label(bottom,textvariable=status,bg=BG,fg=GRAY,font=('Segoe UI',9),
             wraplength=405,justify='left').pack(side='left',fill='x',expand=True)

    body=tk.Frame(mainarea,bg=BG)
    body.pack(fill='both',expand=True,padx=(18,19),pady=(0,9))
    left=tk.Frame(body,bg=WHITE,highlightbackground='#dae5eb',highlightthickness=1)
    left.pack(side='left',fill='both',expand=True,padx=(0,12))
    right=tk.Frame(body,bg=WHITE,width=426,highlightbackground='#dae5eb',highlightthickness=1)
    right.pack(side='left',fill='y')
    right.pack_propagate(False)

    scroll=tk.Canvas(left,bg=WHITE,bd=0,highlightthickness=0)
    scr=ttk.Scrollbar(left,orient='vertical',command=scroll.yview)
    scroll.configure(yscrollcommand=scr.set)
    scr.pack(side='right',fill='y')
    scroll.pack(side='left',fill='both',expand=True)
    content=tk.Frame(scroll,bg=WHITE)
    frame_window=scroll.create_window((0,0),window=content,anchor='nw')
    content.bind('<Configure>',lambda event: scroll.configure(scrollregion=scroll.bbox('all')))
    scroll.bind('<Configure>',lambda event: scroll.itemconfigure(frame_window,width=event.width))
    content.columnconfigure(0,weight=1)
    content.columnconfigure(1,weight=1)

    def label(text,row,column=0,span=2):
        ttk.Label(content,text=text,style='Modern.TLabel').grid(row=row,column=column,columnspan=span,
                                              sticky='w',pady=(8,4),padx=(17,11))

    def field(var,row,col=0,span=2):
        widget=ttk.Entry(content,textvariable=var,style='Modern.TEntry')
        widget.grid(row=row,column=col,columnspan=span,sticky='ew',
                    padx=(17,7) if col==0 else (7,17))
        return widget

    label('Empresa / institución (opcional)',0,0,1)
    label('Área, público o grupo (libre)',0,1,1)
    field(company_var,1,0,1)
    field(group_var,1,1,1)
    label('Título de la evaluación',2)
    field(title_var,3)
    label('Subtítulo (opcional)',4)
    field(subtitle_var,5)
    label('Archivo de preguntas (.xlsx)',6)
    row_xlsx=tk.Frame(content,bg=WHITE)
    row_xlsx.grid(row=7,column=0,columnspan=2,sticky='ew',padx=(17,17))
    row_xlsx.columnconfigure(0,weight=1)
    ttk.Entry(row_xlsx,textvariable=file_var,style='Modern.TEntry').grid(row=0,column=0,sticky='ew')

    def choose_xlsx():
        chosen=filedialog.askopenfilename(title='Seleccionar Excel de preguntas',
                    filetypes=[('Libro de Excel','*.xlsx')],parent=root)
        if chosen:file_var.set(chosen)

    tk.Button(row_xlsx,text='Examinar',command=choose_xlsx,bg='#ecf2f5',fg=NAVY,
              bd=0,padx=13,pady=10,cursor='hand2',font=('Segoe UI',9,'bold')).grid(row=0,column=1,padx=(8,0))
    tk.Label(content,text='Si hay imágenes, colócalas en «imagenes» junto al XLSX y escribe su nombre en la columna Imagen.',
             bg=WHITE,fg=GRAY,font=('Segoe UI',8),wraplength=475,
             justify='left').grid(row=8,column=0,columnspan=2,sticky='w',padx=17,pady=(5,4))
    label('Logotipo institucional (PNG o JPEG, opcional)',9)
    logorow=tk.Frame(content,bg=WHITE)
    logorow.grid(row=10,column=0,columnspan=2,sticky='ew',padx=(17,17))
    logorow.columnconfigure(0,weight=1)
    ttk.Entry(logorow,textvariable=logo_var,style='Modern.TEntry').grid(row=0,column=0,sticky='ew')

    def choose_logo():
        chosen=filedialog.askopenfilename(title='Seleccionar logotipo',
                   filetypes=[('Imágenes PNG/JPEG','*.png *.jpg *.jpeg')],parent=root)
        if chosen:logo_var.set(chosen)

    tk.Button(logorow,text='Elegir logo',command=choose_logo,bg='#ecf2f5',fg=NAVY,
              bd=0,padx=13,pady=10,cursor='hand2',font=('Segoe UI',9,'bold')).grid(row=0,column=1,padx=(8,0))
    label('Instrucciones para el participante',11)
    instruction=tk.Text(content,height=4,wrap='word',font=('Segoe UI',10),fg=NAVY,
                        bg='#f9fbfc',relief='flat',highlightthickness=1,
                        highlightbackground='#dce5ea',padx=10,pady=8)
    instruction.grid(row=12,column=0,columnspan=2,sticky='ew',padx=17,pady=(1,8))
    instruction.insert('1.0','Lee cada pregunta y elige una respuesta. Marca tus respuestas únicamente en la hoja separada.')
    tk.Label(content,text='El campo de grupo admite cualquier texto: colaboradores, alumnos, proveedores, turno o área.',
             bg=WHITE,fg=GRAY,font=('Segoe UI',8),wraplength=480,justify='left').grid(
             row=13,column=0,columnspan=2,padx=17,pady=(8,15),sticky='w')

    tk.Label(right,text='VISTA PREVIA',bg=WHITE,fg=TEAL,
             font=('Segoe UI',10,'bold')).pack(anchor='w',padx=16,pady=(13,4))
    tabs=tk.Frame(right,bg=WHITE)
    tabs.pack(fill='x',padx=13,pady=(0,5))
    tab_buttons={}
    preview_label=tk.Label(right,bg='#edf3f6',bd=0)
    preview_label.pack(anchor='center',pady=(1,5))
    preview_info=tk.StringVar(value='Cargando vista previa…')
    tk.Label(right,textvariable=preview_info,bg=WHITE,fg=GRAY,
             font=('Segoe UI',9),wraplength=390,justify='center').pack(padx=10,pady=(3,1))
    tk.Label(right,text='Vista en pantalla orientativa. Para imprimir utiliza\nlos PDF finales A4 al 100 % de escala.',
             bg=WHITE,fg=GRAY,font=('Segoe UI',8),justify='center').pack(padx=10,pady=(0,5))

    def load_questions():
        file=Path(file_var.get()).expanduser()
        try:key=(str(file),file.stat().st_mtime_ns,file.stat().st_size)
        except OSError:key=(str(file),None,None)
        if cache['key']!=key:
            cache['key']=key
            try:
                cache['questions']=tuple(read_questions(file))
                cache['error']=None
            except (ExamError,OSError,ValueError) as exc:
                cache['questions']=()
                cache['error']=str(exc)
        return cache['questions']

    def render():
        scheduled[0]=None
        questions=load_questions()
        logo=Path(logo_var.get().strip()) if logo_var.get().strip() else None
        data=PreviewData(empresa=company_var.get().strip(),grupo=group_var.get().strip(),
             titulo=title_var.get().strip(),subtitulo=subtitle_var.get().strip(),
             instrucciones=instruction.get('1.0','end-1c').strip(),questions=questions,logo=logo)
        try:
            preview_width=max(245,min(370,int((right.winfo_height()-158)*0.707)))
            pic=render_preview(data,current_view.get(),width=preview_width)
            photo=ImageTk.PhotoImage(pic,master=root)
            preview_label.configure(image=photo)
            preview_label.image=photo
        except (OSError,ValueError) as exc:
            preview_info.set('Vista previa no disponible: '+str(exc))
            return
        if cache['error']:
            preview_info.set('Excel pendiente de revisar: '+cache['error'][:135])
        else:
            topics=len({x.section for x in questions})
            preview_info.set(f'{len(questions)} preguntas · {topics} temas · Vista: {current_view.get()}')

    def schedule(*_):
        if scheduled[0] is not None:
            root.after_cancel(scheduled[0])
        scheduled[0]=root.after(250,render)

    def mode(value):
        current_view.set(value)
        for name,button in tab_buttons.items():
            selected=name==value
            button.configure(bg=TEAL if selected else '#eaf1f5',
                             fg=WHITE if selected else NAVY)
        schedule()

    for name in ('Cuadernillo','Respuestas','Acetato'):
        b=tk.Button(tabs,text=name,bd=0,padx=9,pady=8,
                   bg='#eaf1f5',fg=NAVY,cursor='hand2',font=('Segoe UI',9),
                   command=lambda n=name:mode(n))
        b.pack(side='left',padx=3)
        tab_buttons[name]=b
    mode('Cuadernillo')

    for var in (file_var,logo_var,company_var,group_var,title_var,subtitle_var):
        var.trace_add('write',schedule)
    right.bind('<Configure>',schedule)
    instruction.bind('<KeyRelease>',schedule)
    instruction.bind('<<Paste>>',lambda event:root.after(100,schedule))

    def run():
        btn.config(state='disabled',text='Generando…')
        root.update_idletasks()
        try:
            folder=generate(Path(file_var.get()),BASE/'salidas',title_var.get(),subtitle_var.get(),
                empresa=company_var.get(),puesto=group_var.get(),
                instrucciones=instruction.get('1.0','end-1c'),
                logo=Path(logo_var.get()) if logo_var.get().strip() else None)
        except (ExamError,OSError,ValueError) as exc:
            status.set('Revisa los datos · no se crearon los documentos.')
            messagebox.showerror('No se pudo generar la evaluación',str(exc),parent=root)
        except Exception as exc:
            status.set('Error al generar los documentos.')
            messagebox.showerror('Error inesperado',str(exc),parent=root)
        else:
            last_output[0]=folder
            status.set('Documentos generados: '+folder.name)
            openbtn.configure(state='normal')
            messagebox.showinfo('Evaluación generada',
               'Se generaron los cuatro PDF y una copia de las preguntas.\n\n'+str(folder)+
               '\n\nImprime la hoja y el acetato a escala 100 %.',parent=root)
        finally:
            btn.config(state='normal',text='Generar documentos')

    btn=tk.Button(bottom,text='Generar documentos',command=run,fg=WHITE,bg=TEAL,
        activebackground='#096272',activeforeground=WHITE,
        padx=18,pady=11,bd=0,cursor='hand2',font=('Segoe UI',10,'bold'))
    btn.pack(side='right')

    def open_last():
        if last_output[0] is not None:
            try:open_folder(last_output[0])
            except (OSError,FileNotFoundError) as exc:
                messagebox.showerror('No se puede abrir el resultado',str(exc),parent=root)

    openbtn=tk.Button(bottom,text='Abrir resultado',command=open_last,
           fg=NAVY,bg='#e4edf1',padx=13,pady=11,bd=0,cursor='hand2',font=('Segoe UI',9))
    openbtn.config(state='disabled')
    openbtn.pack(side='right',padx=(0,10))
    root.after(50,render)
    return root


def main():
    root=build_ui()
    root.mainloop()


if __name__=='__main__':
    main()
