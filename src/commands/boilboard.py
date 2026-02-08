from pathlib import Path
import sqlite3

import discord
from table2ascii import table2ascii as t2a, PresetStyle

async def boilboard(
        interaction: discord.Interaction,
        user: discord.User,
        boilboard_db: Path
):
    con = sqlite3.connect(str(boilboard_db))
    cur = con.cursor()

    if user is not None:
        res = cur.execute("SELECT * FROM ? WHERE user_id = ?", (user.id,))
    else:
        res = cur.execute("SELECT * FROM ?")



    await interaction.followup.send(
        content=f'"hey {user.mention}" and they\'re boiled 😭😭😭😭',
        file=discord.File(temp_output)
    )