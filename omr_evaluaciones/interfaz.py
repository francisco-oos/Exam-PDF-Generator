"""Interfaz de aplicación OMR: toda lectura y escritura pasa por motor.py.

Modos: tradicional/ecológico mantienen el flujo manual; personalizado habilita
QR, escaneo, revisión y entrega. No se alteran las pantallas ya existentes.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
from PIL import Image,ImageTk,ImageDraw

from .motor import (OMRStore,read_roster,create_forms_pdf,scan_document,
                    export_report,PAPERS,bubble_positions,RENDER_DPI,
                    render_review_with_acetato)
from .demo import create_synthetic_scan

NAVY='#132e40';INK='#243e4c';TEAL='#0b7988';LIGHT='#eff4f6';WHITE='#ffffff'

class OMRApp:
    def __init__(self,parent=None,db_root=None, *,
                 questions=None, title=None, paper=None, source=None,
                 on_return=None, start_page='Inicio', review_only=False,
                 library_db_path=None, on_open_exam=None):
        self.parent = parent
        self.on_return = on_return
        self.on_open_exam = on_open_exam
        self.library_db_path = (Path(library_db_path) if library_db_path
                                else Path(__file__).resolve().parents[1]/'datos'/'biblioteca.sqlite3')
        self.review_only = review_only
        self.window=tk.Toplevel(parent) if parent is not None else tk.Tk()
        self.window.title('Evaluaciones · Folios, escaneo y calificación OMR')
        w=min(1390,self.window.winfo_screenwidth()-50)
        h=min(870,self.window.winfo_screenheight()-75)
        self.window.geometry(f'{w}x{h}')
        self.window.minsize(930,590)
        self.window.configure(bg=LIGHT)
        # Espacio dedicado a la calificación: se maximiza para revisar
        # escaneos y evidencias sin tener el editor PDF detrás.
        try:
            self.window.state('zoomed')
        except tk.TclError:
            try:
                self.window.attributes('-zoomed', True)
            except tk.TclError:
                self.window.geometry(
                    f'{self.window.winfo_screenwidth()}x{self.window.winfo_screenheight()}+0+0')
        self.store=OMRStore(db_root or Path(__file__).resolve().parents[1]/'datos'/'omr')
        self.session_id=None
        self.mode=tk.StringVar(value='personalizado')
        self.paper=tk.StringVar(value=paper if paper in PAPERS else 'Carta')
        self.title=tk.StringVar(value=title or 'Evaluación de conocimientos')
        self.file_questions=tk.StringVar(value=source or ('Cuestionario abierto en el generador' if questions else ''))
        self.file_roster=tk.StringVar(value='')
        # Reutilizamos la clave y los temas del cuestionario que ya se está
        # diseñando. No obligamos al evaluador a cargar dos veces el XLSX.
        self.questions=[{'tema':q.section, 'pregunta':q.prompt,
                         'correcta':'ABCD'[q.correct]} for q in (questions or [])]
        self.people=[]
        self.active_page=None
        self.photo=None
        self.scan_updates=Queue()
        self.scanning=False
        self.active_view='Historial' if self.review_only else 'Inicio'
        self.buttons={}
        self.last_print=None
        self.feedback=tk.StringVar(value='Listo para configurar una evaluación.')
        self._layout()
        self.mode.trace_add('write',lambda *_:self._refresh_navigation())
        self._refresh_navigation()
        self.window.protocol('WM_DELETE_WINDOW', self.return_to_generator)
        self.navigate('Historial' if self.review_only else
                      (start_page if start_page in ('Inicio','Historial') else 'Inicio'))

    def _layout(self):
        sidebar=tk.Frame(self.window,bg=NAVY,width=232)
        sidebar.pack(side='left',fill='y');sidebar.pack_propagate(False)
        tk.Label(sidebar,text='EVALUACIONES',bg=NAVY,fg='#68dce4',font=('Segoe UI',11,'bold'),pady=25).pack(anchor='w',padx=21)
        tk.Label(sidebar,text='Escanea · Revisa · Entrega' if self.review_only else
                 'Diseña · Aplica · Califica',bg=NAVY,fg=WHITE,
                 font=('Segoe UI',11,'bold')).pack(anchor='w',padx=21,pady=(0,17))
        for item in ['Inicio','Participantes','Hojas con QR','Escanear PDF','Revisión','Resultados','Excel de entrega','Historial']:
            b=tk.Button(sidebar,text=item,anchor='w',bd=0,highlightthickness=0,bg=NAVY,fg='#dae6ea',
                activebackground='#1e5360',activeforeground=WHITE,font=('Segoe UI',10),padx=21,pady=12,
                command=lambda v=item:self.navigate(v))
            self.buttons[item]=b
            b.pack(fill='x',padx=9,pady=1)
        tk.Label(sidebar,text='Datos locales · Sin Internet\nQR firmado · Revisión humana',
            bg=NAVY,fg='#a4b9c1',justify='left',font=('Segoe UI',9)).pack(side='bottom',anchor='w',padx=21,pady=(12,18))
        tk.Button(sidebar,text='← Diseño e impresión',command=self.return_to_generator,
            bg='#205267',fg=WHITE,activebackground='#297083',
            activeforeground=WHITE,anchor='w',bd=0,padx=14,pady=11,
            font=('Segoe UI',10,'bold')).pack(side='bottom',fill='x',padx=9,pady=4)
        right=tk.Frame(self.window,bg=LIGHT)
        right.pack(side='left',fill='both',expand=True)
        bar=tk.Frame(right,bg=WHITE,height=63)
        bar.pack(fill='x');bar.pack_propagate(False)
        tk.Label(bar,text='CALIFICACIÓN Y RESULTADOS' if self.review_only else
                 'GESTOR DE APLICACIONES',bg=WHITE,fg=TEAL,
                 font=('Segoe UI',11,'bold')).pack(side='left',padx=20)
        self.state_label=tk.Label(bar,textvariable=self.feedback,bg=WHITE,fg=INK,font=('Segoe UI',9),wraplength=480)
        self.state_label.pack(side='right',padx=18)
        self.stage=tk.Frame(right,bg=LIGHT,padx=22,pady=18)
        self.stage.pack(fill='both',expand=True)

    def return_to_generator(self):
        """Vuelve al diseñador existente, también cuando se cierra con la X."""
        self.window.destroy()
        if self.on_return is not None:
            # La aplicación principal decide qué ventana restaurar. No mostrar
            # la raíz oculta: causaría las dos ventanas que se quieren eliminar.
            self.on_return()
        elif self.parent is not None and self.parent.winfo_exists():
            self.parent.deiconify()
            self.parent.lift()
            self.parent.focus_force()

    def _refresh_navigation(self):
        all_items=['Inicio','Participantes','Hojas con QR','Escanear PDF','Revisión','Resultados','Excel de entrega','Historial']
        active=(['Historial','Escanear PDF','Revisión','Resultados','Excel de entrega']
                if self.review_only else
                (['Inicio','Historial'] if self.mode.get() in ('tradicional','ecologico')
                 else all_items))
        for item in all_items:
            self.buttons[item].pack_forget()
        for item in active:
            self.buttons[item].pack(fill='x',padx=9,pady=1)
        if self.active_view not in active:self.navigate(active[0])

    def _clear(self):
        for w in self.stage.winfo_children():w.destroy()

    def _heading(self,text,desc=''):
        tk.Label(self.stage,text=text,bg=LIGHT,fg=NAVY,font=('Segoe UI',20,'bold')).pack(anchor='w')
        if desc:tk.Label(self.stage,text=desc,bg=LIGHT,fg='#607887',font=('Segoe UI',10),wraplength=800,justify='left').pack(anchor='w',pady=(3,15))

    def _card(self,parent=None):
        frame=tk.Frame(parent or self.stage,bg=WHITE,padx=18,pady=15,highlightbackground='#d9e5ea',highlightthickness=1)
        frame.pack(fill='x',pady=7)
        return frame

    def _field(self,parent,label,variable,read_only=False):
        tk.Label(parent,text=label,bg=WHITE,fg=INK,font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(8,4))
        ttk.Entry(parent,textvariable=variable,state='readonly' if read_only else 'normal').pack(fill='x')

    def _btn(self,parent,text,command,primary=False):
        btn=tk.Button(parent,text=text,command=command,bg=TEAL if primary else '#e4edf1',
             fg=WHITE if primary else NAVY,bd=0,font=('Segoe UI',10,'bold'),padx=15,pady=10)
        btn.pack(side='left',padx=(0,8),pady=8)
        return btn

    def navigate(self,page):
        if self.review_only and page in ('Inicio','Participantes','Hojas con QR'):
            return
        self.active_view=page;self._clear()
        for item,b in self.buttons.items():b.configure(bg='#1c5163' if item==page else NAVY)
        pages={'Inicio':self._home,'Participantes':self._roster,'Hojas con QR':self._paper,
            'Escanear PDF':self._scanner,'Revisión':self._review,'Resultados':self._results,
            'Excel de entrega':self._export,'Historial':self._history}
        pages[page]()

    def _home(self):
        self._heading('Preparar evaluación','Selecciona cómo se aplicará el examen. El menú se adapta al modo elegido.')
        c=self._card();tk.Label(c,text='Modalidad',bg=WHITE,fg=NAVY,font=('Segoe UI',12,'bold')).pack(anchor='w')
        for code,label,desc in [
            ('tradicional','Tradicional · Cuadernillo y talón','Se imprime y corrige manualmente con la clave.'),
            ('ecologico','Ecológico · Cuadernillo reutilizable','Un cuadernillo común; respuestas en hojas separadas.'),
            ('personalizado','Personalizado · Folio, QR y lectura de escáner','Carga personal, imprime hojas individuales y reconoce PDF multipágina.')]:
            r=tk.Frame(c,bg=WHITE)
            r.pack(fill='x',pady=5)
            ttk.Radiobutton(r,text=label,variable=self.mode,value=code,command=lambda:self.navigate('Inicio')).pack(anchor='w')
            tk.Label(r,text=desc,bg=WHITE,fg='#6b8290',font=('Segoe UI',9)).pack(anchor='w',padx=22)
        b=self._card()
        self._field(b,'Título',self.title)
        tk.Label(b,text='Papel',bg=WHITE,fg=INK,font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(12,3))
        ttk.Combobox(b,textvariable=self.paper,values=list(PAPERS),state='readonly').pack(fill='x')
        self._field(b,'Cuestionario XLSX',self.file_questions,True)
        controls=tk.Frame(b,bg=WHITE);controls.pack(fill='x')
        self._btn(controls,'Importar preguntas',self.choose_questions)
        self._btn(controls,'Cargar ejemplo ficticio',self.load_example)
        if self.questions:
            tk.Label(b,text=f'{len(self.questions)} preguntas · {len(set(q["tema"] for q in self.questions))} temas',bg=WHITE,fg=TEAL).pack(anchor='w')
        c2=self._card()
        self._btn(c2,'Crear sesión de aplicación',self.create_session,True)
        if self.session_id:tk.Label(c2,text='Sesión actual: '+self.session_id,bg=WHITE,fg='#667e8d').pack(side='left',padx=8)
        if self.mode.get()!='personalizado':
            self._note('La impresión tradicional y ecológica se prepara en el mismo generador, '
                       'con editor visual, cuadernillo, respuestas y acetato. '
                       'Pulsa el botón siguiente para regresar sin cargar preguntas otra vez.')
            c3=self._card()
            self._btn(c3,'Abrir diseñador e imprimir PDF',self.return_to_generator,True)

    def _note(self,text):
        tk.Label(self.stage,text=text,bg='#e3f1f3',fg='#244e5b',padx=13,pady=12,wraplength=850,justify='left').pack(fill='x',pady=10)

    def load_example(self):
        self.questions=[{'tema':f'Tema {i%4+1}','pregunta':f'Pregunta de demostración {i+1}',
            'correcta':'ABCD'[i%4]} for i in range(20)]
        self.file_questions.set('20 preguntas FICTICIAS internas')
        self.feedback.set('Ejemplo: 20 preguntas y 4 temas. No usar para evaluaciones reales.')
        self.navigate('Inicio')

    def choose_questions(self):
        f=filedialog.askopenfilename(parent=self.window,title='Excel de preguntas',filetypes=[('Excel','*.xlsx')])
        if not f:return
        try:
            from src.evaluaciones.core import read_questions
            qs=read_questions(Path(f))
            self.questions=[{'tema':q.section,'pregunta':q.prompt,'correcta':'ABCD'[q.correct]} for q in qs]
            self.file_questions.set(f)
            self.feedback.set(f'Se importaron {len(qs)} preguntas.')
        except Exception as exc:
            messagebox.showerror('No se pudo importar',str(exc),parent=self.window)
        self.navigate('Inicio')

    def _roster(self):
        self._heading('Participantes','Importa CSV/XLSX con ID_personal, Nombre, Area_adscripcion, Grupo y Turno.')
        c=self._card();self._field(c,'Archivo de personal',self.file_roster,True)
        controls=tk.Frame(c,bg=WHITE);controls.pack(fill='x')
        self._btn(controls,'Cargar lista',self.choose_roster,True)
        self._btn(controls,'Usar 8 personas ficticias',self.sample_roster)
        if self.session_id:self._note('La lista queda fijada en la sesión ya creada. Para cambiarla, crea una sesión nueva desde Inicio.')
        self._table(['ID','Nombre','Área','Grupo'],[(p['id'],p['nombre'],p.get('area',''),p.get('grupo','')) for p in self.people])

    def choose_roster(self):
        file=filedialog.askopenfilename(parent=self.window,title='Lista de personal',filetypes=[('Excel o CSV','*.xlsx *.csv')])
        if not file:return
        try:
            self.people=read_roster(Path(file));self.file_roster.set(file)
            self.feedback.set(f'{len(self.people)} participantes de la lista.')
            self.navigate('Participantes')
        except Exception as exc:messagebox.showerror('Lista inválida',str(exc),parent=self.window)

    def sample_roster(self):
        self.people=[{'id':f'{i:06d}','nombre':f'Participante ficticio {i}',
            'area':'Área demostración','grupo':'Grupo A','turno':'Matutino'} for i in range(1,9)]
        self.file_roster.set('8 personas ficticias internas')
        self.navigate('Participantes')

    def create_session(self):
        try:
            if not self.questions:raise ValueError('Primero importa preguntas o carga el ejemplo.')
            if self.mode.get()=='personalizado' and not self.people:raise ValueError('Carga personal antes de crear esta modalidad.')
            sid=self.store.create_session(self.title.get(),self.questions,self.people if self.mode.get()=='personalizado' else [],
                self.paper.get(),self.mode.get())
            self.session_id=sid;self.feedback.set('Sesión creada: '+sid)
            self.navigate('Hojas con QR' if self.mode.get()=='personalizado' else 'Inicio')
        except Exception as exc:messagebox.showerror('No se creó sesión',str(exc),parent=self.window)

    def _session_required(self):
        if not self.session_id:
            self._note('Primero crea la sesión desde Inicio.')
            return False
        return True

    def _paper(self):
        self._heading('Hojas de respuesta con folio y QR real','Cada hoja identifica una persona mediante un token firmado. El nombre no está codificado en el QR.')
        if not self._session_required():return
        s=self.store.session(self.session_id)
        c=self._card()
        tk.Label(c,text=f'Sesión {self.session_id} · {len(s["personal"])} personas · {len(s["preguntas"])} preguntas · {s["papel"]}',bg=WHITE,fg=NAVY).pack(anchor='w')
        controls=tk.Frame(c,bg=WHITE);controls.pack(fill='x')
        self._btn(controls,'Generar PDF para imprimir',self.print_forms,True)
        self._btn(controls,'Mostrar primera hoja real',self.preview_form)
        if self.last_print:tk.Label(c,text=str(self.last_print),bg=WHITE,fg='#66808f',wraplength=750).pack(anchor='w')
        self.preview=tk.Label(self.stage,bg=LIGHT)
        self.preview.pack(fill='both',expand=True,pady=8)

    def print_forms(self):
        if not self.session_id:return
        location=filedialog.asksaveasfilename(parent=self.window,defaultextension='.pdf',
            initialfile='Hojas_OMR_Folios_QR.pdf',filetypes=[('PDF','*.pdf')])
        if not location:return
        try:
            self.last_print=create_forms_pdf(self.store,self.session_id,Path(location))
            self.feedback.set('PDF de hojas personalizado generado.')
            self.navigate('Hojas con QR')
            self.preview_form()
        except Exception as exc:messagebox.showerror('Error al imprimir',str(exc),parent=self.window)

    def preview_form(self):
        if not self.session_id:return
        import pypdfium2 as pdfium
        path=self.last_print or create_forms_pdf(self.store,self.session_id,self.store.root/'temporales'/f'{self.session_id}_vista.pdf')
        doc=pdfium.PdfDocument(str(path))
        page=doc[0]
        try:pic=page.render(scale=1.25).to_pil().convert('RGB')
        finally:page.close();doc.close()
        pic.thumbnail((680,690))
        self.photo=ImageTk.PhotoImage(pic,master=self.window)
        self.preview.configure(image=self.photo)

    def _scanner(self):
        self._heading('Escanear respuestas','Xerox VersaLink C7120 · PDF multipágina · 300 dpi en grises para la prueba física inicial.')
        if not self._session_required():return
        c=self._card()
        self._btn(c,'Cargar PDF escaneado',self.load_scanned,True)
        self._btn(c,'Simular lectura OMR real con hojas sintéticas',self.simulate_scanned)
        self._note('La simulación sí utiliza el mismo motor de reconocimiento y compara píxeles de hojas marcadas, pero las marcas se generan digitalmente. No demuestra precisión en la Xerox física.')
        self._scan_status=tk.Text(self.stage,height=8,wrap='word',bg=WHITE,fg=INK,font=('Consolas',10))
        self._scan_status.pack(fill='x',pady=10)

    def simulate_scanned(self):
        if not self.session_id:return
        try:
            folder=self.store.root/'pruebas_sinteticas'/self.session_id
            _,scan=create_synthetic_scan(self.store,self.session_id,folder)
            self._run_scan(scan)
        except Exception as exc:messagebox.showerror('Error en simulación',str(exc),parent=self.window)

    def load_scanned(self):
        if not self.session_id:return
        f=filedialog.askopenfilename(parent=self.window,title='PDF de escáner',filetypes=[('PDF','*.pdf')])
        if f:self._run_scan(Path(f))

    def _run_scan(self,source):
        """Nunca procesa píxeles en Tk: un hilo hace el trabajo y entrega resultado por Queue."""
        if self.scanning:
            messagebox.showinfo('Lectura en proceso','Ya hay un lote en procesamiento.',parent=self.window)
            return
        self.scanning=True
        self.feedback.set('Leyendo PDF en segundo plano… Se mantiene disponible la interfaz.')
        def work():
            try:self.scan_updates.put(('ok',source,scan_document(self.store,self.session_id,Path(source))))
            except Exception as exc:self.scan_updates.put(('error',source,str(exc)))
        Thread(target=work,daemon=True).start()
        self.window.after(120,self._finish_scan)

    def _finish_scan(self):
        try:status,source,payload=self.scan_updates.get_nowait()
        except Empty:
            if self.window.winfo_exists():self.window.after(120,self._finish_scan)
            return
        self.scanning=False
        if status=='error':
            self.feedback.set('No se completó la lectura.')
            messagebox.showerror('No se pudo leer PDF',payload,parent=self.window)
            return
        report=payload
        summary=(f'PDF: {source} · Páginas: {report["leidas"]} · '
            f'Validadas: {report["validadas"]} · Pendientes: {report["revisar"]} · '
            f'Sin identificar: {report["sin_identificar"]} · Duplicadas: {report["duplicadas"]} · '
            f'Reimportadas: {report["repetidas"]} · '
            f'Reprocesadas: {report.get("reprocesadas",0)}')
        problems=[d for d in report.get('detalles',[])
                  if d.get('diagnostico') and d.get('estado')=='sin_identificar']
        if problems:
            reasons=sorted({d['diagnostico'] for d in problems})
            summary+=' · Diagnóstico: '+'; '.join(reasons)
        self.feedback.set(summary)
        self.navigate('Revisión')
        different=sorted({d['sesion_detectada'] for d in problems
                          if d.get('sesion_detectada')})
        if different:
            messagebox.showwarning(
                'Hojas de otra evaluación',
                'El QR corresponde a una sesión diferente: '+
                ', '.join(different)+
                '. Abre esa evaluación desde Historial antes de volver a importar. '
                'No se asignaron notas a otra persona.',
                parent=self.window)

    def _table(self,columns,rows,on_select=None):
        frame=tk.Frame(self.stage,bg=LIGHT)
        frame.pack(fill='both',expand=True,pady=10)
        tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse',height=15)
        for col in columns:
            tree.heading(col,text=col);tree.column(col,width=125 if col!='Nombre' else 215,stretch=True)
        sc=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=sc.set)
        tree.pack(side='left',fill='both',expand=True);sc.pack(side='left',fill='y')
        for row in rows:tree.insert('', 'end',values=row)
        if on_select:tree.bind('<<TreeviewSelect>>',lambda _:on_select(tree))
        return tree

    def _review(self):
        self._heading('Revisión y captura con acetato digital',
                      'Navega entre todas las hojas, superpone la clave sobre '
                      'las marcas y captura respuestas manualmente si hace falta.')
        if not self._session_required():return
        pages=self.store.pages(self.session_id)
        people={p['token']:p for p in self.store.session(self.session_id)['personal']}
        # Incluir también hojas ya validadas: facilita comprobar el acetato,
        # cambiar de página y verificar las respuestas antes de la entrega.
        suspects=sorted(pages,key=lambda item:(item['estado']=='validada',
                                               item['pagina']))
        self._note('Resultados definitivos bloqueados si hay hojas sin identificar, ambiguas o duplicadas. Las correcciones quedan firmadas en la bitácora.')
        content=tk.Frame(self.stage,bg=LIGHT);content.pack(fill='both',expand=True)
        left=tk.Frame(content,bg=LIGHT,width=450);left.pack(side='left',fill='both',expand=False)
        right=tk.Frame(content,bg=WHITE,padx=10,pady=10);right.pack(side='left',fill='both',expand=True,padx=9)
        tree=ttk.Treeview(left,columns=('Persona','Estado','Dudas'),show='headings',height=7)
        for name,width in [('Persona',190),('Estado',130),('Dudas',90)]:tree.heading(name,text=name);tree.column(name,width=width)
        tree.pack(fill='x')
        lookup={}
        for p in suspects:
            who=people.get(p['token'],{}).get('nombre','Sin identificar')
            q=','.join(str(x.get('pregunta')) for x in p['dudas'])
            tree.insert('', 'end',iid=p['id'],values=(who,p['estado'],q))
            lookup[p['id']]=p
        tk.Label(right,text='Hoja escaneada · evidencia',bg=WHITE,fg=NAVY,font=('Segoe UI',11,'bold')).pack(anchor='w')
        show_overlay=tk.BooleanVar(value=True)
        zoom_issue=tk.BooleanVar(value=False)
        show_acetato=tk.BooleanVar(value=True)
        tk.Checkbutton(right,text='Superponer acetato digital (verde = clave correcta)',
                       variable=show_acetato,bg=WHITE,fg=INK,
                       command=lambda:redraw()).pack(anchor='w')
        tk.Checkbutton(right,text='Resaltar dudas (naranja, sin cambiar el original)',
                       variable=show_overlay,bg=WHITE,fg=INK,
                       command=lambda:redraw()).pack(anchor='w')
        tk.Checkbutton(right,text='Acercar reactivo seleccionado',
                       variable=zoom_issue,bg=WHITE,fg=INK,
                       command=lambda:redraw()).pack(anchor='w')
        image_label=tk.Label(right,bg=WHITE)
        image_label.pack(fill='both',expand=True)
        detail=tk.StringVar(value='Selecciona una hoja para verla.')
        tk.Label(left,textvariable=detail,bg=LIGHT,fg='#607987',wraplength=385,justify='left').pack(anchor='w',pady=8)
        opt=tk.StringVar(value='A')
        question=tk.StringVar(value='1')
        reviewer=tk.StringVar(value='Evaluador')
        reason=tk.StringVar(value='Marca verificada en el escaneo original')
        form=tk.Frame(left,bg=LIGHT);form.pack(fill='x')
        for label,var,vals in [('Reactivo',question,None),('Decisión A/B/C/D o BLANCO',opt,('A','B','C','D','BLANCO','DESCARTAR')),('Revisor',reviewer,None),('Justificación',reason,None)]:
            tk.Label(form,text=label,bg=LIGHT,fg=INK).pack(anchor='w',pady=(6,1))
            if vals:ttk.Combobox(form,textvariable=var,values=vals,state='readonly').pack(fill='x')
            else:ttk.Entry(form,textvariable=var).pack(fill='x')
        selected={'id':None}
        def redraw(*_):
            sel=tree.selection()
            if not sel:return
            selected['id']=sel[0];p=lookup[sel[0]]
            reasons='; '.join(str(issue.get('razon',''))
                              for issue in p['dudas'][:2])
            detail.set(f'{p["estado"].upper()} · página {p["pagina"]+1} · '
                       f'{len(p["dudas"])} observaciones'+
                       (f' · {reasons}' if reasons else ''))
            if p['dudas'] and p['dudas'][0].get('pregunta'):
                question.set(str(p['dudas'][0]['pregunta']))
            try:
                # El archivo PNG archivado y el PDF original jamás se editan.
                # La hoja se rectifica EN MEMORIA a partir de las cuatro marcas.
                import cv2
                original=cv2.imread(str(p['imagen']))
                if original is None:
                    raise OSError('No se encontró la evidencia archivada.')
                session=self.store.session(self.session_id)
                try:
                    img=render_review_with_acetato(
                        original,session['papel'],session['preguntas'],
                        show_acetato=show_acetato.get(),
                        issue_numbers=(
                            [i.get('pregunta') for i in p['dudas']]
                            if show_overlay.get() else []
                        ),
                    )
                except ValueError as alignment_error:
                    # No falsificar coincidencia del acetato sin cuatro marcas.
                    img=Image.open(p['imagen']).convert('RGB')
                    detail.set(detail.get()+' · SIN ACETATO: '+str(alignment_error))
                if zoom_issue.get():
                    try:
                        qid=int(question.get())
                        dots=bubble_positions(session['papel'],
                                               len(session['preguntas']))[qid-1]
                        height=PAPERS[session['papel']][1]
                        xx=[round(x*RENDER_DPI/72) for x,y in dots]
                        yy=[round((height-y)*RENDER_DPI/72) for x,y in dots]
                        img=img.crop((max(0,min(xx)-120),max(0,min(yy)-85),
                                    min(img.width,max(xx)+115),
                                    min(img.height,max(yy)+90)))
                    except (ValueError,IndexError):
                        pass
                # Aprovechar el espacio de revisión maximizado sin forzar
                # reescalado hacia arriba ni alterar el escaneo original.
                area_width = max(520, min(1150, self.window.winfo_width() - 790))
                area_height = max(540, min(960, self.window.winfo_height() - 220))
                img.thumbnail((area_width, area_height))
                self.photo=ImageTk.PhotoImage(img,master=self.window)
                image_label.configure(image=self.photo)
            except Exception as exc:detail.set('No se puede mostrar imagen: '+str(exc))
        tree.bind('<<TreeviewSelect>>',redraw)
        question.trace_add('write',lambda *_:redraw() if zoom_issue.get() else None)
        def decide():
            if selected['id'] is None:return
            try:
                self.store.review(selected['id'],int(question.get()) if opt.get()!='DESCARTAR' else None,
                    opt.get(),reason.get(),reviewer.get())
                self.navigate('Revisión')
                self.feedback.set('Decisión registrada con trazabilidad.')
            except Exception as exc:messagebox.showerror('Revisión inválida',str(exc),parent=self.window)
        self._btn(form,'Confirmar decisión',decide,True)
        tk.Label(form,text='Si el QR es ilegible: ID y folio visible de la hoja',bg=LIGHT,fg=INK).pack(anchor='w',pady=(12,2))
        manual_id=tk.StringVar();manual_folio=tk.StringVar()
        ttk.Entry(form,textvariable=manual_id).pack(fill='x')
        ttk.Entry(form,textvariable=manual_folio).pack(fill='x',pady=(3,1))
        def assign():
            if selected['id'] is None:return
            try:
                self.store.identify_page(selected['id'],manual_id.get(),manual_folio.get(),reason.get(),reviewer.get())
                self.feedback.set('Hoja identificada bajo supervisión: revisa TODAS sus respuestas.')
                self.navigate('Revisión')
            except Exception as exc:messagebox.showerror('No se identificó la hoja',str(exc),parent=self.window)
        self._btn(form,'Vincular por ID y folio (sin calificar)',assign)
        def next_sheet():
            if not suspects:return
            current=tree.selection()
            ids=[p['id'] for p in suspects]
            pos=ids.index(current[0]) if current and current[0] in ids else -1
            nxt=ids[(pos+1)%len(ids)]
            tree.selection_set(nxt)
            tree.see(nxt)
            redraw()

        def manual_entry():
            if selected['id'] is None:return
            sheet=lookup[selected['id']]
            if sheet['token'] is None:
                messagebox.showwarning(
                    'Primero identificar hoja',
                    'Vincula la hoja por ID y folio, o reimporta el PDF con el '
                    'nuevo lector. No se guardan notas de personas desconocidas.',
                    parent=self.window)
                return
            if sheet['estado'] in ('descartada','duplicado'):
                messagebox.showwarning(
                    'Hoja no disponible',
                    'Resuelve primero el duplicado o la hoja descartada.',
                    parent=self.window)
                return
            session=self.store.session(self.session_id)
            questions=session['preguntas']
            dlg=tk.Toplevel(self.window)
            dlg.title('Captura manual · hoja '+str(sheet['pagina']+1))
            # Abrir el formulario a la IZQUIERDA para conservar visible
            # la hoja y el acetato digital a la derecha durante la captura.
            dw=460
            dh=max(430,min(760,self.window.winfo_screenheight()-135))
            dx=self.window.winfo_rootx()+210
            dy=self.window.winfo_rooty()+85
            dlg.geometry(f'{dw}x{dh}+{dx}+{dy}')
            dlg.minsize(410,400)
            dlg.transient(self.window)
            dlg.grab_set()
            tk.Label(dlg,
                text='Captura íntegra con acetato digital',
                font=('Segoe UI',15,'bold'),fg=NAVY,pady=9).pack(anchor='w',padx=15)
            tk.Label(dlg,
                text='Verifica cada círculo. BLANCO indica que no contestó; '
                     'SIN REVISAR impide guardar.',
                fg=INK,wraplength=600,justify='left').pack(anchor='w',padx=15)
            wrapper=tk.Frame(dlg)
            wrapper.pack(fill='both',expand=True,padx=15,pady=(8,4))
            sc=tk.Canvas(wrapper,highlightthickness=0)
            sb=ttk.Scrollbar(wrapper,orient='vertical',command=sc.yview)
            sc.configure(yscrollcommand=sb.set)
            sb.pack(side='right',fill='y')
            sc.pack(side='left',fill='both',expand=True)
            inner=tk.Frame(sc)
            wnd=sc.create_window((0,0),window=inner,anchor='nw')
            inner.bind('<Configure>',lambda e:sc.configure(scrollregion=sc.bbox('all')))
            sc.bind('<Configure>',lambda e:sc.itemconfigure(wnd,width=e.width))
            selections=[]
            for number,item in enumerate(questions,1):
                row=tk.Frame(inner,pady=4)
                row.pack(fill='x')
                txt=str(item['pregunta']).replace('\n',' ')
                tk.Label(row,text=f'{number:02d}  {txt[:43]}',
                         anchor='w',width=42).pack(side='left',fill='x',expand=True)
                old=(sheet['respuestas'][number-1]
                     if number<=len(sheet['respuestas']) else None)
                current=tk.StringVar(value=old if old else 'SIN REVISAR')
                selections.append(current)
                ttk.Combobox(row,textvariable=current,values=(
                    'SIN REVISAR','A','B','C','D','BLANCO'),
                    width=12,state='readonly').pack(side='right')
            footer=tk.Frame(dlg,padx=15,pady=10)
            footer.pack(fill='x')
            tk.Label(footer,text='Revisor: '+reviewer.get(),
                     fg=INK).pack(anchor='w')
            def save_all():
                responses=[v.get() for v in selections]
                try:
                    count=self.store.capture_manual_sheet(
                        selected['id'],responses,reason.get(),reviewer.get())
                except (ValueError,OSError) as exc:
                    messagebox.showerror('Captura incompleta',
                                         str(exc),parent=dlg)
                    return
                ids=[p['id'] for p in suspects]
                self.review_focus_id=(
                    ids[(ids.index(selected['id'])+1)%len(ids)]
                    if len(ids)>1 else selected['id'])
                dlg.destroy()
                self.feedback.set(
                    f'{count} respuestas verificadas y guardadas con auditoría.')
                self.navigate('Revisión')
            ttk.Button(footer,text='Guardar TODAS las respuestas',
                       command=save_all).pack(side='left')
            ttk.Button(footer,text='Cancelar',
                       command=dlg.destroy).pack(side='right')

        self._btn(form,'Capturar hoja completa',manual_entry,True)
        self._btn(form,'Siguiente hoja',next_sheet)
        if not suspects:
            self._note('Todavía no hay hojas escaneadas para esta sesión.')
        else:
            focus=getattr(self,'review_focus_id',None)
            ids=[p['id'] for p in suspects]
            first=focus if focus in ids else next(
                (p['id'] for p in suspects if p['estado']!='validada'),
                suspects[0]['id'])
            tree.selection_set(first)
            tree.see(first)
            redraw()

    def _results(self):
        self._heading('Resultados y desempeño','El promedio excluye ausentes y pendientes. El desempeño por tema utiliza preguntas de ese tema.')
        if not self._session_required():return
        report=self.store.results(self.session_id)
        c=self._card()
        tk.Label(c,text=f'PROMEDIO DE VALIDADOS: {report["promedio"] if report["promedio"] is not None else "—"}%  ·  '
                        f'Validados {report["validados"]}  ·  Pendientes {report["pendientes"]}  ·  Ausentes {report["ausentes"]}',
                  bg=WHITE,fg=NAVY,font=('Segoe UI',12,'bold')).pack(anchor='w')
        listing=self._table(['ID','Nombre','Aciertos','Porcentaje','Estado'],
                    [(p['id'],p['nombre'],f'{p["aciertos"]}/{p["preguntas"]}' if p['aciertos'] is not None else '—',
                    str(p['porcentaje'])+'%' if p['porcentaje'] is not None else '—',p['estado']) for p in report['participantes']])
        breakdown=tk.StringVar(value='Selecciona una persona para ver sus temas.')
        tk.Label(self.stage,textvariable=breakdown,bg=LIGHT,fg=INK,font=('Segoe UI',10),wraplength=860,justify='left').pack(anchor='w',pady=7)
        def show_detail(_event):
            sel=listing.selection()
            if not sel:return
            personid=listing.item(sel[0],'values')[0]
            person=next(p for p in report['participantes'] if p['id']==personid)
            breakdown.set(person['nombre']+': '+ ' · '.join(f'{n}: {v["aciertos"]}/{v["preguntas"]} ({v["porcentaje"]}%)'
                  for n,v in person['temas'].items()) if person['temas'] else 'Sin calificación validada.')
        listing.bind('<<TreeviewSelect>>',show_detail)
        self._note('GRUPO · DESEMPEÑO POR TEMA: '+ '   ·   '.join(f'{n}: {v["porcentaje"] if v["porcentaje"] is not None else "—"}%'
                   for n,v in report['temas'].items()))

    def _export(self):
        self._heading('Entregables en Excel','Un archivo oficial sin claves, y otro interno con incidencias, escaneos y bitácora.')
        if not self._session_required():return
        report=self.store.results(self.session_id)
        c=self._card()
        status='DEFINITIVO' if report['definitivo'] else 'PROVISIONAL · Faltan revisiones'
        tk.Label(c,text='ESTADO DE LA SESIÓN: '+status,bg=WHITE,fg=TEAL if report['definitivo'] else '#AF6F25',
                 font=('Segoe UI',12,'bold')).pack(anchor='w')
        self._btn(c,'Generar Excel oficial',lambda:self.save_excel(False),True)
        self._btn(c,'Generar Excel interno',lambda:self.save_excel(True))
        self._note('El reporte oficial no revela las respuestas correctas. Si hay pendientes, se etiqueta PROVISIONAL. La sesión se guarda y permite reexportar sin escanear de nuevo.')

    def save_excel(self,internal=False):
        target=filedialog.asksaveasfilename(parent=self.window,defaultextension='.xlsx',
            filetypes=[('Libro Excel','*.xlsx')],initialfile='Resultados_Internos.xlsx' if internal else 'Resultados_Oficiales.xlsx')
        if not target:return
        try:
            export_report(self.store,self.session_id,Path(target),internal=internal)
            self.feedback.set('Excel exportado: '+str(target))
            messagebox.showinfo('Archivo generado','Excel disponible en:\n'+str(target),parent=self.window)
        except Exception as exc:messagebox.showerror('No se pudo exportar',str(exc),parent=self.window)

    def _history(self):
        self._heading(
            'Historial de evaluaciones y aplicaciones',
            'La biblioteca y sus folios/escaneos se relacionan por el ID del cuestionario. '
            'La clave y los resultados permanecen en la sesión original.',
        )
        from biblioteca import list_exams
        exams=(list_exams(self.library_db_path)
               if self.library_db_path.is_file() else [])
        sessions=self.store.sessions()
        if self.review_only:
            sessions=[x for x in sessions if x.get('cantidad_participantes',0)>0]

        # La biblioteca conserva el nombre de la evaluación. Los folios nacen
        # como aplicaciones de esa evaluación y no duplican otro cuestionario.
        linked={x['cuestionario_id'] for x in sessions if x.get('cuestionario_id')}
        box=tk.Frame(self.stage,bg=LIGHT)
        box.pack(fill='both',expand=True,pady=(5,8))
        cols=('Modalidad','Participantes','Escaneadas','Pendientes','Fecha')
        tree=ttk.Treeview(box,columns=cols,show='tree headings',height=13,
                          selectmode='browse')
        tree.heading('#0',text='Evaluación / aplicación / folio')
        tree.column('#0',width=380,minwidth=280,stretch=True)
        for col,width in [('Modalidad',120),('Participantes',104),
                          ('Escaneadas',95),('Pendientes',95),('Fecha',148)]:
            tree.heading(col,text=col)
            tree.column(col,width=width,minwidth=75,stretch=True)
        scroll=ttk.Scrollbar(box,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        known={}
        for exam in exams:
            iid='exam:'+exam['id']
            tree.insert('', 'end',iid=iid,
                text=exam['nombre'] or exam['titulo'],
                values=('Biblioteca · rev. '+str(exam['revision']),
                        '—','—','—',
                        exam['actualizado_en'][:16].replace('T',' ')),open=True)
            known[exam['id']]=iid
        for session in sessions:
            sid=session['id']
            parent=known.get(session.get('cuestionario_id'),'')
            name=session.get('nombre_evaluacion') or session['titulo']
            if not session.get('nombre_evaluacion'):
                name += ' · histórica '+sid[:8]
            mode={'normal':'Normal + QR','ecologico':'Ecológico + QR',
                  'personalizado':'QR (anterior)'}.get(
                      session['modo'],session['modo'])
            tree.insert(parent,'end',iid='session:'+sid,
                text=name+' · '+sid[:8],
                values=(mode,session['cantidad_participantes'],
                        session.get('hojas_escaneadas',0),
                        session.get('hojas_pendientes',0),
                        session['creada'][:16].replace('T',' ')))
        if not exams and not sessions:
            self._note('Todavía no hay evaluaciones guardadas. Diseña el examen, '
                       'ponle un nombre y genera los documentos.')
        elif not sessions:
            self._note('Los cuestionarios están guardados; para calificar '
                       'automáticamente genera hojas con una lista de participantes.')

        def selected_entry():
            chosen=tree.selection()
            return chosen[0] if chosen else None

        def open_item():
            selected=selected_entry()
            if not selected:return
            if selected.startswith('exam:'):
                if self.on_open_exam is None:
                    messagebox.showinfo('Abrir evaluación',
                        'Vuelve a Diseñar e imprimir y abre el examen en Biblioteca.',
                        parent=self.window)
                    return
                exam_id=selected.split(':',1)[1]
                # Cerrar OMR restaura la raíz y el diseñador; el callback carga
                # después ese examen exacto por UUID, nunca solo por título.
                self.return_to_generator()
                self.on_open_exam(exam_id)
                return
            sid=selected.split(':',1)[1]
            try:
                session=self.store.session(sid)
            except ValueError as exc:
                messagebox.showerror('Sesión inválida',str(exc),parent=self.window)
                return
            self.session_id=sid
            self.mode.set(session['modo'])
            self.title.set(session['titulo'])
            self.paper.set(session['papel'])
            self.questions=session['preguntas']
            self.people=session['personal']
            self.feedback.set('Aplicación abierta: '+
                (session.get('nombre_evaluacion') or session['titulo'])+
                ' · Folios: '+str(len(self.people)))
            self.navigate('Resultados' if self.review_only or
                          self.mode.get()=='personalizado' else 'Inicio')

        def rename_item():
            selected=selected_entry()
            if not selected or not selected.startswith('session:'):
                messagebox.showinfo('Renombrar aplicación',
                    'Selecciona un registro con folios/QR para ponerle un nombre.',
                    parent=self.window)
                return
            sid=selected.split(':',1)[1]
            session=self.store.session(sid)
            proposed=session.get('nombre_evaluacion') or session['titulo']
            name=simpledialog.askstring('Nombre de la aplicación',
                'Nombre visible en el historial (no altera respuestas ni folios):',
                initialvalue=proposed,parent=self.window)
            if name is None:return
            try:self.store.rename_session(sid,name)
            except ValueError as exc:
                messagebox.showerror('Nombre inválido',str(exc),parent=self.window)
                return
            self.navigate('Historial')

        toolbar=tk.Frame(self.stage,bg=LIGHT)
        toolbar.pack(fill='x',pady=(0,6))
        self._btn(toolbar,'Abrir seleccionado',open_item,True)
        self._btn(toolbar,'Renombrar aplicación anterior',rename_item)
        self._btn(toolbar,'Actualizar historial',
                  lambda:self.navigate('Historial'))
        tree.bind('<Double-Button-1>',lambda _event:open_item())


def launch(parent=None, *, questions=None, title=None, paper=None, source=None,
           on_return=None, start_page='Inicio', review_only=False,
           library_db_path=None, on_open_exam=None):
    """Abre la calificación dentro del generador y hereda preguntas si existen."""
    app=OMRApp(parent=parent,questions=questions,title=title,paper=paper,
               source=source,on_return=on_return,start_page=start_page,
               review_only=review_only,
               library_db_path=library_db_path,on_open_exam=on_open_exam)
    if parent is None:app.window.mainloop()
    return app
