'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="thermy-token"]').content;
let defaults = {}, personal = {}, settings = {}, kind = 'cable', panel = 'layout';
let revision = 0, timer, rendering = false, current = null, busy = false, imageData = '';
let previewMeta = null;
let rowCopies = [];
const fieldIds = ['left', 'left_extra', 'right', 'right_extra'];
let editTarget = 'left', editStart = 0, editEnd = 0;
const iconCatalogue = JSON.parse($('iconCatalogue').textContent);
function rememberSelection(id) {
  if ($(id).readOnly) return;
  editTarget=id; editStart=$(id).selectionStart; editEnd=$(id).selectionEnd;
}
for (const id of [...fieldIds,'machineText']) {
  for (const event of ['focus','select','keyup','mouseup','input']) $(id).addEventListener(event,()=>rememberSelection(id));
  $(id).addEventListener('keydown',event=>{
    if(event.key==='Enter' && event.shiftKey && !$(id).readOnly) {
      event.preventDefault(); rememberSelection(id); insertFormatted(id==='machineText'?'\n':'[br]');
    }
  });
}
function insertFormatted(prefix, suffix='', keepSelection=false) {
  if(kind==='paragraph' && editTarget!=='machineText') { editTarget='machineText'; editStart=editEnd=$('machineText').value.length; }
  if(kind==='cable' && (editTarget==='machineText' || $(editTarget).readOnly || (Number(settings.columns)!==4 && editTarget.endsWith('_extra')))) {
    editTarget='left'; editStart=editEnd=$('left').value.length;
  }
  const target=$(editTarget), selected=target.value.slice(editStart,editEnd);
  target.setRangeText(prefix+((suffix||keepSelection)?selected:'')+suffix,editStart,editEnd,'end');
  if(suffix && !selected) target.setSelectionRange(editStart+prefix.length, editStart+prefix.length);
  target.focus(); rememberSelection(editTarget); changed();
}
$('formatRegular').addEventListener('click',()=>insertFormatted('[regular]','[/regular]'));
$('formatLineAlign').addEventListener('change',()=>{ if($('formatLineAlign').value) { insertFormatted(`[${$('formatLineAlign').value}]`, '', true); $('formatLineAlign').value=''; } });
$('formatBold').addEventListener('click',()=>insertFormatted('[b]','[/b]'));
$('formatSize').addEventListener('click',()=>{
  if($('selectionSize').reportValidity() && $('selectionSize').value) insertFormatted(`[size:${$('selectionSize').value}]`,'[/size]');
});
$('insertBreak').addEventListener('click',()=>insertFormatted(kind==='paragraph'?'\n':'[br]'));
function iconChoices() {
  $('iconList').replaceChildren();
  let matches=0;
  const query=$('iconSearch').value.toLowerCase().trim().split(/[\s-]+/).filter(Boolean);
  for(const [name,shapes] of Object.entries(iconCatalogue)) {
    if(!query.every(word=>name.includes(word))) continue;
    matches++;
    const button=document.createElement('button'); button.type='button'; button.title=name; button.setAttribute('aria-label',`Insert ${name} icon`);
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    for(const [key,value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'2','stroke-linecap':'round','stroke-linejoin':'round'})) svg.setAttribute(key,value);
    for(const [type,...v] of shapes) {
      const shape=document.createElementNS('http://www.w3.org/2000/svg',type);
      const attributes=type==='text'?{x:v[0],y:v[1],'font-size':v[2],'font-family':'sans-serif','font-weight':'bold','text-anchor':'middle',fill:'currentColor',stroke:'none'}:type==='circle'?{cx:v[0],cy:v[1],r:v[2]}:type==='rect'?{x:v[0],y:v[1],width:v[2],height:v[3]}:type==='line'?{x1:v[0],y1:v[1],x2:v[2],y2:v[3]}:{points:v.join(' ')};
      for(const [key,value] of Object.entries(attributes)) shape.setAttribute(key,value);
      if(type==='text') shape.textContent=v[4];
      svg.append(shape);
    }
    const label=document.createElement('span'); label.textContent=name;
    button.append(svg,label);
    button.addEventListener('click',()=>{
      if(!$('insertIconSize').reportValidity() || !$('insertIconSize').value) return;
      const size=Number($('insertIconSize').value);
      $('iconsDialog').close(); insertFormatted(size===Number(settings.icon_size||32)?`[icon:${name}]`:`[icon:${name}:${size}]`);
    });
    $('iconList').append(button);
  }
  $('iconCount').textContent=matches?`${matches} of ${Object.keys(iconCatalogue).length} icons`:'No matching icons. Try GPU, network, storage or a model number.';
}
$('openIcons').addEventListener('click',()=>{ $('insertIconSize').value=settings.icon_size||32; $('iconSearch').value=''; iconChoices(); $('iconsDialog').showModal(); $('iconSearch').focus(); });
$('iconSearch').addEventListener('input',iconChoices);
async function api(path, data = {}) {
  if (window.__TAURI__?.core) {
    try { return await window.__TAURI__.core.invoke('api', {path, data}); }
    catch (error) { throw new Error(typeof error === 'string' ? error : String(error)); }
  }
  const response = await fetch('/api/' + path, {method: 'POST', headers: {'Content-Type':'application/json', 'X-Thermy9-Token':token}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) {
    let error = result.error || 'Something went wrong.';
    const match = error.match(/Rendering failed \(no print sent\): ([\s\S]+)/);
    if (match) { try { error = JSON.parse(match[1]).message || error; } catch {} }
    throw new Error(error);
  }
  return result;
}
function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
function presets(selected = '') {
  const select = $('preset'); select.replaceChildren();
  for (const [title, entries] of [['Starting points', defaults], ['Saved by you', personal]]) {
    if (!Object.keys(entries).length) continue;
    const group = document.createElement('optgroup'); group.label = title;
    for (const name of Object.keys(entries)) { const option = new Option(name, name); group.append(option); }
    select.append(group);
  }
  if (selected) select.value = selected;
}
function applyPreset(name) {
  const preset = personal[name] || defaults[name]; if (!preset) return;
  kind = preset.kind;
  settings = {...defaults[kind === 'cable' ? 'Cable flags' : 'Machine label'].settings, ...preset.settings};
  $('preset').value = name;
  syncView(); drawControls(); changed();
}
function syncView() {
  document.querySelectorAll('[data-kind]').forEach(b => b.classList.toggle('active', b.dataset.kind === kind));
  $('richToolbar').hidden = kind === 'image';
  $('cableEditor').hidden = kind !== 'cable'; $('columnToggle').hidden = kind !== 'cable';
  $('machineEditor').hidden = kind !== 'paragraph'; $('imageEditor').hidden = kind !== 'image';
  $('contentTitle').textContent = {cable:'What’s on your cable?', paragraph:'Give it a name.', image:'A picture worth printing.'}[kind];
  const four = Number(settings.columns) === 4;
  $('columnGrid').classList.toggle('four', four); $('fourHint').hidden = !four;
  document.querySelectorAll('[data-columns]').forEach(b => b.classList.toggle('active', Number(b.dataset.columns) === Number(settings.columns || 2)));
  $('mirror').checked = settings.mirror !== false;
  $('image_mode').value = settings.image_mode || 'sticker';
  syncFieldLayout();
  syncMirror();
}
function syncFieldLayout() {
  const four = Number(settings.columns) === 4;
  for (const side of ['left', 'right']) {
    const swap = four && !!settings[side + '_swap'];
    const button = $(side === 'left' ? 'swapLeft' : 'swapRight');
    button.hidden = !four;
    button.setAttribute('aria-pressed', String(swap));
    button.textContent = swap ? '⇄ Restore order' : '⇄ Swap fields';
    $(side).closest('label').style.order = swap ? '2' : '0';
    $(side + '_extra').closest('label').style.order = '1';
    for (const id of [side, side + '_extra']) {
      const alignment = settings[id + '_align'] || (side === 'left' ? 'left' : 'right');
      $(id + '_align').value = alignment;
      $(id).style.textAlign = alignment;
    }
  }
}
function syncMirror() {
  for (const [left, right] of [['left', 'right'], ['left_extra', 'right_extra']]) {
    $(right).readOnly = settings.mirror !== false;
    if ($(right).readOnly) $(right).value = $(left).value;
  }
  syncCopies();
}
function syncCopies() {
  const active = Number(settings.columns) === 4 ? fieldIds : ['left', 'right'];
  const lines = value => value === '' ? 0 : value.replace(/\r\n/g, '\n').replace(/\n$/, '').split('\n').length;
  const count = Math.max(1, ...active.map(id => lines($(id).value)));
  rowCopies = Array.from({length:count}, (_, i) => rowCopies[i] ?? 1);
  const container = $('rowCopies');
  if (container.children.length !== count) {
    container.replaceChildren();
    rowCopies.forEach((quantity, i) => {
      const input = document.createElement('input'); input.type = 'number'; input.min = '1'; input.max = '50'; input.step = '1';
      input.value = quantity; input.setAttribute('aria-label', `Copies for row ${i+1}`); input.title = `Row ${i+1} copies`;
      input.addEventListener('input', () => { rowCopies[i] = input.value === '' ? '' : Number(input.value); changed(); });
      const row = document.createElement('div'); row.className = 'copy-row'; row.append(input); container.append(row);
    });
  }
  const valid = rowCopies.every(n => Number.isInteger(n) && n >= 1 && n <= 50);
  $('copiesSummary').textContent = valid ? `${count} rows → ${rowCopies.reduce((a,b)=>a+b,0)} labels` : 'Enter whole numbers from 1 to 50.';
}
$('setAllCopies').addEventListener('click', () => {
  if (!$('allCopies').reportValidity() || !$('allCopies').value) return;
  const quantity = Number($('allCopies').value);
  rowCopies = rowCopies.map(() => quantity);
  $('rowCopies').querySelectorAll('input').forEach(input => { input.value = quantity; });
  changed();
});
for (const id of fieldIds) $(id).addEventListener('scroll', () => {
  for (const other of fieldIds) if ($(other).scrollTop !== $(id).scrollTop) $(other).scrollTop = $(id).scrollTop;
  $('rowCopies').scrollTop = $(id).scrollTop;
});
$('rowCopies').addEventListener('scroll', () => {
  for (const id of fieldIds) if ($(id).scrollTop !== $('rowCopies').scrollTop) $(id).scrollTop = $('rowCopies').scrollTop;
});
// label, setting, minimum, maximum, step, unit, fallback
const ranges = {
  icon_size:['Default icon size','icon_size',8,240,1,'px',32], line_gap:['Between lines within a label','line_gap',0,100,1,'px',4],
  font_size:['Text size','font_size',8,240,1,'px',32], padding_mm:['Side inset','padding_mm',0,20,.25,'mm',2.5],
  width_mm:['Label width','width_mm',5,44,.5,'mm',44], row_mm:['Row height','row_mm',5,100,.5,'mm',10],
  gap_mm:['Between rows','gap_mm',0,30,.5,'mm',2], fold_mm:['Fold space','fold_mm',0,30,.5,'mm',4],
  field_gap_mm:['Between fields','field_gap_mm',0,20,.25,'mm',1], first_field_percent:['Preferred field 1 share','first_field_percent',5,95,1,'%',40],
  label_length_mm:['Label length','label_length_mm',5,500,.5,'mm',30], stroke:['Border thickness','stroke',0,16,1,'px',2],
  radius_mm:['Corner radius','radius_mm',0,20,.25,'mm',1.5], leading_mm:['Blank paper at start','leading_mm',0,100,.5,'mm',0],
  trailing_mm:['Tear-off space at end','trailing_mm',0,100,.5,'mm',14]
};
function drawControls() {
  $('settings').replaceChildren();
  document.querySelectorAll('[data-panel]').forEach(b => b.classList.toggle('active', b.dataset.panel === panel));
  const addRange = key => {
    const [title, name, min, maximum, step, unit, fallback] = ranges[key];
    const max = maximum;
    const wrap = document.createElement('div'); wrap.className = 'control';
    const label = document.createElement('label'); label.htmlFor = name; label.textContent = title;
    const output = document.createElement('output'); output.htmlFor = name;
    const input = document.createElement('input'); input.type = 'range'; input.id = name; input.min = min; input.max = max; input.step = step;
    input.value = settings[name] ?? fallback; output.textContent = `${input.value} ${unit}`;
    input.addEventListener('input', () => { settings[name] = Number(input.value); output.textContent = `${input.value} ${unit}`; changed(); });
    label.append(output); wrap.append(label,input); $('settings').append(wrap);
  };
  const addCheck = (title, key, fallback) => {
    const wrap = document.createElement('div'); wrap.className = 'control check-control';
    const label = document.createElement('label'); label.className = 'check';
    const input = document.createElement('input'); input.type = 'checkbox'; input.checked = settings[key] ?? fallback; input.id = key;
    input.addEventListener('change', () => { settings[key] = input.checked; changed(); });
    label.append(input, document.createTextNode(title)); wrap.append(label); $('settings').append(wrap);
  };
  const addSelect = (title, key, options, fallback) => {
    const wrap = document.createElement('div'); wrap.className = 'control';
    const label = document.createElement('label'); label.textContent = title; label.htmlFor = key;
    const select = document.createElement('select'); select.id = key;
    options.forEach(([value, text]) => select.add(new Option(text, value)));
    select.value = settings[key] ?? fallback;
    select.addEventListener('change', () => { settings[key] = select.value; changed(); });
    wrap.append(label,select); $('settings').append(wrap);
  };
  const note = text => { const el = document.createElement('p'); el.className = 'control-note'; el.textContent = text; $('settings').append(el); };
  if (panel === 'paper') {
    addRange('leading_mm'); addRange('trailing_mm');
    note('Start at 0 to add no leading paper. Paper already past the print head cannot be pulled back. End feed gives room to tear, and also affects the blank area before your next print.');
  } else if (kind === 'image') {
    note('Choose Sticker for sharp artwork or Photo for shaded images. Paper & tear-off controls the blank space around your print.');
  } else if (panel === 'borders') {
    addRange('stroke'); addRange('radius_mm');
    if (kind === 'cable') {
      addSelect('Border around','border_mode',[['Whole row','Whole row'],['Each half','Each side of the fold']], 'Whole row');
      addCheck('Dotted fold line','fold_mark',false);
    } else addCheck('Show border','border',true);
    note('Set thickness to 0 for no border. Set radius to 0 for square corners.');
  } else {
    addRange('font_size'); addRange('icon_size'); addRange('line_gap'); addRange('padding_mm'); addCheck('Bold text','bold',true);
    if (kind === 'cable') {
      ['width_mm','row_mm','gap_mm','fold_mm'].forEach(addRange);
      if (Number(settings.columns) === 4) {
        addRange('field_gap_mm'); addRange('first_field_percent');
        addCheck('Let fields share spare space','auto_field_widths',true);
        note('Fields can borrow unused width from their neighbour without changing the text size. Turn this off for a fixed percentage split. Show rulers and lines to see the actual space available.');
      }
    } else {
      addRange('label_length_mm');
      addSelect('Text alignment','align',[['left','Left'],['center','Centre'],['right','Right']],'center');
      addSelect('Typeface','font_family',[['sans','Sans serif'],['serif','Serif'],['mono','Monospace']],'sans');
    }
  }
}
function snapshot() {
  let content = $('machineText').value;
  if (kind === 'cable') content = JSON.stringify({...Object.fromEntries(fieldIds.map(id => [id, $(id).value])), copies:rowCopies});
  return {kind, content, image:imageData, mode:settings.image_mode || 'sticker', settings:{...settings}};
}
function updatePrint() { $('print').disabled = !current || busy; }
function drawGuides() {
  const svg = $('previewGuides'), enabled = $('showGuides').checked;
  svg.replaceChildren(); svg.toggleAttribute('hidden', !enabled || !previewMeta);
  $('guideLegend').hidden = !enabled;
  $('previewSheet').classList.toggle('with-guides', enabled);
  if (!enabled || !previewMeta) return;
  const m = previewMeta, h = m.height, lead = m.leading_rows || 0;
  svg.setAttribute('viewBox', `0 0 576 ${h}`);
  const element = (tag, attributes, text) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attributes).forEach(([key,value]) => node.setAttribute(key,value));
    if (text !== undefined) node.textContent = text;
    svg.append(node); return node;
  };
  const line = (x1,y1,x2,y2,color,dashed=false) => element('line',{x1,y1,x2,y2,stroke:color,'stroke-width':1,'vector-effect':'non-scaling-stroke',...(dashed?{'stroke-dasharray':'4 3'}:{})});
  const rect = (x,y,width,height,color,fill='none') => element('rect',{x,y,width,height,stroke:color,fill,'stroke-width':1,'stroke-dasharray':'4 3','vector-effect':'non-scaling-stroke'});
  line(0,-7,576,-7,'#617457'); line(-7,0,-7,h,'#617457');
  for (let mm=0;mm<=44;mm++) {
    const x=mm*576/44; line(x,-7,x,mm%5===0?-17:-12,'#617457');
    if(mm%5===0) element('text',{x,y:-23,'text-anchor':'middle','font-size':18,fill:'#48613e'},mm);
  }
  for (let mm=0;mm<=h*.08472;mm++) {
    const y=mm/.08472; line(-7,y,mm%5===0?-17:-12,y,'#617457');
    if(mm%5===0) element('text',{x:-23,y:y+6,'text-anchor':'end','font-size':18,fill:'#48613e'},mm);
  }
  if(lead) rect(0,0,576,lead,'#718b76','#718b7612');
  if(m.trailing_rows) rect(0,lead+m.content_height,576,m.trailing_rows,'#718b76','#718b7612');
  line(0,lead,576,lead,'#718b76',true); line(0,lead+m.content_height,576,lead+m.content_height,'#718b76',true);
  if(m.guides) {
    const g=m.guides;
    rect(g.fold[0],lead,g.fold[1],g.content_height,'#568db2','#568db21a');
    line(288,lead,288,lead+g.content_height,'#568db2',true);
    g.rows.forEach(([x,y,w,h])=>rect(x,y+lead,w,h,'#5d9270'));
    g.fields.forEach(([x,y,w,h])=>rect(x,y+lead,w,h,'#d58b47','#d58b4709'));
  }
}
$('showGuides').addEventListener('change', () => {
  try { localStorage.setItem('thermy9-guides', $('showGuides').checked ? '1' : '0'); } catch {}
  drawGuides();
});
try { $('showGuides').checked = localStorage.getItem('thermy9-guides') === '1'; } catch {}
function changed() {
  syncMirror(); revision++; current = null; updatePrint();
  $('previewBadge').textContent = 'Updating'; $('previewError').hidden = true;
  $('previewImage').style.opacity = '.4';
  previewMeta = null; drawGuides();
  clearTimeout(timer); timer = setTimeout(render, 450);
}
async function render() {
  if (rendering) return;
  const rev = revision, data = snapshot();
  if (kind === 'image' && !imageData) {
    $('previewBadge').textContent = 'Choose image'; $('previewImage').hidden = true; $('previewSheet').hidden = true;
    $('previewEmpty').hidden = false; $('previewEmpty').textContent = 'Choose an image to see your print.'; return;
  }
  rendering = true;
  try {
    const result = await api('preview', data);
    if (rev !== revision) return;
    current = result;
    previewMeta = result; $('previewSheet').hidden = false; drawGuides();
    $('previewImage').src = 'data:image/png;base64,' + result.preview_png;
    $('previewImage').hidden = false; $('previewImage').style.opacity = '1'; $('previewEmpty').hidden = true;
    $('previewBadge').textContent = 'Ready to print';
    $('previewSummary').textContent = kind === 'cable' ? `${result.source_rows || result.rows} rows → ${result.rows} label${result.rows === 1 ? '' : 's'} · ${result.columns} columns` : (kind === 'image' ? 'Your image, converted for thermal paper.' : 'One machine label, just how you like it.');
    $('paperLength').textContent = `~${result.estimated_length_mm} mm of paper`;
  } catch (error) {
    if (rev !== revision) return;
    $('previewBadge').textContent = 'Needs a tweak'; $('previewError').textContent = error.message; $('previewError').hidden = false;
    $('previewImage').hidden = true; $('previewSheet').hidden = true; $('previewEmpty').hidden = false; $('previewEmpty').textContent = 'Adjust the settings to see your preview.';
    $('paperLength').textContent = '—';
  } finally {
    rendering = false; updatePrint(); if (rev !== revision) render();
  }
}
document.querySelectorAll('[data-kind]').forEach(button => button.addEventListener('click', () => {
  if (button.dataset.kind === kind) return;
  if (button.dataset.kind === 'image') { kind = 'image'; $('preset').selectedIndex = -1; syncView(); drawControls(); changed(); }
  else applyPreset(button.dataset.kind === 'cable' ? 'Cable flags' : 'Machine label');
}));
document.querySelectorAll('[data-columns]').forEach(button => button.addEventListener('click', () => { settings.columns = button.dataset.columns; syncView(); drawControls(); changed(); }));
document.querySelectorAll('[data-panel]').forEach(button => button.addEventListener('click', () => { panel = button.dataset.panel; drawControls(); }));
[...fieldIds, 'machineText'].forEach(id => $(id).addEventListener('input', changed));
$('mirror').addEventListener('change', () => { settings.mirror = $('mirror').checked; syncMirror(); changed(); });
for (const side of ['left', 'right']) {
  $(side === 'left' ? 'swapLeft' : 'swapRight').addEventListener('click', () => {
    settings[side + '_swap'] = !settings[side + '_swap']; syncFieldLayout(); changed();
  });
  for (const id of [side, side + '_extra']) $(id + '_align').addEventListener('change', () => {
    settings[id + '_align'] = $(id + '_align').value; syncFieldLayout(); changed();
  });
}
$('image_mode').addEventListener('change', () => { settings.image_mode = $('image_mode').value; changed(); });
$('preset').addEventListener('change', () => applyPreset($('preset').value));
$('refresh').addEventListener('click', changed);
$('imageFile').addEventListener('change', async () => {
  const file = $('imageFile').files[0]; if (!file) return;
  imageData = ''; changed();
  if (file.size > 20 * 1024 * 1024) { message('Choose an image smaller than 20 MB.',true); return; }
  const reader = new FileReader();
  reader.onload = () => { imageData = String(reader.result).split(',')[1]; $('imageName').textContent = file.name; changed(); };
  reader.onerror = () => message('Could not read this image.', true);
  reader.readAsDataURL(file);
});
$('print').addEventListener('click', async () => {
  if (!current || busy) return;
  if (!$('address').value.trim()) { $('printerDialog').showModal(); $('address').focus(); return; }
  const job = current.job; current = null; busy = true; updatePrint(); $('print').textContent = 'Printing…';
  message('Sending one copy to your printer…');
  try { const result = await api('print', {job, address:$('address').value}); message(result.message); }
  catch (error) { message(error.message,true); }
  finally { busy = false; $('print').textContent = 'Print this label ↗'; $('previewBadge').textContent = 'Refresh to print again'; updatePrint(); }
});
$('save').addEventListener('click', () => { $('presetName').value = ''; $('saveDialog').showModal(); $('presetName').focus(); });
$('saveForm').addEventListener('submit', async event => {
  event.preventDefault(); const name = $('presetName').value.trim();
  try { const result = await api('preset', {name,kind,settings}); personal = result.personal; presets(name); $('saveDialog').close(); message(`Saved “${name}”. Your layout is ready for next time.`); }
  catch(error) { message(error.message,true); $('presetName').setCustomValidity(error.message); $('presetName').reportValidity(); }
});
$('presetName').addEventListener('input', () => $('presetName').setCustomValidity(''));
$('exportPresets').addEventListener('click', async () => {
  try { const result = await api('export-presets'); $('presetTransferResult').textContent = `Saved to ${result.file}`; }
  catch (error) { $('presetTransferResult').textContent = error.message; }
});
$('importPresets').addEventListener('change', async () => {
  const file = $('importPresets').files[0]; if (!file) return;
  try {
    if (file.size > 1024 * 1024) throw new Error('Preset file is too large (maximum 1 MB).');
    const result = await api('import-presets', JSON.parse(await file.text()));
    personal = result.personal; presets(); $('presetTransferResult').textContent = 'Presets imported. Choose one from Your starting point.';
  } catch (error) { $('presetTransferResult').textContent = error.message; }
  finally { $('importPresets').value = ''; }
});
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => $(button.dataset.close).close()));
$('printerButton').addEventListener('click', () => $('printerDialog').showModal());
for (const operation of ['status','discover']) $(operation).addEventListener('click', async () => {
  if (busy) return; busy = true; updatePrint(); $('status').disabled = $('discover').disabled = true;
  $('printerResult').textContent = operation === 'discover' ? 'Looking for printers… this takes about 20 seconds.' : 'Checking printer…';
  try {
    const result = await api(operation, {address:$('address').value});
    $('printerResult').replaceChildren();
    if (operation === 'discover') {
      const devices = [...new Map(result.devices.map(device => [device.address,device])).values()];
      $('printerResult').textContent = devices.length ? 'Choose your printer:' : 'No printer found. Check that it is powered on and nearby.';
      devices.forEach(device => { const button = document.createElement('button'); button.className = 'secondary'; button.textContent = `${device.name} · ${device.address}`; button.onclick = () => { $('address').value = device.address; $('printerResult').textContent = 'Printer selected.'; }; $('printerResult').append(button); });
    } else $('printerResult').textContent = Object.entries(result).map(([key,value]) => `${key.replaceAll('_',' ')}: ${typeof value === 'object' ? JSON.stringify(value) : value}`).join('\n');
  } catch(error) { $('printerResult').textContent = error.message; }
  finally { busy = false; updatePrint(); $('status').disabled = $('discover').disabled = false; }
});
async function init() {
  try {
    const data = await api('init'); defaults = data.defaults; personal = data.personal; $('address').value = data.address;
    $('nativePresetTools').hidden = !data.native;
    if (data.native) $('printerHint').textContent = 'Keep the printer on and nearby, with Bluetooth enabled on this computer.';
    presets('Cable flags'); applyPreset('Cable flags'); if (data.warning) message(data.warning,true);
  } catch(error) { message('Could not start the editor: ' + error.message,true); }
}
init();
