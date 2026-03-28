import os
from dotenv import load_dotenv
import discord
import aiosqlite
import asyncio
from datetime import datetime, timedelta
import pytz

# ==============================
# CARREGAMENTO DE TOKEN (FIX RAILWAY)
# ==============================
load_dotenv()
TOKEN = os.getenv("TOKEN")

print("--- DEBUG SISTEMA ---")
if not TOKEN:
    print("❌ ERRO: O TOKEN não foi detectado no ambiente do Railway!")
    print("Verifique a aba 'Variables' no painel do Railway.")
else:
    # Mostra apenas os 4 primeiros caracteres por segurança
    print(f"✅ Token detectado (Inicia com: {TOKEN[:4]}...)")
print("---------------------")

if not TOKEN:
    raise Exception("❌ TOKEN não configurado no ambiente!")

# ==============================
# CONFIGURAÇÕES
# ==============================
TIMEZONE = pytz.timezone("America/Sao_Paulo")
CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076
DB_PATH = "ranking.db"

# Lista de Eventos
eventos = [
    ("Galia Black", "21:35", None, 2, "🗡️"),
    ("Kundun", "13:10", None, 2, "🐲"),
    ("Kundun", "15:10", None, 2, "🐲"),
    ("Galia Black", "16:45", None, 2, "🗡️"),
    ("Blood Wizard", "18:10", None, 5, "🧙‍♂️"),
    ("Crusher Skeleton", "19:05", None, 5, "💀"),
    ("Necromancer", "19:40", None, 5, "☠️"),
    ("Selupan", "20:10", None, 5, "🦂"),
    ("Skull Reaper", "20:50", None, 5, "👻"),
    ("Gywen", "22:10", None, 5, "🐺"),
    ("HellMaine", "22:30", None, 20, "👿"),
    ("Balgass", "23:00", [2, 5], 30, "🧌"),
    ("Yorm", "23:40", None, 15, "🐗"),
    ("Zorlak", "01:10", None, 15, "🐉"),
    ("Castle Siege", "21:10", [6], 50, "🛡️"),
]

# Inicialização do Bot
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Variáveis de Controle
lista_ativa = None
participantes = {}
usuarios_registrados = set()
mensagem_lista = None
evento_aberto_id = None
evento_fechado_id = None

# ==============================
# DATABASE
# ==============================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS ranking (
            nick TEXT PRIMARY KEY,
            pontos INTEGER DEFAULT 0
        )
        """)
        await db.commit()
    print("🗄️ Banco de dados verificado.")

# ==============================
# FINALIZAR EVENTO
# ==============================
async def distribuir_pontos(canal_presenca, canal_pontos, nome, pontos, emoji):
    global participantes, lista_ativa, mensagem_lista, usuarios_registrados

    lista_final = list(participantes.values())

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            for nick in lista_final:
                cur = await db.execute("SELECT pontos FROM ranking WHERE nick=?", (nick,))
                row = await cur.fetchone()

                if row:
                    await db.execute("UPDATE ranking SET pontos = pontos + ? WHERE nick=?", (pontos, nick))
                else:
                    await db.execute("INSERT INTO ranking (nick, pontos) VALUES (?,?)", (nick, pontos))
            await db.commit()

            cur = await db.execute("SELECT nick, pontos FROM ranking ORDER BY pontos DESC LIMIT 10")
            ranking_geral = await cur.fetchall()

        if mensagem_lista:
            try: await mensagem_lista.delete()
            except: pass

        lista_txt = "\n".join([f"{i+1}. {n}" for i, n in enumerate(lista_final)])
        await canal_presenca.send(
            f"🔒 **Lista fechada!**\n\n"
            f"{emoji} **{nome} FINALIZADO**\n\n"
            f"👥 Participantes:\n"
            f"{lista_txt if lista_txt else 'Nenhum participante.'}"
        )

        msg = "🏆 **RANKING GERAL – BOSSES**\n\n"
        for i, (nick, pts) in enumerate(ranking_geral, 1):
            msg += f"{i}. {nick} — {pts} pts\n"
        await canal_pontos.send(msg)

    except Exception as e:
        print(f"Erro ao salvar no DB: {e}")
    finally:
        participantes = {}
        usuarios_registrados = set()
        lista_ativa = None
        mensagem_lista = None

# ==============================
# SCHEDULER
# ==============================
async def scheduler():
    global lista_ativa, participantes, mensagem_lista
    global evento_aberto_id, evento_fechado_id, usuarios_registrados

    await client.wait_until_ready()
    print("⏰ Scheduler iniciado.")

    while not client.is_closed():
        try:
            canal_presenca = client.get_channel(CANAL_PRESENCA_ID)
            canal_pontos = client.get_channel(CANAL_PONTOS_ID)
            
            if not canal_presenca:
                await asyncio.sleep(10)
                continue

            now = datetime.now(TIMEZONE)

            for nome, hora, dias, pontos, emoji in eventos:
                h, m = map(int, hora.split(":"))
                evento = now.replace(hour=h, minute=m, second=0, microsecond=0)

                if evento < now:
                    evento += timedelta(days=1)

                if dias and now.weekday() not in dias:
                    continue

                evento_id = f"{nome}-{evento.date()}"
                abrir = evento - timedelta(minutes=5)
                fechar = evento + timedelta(minutes=10)

                # Abrir Lista
                if abrir <= now <= abrir + timedelta(seconds=40):
                    if lista_ativa is None and evento_aberto_id != evento_id:
                        lista_ativa = nome
                        participantes = {}
                        usuarios_registrados = set()
                        evento_aberto_id = evento_id
                        mensagem_lista = await canal_presenca.send(
                            f"{emoji} **LISTA ABERTA — {nome}**\n\n"
                            f"👥 Participantes: 0\n\n"
                            f"✍️ Envie seu nick no chat!"
                        )

                # Fechar Lista
                if fechar <= now <= fechar + timedelta(seconds=40):
                    if lista_ativa == nome and evento_fechado_id != evento_id:
                        evento_fechado_id = evento_id
                        await distribuir_pontos(canal_presenca, canal_pontos, nome, pontos, emoji)

        except Exception as e:
            print(f"Erro no loop do scheduler: {e}")
        
        await asyncio.sleep(30)

# ==============================
# EVENTOS DISCORD
# ==============================
@client.event
async def on_message(message):
    global participantes, mensagem_lista, usuarios_registrados

    if message.author.bot or message.channel.id != CANAL_PRESENCA_ID:
        return

    if not lista_ativa:
        try: await message.delete()
        except: pass
        return

    if message.author.id in usuarios_registrados:
        try: await message.delete()
        except: pass
        return

    nick = message.content.strip()
    if not nick or len(nick) > 30: # Proteção contra spam
        return

    usuarios_registrados.add(message.author.id)
    participantes[message.author.id] = nick

    try: await message.delete()
    except: pass

    if mensagem_lista:
        lista_txt = "\n".join([f"• {n}" for n in participantes.values()])
        try:
            await mensagem_lista.edit(
                content=(
                    f"📋 **LISTA ABERTA — {lista_ativa}**\n\n"
                    f"👥 Participantes: {len(participantes)}\n\n"
                    f"{lista_txt}"
                )
            )
        except Exception as e:
            print(f"Erro ao editar lista: {e}")

@client.event
async def on_ready():
    await init_db()
    print(f"🚀 Bot online como {client.user}")
    
    # Garante que o scheduler só inicie uma vez
    if not hasattr(client, 'scheduler_running'):
        client.scheduler_running = True
        asyncio.create_task(scheduler())

# ==============================
# START
# ==============================
try:
    client.run(TOKEN)
except Exception as e:
    print(f"❌ Erro ao iniciar o bot: {e}")
