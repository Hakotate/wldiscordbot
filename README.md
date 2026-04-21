[README.md](https://github.com/user-attachments/files/26949470/README.md)
# Warlords Lookup

This project now supports both:

- the original local Flask web app
- a Discord slash-command bot that anyone in an invited server can use
- a paged Discord card system with section switching for stats like Overall, Class & SR, Boosts, Modes, Crafting, Weapons, and Other Fields

## Commands

- `/sr <player>`: fetches Hypixel Warlords stats for a Minecraft username
- `/lb overall`: tracked overall SR leaderboard
- `/lb mage`: tracked Mage SR leaderboard
- `/lb warrior`: tracked Warrior SR leaderboard
- `/lb paladin`: tracked Paladin SR leaderboard
- `/lb shaman`: tracked Shaman SR leaderboard
- `/seasonlb`: seasonal WSR leaderboard (separate from normal SR)

## Files You Care About

- `app.py`: shared stat lookup and formatting logic
- `launcher.py`: launches the original local web app
- `discord_bot.py`: launches the Discord bot
- `player_descriptions.json`: optional manual player descriptions shown inside the Discord cards
- `leaderboard_cache.json`: tracked player cache used by `/lb`
- `season_tracking_players.txt`: list of tracked players for `/seasonlb` (UUIDs or usernames, one per line)
- `seasonlb_state.json`: persistent seasonal tracking state and snapshots
- `OldSeasons/`: archived final season leaderboard images
- `.env.example`: environment variable template

## Quick Start

1. Copy `.env.example` to `.env`.
2. Fill in these values:
   - `HYPIXEL_API_KEY`
   - `DISCORD_BOT_TOKEN`
   - `DISCORD_GUILD_ID` (optional, but recommended while testing)
3. Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

4. Install the Chromium renderer used for the Discord stat cards:

```powershell
py -m playwright install chromium
```

5. Start the bot:

```powershell
py discord_bot.py
```

Or just double-click:

- `run_discord_bot.bat`
- `start_discord_bot_background.bat`

6. If you still want the old local website:

```powershell
py launcher.py
```

## Discord Setup

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a new application.
3. Open the `Bot` tab and create the bot user.
4. Click `Reset Token`, copy the token, and place it in `DISCORD_BOT_TOKEN`.
5. Leave privileged intents off. This bot uses slash commands, so it does not need Message Content intent.
6. In `OAuth2 -> URL Generator`, select:
   - scope: `bot`
   - scope: `applications.commands`
7. In the bot permissions list, enable at least:
   - `View Channels`
   - `Send Messages`
   - `Embed Links`
   - `Read Message History`
8. Open the generated invite URL and add the bot to your server.

Live invite URL for this bot:

[Invite Teishoko WL-SR](https://discord.com/api/oauth2/authorize?client_id=1493361708025254102&permissions=84992&scope=bot%20applications.commands)

## Testing Vs Public Rollout

- If `DISCORD_GUILD_ID` is set to your server ID, slash commands usually appear almost instantly in that server.
- If `DISCORD_GUILD_ID` is blank, commands sync globally. Global Discord slash-command rollout can take a while.
- Good testing flow:
  - test with `DISCORD_GUILD_ID`
  - confirm `/sr` works
  - remove `DISCORD_GUILD_ID`
  - restart the bot for global sync
- `/sr` now uses a dropdown plus arrow buttons to switch between sections on the same player card.
- If Playwright rendering ever fails, the bot automatically falls back to standard Discord embeds instead of failing the command.

## What You Need To Know

- The bot only works while the process is running. If your PC is off, the bot is offline.
- If you want "everyone" to use it reliably, host it on a VPS, cloud VM, or always-on machine.
- Keep `.env` private. Never post your Hypixel API key or Discord bot token.
- Hypixel can rate-limit requests. The bot includes a short in-memory cache to reduce duplicate lookups.
- `/lb` only ranks tracked players the bot has already saved. Saved player data refreshes when it is older than 1 day and that player gets searched again.
- Your existing Flask app still works, so you can keep the website version and the bot in the same repo.
- If you start the background version, you can stop it with `stop_discord_bot.bat`.
