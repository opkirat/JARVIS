import json
import base64


def get_body_data(payload):
    if payload.get("body", {}).get("data"):
        return payload["body"]["data"]

    for part in payload.get("parts", []):
        data = get_body_data(part)
        if data:
            return data

    return ""


with open("email.json", "r") as file:
    emails = json.load(file)

cleaned_emails = []

# Cleaned out Email
for email in emails:
    headers = email["payload"]["headers"]

    # Data
    payload = email["payload"]

    text = get_body_data(payload)
    if not text:
        continue

    # Decode Base64 string
    text += "=" * (-len(text) % 4)
    decoded_bytes = base64.urlsafe_b64decode(text)
    content = decoded_bytes.decode("utf-8", errors="replace")

    for header in headers:
        if header["name"] == "Date":
            date = header["value"]
        if header["name"] == "Subject":
            subject = header["value"]

    cleaned_emails.append({
        "id": email["id"],
        "snippet": email["snippet"],
        "labels": email["labelIds"],
        "date": date,
        "subject": subject,
        "body": content,
    })

    print(f'ID: {email["id"]} \n'
        f'Snippet: {email["snippet"]} \n'
        f'Labels: {email["labelIds"]} \n'
        f'Date Received: {date} \n'
        f'Subject: {subject} \n'
        f'Content: {content} \n'
            )

with open("cleaned_emails.json", "w", encoding="utf-8") as file:
    json.dump(cleaned_emails, file, ensure_ascii=False, indent=2)
