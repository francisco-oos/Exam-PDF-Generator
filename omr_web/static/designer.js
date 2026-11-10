/* Diseñador web OMR: reutiliza biblioteca + preview PDF original. Sin CDN.
 * Sólo admin; el servidor vuelve a verificar TODOS los permisos.
 */
(() => {
  "use strict";
  const h = v => String(v ?? "").replace(/[&<>"']/g,
    s => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[s]));
  const sel = (root, q) => root.querySelector(q);
  const all = (root, q) => Array.from(root.querySelectorAll(q));
  let api, alertBox, root, onCreated, exams=[], draft=null, examId=null,
      previewURL=null, activeView="Cuadernillo", previewSeq=0,
      savedDesign=null, pendingLogo=null, previewTimer=null;

  const meta = (id, label, value, kind="text", extra="") =>
    '<label>'+h(label)+'<input data-meta="'+h(id)+'" type="'+kind+
    '" value="'+h(value)+'" '+extra+'></label>';
  const options = (items,value) => items.map(v=>
    '<option value="'+h(v)+'"'+(v===value?' selected':'')+'>'+h(v)+'</option>').join('');
  const choose = (id,label,values,value) =>
    '<label>'+h(label)+'<select data-meta="'+h(id)+'">'+
    options(values,value)+'</select></label>';

  function schedulePreview(){
    clearTimeout(previewTimer);
    previewTimer=setTimeout(()=>preview(),450);
  }
  function fileQuestion(q,i){
    return '<details class="questionEditor" data-question="'+i+'">'+
      '<summary><b>Pregunta '+(i+1)+'</b> · '+h(q.pregunta.slice(0,85))+
      (q.imagen?' · con imagen':'')+
      (q.pendingImage?' · imagen seleccionada sin guardar':'')+
      '</summary><div class="cols">'+
      meta('tema','Tema',q.tema)+meta('pregunta','Pregunta',q.pregunta)+
      '</div><div class="cols">'+
      'ABCD'.split('').map((letter,k)=>meta('opt'+k,'Opción '+letter,q.opciones[k])).join('')+
      '</div><div class="cols">'+
      choose('correcta','Respuesta correcta',['A','B','C','D'],q.correcta)+
      '<label>Imagen opcional PNG/JPG'+(q.imagen?
         ' · <a target="_blank" rel="noopener" href="/api/library/'+
           encodeURIComponent(examId)+'/images/'+encodeURIComponent(q.imagen)+'">Ver actual</a>':'')+
      '<input type="file" accept=".png,.jpg,.jpeg" data-image="'+i+'">'+
      (q.pendingImage?'<span class="hint">Pendiente: '+h(q.pendingImage.name)+'</span>':'')+
      '</label></div><div class="cols">'+
      meta('ancho_imagen_mm','Ancho foto (30–165 mm)',
        q.ancho_imagen_mm??106,'number','min="30" max="165" step="1"')+
      meta('alto_imagen_mm','Alto foto (15–90 mm)',
        q.alto_imagen_mm??62,'number','min="15" max="90" step="1"')+
      '<label>Alineación foto<select data-meta="alineacion_imagen">'+
      [['LEFT','Izquierda'],['CENTER','Centrada'],['RIGHT','Derecha']]
        .map(([value,label])=>'<option value="'+value+'"'+
          ((q.alineacion_imagen||'CENTER')===value?' selected':'')+'>'+label+'</option>')
        .join('')+'</select></label>'+
      '</div><p class="hint">El PDF conserva la proporción, sin deformar el dibujo.</p>'+
      (q.imagen?'<label class="check"><input type="checkbox" data-remove-image>Quitar imagen actual</label>':'')+
      '<div class="actions"><button type="button" class="ghost" data-remove-q="'+i+
      '">Eliminar pregunta</button></div></details>';
  }
  function readEditor(){
    const panel=sel(root,'#designerPanel');
    if(!draft||!panel)return;
    all(panel,'[data-meta]').filter(e=>!e.closest('[data-question]')).forEach(e=>{
      draft[e.dataset.meta]=e.value;
    });
    draft.quitarLogo=!!sel(panel,'#removeLogo')?.checked;
    const selectedLogo=sel(panel,'#designerLogo')?.files?.[0];
    if(selectedLogo){pendingLogo=selectedLogo;draft.quitarLogo=false;}
    all(panel,'[data-question]').forEach((row,i)=>{
      const q=draft.preguntas[i];
      all(row,'[data-meta]').forEach(e=>{
        const key=e.dataset.meta;
        if(key.startsWith('opt'))q.opciones[Number(key.slice(3))]=e.value;
        else q[key]=e.value;
      });
      q.quitarImagen=!!sel(row,'[data-remove-image]')?.checked;
      const image=sel(row,'[data-image]')?.files?.[0];
      if(image){q.pendingImage=image;q.quitarImagen=false;}
    });
  }
  function cleanPayload(){
    readEditor();
    return {
      nombre:draft.nombre,titulo:draft.titulo,empresa:draft.empresa,
      grupo:draft.grupo,subtitulo:draft.subtitulo,
      instrucciones:draft.instrucciones,papel:draft.papel,
      modo:draft.modo,letra:Number(draft.letra),
      color_titulo:draft.color_titulo,
      color_subtitulo:draft.color_subtitulo,
      color_respuestas:draft.color_respuestas,
      color_acetato:draft.color_acetato,
      quitar_logo:!!draft.quitarLogo&&!pendingLogo,
      logo_ancho_mm:Number(draft.logo_ancho_mm??23),
      preguntas:draft.preguntas.map(q=>({
        tema:q.tema,pregunta:q.pregunta,opciones:q.opciones,
        correcta:q.correcta,
        ancho_imagen_mm:Number(q.ancho_imagen_mm??106),
        alto_imagen_mm:Number(q.alto_imagen_mm??62),
        alineacion_imagen:q.alineacion_imagen||'CENTER',
        imagen:q.quitarImagen?null:q.sourceIndex
      }))
    };
  }
  function showEditor(){
    const panel=sel(root,'#designerPanel');
    if(!panel||!draft)return;
    panel.innerHTML='<h2>Diseñar cuestionario · revisión '+h(draft.revision)+'</h2>'+
      '<p class="hint">La edición queda en la biblioteca. Aplicaciones ya impresas mantienen su propia versión y QR.</p>'+
      '<div class="designerControls"><div class="cols">'+
      meta('nombre','Nombre en biblioteca',draft.nombre)+
      meta('titulo','Título del examen',draft.titulo)+
      meta('empresa','Empresa',draft.empresa)+
      meta('grupo','Área / grupo',draft.grupo)+
      meta('subtitulo','Subtítulo',draft.subtitulo)+
      '</div><label>Instrucciones<textarea data-meta="instrucciones">'+
      h(draft.instrucciones)+'</textarea></label>'+
      '<div class="cols">'+
      choose('modo','Modalidad',['normal','ecologico'],draft.modo)+
      choose('papel','Papel',['Carta','A4','Oficio'],draft.papel)+
      meta('letra','Tamaño de letra 8–12 pt',draft.letra,'number',
        'min="8" max="12" step="0.5"')+
      '</div><div class="cols">'+
      meta('color_titulo','Color título',draft.color_titulo,'color')+
      meta('color_subtitulo','Color subtítulo',draft.color_subtitulo,'color')+
      meta('color_respuestas','Tinta de respuestas',draft.color_respuestas,'color')+
      meta('color_acetato','Color acetato',draft.color_acetato,'color')+
      '</div><div class="cols"><label>Logotipo PNG/JPG'+
      (draft.logo?' · <a href="/api/library/'+encodeURIComponent(examId)+
       '/images/'+encodeURIComponent(draft.logo)+'" target="_blank" rel="noopener">Ver actual</a>':'')+
      '<input id="designerLogo" type="file" accept=".png,.jpg,.jpeg"></label>'+
      (pendingLogo?'<p class="hint">Logotipo pendiente: '+h(pendingLogo.name)+'</p>':'')+
      (draft.logo?'<label class="check"><input id="removeLogo" type="checkbox" '+
        (draft.quitarLogo?'checked':'')+'>Quitar logotipo</label>':'')+
      '</div><div class="cols">'+
      meta('logo_ancho_mm','Ancho logotipo (10–28 mm)',
        draft.logo_ancho_mm??23,'number','min="10" max="28" step="1"')+
      '</div><h3>Preguntas y respuestas</h3>'+
      '<p class="hint">Cada pregunta admite cuatro opciones, una respuesta correcta y una imagen. El acetato siempre usa esa clave.</p>'+
      '<div id="questionRows">'+draft.preguntas.map(fileQuestion).join('')+'</div>'+
      '<div class="actions"><button type="button" class="ghost" id="addQuestion">Añadir pregunta</button>'+
      '<button type="button" class="primary" id="saveDesign">Guardar diseño</button></div>'+
      '<p class="hint">La vista previa incluye temporalmente fotos y logo seleccionados; sólo Guardar diseño los conserva en la biblioteca.</p>'+
      '</div>';
    all(panel,'[data-remove-q]').forEach(button=>button.onclick=()=>{
      readEditor();
      if(draft.preguntas.length===1){alertBox('Necesitas conservar una pregunta.',true);return;}
      draft.preguntas.splice(Number(button.dataset.removeQ),1);showEditor();
    });
    sel(panel,'#addQuestion').onclick=()=>{
      readEditor();
      if(draft.preguntas.length>=100){alertBox('Máximo 100 preguntas.',true);return;}
      draft.preguntas.push({tema:'',pregunta:'',opciones:['','','',''],
        correcta:'A',imagen:null,sourceIndex:null,quitarImagen:false,
        pendingImage:null,ancho_imagen_mm:106,
        alto_imagen_mm:62,alineacion_imagen:'CENTER'});
      showEditor();
      all(panel,'.questionEditor').at(-1)?.setAttribute('open','');
    };
    sel(panel,'#saveDesign').onclick=()=>saveDesign();
    // Conservar archivos pendientes como File en el borrador, incluso
    // si "Añadir/Eliminar pregunta" reconstruye los inputs del DOM.
    all(panel,'[data-image]').forEach(input=>input.onchange=()=>{
      const q=draft.preguntas[Number(input.dataset.image)];
      if(input.files?.length){q.pendingImage=input.files[0];q.quitarImagen=false;
        const remove=sel(input.closest('[data-question]'),'[data-remove-image]');
        if(remove)remove.checked=false;
        schedulePreview();
      }
    });
    sel(panel,'#designerLogo').onchange=e=>{
      if(e.target.files?.length){pendingLogo=e.target.files[0];draft.quitarLogo=false;
        const remove=sel(panel,'#removeLogo');
        if(remove)remove.checked=false;
        schedulePreview();
      }
    };
    const removeLogo=sel(panel,'#removeLogo');
    if(removeLogo)removeLogo.onchange=e=>{
      draft.quitarLogo=e.target.checked;
      if(e.target.checked){
        pendingLogo=null;
        sel(panel,'#designerLogo').value='';
      }
      schedulePreview();
    };
    all(panel,'[data-remove-image]').forEach(box=>box.onchange=e=>{
      if(!e.target.checked)return;
      const row=e.target.closest('[data-question]');
      const index=Number(row.dataset.question);
      draft.preguntas[index].pendingImage=null;
      const input=sel(row,'[data-image]');
      if(input)input.value='';
      schedulePreview();
    });
    all(panel,'[data-meta]').forEach(field=>{
      field.addEventListener('input',()=>schedulePreview());
      field.addEventListener('change',()=>schedulePreview());
    });
    const modeGen=sel(root,'#applicationMode'),paperGen=sel(root,'#applicationPaper');
    if(modeGen)modeGen.value=draft.modo;
    if(paperGen)paperGen.value=draft.papel;
  }
  async function saveDesign(){
    const payload=cleanPayload();
    const form=new FormData();
    form.append('payload',JSON.stringify(payload));
    for(const [i,q] of draft.preguntas.entries()){
      if(q.pendingImage){
        const file=q.pendingImage;
        form.append('images',new File([file],'q'+(i+1)+'__'+file.name,
                                      {type:file.type}));
      }
    }
    if(pendingLogo)form.append('logo',pendingLogo);
    try{
      await api('/library/'+encodeURIComponent(examId)+'/edit',
                {method:'POST',body:form});
      alertBox('Diseño, preguntas e imágenes guardadas.');
      await loadExam(examId);
    }catch(err){alertBox(err.message,true);}
  }
  async function loadExam(id){
    examId=id;
    const detail=await api('/library/'+encodeURIComponent(id));
    pendingLogo=null;
    draft={...detail,quitarLogo:false,preguntas:detail.preguntas.map((q,i)=>({
      ...q,opciones:q.opciones.slice(),sourceIndex:i,quitarImagen:false,
      pendingImage:null
    }))};
    if(sel(root,'#examSelector'))sel(root,'#examSelector').value=id;
    showEditor();
    savedDesign=JSON.stringify(cleanPayload());
    await preview();
  }
  function parseRow(line){
    // CSV básico con comillas y escape doble; pegar también desde Excel (TAB).
    const delimiter=line.includes('\t')?'\t':',';
    const fields=[];let value='',quoted=false;
    for(let i=0;i<line.length;i++){
      const ch=line[i];
      if(ch==='"'&&line[i+1]==='"'&&quoted){value+='"';i++;continue;}
      if(ch==='"'){quoted=!quoted;continue;}
      if(ch===delimiter&&!quoted){fields.push(value.trim());value='';continue;}
      value+=ch;
    }
    if(quoted)throw Error('Comillas sin cerrar en la lista de personal.');
    fields.push(value.trim());
    return fields;
  }
  const csv = value => /[,"\n]/.test(value)?'"'+String(value).replace(/"/g,'""')+'"':value;
  function peopleFromText(){
    const value=sel(root,'#rosterInput').value;
    const lines=value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    if(!lines.length)return [];
    if(/^(id|id_personal)(,|\t)/i.test(lines[0]))lines.shift();
    return lines.map((line,i)=>{
      const cols=parseRow(line);
      if(cols.length>5)throw Error('Fila '+(i+1)+': se esperan ID, Nombre, Área, Grupo, Turno.');
      return {id:cols[0]||'',nombre:cols[1]||'',area:cols[2]||'',
              grupo:cols[3]||'',turno:cols[4]||''};
    });
  }
  async function renderGeneration(){
    const panel=sel(root,'#generationPanel');
    if(!panel)return;
    panel.innerHTML='<h2>Emitir e imprimir</h2>'+
      '<p>Elige Normal o Ecológico. La lista es <b>opcional</b>. QR y folios sólo cuando hay participantes.</p>'+
      '<div class="cols"><label>Nombre de la aplicación<input id="appName" placeholder="Ej. Cabos turno C"></label>'+
      '<label>Modalidad<select id="applicationMode"><option value="normal">Normal · cuadernillo individual</option>'+
      '<option value="ecologico">Ecológico · cuadernillo reutilizable</option></select></label>'+
      '<label>Papel<select id="applicationPaper"><option>Carta</option><option>A4</option><option>Oficio</option></select></label>'+
      '</div><h3>Lista de personal (opcional)</h3>'+
      '<a class="ghost" href="/api/templates/personal">Descargar plantilla de personal XLSX</a>'+
      '<label>Cargar CSV o Excel XLSX<input id="rosterFile" type="file" accept=".csv,.xlsx"></label>'+
      '<p class="hint">El archivo puede tener ID_personal, Nombre, Area_adscripcion, Grupo y Turno. Sólo ID y Nombre son obligatorios; se conservan ceros iniciales si Excel los almacena como texto.</p>'+
      '<label>También puedes escribir o pegar desde Excel: ID, Nombre, Área, Grupo, Turno'+
      '<textarea id="rosterInput" rows="6" placeholder="000001,Persona ficticia,Área A,Equipo 1,Día"></textarea></label>'+
      '<div id="rosterCount" class="hint">Sin lista: hoja sin QR y corrección manual con acetato.</div>'+
      '<div class="actions"><button id="generateFiles" class="primary">Generar documentos del examen</button></div>'+
      '<div id="createdFiles"></div><div id="manualHistory"></div>';
    sel(panel,'#applicationMode').value=draft?.modo||'ecologico';
    sel(panel,'#applicationPaper').value=draft?.papel||'Carta';
    sel(panel,'#rosterFile').onchange=async e=>{
      const file=e.currentTarget.files[0];
      if(!file)return;
      const form=new FormData();form.append('file',file);
      try{
        const resp=await api('/roster/import',{method:'POST',body:form});
        sel(panel,'#rosterInput').value=resp.participantes.map(p=>
          [p.id,p.nombre,p.area,p.grupo,p.turno].map(csv).join(',')).join('\n');
        sel(panel,'#rosterCount').textContent=resp.cantidad+' participantes leídos; revisa los campos antes de generar.';
        alertBox('Lista de personal importada y validada.');
      }catch(err){alertBox(err.message,true);}
    };
    sel(panel,'#rosterInput').oninput=()=>{
      try{
        const list=peopleFromText();
        sel(panel,'#rosterCount').textContent=list.length?
          list.length+' participantes: se emitirán folios QR firmados.':
          'Sin lista: la corrección será manual con el acetato.';
      }catch(err){sel(panel,'#rosterCount').textContent=err.message;}
    };
    await refreshManualHistory();
    sel(panel,'#generateFiles').onclick=async e=>{
      if(!examId){alertBox('Selecciona un cuestionario.',true);return;}
      const button=e.currentTarget;
      try{
        // Un examen emitido es inmutable: impedir que campos aún sin guardar
        // parezcan formar parte de la versión usada para los folios.
        if(JSON.stringify(cleanPayload())!==savedDesign)
          throw Error('Primero guarda los cambios del diseño y después genera el examen.');
        const people=peopleFromText();
        if(people.length>500)throw Error('Máximo 500 participantes por aplicación.');
        if(people.some(p=>!p.id||!p.nombre))
          throw Error('Cada participante debe tener ID y nombre.');
        button.disabled=true;
        const resp=await api('/applications',{method:'POST',body:{
          cuestionario_id:examId,nombre:sel(panel,'#appName').value,
          modalidad:sel(panel,'#applicationMode').value,
          papel:sel(panel,'#applicationPaper').value,participantes:people}});
        const dir=resp.sid?'/api/applications/'+encodeURIComponent(resp.sid)+
          '/files/':'/api/print-lots/'+encodeURIComponent(resp.lote_id)+'/files/';
        sel(panel,'#createdFiles').innerHTML='<div class="panel">'+
          '<h3>'+(resp.tipo==='omr'?'Aplicación OMR: '+h(resp.sid):
             'Lote genérico sin QR')+'</h3>'+
          '<p>'+h(resp.aviso||'Lista de participantes asociada con folios firmados.')+'</p>'+
          '<div class="actions">'+resp.archivos.map(file=>
             '<a class="secondary" href="'+dir+encodeURIComponent(file)+'">'+h(file)+'</a>').join('')+'</div>'+
          '<p class="hint">Imprimir al 100 % sin ajustar escala. La hoja de respuestas y su acetato deben ser del mismo lote.</p></div>';
        if(resp.sid&&onCreated)await onCreated(resp.sid);
        if(resp.tipo==='manual')await refreshManualHistory();
        alertBox('Material del examen generado correctamente.');
      }catch(err){alertBox(err.message,true);}
      finally{button.disabled=false;}
    };
  }
  async function refreshManualHistory(){
    const target=sel(root,'#manualHistory');
    if(!target)return;
    try{
      const lots=await api('/print-lots');
      target.innerHTML=lots.length?
        '<h3>Lotes sin lista · acetato manual</h3><p class="hint">Sin sesión QR, conservados para reimpresión.</p>'+
        '<div class="tableWrap"><table><thead><tr><th>Lote</th><th>Modo</th><th>Documentos</th></tr></thead><tbody>'+
        lots.map(lot=>'<tr><td>'+h(lot.nombre)+'<br><code>'+h(lot.id)+'</code></td>'+
          '<td>'+h(lot.modo)+'</td><td>'+
          ['Cuadernillo.pdf','Hoja_respuestas.pdf','Acetato_clave.pdf','Clave_docente.pdf'].map(name=>
            '<a class="listLink" href="/api/print-lots/'+encodeURIComponent(lot.id)+
            '/files/'+encodeURIComponent(name)+'">'+h(name)+'</a>').join(' · ')+
          '</td></tr>').join('')+'</tbody></table></div>':'';
    }catch(err){target.textContent='No se pudo consultar historial: '+err.message;}
  }
  async function preview(){
    if(!examId)return;
    const seq=++previewSeq;
    const config=cleanPayload();
    config.con_personal=!!sel(root,'#previewPersonal')?.checked;
    const csrf=document.cookie.split('; ').find(x=>x.startsWith('omr_csrf='));
    const token=csrf?decodeURIComponent(csrf.slice('omr_csrf='.length)):'';
    const pending=draft.preguntas.some(q=>q.pendingImage)||!!pendingLogo;
    const status=sel(root,'#previewStatus');
    if(status)status.textContent='Actualizando vista previa PDF…';
    const endpoint='/api/library/'+encodeURIComponent(examId)+
      (pending?'/preview-live?view=':'/preview?view=')+
      encodeURIComponent(activeView);
    const headers={'X-CSRF-Token':token};
    let payload;
    if(pending){
      const form=new FormData();
      form.append('config',JSON.stringify(config));
      for(const [i,q] of draft.preguntas.entries()){
        if(q.pendingImage){
          const file=q.pendingImage;
          form.append('images',new File([file],'q'+(i+1)+'__'+file.name,
                                        {type:file.type}));
        }
      }
      if(pendingLogo)form.append('logo',pendingLogo);
      payload=form;
    }else{
      headers['Content-Type']='application/json';
      payload=JSON.stringify(config);
    }
    try{
      const response=await fetch(endpoint,{
        method:'POST',headers,credentials:'same-origin',body:payload});
      if(!response.ok){
        const detail=await response.json().catch(()=>({}));
        throw Error(detail.error||detail.detail||'No se generó vista PDF.');
      }
      const blob=await response.blob();
      if(seq!==previewSeq || !sel(root,'#pdfPreview'))return;
      const previous=previewURL;
      previewURL=URL.createObjectURL(blob);
      sel(root,'#pdfPreview').src=previewURL;
      if(previous)URL.revokeObjectURL(previous);
      if(status)status.textContent=pending?
        'Vista temporal con fotos o logo aún sin guardar.' :
        'Vista exacta de la revisión actual.';
    }catch(err){
      if(seq!==previewSeq)return;
      if(status)status.textContent='Vista previa: '+err.message;
      alertBox(err.message,true);
    }
  }
  async function start(params){
    ({api,alertBox,root,onCreated}=params);
    previewSeq++;
    if(previewURL){URL.revokeObjectURL(previewURL);previewURL=null;}
    exams=await api('/library');
    root.innerHTML='<div class="designerWorkbench"><div class="designerSteps">'+
      '<details class="panel designerSection" id="importSection">'+
      '<summary><b>Importar preguntas y crear cuestionario</b>'+
      '<small>Plantilla Excel, imágenes y logo</small></summary>'+
      '<p class="hint">En Excel puedes escribir el nombre PNG/JPG en la columna Imagen (H) o pegar la foto anclada a la fila de esa pregunta. Una foto incrustada no necesita adjuntarse de nuevo.</p>'+
      '<div class="actions"><a class="ghost" href="/api/templates/preguntas">Descargar plantilla de preguntas</a>'+
      '<a class="ghost" href="/api/templates/personal">Descargar plantilla de personal</a></div>'+
      '<form id="importQ"><div class="cols">'+
      '<label>Nombre en biblioteca<input name="name" required placeholder="Evaluación de Cabos"></label>'+
      '<label>Título de impresión<input name="title" required placeholder="Evaluación de conocimientos"></label>'+
      '<label>Excel de preguntas (.xlsx)<input name="file" type="file" accept=".xlsx" required></label>'+
      '<label>Fotos mencionadas en columna Imagen (PNG/JPG, opcional)<input name="images" type="file" accept=".png,.jpg,.jpeg" multiple></label>'+
      '<label>Logotipo (opcional)<input name="logo" type="file" accept=".png,.jpg,.jpeg"></label>'+
      '</div><details><summary>Datos y diseño inicial</summary>'+
      '<div class="cols">'+
      meta('empresa','Empresa','').replace('data-meta=','name=')+
      meta('grupo','Área / grupo','').replace('data-meta=','name=')+
      meta('subtitulo','Subtítulo','').replace('data-meta=','name=')+
      choose('papel','Papel',['Carta','A4','Oficio'],'Carta').replace('data-meta=','name=')+
      choose('modo','Modalidad',['normal','ecologico'],'ecologico').replace('data-meta=','name=')+
      meta('letra','Tamaño de letra',9,'number','min="8" max="12" step="0.5"').replace('data-meta=','name=')+
      meta('logo_ancho_mm','Ancho logotipo en mm (10–28)',23,
        'number','min="10" max="28" step="1"').replace('data-meta=','name=')+
      meta('color_titulo','Color título','#213A4C','color').replace('data-meta=','name=')+
      meta('color_subtitulo','Color subtítulo','#5E7180','color').replace('data-meta=','name=')+
      meta('color_respuestas','Color hoja','#213A4C','color').replace('data-meta=','name=')+
      meta('color_acetato','Color acetato','#167341','color').replace('data-meta=','name=')+
      '</div><label>Instrucciones<textarea name="instrucciones">Selecciona una sola respuesta por pregunta.</textarea></label>'+
      '</details><div class="actions"><button class="primary">Importar a biblioteca</button></div></form></details>'+
      '<details class="panel designerSection" id="librarySection" open>'+
      '<summary><b>Biblioteca de cuestionarios</b><small>Seleccionar versión para editar</small></summary>'+
      '<label>Seleccionar y editar<select id="examSelector"><option value="">Selecciona un cuestionario…</option>'+
      exams.map(x=>'<option value="'+h(x.id)+'">'+h(x.nombre)+' · '+x.total+' preguntas (rev. '+x.revision+')</option>').join('')+
      '</select></label></details>'+
      '<details class="panel designerSection" id="designSection" open>'+
      '<summary><b>Diseñar cuestionario</b><small>Preguntas, colores, medidas y fotos</small></summary>'+
      '<div id="designerPanel"></div></details>'+
      '<details class="panel designerSection" id="generationSection">'+
      '<summary><b>Emitir e imprimir</b><small>Normal / Ecológico, lista opcional, QR y acetato</small></summary>'+
      '<div id="generationPanel"></div></details></div>'+
      '<aside class="panel designerPreview" id="designerPreview">'+
      '<h3>Vista previa PDF real</h3>'+
      '<p class="hint">Los cambios de texto, colores, fotografías y medidas se actualizan sin cerrar el visor.</p>'+
      '<div class="actions"><button type="button" class="ghost" id="refreshPdfPreview">Actualizar vista previa</button></div>'+
      '<div class="actions">'+['Cuadernillo','Respuestas','Acetato'].map(v=>
        '<button type="button" class="secondary" data-preview="'+v+'">'+
        (v==='Respuestas'?'Hoja de respuestas':v)+'</button>').join('')+'</div>'+
      '<label class="check"><input type="checkbox" id="previewPersonal">'+
      'Mostrar participante y QR de EJEMPLO (no emite folios)</label>'+
      '<p class="hint" id="previewStatus">Selecciona un cuestionario para ver la vista previa.</p>'+
      '<iframe id="pdfPreview" class="pdfPreview" title="Vista real de impresión del examen"></iframe>'+
      '</aside></div>';
    all(root,'[data-preview]').forEach(button=>button.onclick=()=>{
      activeView=button.dataset.preview;
      preview();
    });
    sel(root,'#previewPersonal').onchange=()=>preview();
    sel(root,'#refreshPdfPreview').onclick=()=>preview();
    sel(root,'#importQ').onsubmit=async e=>{
      e.preventDefault();
      const form=e.target, fd=new FormData(form), name=String(fd.get('name')||''),
            title=String(fd.get('title')||'');
      const btn=sel(form,'button');btn.disabled=true;
      try{
        // Inputs múltiples vacíos son omitidos para evitar "archivo" sin nombre.
        if(!sel(form,'[name="logo"]').files.length)fd.delete('logo');
        if(!sel(form,'[name="images"]').files.length)fd.delete('images');
        const result=await api('/library/import?name='+encodeURIComponent(name)+
          '&title='+encodeURIComponent(title),{method:'POST',body:fd});
        alertBox('Cuestionario importado: '+result.preguntas+' preguntas.');
        await start(params);
        await loadExam(result.cuestionario_id);
      }catch(err){alertBox(err.message,true);}
      finally{btn.disabled=false;}
    };
    sel(root,'#examSelector').onchange=async e=>{
      if(!e.target.value){sel(root,'#designerPanel').innerHTML='';return;}
      try{await loadExam(e.target.value);}catch(err){alertBox(err.message,true);}
    };
    if(exams.length){
      await loadExam(exams[0].id);
      await renderGeneration();
    }else{
      sel(root,'#designerPanel').innerHTML='<p class="hint">Importa una plantilla para empezar a diseñar.</p>';
      sel(root,'#generationPanel').innerHTML='<p class="hint">Primero crea un cuestionario.</p>';
    }
  }
  window.OMRDesigner={start};
})();
