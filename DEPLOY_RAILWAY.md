# 🚂 Deploy AIgambit to Railway (FREE)

Railway.app offers **$5 free credits/month** - enough for a chess site!
It also supports installing Stockfish properly.

## Quick Deploy (5 minutes)

### Step 1: Sign Up for Railway
1. Go to **https://railway.app**
2. Click **Login** → **Login with GitHub**
3. Authorize Railway

### Step 2: Create New Project
1. Click **New Project**
2. Select **Deploy from GitHub repo**
3. Find and select: `Katleho-Success/AIgambit`
4. Click **Deploy Now**

### Step 3: Configure (Automatic!)
Railway auto-detects the `nixpacks.toml` file which:
- ✅ Installs Python 3.11
- ✅ Installs Stockfish chess engine
- ✅ Installs all pip requirements

### Step 4: Get Your URL
1. Wait for deployment to complete (2-3 minutes)
2. Click on your service
3. Go to **Settings** → **Networking**
4. Click **Generate Domain**
5. Your site will be at: `https://aigambit-production.up.railway.app` or similar

## 🎉 That's it!

Your chess site with working Stockfish AI is now live!

---

## Why Railway over Render?

| Feature | Railway | Render (Free) |
|---------|---------|---------------|
| System packages (stockfish) | ✅ Yes | ❌ No |
| Free tier | $5/month credits | 750 hours |
| Sleep after inactivity | No | Yes (15 min) |
| Custom domains | ✅ Free | ✅ Free |

---

## Troubleshooting

### Check Logs
1. Click on your service in Railway
2. Click **Deployments** → Latest deployment
3. Click **View Logs**

### If Stockfish still fails
The nixpacks.toml installs stockfish system-wide. Check logs for:
```
✓ Stockfish loaded from: /nix/store/.../stockfish
```

### Redeploy
If you push changes to GitHub, Railway auto-redeploys!

---

## Alternative Free Hosts (if needed)

1. **Fly.io** - $5 free, Docker support
2. **Koyeb** - Free tier, Docker support  
3. **Cyclic.sh** - Free, but no long processes
