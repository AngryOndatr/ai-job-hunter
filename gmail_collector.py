import os
import json
import re
import base64
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
import yaml

from google_auth import BASE_SCOPES, get_google_credentials
from logging_setup import get_logger

logger = get_logger("gmail_collector")

_VIEW_JOB_URL_RE = re.compile(r"View job:\s*(https?://\S+)")
_JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")
_SEPARATOR_RE = re.compile(r"^-{10,}\s*$")

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
        creds = get_google_credentials(
            self.credentials_file, self.token_file, scopes=BASE_SCOPES
        )
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
            json.dump(sorted(self.processed_ids), f, indent=2)

    def fetch_new_job_emails(self, defer_processed=False, reprocess_ids=None):
        """Сканирует новые письма по целевым меткам с учетом даты и дедупликации."""
        all_messages = []
        discovered_ids = set()
        reprocess_ids = set(reprocess_ids or ())
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)

        # Получаем список лейблов в Gmail для сопоставления названий с ID
        labels_response = self.service.users().labels().list(userId='me').execute()
        labels = labels_response.get('labels', [])
        label_map = {lbl['name']: lbl['id'] for lbl in labels}

        for label_name in self.target_labels:
            label_id = label_map.get(label_name)
            if not label_id:
                logger.warning("Label '%s' not found in Gmail; skipping.", label_name)
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
                    if (
                        (msg_id in self.processed_ids and msg_id not in reprocess_ids)
                        or msg_id in discovered_ids
                    ):
                        continue

                    # Получаем детали письма
                    msg_detail = self.service.users().messages().get(
                        userId='me', id=msg_id, format='full'
                    ).execute()

                    parsed_email = self._parse_message(msg_detail, label_name)
                    if parsed_email:
                        digest_jobs = self._split_digest(parsed_email)
                        if digest_jobs:
                            all_messages.extend(digest_jobs)
                        else:
                            all_messages.append(parsed_email)
                        discovered_ids.add(msg_id)
                        if not defer_processed:
                            self.processed_ids.add(msg_id)

            except Exception as exc:
                logger.error(
                    "Failed to scan Gmail label %s (%s); details redacted.",
                    label_name, type(exc).__name__,
                )

        if not defer_processed:
            self._save_processed_ids()
        return all_messages

    def mark_processed(self, message_id):
        """Persist one message ID after the downstream pipeline has handled it."""
        if not isinstance(message_id, str) or not message_id:
            raise ValueError("message_id must be a non-empty string.")
        self.processed_ids.add(message_id)
        self._save_processed_ids()

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

    @staticmethod
    def _split_digest(parsed_email):
        """Split a multi-job digest email into one record per job listing.

        Returns an empty list when the body is not a digest (fewer than two
        ``View job:`` links), so callers fall back to the original record.
        Each split record keeps the source message metadata but gets a
        per-job synthetic ID (``<message_id>:<job_id>``), the extracted
        title/company/location, the job URL, and its own body block.
        """
        body = parsed_email.get("body", "")
        if not isinstance(body, str):
            return []
        if len(_VIEW_JOB_URL_RE.findall(body)) < 2:
            return []

        chunks = []
        current = []
        for line in body.splitlines():
            if _SEPARATOR_RE.match(line.strip()):
                if current:
                    chunks.append("\n".join(current))
                    current = []
                continue
            current.append(line)
        if current:
            chunks.append("\n".join(current))

        jobs = []
        for chunk in chunks:
            match = _VIEW_JOB_URL_RE.search(chunk)
            if not match:
                continue
            job_url = match.group(1).rstrip(".,;)")
            id_match = _JOB_ID_RE.search(job_url)
            job_id = id_match.group(1) if id_match else ""
            lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
            hiring_idx = next(
                (i for i, ln in enumerate(lines)
                 if ln.lower().startswith("this company is actively hiring")),
                None,
            )
            header = lines[:hiring_idx] if hiring_idx is not None else lines
            if len(header) >= 3:
                title, company, location = header[-3], header[-2], header[-1]
            elif len(header) == 2:
                title, company, location = header[-2], header[-1], ""
            else:
                continue
            record = dict(parsed_email)
            if job_id:
                record["id"] = f"{parsed_email['id']}:{job_id}"
            record["job_title"] = title
            record["company"] = company
            record["location"] = location
            record["job_url"] = job_url
            record["job_id"] = job_id
            record["body"] = chunk.strip()
            jobs.append(record)
        return jobs


if __name__ == "__main__":
    # Локальный тест сборщика
    collector = GmailJobCollector()
    emails = collector.fetch_new_job_emails()
    print(f"📥 Успешно собрано новых писем: {len(emails)}")
    for email in emails:
        # Ограничиваем вывод темы 50 символами для читаемости консоли
        print(f"- [{email['source']}] {email['subject'][:50]} (ID: {email['id']})")
