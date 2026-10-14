import os
import json
import base64
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import yaml

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class GmailJobCollector:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.gmail_config = self.config.get("gmail", {})
        self.target_labels = self.gmail_config.get("target_labels", [])
        self.max_age_days = self.gmail_config.get("max_email_age_days", 2)
        self.processed_ids_file = self.gmail_config.get("processed_ids_file", "processed_ids.json")

        self.paths_config = self.config.get("paths", {})
        self.credentials_file = self.paths_config.get("credentials_file", "credentials.json")
        self.token_file = self.paths_config.get("token_file", "token.json")

        self.service = self._authenticate()
        self.processed_ids = self._load_processed_ids()

    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"Credentials file '{self.credentials_file}' not found. "
                        "Please download it from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(self.token_file, "w") as token:
                token.write(creds.to_json())

        return build('gmail', 'v1', credentials=creds)

    def _load_processed_ids(self):
        if os.path.exists(self.processed_ids_file):
            try:
                with open(self.processed_ids_file, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                return set()
        return set()

    def _save_processed_ids(self):
        with open(self.processed_ids_file, "w", encoding="utf-8") as f:
            json.dump(list(self.processed_ids), f, indent=2)

    def fetch_new_job_emails(self):
        """Сканирует новые письма по целевым меткам с учетом даты и дедупликации."""
        all_messages = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)

        # Получаем список лейблов в Gmail для сопоставления названий с ID
        labels_response = self.service.users().labels().list(userId='me').execute()
        labels = labels_response.get('labels', [])
        label_map = {lbl['name']: lbl['id'] for lbl in labels}

        for label_name in self.target_labels:
            label_id = label_map.get(label_name)
            if not label_id:
                print(f"⚠️ Метка '{label_name}' не найдена в вашем Gmail. Пропускаем.")
                continue

            query = f"after:{int(cutoff_date.timestamp())}"
            try:
                results = self.service.users().messages().list(
                    userId='me',
                    labelIds=[label_id],
                    q=query
                ).execute()

                messages = results.get('messages', [])
                for msg in messages:
                    msg_id = msg['id']
                    if msg_id in self.processed_ids:
                        continue

                    # Получаем детали письма
                    msg_detail = self.service.users().messages().get(
                        userId='me', id=msg_id, format='full'
                    ).execute()

                    parsed_email = self._parse_message(msg_detail, label_name)
                    if parsed_email:
                        all_messages.append(parsed_email)
                        self.processed_ids.add(msg_id)

            except Exception as e:
                print(f"❌ Ошибка при сканировании метки {label_name}: {e}")

        self._save_processed_ids()
        return all_messages

    def _parse_message(self, msg_detail, source_label):
        headers = msg_detail.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
        date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

        body = self._extract_body(msg_detail.get('payload', {}))

        return {
            'id': msg_detail['id'],
            'threadId': msg_detail['threadId'],
            'source': source_label,
            'subject': subject,
            'sender': sender,
            'date': date_str,
            'body': body
        }

    def _extract_body(self, payload):
        body = ""
        if 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                if mime_type == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                        break
                elif 'parts' in part:
                    body = self._extract_body(part)
                    if body:
                        break
        elif 'body' in payload:
            data = payload['body'].get('data', '')
            if data:
                body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        return body


if __name__ == "__main__":
    # Локальный тест сборщика
    collector = GmailJobCollector()
    emails = collector.fetch_new_job_emails()
    print(f"📥 Успешно собрано новых писем: {len(emails)}")
    for email in emails:
        # Ограничиваем вывод темы 50 символами для читаемости консоли
        print(f"- [{email['source']}] {email['subject'][:50]} (ID: {email['id']})")