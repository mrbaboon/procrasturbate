# GitHub App Setup Guide

This guide walks you through creating and configuring a GitHub App for Procrasturbate.

## Step 1: Create a GitHub App

1. Go to **GitHub Settings** > **Developer settings** > **GitHub Apps**
2. Click **New GitHub App**
3. Fill in the basic information:
   - **GitHub App name**: `Procrasturbate` (or your preferred name)
   - **Homepage URL**: Your deployment URL (e.g., `https://procrasturbate.example.com`)
   - **Webhook URL**: `https://your-domain.com/webhooks/github`
   - **Webhook secret**: Generate a secure random string (save this for `.env`)

## Step 2: Configure Permissions

Under **Repository permissions**, set:

| Permission | Access |
|------------|--------|
| Contents | Read |
| Pull requests | Read & Write |
| Metadata | Read |

Under **Subscribe to events**, check:

- [x] Pull request
- [x] Issue comment
- [x] Installation
- [x] Installation repositories

## Step 3: Generate Private Key

1. After creating the app, scroll down to **Private keys**
2. Click **Generate a private key**
3. A `.pem` file will be downloaded
4. Save this file securely - you'll need it for configuration

## Step 4: Note Your App ID

Your App ID is displayed at the top of the app settings page. Save this for configuration.

## Step 5: Configure the Application

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and set:

```env
GITHUB_APP_ID=123456  # Your App ID
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----
<paste your entire private key here>
-----END RSA PRIVATE KEY-----"
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here
```

**Note**: The private key must include the BEGIN/END markers and can be on multiple lines.

## Step 6: Install the App

1. Go to your GitHub App's page
2. Click **Install App**
3. Choose the organization or account where you want to install
4. Select which repositories to grant access to:
   - **All repositories** - Reviews all repos
   - **Only select repositories** - Choose specific repos

## Step 7: Expose Webhook Endpoint

For local development, use a tunnel service like [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Update your GitHub App's webhook URL to the ngrok URL:
```
https://abc123.ngrok.io/webhooks/github
```

For production, deploy behind a reverse proxy (nginx, Caddy) with a valid SSL certificate.

## Verifying Setup

1. Open a PR in a configured repository
2. Check the Procrasturbate logs for incoming webhook
3. Verify the review appears on the PR

## Troubleshooting

### Webhook signature validation fails

- Ensure `GITHUB_WEBHOOK_SECRET` matches exactly what you set in GitHub
- Check for extra whitespace or encoding issues

### "Installation not found" errors

- Verify the app is installed on the repository
- Check that `handle_installation_event` ran when the app was installed

### Reviews not posting

- Check Claude API key is valid
- Verify GitHub App has write access to Pull Requests
- Check worker logs for errors

### Rate limiting

GitHub API has rate limits. If you hit them:
- Check `X-RateLimit-Remaining` headers in logs
- Consider caching more aggressively
- Reduce review frequency for high-traffic repos
