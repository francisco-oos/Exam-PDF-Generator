"""Interfaz empresarial local (Tkinter): sin servidor ni envío de datos."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from src.evaluaciones.core import ExamError, generate

BASE = Path(__file__).resolve().parent
NAVY = '#132d41'
SLATE = '#223f52'
TEAL = '#0b7988'
WHITE = '#ffffff'
BG = '#f3f6f8'
GRAY = '#617382'


def open_folder(path: Path):
    """Abrir carpeta generada solo tras interacción del usuario; sin shell=True."""
    if sys.platform == 'win32':
        os.startfile(str(path))
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(path)])
    else:
        subprocess.Popen(['xdg-open', str(path)])


def main():
    root = tk.Tk()
    root.title('Generador de evaluaciones | Panel de diseño')
    root.geometry('1040x760')
    root.minsize(920, 670)
    root.configure(bg=BG)

    styles = ttk.Style(root)
    styles.theme_use('clam')
    styles.configure('Modern.TEntry', padding=9, bordercolor='#ced8df', lightcolor='#ced8df',
                     fieldbackground='#ffffff', font=('Segoe UI', 10))
    styles.configure('Modern.TCombobox', padding=7, font=('Segoe UI', 10))
    styles.configure('Modern.TLabel', background=WHITE, foreground=NAVY,
                     font=('Segoe UI', 10))

    file_var = tk.StringVar(value=str(BASE / 'ejemplos' / 'Plantilla_20_preguntas.xlsx'))
    logo_var = tk.StringVar()
    company_var = tk.StringVar(value='Evaluación interna · Empresa')
    title_var = tk.StringVar(value='Evaluación de manejo de material en campo')
    subtitle_var = tk.StringVar(value='Conocimientos y criterios de registro')
    role_var = tk.StringVar(value='Cabos')
    last_output: list[Path | None] = [None]

    sidebar = tk.Frame(root, bg=NAVY, width=268)
    sidebar.pack(side='left', fill='y')
    sidebar.pack_propagate(False)
    tk.Label(sidebar, text='EVALUACIONES', bg=NAVY, fg='#62d3d5',
             font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=26, pady=(35, 2))
    tk.Label(sidebar, text='Diseña, imprime\ny evalúa.', bg=NAVY, fg=WHITE,
             font=('Segoe UI', 22, 'bold'), justify='left').pack(anchor='w', padx=26, pady=(6, 32))
    for icon, number, title, desc in [
        ('01', '01', 'DATOS', 'Identidad, portada y logotipo'),
        ('02', '02', 'PREGUNTAS', 'Plantilla XLSX por temas'),
        ('03', '03', 'ENTREGA', 'Cuadernillo, hoja y acetato'),
    ]:
        wrapper=tk.Frame(sidebar, bg=SLATE, padx=15,pady=13)
        wrapper.pack(fill='x',padx=17,pady=5)
        tk.Label(wrapper,text=number,bg=SLATE,fg='#71d5d6',font=('Segoe UI',13,'bold')).pack(side='left',padx=(0,11))
        txt=tk.Frame(wrapper,bg=SLATE);txt.pack(side='left')
        tk.Label(txt,text=title,bg=SLATE,fg='white',font=('Segoe UI',9,'bold')).pack(anchor='w')
        tk.Label(txt,text=desc,bg=SLATE,fg='#c3d4dd',font=('Segoe UI',8),wraplength=172,justify='left').pack(anchor='w')
    tk.Label(sidebar,text='Sin Internet al generar archivos\nSin suscripción · Datos locales\nLicencia MIT · Uso empresarial',
             bg=NAVY,fg='#bbced7',font=('Segoe UI',9),justify='left',
             wraplength=220).pack(side='bottom',anchor='w',padx=25,pady=27)

    mainarea=tk.Frame(root,bg=BG)
    mainarea.pack(side='right',fill='both',expand=True)
    tk.Label(mainarea,text='NUEVO EXAMEN',bg=BG,fg=TEAL,font=('Segoe UI',10,'bold')).pack(anchor='w',padx=30,pady=(24,2))
    tk.Label(mainarea,text='Preparar evaluación',bg=BG,fg=NAVY,font=('Segoe UI',22,'bold')).pack(anchor='w',padx=30)
    tk.Label(mainarea,text='Un solo examen, hoja de respuestas y clave superponible en acetato.',
             bg=BG,fg=GRAY,font=('Segoe UI',10)).pack(anchor='w',padx=30,pady=(1,12))

    bottom=tk.Frame(mainarea,bg=BG)
    bottom.pack(side='bottom',fill='x',padx=29,pady=(5,20))

    card=tk.Frame(mainarea,bg=WHITE,highlightbackground='#dce5ea',highlightthickness=1)
    card.pack(fill='both',expand=True,padx=29,pady=(2,13))
    content=tk.Frame(card,bg=WHITE)
    content.pack(fill='both',expand=True,padx=21,pady=16)
    content.columnconfigure(0,weight=1)
    content.columnconfigure(1,weight=1)

    def label(parent,text,row,column,span=1):
        ttk.Label(parent,text=text,style='Modern.TLabel').grid(row=row,column=column,columnspan=span,
                                                    sticky='w',pady=(7,4))

    def entry(var,row,col,span=1):
        wid=ttk.Entry(content,textvariable=var,style='Modern.TEntry')
        wid.grid(row=row,column=col,columnspan=span,sticky='ew',padx=(0,13) if col==0 else (0,0))
        return wid

    label(content,'Empresa / encabezado',0,0)
    label(content,'Puesto / tipo de personal',0,1)
    entry(company_var,1,0)
    roles=('Cabos','Checadores','Sobrestantes','Captura y verificación','Otro')
    box=ttk.Combobox(content,textvariable=role_var,values=roles,style='Modern.TCombobox',state='normal')
    box.grid(row=1,column=1,sticky='ew')

    label(content,'Título de la evaluación',2,0,2)
    entry(title_var,3,0,2)
    label(content,'Subtítulo',4,0,2)
    entry(subtitle_var,5,0,2)

    label(content,'Archivo de preguntas (.xlsx)',6,0,2)
    fileline=tk.Frame(content,bg=WHITE)
    fileline.grid(row=7,column=0,columnspan=2,sticky='ew')
    fileline.columnconfigure(0,weight=1)
    ttk.Entry(fileline,textvariable=file_var,style='Modern.TEntry').grid(row=0,column=0,sticky='ew')
    def choose_xlsx():
        chosen=filedialog.askopenfilename(title='Elegir Excel de preguntas',
                    filetypes=[('Excel .xlsx','*.xlsx')],parent=root)
        if chosen:file_var.set(chosen)
    tk.Button(fileline,text='Examinar',command=choose_xlsx,bg='#ecf2f5',fg=NAVY,
              bd=0,padx=13,pady=9,cursor='hand2',font=('Segoe UI',9,'bold')).grid(row=0,column=1,padx=(7,0))
    tk.Label(content,text='Imágenes opcionales: columna Imagen y archivos en la carpeta «imagenes» junto al Excel.',
             bg=WHITE,fg=GRAY,font=('Segoe UI',9)).grid(row=8,column=0,columnspan=2,sticky='w',pady=(5,6))

    label(content,'Logotipo (opcional: PNG o JPG)',9,0,2)
    logoline=tk.Frame(content,bg=WHITE);logoline.grid(row=10,column=0,columnspan=2,sticky='ew')
    logoline.columnconfigure(0,weight=1)
    ttk.Entry(logoline,textvariable=logo_var,style='Modern.TEntry').grid(row=0,column=0,sticky='ew')
    def choose_logo():
        chosen=filedialog.askopenfilename(title='Elegir logotipo',filetypes=[('Imágenes PNG/JPEG','*.png *.jpg *.jpeg')],parent=root)
        if chosen:logo_var.set(chosen)
    tk.Button(logoline,text='Elegir logo',command=choose_logo,bg='#ecf2f5',fg=NAVY,
              bd=0,padx=13,pady=9,cursor='hand2',font=('Segoe UI',9,'bold')).grid(row=0,column=1,padx=(7,0))

    label(content,'Instrucciones al participante',11,0,2)
    instruction=tk.Text(content,height=3,wrap='word',font=('Segoe UI',10),fg=NAVY,
                        bg='#f9fbfc',relief='flat',highlightthickness=1,highlightbackground='#dce5ea',
                        padx=10,pady=7)
    instruction.grid(row=12,column=0,columnspan=2,sticky='ew',pady=(1,8))
    instruction.insert('1.0','Lee cada pregunta y elige una respuesta. Marca tus respuestas únicamente en la hoja separada.')

    status=tk.StringVar(value='Listo para generar · sin cambios en tus archivos originales')
    tk.Label(bottom,textvariable=status,bg=BG,fg=GRAY,font=('Segoe UI',9)).pack(side='left',fill='x',expand=True)

    def run():
        btn.config(state='disabled',text='Generando...')
        root.update_idletasks()
        try:
            result=generate(Path(file_var.get()),BASE/'salidas',title_var.get(),subtitle_var.get(),
                    empresa=company_var.get(),puesto=role_var.get(),
                    instrucciones=instruction.get('1.0','end-1c'),
                    logo=Path(logo_var.get()) if logo_var.get().strip() else None)
        except (ExamError,OSError,ValueError) as exc:
            status.set('Revisa los datos: no se generaron documentos.')
            messagebox.showerror('No se pudo generar el examen',str(exc),parent=root)
        except Exception as exc:
            status.set('Error de generación. Revisa el registro de la aplicación.')
            messagebox.showerror('Error inesperado',str(exc),parent=root)
        else:
            last_output[0]=result
            status.set('Generado: '+result.name)
            openbtn.config(state='normal')
            messagebox.showinfo('Evaluación creada',
                    'Se generaron los cuatro PDF y una copia de las preguntas.\n\n'+str(result)+
                    '\n\nAl imprimir la hoja y el acetato, usa siempre escala 100 %.',parent=root)
        finally:
            btn.config(state='normal',text='Generar documentos')

    btn=tk.Button(bottom,text='Generar documentos',command=run,fg=WHITE,bg=TEAL,
                  activebackground='#096272',activeforeground=WHITE,padx=21,pady=12,
                  bd=0,cursor='hand2',font=('Segoe UI',10,'bold'))
    btn.pack(side='right')
    def open_last():
        if last_output[0] is not None:
            try:open_folder(last_output[0])
            except (OSError,FileNotFoundError) as exc:messagebox.showerror('No se puede abrir la carpeta',str(exc),parent=root)
    openbtn=tk.Button(bottom,text='Abrir resultado',command=open_last,fg=NAVY,bg='#e4edf1',
                  padx=13,pady=12,bd=0,cursor='hand2',font=('Segoe UI',9))
    openbtn.config(state='disabled')
    openbtn.pack(side='right',padx=(0,10))
    root.mainloop()


if __name__=='__main__':
    main()
