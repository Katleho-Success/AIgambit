# 🚀 5-Minute Deployment Guide

Your chess platform is ready to deploy! Everything will work including AI games.

## ✨ What's Special
- **Smart Stockfish:** Automatically downloads Linux version on cloud hosting
- **Windows Stockfish:** You keep `stockfish.exe` for local testing
- **Zero Config:** Just deploy and it works!

---

## Deploy to Render.com (100% FREE)

### Step 1: Go to [render.com](https://render.com)
- Click **"Get Started"**
- Sign up with your GitHub account

### Step 2: Create Web Service
1. Click **"New +"** → **"Web Service"**
2. Click **"Connect a repository"**
3. Find and select **`AIgambit`** (or your repo name)
4. Click **"Connect"**

### Step 3: Configure (copy these exactly)

**Name:**
```
aigambit
```

**Build Command:**
```
pip install -r requirements.txt
```

**Start Command:**
```
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT app:app
```

**Environment:** `Python 3`

**Instance Type:** `Free`

### Step 4: Deploy!
- Click **"Create Web Service"**
- Wait 3-5 minutes while it builds
- Your site will be live at: **`https://aigambit.onrender.com`**

---

## 🎉 You're Live!

Share your free URL with anyone:
```
https://aigambit.onrender.com
```

Features that work:
- ✅ User accounts & login
- ✅ Play vs AI (Stockfish Level 1-20)
- ✅ Play online with friends
- ✅ Tournament system
- ✅ Rating & stats tracking
- ✅ AI Clone learning
- ✅ Voice chat

---

## 💡 Tips

**Free Tier Limitations:**
- Sleeps after 15 min of inactivity (wakes up in ~30 seconds on first visit)
- That's it! No other limits.

**Want it faster?**
Upgrade to paid tier ($7/month) for:
- No sleep
- Better performance
- More memory

**Later: Get Custom Domain**
When you're ready (after testing with users):
1. Buy domain at [Porkbun.com](https://porkbun.com) (~$9/year)
2. In Render: Settings → Custom Domain
3. Add your domain and update DNS

---

## 🆘 Need Help?

**Deployment failed?**
Check the logs in Render dashboard - usually just a missing dependency.

**Stockfish not working?**
The Linux version auto-downloads on first AI game. Check logs for download status.

**Can't connect online games?**
WebSockets work on Render - just make sure users have good internet.

---

## 🎮 Test Your Live Site

After deployment, test:
1. Sign up for account
2. Play vs AI (all levels)
3. Open 2 browser tabs to test online multiplayer
4. Create a tournament
5. Share the URL with friends!

---

**That's it! You're live without spending a penny.** 🚀
