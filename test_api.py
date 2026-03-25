import urllib.request
import json

response = urllib.request.urlopen('http://localhost:8098/api/appointments-data')
data = json.loads(response.read())

print(f'Total appointments: {data["count"]}')
for a in data['appointments']:
    print(f'  - Appt {a["id"]}: {a["phone"]} | {a["doctor_name"]} | {a["date"]} at {a["time"]} [{a["status"]}]')
