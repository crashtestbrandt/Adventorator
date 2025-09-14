# Named Cloudflare Tunnel for Adventorator (stable URL)

Quick tunnels (trycloudflare.com) rotate URLs every run, forcing you to update the Discord "Interactions Endpoint URL" each time. Use a named tunnel with a DNS hostname for a stable URL during dev.

## Prereqs
- Cloudflare account and a zone you control (e.g., example.com)
- cloudflared installed

## One-time setup
1. Authenticate and pick your zone in the browser:
   cloudflared login

2. Create a named tunnel:
   cloudflared tunnel create adventorator-dev

3. Route DNS for a stable hostname (replace with your domain):
   cloudflared tunnel route dns adventorator-dev adv-dev.example.com

4. Create or edit ~/.cloudflared/config.yml with the service:
   tunnel: <TUNNEL-UUID>
   credentials-file: /Users/<you>/.cloudflared/<TUNNEL-UUID>.json
   ingress:
     - hostname: adv-dev.example.com
       service: http://127.0.0.1:18000
     - service: http_status:404

5. Start your server:
   make run

6. Run the named tunnel (stable URL):
   make tunnel-dev-run

7. Set Discord Interactions Endpoint once (only updates if hostname changes):
   https://adv-dev.example.com/interactions

## Notes
- For multiple devs, create distinct hostnames (e.g., <user>-adv-dev.example.com) per tunnel.
- You can create a second tunnel (adventorator-staging) pointing to your staging app.
- If your local port differs, update the ingress service.
