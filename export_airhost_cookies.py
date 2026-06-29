# -*- coding: utf-8 -*-
"""
AirHost Cookieエクスポーター
─────────────────────────────
【使い方】
1. このスクリプトをダブルクリック（または python export_airhost_cookies.py）
2. ブラウザが開くので、AirHostに手動でログイン（2FAも含めて完了させる）
3. 会社選択画面に到達したらEnterを押す
4. airhost_cookies.json が生成される
5. そのファイルの中身をまるごとコピーして GitHub Secrets の AIRHOST_COOKIES_JSON に貼り付ける
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

AIRHOST_LOGIN_URL = 'https://pms.airhost.co/sign_in'
OUT_FILE = Path(__file__).parent / 'airhost_cookies.json'

def main():
    print('=' * 50)
    print('AirHost Cookie エクスポーター')
    print('=' * 50)
    print()
    print('ブラウザを開きます。')
    print('AirHostに手動でログイン（2FAも）して、会社選択画面まで進めてください。')
    print('会社選択画面に到達したら、このターミナルに戻ってEnterを押してください。')
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(AIRHOST_LOGIN_URL)

        input('─── ログインが完了したらEnterを押してください ───')

        cookies = context.cookies()
        browser.close()

    OUT_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding='utf-8')

    print()
    print(f'✅ Cookie を保存しました: {OUT_FILE}')
    print()
    print('─── 次の手順 ───────────────────────────────────')
    print(f'1. {OUT_FILE} をメモ帳などで開く')
    print('2. 内容をすべて選択してコピー（Ctrl+A → Ctrl+C）')
    print('3. GitHubリポジトリ → Settings → Secrets and variables → Actions')
    print('4. 「AIRHOST_COOKIES_JSON」という名前でSecretを新規作成（または更新）して貼り付け')
    print('───────────────────────────────────────────────')
    input('Enterで終了...')

if __name__ == '__main__':
    main()
