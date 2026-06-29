# -*- coding: utf-8 -*-
"""
AirHost CSV 自動エクスポートスクリプト（改良版）
- Cookieを保存して再ログイン不要にする
- ダウンロード間にランダム待機（人間らしく）
- 取得範囲：過去2ヶ月 + 未来6ヶ月
- playwright-stealth でbot検知を回避
"""
import io, os, json, time, re, base64, sys, random, imaplib, email as _email
from email.utils import parsedate_to_datetime
from datetime import date, timedelta
from pathlib import Path
from dateutil.relativedelta import relativedelta
import pandas as pd
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# CI環境（GitHub Actions）かどうか
IS_CI = os.environ.get('CI', '').lower() == 'true'

# ─── 設定 ────────────────────────────────────────────────────
SIGN_IN_URL      = 'https://pms.airhost.co/ja/sign_in'
EXPORT_URL       = 'https://pms.airhost.co/ja/import-export/export-bookings'
AIRHOST_EMAIL    = 'ishizaki.imovel@gmail.com'
AIRHOST_PASS     = os.environ.get('AIRHOST_PASS', '')

GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')

DRIVE_FOLDER_ID      = '10SFTfWNehj8M9gEgGpFh-W-VmTLkrC2V'
DRIVE_SUBFOLDER_NAME = '元データ'
COMPANY_SELECT_URL   = 'https://pms.airhost.co/ja/company-select'

# ダウンロード対象の会社一覧（name: AirHost上の表示名, prefix: ファイル名の接頭辞）
# 山王は月次（毎月10日）に別スケジュールで実行するため週次からは除外
COMPANIES = [
    {'name': '合同会社あおい', 'prefix': ''},
]

# ローカルとCIで切り替わるパス
GMAIL_CREDS_PATH = os.environ.get(
    'GMAIL_CREDS_PATH',
    r'C:\Users\ishiz\google-workspace-mcp\credentials\ishizaki.imovel@gmail.com.json'
)
DOWNLOAD_DIR = Path(os.environ.get('DOWNLOAD_DIR', r'C:\Users\ishiz\Downloads\AirHost_CSV'))
COOKIE_FILE  = Path(os.environ.get('COOKIE_FILE',  r'C:\Users\ishiz\Downloads\airhost_cookies.json'))

# ─── 取得対象の日付レンジ（過去2ヶ月 + 未来6ヶ月）──────────
def get_date_ranges():
    today  = date.today()
    start  = today.replace(day=1) - relativedelta(months=2)   # 2ヶ月前の月初
    end_mo = today.replace(day=1) + relativedelta(months=7)   # 6ヶ月先の月末を含む次月初
    ranges = []
    cursor = start
    while cursor < end_mo:
        chunk_end = cursor + relativedelta(months=2) - timedelta(days=1)
        if chunk_end >= end_mo:
            chunk_end = end_mo - timedelta(days=1)
        ranges.append((cursor, chunk_end))
        cursor += relativedelta(months=2)
    return ranges

# ─── Gmail 2FAコード取得（IMAP + App Password）───────────────
def read_2fa_code(wait_sec=90):
    """Gmail App Password + IMAP で2FAコードを取得する（OAuth不要・期限切れなし）"""
    start_time = time.time()
    print('  2FAコード待機中（IMAP）...')
    # IMAP SINCE は英語月名必須（ロケール非依存で生成）
    _MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    _today  = date.today()
    since_str = f'{_today.day:02d}-{_MONTHS[_today.month-1]}-{_today.year}'
    # Gmail はタブ分類で INBOX 以外に入る場合があるため複数フォルダを検索
    SEARCH_FOLDERS = ['INBOX', '"[Gmail]/All Mail"']
    for attempt in range(wait_sec // 5):
        time.sleep(5)
        try:
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            mail.login(AIRHOST_EMAIL, GMAIL_APP_PASSWORD)
            found_code = None
            for folder in SEARCH_FOLDERS:
                rv, _ = mail.select(folder)
                if rv != 'OK':
                    continue
                # 今日届いた未読メールのみ（16,000件超の全未読を舐めるのを防ぐ）
                _, nums = mail.search(None, f'UNSEEN SINCE {since_str}')
                msg_nums = nums[0].split()
                if attempt == 0:
                    print(f'    {folder}: 今日の未読{len(msg_nums)}件')
                for num in reversed(msg_nums):  # 新しい順（降順）に確認
                    _, data = mail.fetch(num, '(RFC822)')
                    msg  = _email.message_from_bytes(data[0][1])
                    # msg.get() は encoded header を Header オブジェクトで返す場合があるため str() で変換
                    from_hdr = str(msg.get('From', '')).lower()
                    subj_hdr = str(msg.get('Subject', '')).lower()
                    # From か Subject に airhost が含まれるメールのみ処理
                    if 'airhost' not in from_hdr and 'airhost' not in subj_hdr:
                        continue
                    # この関数が呼ばれる前に届いていた古いメール（60秒以上前）はスキップ
                    try:
                        mail_ts = parsedate_to_datetime(str(msg.get('Date', ''))).timestamp()
                        if mail_ts < start_time - 60:
                            print(f'    古いコードをスキップ（{int(start_time - mail_ts)}秒前のメール）')
                            continue
                    except Exception:
                        pass
                    body = ''
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                break
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                    m = re.search(r'\b(\d{6})\b', body)
                    if m:
                        mail.store(num, '+FLAGS', '\\Seen')
                        found_code = m.group(1)
                        break
                if found_code:
                    break
            mail.logout()
            if found_code:
                print(f'  コード取得: {found_code}')
                return found_code
        except Exception as e:
            print(f'  IMAPエラー({attempt+1}): {e}')
    print('  ERROR: 2FAコード取得失敗（IMAP）')
    return None

# ─── Driveアップロード ────────────────────────────────────────
def upload_to_drive(filepath, drive_svc, folder_id=None):
    if folder_id is None:
        folder_id = DRIVE_FOLDER_ID
    name = Path(filepath).name
    res  = drive_svc.files().list(
        q=f"'{folder_id}' in parents and name='{name}' and trashed=false",
        fields='files(id)'
    ).execute()
    existing = res.get('files', [])
    media    = MediaFileUpload(str(filepath), mimetype='text/csv')
    if existing:
        drive_svc.files().update(fileId=existing[0]['id'], media_body=media).execute()
        print(f'  Drive更新: {name}')
    else:
        drive_svc.files().create(
            body={'name': name, 'parents': [folder_id]},
            media_body=media
        ).execute()
        print(f'  Drive作成: {name}')


# ─── 元データサブフォルダ取得or作成 ──────────────────────────
def get_or_create_subfolder(drive_svc):
    res = drive_svc.files().list(
        q=(f"'{DRIVE_FOLDER_ID}' in parents"
           f" and name='{DRIVE_SUBFOLDER_NAME}'"
           f" and mimeType='application/vnd.google-apps.folder'"
           f" and trashed=false"),
        fields='files(id)'
    ).execute()
    files = res.get('files', [])
    if files:
        return files[0]['id']
    folder = drive_svc.files().create(
        body={
            'name': DRIVE_SUBFOLDER_NAME,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [DRIVE_FOLDER_ID]
        },
        fields='id'
    ).execute()
    print(f'  「{DRIVE_SUBFOLDER_NAME}」フォルダを作成: {folder["id"]}')
    return folder['id']


# ─── 元データ内に実行日付のサブフォルダを作成 ─────────────────
def get_or_create_date_subfolder(drive_svc, subfolder_id):
    """元データ/YYYY-MM-DD/ フォルダを作成して返す"""
    today_str = date.today().strftime('%Y-%m-%d')
    res = drive_svc.files().list(
        q=(f"'{subfolder_id}' in parents"
           f" and name='{today_str}'"
           f" and mimeType='application/vnd.google-apps.folder'"
           f" and trashed=false"),
        fields='files(id)'
    ).execute()
    files = res.get('files', [])
    if files:
        return files[0]['id']
    folder = drive_svc.files().create(
        body={
            'name':     today_str,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents':  [subfolder_id]
        },
        fields='id'
    ).execute()
    print(f'  日付フォルダ作成: {today_str}')
    return folder['id']


# ─── 既存期間別CSVをサブフォルダへ移動（初回のみ）────────────
def migrate_to_subfolder(drive_svc, subfolder_id):
    res = drive_svc.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and name contains 'Booking_20' and trashed=false",
        fields='files(id, name)'
    ).execute()
    for f in res.get('files', []):
        drive_svc.files().update(
            fileId=f['id'],
            addParents=subfolder_id,
            removeParents=DRIVE_FOLDER_ID
        ).execute()
        print(f'  移動: {f["name"]} → {DRIVE_SUBFOLDER_NAME}/')

# ─── 日付入力（Ant Design RangePicker）─────────────────────
def set_date_range(page, start_dt, end_dt):
    start_str = start_dt.strftime('%Y-%m-%d')
    end_str   = end_dt.strftime('%Y-%m-%d')

    page.keyboard.press('Escape')
    time.sleep(0.3)

    si = page.query_selector('#dateRange')
    if not si:
        print('  開始日inputが見つからない')
        return False

    si.click(click_count=3)
    time.sleep(0.2)
    si.type(start_str)
    time.sleep(0.5)

    page.keyboard.press('Tab')
    time.sleep(0.3)
    page.keyboard.press('Control+a')
    time.sleep(0.1)
    page.keyboard.type(end_str)
    time.sleep(0.3)
    page.keyboard.press('Enter')
    time.sleep(0.5)
    page.keyboard.press('Escape')
    time.sleep(0.5)
    return True

# ─── ログインフロー ────────────────────────────────────────
def do_login(page):
    print('ログイン中...')
    page.goto(SIGN_IN_URL)
    page.wait_for_load_state('networkidle')
    time.sleep(2)
    page.fill('#email', AIRHOST_EMAIL)
    page.fill('#password', AIRHOST_PASS)
    page.click('button[type="submit"]')

    # フォーム送信直後のページ状態をスクリーンショットで記録（ボット検知診断用）
    time.sleep(3)
    ss_path = Path('/tmp/login_debug.png')
    page.screenshot(path=str(ss_path), full_page=True)
    print(f'  スクリーンショット保存: {ss_path}  URL={page.url}')

    # 2FA（メール到着まで最大30秒待つ）
    try:
        page.wait_for_selector('#otpCode', timeout=30000)
        code = read_2fa_code()
        if not code:
            print('  2FAコード取得失敗 → ログイン中断')
            return False
        page.fill('#otpCode', code)
        page.click('button[type="submit"]')
        print('  2FAコード入力完了')
    except Exception as e:
        print(f'  2FAなし（または待機タイムアウト）: {e}')

    # 会社選択画面まで待つ
    try:
        page.wait_for_selector('text=合同会社あおい', timeout=20000)
        print('  会社選択画面に到達')
        return True
    except Exception:
        print(f'  ログイン失敗（会社選択画面に到達せず）: URL={page.url}')
        return False


# ─── 会社選択 ──────────────────────────────────────────────────
def select_company(page, company_name):
    """会社選択画面に移動して指定の会社を選択する"""
    page.goto(COMPANY_SELECT_URL)
    page.wait_for_load_state('networkidle', timeout=20000)
    time.sleep(2)
    btn = page.query_selector(f'text={company_name}')
    if btn:
        btn.click()
        page.wait_for_load_state('networkidle', timeout=30000)
        print(f'  会社選択: {company_name}')
        return True
    print(f'  会社が見つかりません: {company_name}')
    return False

# ─── Cookie を使ってセッション再利用を試みる ────────────────
def ensure_logged_in(page, context):
    """Cookieがあれば再利用、なければ/期限切れならフルログイン（会社選択は select_company() で別途行う）"""
    if COOKIE_FILE.exists():
        print('Cookie読み込み中...')
        cookies = json.loads(COOKIE_FILE.read_text())
        context.add_cookies(cookies)
        page.goto(COMPANY_SELECT_URL)
        time.sleep(3)
        if SIGN_IN_URL not in page.url:
            print('Cookie有効: ログインスキップ')
            return True
        print('Cookie期限切れ → 再ログイン')

    ok = do_login(page)
    if ok:
        cookies = context.cookies()
        COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))
        print('Cookie保存完了')
    return ok

# ─── メイン ──────────────────────────────────────────────────
def main():
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    # Drive 認証（Gmail は IMAP + App Password で行うため gmail_svc 不要）
    with open(GMAIL_CREDS_PATH) as f:
        creds_data = json.load(f)
    drive_creds = Credentials.from_authorized_user_info(creds_data)
    if drive_creds.expired and drive_creds.refresh_token:
        drive_creds.refresh(Request())
    drive_svc = build('drive', 'v3', credentials=drive_creds, cache_discovery=False)
    print('Drive認証 OK')

    # 元データサブフォルダ取得・作成、既存ファイル移動、日付サブフォルダ作成
    subfolder_id = get_or_create_subfolder(drive_svc)
    migrate_to_subfolder(drive_svc, subfolder_id)
    date_subfolder_id = get_or_create_date_subfolder(drive_svc, subfolder_id)

    date_ranges = get_date_ranges()
    print(f'取得範囲: {date_ranges[0][0]} 〜 {date_ranges[-1][1]} ({len(date_ranges)}分割)')

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=IS_CI,
            args=['--no-sandbox', '--disable-dev-shm-usage'] if IS_CI else []
        )
        context = browser.new_context(accept_downloads=True)
        page    = context.new_page()

        # Stealth 適用（bot検知回避）
        Stealth().use_sync(page)

        # ログイン or Cookie再利用
        ok = ensure_logged_in(page, context)
        if not ok:
            print('ログイン失敗')
            # 診断用スクリーンショットをDriveにアップロード
            ss_path = Path('/tmp/login_debug.png')
            if ss_path.exists():
                try:
                    img_data = ss_path.read_bytes()
                    media = MediaIoBaseUpload(io.BytesIO(img_data), mimetype='image/png')
                    drive_svc.files().create(
                        body={'name': f'login_debug_{date.today()}.png', 'parents': [DRIVE_FOLDER_ID]},
                        media_body=media
                    ).execute()
                    print(f'  スクリーンショットをDriveにアップロードしました: login_debug_{date.today()}.png')
                except Exception as e:
                    print(f'  スクリーンショットアップロード失敗: {e}')
            browser.close()
            return

        # ─ 会社別CSVダウンロードループ ─
        current_month_start = date.today().replace(day=1)

        for company in COMPANIES:
            co_name   = company['name']
            co_prefix = company['prefix']
            print(f'\n{"="*40}\n会社: {co_name}\n{"="*40}')

            if not select_company(page, co_name):
                print(f'  スキップ: {co_name}')
                continue

            for i, (start_dt, end_dt) in enumerate(date_ranges):
                prefix_part = f'{co_prefix}_' if co_prefix else ''
                fname = f'Booking_{prefix_part}{start_dt.strftime("%Y%m%d")}_{end_dt.strftime("%Y%m%d")}.csv'
                print(f'\n[{i+1}/{len(date_ranges)}] {start_dt} 〜 {end_dt}  ({co_name})')

                # 確定月スキップ：期間が今月より前に終わっていて、かつ元データに保存済みならスキップ
                if end_dt < current_month_start:
                    res = drive_svc.files().list(
                        q=f"'{subfolder_id}' in parents and name='{fname}' and trashed=false",
                        fields='files(id)'
                    ).execute()
                    if res.get('files'):
                        print(f'  確定済み・スキップ（元データに保存済み）')
                        continue

                success = False
                for attempt in range(2):
                    # エクスポートページへ（毎回新鮮な状態）
                    page.goto(EXPORT_URL)
                    time.sleep(3)

                    # ログアウト・会社切替されていたら再ログイン＋会社選択
                    if SIGN_IN_URL in page.url or 'company-select' in page.url:
                        print('  セッション切れ → 再ログイン')
                        do_login(page)
                        cookies = context.cookies()
                        COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))
                        select_company(page, co_name)
                        page.goto(EXPORT_URL)
                        time.sleep(3)

                    # アコーディオン展開（テキストで確実に「予約データのエクスポート」を開く）
                    try:
                        page.click('text=予約データのエクスポート', timeout=10000)
                        page.wait_for_selector('#dateRange', timeout=10000)
                    except Exception as e:
                        print(f'  アコーディオン展開失敗 (attempt {attempt+1}): {e}')
                        continue

                    # 日付セット
                    if not set_date_range(page, start_dt, end_dt):
                        print(f'  日付セット失敗 (attempt {attempt+1})')
                        continue

                    time.sleep(1)

                    # CSVダウンロード
                    try:
                        btns_now = page.query_selector_all('button, [role="button"]')
                        csv_btn  = next((b for b in btns_now if 'CSV' in b.inner_text()), None)
                        if not csv_btn:
                            print(f'  CSVボタンなし (attempt {attempt+1})')
                            continue

                        with page.expect_download(timeout=150000) as dl_info:
                            csv_btn.click()
                        download  = dl_info.value
                        save_path = DOWNLOAD_DIR / fname
                        download.save_as(str(save_path))
                        print(f'  保存: {fname}')

                        upload_to_drive(save_path, drive_svc, folder_id=date_subfolder_id)
                        success = True
                        break

                    except Exception as e:
                        print(f'  エラー (attempt {attempt+1}): {e}')
                        continue

                if not success:
                    print(f'  => {i+1}本目スキップ')
                    continue

                # ダウンロード間のランダム待機（人間らしく）
                if i < len(date_ranges) - 1:
                    wait = random.uniform(5, 15)
                    print(f'  次まで {wait:.1f}秒 待機...')
                    time.sleep(wait)

        browser.close()

    # 全期間統合ファイルを生成
    generate_combined(drive_svc, subfolder_id)
    print('\n完了！')


# ─── 元データ内 Booking_*.csv を再帰1段で列挙 ──────────────
def _list_all_booking_files(drive_svc, subfolder_id):
    """元データ直下 + 日付サブフォルダ内の Booking_*.csv を古い順に返す"""
    all_files = []
    # 直下のフラットファイル（旧形式との互換）
    res = drive_svc.files().list(
        q=(f"'{subfolder_id}' in parents"
           f" and name contains 'Booking_'"
           f" and mimeType='text/csv'"
           f" and trashed=false"),
        fields='files(id, name)',
        orderBy='name',
        pageSize=200,
    ).execute()
    all_files.extend(res.get('files', []))
    # 日付サブフォルダを名前順（＝日付順）で取得
    sub_res = drive_svc.files().list(
        q=(f"'{subfolder_id}' in parents"
           f" and mimeType='application/vnd.google-apps.folder'"
           f" and trashed=false"),
        fields='files(id, name)',
        orderBy='name',
    ).execute()
    for sub in sub_res.get('files', []):
        res2 = drive_svc.files().list(
            q=(f"'{sub['id']}' in parents"
               f" and name contains 'Booking_'"
               f" and mimeType='text/csv'"
               f" and trashed=false"),
            fields='files(id, name)',
            orderBy='name',
            pageSize=200,
        ).execute()
        all_files.extend(res2.get('files', []))
    return all_files


# ─── 全期間統合CSVを生成してDriveにアップロード ─────────────
def generate_combined(drive_svc, subfolder_id):
    print('\n全期間統合ファイルを生成中...')

    # 元データ直下 + 日付サブフォルダ内の Booking_*.csv を全件取得
    dfs = []
    for f in _list_all_booking_files(drive_svc, subfolder_id):
        request = drive_svc.files().get_media(fileId=f['id'])
        fh = io.BytesIO()
        dl = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
        fh.seek(0)
        try:
            df = pd.read_csv(fh, encoding='utf-8-sig')
            if len(df) > 0:
                dfs.append(df)
                print(f'  読込: {f["name"]} ({len(df)}件)')
        except Exception as e:
            print(f'  スキップ: {f["name"]} ({e})')

    if not dfs:
        print('  結合対象なし')
        return

    combined = pd.concat(dfs, ignore_index=True)

    # AirHost予約IDで重複除去（最新の更新日時を優先）
    if 'AirHost予約ID' in combined.columns:
        if '更新日時' in combined.columns:
            combined = combined.sort_values('更新日時', ascending=True)
        combined = combined.drop_duplicates(subset=['AirHost予約ID'], keep='last')

    # チェックイン日順にソート
    if 'チェックイン' in combined.columns:
        combined['チェックイン'] = pd.to_datetime(combined['チェックイン'], errors='coerce')
        combined = combined.sort_values('チェックイン')

    # CSV化してアップロード
    csv_bytes = combined.to_csv(index=False).encode('utf-8-sig')
    fname = 'AirHost_全予約データ.csv'
    existing = drive_svc.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and name='{fname}' and trashed=false",
        fields='files(id)'
    ).execute().get('files', [])

    media = MediaIoBaseUpload(io.BytesIO(csv_bytes), mimetype='text/csv', resumable=False)
    if existing:
        drive_svc.files().update(fileId=existing[0]['id'], media_body=media).execute()
    else:
        drive_svc.files().create(
            body={'name': fname, 'parents': [DRIVE_FOLDER_ID]},
            media_body=media
        ).execute()
    print(f'  => {fname} 更新完了（{len(combined)}件）')

if __name__ == '__main__':
    main()
