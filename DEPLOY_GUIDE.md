# 🚀 Deploy AIgambit.com to the World

## Step 1: Get a Domain Name (~$10/year)

Choose a registrar and search for your domain:

| Registrar | Price | Link |
|-----------|-------|------|
| **Porkbun** | ~$9/year | https://porkbun.com |
| **Namecheap** | ~$10/year | https://namecheap.com |
| **Cloudflare** | ~$9/year | https://cloudflare.com |

**Suggested domains:**
- `aigambit.com`
- `aigambit.io`
- `playgambit.com`
- `chessclone.com`

---

## Step 2: Deploy to Render.com (FREE)

### 2a. Create a Render Account
1. Go to https://render.com
2. Sign up with GitHub

### 2b. Push Code to GitHub
```bash
cd C:\Users\katle\.vscode\systems\web_chess
git add .
git commit -m "Prepare for deployment"
git push
```

### 2c. Create New Web Service
1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub repo
3. Settings:
   - **Name:** `aigambit`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT app:app`
4. Click **"Create Web Service"**

Your site will be live at: `https://aigambit.onrender.com`

---

## Step 3: Connect Your Domain

### On Render:
1. Go to your service → **Settings** → **Custom Domains**
2. Click **"Add Custom Domain"**
3. Enter: `aigambit.com` and `www.aigambit.com`

### On Your Domain Registrar:
Add these DNS records:

| Type | Name | Value |
|------|------|-------|
| CNAME | `@` | `aigambit.onrender.com` |
| CNAME | `www` | `aigambit.onrender.com` |

Or if CNAME on root isn't supported:
| Type | Name | Value |
|------|------|-------|
| A | `@` | (IP provided by Render) |
| CNAME | `www` | `aigambit.onrender.com` |

---

## Step 4: Enable HTTPS (Automatic)
Render automatically provides free SSL certificates. Your site will be secure at:
- ✅ `https://aigambit.com`
- ✅ `https://www.aigambit.com`

---

## Alternative: Deploy to Railway.app

1. Go to https://railway.app
2. Click **"Start a New Project"**
3. Select **"Deploy from GitHub repo"**
4. Select your `web_chess` repository
5. Railway auto-detects Python and deploys!

Free tier: 500 hours/month

---

## Alternative: Deploy to Fly.io

```bash
# Install flyctl
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"

# Login
fly auth login

# Launch (from web_chess folder)
cd C:\Users\katle\.vscode\systems\web_chess
fly launch

# Deploy
fly deploy
```

---

## Quick Comparison

| Platform | Free Tier | Custom Domain | WebSocket Support |
|----------|-----------|---------------|-------------------|
| **Render** | ✅ Yes | ✅ Free | ✅ Yes |
| **Railway** | ✅ 500hrs/mo | ✅ Free | ✅ Yes |
| **Fly.io** | ✅ 3 VMs | ✅ Free | ✅ Yes |
| **Heroku** | ❌ Paid only | ✅ Free | ✅ Yes |

---

## 🎉 That's It!

Once deployed, anyone in the world can:
1. Type `aigambit.com` in their browser
2. Play chess against AI or other players
3. Join tournaments
4. Track their rating

**Total cost: ~$10/year for the domain (hosting is FREE!)**
