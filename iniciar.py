"""Diseñador de evaluaciones para Windows y Linux (Tkinter, sin servidor).

Los campos de identidad son libres; la vista previa se actualiza al escribir,
y únicamente el botón Generar escribe PDFs en disco.
"""
from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
from PIL import ImageTk
from estudio_diseno import open_design_studio

from src.evaluaciones.core import ExamError, generate, read_questions
from vista_previa import PreviewData, render_preview
from biblioteca import (save_exam, load_exam, list_exams, delete_exam, restore_exam, purge_exam,
    export_workbook, hex_color,
    DEFAULT_COLOR_TITLE, DEFAULT_COLOR_SUBTITLE)
from editor_preguntas import edit_questions

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
    color_title = tk.StringVar(value=DEFAULT_COLOR_TITLE)
    color_subtitle = tk.StringVar(value=DEFAULT_COLOR_SUBTITLE)
    color_answers = tk.StringVar(value='#213A4C')
    paper_choice = tk.StringVar(value='A4')
    body_font = tk.StringVar(value='9.0')
    reuse_booklet = tk.BooleanVar(value=True)
    large_preview: list[dict | None] = [None]

    lib_name = tk.StringVar(value='')
    active_id: list[str | None] = [None]
    db_path = BASE / 'datos' / 'biblioteca.sqlite3'
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
    tk.Label(mainarea,text='Preparar y diseñar documentos',bg=BG,fg=NAVY,
             font=('Segoe UI',21,'bold')).pack(anchor='w',padx=20)
    tk.Label(mainarea,text='Configura cualquier empresa, público o proyecto. Cuadernillos reutilizables y formatos Carta, A4 u Oficio.',
             bg=BG,fg=GRAY,font=('Segoe UI',9)).pack(anchor='w',padx=20,pady=(3,10))

    toolbar=tk.Frame(mainarea,bg=BG)
    toolbar.pack(fill='x',padx=18,pady=(0,9))

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
        if chosen:
            active_id[0]=None
            lib_name.set('')
            file_var.set(chosen)

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
    label('Colores del documento (RGB)',14)
    colorsrow=tk.Frame(content,bg=WHITE)
    colorsrow.grid(row=15,column=0,columnspan=2,sticky='ew',padx=17,pady=(2,13))
    colorsrow.columnconfigure(1,weight=1)
    colorsrow.columnconfigure(3,weight=1)
    tk.Label(colorsrow,text='Título',bg=WHITE,fg=NAVY).grid(row=0,column=0,sticky='w')
    ttk.Entry(colorsrow,textvariable=color_title,width=10).grid(row=0,column=1,sticky='ew',padx=(5,5))
    tk.Label(colorsrow,text='Subtítulo',bg=WHITE,fg=NAVY).grid(row=0,column=2,sticky='w',padx=(8,0))
    ttk.Entry(colorsrow,textvariable=color_subtitle,width=10).grid(row=0,column=3,sticky='ew',padx=(5,5))
    def choose_color(var, label):
        try:current=hex_color(var.get())
        except ExamError:current='#213A4C'
        rgb=colorchooser.askcolor(color=current,
                                  title='Elegir color RGB para '+label,parent=root)
        if rgb and rgb[1]:var.set(rgb[1].upper())
    tk.Button(colorsrow,text='Paleta',command=lambda:choose_color(color_title,'título'),
              bg='#e4edf1',bd=0,padx=8,pady=7,cursor='hand2').grid(row=1,column=1,sticky='w',pady=(5,0))
    tk.Button(colorsrow,text='Paleta',command=lambda:choose_color(color_subtitle,'subtítulo'),
              bg='#e4edf1',bd=0,padx=8,pady=7,cursor='hand2').grid(row=1,column=3,sticky='w',pady=(5,0))
    # Opciones que gobiernan la paginación real: no son atributos solo visuales.
    label('Impresión y ahorro de papel',19)
    setting=tk.Frame(content,bg=WHITE)
    setting.grid(row=20,column=0,columnspan=2,sticky='ew',padx=17,pady=(4,5))
    tk.Label(setting,text='Papel',bg=WHITE,fg=NAVY).pack(side='left')
    paper_box=ttk.Combobox(setting,textvariable=paper_choice,state='readonly',width=12,
        values=('A4','Carta','Oficio'))
    paper_box.pack(side='left',padx=(7,14))
    tk.Label(setting,text='Letra (pt)',bg=WHITE,fg=NAVY).pack(side='left')
    font_box=ttk.Combobox(setting,textvariable=body_font,state='readonly',width=7,
        values=tuple(f'{x/2:.1f}' for x in range(16,25)))
    font_box.pack(side='left',padx=(7,0))
    tk.Checkbutton(content, text='Cuadernillo reutilizable: sin nombre ni folio, con marca de agua',
        variable=reuse_booklet,bg=WHITE,fg=NAVY,activebackground=WHITE,
        anchor='w',wraplength=490).grid(row=21,column=0,columnspan=2,sticky='w',padx=17,pady=(3,7))
    tk.Label(content,text='Color de impresión: hoja de respuestas (RGB)',bg=WHITE,
        fg=NAVY,font=('Segoe UI',9)).grid(row=22,column=0,columnspan=2,sticky='w',padx=17,pady=(3,4))
    ans_row=tk.Frame(content,bg=WHITE)
    ans_row.grid(row=23,column=0,columnspan=2,sticky='ew',padx=17,pady=(0,10))
    ttk.Entry(ans_row,textvariable=color_answers,width=15).pack(side='left',padx=(0,8))
    tk.Button(ans_row,text='Paleta RGB',command=lambda:choose_color(color_answers,'hoja de respuestas'),
        bg='#e4edf1',bd=0,padx=8,pady=7,cursor='hand2').pack(side='left')
    tk.Label(ans_row,text='Cambia tintas y círculos, no el fondo blanco.',bg=WHITE,
        fg=GRAY,font=('Segoe UI',8)).pack(side='left',padx=(9,0))
    label('Nombre en mi biblioteca (opcional)',24)
    field(lib_name,25)
    tk.Label(content,text='El campo de grupo admite cualquier texto: colaboradores, alumnos, proveedores, turno o área.',
             bg=WHITE,fg=GRAY,font=('Segoe UI',8),wraplength=480,justify='left').grid(
             row=26,column=0,columnspan=2,padx=17,pady=(8,15),sticky='w')

    tk.Label(right,text='VISTA PREVIA',bg=WHITE,fg=TEAL,
             font=('Segoe UI',10,'bold')).pack(anchor='w',padx=16,pady=(13,4))
    tabs=tk.Frame(right,bg=WHITE)
    tabs.pack(fill='x',padx=13,pady=(0,5))
    tab_buttons={}
    tk.Button(right,text='Abrir editor visual · PDF real',command=lambda:open_large_preview(),
        bg='#e4edf1',fg=NAVY,bd=0,padx=11,pady=7,cursor='hand2',
        font=('Segoe UI',9,'bold')).pack(anchor='center',pady=(0,7))
    preview_label=tk.Label(right,bg='#edf3f6',bd=0)
    preview_label.pack(anchor='center',pady=(1,5))
    preview_info=tk.StringVar(value='Cargando vista previa…')
    tk.Label(right,textvariable=preview_info,bg=WHITE,fg=GRAY,
             font=('Segoe UI',9),wraplength=390,justify='center').pack(padx=10,pady=(3,1))
    tk.Label(right,text='Vista orientativa. En «Editar diseño» verás\nel PDF real y podrás ajustar sus propiedades.',
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

    def preview_data():
        """Configuración única para ambas vistas; evita divergencias de colores."""
        questions=load_questions()
        logo=Path(logo_var.get().strip()) if logo_var.get().strip() else None
        def safe_color(var,default):
            try:return hex_color(var.get())
            except ExamError:return default
        return PreviewData(empresa=company_var.get().strip(),grupo=group_var.get().strip(),
             titulo=title_var.get().strip(),subtitulo=subtitle_var.get().strip(),
             instrucciones=instruction.get('1.0','end-1c').strip(),questions=questions,logo=logo,
             color_titulo=safe_color(color_title,DEFAULT_COLOR_TITLE),
             color_subtitulo=safe_color(color_subtitle,DEFAULT_COLOR_SUBTITLE),
             color_respuestas=safe_color(color_answers,'#213A4C'),
             tamano_papel=paper_choice.get(),letra=float(body_font.get()),
             reutilizable=bool(reuse_booklet.get()))

    def open_large_preview():
        """Abre el editor dedicado, con controles junto al PDF real.

        Las variables se comparten con el formulario principal: ningún ajuste
        se pierde al regresar, y sólo Guardar lo persiste en la biblioteca.
        """
        if large_preview[0] is not None:
            try:
                large_preview[0]['win'].lift()
                large_preview[0]['win'].focus_force()
                return
            except tk.TclError:
                large_preview[0] = None
        vars_studio = {
            'titulo': title_var, 'subtitulo': subtitle_var,
            'empresa': company_var, 'grupo': group_var,
            'archivo': file_var, 'logotipo': logo_var,
            'papel': paper_choice, 'letra': body_font,
            'reutilizable': reuse_booklet, 'color_titulo': color_title,
            'color_subtitulo': color_subtitle, 'color_respuestas': color_answers,
        }
        editor=open_design_studio(root,datos_fn=preview_data,variables=vars_studio,
            editar_preguntas=edit_current,guardar=save_in_library,generar=run)
        large_preview[0]={'win':editor}
        def clear_state(event):
            if event.widget is editor:
                large_preview[0]=None
        editor.bind('<Destroy>',clear_state,add='+')

    def render():
        scheduled[0]=None
        data=preview_data()
        questions=data.questions
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

    for var in (file_var,logo_var,company_var,group_var,title_var,subtitle_var,color_title,color_subtitle,color_answers,paper_choice,body_font,reuse_booklet):
        var.trace_add('write',schedule)
    right.bind('<Configure>',schedule)
    instruction.bind('<KeyRelease>',schedule)
    instruction.bind('<<Paste>>',lambda event:root.after(100,schedule))

    def template_download():
        origin=BASE/'plantillas'/'Plantilla_Cuestionario.xlsx'
        if not origin.is_file():
            messagebox.showerror('Plantilla no disponible','No se encontró la plantilla incluida en el proyecto.',parent=root)
            return
        target=filedialog.asksaveasfilename(parent=root,defaultextension='.xlsx',
                initialfile='Plantilla_Cuestionario.xlsx',title='Guardar plantilla para rellenar',
                filetypes=[('Archivo de Excel','*.xlsx')])
        if not target:return
        try:
            from shutil import copyfile
            copyfile(origin,target)
            status.set('Plantilla guardada en: '+str(target))
        except OSError as exc:messagebox.showerror('No se pudo guardar',str(exc),parent=root)

    def save_in_library(*, silent=False):
        try:
            questions=load_questions()
            key=save_exam(db_path,nombre=lib_name.get().strip() or title_var.get().strip(),
                empresa=company_var.get(),grupo=group_var.get(),titulo=title_var.get(),
                subtitulo=subtitle_var.get(),instrucciones=instruction.get('1.0','end-1c'),
                questions=questions,logo=Path(logo_var.get()) if logo_var.get().strip() else None,
                color_titulo=color_title.get(),color_subtitulo=color_subtitle.get(),
                color_respuestas=color_answers.get(),tamano_papel=paper_choice.get(),
                letra=float(body_font.get()),reutilizable=bool(reuse_booklet.get()),exam_id=active_id[0])
            active_id[0]=key
            if not lib_name.get().strip():lib_name.set(title_var.get())
            status.set('Cuestionario guardado en biblioteca local SQLite')
            if not silent:
                messagebox.showinfo('Biblioteca','Cuestionario, respuestas, imágenes y datos guardados. Puedes abrirlo o editarlo después.',parent=root)
            return key
        except (ExamError,OSError,ValueError) as exc:
            if not silent:messagebox.showerror('No se guardó',str(exc),parent=root)
            return None

    def edit_current():
        questions=load_questions()
        if not questions:
            messagebox.showerror('Faltan preguntas',cache['error'] or 'Selecciona primero un Excel válido.',parent=root)
            return
        edited=edit_questions(root,questions)
        if edited is None:return
        new_path=BASE/'datos'/'ediciones'/uuid4().hex/'Preguntas.xlsx'
        try:
            export_workbook(edited,new_path)
        except (ExamError,OSError) as exc:
            messagebox.showerror('Edición no guardada',str(exc),parent=root);return
        file_var.set(str(new_path))
        cache['key']=None
        schedule()
        status.set('Preguntas editadas. Usa «Guardar cuestionario» para conservar los cambios en la biblioteca.')

    def open_library():
        """Gestiona biblioteca y papelera; no elimina archivos PDF ya exportados."""
        win=tk.Toplevel(root);win.title('Biblioteca y papelera de cuestionarios')
        win.geometry('920x560');win.minsize(760,440);win.transient(root);win.grab_set()
        tk.Label(win,text='Biblioteca de cuestionarios',font=('Segoe UI',17,'bold'),
                 padx=18,pady=12).pack(anchor='w')
        options=tk.Frame(win,padx=18);options.pack(fill='x')
        trashed=tk.BooleanVar(master=win,value=False)
        tk.Checkbutton(options,text='Mostrar papelera (cuestionarios eliminados)',
            variable=trashed,command=lambda:refresh(),font=('Segoe UI',10)).pack(side='left')
        frame=tk.Frame(win,padx=18,pady=8);frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=('nombre','grupo','preguntas','revision','fecha'),
                          show='headings',selectmode='browse')
        for col,caption,width in [('nombre','Nombre',280),('grupo','Área / grupo',160),
                                  ('preguntas','Preguntas',85),('revision','Rev.',48),
                                  ('fecha','Modificado UTC',175)]:
            tree.heading(col,text=caption)
            tree.column(col,width=width,stretch=col in ('nombre','grupo'))
        bar=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y')
        tree.pack(fill='both',expand=True)
        hint=tk.StringVar(master=win,value='Elige un cuestionario para abrirlo o enviarlo a la papelera.')
        tk.Label(win,textvariable=hint,padx=18,fg=GRAY,anchor='w').pack(fill='x')
        controls=tk.Frame(win,padx=18,pady=12);controls.pack(fill='x')
        def pick():
            selected=tree.selection()
            return selected[0] if selected else None
        def refresh():
            tree.delete(*tree.get_children())
            for item in list_exams(db_path,trash=trashed.get()):
                tree.insert('','end',iid=item['id'],values=(item['nombre'],item['grupo'],
                    item['total'],item['revision'],item['actualizado_en'][:19].replace('T',' ')))
            deleted=trashed.get()
            opener.config(state='disabled' if deleted else 'normal')
            remover.config(text='Eliminar definitivamente' if deleted else 'Eliminar de biblioteca',
                           bg='#a73535' if deleted else '#e6b6b1')
            recover.config(state='normal' if deleted else 'disabled')
            hint.set('Papelera: restaura o elimina definitivamente con confirmación.' if deleted
                    else 'Eliminar mueve a la papelera: podrás recuperar tus preguntas e imágenes.')
        def load_selected():
            if trashed.get():return
            item=pick()
            if not item:return
            try:
                exam=load_exam(db_path,item,BASE/'datos'/'biblioteca_cache')
                workbook=export_workbook(exam.questions,BASE/'datos'/'biblioteca_cache'/exam.id/'Preguntas.xlsx')
            except (ExamError,OSError,ValueError) as exc:
                messagebox.showerror('No se pudo abrir',str(exc),parent=win);return
            active_id[0]=exam.id
            lib_name.set(exam.nombre);company_var.set(exam.empresa);group_var.set(exam.grupo)
            title_var.set(exam.titulo);subtitle_var.set(exam.subtitulo)
            color_title.set(exam.color_titulo);color_subtitle.set(exam.color_subtitulo)
            color_answers.set(exam.color_respuestas);paper_choice.set(exam.tamano_papel)
            body_font.set(f'{exam.letra:.1f}');reuse_booklet.set(exam.reutilizable)
            instruction.delete('1.0','end');instruction.insert('1.0',exam.instrucciones)
            logo_var.set(str(exam.logo) if exam.logo else '')
            file_var.set(str(workbook));cache['key']=None
            status.set(f'Cuestionario cargado · revisión {exam.revision}. Puedes editarlo y diseñarlo.')
            win.destroy();schedule()
        def delete_selected():
            item=pick()
            if not item:return
            name=tree.item(item,'values')[0]
            if trashed.get():
                # Esta acción es irreversible: doble validación para evitar errores.
                if not messagebox.askyesno('Eliminar definitivamente',
                    f'¿Borrar permanentemente «{name}» y todas sus imágenes de la base?\n'
                    'Los PDF exportados previamente no se eliminarán.',parent=win):return
                confirmed=simpledialog.askstring('Confirmación final',
                    f'Escribe ELIMINAR para confirmar el borrado de «{name}»:',parent=win)
                if confirmed!='ELIMINAR':return
                operation=purge_exam
            else:
                if not messagebox.askyesno('Mover a papelera',
                   f'¿Eliminar «{name}» de la biblioteca?\n'
                   'Podrás restaurarlo desde la papelera.',parent=win):return
                operation=delete_exam
            try:operation(db_path,item)
            except (ExamError,OSError) as exc:
                messagebox.showerror('No se pudo eliminar',str(exc),parent=win);return
            if active_id[0]==item:
                # Evitar que un Guardar posterior resucite o sobrescriba el eliminado.
                active_id[0]=None
                lib_name.set('')
                status.set('Cuestionario eliminado de biblioteca; los archivos PDF siguen intactos.')
            refresh()
        def restore_selected():
            item=pick()
            if not item or not trashed.get():return
            try:restore_exam(db_path,item)
            except (ExamError,OSError) as exc:
                messagebox.showerror('No se pudo restaurar',str(exc),parent=win);return
            refresh()
            hint.set('Cuestionario restaurado: aparece nuevamente en la biblioteca.')
        opener=tk.Button(controls,text='Abrir para editar',command=load_selected,
            bg=TEAL,fg=WHITE,bd=0,padx=12,pady=9)
        opener.pack(side='left')
        recover=tk.Button(controls,text='Restaurar',command=restore_selected,
            bd=0,padx=12,pady=9)
        recover.pack(side='left',padx=7)
        remover=tk.Button(controls,text='Eliminar de biblioteca',command=delete_selected,
            bg='#e6b6b1',fg=NAVY,bd=0,padx=12,pady=9)
        remover.pack(side='left')
        ttk.Button(controls,text='Actualizar',command=refresh).pack(side='left',padx=8)
        ttk.Button(controls,text='Cerrar',command=win.destroy).pack(side='right')
        tree.bind('<Double-Button-1>',lambda e:load_selected())
        refresh()

    tk.Button(toolbar,text='Editar diseño · PDF real',command=open_large_preview,
        bg=NAVY,fg=WHITE,bd=0,padx=10,pady=9,cursor='hand2',
        font=('Segoe UI',9,'bold')).pack(side='left',padx=(0,7))
    tk.Button(toolbar,text='Descargar plantilla Excel',command=template_download,
        bg='#E4EDF1',fg=NAVY,bd=0,padx=9,pady=9,cursor='hand2').pack(side='left',padx=(0,7))
    tk.Button(toolbar,text='Mis cuestionarios',command=open_library,
        bg='#E4EDF1',fg=NAVY,bd=0,padx=9,pady=9,cursor='hand2').pack(side='left',padx=(0,7))
    tk.Button(toolbar,text='Editar preguntas',command=edit_current,
        bg='#E4EDF1',fg=NAVY,bd=0,padx=9,pady=9,cursor='hand2').pack(side='left',padx=(0,7))
    tk.Button(toolbar,text='Guardar cuestionario',command=save_in_library,
        bg=TEAL,fg=WHITE,bd=0,padx=9,pady=9,cursor='hand2').pack(side='left')

    def run():
        btn.config(state='disabled',text='Generando…')
        root.update_idletasks()
        try:
            folder=generate(Path(file_var.get()),BASE/'salidas',title_var.get(),subtitle_var.get(),
                empresa=company_var.get(),puesto=group_var.get(),
                instrucciones=instruction.get('1.0','end-1c'),
                logo=Path(logo_var.get()) if logo_var.get().strip() else None,
                color_titulo=color_title.get(),color_subtitulo=color_subtitle.get(),
                color_respuestas=color_answers.get(),tamano_papel=paper_choice.get(),
                letra=float(body_font.get()),reutilizable=bool(reuse_booklet.get()))
        except (ExamError,OSError,ValueError) as exc:
            status.set('Revisa los datos · no se crearon los documentos.')
            messagebox.showerror('No se pudo generar la evaluación',str(exc),parent=root)
        except Exception as exc:
            status.set('Error al generar los documentos.')
            messagebox.showerror('Error inesperado',str(exc),parent=root)
        else:
            last_output[0]=folder
            # Las evaluaciones generadas también se conservan para reabrirlas.
            saved=save_in_library(silent=True)
            status.set('Documentos generados: '+folder.name)
            openbtn.configure(state='normal')
            messagebox.showinfo('Evaluación generada',
               'Se generaron los cuatro PDF, una copia de las preguntas y se guardó en la biblioteca' +
               (' local.' if saved else ' (revisa la biblioteca para guardarlo).') + '\n\n'+str(folder)+
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
