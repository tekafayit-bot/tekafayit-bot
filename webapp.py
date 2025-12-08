from flask import Flask, render_template_string, request, redirect, url_for, session
from tinydb import TinyDB
import datetime

app = Flask(__name__)
app.secret_key = "tekafayit_secret"
PASSWORD = "1096gech"
db = TinyDB("db.json")

LOGIN_PAGE = """<form method="post">
  <input type="password" name="pw" placeholder="Password">
  <button>Login</button></form>"""

@app.route("/dashboard", methods=["GET","POST"])
def dashboard():
    if request.method == "POST":
        if request.form["pw"] == PASSWORD:
            session["ok"] = True
            return redirect(url_for("view"))
    if not session.get("ok"):
        return LOGIN_PAGE
    return redirect(url_for("view"))

@app.route("/dashboard/view")
def view():
    if not session.get("ok"):
        return redirect(url_for("dashboard"))
    data = db.all()[-20:]
    html = """
    <meta http-equiv="refresh" content="30">
    <h2>Tekafayit Dashboard</h2>
    <table border=1>
    <tr><th>Type</th><th>User</th><th>Description</th><th>Photos</th><th>Time</th></tr>
    {% for r in data %}
      <tr>
        <td>{{r.type}}</td>
        <td>{{r.user}}</td>
        <td>{{r.desc}}</td>
        <td>{% for p in r.photos %}
              <img src="https://api.telegram.org/file/bot{{token}}/{{p}}" width="60">
            {% endfor %}
        </td>
        <td>{{r.time}}</td>
      </tr>
    {% endfor %}
    </table>
    """
    return render_template_string(html, data=data, token="7378411294:AAG02Noxl3PCpA9F7-7eLFlmJVEtejd87vo")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
