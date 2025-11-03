from nicegui import ui, app
from datetime import datetime, timedelta
import os, pytz, pandas as pd

CC_TZ = os.getenv('CC_TZ', 'America/Chicago')
TZ = pytz.timezone(CC_TZ)
ASSIGNMENTS_CSV = os.getenv('CC_ASSIGNMENTS_CSV', 'app/data/assignments.csv')
SUBMISSIONS_CSV = os.getenv('CC_SUBMISSIONS_CSV', 'app/data/submissions.csv')
LOG_DIR = os.getenv('CC_LOG_DIR', 'app/data')
os.makedirs(os.path.dirname(ASSIGNMENTS_CSV), exist_ok=True)
os.makedirs(os.path.dirname(SUBMISSIONS_CSV), exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

ASSIGN_NAME_OPTIONS = [
    'Aldo','Alex','Carlos','Clayton','Cody','Enrique','Eric','James','Jake',
    'Johntai','Karen','Kevin','Luis','Nyahok','Stephanie','Tyteanna'
]
LANG_OPTIONS = {'en':'English','es':'Español'}
STATE = app.storage.user

def now_local(): return datetime.now(TZ)
def fmt_ts(dt): return dt.strftime('%Y-%m-%d %I:%M:%S %p')
def read_csv_safe(p):
    if not os.path.exists(p) or os.stat(p).st_size == 0: return pd.DataFrame()
    try: return pd.read_csv(p)
    except: return pd.DataFrame()
def write_csv_safe(df,p):
    tmp=p+'.tmp'; df.to_csv(tmp, index=False)
    os.replace(tmp, p) if os.path.exists(p) else os.rename(tmp, p)

for path, cols in [(ASSIGNMENTS_CSV,['assignment_id','location','sku','expected_qty','assigned_to','assigned_at','lock_until','status']),
                   (SUBMISSIONS_CSV,['submission_id','assignment_id','counter','location','sku','expected_qty','counted_qty','issue_type','actual_pallet','actual_lot','note','submitted_at'])]:
    if not os.path.exists(path): write_csv_safe(pd.DataFrame(columns=cols), path)

def get_lang(): return STATE.get('lang','en')
def set_lang(v): STATE['lang']=v
def t(en,es): return en if get_lang()=='en' else es

def get_feedback(): return STATE.get('feedback', {'sound': True, 'vibrate': True})
def set_feedback(sound, vibrate): STATE['feedback']={'sound':sound,'vibrate':vibrate}
def play_feedback():
    fb=get_feedback(); js=""
    if fb.get('sound',True):
        js+= """
        (function(){
          const ctx = new (window.AudioContext||window.webkitAudioContext)();
          const o = ctx.createOscillator(); const g = ctx.createGain();
          o.type='sine'; o.frequency.setValueAtTime(880, ctx.currentTime);
          o.connect(g); g.connect(ctx.destination); o.start();
          g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime+0.15);
          o.stop(ctx.currentTime+0.15);
        })();"""
    if fb.get('vibrate',True): js += "if (navigator.vibrate) { navigator.vibrate([40,30,40]); }"
    if js: ui.run_javascript(js)

def create_assignment(location, sku, expected_qty, assigned_to):
    df=read_csv_safe(ASSIGNMENTS_CSV)
    assignment_id=f"A{int(datetime.utcnow().timestamp())}"
    assigned_at=now_local(); lock_until=assigned_at+timedelta(minutes=20)
    row={'assignment_id':assignment_id,'location':location.strip(),'sku':(sku or '').strip(),
         'expected_qty': int(expected_qty) if str(expected_qty).strip().isdigit() else expected_qty,
         'assigned_to':assigned_to,'assigned_at':fmt_ts(assigned_at),'lock_until':fmt_ts(lock_until),'status':'Assigned'}
    df=pd.concat([df,pd.DataFrame([row])], ignore_index=True); write_csv_safe(df, ASSIGNMENTS_CSV); return assignment_id

def my_assignments(user_name:str):
    df=read_csv_safe(ASSIGNMENTS_CSV)
    if df.empty: return df
    now_ts=now_local()
    def within_lock(s):
        try: return now_ts <= TZ.localize(datetime.strptime(s, '%Y-%m-%d %I:%M:%S %p'))
        except: return True
    dfu=df[(df['assigned_to']==user_name) & (df['status'].isin(['Assigned','In Progress']))].copy()
    dfu['is_locked']=dfu['lock_until'].apply(within_lock) if 'lock_until' in dfu.columns else True
    return dfu

def submit_count(assignment_id, counter, counted_qty, issue_type, actual_pallet, actual_lot, note):
    s_df=read_csv_safe(SUBMISSIONS_CSV); sub_id=f"S{int(datetime.utcnow().timestamp())}"
    a_df=read_csv_safe(ASSIGNMENTS_CSV); rec=a_df[a_df['assignment_id']==assignment_id]
    location=rec['location'].iloc[0] if not rec.empty else ''; sku=rec['sku'].iloc[0] if not rec.empty else ''
    expected=rec['expected_qty'].iloc[0] if not rec.empty else ''
    row={'submission_id':sub_id,'assignment_id':assignment_id,'counter':counter,'location':location,'sku':sku,'expected_qty':expected,
         'counted_qty':counted_qty,'issue_type':issue_type,'actual_pallet':actual_pallet,'actual_lot':actual_lot,'note':note,
         'submitted_at':fmt_ts(now_local())}
    s_df=pd.concat([s_df,pd.DataFrame([row])], ignore_index=True); write_csv_safe(s_df, SUBMISSIONS_CSV)
    a_df.loc[a_df['assignment_id']==assignment_id,'status']='Completed'; write_csv_safe(a_df, ASSIGNMENTS_CSV)

def topbar():
    with ui.header().classes('items-center justify-between'):
        ui.label('Cycle Count (NiceGUI)').classes('text-lg font-semibold')
        with ui.row().classes('items-center gap-4'):
            ui.select({'en':'English','es':'Español'}, value=get_lang(),
                      on_change=lambda e:(set_lang(e.value), ui.notify(t('Language set to English','Idioma cambiado a Español')), ui.navigate.reload())
                     ).label=t('Language','Idioma')
            fb=get_feedback()
            s=ui.switch(value=fb.get('sound',True), on_change=lambda e:set_feedback(e.value,get_feedback().get('vibrate',True))); s.props('label="'+t('Sound','Sonido')+'"')
            v=ui.switch(value=fb.get('vibrate',True), on_change=lambda e:set_feedback(get_feedback().get('sound',True),e.value)); v.props('label="'+t('Vibration','Vibración')+'"')

def page_assign_counts():
    with ui.card():
        ui.label(t('Assign Counts','Asignar Conteos')).classes('text-md font-medium')
        assignee=ui.select(ASSIGN_NAME_OPTIONS, value='Aldo', label=t('Assign to (name)','Asignar a (nombre)'))
        location=ui.input(label=t('Location','Ubicación'), placeholder='e.g., 11400804').props('autofocus')
        sku=ui.input(label='SKU'); expected=ui.input(label=t('Expected QTY','Cantidad Esperada'), input_type='number')
        def do_assign():
            if not assignee.value or not location.value:
                ui.notify(t('Assignee and location are required.','Se requieren responsable y ubicación.'), type='warning'); return
            a_id=create_assignment(location.value, sku.value or '', expected.value or '', assignee.value)
            play_feedback(); ui.notify(t(f'Assigned {location.value} to {assignee.value} (ID {a_id})', f'Asignado {location.value} a {assignee.value} (ID {a_id})'), type='positive')
            location.value=''; sku.value=''; expected.value=''
        ui.button(t('Assign','Asignar'), on_click=do_assign).props('color=primary')

def page_my_assignments():
    with ui.card():
        ui.label(t('My Assignments','Mis Asignaciones')).classes('text-md font-medium')
        me=ui.select(ASSIGN_NAME_OPTIONS, value='Aldo', label=t('I am','Yo soy'))
        container=ui.column()
        def refresh():
            container.clear()
            df=my_assignments(me.value)
            if df.empty: ui.label(t('No active assignments.','No hay asignaciones activas.')).classes('text-gray-500'); return
            cols=[{'name':'assignment_id','label':'ID','field':'assignment_id'},
                  {'name':'location','label':t('Location','Ubicación'),'field':'location'},
                  {'name':'sku','label':'SKU','field':'sku'},
                  {'name':'expected_qty','label':t('Expected','Esperado'),'field':'expected_qty'},
                  {'name':'status','label':t('Status','Estado'),'field':'status'},
                  {'name':'lock_until','label':t('Lock Until','Bloqueo Hasta'),'field':'lock_until'}]
            ui.table(rows=df.to_dict('records'), columns=cols, row_key='assignment_id', pagination=10)
        refresh(); ui.button(t('Refresh','Actualizar'), on_click=refresh)

def page_perform_count():
    with ui.card():
        ui.label(t('Perform Count','Realizar Conteo')).classes('text-md font-medium')
        counter=ui.select(ASSIGN_NAME_OPTIONS, value='Aldo', label=t('Counter','Contador'))
        assignment_id=ui.input(label=t('Assignment ID','ID de Asignación'), placeholder='Scan or enter ID')
        counted_qty=ui.input(label=t('Counted QTY','Cantidad Contada'), input_type='number')
        issue_type=ui.select(['None','Over','Short','Damage','Other'], value='None', label=t('Issue Type','Tipo de Problema'))
        actual_pallet=ui.input(label=t('Actual Pallet','Tarima Actual')); actual_lot=ui.input(label=t('Actual LOT','Lote Actual')); note=ui.input(label=t('Note','Nota'))
        def do_submit():
            if not assignment_id.value or counted_qty.value in (None,''):
                ui.notify(t('Assignment ID and Counted QTY are required.','Se requieren ID de asignación y cantidad.'), type='warning'); return
            try: cq=int(float(counted_qty.value))
            except: ui.notify(t('Counted QTY must be a number.','Cantidad debe ser numérica.'), type='warning'); return
            submit_count(assignment_id.value.strip(), counter.value, cq, issue_type.value, actual_pallet.value or '', actual_lot.value or '', note.value or '')
            play_feedback(); ui.notify(t('Submitted. Returning to My Assignments...','Enviado. Regresando a Mis Asignaciones...'), type='positive')
            assignment_id.value=''; counted_qty.value=''; issue_type.value='None'; actual_pallet.value=''; actual_lot.value=''; note.value=''; ui.navigate.to('/my')
        ui.button(t('Submit','Enviar'), on_click=do_submit).props('color=primary')

def page_dashboard():
    with ui.card():
        ui.label('Dashboard').classes('text-md font-medium')
        a=read_csv_safe(ASSIGNMENTS_CSV); s=read_csv_safe(SUBMISSIONS_CSV)
        total_assigned=len(a); total_completed=int((a['status']=='Completed').sum()) if not a.empty else 0; total_pending=max(0,total_assigned-total_completed)
        ui.label(f"Assigned: {total_assigned}  |  Completed: {total_completed}  |  Pending: {total_pending}").classes('text-sm')
        def download_submissions():
            df=read_csv_safe(SUBMISSIONS_CSV)
            if df.empty: ui.notify(t('No submissions yet.','Sin envíos todavía.'), type='warning'); return
            ui.download(df.to_csv(index=False).encode('utf-8'), filename=f"submissions_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv")
        ui.button(t('Download Submissions (CSV)','Descargar Envíos (CSV)'), on_click=download_submissions)

def layout():
    topbar()
    with ui.tabs().classes('w-full') as tabs:
        t_assign=ui.tab(t('Assign Counts','Asignar Conteos')); t_my=ui.tab(t('My Assignments','Mis Asignaciones'))
        t_perform=ui.tab(t('Perform Count','Realizar Conteo')); t_dash=ui.tab('Dashboard')
    with ui.tab_panels(tabs, value=t_my).classes('w-full'):
        with ui.tab_panel(t_assign): page_assign_counts()
        with ui.tab_panel(t_my): page_my_assignments()
        with ui.tab_panel(t_perform): page_perform_count()
        with ui.tab_panel(t_dash): page_dashboard()

@ui.page('/')
def index():
    if 'lang' not in STATE: set_lang('en')
    if 'feedback' not in STATE: set_feedback(True, True)
    layout()

if __name__ in {'__main__','__mp_main__'}:
    ui.run(title='Cycle Count (NiceGUI)', storage_secret='cc_nicegui_secret', host='0.0.0.0', port=int(os.getenv('PORT','8080')))