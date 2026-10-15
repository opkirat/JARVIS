import json

with open("email.json", "r") as file:
    emails = json.load(file)

# Cleaned out Email
for email in emails:
    headers = email["payload"]["headers"]
    for header in headers:
        if header["name"] == "Date":
            date = header["value"]
        if header["name"] == "Subject":
            subject = header["value"]

    print(f'ID: {email["id"]} \n'
        f'Snippet: {email["snippet"]} \n'
        f'Labels: {email["labelIds"]} \n'
        f'Date Received: {date} \n'
        f'Subject: {subject} \n'
            )
