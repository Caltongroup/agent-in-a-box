# AgentSoul Cloud Deployment Plan
## Cloudflare + DigitalOcean + Astro

---

## Architecture Overview

```
Customer visits agentsoul.ai (Astro on Cloudflare Pages — free)
        ↓
Cloudflare Worker (API proxy + auth — free tier)
        ↓
DigitalOcean Droplet ($12-24/month per customer)
  nginx (SSL termination)
  Flask web_ui.py (port 5000)
  ChromaDB (RAG)
  PocketBase (sessions + auth)
  llama.cpp or Claude API (inference)
```

---

## Phase 1 — DigitalOcean Droplet Setup

### 1.1 Create the Droplet
- Region: Seattle or San Francisco (closest to Boise)
- Image: Ubuntu 22.04 LTS
- Size: $24/month (4 vCPU, 8GB RAM) for llama.cpp
         $12/month (2 vCPU, 4GB RAM) if using Claude API for inference
- Storage: 50GB SSD (add volume for documents if needed)
- Authentication: SSH key

### 1.2 Run deploy_stack_cloud.sh
Create a cloud variant of deploy_stack.sh with these differences:
- Skip NVMe mount (use /home/pi/data → /home/agent/data)
- Skip Ollama model pull on first run (download on demand)
- Add nginx install and SSL setup
- Add user creation (no 'pi' user on DO)
- Same venv, same Python packages, same PocketBase

### 1.3 nginx Configuration
```nginx
server {
    listen 80;
    server_name client.agentsoul.ai;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name client.agentsoul.ai;

    ssl_certificate /etc/letsencrypt/live/client.agentsoul.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/client.agentsoul.ai/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;          # critical for SSE streaming
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

### 1.4 SSL via Certbot
```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d client.agentsoul.ai
```

---

## Phase 2 — Cloudflare Setup

### 2.1 Domain Setup
- Register agentsoul.ai on Cloudflare (or transfer existing domain)
- Point DNS to Cloudflare nameservers
- Create subdomain per client: iliad.agentsoul.ai, demo-hr.agentsoul.ai, etc.

### 2.2 Cloudflare Worker (API Proxy)
The Worker sits between the Astro frontend and the DO droplet.
It handles:
- CORS headers
- Rate limiting
- Routing subdomains to the right droplet
- Hiding the DO droplet IP

```javascript
// worker.js
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const subdomain = url.hostname.split('.')[0];

    // Route subdomain to correct backend
    const backends = {
      'iliad': 'http://YOUR_DO_IP:5000',
      'demo-hr': 'http://YOUR_DO_IP:5000',
      'demo-hvac': 'http://YOUR_DO_IP_2:5000',
    };

    const backend = backends[subdomain];
    if (!backend) return new Response('Not found', { status: 404 });

    const newUrl = backend + url.pathname + url.search;
    const response = await fetch(newUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });

    return new Response(response.body, {
      status: response.status,
      headers: {
        ...Object.fromEntries(response.headers),
        'Access-Control-Allow-Origin': '*',
      },
    });
  }
};
```

### 2.3 Cloudflare Pages (Astro Frontend)
- Connect GitHub repo to Cloudflare Pages
- Auto-deploys on every push to main
- Free SSL, free CDN, global edge network

---

## Phase 3 — Astro Frontend

### 3.1 Project Setup
```bash
npm create astro@latest agentsoul-site
cd agentsoul-site
npx astro add tailwind
```

### 3.2 Site Structure
```
agentsoul-site/
├── src/
│   ├── pages/
│   │   ├── index.astro        # Landing page
│   │   ├── demo.astro         # Live demo selector
│   │   └── docs.astro         # How it works
│   ├── components/
│   │   ├── Hero.astro         # Main headline + CTA
│   │   ├── ChatWidget.astro   # Embeddable chat UI
│   │   ├── VerticalCard.astro # HR / HVAC / Dental cards
│   │   └── Nav.astro
│   └── layouts/
│       └── Base.astro
├── public/
└── astro.config.mjs
```

### 3.3 Landing Page Sections
1. **Hero** — "Your business. Your AI. Your box."
2. **How it works** — 3 steps: Deploy → Onboard → Ask
3. **Verticals** — HR, HVAC, Dental, Mechanics, Senior Care
4. **Live Demo** — embedded chat widget pointing to demo Pi
5. **Pricing** — Box ($X hardware + setup) / Cloud ($X/month)
6. **GitHub** — link to public agent-in-a-box repo
7. **Contact** — simple form

### 3.4 ChatWidget Component
```astro
---
// ChatWidget.astro
const { endpoint, agentName } = Astro.props;
---
<div class="chat-container">
  <!-- Reuse the HTML from web_ui.py _HTML template -->
  <!-- Point API calls to Cloudflare Worker endpoint -->
</div>
```

---

## Phase 4 — Demo Verticals

Each demo runs on the Orange Pi at your home office via Tailscale.

| Subdomain | Vertical | Documents needed |
|-----------|----------|-----------------|
| demo-hr.agentsoul.ai | HR | Generic employee handbook (no real company data) |
| demo-hvac.agentsoul.ai | HVAC | Equipment manuals, service procedures |
| demo-dental.agentsoul.ai | Dental Practice | Patient FAQ, procedures, insurance guide |
| demo-mechanics.agentsoul.ai | Auto Shop | Labor rates, common repairs, parts guide |

Each demo uses `onboard_wizard.py` with a generic business name and demo documents.

---

## Phase 5 — Inference Strategy by Tier

| Tier | Inference | Cost | Speed | Use case |
|------|-----------|------|-------|----------|
| Pi Box | llama.cpp local | $0/month | 8-15s | Privacy-first clients |
| DO Small | Claude API | ~$5-20/month usage | 1-2s | Demo / SMB cloud |
| DO Large | llama.cpp local | $24/month flat | 3-5s | Enterprise cloud |

For demos: use Claude API (fast, impressive, no GPU needed)
For production cloud: offer both options

---

## Build Order (Next Sessions)

### Session 1 — DO Droplet
- [ ] Create droplet on DigitalOcean
- [ ] Write deploy_stack_cloud.sh
- [ ] Run it, verify stack comes up
- [ ] Install nginx + SSL
- [ ] Test web_ui.py behind nginx

### Session 2 — Cloudflare
- [ ] Register/transfer agentsoul.ai
- [ ] Set up Cloudflare Pages
- [ ] Write and deploy Cloudflare Worker
- [ ] Test subdomain routing

### Session 3 — Astro Site
- [ ] Scaffold Astro + Tailwind project
- [ ] Build landing page
- [ ] Wire ChatWidget to Worker
- [ ] Deploy to Cloudflare Pages

### Session 4 — Demo Verticals
- [ ] Create demo documents for each vertical
- [ ] Run onboard_wizard.py for each
- [ ] Test all demos live
- [ ] Link from landing page

---

## Immediate Next Steps (Before Next Session)

1. Create DigitalOcean account at digitalocean.com
   - Add payment method
   - Generate SSH key if you don't have one: `ssh-keygen -t ed25519`
   - Add SSH key to DO account

2. Register agentsoul.ai on Cloudflare
   - Create free Cloudflare account
   - Register domain (~$10/year)
   - Enable Cloudflare Pages and Workers

3. Install Astro locally on your Mac
   - `npm create astro@latest agentsoul-site`
   - Get familiar with .astro file format

4. Create new GitHub repo: AgentSoul-LLC/agentsoul-site
   - This will be the public frontend repo
   - Connect to Cloudflare Pages for auto-deploy
