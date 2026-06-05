from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
import sqlite3
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends
import os

from fastapi import FastAPI, UploadFile, File, Header, HTTPException

def token_pruefen(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Kein Token!")
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM User WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()
        return dict(user)
    except JWTError:
        raise HTTPException(status_code=401, detail="Ungültiger Token!")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "dein-geheimer-schluessel-123"
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTEN = 60

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/fotos", StaticFiles(directory="fotos"), name="fotos")


def init_db():
    conn = sqlite3.connect("rezepte.sqlite")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Rezepte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            titel TEXT,
            kategorie TEXT,
            schwierigkeit TEXT,
            portionen INTEGER,
            zubereitungszeit INTEGER,
            zutaten TEXT,
            zubereitung TEXT,
            foto TEXT,
            FOREIGN KEY (user_id) REFERENCES User(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS User (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            passwort TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect("rezepte.sqlite")
    conn.row_factory = sqlite3.Row
    return conn

class Rezept(BaseModel):
    titel: str
    kategorie: str
    schwierigkeit: str
    portionen: int
    zubereitungszeit: int
    zutaten: str
    zubereitung: str
    foto: str = ""
    user_id: int = 0

class UserRegistrierung(BaseModel):
    username: str
    email: str
    passwort: str

class UserLogin(BaseModel):
    username: str
    passwort: str


init_db()

@app.get("/rezepte")
def rezepte_abrufen(user = Depends(token_pruefen)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM Rezepte WHERE user_id = ?", (user["id"],))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/rezepte")
def rezept_hinzufuegen(rezept: Rezept, user = Depends(token_pruefen)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO Rezepte
        (user_id, titel, kategorie, schwierigkeit, portionen, zubereitungszeit, zutaten, zubereitung, foto)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user["id"], rezept.titel, rezept.kategorie, rezept.schwierigkeit,
          rezept.portionen, rezept.zubereitungszeit, rezept.zutaten,
          rezept.zubereitung, rezept.foto))
    conn.commit()
    conn.close()
    return {"nachricht": f"{rezept.titel} wurde gespeichert!"}

@app.delete("/rezepte/{id}")
def rezepte_loeschen(id: int, user = Depends(token_pruefen)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM Rezepte WHERE id = ? AND user_id = ?", (id, user["id"]))
    conn.commit()
    conn.close()
    return {"nachricht": "Rezept gelöscht!"}

@app.post("/upload-foto")
async def foto_hochladen(datei: UploadFile = File(...)):
    dateipfad = f"fotos/{datei.filename}"
    with open(dateipfad, "wb") as f:
        f.write(await datei.read())
    return {"foto_url": f"/fotos/{datei.filename}"}

@app.put("/rezepte/{id}")
def rezept_bearbeiten(id: int, rezept: Rezept, user = Depends(token_pruefen)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE Rezepte SET
        titel=?, kategorie=?, schwierigkeit=?, portionen=?,
        zubereitungszeit=?, zutaten=?, zubereitung=?, foto=?
        WHERE id=? AND user_id=?
    """, (rezept.titel, rezept.kategorie, rezept.schwierigkeit,
          rezept.portionen, rezept.zubereitungszeit, rezept.zutaten,
          rezept.zubereitung, rezept.foto, id, user["id"]))
    conn.commit()
    conn.close()
    return {"nachricht": f"{rezept.titel} wurde gespeichert!"}

@app.post("/registrieren")
def registrieren(user: UserRegistrierung):
    conn = get_db()
    cur = conn.cursor()

    #Prüfen ob User bereits exisitert
    cur.execute("SELECT id FROM User WHERE username = ?", (user.username,))
    if cur.fetchone():
        conn.close()
        return {"fehler": "Username bereits vergeben"}

    # Passwort verschlüsseln
    passwort_hash = pwd_context.hash(user.passwort)

    cur.execute("INSERT INTO User (username, email, passwort) VALUES (?, ?, ?)", (user.username, user.email, passwort_hash))
    conn.commit()
    conn.close()
    return {"nachricht": f"{user.username} wurde registiert"}

@app.post("/login")
def login(user: UserLogin):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM User WHERE username = ?", (user.username,))
    db_user = cur.fetchone()
    conn.close()

    if not db_user or not pwd_context.verify(user.passwort, db_user["passwort"]):
        return {"fehler": "Falscher Username oder Passwort"}

    #Token erstellen
    token_data = {"sub": user.username, "exp": datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTEN)}
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

    return {"token": token, "username": user.username}