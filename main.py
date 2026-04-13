import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

def get_strava_access_token():
    response = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": os.environ.get("STRAVA_CLIENT_ID"),
        "client_secret": os.environ.get("STRAVA_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": os.environ.get("STRAVA_REFRESH_TOKEN")
    })
    return response.json().get("access_token")

def get_activity(activity_id, access_token):
    response = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    return response.json()

def get_coaching(activity):
    name = activity.get("name", "Unknown")
    distance = round(activity.get("distance", 0) / 1000, 2)
    moving_time = round(activity.get("moving_time", 0) / 60, 1)
    elevation = activity.get("total_elevation_gain", 0)
    avg_hr = activity.get("average_heartrate", "N/A")
    max_hr = activity.get("max_heartrate", "N/A")
    cadence = activity.get("average_cadence", "N/A")
    avg_speed = activity.get("average_speed", 0)
    pace = round(1000 / avg_speed / 60, 2) if avg_speed > 0 else "N/A"
    activity_type = activity.get("type", "Unknown")
    description = activity.get("description", "None")

    prompt = f"""New activity from Connor:

Name: {name}
Type: {activity_type}
Distance: {distance} km
Moving time: {moving_time} mins
Average pace: {pace} min/km
Elevation gain: {elevation} m
Average HR: {avg_hr} bpm
Max HR: {max_hr} bpm
Average cadence: {cadence} rpm
Description: {description}"""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ.get("ANTHROPIC_API_KEY"),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "system": "You are an experienced running coach working with Connor, a runner in Sydney focused on general fitness and building toward race targets. He has a mild lower leg niggle to manage. Be direct, honest, conversational. Analyse each activity, flag anything worth noting, and end with a clear recommendation for his next session. Under 200 words.",
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    return response.json()["content"][0]["text"]

def send_telegram(message):
    requests.post(
        f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN')}/sendMessage",
        json={"chat_id": os.environ.get("TELEGRAM_CHAT_ID"), "text": message, "parse_mode": "Markdown"}
    )

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    expected = os.environ.get("STRAVA_VERIFY_TOKEN")
    if mode == "subscribe" and token == expected:
        return jsonify({"hub.challenge": challenge})
    return f"Forbidden - got: {token} expected: {expected}", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data.get("object_type") == "activity" and data.get("aspect_type") == "create":
        activity_id = data.get("object_id")
        access_token = get_strava_access_token()
        activity = get_activity(activity_id, access_token)
        if activity.get("type") in ["Run", "TrailRun"]:
            coaching = get_coaching(activity)
            send_telegram(f"*New run coached*\n\n{coaching}")
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
