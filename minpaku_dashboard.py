"""
民泊 施設ダッシュボード
実行: streamlit run minpaku_dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date
import calendar
import glob
import os
import io as _io
import json as _json
import urllib.request

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    _GDRIVE_OK = True
except ImportError:
    _GDRIVE_OK = False

# ─────────────────────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────────────────────

FACILITY_MAP = {
    # ── 自社物件（1部屋）──────────────────────────────────────
    'Sakura An｜北新宿':                       {'display': '北新宿（SakuraAn）',    'rooms': 1, 'capacity': '10名'},
    'Ann Stay Asakusabashi｜浅草橋':           {'display': '浅草橋（AnnStay）',      'rooms': 1, 'capacity': '5名'},
    'Home Oasis｜笹塚ホワイトハウス':          {'display': '笹塚ホワイトハウス',     'rooms': 1, 'capacity': '13名'},
    'R.Asakusa｜浅草（本所吾妻橋）':           {'display': '浅草（R.Asakusa）',      'rooms': 1, 'capacity': '5名'},
    'R.Ikebukuro｜池袋ロックビル':             {'display': '池袋ロックビル',         'rooms': 1, 'capacity': '5名'},
    'R.Shinjuku｜新宿（Green House市谷台町）': {'display': '新宿（GreenHouse）',      'rooms': 1, 'capacity': '8名'},
    'Shinjuku Blue｜下落合':                   {'display': '下落合（ShinjukuBlue）', 'rooms': 1, 'capacity': '12名'},
    # ── 自社物件（複数部屋）──────────────────────────────────
    'Feliz stay｜池袋フェリス': {
        'display': '池袋フェリス', 'rooms': 5, 'capacity': '3〜4名',
        'room_types': [
            {'label': '3人部屋（607・905）',     'rtm': 'Felizstay 3人部屋(607、905)',       'rooms': 2, 'capacity': '3名'},
            {'label': '4人部屋（507・702・707）', 'rtm': 'Felizstay 4人部屋(507, 702, 707)', 'rooms': 3, 'capacity': '4名'},
        ],
    },
    'Flag Suites｜幡ヶ谷': {
        'display': '幡ヶ谷（Flag）', 'rooms': 2, 'capacity': '8〜12名',
        'room_types': [
            {'label': '3F', 'rtm': '3F', 'rooms': 1, 'capacity': '12名'},
            {'label': '4F', 'rtm': '4F', 'rooms': 1, 'capacity': '8名'},
        ],
    },
    'Hotel IROIRO｜牛込柳町': {
        'display': '牛込柳町（IROIRO）', 'rooms': 2, 'capacity': '4〜15名',
        'room_types': [
            {'label': '1F', 'rtm': 'IROIRO 1F', 'rooms': 1, 'capacity': '4名'},
            {'label': '2F', 'rtm': 'IROIRO 2F', 'rooms': 1, 'capacity': '15名'},
        ],
    },
    # ── 代行物件（1部屋）──────────────────────────────────────
    'Hotel Hale Hale｜目白':     {'display': '目白（HaleHale）★代行',  'rooms': 1, 'capacity': '15名'},
    'Sasazuka Stay｜笹塚ステイ': {'display': '笹塚ステイ★代行',         'rooms': 1, 'capacity': '11名'},
    # ── 代行物件（複数部屋）──────────────────────────────────
    'ARiA STAY SHINAGAWA｜新馬場': {
        'display': '新馬場（ARiA）★代行', 'rooms': 27, 'capacity': '3〜7名',
        'room_types': [
            {'label': '3人部屋Aタイプ（3部屋）',  'rtm': '3人部屋Aタイプ',                'rooms': 3,  'capacity': '3名'},
            {'label': '3人部屋Bタイプ（11部屋）', 'rtm': '3人部屋Bタイプ',                'rooms': 11, 'capacity': '3名'},
            {'label': '3人部屋Cタイプ（4部屋）',  'rtm': '3人部屋Cタイプ',                'rooms': 4,  'capacity': '3名'},
            {'label': 'ペントハウス5人（1部屋）', 'rtm': '5人部屋ペントハウス(Penthouse)', 'rooms': 1,  'capacity': '5名'},
            {'label': '漫画部屋5人（1部屋）',     'rtm': '5人部屋漫画部屋(Manga)',         'rooms': 1,  'capacity': '5名'},
            {'label': '6人部屋（3部屋）',         'rtm': '6人部屋タイプ',                 'rooms': 3,  'capacity': '6名'},
            {'label': '7人部屋（4部屋）',         'rtm': '7人部屋タイプ',                 'rooms': 4,  'capacity': '7名'},
        ],
    },
    'TOMORU TOKYO Sasazuka｜TOMORU笹塚': {
        'display': '笹塚TOMORU★代行', 'rooms': 2, 'capacity': None,
        'room_types': [
            {'label': '2F', 'rtm': 'TOMORU 2F', 'rooms': 1, 'capacity': None},
            {'label': '3F', 'rtm': 'TOMORU 3F', 'rooms': 1, 'capacity': None},
        ],
    },
    'Vista FUJIMI｜富士見町': {
        'display': 'Vista FUJIMI（富士見）★代行', 'rooms': 12, 'capacity': '2〜3名',
        'room_types': [
            {'label': '01号室 1・2F', 'rtm': '富士見町 - 01号室 - 1・2F', 'rooms': 2, 'capacity': '2名'},
            {'label': '02号室 1・2F', 'rtm': '富士見町 - 02号室 - 1・2F', 'rooms': 2, 'capacity': '3名'},
            {'label': '03号室 1・2F', 'rtm': '富士見町 - 03号室 - 1・2F', 'rooms': 2, 'capacity': '3名'},
            {'label': '01号室 3・4F', 'rtm': '富士見町 - 01号室 - 3・4F', 'rooms': 2, 'capacity': '2名'},
            {'label': '02号室 3・4F', 'rtm': '富士見町 - 02号室 - 3・4F', 'rooms': 2, 'capacity': '3名'},
            {'label': '03号室 3・4F', 'rtm': '富士見町 - 03号室 - 3・4F', 'rooms': 2, 'capacity': '3名'},
        ],
    },
}

OCC_TARGETS = [
    (30,  0.80),
    (60,  0.70),
    (90,  0.50),
    (120, 0.30),
    (150, 0.20),
]

CSV_ROOTS = [
    r'C:\Users\ishiz\Downloads\AirHost_CSV',
    r'C:\Users\ishiz\Downloads',
]

TODAY           = date.today()
DRIVE_FOLDER_ID = '10SFTfWNehj8M9gEgGpFh-W-VmTLkrC2V'

# ─────────────────────────────────────────────────────────────
# データ読み込み・前処理
# ─────────────────────────────────────────────────────────────

def _parse_csv_bytes(raw: bytes):
    for enc in ('utf-8-sig', 'cp932', 'utf-8'):
        try:
            df = pd.read_csv(_io.BytesIO(raw), encoding=enc)
            if '物件名' in df.columns and 'チェックイン' in df.columns:
                return df
        except Exception:
            pass
    return None


COMBINED_FILENAME = 'AirHost_全予約データ.csv'


def _get_dfs_from_local():
    # まず統合ファイルを探す
    for root in CSV_ROOTS:
        combined = os.path.join(root, COMBINED_FILENAME)
        if os.path.exists(combined):
            try:
                with open(combined, 'rb') as fh:
                    df = _parse_csv_bytes(fh.read())
                if df is not None:
                    return [df]
            except Exception:
                pass
    # フォールバック: 個別ファイル
    dfs, seen = [], set()
    for root in CSV_ROOTS:
        for f in sorted(glob.glob(os.path.join(root, 'Booking_*.csv'))):
            abspath = os.path.abspath(f)
            if abspath in seen:
                continue
            seen.add(abspath)
            try:
                with open(abspath, 'rb') as fh:
                    df = _parse_csv_bytes(fh.read())
                if df is not None:
                    dfs.append(df)
            except Exception:
                pass
    return dfs


def _get_dfs_from_drive():
    creds = service_account.Credentials.from_service_account_info(
        dict(st.secrets['gcp_service_account']),
        scopes=['https://www.googleapis.com/auth/drive.readonly'],
    )
    svc   = build('drive', 'v3', credentials=creds, cache_discovery=False)
    items = svc.files().list(
        q=(f"'{DRIVE_FOLDER_ID}' in parents "
           f"and name = '{COMBINED_FILENAME}' "
           f"and trashed = false"),
        fields='files(id, name)',
    ).execute().get('files', [])
    if not items:
        return []
    buf = _io.BytesIO()
    dl  = MediaIoBaseDownload(buf, svc.files().get_media(fileId=items[0]['id']))
    done = False
    while not done:
        _, done = dl.next_chunk()
    df = _parse_csv_bytes(buf.getvalue())
    return [df] if df is not None else []


def _process_dfs(raw_dfs: list):
    df = pd.concat(raw_dfs, ignore_index=True)
    if 'AirHost予約ID' in df.columns:
        df = df.drop_duplicates(subset=['AirHost予約ID'], keep='last')
    if 'キャンセル' in df.columns:
        df = df[df['キャンセル'].isna() | (df['キャンセル'].astype(str).str.strip() == '')]
    if '状態' in df.columns:
        df = df[~df['状態'].astype(str).str.contains('キャンセル', na=False)]
    for col in ('受取金', '合計日数', 'ゲスト数', '大人', '子供', '幼児'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    cleaning = df['クリーニング代'] if 'クリーニング代' in df.columns else 0
    df['クリーニング代'] = pd.to_numeric(cleaning, errors='coerce').fillna(0)
    df['受取金_純'] = df['受取金'] - df['クリーニング代']
    df['国籍'] = df['国籍'].astype(str).replace({'nan': '', 'None': ''})

    for col in ('チェックイン', 'チェックアウト'):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    if '予約日' in df.columns:
        df['予約日'] = pd.to_datetime(df['予約日'], errors='coerce')
        def _strip_tz(s):
            s = pd.to_datetime(s, errors='coerce')
            if s.dt.tz is not None:
                return s.dt.tz_convert('UTC').dt.tz_localize(None)
            return s
        df['リードタイム日数'] = (_strip_tz(df['チェックイン']) - _strip_tz(df['予約日'])).dt.days
    return df


@st.cache_data(ttl=300)
def load_data():
    raw_dfs = []
    # Google Drive（本番）
    if _GDRIVE_OK and 'gcp_service_account' in st.secrets:
        try:
            raw_dfs = _get_dfs_from_drive()
        except Exception as e:
            st.warning(f'Drive読み込みエラー: {e}')
    # ローカル（開発・フォールバック）
    if not raw_dfs:
        raw_dfs = _get_dfs_from_local()
    if not raw_dfs:
        return pd.DataFrame()
    return _process_dfs(raw_dfs)


def add_months(d: date, n: int) -> date:
    m = (d.month - 1 + n)
    return date(d.year + m // 12, m % 12 + 1, 1)


def calc_month(df_fac: pd.DataFrame, year: int, month: int, rooms: int) -> dict:
    days  = calendar.monthrange(year, month)[1]
    avail = days * rooms
    rows  = df_fac[
        (df_fac['チェックイン'].dt.year  == year) &
        (df_fac['チェックイン'].dt.month == month)
    ]
    rev     = rows['受取金'].sum()
    rev_net = rows['受取金_純'].sum()
    nights  = rows['合計日数'].sum()
    occ     = nights / avail if avail > 0 else 0
    adr     = rev_net / nights if nights > 0 else 0
    revpar  = rev_net / avail  if avail  > 0 else 0
    guests  = int(rows['ゲスト数'].sum())
    lead_avg = None
    if 'リードタイム日数' in rows.columns:
        valid = rows['リードタイム日数'].dropna()
        valid = valid[valid >= 0]
        if len(valid) > 0:
            lead_avg = valid.mean()
    n_books   = len(rows)
    avg_guests = guests / n_books if n_books > 0 else 0
    return dict(rev=rev, rev_net=rev_net, occ=occ, adr=adr,
                revpar=revpar, guests=guests, avg_guests=avg_guests,
                nights=nights, avail=avail, bookings=n_books, days=days,
                lead_avg=lead_avg)


def calc_combined(df_fac: pd.DataFrame, sel_dates: list, rooms: int) -> dict:
    if not sel_dates:
        return dict(rev=0, rev_net=0, occ=0, adr=0, revpar=0, guests=0, avg_guests=0,
                    nights=0, avail=0, bookings=0, days=0, lead_avg=None)
    totals = dict(rev=0, rev_net=0, nights=0, avail=0, guests=0, bookings=0, days=0)
    lead_vals = []
    for d in sel_dates:
        m = calc_month(df_fac, d.year, d.month, rooms)
        for k in totals:
            totals[k] += m[k]
        if m['lead_avg'] is not None:
            lead_vals.append(m['lead_avg'])
    occ        = totals['nights']   / totals['avail']    if totals['avail']    > 0 else 0
    adr        = totals['rev_net']  / totals['nights']   if totals['nights']   > 0 else 0
    revpar     = totals['rev_net']  / totals['avail']    if totals['avail']    > 0 else 0
    avg_guests = totals['guests']   / totals['bookings'] if totals['bookings'] > 0 else 0
    lead_avg   = sum(lead_vals) / len(lead_vals)         if lead_vals          else None
    return dict(**totals, occ=occ, adr=adr, revpar=revpar, avg_guests=avg_guests, lead_avg=lead_avg)


def occ_target(lead_days: int):
    for days, target in OCC_TARGETS:
        if lead_days <= days:
            return target, days
    return None, None


# ─────────────────────────────────────────────────────────────
# 認証
# ─────────────────────────────────────────────────────────────

def _get_auth():
    """ログイン済みユーザー情報を返す。未ログインの場合はフォームを表示して停止。"""
    # secrets未設定 = ローカル開発モード（認証スキップ）
    if not st.secrets.get('master_password'):
        return {'type': 'master'}

    if st.session_state.get('_auth'):
        return st.session_state['_auth']

    # ログインフォーム
    st.markdown("""
<style>
[data-testid="stSidebar"]{display:none}
</style>
""", unsafe_allow_html=True)
    _c1, _c2, _c3 = st.columns([1, 1.4, 1])
    with _c2:
        st.markdown('<div style="height:60px"></div>', unsafe_allow_html=True)
        st.markdown("""
<div style="background:linear-gradient(135deg,#1a3a5c,#2c6fa8);color:white;
            padding:22px 28px;border-radius:10px;margin-bottom:24px;text-align:center">
  <div style="font-size:26px;font-weight:bold">🏠 民泊ダッシュボード</div>
  <div style="font-size:13px;opacity:0.8;margin-top:6px">管理者・オーナー用</div>
</div>
""", unsafe_allow_html=True)
        with st.form('login_form'):
            _uname = st.text_input('ユーザー名')
            _pwd   = st.text_input('パスワード', type='password')
            _ok    = st.form_submit_button('ログイン', use_container_width=True)
        if _ok:
            if _uname == 'master' and _pwd == st.secrets.get('master_password', ''):
                st.session_state['_auth'] = {'type': 'master'}
                st.rerun()
            _owners = st.secrets.get('owners', {})
            if _uname in _owners:
                _info = _owners[_uname]
                if _pwd == _info.get('password', ''):
                    st.session_state['_auth'] = {
                        'type':         'owner',
                        'fac_key':      _info['fac_key'],
                        'rt_label':     _info.get('rt_label', ''),
                        'display_name': _info.get('display_name', _uname),
                    }
                    st.rerun()
            st.error('ユーザー名またはパスワードが違います')
    st.stop()


# ─────────────────────────────────────────────────────────────
# ページ設定
# ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title='民泊ダッシュボード',
    page_icon='🏠',
    layout='wide',
)

df_all = load_data()
if df_all.empty:
    st.error('CSVデータが読み込めませんでした。')
    st.stop()

auth_user = _get_auth()
is_master = auth_user['type'] == 'master'

# ─ サイドバー ───────────────────────────────────────────────
with st.sidebar:
    if is_master:
        st.header('⚙️ 設定')
        # 施設・部屋タイプ選択（マスターのみ）
        fac_options = list(FACILITY_MAP.keys())
        fac_display = [FACILITY_MAP[k]['display'] for k in fac_options]
        sel_display = st.selectbox('施設', fac_display)
        fac_key  = fac_options[fac_display.index(sel_display)]
        fac_info = FACILITY_MAP[fac_key]

        room_types = fac_info.get('room_types', [])
        if room_types:
            rt_all_label = 'すべて'
            rt_choices   = [rt_all_label] + [rt['label'] for rt in room_types]
            rt_key       = f'rt_{fac_key}'
            rt_prev_key  = f'rt_prev_{fac_key}'
            if st.session_state.get('_last_fac') != fac_key:
                st.session_state[rt_key]      = [rt_all_label]
                st.session_state[rt_prev_key] = [rt_all_label]
                st.session_state['_last_fac'] = fac_key
            if rt_key not in st.session_state:
                st.session_state[rt_key]      = [rt_all_label]
                st.session_state[rt_prev_key] = [rt_all_label]

            def _rt_on_change():
                curr = list(st.session_state[rt_key])
                prev = list(st.session_state.get(rt_prev_key, [rt_all_label]))
                if not curr:
                    new = [rt_all_label]
                elif rt_all_label in curr and rt_all_label not in prev:
                    new = [rt_all_label]
                elif rt_all_label in curr and len(curr) > 1:
                    new = [x for x in curr if x != rt_all_label]
                else:
                    new = curr
                st.session_state[rt_key]      = new
                st.session_state[rt_prev_key] = new

            st.multiselect('部屋タイプ', rt_choices, key=rt_key, on_change=_rt_on_change)
            sel_rt_labels = st.session_state[rt_key]
            if rt_all_label in sel_rt_labels:
                sel_rtm = None
                rooms   = fac_info['rooms']
            else:
                _sel_rts = [rt for rt in room_types if rt['label'] in sel_rt_labels]
                sel_rtm  = [rt['rtm'] for rt in _sel_rts]
                rooms    = sum(rt['rooms'] for rt in _sel_rts)
        else:
            sel_rtm = None
            rooms   = fac_info['rooms']
    else:
        # オーナー: 施設・部屋タイプはログイン情報から固定
        fac_key  = auth_user['fac_key']
        fac_info = FACILITY_MAP.get(fac_key, {})
        rt_label = auth_user.get('rt_label', '')
        _rts     = fac_info.get('room_types', [])
        if rt_label and _rts:
            _matched = next((rt for rt in _rts if rt['label'] == rt_label), None)
            if _matched:
                sel_rtm = [_matched['rtm']]
                rooms   = _matched['rooms']
            else:
                sel_rtm = None
                rooms   = fac_info.get('rooms', 1)
        else:
            sel_rtm = None
            rooms   = fac_info.get('rooms', 1)
        st.markdown(f'**{auth_user.get("display_name", fac_info.get("display", ""))}**')
        st.caption('施設詳細ダッシュボード')

    # 月選択（共通）
    month_list   = [add_months(TODAY.replace(day=1), n) for n in range(-11, 1)]
    def _mlabel(m: date) -> str:
        suffix = ' ◀ 今月' if (m.year == TODAY.year and m.month == TODAY.month) else ''
        return f'{m.year}年{m.month}月{suffix}'
    month_labels = [_mlabel(m) for m in month_list]
    sel_labels   = st.multiselect('月（複数選択可）', month_labels, default=[month_labels[-1]])
    sel_dates    = [month_list[month_labels.index(l)] for l in sel_labels]
    sel_date     = sel_dates[-1] if sel_dates else TODAY.replace(day=1)
    sel_y, sel_m = sel_date.year, sel_date.month

    st.divider()
    if st.button('🔄 データ再読込'):
        st.cache_data.clear()
        st.rerun()
    st.caption(f'読込件数: {len(df_all):,} 件')

    # AirHostデータ手動取得（マスターのみ）
    if is_master:
        st.divider()
        if st.button('🚀 AirHostデータ取得'):
            gh_token = st.secrets.get('github_token', '')
            if not gh_token:
                st.error('Streamlit secrets に github_token が未設定です')
            else:
                req = urllib.request.Request(
                    'https://api.github.com/repos/ishizakiimovel-gif/minpaku-dashboard'
                    '/actions/workflows/airhost_export.yml/dispatches',
                    data=_json.dumps({'ref': 'master'}).encode(),
                    headers={
                        'Authorization': f'Bearer {gh_token}',
                        'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28',
                        'Content-Type': 'application/json',
                    },
                    method='POST',
                )
                try:
                    with urllib.request.urlopen(req) as resp:
                        if resp.status == 204:
                            st.success('✅ 実行をリクエストしました（1〜2分後に開始）')
                except urllib.error.HTTPError as e:
                    st.error(f'GitHub APIエラー {e.code}: {e.read().decode()}')
                except Exception as e:
                    st.error(f'エラー: {e}')
    if is_master:
        with st.expander('利用可能物件名（CSVから）'):
            for n in sorted(df_all['物件名'].dropna().unique()):
                st.text(n)
    # ログアウトボタン（認証が有効な場合のみ）
    if st.secrets.get('master_password'):
        st.divider()
        if st.button('ログアウト'):
            st.session_state['_auth'] = None
            st.rerun()

# 施設フィルタ
df_fac = df_all[df_all['物件名'] == fac_key].copy()
if sel_rtm and 'ルームタイプメニュー' in df_fac.columns:
    df_fac = df_fac[df_fac['ルームタイプメニュー'].isin(sel_rtm)]

# ─ ヘッダー帯 ───────────────────────────────────────────────
_banner_title   = '🏠 実績ダッシュボード' if is_master else f'🏠 {fac_info.get("display","").replace("★代行","")}'
_banner_sub     = '民泊施設 運営実績・稼働率管理' if is_master else '施設詳細ダッシュボード'
st.markdown(f"""
<div style="
  background: linear-gradient(135deg, #1a3a5c 0%, #2c6fa8 100%);
  color: white;
  padding: 18px 28px;
  border-radius: 10px;
  margin-bottom: 6px;
  box-shadow: 0 3px 10px rgba(0,0,0,0.15);
">
  <div style="font-size:26px;font-weight:bold;letter-spacing:0.5px">{_banner_title}</div>
  <div style="font-size:13px;opacity:0.8;margin-top:4px">{_banner_sub}</div>
</div>
""", unsafe_allow_html=True)

# ─ タブ（マスター：3タブ、オーナー：施設詳細のみ）──────────
if is_master:
    tab1, tab2, tab3 = st.tabs(['　📊 施設詳細　', '　📈 全施設サマリー　', '　🎯 稼働率モニター　'])
else:
    (tab1,) = st.tabs(['　📊 施設詳細　'])
    tab2 = tab3 = None

# ══ Tab 1: 施設詳細 ══════════════════════════════════════════
with tab1:
    _disp_title = fac_info.get('display', fac_key).replace('★代行', '')
    st.title(f'🏠 {_disp_title}')
    if not sel_dates:
        st.warning('左のメニューから月を選択してください。')
        st.stop()

    if len(sel_dates) == 1:
        period_label = f'{sel_y}年{sel_m}月　✅ 実績'
    else:
        first, last = sel_dates[0], sel_dates[-1]
        period_label = f'{first.year}年{first.month}月〜{last.year}年{last.month}月（{len(sel_dates)}ヶ月 合算）'
    st.subheader(period_label)

    # ─ KPI カード ─────────────────────────────────────────
    cur  = calc_combined(df_fac, sel_dates, rooms)
    prev_dates = [date(d.year - 1, d.month, 1) for d in sel_dates]
    prev = calc_combined(df_fac, prev_dates, rooms)

    def delta(c, p, is_pp=False):
        if p == 0:
            return None
        return f'{(c - p) * 100:.1f}pp' if is_pp else f'{(c / p - 1) * 100:+.1f}%'

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.metric('💰 売上',           f'¥{cur["rev"]:,.0f}',    delta=delta(cur['rev'],    prev['rev']))
    with c2:
        st.metric('🏷 ADR',            f'¥{cur["adr"]:,.0f}',    delta=delta(cur['adr'],    prev['adr']))
    with c3:
        st.metric('📈 RevPAR',         f'¥{cur["revpar"]:,.0f}', delta=delta(cur['revpar'], prev['revpar']))
    with c4:
        st.metric('🏨 稼働率',         f'{cur["occ"]*100:.1f}%', delta=delta(cur['occ'],    prev['occ'], is_pp=True))
    with c5:
        _avg_str   = f'{cur["avg_guests"]:.1f}名'  if cur['bookings'] > 0 else '―'
        _avg_delta = (f'{cur["avg_guests"] - prev["avg_guests"]:+.1f}名'
                      if prev['bookings'] > 0 else None)
        st.metric('👥 平均宿泊人数', _avg_str, delta=_avg_delta,
                  help='1予約あたりの平均ゲスト数')
    with c6:
        lead_str   = f'{cur["lead_avg"]:.0f}日前' if cur['lead_avg'] is not None else '―'
        prev_lead  = prev.get('lead_avg')
        lead_delta = None
        if cur['lead_avg'] is not None and prev_lead is not None:
            lead_delta = f'{cur["lead_avg"] - prev_lead:+.0f}日'
        st.metric('📅 予約リードタイム', lead_str, delta=lead_delta,
                  help='チェックイン月ベース：この月に泊まった予約が、平均して何日前に入ったか')

    if prev['bookings'] == 0:
        st.caption('⚠️ 前年同月のCSVデータがないため前年比は表示されません')

    st.divider()

    # ─ 月次推移グラフ ────────────────────────────────────
    st.subheader('📅 月次推移（前後6ヶ月）')

    chart_months = [add_months(TODAY.replace(day=1), n) for n in range(-6, 7)]
    x_labels, rev_vals, occ_vals, bar_colors = [], [], [], []

    for cm in chart_months:
        met = calc_month(df_fac, cm.year, cm.month, rooms)
        x_labels.append(f'{cm.year}/{cm.month}')
        rev_vals.append(met['rev'])
        occ_vals.append(met['occ'] * 100)
        is_f = cm > TODAY.replace(day=1)
        bar_colors.append('rgba(100,160,220,0.5)' if is_f else 'rgba(54,120,190,0.9)')

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Bar(
        x=x_labels, y=rev_vals,
        marker_color=bar_colors,
        name='売上（円）', yaxis='y1',
        text=[f'¥{v/10000:.0f}万' if v > 0 else '' for v in rev_vals],
        textposition='outside', textfont=dict(size=10),
    ))
    fig_trend.add_trace(go.Scatter(
        x=x_labels, y=occ_vals,
        name='稼働率（%）', yaxis='y2',
        mode='lines+markers+text',
        line=dict(color='orange', width=2), marker=dict(size=7),
        text=[f'{v:.0f}%' if v > 0 else '' for v in occ_vals],
        textposition='top center', textfont=dict(size=10, color='darkorange'),
    ))

    today_x = f'{TODAY.year}/{TODAY.month}'
    if today_x in x_labels:
        idx = x_labels.index(today_x)
        fig_trend.add_vline(x=idx - 0.5, line_dash='dot', line_color='gray', opacity=0.6,
                            annotation_text='今月', annotation_position='top right')

    fig_trend.update_layout(
        yaxis =dict(title='売上（円）', tickformat=',.0f', showgrid=True),
        yaxis2=dict(title='稼働率（%）', overlaying='y', side='right',
                    range=[0, 130], ticksuffix='%'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        height=400, margin=dict(t=50, b=40, l=60, r=60),
        plot_bgcolor='white', paper_bgcolor='white', xaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    st.divider()

    # ─ 稼働率 目標管理 ───────────────────────────────────
    st.subheader('🎯 稼働率 目標管理（今月・今後6ヶ月）')
    st.caption('リードタイム別目標: 30日以内→80% / 60日→70% / 90日→50% / 120日→30% / 150日→20%')

    _this_month  = TODAY.replace(day=1)
    target_months = [add_months(_this_month, n) for n in range(0, 7)]
    labels_f, occ_act, occ_tgt, tgt_labels, future_data = [], [], [], [], []

    for fm in target_months:
        lead     = (fm - TODAY).days
        tgt, thr = occ_target(lead)
        met      = calc_month(df_fac, fm.year, fm.month, rooms)
        _is_cur  = (fm == _this_month)
        labels_f.append(f'今月\n{fm.year}/{fm.month}' if _is_cur else f'{fm.year}/{fm.month}')
        occ_act.append(met['occ'] * 100)
        occ_tgt.append(tgt * 100 if tgt else None)
        tgt_labels.append(f'目標{tgt*100:.0f}% (〜{thr}日)' if tgt else '目標なし')
        tgt_nights  = round(tgt * met['days'] * rooms) if tgt else None
        cur_nights  = int(met['nights'])
        need_nights = max(0, tgt_nights - cur_nights) if tgt_nights is not None else None
        future_data.append({'fm': fm, 'lead': lead, 'tgt': tgt, 'is_cur': _is_cur,
                            'tgt_nights': tgt_nights, 'cur_nights': cur_nights,
                            'need_nights': need_nights, 'act_occ': met['occ']})

    bar_col_f = []
    for i, (act, tgt_v) in enumerate(zip(occ_act, occ_tgt)):
        if tgt_v is None:             bar_col_f.append('rgba(180,180,180,0.7)')
        elif act >= tgt_v:            bar_col_f.append('rgba(70,190,120,0.85)')
        elif act >= tgt_v * 0.8:      bar_col_f.append('rgba(255,180,50,0.85)')
        else:                         bar_col_f.append('rgba(220,80,80,0.85)')

    fig_tgt = go.Figure()
    fig_tgt.add_trace(go.Bar(
        x=labels_f, y=occ_act, marker_color=bar_col_f, name='現在の稼働率',
        text=[f'{v:.0f}%' for v in occ_act], textposition='outside',
    ))
    fig_tgt.add_trace(go.Scatter(
        x=labels_f, y=occ_tgt, mode='lines+markers', name='リードタイム目標',
        line=dict(color='red', dash='dash', width=2), marker=dict(size=8, symbol='diamond'),
        text=tgt_labels, hovertemplate='%{text}<extra></extra>',
    ))
    fig_tgt.update_layout(
        yaxis=dict(title='稼働率（%）', range=[0, 110], ticksuffix='%'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=320, margin=dict(t=50, b=40, l=60, r=40),
        plot_bgcolor='white', paper_bgcolor='white', xaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig_tgt, use_container_width=True)

    st.markdown('**📋 月別 予約日数の進捗**')
    cols_card = st.columns(len(future_data))
    for col, d in zip(cols_card, future_data):
        fm       = d['fm']
        is_cur   = d['is_cur']
        fm_hdr   = f'今月 {fm.year}/{fm.month}' if is_cur else f'{fm.year}/{fm.month}'
        lead_str = '今月実績' if is_cur else f'L:{d["lead"]}日'
        with col:
            if d['tgt_nights'] is None:
                st.markdown(
                    f'<div style="border:1px solid #ccc;border-radius:8px;padding:10px;'
                    f'text-align:center;background:#f9f9f9">'
                    f'<b>{fm_hdr}</b><br>'
                    f'<small>{lead_str}</small>'
                    f'<br>目標なし</div>',
                    unsafe_allow_html=True)
            else:
                need    = d['need_nights']
                cur     = d['cur_nights']
                tgt     = d['tgt_nights']
                tgt_pct = int(d['tgt'] * 100) if d['tgt'] else 0
                if need == 0:
                    color = '#2e7d32'
                    center_html = '<span style="font-size:30px">✅</span><br><span style="font-size:13px;color:#2e7d32">目標達成！</span>'
                else:
                    color = '#c62828' if d['act_occ'] < (d['tgt'] or 0) * 0.8 else '#e65100'
                    center_html = (
                        f'<span style="font-size:38px;font-weight:bold;color:{color}">{need}</span>'
                        f'<span style="font-size:16px;color:{color}">泊</span><br>'
                        f'<span style="font-size:12px;color:#888">{"残り" if is_cur else "あと"}必要</span>'
                    )
                _bdr = '2px solid #1565c0' if is_cur else '1px solid #ddd'
                st.markdown(
                    f'<div style="border:{_bdr};border-radius:8px;padding:10px 8px;text-align:center">'
                    f'<b>{fm_hdr}</b><br>'
                    f'<small style="color:#888">{lead_str} 目標{tgt_pct}%</small><br>'
                    f'<div style="margin:8px 0;line-height:1.3">{center_html}</div>'
                    f'<small style="color:#555">目標 {tgt}泊 / 現在 {cur}泊</small>'
                    f'</div>',
                    unsafe_allow_html=True)

    st.divider()

    # ─ 宿泊者プロフィール ─────────────────────────────────
    if len(sel_dates) == 1:
        prof_title = f'{sel_y}年{sel_m}月'
    else:
        first, last = sel_dates[0], sel_dates[-1]
        prof_title = f'{first.year}年{first.month}月〜{last.year}年{last.month}月（{len(sel_dates)}ヶ月）'
    st.subheader(f'🌍 宿泊者プロフィール — {prof_title}')

    prof_ym = {(d.year, d.month) for d in sel_dates}
    df_prof = df_fac[
        df_fac['チェックイン'].apply(
            lambda dt: (int(dt.year), int(dt.month)) in prof_ym if pd.notna(dt) else False
        )
    ].copy()

    if df_prof.empty:
        st.info('選択した月に予約データがありません。')
    else:
        col_nat, col_pax, col_child = st.columns(3)

        with col_nat:
            st.markdown('**① 国籍別**')
            df_nat = df_prof[df_prof['国籍'] != ''].copy()
            if df_nat.empty:
                st.info('国籍データなし')
            else:
                nat_grp = df_nat.groupby('国籍')['ゲスト数'].sum().sort_values(ascending=False)
                fig_nat = px.pie(names=nat_grp.index.tolist(), values=nat_grp.values.tolist(),
                                 color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_nat.update_traces(textinfo='label+percent', textposition='inside', sort=False)
                fig_nat.update_layout(height=300, margin=dict(t=10,b=10,l=10,r=10), showlegend=False)
                st.plotly_chart(fig_nat, use_container_width=True)

        with col_pax:
            cap = fac_info.get('capacity')
            if sel_rtm and len(sel_rtm) == 1:
                rt = next((rt for rt in room_types if rt['rtm'] == sel_rtm[0]), None)
                if rt and rt.get('capacity'):
                    cap = rt['capacity']
            cap_str = f'定員: {cap}' if cap else ''
            st.markdown(f'**② 宿泊人数別（予約件数）**　<small style="color:#888">{cap_str}</small>',
                        unsafe_allow_html=True)
            pax_cnt = df_prof['ゲスト数'].apply(lambda n: int(n)).value_counts().sort_index()
            fig_pax = px.pie(names=[f'{n}人' for n in pax_cnt.index], values=pax_cnt.values.tolist(),
                             color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_pax.update_traces(textinfo='label+percent', textposition='inside', sort=False)
            fig_pax.update_layout(height=300, margin=dict(t=10,b=10,l=10,r=10), showlegend=False)
            st.plotly_chart(fig_pax, use_container_width=True)

        with col_child:
            st.markdown('**③ 子連れ率**')
            has_child_cols = any(c in df_prof.columns for c in ('子供', '幼児'))
            if not has_child_cols:
                st.info('子供・幼児の列がCSVにないため表示できません。')
            else:
                child_mask = pd.Series([False] * len(df_prof), index=df_prof.index)
                if '子供' in df_prof.columns:
                    child_mask = child_mask | (df_prof['子供'] > 0)
                if '幼児' in df_prof.columns:
                    child_mask = child_mask | (df_prof['幼児'] > 0)
                n_child    = int(child_mask.sum())
                n_no_child = len(df_prof) - n_child
                fig_child = px.pie(
                    names=['子連れあり', '子連れなし'], values=[n_child, n_no_child],
                    color_discrete_map={'子連れあり': 'salmon', '子連れなし': 'lightsteelblue'},
                )
                fig_child.update_traces(textinfo='label+percent', textposition='inside')
                fig_child.update_layout(height=300, margin=dict(t=10,b=10,l=10,r=10), showlegend=False)
                st.plotly_chart(fig_child, use_container_width=True)


# ══ Tab 2: 全施設サマリー ════════════════════════════════════
if tab2 is not None:
 with tab2:
    st.title('📈 全施設 月次サマリー')
    if not sel_dates:
        st.warning('左のメニューから月を選択してください。')
    else:
        if len(sel_dates) == 1:
            t2_period = f'{sel_dates[0].year}年{sel_dates[0].month}月'
        else:
            _f, _l = sel_dates[0], sel_dates[-1]
            t2_period = f'{_f.year}年{_f.month}月〜{_l.year}年{_l.month}月（{len(sel_dates)}ヶ月 合算）'
        st.subheader(t2_period)

        def _is_jisha(key):
            return '★代行' not in FACILITY_MAP[key]['display']

        def _met_disp(m, pm):
            _od = f'{(m["occ"] - pm["occ"])*100:+.1f}pp' if pm['bookings'] > 0 else '―'
            return {
                '売上':         f'¥{m["rev"]:,.0f}'     if m['rev']     > 0 else '―',
                '稼働率':       f'{m["occ"]*100:.1f}%'  if m['nights']  > 0 else '―',
                '前年比(稼働)': _od,
                'ADR':          f'¥{m["adr"]:,.0f}'     if m['adr']     > 0 else '―',
                'RevPAR':       f'¥{m["revpar"]:,.0f}'  if m['revpar']  > 0 else '―',
                'リードタイム': f'{m["lead_avg"]:.0f}日前' if m['lead_avg'] is not None else '―',
            }

        # 全施設のメトリクスを収集（施設合計＋部屋タイプ内訳）
        summary_data = []
        for _key, _info in FACILITY_MAP.items():
            _df      = df_all[df_all['物件名'] == _key].copy()
            _pd_list = [date(d.year - 1, d.month, 1) for d in sel_dates]
            _m       = calc_combined(_df, sel_dates,  _info['rooms'])
            _mp      = calc_combined(_df, _pd_list,   _info['rooms'])
            _rt_rows = []
            for _rt in _info.get('room_types', []):
                _df_rt = _df.copy()
                if 'ルームタイプメニュー' in _df_rt.columns:
                    _df_rt = _df_rt[_df_rt['ルームタイプメニュー'] == _rt['rtm']]
                _rm  = calc_combined(_df_rt, sel_dates, _rt['rooms'])
                _rmp = calc_combined(_df_rt, _pd_list,  _rt['rooms'])
                _rt_rows.append({'name': _rt['label'], **_met_disp(_rm, _rmp)})
            summary_data.append({
                'name':     _info['display'].replace('★代行', ''),
                'kind':     '自社' if _is_jisha(_key) else '代行',
                '_rev':     _m['rev'],
                '_rev_net': _m['rev_net'],
                '_nights':  _m['nights'],
                '_avail':   _m['avail'],
                '_rt_rows': _rt_rows,
                **_met_disp(_m, _mp),
            })

        _COLS = [
            ('施設',         'name',          'left'),
            ('売上',         '売上',          'right'),
            ('稼働率',       '稼働率',        'center'),
            ('前年比(稼働)', '前年比(稼働)',   'center'),
            ('ADR',          'ADR',           'right'),
            ('RevPAR',       'RevPAR',        'right'),
            ('リードタイム', 'リードタイム',  'center'),
        ]

        def _build_tbl(fac_rows, is_jisha):
            hdr_bg  = '#e8f0fa' if is_jisha else '#faecd8'
            hdr_bdr = '#5586c8' if is_jisha else '#c87040'
            html = '<table style="width:100%;border-collapse:collapse;font-size:14px">'
            html += (f'<thead><tr style="background:{hdr_bg};'
                     f'border-bottom:2px solid {hdr_bdr}">')
            for hdr, _, align in _COLS:
                html += (f'<th style="padding:8px 12px;text-align:{align};'
                         f'white-space:nowrap">{hdr}</th>')
            html += '</tr></thead><tbody>'
            for row in fac_rows:
                # 施設合計行（太字）
                html += '<tr style="background:#fff;border-bottom:1px solid #dde">'
                for _, key, align in _COLS:
                    v = row.get(key, '―')
                    html += (f'<td style="padding:8px 12px;text-align:{align};'
                             f'font-weight:bold">{v}</td>')
                html += '</tr>'
                # 部屋タイプ内訳行（インデント・小さめ）
                for rt in row.get('_rt_rows', []):
                    html += '<tr style="background:#f7f8fa;border-bottom:1px solid #eee">'
                    for _, key, align in _COLS:
                        v = rt.get(key, '―')
                        if key == 'name':
                            html += (f'<td style="padding:5px 12px 5px 28px;'
                                     f'text-align:{align};color:#555;font-size:13px">'
                                     f'└ {v}</td>')
                        else:
                            html += (f'<td style="padding:5px 12px;text-align:{align};'
                                     f'color:#555;font-size:13px">{v}</td>')
                    html += '</tr>'
            html += '</tbody></table>'
            return html

        for _label, _jisha in [('自社', True), ('代行', False)]:
            _rows = [r for r in summary_data if (r['kind'] == '自社') == _jisha]
            if not _rows:
                continue
            _rows = sorted(_rows, key=lambda x: x['_rev'], reverse=True)

            # 合計値を計算
            _tot_rev     = sum(r['_rev']     for r in _rows)
            _tot_rev_net = sum(r['_rev_net'] for r in _rows)
            _tot_nights  = sum(r['_nights']  for r in _rows)
            _tot_avail   = sum(r['_avail']   for r in _rows)
            _comb_occ    = _tot_nights  / _tot_avail   if _tot_avail  > 0 else 0
            _comb_adr    = _tot_rev_net / _tot_nights  if _tot_nights > 0 else 0
            _comb_revpar = _tot_rev_net / _tot_avail   if _tot_avail  > 0 else 0

            st.markdown(f'### {_label}物件')

            _tot_bg     = '#e8f4fd' if _jisha else '#fdf0e8'
            _tot_border = '#1565c0' if _jisha else '#c75000'
            st.markdown(
                f'<div style="background:{_tot_bg};border-left:5px solid {_tot_border};'
                f'border-radius:6px;padding:12px 20px;margin-bottom:10px">'
                f'<b style="font-size:16px">合計</b>&emsp;'
                f'売上: <b style="font-size:17px">¥{_tot_rev:,.0f}</b>'
                f'&emsp;稼働率（合算）: <b>{_comb_occ*100:.1f}%</b>'
                f'&emsp;ADR: <b>¥{_comb_adr:,.0f}</b>'
                f'&emsp;RevPAR: <b>¥{_comb_revpar:,.0f}</b>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.markdown(_build_tbl(_rows, _jisha), unsafe_allow_html=True)
            st.write('')


# ══ Tab 3: 稼働率モニター ════════════════════════════════════
if tab3 is not None:
 with tab3:
    st.title('🎯 稼働率モニター')
    st.caption('リードタイム別目標: 30日以内→80% / 60日→70% / 90日→50% / 120日→30% / 150日→20%　｜　❌ 大幅未達　⚠️ 要注意　✅ 達成')

    _show_alert = st.checkbox('要注意・未達のみ表示')
    # 今月 + 次4ヶ月
    _this_m     = TODAY.replace(day=1)
    _mon_months = [add_months(_this_m, n) for n in range(0, 5)]

    def _occ_cell(met, tgt, rooms):
        _tgt_n = round(tgt * met['days'] * rooms) if tgt else None
        _cur_n = int(met['nights'])
        _need  = max(0, _tgt_n - _cur_n) if _tgt_n is not None else None
        if tgt is None:
            _bg, _fg, _icon = '#f0f0f0', '#aaa', '―'
        elif met['occ'] >= tgt:
            _bg, _fg, _icon = '#f0f0f0', '#888', '✅'
        elif met['occ'] >= tgt * 0.8:
            _bg, _fg, _icon = '#fff8e1', '#e65100', '⚠️'
        else:
            _bg, _fg, _icon = '#ffebee', '#c62828', '❌'
        _occ_str  = f'{met["occ"]*100:.0f}%'
        _need_str = f'あと{_need}泊' if _need and _need > 0 else ('達成' if _need == 0 else '―')
        return {'bg': _bg, 'fg': _fg, 'icon': _icon, 'occ_str': _occ_str, 'need_str': _need_str}

    # 全施設を事前計算（やばい順ソートのため）
    _fac_list = []
    for _key, _info in FACILITY_MAP.items():
        _df_f   = df_all[df_all['物件名'] == _key].copy()
        _frooms = _info['rooms']
        _cells  = []
        _score  = 0
        for _fm in _mon_months:
            _lead   = (_fm - TODAY).days
            _tgt, _ = occ_target(_lead)
            _met    = calc_month(_df_f, _fm.year, _fm.month, _frooms)
            _c      = _occ_cell(_met, _tgt, _frooms)
            _cells.append(_c)
            # 今月は実績確認のみでスコアに加算しない
            if _fm != _this_m:
                _score += 2 if _c['icon'] == '❌' else (1 if _c['icon'] == '⚠️' else 0)
        _rt_data = []
        for _rt in _info.get('room_types', []):
            _df_rt = _df_f.copy()
            if 'ルームタイプメニュー' in _df_rt.columns:
                _df_rt = _df_rt[_df_rt['ルームタイプメニュー'] == _rt['rtm']]
            _rt_cells = []
            for _fm in _mon_months:
                _lead   = (_fm - TODAY).days
                _tgt, _ = occ_target(_lead)
                _met_rt = calc_month(_df_rt, _fm.year, _fm.month, _rt['rooms'])
                _rt_cells.append(_occ_cell(_met_rt, _tgt, _rt['rooms']))
            _rt_data.append({'label': _rt['label'], 'cells': _rt_cells})
        _fac_list.append((_score, _key, _info, _cells, _rt_data))

    _fac_list.sort(key=lambda x: x[0], reverse=True)

    # ── HTML テーブル（スティッキーヘッダー付き）─────────────
    def _cell_html(c, big=True):
        fs1 = '14px' if big else '12px'
        fs2 = '13px' if big else '11px'
        pd  = '6px 6px' if big else '3px 4px'
        fw  = 'bold' if big else 'normal'
        return (
            f'<div style="background:{c["bg"]};border-radius:5px;'
            f'padding:{pd};text-align:center;margin:1px 0;white-space:nowrap">'
            f'<span style="font-size:{fs1};font-weight:{fw};color:{c["fg"]}">'
            f'{c["icon"]} {c["occ_str"]}</span>'
            f'&nbsp;<span style="font-size:{fs2};color:{c["fg"]}">{c["need_str"]}</span>'
            f'</div>'
        )

    # ヘッダー列の定義
    _col_w = ['28%'] + [f'{72 // len(_mon_months)}%'] * len(_mon_months)
    _col_w_style = ''.join(f'<col style="width:{w}">' for w in _col_w)

    def _th(fm):
        is_cur = (fm == _this_m)
        lead   = (fm - TODAY).days
        tgt, _ = occ_target(lead)
        ts     = f'目標{tgt*100:.0f}%' if tgt else '―'
        label  = f'今月　{fm.year}/{fm.month}' if is_cur else f'{fm.year}/{fm.month}'
        sub    = '今月実績' if is_cur else f'L{lead}日 {ts}'
        bg     = '#eef5ff' if is_cur else '#f4f4f8'
        return (
            f'<th style="padding:10px 8px;text-align:center;background:{bg};'
            f'border-bottom:2px solid #c0c8d8;white-space:nowrap">'
            f'<b>{label}</b><br>'
            f'<span style="font-size:11px;color:#666">{sub}</span></th>'
        )

    html = (
        '<div style="overflow-y:auto;max-height:72vh;border:1px solid #dde;border-radius:8px">'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px"><colgroup>{_col_w_style}</colgroup>'
        '<thead style="position:sticky;top:0;z-index:10;background:white;'
        'box-shadow:0 2px 5px rgba(0,0,0,0.08)">'
        '<tr><th style="padding:10px 12px;text-align:left;background:#f4f4f8;'
        'border-bottom:2px solid #c0c8d8">施設</th>'
    )
    for _fm in _mon_months:
        html += _th(_fm)
    html += '</tr></thead><tbody>'

    for _score, _key, _info, _cells, _rt_data in _fac_list:
        if _show_alert and _score == 0:
            continue
        _disp = _info['display'].replace('★代行', ' 代行')
        html += (
            f'<tr style="border-bottom:1px solid #dde;background:white">'
            f'<td style="padding:8px 12px;font-weight:bold">{_disp}</td>'
        )
        for _i, _c in enumerate(_cells):
            _bg_td = '#f0f4ff' if _mon_months[_i] == _this_m else 'transparent'
            html += f'<td style="padding:4px 6px;background:{_bg_td}">{_cell_html(_c, big=True)}</td>'
        html += '</tr>'
        for _rt in _rt_data:
            html += (
                f'<tr style="border-bottom:1px solid #eee;background:#f8f8fb">'
                f'<td style="padding:4px 12px 4px 26px;color:#555;font-size:13px">'
                f'└ {_rt["label"]}</td>'
            )
            for _i, _c in enumerate(_rt['cells']):
                _bg_td = '#f0f4ff' if _mon_months[_i] == _this_m else 'transparent'
                html += f'<td style="padding:2px 6px;background:{_bg_td}">{_cell_html(_c, big=False)}</td>'
            html += '</tr>'

    html += '</tbody></table></div>'
    st.markdown(html, unsafe_allow_html=True)
