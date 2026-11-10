/* Centro de control web OMR: sin CDN, cuentas ni secretos en localStorage. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const content = byId("content");
  const state = {user:null, apps:[], sid:null, view:"inicio", sheet:null,
                 lease:null, revision:0, question:1,
                 highlight:true, acetate:false, jobs:[], timer:null};
  const h = value => String(value ?? "").replace(/[&<>"']/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const cookie = name => {
    const item = document.cookie.split("; ").find(x => x.startsWith(name+"="));
    return item ? decodeURIComponent(item.slice(name.length+1)) : "";
  };
  function alertBox(message, error=false) {
    const elem=byId("notice");
    elem.textContent=String(message);
    elem.className=error?"error":"";
    elem.hidden=false;
    clearTimeout(state.timer);
    state.timer=setTimeout(()=>{elem.hidden=true;},7000);
  }
  async function api(path, opts={}) {
    const method=opts.method || "GET";
    const headers={"Accept":"application/json"};
    if(!["GET","HEAD"].includes(method))
      headers["X-CSRF-Token"]=cookie("omr_csrf");
    if(opts.body && !(opts.body instanceof FormData))
      headers["Content-Type"]="application/json";
    const response=await fetch("/api"+path,{method,headers,
      body:opts.body instanceof FormData?opts.body:
           opts.body?JSON.stringify(opts.body):undefined,credentials:"same-origin"});
    if(!response.ok){
      const obj=await response.json().catch(()=>({error:response.statusText}));
      throw Error(obj.error||obj.detail||"Error HTTP "+response.status);
    }
    return response.status===204?{}:await response.json();
  }
  function onButton(parent, selector, callback) {
    parent.querySelectorAll(selector).forEach(el=>el.addEventListener("click",callback));
  }
  function renderTitle(title,desc) {
    content.innerHTML='<div class="cardTitle"><div><h1>'+h(title)+'</h1><p>'+h(desc)+'</p></div></div>';
  }
  function optionList(items,valueKey="id",textKey="nombre",value=state.sid) {
    return items.map(x=>'<option value="'+h(x[valueKey])+'"'+
      (x[valueKey]===value?' selected':'')+'>'+h(x[textKey])+'</option>').join("");
  }
  function isAdmin(){return state.user?.rol==="admin";}
  function canUpload(){return ["admin","coordinador"].includes(state.user?.rol);}
  function canReview(){return ["admin","coordinador","capturista"].includes(state.user?.rol);}
  function canExport(){return ["admin","coordinador"].includes(state.user?.rol);}
  async function refreshApps(){
    state.apps=await api("/applications");
    if(!state.apps.some(x=>x.id===state.sid))
      state.sid=state.apps[0]?.id||null;
  }
  function setLoggedIn(me){
    state.user=me;
    byId("authPanel").hidden=true;
    byId("workspace").hidden=false;
    byId("logout").hidden=false;
    byId("identity").textContent=me.nombre+" · "+(me.rol==="capturista"?"Auxiliar de calificación":me.rol==="admin"?"Administrador":me.rol);
    document.querySelectorAll(".nav [data-view]").forEach(b=>{
      b.hidden=((b.dataset.view==="usuarios"||b.dataset.view==="biblioteca"||
                 b.dataset.view==="bandeja")&&!isAdmin())||
               (b.dataset.view==="escaneo"&&!canUpload())||
               (b.dataset.view==="resultados"&&
                !["admin","coordinador","auditor"].includes(me.rol));
    });
  }
  async function boot(){
    try{
      const me=await api("/me");
      setLoggedIn(me.usuario);
      if(me.usuario.cambiar_clave) await showChangePassword();
      else {await refreshApps();await navigate("inicio");}
    }catch{
      const status=await api("/setup/status").catch(()=>({necesita_configuracion:false}));
      byId("setupFields").hidden=!status.necesita_configuracion;
      byId("authTitle").textContent=status.necesita_configuracion?
        "Configurar administrador":"Entrar al sistema";
      byId("authSubmit").textContent=status.necesita_configuracion?
        "Crear administrador":"Iniciar sesión";
      byId("authPanel").hidden=false;byId("workspace").hidden=true;
    }
  }
  byId("authForm").addEventListener("submit",async evt=>{
    evt.preventDefault();
    const username=byId("username").value.trim();
    const password=byId("password").value;
    try {
      if(!byId("setupFields").hidden){
        await api("/setup",{method:"POST",body:{
          token:byId("setupToken").value,usuario:username,
          nombre:byId("setupName").value,password}});
        alertBox("Administrador creado. Ahora inicia sesión.");
        byId("setupFields").hidden=true;
        byId("authTitle").textContent="Entrar al sistema";
        byId("authSubmit").textContent="Iniciar sesión";
      }else{
        await api("/login",{method:"POST",body:{usuario:username,password}});
        await boot();
      }
    }catch(e){alertBox(e.message,true);}
  });
  byId("logout").addEventListener("click",async()=>{
    try{await api("/logout",{method:"POST"});}catch{}
    window.location.reload();
  });
  async function showChangePassword(){
    renderTitle("Cambiar contraseña","La contraseña temporal debe reemplazarse antes de trabajar.");
    content.innerHTML+='<form id="changePassword" class="panel">'+
      '<label>Contraseña actual<input name="old" type="password" required></label>'+
      '<label>Nueva contraseña (mínimo 12 caracteres)<input name="new" type="password" minlength="12" required></label>'+
      '<button class="primary">Cambiar y volver a entrar</button></form>';
    byId("changePassword").onsubmit=async e=>{
      e.preventDefault();
      try{await api("/change-password",{method:"POST",body:{
        anterior:e.target.old.value,nueva:e.target.new.value}});
        alertBox("Contraseña actualizada. Inicia sesión de nuevo.");
        window.location.reload();
      }catch(err){alertBox(err.message,true);}
    };
  }
  async function navigate(view){
    if(state.user?.cambiar_clave){await showChangePassword();return;}
    state.view=view;
    document.querySelectorAll(".nav [data-view]").forEach(b=>
      b.classList.toggle("active",b.dataset.view===view));
    try{
      if(view==="inicio")return await overview();
      if(view==="aplicaciones")return await applications();
      if(view==="revision")return await reviewQueue();
      if(view==="escaneo")return await scanner();
      if(view==="biblioteca")return await library();
      if(view==="bandeja")return await documents();
      if(view==="resultados")return await results();
      if(view==="usuarios")return await users();
    }catch(err){renderTitle("No se pudo abrir la sección",err.message);alertBox(err.message,true);}
  }
  document.querySelectorAll(".nav [data-view]").forEach(b=>b.onclick=()=>navigate(b.dataset.view));
  async function overview(){
    await refreshApps();
    const pend=state.apps.reduce((n,x)=>n+x.hojas_pendientes,0);
    const total=state.apps.reduce((n,x)=>n+x.cantidad_participantes,0);
    renderTitle("Panel de operación","Una sola base central. Toda hoja conserva su aplicación, folio y evidencia.");
    content.innerHTML+='<div class="kpiList">'+[
      ["Aplicaciones",state.apps.length],["Folios emitidos",total],
      ["Hojas por revisar",pend],["Con sesión QR",state.apps.filter(x=>x.cantidad_participantes).length]
    ].map(x=>'<div class="panel"><div class="metric">'+x[1]+'</div><div class="muted">'+x[0]+'</div></div>').join("")+'</div>'+
    '<div class="panel"><h2>¿Qué necesitas hacer?</h2><div class="actions">'+
    '<button class="primary" data-go="revision">Tomar siguiente hoja</button>'+
    '<button class="secondary" data-go="aplicaciones">Ver aplicaciones</button>'+
    (canUpload()?'<button class="ghost" data-go="escaneo">Cargar escaneo</button>':"")+
    '</div><p class="hint">Servidor piloto: no hay conexión activa con licencias de producción. No usar por Internet público.</p></div>';
    onButton(content,"[data-go]",e=>navigate(e.currentTarget.dataset.go));
  }
  async function applications(){
    await refreshApps();
    renderTitle("Aplicaciones de evaluación",
      "Una aplicación conserva sus QR, participantes y escaneos de distintas jornadas.");
    content.innerHTML+='<div class="panel"><div class="tableWrap"><table><thead><tr><th>Evaluación</th><th>Modo</th><th>Participantes</th><th>Hojas</th><th>Pendientes</th><th>Acciones</th></tr></thead><tbody>'+
      (state.apps.length?state.apps.map(x=>'<tr><td><b>'+h(x.nombre_evaluacion||x.titulo)+'</b><br><code>'+h(x.id)+'</code></td>'+
        '<td>'+h(x.modo)+'</td><td>'+x.cantidad_participantes+'</td><td>'+x.hojas_escaneadas+'</td><td>'+x.hojas_pendientes+
        '</td><td><button class="secondary" data-sid="'+h(x.id)+'">Abrir</button></td></tr>').join(""):
        '<tr><td colspan="6">Todavía no hay aplicaciones.</td></tr>')+
    '</tbody></table></div></div>'+
    (state.sid?'<div class="panel"><h3>Aplicación seleccionada: '+h(state.sid)+'</h3><div id="appFiles" class="actions"></div>'+
      '<div class="actions"><button data-go="revision" class="primary">Revisar hojas</button>'+
      '<button data-go="resultados" class="secondary">Resultados</button></div></div>':"");
    onButton(content,"[data-sid]",async e=>{state.sid=e.currentTarget.dataset.sid;await applications();});
    onButton(content,"[data-go]",e=>navigate(e.currentTarget.dataset.go));
    if(state.sid && canExport()){
      const base="/api/applications/"+encodeURIComponent(state.sid)+"/files/";
      byId("appFiles").innerHTML=["Cuadernillo.pdf","Hoja_respuestas.pdf","Acetato_clave.pdf",
        "Paquetes_individuales.zip"].map(n=>
        '<a class="ghost" href="'+base+encodeURIComponent(n)+'">'+h(n)+'</a>').join("");
    }
  }
  async function reviewQueue(){
    await refreshApps();
    renderTitle("Corrección compartida","Cada capturista reclama una hoja. Dos usuarios nunca pueden guardar sobre la misma versión.");
    if(!state.sid){
      content.innerHTML+='<div class="panel empty">Todavía no hay aplicaciones con QR.</div>';return;
    }
    const opts=state.apps.map(x=>({id:x.id,nombre:x.nombre_evaluacion||x.titulo}));
    content.innerHTML+='<div class="panel"><label>Evaluación<select id="reviewApp">'+
      optionList(opts)+'</select></label><div class="actions"><button class="primary" id="claimNext">Tomar siguiente hoja disponible</button></div>'+
      '<div id="queueArea"></div></div><div id="sheetArea"></div>';
    byId("claimNext").onclick=async()=>{
      try{
        const claim=await api("/applications/"+state.sid+"/claim-next",{method:"POST"});
        state.lease=claim.lease;state.revision=claim.revision;
        state.sheet=await api("/sheets/"+claim.hoja_id);
        const first=state.sheet.dudas.find(x=>typeof x.pregunta==="number");
        state.question=first?.pregunta||1;
        await renderSheet();await queueTable();
      }catch(err){alertBox(err.message,true);}
    };
    byId("reviewApp").onchange=async e=>{
      state.sid=e.target.value;state.sheet=null;state.lease=null;await reviewQueue();
    };
    await queueTable();
  }
  async function queueTable(){
    const list=await api("/applications/"+state.sid+"/sheets");
    const area=byId("queueArea");
    if(!area)return;
    area.innerHTML='<p class="muted">Hojas que requieren intervención: <b>'+list.length+'</b></p>'+
      '<div class="tableWrap"><table><thead><tr><th>Folio</th><th>Participante</th><th>Estado</th><th>Dudas</th><th>Acción</th></tr></thead><tbody>'+
      (list.length?list.map(x=>'<tr><td><code>'+h(x.folio||"Sin QR")+'</code></td>'+
      '<td>'+h(x.nombre)+'</td><td><span class="tag '+(x.ocupada_por_otro?"warn":"")+'">'+
      h(x.ocupada_por_otro?"Ocupada":"Disponible")+'</span></td><td>'+x.dudas+
      '</td><td><button class="secondary" data-sheet="'+h(x.id)+'"'+
      (x.ocupada_por_otro||x.estado==="duplicado"?' disabled':'')+
      '>Revisar</button></td></tr>').join(""):
      '<tr><td colspan="5">No hay hojas pendientes de corrección.</td></tr>')+
      '</tbody></table></div>';
    onButton(area,"[data-sheet]",async e=>{
      try{await openSheet(e.currentTarget.dataset.sheet);}
      catch(err){alertBox(err.message,true);await queueTable();}
    });
  }
  async function openSheet(id){
    if(!canReview())throw Error("No tienes permiso de captura.");
    const claim=await api("/sheets/"+id+"/claim",{method:"POST"});
    state.lease=claim.lease;state.revision=claim.revision;
    state.sheet=await api("/sheets/"+id);
    const q=state.sheet.dudas.find(x=>typeof x.pregunta==="number");
    state.question=q?.pregunta||1;
    await renderSheet();
  }
  function showSheetVisual(){
    const sheet=state.sheet, img=byId("sheetImage");
    if(!sheet||!img)return;
    const base="/api/sheets/"+encodeURIComponent(sheet.id);
    const overlay=state.highlight||state.acetate;
    img.onerror=()=>{
      // Si el PNG original está disponible, no dejar un recuadro roto.
      if(overlay){img.onerror=null;img.src=base+"/image";}
      else alertBox("No se pudo mostrar la imagen de la hoja.",true);
    };
    img.src=overlay?
      base+"/overlay?pregunta="+state.question+
      "&resaltar="+state.highlight+"&acetato="+state.acetate+
      "&v="+state.revision:base+"/image";
  }
  async function renderSheet(){
    const sheet=state.sheet;if(!sheet)return;
    const area=byId("sheetArea");if(!area)return;
    const q=sheet.preguntas[state.question-1];
    const value=sheet.respuestas[state.question-1]||"BLANCO";
    const questions=sheet.preguntas.map(item=>
      '<option value="'+item.numero+'"'+(item.numero===state.question?" selected":"")+'>'+
      String(item.numero).padStart(2,"0")+" · "+h(item.pregunta.slice(0,90))+"</option>").join("");
    area.innerHTML='<div class="scanBox">'+
      '<div class="panel"><h3>Hoja física y marcas</h3><p class="hint">El visor nunca cambia la evidencia original. El contorno naranja señala la pregunta, las marcas verdes corresponden al acetato.</p>'+
      '<img class="scanImage" alt="Hoja escaneada" id="sheetImage">'+
      '<div class="actions overlayControls"><label class="check"><input type="checkbox" id="highlightToggle" '+
      (state.highlight?'checked':'')+'> Resaltar reactivo</label>'+
      (["admin","coordinador"].includes(state.user?.rol)?
      '<label class="check"><input type="checkbox" id="acetateToggle" '+
      (state.acetate?'checked':'')+'> Superponer acetato</label>':'')+
      '</div></div>'+
      '<div class="panel"><div class="cardTitle"><div><h3>Corregir respuesta</h3>'+
      '<p>Pregunta seleccionada · versión '+state.revision+'</p></div><span class="tag warn">'+
      h(sheet.estado)+'</span></div>'+
      '<div class="questionBox"><b>Participante:</b> '+h(sheet.participante)+
      ' · <b>Folio:</b> '+h(sheet.folio||"Sin identificar")+'<p class="hint">'+
      h(sheet.evaluacion)+' · Biblioteca: '+h(sheet.biblioteca)+
      (sheet.revision_biblioteca?' · Revisión '+h(sheet.revision_biblioteca):'')+
      '</p></div><label>Reactivo del examen<select id="questionSelect">'+questions+'</select></label>'+
      '<div class="questionBox"><b>'+h(q?.tema||"")+'</b><br>'+h(q?.pregunta||"")+'</div>'+
      '<p class="muted">Lectura automática: <b>'+h(value)+'</b> · dudas restantes: '+sheet.dudas.length+'</p>'+
      '<label>Decisión A/B/C/D o BLANCO<select id="decision">'+
      ["A","B","C","D","BLANCO"].map(c=>'<option '+(c===value?'selected':'')+'>'+c+'</option>').join("")+
      '</select></label><label>Justificación<textarea id="reason" placeholder="Ej. Dos marcas, se considera BLANCO conforme a la política"></textarea></label>'+
      '<div class="actions"><button class="primary" id="saveChoice">Guardar decisión</button>'+
      '<button class="secondary" id="captureWhole">Captura completa</button>'+
      '<button class="ghost" id="releaseSheet">Liberar hoja</button></div>'+
      '<p class="hint">No elijas la respuesta solo por el acetato: comprueba la marca física. Toda decisión deja auditoría.</p></div></div>';
    byId("questionSelect").onchange=e=>{
      state.question=Number(e.target.value);renderSheet();
    };
    byId("highlightToggle").onchange=e=>{
      state.highlight=e.target.checked;showSheetVisual();
    };
    if(byId("acetateToggle"))byId("acetateToggle").onchange=e=>{
      state.acetate=e.target.checked;showSheetVisual();
    };
    showSheetVisual();
    byId("saveChoice").onclick=async()=>{
      try{
        const result=await api("/sheets/"+sheet.id+"/decisions",{
          method:"PUT",body:{lease:state.lease,expected_revision:state.revision,
            cambios:[{pregunta:state.question,decision:byId("decision").value}],
            motivo:byId("reason").value}});
        state.revision=result.revision;
        alertBox("Corrección guardada con auditoría.");
        state.sheet=await api("/sheets/"+sheet.id);
        await renderSheet();
        await queueTable();
      }catch(err){alertBox(err.message,true);}
    };
    byId("captureWhole").onclick=async()=>{
      const area=byId("sheetArea");
      if(!area)return;
      const questions=state.sheet.preguntas,original=state.sheet.respuestas;
      const form=document.createElement("div");
      form.className="panel";
      form.innerHTML='<h3>Captura íntegra auditada · '+questions.length+' preguntas</h3>'+
        '<p class="hint">Es obligatorio revisar TODOS los reactivos. Los que no tengan decisión permanecen como SIN REVISAR.</p>'+
        questions.map((q,i)=>{
          const previous=original[i];
          const unresolved=state.sheet.dudas.some(x=>x.pregunta===i+1);
          const current=unresolved?"SIN REVISAR":previous||"SIN REVISAR";
          return '<div class="inline"><div><label>'+String(i+1).padStart(2,"0")+' · '+
            h(q.pregunta)+'</label></div><div><select data-q="'+(i+1)+'">'+
            ["SIN REVISAR","A","B","C","D","BLANCO"].map(opt=>
              '<option'+(opt===current?" selected":"")+'>'+opt+'</option>').join("")+
            '</select></div></div>';
        }).join("")+
        '<label>Justificación de la captura completa<textarea id="fullReason" required placeholder="Cotejo físico de todas las marcas"></textarea></label>'+
        '<div class="actions"><button class="primary" id="submitFull">Guardar todas las decisiones</button>'+
        '<button class="ghost" id="cancelFull">Cancelar</button></div>';
      area.append(form);form.scrollIntoView({behavior:"smooth",block:"start"});
      form.querySelector("#cancelFull").onclick=()=>form.remove();
      form.querySelector("#submitFull").onclick=async()=>{
        const changes=[...form.querySelectorAll("[data-q]")].map(field=>({
          pregunta:Number(field.dataset.q),decision:field.value}));
        if(changes.some(x=>x.decision==="SIN REVISAR")){
          alertBox("Todas las preguntas requieren una decisión.",true);return;
        }
        try{
          const result=await api("/sheets/"+state.sheet.id+"/decisions",{
            method:"PUT",body:{lease:state.lease,
              expected_revision:state.revision,cambios:changes,
              motivo:form.querySelector("#fullReason").value}});
          state.revision=result.revision;
          alertBox("Hoja completa auditada y guardada.");
          state.sheet=await api("/sheets/"+state.sheet.id);
          await renderSheet();await queueTable();
        }catch(err){alertBox(err.message,true);}
      };
    };
    byId("releaseSheet").onclick=async()=>{
      try{await api("/sheets/"+sheet.id+"/release",{
          method:"POST",body:{lease:state.lease}});
        state.lease=null;state.sheet=null;area.innerHTML="";
        await queueTable();
      }catch(err){alertBox(err.message,true);}
    };
  }
  async function scanner(){
    if(!canUpload())throw Error("No tienes permisos de importación.");
    renderTitle("Importar escaneos","Los PDF se archivan completos; Cabos y Checadores se separan por QR y las hojas desconocidas se conservan.");
    content.innerHTML+='<form class="panel" id="scanForm"><h2>Nuevo lote de escáner</h2>'+
      '<label>PDF multipágina de Xerox o cualquier escáner<input type="file" id="scanPdf" accept=".pdf,application/pdf" required></label>'+
      '<button class="primary">Archivar y reconocer</button>'+
      '<p class="hint">El motor trabaja en segundo plano. Puedes salir de esta pantalla y consultar el ID de trabajo.</p></form>'+
      '<div class="panel"><h3>Estado del procesamiento</h3><div id="scanProgress" class="muted">Sin trabajos activos.</div></div>';
    byId("scanForm").onsubmit=async e=>{
      e.preventDefault();const f=byId("scanPdf").files[0];
      if(!f)return;const body=new FormData();body.append("file",f);
      try{const job=await api("/scans",{method:"POST",body});
        alertBox("Documento recibido. ID: "+job.trabajo_id);
        pollJob(job.trabajo_id);
      }catch(err){alertBox(err.message,true);}
    };
  }
  async function pollJob(jobId){
    const el=byId("scanProgress");
    if(!el)return;
    try{
      const job=await api("/jobs/"+jobId);
      el.innerHTML='<p>Trabajo <code>'+h(job.id)+'</code> · <b>'+h(job.estado)+
        '</b></p><pre>'+h(JSON.stringify(job.resultado,null,2))+'</pre>'+
        (job.error?'<p class="tag bad">'+h(job.error)+'</p>':'');
      if(["pendiente","procesando"].includes(job.estado) && state.view==="escaneo")
        setTimeout(()=>pollJob(jobId),1600);
      if(job.estado==="terminado")await refreshApps();
    }catch(err){el.textContent=err.message;}
  }
  async function library(){
    if(!isAdmin())throw Error("Solo el administrador crea evaluaciones.");
    renderTitle("Diseñar e imprimir",
      "Las modalidades Normal y Ecológico conservan las hojas y el acetato originales.");
    await window.OMRDesigner.start({api,alertBox,root:content,
      onCreated:async sid=>{state.sid=sid;await refreshApps();}});
  }
  async function documents(){
    if(!isAdmin())throw Error("Solo el administrador ve originales mezclados.");
    const docs=await api("/documents");
    renderTitle("Bandeja documental","Originales conservados por SHA-256, incluidos PDF mezclados y QR ilegibles.");
    content.innerHTML+='<div class="panel"><div class="tableWrap"><table><thead><tr><th>Archivo</th><th>Páginas</th><th>Pendientes</th><th>Ingresos</th><th></th></tr></thead><tbody>'+
      (docs.length?docs.map(d=>'<tr><td>'+h(d.nombre)+'<br><code>'+h(d.sha.slice(0,18))+'…</code></td>'+
      '<td>'+d.paginas+'</td><td>'+d.pendientes+'</td><td>'+d.veces_recibido+'</td>'+
      '<td><button class="secondary" data-doc="'+h(d.sha)+'">Ver páginas</button></td></tr>').join(""):
      '<tr><td colspan="5">Todavía no hay PDF archivados.</td></tr>')+
      '</tbody></table></div></div><div id="documentPages"></div>';
    onButton(content,"[data-doc]",async e=>{
      try{
        const digest=e.currentTarget.dataset.doc;
        const pages=await api("/documents/"+digest+"/pages");
        const original=pages.filter(p=>p.estado==="pendiente");
        byId("documentPages").innerHTML='<div class="panel"><h3>Páginas del documento</h3>'+
          '<div class="actions">'+pages.map(p=>
            '<button class="ghost" data-num="'+p.pagina+'">Página '+(p.pagina+1)+
            ' · '+h(p.estado)+'</button>').join("")+'</div>'+
          '<p class="hint" id="documentHint">Selecciona una página para visualizarla.</p>'+
          '<div class="actions"><button type="button" class="secondary" id="retryDocImage" hidden>Reintentar imagen</button></div>'+
          '<img id="documentImg" class="scanImage" alt="Vista de la página seleccionada">'+
          '<div id="manualLinkArea"></div></div>';
        let selected=null;
        function showDoc(page){
          selected=page;
          const image=byId("documentImg");
          image.alt="Evidencia de la página "+(page+1);
          image.onerror=()=>{
            byId("documentHint").textContent="No se cargó la página; puedes volver a intentar.";
            byId("retryDocImage").hidden=false;
          };
          image.onload=()=>{
            byId("documentHint").textContent="Página "+(page+1)+" · PDF original archivado.";
            byId("retryDocImage").hidden=true;
          };
          image.src="/api/documents/"+digest+"/pages/"+page+"/image";
          const entry=pages.find(p=>p.pagina===page);
          const target=byId("manualLinkArea");
          target.innerHTML=entry?.estado==="pendiente"?
            '<hr class="hr"><h3>Segunda modalidad: corrección manual con acetato</h3>'+
            '<p>Esta página no tiene un QR verificable. El administrador debe comprobar el nombre y seleccionar el cuestionario de la biblioteca. Se generará un folio <b>interno nuevo</b>, sin modificar el PDF ni atribuirle una identidad histórica.</p>'+
            '<button type="button" class="secondary" id="prepareManual">Identificar manualmente y seleccionar examen</button>':'';
          if(byId("prepareManual"))byId("prepareManual").onclick=()=>openManualForm(page);
        }
        async function openManualForm(page){
          try{
            const library=await api("/library");
            const target=byId("manualLinkArea");
            if(!library.length){
              target.innerHTML='<div class="panel">Primero importa la plantilla de preguntas en Generar exámenes.</div>';
              return;
            }
            target.innerHTML='<hr class="hr"><form class="panel" id="manualBindForm">'+
              '<h3>Vincular página '+(page+1)+' a la biblioteca</h3>'+
              '<p class="hint">Una aplicación de captura manual por hoja. Sin firma QR original, las 20 respuestas deberán verificarse una por una; ningún acierto se asigna automáticamente.</p>'+
              '<label>Cuestionario aprobado<select name="cuestionario_id" required>'+
              library.map(q=>'<option value="'+h(q.id)+'">'+h(q.nombre)+' · '+q.total+' reactivos · rev. '+q.revision+'</option>').join("")+
              '</select></label><div class="cols">'+
              '<label>Nombre escrito/verificado<input name="nombre" required maxlength="130" placeholder="Nombre de la hoja"></label>'+
              '<label>ID de la persona<input name="id" required maxlength="64" placeholder="ID sin inventar ceros"></label>'+
              '<label>Papel<select name="papel"><option>Carta</option><option>A4</option><option>Oficio</option></select></label>'+
              '<label>Grupo (opcional)<input name="grupo" maxlength="80"></label>'+
              '</div><label>Justificación de la vinculación<textarea name="motivo" required minlength="8" placeholder="Verifiqué el nombre/ID de la hoja física contra el registro correspondiente."></textarea></label>'+
              '<div class="actions"><button class="primary">Crear folio interno y abrir captura manual</button>'+
              '<button type="button" class="ghost" id="cancelManual">Cancelar</button></div></form>';
            byId("cancelManual").onclick=()=>showDoc(page);
            byId("manualBindForm").onsubmit=async event=>{
              event.preventDefault();
              const form=event.target,button=form.querySelector('button.primary');
              const data=Object.fromEntries(new FormData(form).entries());
              button.disabled=true;
              try{
                const result=await api("/documents/"+digest+"/pages/"+page+"/manual",
                  {method:"POST",body:data});
                state.sid=result.sesion_id;
                await refreshApps();
                target.innerHTML='<div class="panel"><h3>Folio manual creado</h3>'+
                  '<p><b>'+h(result.participante)+'</b> · <code>'+h(result.folio)+'</code></p>'+
                  '<p>Cuestionario: '+h(result.biblioteca)+' · revisión '+h(result.revision)+
                  '. Es obligatorio confirmar todas las respuestas antes de calificar.</p>'+
                  '<button class="primary" id="goManualReview">Abrir revisión de esta aplicación</button></div>';
                byId("goManualReview").onclick=()=>navigate("revision");
                alertBox("Hoja vinculada a una nueva aplicación de captura manual.");
              }catch(err){alertBox(err.message,true);button.disabled=false;}
            };
          }catch(err){alertBox(err.message,true);}
        }
        byId("retryDocImage").onclick=()=>{
          if(selected!==null){byId("documentImg").src="/api/documents/"+digest+
              "/pages/"+selected+"/image?retry="+Date.now();}
        };
        onButton(byId("documentPages"),"[data-num]",ev=>showDoc(Number(ev.currentTarget.dataset.num)));
        if(pages.length)showDoc(pages[0].pagina);
      }catch(err){alertBox(err.message,true);}
    });
  }
  async function results(){
    await refreshApps();
    renderTitle("Resultados y entregables","Resultados por aplicación, sin mezclar evidencias de otras evaluaciones.");
    if(!state.sid){content.innerHTML+='<div class="panel empty">No hay aplicación.</div>';return;}
    const opts=state.apps.map(x=>({id:x.id,nombre:x.nombre_evaluacion||x.titulo}));
    content.innerHTML+='<div class="panel"><label>Evaluación<select id="resultsApp">'+optionList(opts)+'</select></label>'+
      '<div id="resultsBody"></div></div>';
    byId("resultsApp").onchange=async e=>{state.sid=e.target.value;await results();};
    const report=await api("/applications/"+state.sid+"/results");
    byId("resultsBody").innerHTML='<div class="kpiList">'+[
      ["Validados",report.validados],["Pendientes",report.pendientes],
      ["Ausentes",report.ausentes],["Promedio",report.promedio===null?"—":report.promedio+"%"]
    ].map(x=>'<div class="panel"><div class="metric">'+h(x[1])+'</div><div class="muted">'+h(x[0])+'</div></div>').join("")+'</div>'+
      (canExport()?'<div class="actions"><a class="secondary" href="/api/applications/'+h(state.sid)+
       '/export">ZIP oficial</a><a class="ghost" href="/api/applications/'+h(state.sid)+
       '/export?internal=true">Expediente interno y evidencias</a></div>':'')+
      '<div class="tableWrap"><table><thead><tr><th>Folio</th><th>Nombre</th><th>Aciertos</th><th>Estado</th><th></th></tr></thead><tbody>'+
      report.participantes.map(p=>'<tr><td><code>'+h(p.folio)+'</code></td>'+
      '<td>'+h(p.nombre)+'</td><td>'+h(p.aciertos===null?"—":p.aciertos)+'</td>'+
      '<td>'+h(p.estado)+'</td><td>'+(canExport()?
        '<a class="listLink" href="/api/applications/'+h(state.sid)+
        '/participants/'+encodeURIComponent(p.id)+'/result">PDF individual</a>':'')+
      '</td></tr>').join("")+'</tbody></table></div>';
  }
  async function users(){
    if(!isAdmin())throw Error("Solo el administrador administra cuentas.");
    await refreshApps();const users=await api("/users");
    renderTitle("Usuarios y asignaciones","Una cuenta individual por capturista. Los permisos se validan en el servidor.");
    content.innerHTML+='<div class="cols"><form id="userForm" class="panel">'+
      '<h3>Crear usuario</h3><label>Usuario<input name="usuario" required></label>'+
      '<label>Nombre<input name="nombre" required></label>'+
      '<label>Contraseña temporal de al menos 12 caracteres<input type="password" name="password" minlength="12" required></label>'+
      '<label>Rol<select name="rol"><option value="auxiliar">Auxiliar de calificación</option>'+
      '<option value="admin">Administrador</option></select></label>'+
      '<button class="primary">Crear cuenta</button></form>'+
      '<form id="assignForm" class="panel"><h3>Asignar evaluación</h3>'+
      '<label>Usuario<select name="usuario_id">'+users.map(u=>
      '<option value="'+h(u.id)+'">'+h(u.nombre)+' · '+h(u.rol)+'</option>').join("")+
      '</select></label><label>Aplicación<select name="sesion_id">'+state.apps.map(a=>
      '<option value="'+h(a.id)+'">'+h(a.nombre_evaluacion||a.titulo)+'</option>').join("")+
      '</select></label><button class="secondary">Asignar acceso</button>'+
      '<p class="hint">No compartas usuarios ni contraseñas. Cada acción queda vinculada a una persona.</p></form></div>';
    byId("userForm").onsubmit=async e=>{
      e.preventDefault();const fd=new FormData(e.target);
      try{await api("/users",{method:"POST",body:Object.fromEntries(fd.entries())});
        alertBox("Cuenta creada.");await users();
      }catch(err){alertBox(err.message,true);}
    };
    byId("assignForm").onsubmit=async e=>{
      e.preventDefault();
      try{await api("/assignments",{method:"POST",
        body:Object.fromEntries(new FormData(e.target).entries())});
        alertBox("Evaluación asignada.");
      }catch(err){alertBox(err.message,true);}
    };
  }
  boot().catch(err=>alertBox(err.message,true));
})();
