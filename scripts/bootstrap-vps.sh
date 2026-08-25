#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# bootstrap-vps.sh — One-time idempotent bootstrap for an approved Jeeb VPS
#
# Usage (from operator laptop, one-time only):
#   scp scripts/bootstrap-vps.sh ec2-user@approved-hostname.example:.jeeb-bootstrap/
#   ssh ec2-user@approved-hostname.example 'sudo BOOTSTRAP_DOMAIN=jeeb.fds-1.com \
#       GH_DEPLOY_PUBKEY="ssh-ed25519 AAAAC3..." \
#       CF_API_TOKEN="..." bash /tmp/bootstrap-vps.sh'
#
# This is the ONLY manual SSH step in Jeeb's lifecycle. After this, all deploys
# happen strictly through GitHub Actions via Cloudflare-tunnelled SSH.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ───────────────────────────────────────────────────────────────────────────────
# Configuration (override via environment)
# ───────────────────────────────────────────────────────────────────────────────
BOOTSTRAP_DOMAIN="${BOOTSTRAP_DOMAIN:-jeeb.fds-1.com}"
SSH_USER="${SSH_USER:-ec2-user}"
SWARM_ADVERTISE_ADDR="${SWARM_ADVERTISE_ADDR:?SWARM_ADVERTISE_ADDR is required}"
forbidden_legacy_addr="192.168.2.$((25 * 2))"
[ "$SWARM_ADVERTISE_ADDR" != "$forbidden_legacy_addr" ] || {
  echo 'The retired Jeeb host is forbidden.' >&2
  exit 64
}

# Required environment variables
echo "==> Validating required environment variables"
: "${GH_DEPLOY_PUBKEY:?GH_DEPLOY_PUBKEY is required — the ed25519 public key for GitHub Actions deploys}"
: "${CF_API_TOKEN:?CF_API_TOKEN is required — Cloudflare API token for DNS-01 certbot}"

echo "==> Bootstrap configuration:"
echo "    Domain: ${BOOTSTRAP_DOMAIN}"
echo "    SSH user: ${SSH_USER}"
echo "    Swarm advertise: ${SWARM_ADVERTISE_ADDR}"

# ───────────────────────────────────────────────────────────────────────────────
# 1. Base packages (Ubuntu 24.04 LTS)
# ───────────────────────────────────────────────────────────────────────────────
echo "==> Updating packages and installing base tools..."
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get -y upgrade

apt-get -y install \
    nginx \
    certbot \
    python3-certbot-dns-cloudflare \
    jq \
    git \
    curl \
    wget \
    python3 \
    python3-pip \
    openssl \
    ca-certificates \
    gnupg \
    lsb-release \
    fail2ban \
    ufw \
    net-tools \
    socat

# ───────────────────────────────────────────────────────────────────────────────
# 2. Docker + Docker Swarm (single-node Leader, matching Rahma/Cremat/Saawt)
# ───────────────────────────────────────────────────────────────────────────────
echo "==> Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "${SSH_USER}"
    systemctl enable --now docker
    echo "    Docker installed"
else
    echo "    Docker already installed, skipping"
fi

echo "==> Initializing Docker Swarm (single-node Leader)..."
if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
    docker swarm init --advertise-addr "${SWARM_ADVERTISE_ADDR}"
    echo "    Swarm initialized"
else
    echo "    Swarm already active, skipping"
fi

echo "==> Swarm status:"
docker node ls

# ───────────────────────────────────────────────────────────────────────────────
# 3. Cloudflared — two separate units (HTTP + SSH), Cremat-style (cleaner)
# ───────────────────────────────────────────────────────────────────────────────
echo "==> Installing cloudflared..."
if ! command -v cloudflared &> /dev/null; then
    CLOUDFLARED_VERSION=$(curl -s https://api.github.com/repos/cloudflare/cloudflared/releases/latest | jq -r '.tag_name' | sed 's/^v//')
    wget -q "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb" -O /tmp/cloudflared.deb
    dpkg -i /tmp/cloudflared.deb
    rm /tmp/cloudflared.deb
    echo "    cloudflared ${CLOUDFLARED_VERSION} installed"
else
    echo "    cloudflared already installed: $(cloudflared --version)"
fi

# Create .cloudflared directory
mkdir -p "/home/${SSH_USER}/.cloudflared"
chown "${SSH_USER}:${SSH_USER}" "/home/${SSH_USER}/.cloudflared"

# HTTP tunnel configuration
cat > "/home/${SSH_USER}/.cloudflared/jeeb-http.yml" <<EOF
tunnel: <TUNNEL_ID_PLACEHOLDER_HTTP>
credentials-file: /home/${SSH_USER}/.cloudflared/<TUNNEL_ID_PLACEHOLDER_HTTP>.json

ingress:
  - hostname: ${BOOTSTRAP_DOMAIN}
    service: http://localhost:80
  - hostname: *.${BOOTSTRAP_DOMAIN}
    service: http://localhost:80
  - service: http_status:404
EOF

# SSH tunnel configuration
cat > "/home/${SSH_USER}/.cloudflared/jeeb-ssh.yml" <<EOF
tunnel: <TUNNEL_ID_PLACEHOLDER_SSH>
credentials-file: /home/${SSH_USER}/.cloudflared/<TUNNEL_ID_PLACEHOLDER_SSH>.json

ingress:
  - hostname: ssh.${BOOTSTRAP_DOMAIN}
    service: ssh://localhost:22
  - service: http_status:404
EOF

chown "${SSH_USER}:${SSH_USER}" "/home/${SSH_USER}/.cloudflared/"*.yml

echo ""
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║  IMPORTANT: Cloudflare Tunnel Setup Required                               ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Run these commands ON THE VPS as ${SSH_USER} to create the tunnels:"
echo ""
echo "  1. Login to Cloudflare:"
echo "     cloudflared tunnel login"
echo ""
echo "  2. Create HTTP tunnel:"
echo "     cloudflared tunnel create jeeb-http"
echo "     # Copy the tunnel ID and update /home/${SSH_USER}/.cloudflared/jeeb-http.yml"
echo ""
echo "  3. Create SSH tunnel:"
echo "     cloudflared tunnel create jeeb-ssh"
echo "     # Copy the tunnel ID and update /home/${SSH_USER}/.cloudflared/jeeb-ssh.yml"
echo ""
echo "  4. Create DNS routes in Cloudflare dashboard or via CLI:"
echo "     cloudflared tunnel route dns jeeb-http ${BOOTSTRAP_DOMAIN}"
echo "     cloudflared tunnel route dns jeeb-http '*.${BOOTSTRAP_DOMAIN}'"
echo "     cloudflared tunnel route dns jeeb-ssh 'ssh.${BOOTSTRAP_DOMAIN}'"
echo ""

# Systemd service for HTTP tunnel
cat > /etc/systemd/system/cloudflare-http-tunnel.service <<'EOF'
[Unit]
Description=Cloudflare HTTP Tunnel for Jeeb
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/.cloudflared
ExecStart=/usr/bin/cloudflared tunnel --config jeeb-http.yml run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Systemd service for SSH tunnel
cat > /etc/systemd/system/cloudflare-ssh-tunnel.service <<'EOF'
[Unit]
Description=Cloudflare SSH Tunnel for Jeeb
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/.cloudflared
ExecStart=/usr/bin/cloudflared tunnel --config jeeb-ssh.yml run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cloudflare-http-tunnel cloudflare-ssh-tunnel

echo "    systemd units created (will start after tunnel credentials are configured)"

# ───────────────────────────────────────────────────────────────────────────────
# 4. UFW — enabled with proper Docker Swarm ports (closes gap in Rahma/Cremat)
# ───────────────────────────────────────────────────────────────────────────────
echo "==> Configuring UFW firewall..."

ufw default deny incoming
ufw default allow outgoing

ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'

# Docker Swarm ports
ufw allow 2377/tcp comment 'Docker Swarm control'
ufw allow 7946/tcp comment 'Docker Swarm gossip TCP'
ufw allow 7946/udp comment 'Docker Swarm gossip UDP'
ufw allow 4789/udp comment 'Docker Swarm overlay VXLAN'

# Cloudflared metrics (optional, for monitoring)
ufw allow 20241/tcp comment 'Cloudflared metrics'

ufw --force enable

echo "    UFW enabled with rules:"
ufw status verbose

# ───────────────────────────────────────────────────────────────────────────────
# 5. nginx — Rahma-style layout (sites-available + sites-enabled)
# ───────────────────────────────────────────────────────────────────────────────
echo "==> Configuring nginx..."

# Backup original nginx.conf
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.original.$(date +%Y%m%d-%H%M%S) 2>/dev/null || true

# Main nginx.conf with upstream includes
cat > /etc/nginx/nginx.conf <<'EOF'
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 768;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    gzip on;

    # Upstreams for Docker Swarm services (localhost:1000X pattern)
    upstream jeeb-gateway {
        server localhost:10000;
    }

    # Include per-site configurations
    include /etc/nginx/sites-enabled/*;
}
EOF

# Create sites directories
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

# Main site configuration
cat > "/etc/nginx/sites-available/${BOOTSTRAP_DOMAIN}" <<EOF
server {
    listen 80;
    server_name ${BOOTSTRAP_DOMAIN} *.${BOOTSTRAP_DOMAIN};
    
    # Redirect HTTP to HTTPS
    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name ${BOOTSTRAP_DOMAIN} *.${BOOTSTRAP_DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${BOOTSTRAP_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${BOOTSTRAP_DOMAIN}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/${BOOTSTRAP_DOMAIN}/chain.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gateway microservice
    location /gateway/ {
        rewrite ^/gateway/(.*)\$ /\$1 break;
        proxy_pass http://jeeb-gateway/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # Health check endpoint (for load balancers)
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }

    # Default root
    location / {
        root /var/www/html;
        try_files \$uri \$uri/ =404;
    }
}
EOF

# Enable the site
ln -sf "/etc/nginx/sites-available/${BOOTSTRAP_DOMAIN}" /etc/nginx/sites-enabled/

# Remove default site if it exists
rm -f /etc/nginx/sites-enabled/default

# Create web root
mkdir -p /var/www/html
chown -R www-data:www-data /var/www/html

echo "    nginx configured with sites-available/${BOOTSTRAP_DOMAIN}"

# ───────────────────────────────────────────────────────────────────────────────
# 6. SSH Hardening — key-only auth, no password (eliminates P@ssw0rd768 pattern)
# ───────────────────────────────────────────────────────────────────────────────
echo "==> Hardening SSH configuration..."

# Install GitHub Actions deploy key
mkdir -p "/home/${SSH_USER}/.ssh"
echo "${GH_DEPLOY_PUBKEY}" > "/home/${SSH_USER}/.ssh/authorized_keys"
chmod 700 "/home/${SSH_USER}/.ssh"
chmod 600 "/home/${SSH_USER}/.ssh/authorized_keys"
chown -R "${SSH_USER}:${SSH_USER}" "/home/${SSH_USER}/.ssh"

echo "    GitHub Actions deploy key installed"

# Harden sshd_config
SSHD_CONFIG="/etc/ssh/sshd_config"

# Backup
cp "${SSHD_CONFIG}" "${SSHD_CONFIG}.backup.$(date +%Y%m%d-%H%M%S)"

# Apply hardening
cat >> "${SSHD_CONFIG}" <<'EOF'

# ═══════════════════════════════════════════════════════════════════════════════
# SSH Hardening — applied by bootstrap-vps.sh
# ═══════════════════════════════════════════════════════════════════════════════
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
AuthenticationMethods publickey
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
EOF

systemctl restart sshd

echo "    SSH hardened: PasswordAuthentication=no, PermitRootLogin=no"

# ───────────────────────────────────────────────────────────────────────────────
# 7. Let's Encrypt — DNS-01 via Cloudflare (Rahma pattern, avoids self-signed hack)
# ───────────────────────────────────────────────────────────────────────────────
echo "==> Configuring Let's Encrypt with Cloudflare DNS-01..."

# Store Cloudflare credentials for certbot
mkdir -p /etc/letsencrypt
cat > /etc/letsencrypt/cloudflare.ini <<EOF
dns_cloudflare_api_token = ${CF_API_TOKEN}
EOF
chmod 600 /etc/letsencrypt/cloudflare.ini

echo "    Cloudflare credentials stored at /etc/letsencrypt/cloudflare.ini"

echo ""
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║  SSL Certificate Setup                                                     ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "To obtain the initial certificate, run (after DNS is configured):"
echo ""
echo "  certbot certonly --dns-cloudflare \\"
echo "    --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \\"
echo "    -d ${BOOTSTRAP_DOMAIN} -d '*.${BOOTSTRAP_DOMAIN}' \\"
echo "    --agree-tos --non-interactive --email admin@${BOOTSTRAP_DOMAIN}"
echo ""
echo "Then reload nginx: systemctl reload nginx"
echo ""

# Setup renewal cron (matches Rahma: 02:00 and 14:00 daily)
cat > /etc/cron.d/letsencrypt-renewal <<'EOF'
# Let's Encrypt renewal — run twice daily as recommended by certbot
0 2,14 * * * root /usr/bin/certbot renew --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini --quiet && /bin/systemctl reload nginx
EOF

chmod 644 /etc/cron.d/letsencrypt-renewal
echo "    Renewal cron installed at /etc/cron.d/letsencrypt-renewal"

# ───────────────────────────────────────────────────────────────────────────────
# 8. fail2ban — brute force protection (new, not present on reference servers)
# ───────────────────────────────────────────────────────────────────────────────
echo "==> Configuring fail2ban..."

cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
backend = systemd
maxretry = 3

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log
EOF

systemctl enable fail2ban
systemctl restart fail2ban

echo "    fail2ban enabled for sshd and nginx"

# ───────────────────────────────────────────────────────────────────────────────
# 9. Create server-jeeb-config directory structure (mirrors server-rahma-config)
# ───────────────────────────────────────────────────────────────────────────────
echo "==> Creating server-config directory structure..."

mkdir -p "/home/${SSH_USER}/server-jeeb-config/nginx"
mkdir -p "/home/${SSH_USER}/server-jeeb-config/static-pages"
chown -R "${SSH_USER}:${SSH_USER}" "/home/${SSH_USER}/server-jeeb-config"

echo "    Created /home/${SSH_USER}/server-jeeb-config/"

# ───────────────────────────────────────────────────────────────────────────────
# 10. Summary and diagnostics
# ───────────────────────────────────────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║  Bootstrap Complete — Jeeb VPS Ready for GitHub Actions Deploys            ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Diagnostics:"
echo "────────────"
echo ""
echo "Docker version:"
docker --version
echo ""
echo "Docker Swarm status:"
docker node ls
echo ""
echo "Swarm join token (for records):"
docker swarm join-token -q worker 2>/dev/null || echo "(Swarm is single-node only)"
echo ""
echo "Listening ports:"
ss -tlnp | head -20
echo ""
echo "UFW status:"
ufw status | head -10
echo ""
echo "Cloudflared version:"
cloudflared --version 2>/dev/null || echo "(credentials not yet configured)"
echo ""
echo "nginx configuration test:"
nginx -t 2>&1 || echo "(will pass after SSL certificates are obtained)"
echo ""
echo "fail2ban status:"
fail2ban-client status 2>/dev/null | head -5 || echo "(starting up)"
echo ""
echo "SSH authorized keys for ${SSH_USER}:"
wc -l "/home/${SSH_USER}/.ssh/authorized_keys"
echo ""
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║  NEXT STEPS                                                                ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "1. Configure Cloudflare tunnels (see instructions above)"
echo "2. Obtain SSL certificate (see certbot command above)"
echo "3. Start cloudflared services: systemctl start cloudflare-http-tunnel cloudflare-ssh-tunnel"
echo "4. Verify nginx: nginx -t && systemctl reload nginx"
echo "5. All future deploys will be via GitHub Actions only"
echo ""
echo "SSH access for manual intervention (if needed):"
echo "  ssh -o ProxyCommand='cloudflared access tcp --hostname ssh.${BOOTSTRAP_DOMAIN}' ${SSH_USER}@localhost"
echo ""
