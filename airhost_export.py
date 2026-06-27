# -*- coding: utf-8 -*-
"""
AirHost CSV 自動エクスポートスクリプト（改良版）
- Cookieを保存して再ログイン不要にする
- ダウンロード間にランダム待機（人間らしく）
- 取得範囲：過去2ヶ月 + 未来6ヶ月
- playwright-stealth でbot検知を回避
"""
import os, json, time, re, base64, sys, random
from datetime import date, timedelta
from pathlib import Path
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# CI環境（GitHub Actions）かどうか
IS_CI = os.environ.get('CI', '').lower() == 'true'

# ─── 設定 ────────────────────────────────────────────────────
SIGN_IN_URL      = 'https://pms.airhost.co/ja/sign_in'
EXPORT_URL       = 'https://pms.airhost.co/ja/import-export/export-bookings'
AIRHOST_EMAIL    = 'ishizaki.imovel@gmail.com'
AIRHOST_PASS     = os.environ.get('AIRHOST_PASS', '11aoistaytokyo')

DRIVE_FOLDER_ID  = '10SFTfWNehj8M9gEgGpFh-W-VmTLkrC2V'

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

# ─── Gmail 2FAコード取得 ──────────────────────────────────────
def read_2fa_code(gmail_svc, wait_sec=90):
    print('  2FAコード待機中...')
    for _ in range(wait_sec // 5):
        time.sleep(5)
        res = gmail_svc.users().messages().list(
            userId='me', q='from:airhost is:unread', maxResults=5
        ).execute()
        for m in res.get('messages', []):
            msg   = gmail_svc.users().messages().get(userId='me', id=m['id'], format='full').execute()
            body  = _decode_body(msg['payload'])
            match = re.search(r'\b(\d{6})\b', body)
            if match:
                gmail_svc.users().messages().modify(
                    userId='me', id=m['id'], body={'removeLabelIds': ['UNREAD']}
                ).execute()
                print(f'  コード: {match.group(1)}')
                return match.group(1)
    print('  ERROR: 2FAコード取得失敗')
    return None

def _decode_body(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            data = part.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='ignore')
    data = payload.get('body', {}).get('data', '')
    return base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='ignore') if data else ''

# ─── Driveアップロード ────────────────────────────────────────
def upload_to_drive(filepath, drive_svc):
    name = Path(filepath).name
    res  = drive_svc.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and name='{name}' and trashed=false",
        fields='files(id)'
    ).execute()
    existing = res.get('files', [])
    media    = MediaFileUpload(str(filepath), mimetype='text/csv')
    if existing:
        drive_svc.files().update(fileId=existing[0]['id'], media_body=media).execute()
        print(f'  Drive更新: {name}')
    else:
        drive_svc.files().create(
            body={'name': name, 'parents': [DRIVE_FOLDER_ID]},
            media_body=media
        ).execute()
        print(f'  Drive作成: {name}')

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
def do_login(page, gmail_svc):
    print('ログイン中...')
    page.goto(SIGN_IN_URL)
    page.wait_for_load_state('networkidle')
    time.sleep(2)
    page.fill('#email', AIRHOST_EMAIL)
    page.fill('#password', AIRHOST_PASS)
    page.click('button[type="submit"]')

    # 2FA
    try:
        page.wait_for_selector('#otpCode', timeout=10000)
        code = read_2fa_code(gmail_svc)
        if not code:
            return False
        page.fill('#otpCode', code)
        page.click('button[type="submit"]')
    except Exception:
        print('  2FAなし')

    # 会社選択
    try:
        page.wait_for_selector('text=合同会社あおい', timeout=15000)
        page.query_selector('text=合同会社あおい').click()
        page.wait_for_load_state('networkidle', timeout=30000)
        print('  会社選択完了')
    except Exception:
        pass

    return True

# ─── Cookie を使ってセッション再利用を試みる ────────────────
def ensure_logged_in(page, context, gmail_svc):
    """Cookieがあれば再利用、なければ/期限切れならフルログイン"""
    if COOKIE_FILE.exists():
        print('Cookie読み込み中...')
        cookies = json.loads(COOKIE_FILE.read_text())
        context.add_cookies(cookies)
        page.goto(EXPORT_URL)
        time.sleep(3)
        if SIGN_IN_URL not in page.url and 'company-select' not in page.url:
            print('Cookie有効: ログインスキップ')
            return True
        print('Cookie期限切れ → 再ログイン')

    ok = do_login(page, gmail_svc)
    if ok:
        # Cookie保存
        cookies = context.cookies()
        COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))
        print('Cookie保存完了')
    return ok

# ─── メイン ──────────────────────────────────────────────────
def main():
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    # Gmail / Drive 認証
    with open(GMAIL_CREDS_PATH) as f:
        creds_data = json.load(f)
    gmail_creds = Credentials.from_authorized_user_info(creds_data)
    if gmail_creds.expired and gmail_creds.refresh_token:
        gmail_creds.refresh(Request())
    gmail_svc = build('gmail', 'v1', credentials=gmail_creds, cache_discovery=False)
    drive_svc = build('drive', 'v3', credentials=gmail_creds, cache_discovery=False)
    print('Gmail/Drive認証 OK')

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
        ok = ensure_logged_in(page, context, gmail_svc)
        if not ok:
            print('ログイン失敗')
            browser.close()
            return

        # ─ CSVダウンロードループ ─
        current_month_start = date.today().replace(day=1)

        for i, (start_dt, end_dt) in enumerate(date_ranges):
            fname = f'Booking_{start_dt.strftime("%Y%m%d")}_{end_dt.strftime("%Y%m%d")}.csv'
            print(f'\n[{i+1}/{len(date_ranges)}] {start_dt} 〜 {end_dt}')

            # 確定月スキップ：期間が今月より前に終わっていて、かつDriveにすでに存在する場合はスキップ
            if end_dt < current_month_start:
                res = drive_svc.files().list(
                    q=f"'{DRIVE_FOLDER_ID}' in parents and name='{fname}' and trashed=false",
                    fields='files(id)'
                ).execute()
                if res.get('files'):
                    print(f'  確定済み・スキップ（Driveに保存済み）')
                    continue

            success = False
            for attempt in range(2):
                # エクスポートページへ（毎回新鮮な状態）
                page.goto(EXPORT_URL)
                time.sleep(3)

                # ログアウトされていたら再ログイン
                if SIGN_IN_URL in page.url or 'company-select' in page.url:
                    print('  セッション切れ → 再ログイン')
                    do_login(page, gmail_svc)
                    cookies = context.cookies()
                    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))
                    page.goto(EXPORT_URL)
                    time.sleep(3)

                # アコーディオン展開
                btns = page.query_selector_all('button, [role="button"]')
                if len(btns) < 2:
                    print(f'  アコーディオンボタンなし (attempt {attempt+1})')
                    time.sleep(3)
                    continue
                btns[1].click()
                time.sleep(2)

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

                    upload_to_drive(save_path, drive_svc)
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

    print('\n完了！')

if __name__ == '__main__':
    main()
