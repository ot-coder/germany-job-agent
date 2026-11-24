# Optional: Gmail auto-detection

The tracker can scan your recent emails for application confirmations (*“Thank you for applying”*, *“Vielen Dank für Ihre Bewerbung”*, rejections and interview invitations) and add them to **My applications** for you.

It runs **entirely in your browser**. Your emails go straight from Google to your open dashboard tab, and nothing is uploaded anywhere else. For this to work you need your **own** Google OAuth client ID. It's free and takes about 5 minutes, and it means no shared app ever gets access to your inbox.

## 1. Create a Google Cloud project

1. Open <https://console.cloud.google.com/> and sign in with the Gmail account you apply from.
2. Create a new project, for example `job-agent`.
3. Go to **APIs & Services → Library**, search for **Gmail API**, and click **Enable**.

## 2. Configure the consent screen

1. Go to **Google Auth Platform → Branding** (older consoles call this the *OAuth consent screen*).
2. Enter an app name (`Job Agent`) and your own email address as the support and developer contact.
3. Under **Audience**, choose **External** and leave the publishing status as **Testing**.
4. Under **Test users**, add your own Gmail address.
5. Under **Data access**, add the scope `https://www.googleapis.com/auth/gmail.readonly`.

## 3. Create the client ID

1. Go to **Google Auth Platform → Clients → Create client**.
2. For **Application type**, choose **Web application**.
3. Under **Authorized JavaScript origins**, add your dashboard's origin without the path:
   - `https://<your-github-username>.github.io`
   - `http://127.0.0.1:8787` if you also run it locally
4. You don't need a redirect URI. Click **Create** and copy the **Client ID**. It ends in `.apps.googleusercontent.com`.

## 4. Use it

Open your dashboard, go to **⚙ Settings**, paste the client ID and click **Scan Gmail**. Sign in with the test user you added. Google will warn that the app is unverified. That's expected, because the app is yours and in testing mode.

To skip pasting it on each device, you can put it in `jobs-agent.toml` as `gmail_client_id = "…"`. A client ID is not a secret: it only works from the origins you authorised above.

## Good to know

- **Access is read-only.** The token lasts about an hour and is revoked after each scan.
- **You'll sign in again occasionally.** In testing mode Google asks you to approve again every 7 days or so.
- **Detection is keyword-based.** Check new entries in *My applications* and fix company or position names where needed. Job alerts and *“complete your application”* reminders are ignored.
- **No duplicates.** Each email is only added once, even if you scan repeatedly.
