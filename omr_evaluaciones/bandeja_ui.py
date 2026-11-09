"""Bandeja visual de PDFs OMR; solo copias derivadas, nunca editar originales."""
from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pypdfium2 as pdfium
from PIL import ImageTk

from .expedientes import create_organized_pdf


def show_bandeja(app):
    """Pantalla dentro de Calificar y entregar; sin otra aplicación externa."""
    app._heading(
        "Bandeja y organizador PDF",
        "Todo PDF recibido permanece archivado, incluidas las hojas sin QR. "
        "Selecciona una página, gírala o cambia el orden para exportar una COPIA. "
        "El original y las calificaciones no se alteran."
    )
    # La migración histórica es explícita y no bloquea la interfaz al abrir.
    legacy=tk.Frame(app.stage,bg="#eff4f6")
    legacy.pack(fill="x",pady=(4,9))
    legacy_state=tk.StringVar(
        value="Los PDF de sesiones anteriores pueden incorporarse sin recalificar.")
    tk.Label(legacy,textvariable=legacy_state,bg="#eff4f6",
             fg="#405d68").pack(side="left",padx=(0,12))
    def import_old():
        btn_legacy.configure(state="disabled")
        queue=Queue()
        def task():
            try:
                queue.put((True,app.evidence.migrate_legacy()))
            except Exception as exc:
                queue.put((False,str(exc)))
        Thread(target=task,daemon=True).start()
        def poll():
            try:
                ok,value=queue.get_nowait()
            except Empty:
                if app.window.winfo_exists():
                    app.window.after(130,poll)
                return
            if ok:
                app.feedback.set(
                    f'Migración completa: {value["hojas_vinculadas"]} hojas '
                    'históricas vinculadas, sin recalificar.')
                app.navigate("Bandeja PDF")
            else:
                btn_legacy.configure(state="normal")
                messagebox.showerror("Migración histórica",value,
                                     parent=app.window)
        app.window.after(130,poll)
    btn_legacy=ttk.Button(
        legacy,text="Incorporar escaneos anteriores",command=import_old)
    btn_legacy.pack(side="right")
    docs=app.evidence.documents()
    if not docs:
        app._note("La bandeja está vacía. Importa un PDF desde Escanear PDF. "
                  "Se archivará antes de intentar leer o calificar las hojas.")
        c=app._card()
        app._btn(c,"Ir a Escanear PDF",
                 lambda:app.navigate("Escanear PDF"),True)
        return

    state={"sha":None,"order":[],"rotations":{},"photo":None}
    body=tk.PanedWindow(app.stage,orient="horizontal",bg="#dbe7eb",
                        sashwidth=5)
    body.pack(fill="both",expand=True,pady=(7,0))
    left=tk.Frame(body,bg="#ffffff")
    right=tk.Frame(body,bg="#ffffff")
    body.add(left,minsize=270,width=430)
    body.add(right,minsize=380)

    tk.Label(left,text="Archivos recibidos",bg="#ffffff",fg="#132e40",
             font=("Segoe UI",12,"bold")).pack(anchor="w",padx=12,pady=7)
    file_columns=("Páginas","Sin QR","Con evidencia","Fecha")
    files=ttk.Treeview(left,columns=file_columns,show="tree headings",
                       selectmode="browse",height=9)
    files.heading("#0",text="PDF original")
    files.column("#0",width=165,minwidth=100)
    for col,width in zip(file_columns,(60,56,100,115)):
        files.heading(col,text=col)
        files.column(col,width=width,stretch=True)
    files.pack(fill="x",padx=9,pady=(0,12))
    for row in docs:
        files.insert("","end",iid=row["sha"],
                     text=row["nombre_fuente"][:60],
                     values=(row["paginas"],row["sin_identificar"],
                             row["con_evidencia"],
                             row["recibido"][:16].replace("T"," ")))

    tk.Label(left,text="Orden de las páginas",bg="#ffffff",fg="#132e40",
             font=("Segoe UI",11,"bold")).pack(anchor="w",padx=12,pady=5)
    columns=("Evaluación","Folio","Estado","Giro")
    pages=ttk.Treeview(left,columns=columns,show="tree headings",
                       selectmode="extended",height=15)
    pages.heading("#0",text="Página")
    pages.column("#0",width=70,stretch=False)
    for col,width in zip(columns,(155,96,120,45)):
        pages.heading(col,text=col)
        pages.column(col,width=width,stretch=True)
    scroll=ttk.Scrollbar(left,orient="vertical",command=pages.yview)
    pages.configure(yscrollcommand=scroll.set)
    pages.pack(side="left",fill="both",expand=True,padx=(9,0),pady=3)
    scroll.pack(side="left",fill="y",pady=3)

    tk.Label(right,text="Vista de página · copia de trabajo",
             bg="#ffffff",fg="#132e40",
             font=("Segoe UI",12,"bold")).pack(anchor="w",padx=12,pady=7)
    image_label=tk.Label(right,bg="#edf4f7",text="Selecciona una página")
    image_label.pack(fill="both",expand=True,padx=10,pady=(0,6))
    info=tk.StringVar(value="Se conservan los originales.")
    tk.Label(right,textvariable=info,bg="#ffffff",fg="#405d68",
             wraplength=630,justify="left").pack(anchor="w",padx=12,pady=5)

    bar=tk.Frame(right,bg="#ffffff")
    bar.pack(fill="x",padx=10,pady=5)
    actions=tk.Frame(right,bg="#ffffff")
    actions.pack(fill="x",padx=10,pady=(0,8))
    actions_extra=tk.Frame(right,bg="#ffffff")
    actions_extra.pack(fill="x",padx=10,pady=(0,8))

    def current_page():
        selected=pages.selection()
        if not selected:return None
        return int(selected[0])

    def current_doc():
        return app.evidence.document(state["sha"]) if state["sha"] else None

    def refresh_rows(chosen=None):
        pages.delete(*pages.get_children())
        if not state["sha"]:return
        details={d["pagina"]-1:d for d in app.evidence.pages(state["sha"])}
        for idx in state["order"]:
            row=details[idx]
            pages.insert("","end",iid=str(idx),text=f"{idx+1:03d}",
                         values=(row["evaluacion"] or "SIN IDENTIFICAR",
                                 row["folio"] or "—",
                                 row["estado"],state["rotations"].get(idx,0)))
        selected=chosen if chosen in state["order"] else (
            state["order"][0] if state["order"] else None)
        if selected is not None:
            pages.selection_set(str(selected))
            pages.see(str(selected))
            preview()

    def preview(event=None):
        idx=current_page()
        doc=current_doc()
        if idx is None or doc is None:return
        pdf=pdfium.PdfDocument(doc["ruta"])
        try:
            p=pdf[idx]
            try:
                w,h=p.get_size()
                width=max(300,right.winfo_width()-50)
                height=max(280,right.winfo_height()-165)
                scale=min(1.5,max(.35,min(width/w,height/h)))
                picture=p.render(scale=scale).to_pil().convert("RGB")
            finally:
                p.close()
        finally:
            pdf.close()
        turn=state["rotations"].get(idx,0)
        if turn:
            picture=picture.rotate(-turn,expand=True)
        # At most the document's currently selected page is kept in memory.
        state["photo"]=ImageTk.PhotoImage(picture,master=app.window)
        image_label.configure(image=state["photo"],text="")
        record=app.evidence.pages(state["sha"])[idx]
        info.set(
            f"Página {idx+1} de {doc['paginas']} · {record['estado']} · "
            f"{record['evaluacion'] or 'Aún sin evaluación'} · "
            f"{record['folio'] or 'Sin folio verificado'}\n"
            "Orden y giro son temporales hasta exportar otro PDF."
        )

    def choose_document(event=None):
        selection=files.selection()
        if not selection:return
        sha=selection[0]
        doc=app.evidence.document(sha)
        state["sha"]=sha
        state["order"]=list(range(doc["paginas"]))
        state["rotations"]={}
        refresh_rows()

    def move(direction):
        selected=current_page()
        if selected is None:return
        order=state["order"]
        i=order.index(selected)
        other=i+direction
        if 0<=other<len(order):
            order[i],order[other]=order[other],order[i]
            refresh_rows(selected)

    def rotate(angle):
        idx=current_page()
        if idx is None:return
        state["rotations"][idx]=(
            state["rotations"].get(idx,0)+angle)%360
        refresh_rows(idx)

    def export_copy(selected_only=False):
        doc=current_doc()
        if doc is None:return
        selected={int(i) for i in pages.selection()}
        order=([i for i in state["order"] if i in selected]
               if selected_only else state["order"])
        if not order:
            messagebox.showinfo("Páginas","Selecciona las páginas que quieres extraer.",
                                parent=app.window)
            return
        output=filedialog.asksaveasfilename(
            parent=app.window,defaultextension=".pdf",
            initialfile=("Paginas_extraidas.pdf" if selected_only else
                         "Documento_organizado.pdf"),
            filetypes=[("PDF","*.pdf")])
        if not output:return
        try:
            create_organized_pdf(Path(doc["ruta"]),Path(output),
                                 order,state["rotations"])
        except (OSError,ValueError,ImportError) as exc:
            messagebox.showerror("No se pudo exportar",str(exc),parent=app.window)
            return
        app.feedback.set("PDF derivado guardado: "+output)
        messagebox.showinfo(
            "PDF listo","Se creó una copia; el PDF original no se modificó.",
            parent=app.window)

    def split_evaluations():
        doc=current_doc()
        if doc is None:return
        folder=filedialog.askdirectory(
            parent=app.window,title="Carpeta para páginas por evaluación")
        if not folder:return
        details=app.evidence.pages(state["sha"])
        groups={}
        for row in details:
            key=row["sesion_id"] or "SIN_IDENTIFICAR"
            groups.setdefault(key,[]).append(row["pagina"]-1)
        try:
            for key,indices in groups.items():
                dest=Path(folder)/(state["sha"][:12]+"_"+key+".pdf")
                if dest.exists():
                    raise ValueError(
                        f"{dest.name} ya existe. Elige otra carpeta para "
                        "no sobrescribir un documento anterior.")
                create_organized_pdf(Path(doc["ruta"]),dest,indices)
        except (OSError,ValueError,ImportError) as exc:
            messagebox.showerror("No se pudo separar",str(exc),
                                 parent=app.window)
            return
        messagebox.showinfo(
            "Separación completa",
            f"Se crearon {len(groups)} PDF derivados por evaluación/pendientes. "
            "Ningún original ni resultado se modificó.",
            parent=app.window)

    def manual_link():
        idx=current_page()
        if idx is None:return
        record=app.evidence.pages(state["sha"])[idx]
        if record["sesion_id"] is not None:
            messagebox.showwarning(
                "Hoja ya vinculada",
                "Esta hoja ya tiene una evaluación asignada; revísala "
                "desde Historial, sin reemplazar su vínculo.",
                parent=app.window)
            return
        sessions=[s for s in app.store.sessions()
                  if s["cantidad_participantes"]>0]
        if not sessions:
            messagebox.showinfo("Sin aplicaciones",
                                "Todavía no hay aplicaciones con folios.",
                                parent=app.window)
            return
        popup=tk.Toplevel(app.window)
        popup.title("Vincular página sin QR · sin calificar")
        popup.geometry("520x390")
        popup.transient(app.window)
        popup.grab_set()
        frame=tk.Frame(popup,padx=18,pady=14)
        frame.pack(fill="both",expand=True)
        tk.Label(frame,text=f"Página {idx+1} · QR no identificado",
                 font=("Segoe UI",12,"bold")).pack(anchor="w")
        tk.Label(frame,text="Selecciona la aplicación y el participante "
                 "comprobando ID y folio impresos. El enlace NO calcula notas.",
                 wraplength=450,justify="left").pack(anchor="w",pady=8)
        options=[f"{row['nombre_evaluacion'] or row['titulo']} · "
                 f"{row['id']}" for row in sessions]
        choice=tk.StringVar(value=options[0])
        ttk.Combobox(frame,textvariable=choice,values=options,
                     state="readonly",width=54).pack(fill="x",pady=6)
        people_var=tk.StringVar()
        people_box=ttk.Combobox(frame,textvariable=people_var,
                                state="readonly",width=54)
        people_box.pack(fill="x",pady=6)
        reviewer=tk.StringVar(value="Evaluador")
        reason=tk.StringVar(value="")
        tk.Label(frame,text="Revisor").pack(anchor="w")
        ttk.Entry(frame,textvariable=reviewer).pack(fill="x")
        tk.Label(frame,text="Motivo y cotejo con hoja física").pack(anchor="w")
        ttk.Entry(frame,textvariable=reason).pack(fill="x",pady=3)
        people_lookup={}

        def load_people(event=None):
            selected=sessions[options.index(choice.get())]
            people=app.store.session(selected["id"])["personal"]
            people_lookup.clear()
            labels=[]
            for p in people:
                label=f"{p['nombre']} · ID {p['id']} · Folio {p['folio']}"
                labels.append(label)
                people_lookup[label]=p
            people_box.configure(values=labels)
            people_var.set(labels[0] if labels else "")

        choice.trace_add("write",lambda *_:load_people())
        load_people()
        work=Queue()
        def save_link():
            selected=sessions[options.index(choice.get())]
            person=people_lookup.get(people_var.get())
            if person is None or not reason.get().strip():
                messagebox.showwarning(
                    "Faltan datos","Selecciona participante y escribe el motivo.",
                    parent=popup)
                return
            btn.configure(state="disabled")
            def background():
                try:
                    sheet_id=app.evidence.link_manual(
                        state["sha"],idx+1,selected["id"],person["id"],
                        person["folio"],reviewer.get(),reason.get())
                    work.put((True,sheet_id))
                except Exception as exc:
                    work.put((False,str(exc)))
            Thread(target=background,daemon=True).start()
            def poll():
                try:
                    success,value=work.get_nowait()
                except Empty:
                    if popup.winfo_exists():popup.after(120,poll)
                    return
                if success:
                    popup.destroy()
                    refresh_rows(idx)
                    app.feedback.set("Hoja vinculada para revisión: "+value)
                    messagebox.showinfo(
                        "Identificada",
                        "La página quedó asociada. En Revisión debes capturar "
                        "las respuestas; aún NO tiene nota definitiva.",
                        parent=app.window)
                else:
                    btn.configure(state="normal")
                    messagebox.showerror(
                        "No se pudo identificar",value,parent=popup)
            popup.after(120,poll)
        btn=ttk.Button(frame,text="Vincular sin calificar",command=save_link)
        btn.pack(anchor="w",pady=12)

    def reprocess():
        doc=current_doc()
        if doc is None:return
        path=Path(doc["ruta"])
        app.navigate("Escanear PDF")
        app._run_scan(path)

    for label,handler in [
        ("Subir",lambda:move(-1)),
        ("Bajar",lambda:move(1)),
        ("Girar 90°",lambda:rotate(90)),
        ("Girar -90°",lambda:rotate(-90)),
    ]:
        app._btn(bar,label,handler)
    for label,handler,primary in [
        ("Exportar copia organizada",lambda:export_copy(False),True),
        ("Extraer seleccionadas",lambda:export_copy(True),False),
        ("Separar por evaluación",split_evaluations,False),
    ]:
        app._btn(actions,label,handler,primary)
    for label,handler in [
        ("Identificar hoja",manual_link),
        ("Retomar escaneo",reprocess),
    ]:
        app._btn(actions_extra,label,handler)

    pages.bind("<<TreeviewSelect>>",preview)
    files.bind("<<TreeviewSelect>>",choose_document)
    files.selection_set(docs[0]["sha"])
    choose_document()
