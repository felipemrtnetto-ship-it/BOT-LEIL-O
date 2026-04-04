import os
import discord
from discord.ui import Button, View
import asyncio
import asyncpg
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

# ==============================
# ⚙️ CONFIGURAÇÕES E AMBIENTE
# ==============================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Verificação de segurança para o log do Railway
if not DATABASE_URL:
    print("❌ ERRO: A variável DATABASE_URL está vazia no painel do Railway!")
else:
    # Garante que o esquema seja postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

TIMEZONE = pytz.timezone("America/Sao_Paulo")
CANAL_PRESENCA_ID = 1423485053127753748
CANAL_PONTOS_ID = 1423485889010602076
CANAL_LOGS_ID = 1489805148204040312

# Lista de Eventos
eventos = [
    ("Galia Black", "10:45", None, 2, "🗡️"),
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

# ==============================
# 🗄️ BANCO DE DADOS (POSTGRES)
# ==============================
async def init_db():
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS ranking (
                user_id BIGINT PRIMARY KEY,
                nick TEXT,
                pontos INTEGER DEFAULT 0
            )
        ''')
        await conn.close()
        print("✅ Banco de Dados conectado e tabela verificada!")
    except Exception as e:
        print(f"❌ Erro ao conectar no Banco: {e}")

# ==============================
# 🔘 INTERFACE (BOTÃO)
# ==============================
class PresencaView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Marcar Presença", style=discord.ButtonStyle.green, custom_id="btn_presenca_v2", emoji="✅")
    async def marcar_presenca(self, interaction: discord.Interaction):
        if not self.bot.lista_ativa:
            return await interaction.response.send_message("❌ A lista está fechada!", ephemeral=True)
        
        user_id = interaction.user.id
        nick = interaction.user.display_name

        if user_id in self.bot.participantes:
            return await interaction.response.send_message("⚠️ Você já está na lista!", ephemeral=True)

        self.bot.participantes[user_id] = nick
        await self.bot.atualizar_lista_msg()
        await interaction.response.send_message(f"✅ Presença confirmada como **{nick}**!", ephemeral=True)

# ==============================
# 🤖 BOT CLIENT
# ==============================
class MaratonaBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.lista_ativa = None
        self.participantes = {}
        self.mensagem_lista = None
        self.alerta_enviado = False

    async def setup_hook(self):
        await init_db()
        self.add_view(PresencaView(self))
        self.loop.create_task(self.scheduler())

    async def log_auditoria(self, titulo, descricao, cor=0x3498db):
        canal = self.get_channel(CANAL_LOGS_ID)
        if canal:
            embed = discord.Embed(title=titulo, description=descricao, color=cor, timestamp=datetime.now(TIMEZONE))
            await canal.send(embed=embed)

    async def atualizar_lista_msg(self):
        if self.mensagem_lista:
            txt = "\n".join([f"• {n}" for n in self.participantes.values()])
            embed = discord.Embed(
                title=f"📋 LISTA: {self.lista_ativa}",
                description=f"Clique no botão para participar!\n\n**Participantes ({len(self.participantes)}):**\n{txt}",
                color=0x2ecc71
            )
            try: await self.mensagem_lista.edit(embed=embed, view=PresencaView(self))
            except: pass

    async def distribuir_pontos(self, nome, pontos):
        if not self.participantes:
            await self.log_auditoria("⚠️ Lista Vazia", f"Evento **{nome}** sem participantes.")
            self.lista_ativa = None; return

        try:
            conn = await asyncpg.connect(DATABASE_URL)
            for uid, nick in self.participantes.items():
                await conn.execute('''
                    INSERT INTO ranking (user_id, nick, pontos) VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE SET pontos = ranking.pontos + $3, nick = $2
                ''', uid, nick, pontos)
            await conn.close()
            await self.log_auditoria("💰 Pontos Pagos", f"Evento: **{nome}**\nPlayers: {len(self.participantes)}\nPts: +{pontos}", 0x27ae60)
        except Exception as e:
            print(f"Erro ao distribuir pontos: {e}")
        finally:
            self.participantes = {}; self.lista_ativa = None; self.alerta_enviado = False

    async def scheduler(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                now = datetime.now(TIMEZONE)
                canal_presenca = self.get_channel(CANAL_PRESENCA_ID)
                if not canal_presenca:
                    await asyncio.sleep(30); continue

                for nome, hora, dias, pts, emoji in eventos:
                    h, m = map(int, hora.split(":"))
                    ev_hoje = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if ev_hoje < now - timedelta(hours=1): ev_hoje += timedelta(days=1)
                    if dias and now.weekday() not in dias: continue

                    abrir, fechar = ev_hoje - timedelta(minutes=5), ev_hoje + timedelta(minutes=10)

                    if abrir <= now <= abrir + timedelta(seconds=45) and not self.lista_ativa:
                        self.lista_ativa = nome
                        self.participantes = {}
                        embed = discord.Embed(title=f"{emoji} LISTA ABERTA: {nome}", description="Clique no botão abaixo!", color=0x00FF00)
                        self.mensagem_lista = await canal_presenca.send(content="@everyone", embed=embed, view=PresencaView(self))

                    if fechar <= now <= fechar + timedelta(seconds=45) and self.lista_ativa == nome:
                        await self.distribuir_pontos(nome, pts)
            except Exception as e: print(f"Erro no scheduler: {e}")
            await asyncio.sleep(40)

client = MaratonaBot()

@client.event
async def on_ready():
    print(f"🚀 {client.user} ONLINE!")

@client.event
async def on_message(message):
    if message.author.bot: return
    if message.content == "!ranking":
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch("SELECT nick, pontos FROM ranking ORDER BY pontos DESC LIMIT 25")
        await conn.close()
        embed = discord.Embed(title="🏆 RANKING", description="\n".join([f"**{i+1}º** {r['nick']} — `{r['pontos']} pts`" for i, r in enumerate(rows)]) if rows else "Vazio", color=0xFFD700)
        await message.channel.send(embed=embed)

client.run(TOKEN)
