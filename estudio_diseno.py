"""Editor visual del diseño: el centro siempre representa el PDF real.

La edición ocurre en los valores compartidos con la ventana principal, por lo que
una misma configuración gobierna la vista, el PDF final y SQLite. Este módulo
NO modifica archivos PDF preexistentes ni coloca cuadros flotantes arbitrarios:
permite diseñar las opciones de composición soportadas por el generador.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, colorchooser, filedialog
from PIL import ImageTk

from biblioteca import hex_color
from preview_worker import PreviewWorker

NAVY = '#142e40'
DARK = '#213d50'
ACCENT = '#0b7988'
BG = '#e9eff3'
WHITE = '#ffffff'
LABEL = '#607487'


def open_design_studio(parent: tk.Misc, *, datos_fn, variables: dict,
                       editar_preguntas=None, guardar=None, generar=None,
                       importar=None, biblioteca=None, plantilla=None, estado=None,
                       calificar=None, preparar_folios=None, on_close=None):
    """Crea el diseñador de dos paneles y devuelve la ventana (útil para pruebas).

    ``variables`` contiene StringVar/BooleanVar ya utilizadas por la ventana
    principal; no se guardan cambios en SQLite hasta usar «Guardar». Cada
    parámetro se refleja en el siguiente render de PDF en memoria.
    """
    window = tk.Toplevel(parent)
    window.title('Evaluaciones · Diseñar, imprimir y calificar')
    window.geometry(f'{min(1400, parent.winfo_screenwidth()-60)}x{min(860, parent.winfo_screenheight()-90)}')
    window.minsize(820, 560)
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
    worker = PreviewWorker()
    revision = [0]
    pending = [None]
    polling = [None]

    # Un solo menú para todo el ciclo; no se abre una segunda pantalla principal.
    menu = tk.Menu(window, tearoff=False)
    work_menu = tk.Menu(menu, tearoff=False)
    work_menu.add_command(label='Diseñar examen (vista actual)', command=window.lift)
    if calificar is not None:
        work_menu.add_command(label='Calificar y entregar resultados', command=calificar)
    if biblioteca is not None:
        work_menu.add_command(label='Biblioteca de cuestionarios', command=biblioteca)
    if plantilla is not None:
        work_menu.add_command(label='Descargar plantilla de preguntas', command=plantilla)
    menu.add_cascade(label='Evaluaciones', menu=work_menu)
    window.configure(menu=menu)

    header = tk.Frame(window, bg=NAVY, padx=19, pady=12)
    header.pack(fill='x')
    tk.Label(header, text='DISEÑAR EVALUACIONES', bg=NAVY, fg='#75d9dc',
             font=('Segoe UI', 10, 'bold')).pack(anchor='w')
    tk.Label(header, text='Prepara cualquier modalidad y comprueba el PDF real a la derecha',
             bg=NAVY, fg=WHITE, font=('Segoe UI', 15, 'bold')).pack(anchor='w', pady=(2, 1))
    nav = tk.Frame(header, bg=NAVY)
    nav.pack(anchor='w', pady=(8, 0))
    tk.Button(nav, text='Diseñar e imprimir', state='disabled', bg=ACCENT, fg=WHITE,
              disabledforeground=WHITE, bd=0, padx=13, pady=7).pack(side='left', padx=(0, 7))
    if calificar is not None:
        tk.Button(nav, text='Calificar y entregar', command=calificar,
                  bg='#e0edf1', fg=NAVY, bd=0, padx=13, pady=7).pack(side='left')


    container = tk.PanedWindow(window, orient='horizontal', bd=0, sashwidth=6,
                               bg=BG, opaqueresize=False)
    container.pack(fill='both', expand=True, padx=10, pady=(10, 7))
    settings = tk.Frame(container, bg=WHITE, width=352)
    result = tk.Frame(container, bg=BG)
    container.add(settings, minsize=292, width=354)
    container.add(result, minsize=420, stretch='always')

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

    for title, action in [('Importar XLSX', importar), ('Abrir biblioteca y papelera', biblioteca), ('Descargar plantilla', plantilla)]:
        if action:
            ttk.Button(settings_inner, text=title, command=action).grid(sticky='ew', columnspan=2, pady=3)

    # El acceso a calificación está en el menú superior, no duplicado en el formulario.
    section('01 · Texto de portada', 'Cambia el título y observa el encabezado del cuadernillo.')
    field('Título de la evaluación', variables['titulo'])
    field('Subtítulo', variables['subtitulo'])
    field('Empresa / institución', variables['empresa'])
    field('Área o público', variables['grupo'])
    if 'instrucciones' in variables:
        tk.Label(settings_inner, text='Instrucciones del participante', bg=WHITE, fg=NAVY).grid(sticky='w', columnspan=2)
        instructions = tk.Text(settings_inner, height=4, wrap='word', font=('Segoe UI', 9))
        instructions.grid(sticky='ew', columnspan=2, pady=(3, 8))
        instructions.insert('1.0', variables['instrucciones'].get())
        def sync_instructions(*_):
            value = variables['instrucciones'].get()
            if instructions.get('1.0', 'end-1c') != value:
                instructions.delete('1.0', 'end')
                instructions.insert('1.0', value)
        def change_instructions(event=None):
            if instructions.edit_modified():
                value = instructions.get('1.0', 'end-1c')
                if variables['instrucciones'].get() != value:
                    variables['instrucciones'].set(value)
                instructions.edit_modified(False)
        instructions.bind('<<Modified>>', change_instructions)
        traces.append((variables['instrucciones'], variables['instrucciones'].trace_add('write', sync_instructions)))
    if 'logotipo' in variables:
        field('Ruta del logotipo (PNG/JPG)', variables['logotipo'])
        def choose_logo():
            path = filedialog.askopenfilename(parent=window, title='Elegir logotipo',
                                             filetypes=[('Imagen PNG/JPEG', '*.png *.jpg *.jpeg')])
            if path:
                variables['logotipo'].set(path)
        ttk.Button(settings_inner, text='Elegir logotipo…', command=choose_logo).grid(sticky='ew', columnspan=2)

    section('02 · Tipo de examen', 'Elige qué vas a imprimir; el diseño y la clave del examen son los mismos.')
    exam_type = tk.StringVar(master=window,
        value='ecologico' if variables['reutilizable'].get() else 'normal')
    type_help = tk.StringVar(master=window)
    type_options = (
        ('normal', 'Normal · cuadernillo y hoja de respuestas'),
        ('ecologico', 'Ecológico · cuadernillo reutilizable'),
        ('folio', 'Con folio y QR · hojas individuales para escáner'),
    )
    for code, label in type_options:
        ttk.Radiobutton(settings_inner, text=label, variable=exam_type,
                        value=code).grid(sticky='w', columnspan=2, pady=(1, 5))
    tk.Label(settings_inner, textvariable=type_help, bg=WHITE, fg=LABEL,
             wraplength=300, justify='left').grid(
                 sticky='w', columnspan=2, pady=(2, 6))
    folio_button = None
    if preparar_folios is not None:
        folio_button = tk.Button(settings_inner,
            text='Preparar hojas con folio y QR', command=preparar_folios,
            bg=ACCENT, fg=WHITE, bd=0, pady=10,
            font=('Segoe UI', 10, 'bold'))
        folio_button.grid(sticky='ew', columnspan=2, pady=(4, 10))
    def update_type(*_):
        mode = exam_type.get()
        # Con QR se conserva el cuadernillo reutilizable; la identificación
        # del participante vive exclusivamente en su hoja personalizada.
        variables['reutilizable'].set(mode != 'normal')
        descriptions = {
            'normal': 'Genera cuadernillo, hoja de respuestas, clave y acetato normales.',
            'ecologico': 'Genera cuadernillo sin datos personales y con aviso NO RAYAR NI MANCHAR.',
            'folio': 'Primero genera el cuadernillo; después prepara las hojas individuales '
                     'con folio y QR desde el botón de esta sección.',
        }
        type_help.set(descriptions.get(mode, ''))
        if folio_button is not None:
            if mode == 'folio':
                folio_button.grid()
            else:
                folio_button.grid_remove()

    def sync_type_from_booklet(*_):
        # Al abrir una evaluación de la biblioteca, se respeta su modalidad.
        # La modalidad con QR permanece seleccionada durante el cambio de vistas.
        if exam_type.get() == 'folio':
            return
        expected = 'ecologico' if variables['reutilizable'].get() else 'normal'
        if exam_type.get() != expected:
            exam_type.set(expected)

    traces.append((exam_type, exam_type.trace_add('write', update_type)))
    traces.append((variables['reutilizable'],
                   variables['reutilizable'].trace_add('write', sync_type_from_booklet)))
    update_type()

    section('03 · Página y tipografía', 'Ajusta la composición; no modifica las preguntas originales.')
    tk.Label(settings_inner, text='Formato de papel', bg=WHITE, fg=NAVY).grid(sticky='w', columnspan=2)
    ttk.Combobox(settings_inner, textvariable=variables['papel'],
                 values=('Carta', 'A4', 'Oficio'), state='readonly').grid(
                     sticky='ew', columnspan=2, pady=(3, 8))
    tk.Label(settings_inner, text='Tamaño de letra de preguntas (pt)', bg=WHITE, fg=NAVY).grid(
        sticky='w', columnspan=2)
    ttk.Combobox(settings_inner, textvariable=variables['letra'],
                 values=[f'{n/2:.1f}' for n in range(16, 25)], state='readonly').grid(
                     sticky='ew', columnspan=2, pady=(3, 8))
    section('04 · Paletas de color', 'Elige colores RGB. La hoja de respuestas conserva fondo blanco.')
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
    color_input('Acetato', 'color_acetato')

    section('05 · Preguntas y biblioteca', 'Se edita la fuente del examen; el PDF se regenera al cambiarla.')
    tk.Button(settings_inner, text='Editar preguntas y opciones', command=editar_preguntas,
              bg='#e5eef2', fg=NAVY, bd=0, pady=10).grid(sticky='ew', columnspan=2, pady=(0,7))
    tk.Button(settings_inner, text='Guardar cuestionario en biblioteca', command=guardar,
              bg=ACCENT, fg=WHITE, bd=0, pady=11).grid(sticky='ew', columnspan=2, pady=(0,7))
    tk.Button(settings_inner, text='Generar cuadernillo, respuestas y acetato PDF', command=generar,
              bg=NAVY, fg=WHITE, bd=0, pady=11).grid(sticky='ew', columnspan=2, pady=(0,8))
    tk.Label(settings_inner, text='La vista es exacta respecto al generador. No permite mover '
             'objetos con el ratón ni editar archivos PDF externos.', bg=WHITE, fg=LABEL,
             wraplength=295, justify='left', font=('Segoe UI', 8)).grid(
                 sticky='w', columnspan=2, pady=(5,16))

    actions = tk.Frame(result, bg=WHITE, padx=10, pady=8)
    actions.pack(fill='x', pady=(0, 6))
    actions.columnconfigure(1, weight=1)
    ttk.Combobox(actions, textvariable=selected, state='readonly', width=13,
                 values=('Cuadernillo', 'Respuestas', 'Acetato')).grid(row=0, column=0, padx=(0,8))
    navigation = tk.Frame(actions, bg=WHITE)
    navigation.grid(row=0, column=1, sticky='w')
    tk.Button(navigation, text='◀', width=3, command=lambda:turn_page(-1)).pack(side='left', padx=2)
    tk.Button(navigation, text='▶', width=3, command=lambda:turn_page(1)).pack(side='left', padx=2)
    ttk.Combobox(actions, textvariable=zoom, state='readonly', width=9,
                 values=('Ajustar', '70%', '85%', '100%', '125%', '150%', '175%', '200%')).grid(row=0, column=2)
    tk.Label(actions, textvariable=progress, bg=WHITE, fg=LABEL,
             font=('Segoe UI', 9), anchor='w', wraplength=380).grid(row=1, column=0, columnspan=3, sticky='ew', pady=(5,0))

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

    def receive():
        """Publica solo la última revisión; todas las llamadas Tk ocurren aquí."""
        polling[0] = None
        if closed[0]:
            return
        try:
            result = worker.poll()
            if result is not None:
                token, image, pages, error = result
                if token == revision[0]:
                    if error:
                        progress.set('Vista no disponible: ' + error[:95])
                    else:
                        full_pages[0] = pages
                        page.set(min(page.get(), pages))
                        pic = ImageTk.PhotoImage(image, master=window)
                        preview_photo[0] = pic
                        canvas.delete('all')
                        x = max(14, (canvas.winfo_width()-image.width)//2)
                        canvas.create_image(x, 14, anchor='nw', image=pic)
                        canvas.configure(scrollregion=(0, 0, max(canvas.winfo_width(), x+image.width+15), image.height+30))
                        progress.set(f'Página {page.get()} / {pages}')
            if pending[0] is not None and not worker.busy:
                request = pending[0]
                pending[0] = None
                worker.submit(*request)
        except Exception as exc:
            progress.set('Vista no disponible: ' + str(exc)[:95])
        polling[0] = window.after(50, receive)

    def refresh():
        scheduled[0] = None
        if closed[0]:
            return
        try:
            data = datos_fn()
            from src.evaluaciones.core import paper_dimensions
            paper_width, paper_height = paper_dimensions(data.tamano_papel)
            for key, swatch in swatches.items():
                swatch.configure(bg=hex_color(variables[key].get()))
            if zoom.get() == 'Ajustar':
                width = max(300, min(1500, canvas.winfo_width()-40,
                                    int((canvas.winfo_height()-32)*paper_width/paper_height)))
            else:
                width = max(300, min(2200, int(paper_width*float(zoom.get().rstrip('%'))/72*96)))
            pending[0] = (revision[0], data, selected.get(), max(0, page.get()-1), width)
            progress.set('Actualizando PDF…')
        except Exception as exc:
            progress.set('Revisa los ajustes: ' + str(exc)[:95])

    def queue_render(*_):
        if closed[0]:
            return
        revision[0] += 1
        pending[0] = None
        if scheduled[0] is not None:
            window.after_cancel(scheduled[0])
        scheduled[0] = window.after(330, refresh)

    def new_document(*_):
        page.set(1)
        queue_render()

    traces.append((selected, selected.trace_add('write', new_document)))
    traces.append((zoom, zoom.trace_add('write', queue_render)))
    canvas.bind('<Configure>', queue_render)
    for variable in variables.values():
        ident=variable.trace_add('write', queue_render)
        traces.append((variable, ident))

    footer=tk.Frame(window, bg=BG, pady=8, padx=12)
    footer.pack(fill='x')
    if estado is not None:
        tk.Label(footer, textvariable=estado, bg=BG, fg=NAVY).pack(side='left', padx=8)
    tk.Label(footer, text='Esc: cerrar aplicación · Guarda para conservar los cambios.', bg=BG, fg=LABEL,
             font=('Segoe UI', 9)).pack(side='left')
    tk.Button(footer, text='Cerrar aplicación' if on_close is not None else 'Volver al generador',
              command=lambda:close(),
              bg=NAVY, fg=WHITE, bd=0, padx=13, pady=8).pack(side='right')

    def cleanup(event=None):
        """Libera procesos, callbacks y traces incluso al destruir la ventana padre."""
        if event is not None and event.widget is not window:
            return
        if closed[0]:
            return
        closed[0] = True
        for timer in (scheduled, polling):
            if timer[0] is not None:
                window.after_cancel(timer[0])
                timer[0] = None
        for variable, ident in traces:
            try:
                variable.trace_remove('write', ident)
            except tk.TclError:
                pass
        preview_photo[0] = None
        pending[0] = None
        worker.close()

    def close():
        # El diseñador es la ventana principal cuando on_close está definido.
        # Delegamos la confirmación de cambios y el cierre de la raíz oculta.
        if on_close is not None:
            on_close()
            return
        cleanup()
        window.destroy()

    window.protocol('WM_DELETE_WINDOW', close)
    window.bind('<Escape>', lambda event: close())
    window.bind('<Destroy>', cleanup, add='+')
    def scroll_panel(event):
        target = settings_canvas if event.x_root < result.winfo_rootx() else canvas
        steps = (-1 if event.num == 4 else 1) if event.num in (4, 5) else -int(event.delta/120)
        target.yview_scroll(steps, 'units')
    window.bind('<MouseWheel>', scroll_panel)
    window.bind('<Button-4>', scroll_panel)
    window.bind('<Button-5>', scroll_panel)
    window.lift()
    queue_render()
    polling[0] = window.after(50, receive)
    return window
