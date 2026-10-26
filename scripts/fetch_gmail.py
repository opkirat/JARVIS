import argparse
from datetime import datetime, timezone
from pathlib import Path
from import_gmail import import_emails

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "secrets" / "gmail_credentials.json"
TOKEN_PATH = PROJECT_ROOT / "secrets" / "gmail_token.json"
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete secrets/gmail_token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main(*, non_interactive=False):
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail messages.
    """
    creds = None
    # secrets/gmail_token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                if non_interactive:
                    raise RuntimeError(
                        "Gmail authorization needs attention. Run "
                        ".venv/bin/python scripts/fetch_gmail.py manually."
                    ) from None
                raise
        else:
            if non_interactive:
                raise RuntimeError(
                    "Gmail authorization is required. Run "
                    ".venv/bin/python scripts/fetch_gmail.py manually first."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    try:
        # Call the Gmail API
        service = build("gmail", "v1", credentials=creds)
        results = (
            service.users().messages().list(userId="me", labelIds=["INBOX"]).execute()
        )
        messages = results.get("messages", [])

        if not messages:
            print("No messages found.")
            return

        print(f"Fetching {len(messages)} Gmail messages.")

        all_emails = []
        for message in messages:
            if not non_interactive:
                print(f'Message ID: {message["id"]}')
            msg = (
            service.users().messages().get(userId="me", id=message["id"]).execute()
            )

            all_emails.append(msg)

        import_emails(all_emails)
        print(f"Gmail sync completed: processed {len(all_emails)} messages.")
    
    except HttpError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f"An error occurred: {error}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Gmail messages into SQLite.")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Report missing authorization instead of opening a browser.",
    )
    args = parser.parse_args()
    print(f"Gmail sync started: {datetime.now(timezone.utc).isoformat()}")
    main(non_interactive=args.non_interactive)
