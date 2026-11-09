"""Editor visual del diseño: el centro siempre representa el PDF real.

La edición ocurre en los valores compartidos con la ventana principal, por lo que
una misma configuración gobierna la vista, el PDF final y SQLite. Este módulo
NO modifica archivos PDF preexistentes ni coloca cuadros flotantes arbitrarios:
permite diseñar las opciones de composición soportadas por el generador.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, colorchooser
from PIL import ImageTk

from biblioteca import hex_color
from preview_pdf import render_document_preview

NAVY = '#142e40'
DARK = '#213d50'
ACCENT = '#0b7988'
BG = '#e9eff3'
WHITE = '#ffffff'
LABEL = '#607487'


def open_design_studio(parent: tk.Misc, *, datos_fn, variables: dict,
                       editar_preguntas=None, guardar=None, generar=None):
    """Crea el diseñador de dos paneles y devuelve la ventana (útil para pruebas).

    ``variables`` contiene StringVar/BooleanVar ya utilizadas por la ventana
    principal; no se guardan cambios en SQLite hasta usar «Guardar». Cada
    parámetro se refleja en el siguiente render de PDF en memoria.
    """
    window = tk.Toplevel(parent)
    window.title('Editar diseño · Documento PDF real')
    window.geometry('1460x900')
    window.minsize(1030, 650)
    window.configure(bg=BG)

    # Estado de vista: la página es 1-based en la interfaz y 0-based en PDFium.
    selected = tk.StringVar(master=window, value='Cuadernillo')
    zoom = tk.StringVar(master=window, value='Ajustar')
    page = tk.IntVar(master=window, value=1)
    progress = tk.StringVar(master=window, value='Preparando vista PDF…')
    full_pages = [1]
    preview_photo = [None]
    scheduled = [None]
    traces = []
    closed = [False]

    header = tk.Frame(window, bg=NAVY, padx=19, pady=12)
    header.pack(fill='x')
    tk.Label(header, text='EDITOR DE DISEÑO', bg=NAVY, fg='#75d9dc',
             font=('Segoe UI', 10, 'bold')).pack(anchor='w')
    tk.Label(header, text='Diseña a la izquierda y comprueba el PDF real a la derecha',
             bg=NAVY, fg=WHITE, font=('Segoe UI', 15, 'bold')).pack(anchor='w', pady=(2, 1))

    container = tk.PanedWindow(window, orient='horizontal', bd=0, sashwidth=6,
                               bg=BG, opaqueresize=False)
    container.pack(fill='both', expand=True, padx=10, pady=(10, 7))
    settings = tk.Frame(container, bg=WHITE, width=352)
    result = tk.Frame(container, bg=BG)
    container.add(settings, minsize=292, width=354)
    container.add(result, minsize=550, stretch='always')

    settings_canvas = tk.Canvas(settings, bg=WHITE, highlightthickness=0, bd=0)
    settings_bar = ttk.Scrollbar(settings, orient='vertical', command=settings_canvas.yview)
    settings_canvas.configure(yscrollcommand=settings_bar.set)
    settings_bar.pack(side='right', fill='y')
    settings_canvas.pack(fill='both', expand=True)
    settings_inner = tk.Frame(settings_canvas, bg=WHITE, padx=16, pady=12)
    settings_window = settings_canvas.create_window((0, 0), window=settings_inner, anchor='nw')
    settings_inner.bind('<Configure>', lambda e: settings_canvas.configure(scrollregion=settings_canvas.bbox('all')))
    settings_canvas.bind('<Configure>', lambda e: settings_canvas.itemconfigure(settings_window, width=e.width))
    settings_inner.columnconfigure(0, weight=1)
    settings_inner.columnconfigure(1, weight=1)

    def section(title: str, description: str):
        tk.Label(settings_inner, text=title, bg=WHITE, fg=NAVY,
                 font=('Segoe UI', 11, 'bold')).grid(sticky='w', columnspan=2, pady=(13, 1))
        tk.Label(settings_inner, text=description, bg=WHITE, fg=LABEL,
                 font=('Segoe UI', 9), wraplength=290, justify='left').grid(
                    sticky='w', columnspan=2, pady=(0, 8))

    def field(label: str, var: tk.Variable):
        tk.Label(settings_inner, text=label, bg=WHITE, fg=NAVY,
                 font=('Segoe UI', 9)).grid(sticky='w', columnspan=2, pady=(4, 2))
        ttk.Entry(settings_inner, textvariable=var).grid(sticky='ew', columnspan=2, pady=(0, 6))

    section('01 · Texto de portada', 'Cambia el título y observa el encabezado del cuadernillo.')
    field('Título de la evaluación', variables['titulo'])
    field('Subtítulo', variables['subtitulo'])
    field('Empresa / institución', variables['empresa'])
    field('Área o público', variables['grupo'])

    section('02 · Página y tipografía', 'Ajusta la composición; no modifica las preguntas originales.')
    tk.Label(settings_inner, text='Formato de papel', bg=WHITE, fg=NAVY).grid(sticky='w', columnspan=2)
    ttk.Combobox(settings_inner, textvariable=variables['papel'],
                 values=('Carta', 'A4', 'Oficio'), state='readonly').grid(
                     sticky='ew', columnspan=2, pady=(3, 8))
    tk.Label(settings_inner, text='Tamaño de letra de preguntas (pt)', bg=WHITE, fg=NAVY).grid(
        sticky='w', columnspan=2)
    ttk.Combobox(settings_inner, textvariable=variables['letra'],
                 values=[f'{n/2:.1f}' for n in range(16, 25)], state='readonly').grid(
                     sticky='ew', columnspan=2, pady=(3, 8))
    tk.Checkbutton(settings_inner, text='Cuadernillo reutilizable · NO RAYAR NI MANCHAR',
                   variable=variables['reutilizable'], bg=WHITE, fg=NAVY,
                   activebackground=WHITE, wraplength=280,
                   justify='left').grid(sticky='w', columnspan=2, pady=(4, 7))

    section('03 · Paletas de color', 'Elige colores RGB. La hoja de respuestas conserva fondo blanco.')
    swatches = {}
    def color_input(label: str, key: str):
        row = tk.Frame(settings_inner, bg=WHITE)
        row.grid(sticky='ew', columnspan=2, pady=(2, 8))
        tk.Label(row, text=label, bg=WHITE, fg=NAVY).pack(anchor='w')
        inner = tk.Frame(row, bg=WHITE)
        inner.pack(fill='x')
        swatch=tk.Label(inner, text='     ', relief='solid', bd=1, bg='#d3e4eb')
        swatch.pack(side='left', padx=(0, 7))
        swatches[key]=swatch
        ttk.Entry(inner, textvariable=variables[key], width=13).pack(side='left', fill='x', expand=True)
        def pick():
            try:initial=hex_color(variables[key].get())
            except ValueError:initial='#213A4C'
            new=colorchooser.askcolor(color=initial, title=f'Color RGB de {label.lower()}', parent=window)
            if new and new[1]:variables[key].set(new[1].upper())
        tk.Button(inner, text='Elegir', command=pick, bg='#e4edf1', fg=NAVY,
                  bd=0, padx=8, pady=6).pack(side='left', padx=(7,0))
    color_input('Título', 'color_titulo')
    color_input('Subtítulo', 'color_subtitulo')
    color_input('Hoja de respuestas', 'color_respuestas')

    section('04 · Preguntas y biblioteca', 'Se edita la fuente del examen; el PDF se regenera al cambiarla.')
    tk.Button(settings_inner, text='Editar preguntas y opciones', command=editar_preguntas,
              bg='#e5eef2', fg=NAVY, bd=0, pady=10).grid(sticky='ew', columnspan=2, pady=(0,7))
    tk.Button(settings_inner, text='Guardar cuestionario en biblioteca', command=guardar,
              bg=ACCENT, fg=WHITE, bd=0, pady=11).grid(sticky='ew', columnspan=2, pady=(0,7))
    tk.Button(settings_inner, text='Generar documentos PDF', command=generar,
              bg=NAVY, fg=WHITE, bd=0, pady=11).grid(sticky='ew', columnspan=2, pady=(0,8))
    tk.Label(settings_inner, text='La vista es exacta respecto al generador. No permite mover '
             'objetos con el ratón ni editar archivos PDF externos.', bg=WHITE, fg=LABEL,
             wraplength=295, justify='left', font=('Segoe UI', 8)).grid(
                 sticky='w', columnspan=2, pady=(5,16))

    actions = tk.Frame(result, bg=WHITE, padx=10, pady=8)
    actions.pack(fill='x', pady=(0, 6))
    tk.Label(actions, text='Documento', bg=WHITE, fg=NAVY).pack(side='left', padx=(0, 4))
    ttk.Combobox(actions, textvariable=selected, state='readonly', width=14,
                 values=('Cuadernillo', 'Respuestas', 'Acetato')).pack(side='left', padx=(0,8))
    tk.Button(actions, text='◀', width=4, command=lambda:turn_page(-1)).pack(side='left', padx=3)
    tk.Button(actions, text='▶', width=4, command=lambda:turn_page(1)).pack(side='left', padx=3)
    tk.Label(actions, textvariable=progress, bg=WHITE, fg=LABEL,
             font=('Segoe UI', 9)).pack(side='left', padx=8)
    ttk.Combobox(actions, textvariable=zoom, state='readonly', width=9,
                 values=('Ajustar', '70%', '85%', '100%', '125%', '150%', '175%', '200%')).pack(side='right')
    tk.Label(actions, text='Zoom', bg=WHITE, fg=NAVY).pack(side='right', padx=(0, 5))

    frame=tk.Frame(result, bg='#dbe5ea')
    frame.pack(fill='both', expand=True)
    canvas=tk.Canvas(frame, bg='#dce7ed', bd=0, highlightthickness=0)
    vbar=ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
    hbar=ttk.Scrollbar(frame, orient='horizontal', command=canvas.xview)
    canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
    vbar.pack(side='right', fill='y')
    hbar.pack(side='bottom', fill='x')
    canvas.pack(side='left', fill='both', expand=True)

    def turn_page(delta):
        page.set(max(1, min(full_pages[0], page.get() + delta)))
        queue_render()

    def refresh():
        scheduled[0]=None
        if closed[0] or not window.winfo_exists():return
        try:
            data=datos_fn()
            if zoom.get() == 'Ajustar':
                # La página cabe a lo ancho si el espacio disponible lo permite.
                width=max(360, min(1500, canvas.winfo_width()-52))
            else:
                from src.evaluaciones.core import paper_dimensions
                paper_width=paper_dimensions(data.tamano_papel)[0]
                width=max(340, min(2200, int(paper_width*float(zoom.get().rstrip('%'))/72*96)))
            image,pages=render_document_preview(data, selected.get(), max(0, page.get()-1), width)
            if page.get() > pages:
                page.set(pages)
                image,pages=render_document_preview(data, selected.get(), pages-1, width)
            full_pages[0]=pages
            pic=ImageTk.PhotoImage(image, master=window)
            preview_photo[0]=pic
            canvas.delete('all')
            x=max(14, (canvas.winfo_width()-image.width)//2)
            canvas.create_image(x, 14, anchor='nw', image=pic)
            canvas.configure(scrollregion=(0,0,max(canvas.winfo_width(),x+image.width+15),image.height+30))
            progress.set(f'Página {page.get()} / {pages} · {data.tamano_papel}')
            for key, swatch in swatches.items():
                try:swatch.configure(bg=hex_color(variables[key].get()))
                except ValueError:swatch.configure(bg='#d3e4eb')
        except Exception as exc:
            progress.set('Vista no disponible: '+str(exc)[:95])

    def queue_render(*_):
        if closed[0] or not window.winfo_exists():return
        if scheduled[0] is not None:
            window.after_cancel(scheduled[0])
        scheduled[0]=window.after(330, refresh)

    def new_document(*_):
        page.set(1)
        queue_render()

    selected.trace_add('write', new_document)
    zoom.trace_add('write', queue_render)
    canvas.bind('<Configure>', queue_render)
    for variable in variables.values():
        ident=variable.trace_add('write', queue_render)
        traces.append((variable, ident))

    footer=tk.Frame(window, bg=BG, pady=8, padx=12)
    footer.pack(fill='x')
    tk.Label(footer, text='Los ajustes son compartidos con la ventana principal. Guarda el cuestionario '
             'para conservarlos en SQLite.', bg=BG, fg=LABEL,
             font=('Segoe UI', 9)).pack(side='left')
    tk.Button(footer, text='Volver al generador', command=lambda:close(),
              bg=NAVY, fg=WHITE, bd=0, padx=13, pady=8).pack(side='right')

    def close():
        closed[0]=True
        if scheduled[0] is not None:
            window.after_cancel(scheduled[0]);scheduled[0]=None
        for variable, ident in traces:
            try:variable.trace_remove('write', ident)
            except tk.TclError:pass
        window.destroy()
    window.protocol('WM_DELETE_WINDOW', close)
    window.after(140, queue_render)
    return window
