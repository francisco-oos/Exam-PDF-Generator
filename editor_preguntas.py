"""Editor local de preguntas en memoria, desacoplado de la capa SQLite/PDF."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps

from biblioteca import _check_questions
from src.evaluaciones.core import Question, ExamError, _safe_image


def edit_questions(parent: tk.Tk, initial: list[Question] | tuple[Question, ...]) -> list[Question] | None:
    """Devuelve edición confirmada o None al cancelar, sin tocar archivos originales."""
    items=list(initial) or [Question('Nuevo tema', 'Escribe la nueva pregunta', ('Opción A', 'Opción B', 'Opción C', 'Opción D'), 0)]
    result=[None]
    win=tk.Toplevel(parent)
    win.title('Editar preguntas del cuestionario')
    win.geometry('1080x710')
    win.minsize(880,610)
    win.transient(parent)
    win.grab_set()
    root=tk.Frame(win,padx=18,pady=15)
    root.pack(fill='both',expand=True)
    tk.Label(root,text='Preguntas y respuestas',font=('Segoe UI',17,'bold')).pack(anchor='w')
    tk.Label(root,text='Edita la pregunta seleccionada y guarda cada cambio. La respuesta correcta es la letra A, B, C o D.',
             font=('Segoe UI',9),fg='#617382').pack(anchor='w',pady=(3,11))
    pane=tk.PanedWindow(root,orient='horizontal',sashwidth=5)
    pane.pack(fill='both',expand=True)
    left=tk.Frame(pane)
    panel=tk.Frame(pane)
    pane.add(left,minsize=240)
    pane.add(panel,minsize=360)
    canvas=tk.Canvas(panel,highlightthickness=0)
    bar=ttk.Scrollbar(panel,orient='vertical',command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
    right=tk.Frame(canvas,padx=14)
    entry=canvas.create_window((0,0),window=right,anchor='nw')
    right.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(entry,width=e.width))
    tree=ttk.Treeview(left,columns=('no','tema','correcta'),show='headings',selectmode='browse')
    tree.heading('no',text='N.º');tree.heading('tema',text='Tema');tree.heading('correcta',text='Clave')
    tree.column('no',width=40,anchor='center',stretch=False)
    tree.column('tema',width=205);tree.column('correcta',width=50,anchor='center',stretch=False)
    yscroll=ttk.Scrollbar(left,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=yscroll.set)
    yscroll.pack(side='right',fill='y');tree.pack(side='left',fill='both',expand=True)
    topic=tk.StringVar();answers=[tk.StringVar() for _ in range(4)]
    correct=tk.StringVar(value='A');image=tk.StringVar()
    def label(t):tk.Label(right,text=t,font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(7,3))
    label('Tema o sección')
    ttk.Entry(right,textvariable=topic).pack(fill='x')
    label('Enunciado de la pregunta')
    prompt=tk.Text(right,height=4,wrap='word',font=('Segoe UI',10))
    prompt.pack(fill='x')
    for l,v in zip('ABCD',answers):
        label('Respuesta '+l)
        ttk.Entry(right,textvariable=v).pack(fill='x')
    label('Respuesta correcta')
    ttk.Combobox(right,textvariable=correct,state='readonly',values=list('ABCD'),width=9).pack(anchor='w')
    label('Imagen opcional (PNG/JPG)')
    imgbar=tk.Frame(right);imgbar.pack(fill='x')
    ttk.Entry(imgbar,textvariable=image).pack(side='left',fill='x',expand=True)
    def image_choose():
        f=filedialog.askopenfilename(parent=win,title='Elegir imagen para la pregunta',
                  filetypes=[('PNG o JPEG','*.png *.jpg *.jpeg')])
        if f:image.set(f)
    ttk.Button(imgbar,text='Examinar',command=image_choose).pack(side='right',padx=(6,0))
    def preview_image():
        try:
            path=_safe_image(Path(image.get()),source='Imagen de la pregunta')
            with Image.open(path) as source:
                picture=ImageOps.contain(source.convert('RGB'),(650,500))
            popup=tk.Toplevel(win);popup.title('Vista de imagen')
            photo=ImageTk.PhotoImage(picture,master=popup)
            label=tk.Label(popup,image=photo);label.image=photo;label.pack()
            ttk.Button(popup,text='Cerrar',command=popup.destroy).pack(pady=8)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Imagen no disponible',str(exc),parent=win)
    ttk.Button(right,text='Ver imagen',command=preview_image).pack(anchor='w',pady=8)
    selected=[0]
    def refresh(select=0):
        tree.delete(*tree.get_children())
        for i,q in enumerate(items):tree.insert('', 'end', iid=str(i),values=(i+1,q.section,'ABCD'[q.correct]))
        if items:
            select=max(0,min(select,len(items)-1))
            tree.selection_set(str(select));tree.see(str(select))
            show(select)
    def show(index):
        selected[0]=index
        q=items[index]
        topic.set(q.section);prompt.delete('1.0','end');prompt.insert('1.0',q.prompt)
        for v,a in zip(answers,q.options):v.set(a)
        correct.set('ABCD'[q.correct]);image.set(str(q.image or ''))
    def selection(_):
        picks=tree.selection()
        if not picks or int(picks[0]) == selected[0]:return
        index=int(picks[0])
        if save_item(refresh_ui=False):
            show(index)
        else:
            tree.selection_set(str(selected[0]))
    tree.bind('<<TreeviewSelect>>',selection)
    def save_item(refresh_ui=True):
        if not items:return False
        photo=Path(image.get()) if image.get().strip() else None
        try:
            if photo:_safe_image(photo,source='Imagen de la pregunta')
            q=Question(topic.get().strip(),prompt.get('1.0','end-1c').strip(),
                       tuple(v.get().strip() for v in answers),'ABCD'.index(correct.get()),photo)
            temp=items[selected[0]];items[selected[0]]=q
            try:_check_questions(items)
            except Exception:
                items[selected[0]]=temp
                raise
        except (ExamError,ValueError,OSError) as e:
            messagebox.showerror('Corrige la pregunta',str(e),parent=win);return False
        if refresh_ui:refresh(selected[0])
        return True
    buttons=tk.Frame(root,pady=9);buttons.pack(fill='x')
    ttk.Button(buttons,text='Guardar cambio en pregunta',command=save_item).pack(side='left')
    def add():
        if not save_item():return
        if len(items)>=100:
            messagebox.showwarning('Límite','Máximo 100 preguntas.',parent=win);return
        items.append(Question('Nuevo tema','Escribe la nueva pregunta',('Opción A','Opción B','Opción C','Opción D'),0,None))
        refresh(len(items)-1)
    def remove():
        if len(items)<=1:
            messagebox.showwarning('No se puede eliminar','El cuestionario necesita una pregunta.',parent=win);return
        if messagebox.askyesno('Eliminar pregunta','¿Eliminar la pregunta seleccionada?',parent=win):
            items.pop(selected[0]);refresh(min(selected[0],len(items)-1))
    ttk.Button(buttons,text='Añadir pregunta',command=add).pack(side='left',padx=8)
    ttk.Button(buttons,text='Eliminar pregunta',command=remove).pack(side='left')
    def accept():
        if not save_item():return
        try:_check_questions(items)
        except ExamError as e:messagebox.showerror('Revisar preguntas',str(e),parent=win);return
        result[0]=list(items)
        win.destroy()
    ttk.Button(buttons,text='Cancelar',command=win.destroy).pack(side='right')
    ttk.Button(buttons,text='Aplicar al cuestionario',command=accept).pack(side='right',padx=8)
    if items:refresh()
    win.protocol('WM_DELETE_WINDOW',win.destroy)
    parent.wait_window(win)
    return result[0]
